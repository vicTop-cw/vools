import contextlib
import time
import re
import os
import logging
import subprocess
import shutil
import tempfile
import platform
from pyspark.sql import SparkSession,DataFrame
import copy
from typing import List, Any, Optional, Callable, Dict, Tuple
from functools import partial,wraps

# pyk 内部依赖（双路径 import：既可作 vools.pyk.look_upon 用，也可被外部直接 import）
try:
    from .configs import pg_credentials, upon_sql_file, share_dir
    from .core import get_spark
    from ..data.vtext import VText as _VText
    from ..data.vtext import VText as _vicText
    from ..data.vtext import VText as _get_content_wrapper
    from ..task.core.models import DagValidationError
except ImportError:  # pragma: no cover - 外部独立运行 fallback
    from vools.pyk.configs import pg_credentials, upon_sql_file, share_dir
    from vools.pyk.core import get_spark
    from vools.data.vtext import VText as _VText
    from vools.data.vtext import VText as _vicText
    from vools.data.vtext import VText as _get_content_wrapper
    from vools.task.core.models import DagValidationError


def _get_content(file_path: str):
    """legacy get_content 兼容：返回带 .text 的 VText。"""
    return _VText(_VText.get_content_fromfile(file_path=file_path, to_text=True))


import json as _json  # noqa: E402


# ============================================================
# CLI 执行通道 —— 常用语言默认命令映射（无枚举限制，用户可自由扩展）
# ============================================================
# task_type 列是 VARCHAR(32) 且**没有 CHECK 枚举约束**（只有 state 有 CHECK），
# 所以 Scala / Java / R / Go / Node / Shell ... 都可自由填。
# 本映射只提供 **默认命令前缀**（lang 匹配时使用），用户可用 payload['cli']['cmd']
# 显式覆盖完整命令行。找不到解释器时 cli_execute 返回错误（不静默跳过）。
LANGUAGE_DEFAULT_CMD: Dict[str, List[str]] = {
    "python": ["python"],
    "py": ["python"],
    "python3": ["python3"],
    "scala": ["scala"],
    "sc": ["scala"],
    "java": ["java"],
    "javac": ["javac"],
    "shell": ["bash"],
    "sh": ["sh"],
    "bash": ["bash"],
    "zsh": ["zsh"],
    "sql": ["psql"],
    "psql": ["psql"],
    "r": ["Rscript"],
    "rscript": ["Rscript"],
    "node": ["node"],
    "js": ["node"],
    "javascript": ["node"],
    "go": ["go", "run"],
    "golang": ["go", "run"],
    "julia": ["julia"],
    "ruby": ["ruby"],
    "perl": ["perl"],
    "php": ["php"],
    "dotnet": ["dotnet"],
    "spark-submit": ["spark-submit"],
    "spark_sql": ["spark-sql"],
    "sparksql": ["spark-sql"],
}

# 各语言常见脚本扩展名（内联 script 时自动判断）
LANGUAGE_EXTENSIONS: Dict[str, str] = {
    "python": ".py", "py": ".py", "python3": ".py",
    "scala": ".scala", "sc": ".scala",
    "java": ".java",
    "shell": ".sh", "sh": ".sh", "bash": ".sh", "zsh": ".sh",
    "sql": ".sql", "psql": ".sql",
    "r": ".r", "rscript": ".r",
    "node": ".js", "js": ".js", "javascript": ".js",
    "go": ".go", "golang": ".go",
    "julia": ".jl",
    "ruby": ".rb",
    "perl": ".pl",
    "php": ".php",
    "spark-submit": ".py",  # spark-submit 常用 .py 或 .jar
}


def _detect_language(task_type: str) -> Optional[str]:
    """根据 task_type 推断语言（归一化到 LANGUAGE_DEFAULT_CMD 的 key）。

    参数可以是 'Scala'、'scala'、'SQL'、'PY'、'Python3' 等大小写混合形式。
    匹配失败返回 None（用户应显式指定 payload['cli']['cmd'] 或 payload['cli']['lang']）。
    """
    if not task_type:
        return None
    t = task_type.strip().lower()
    if t in LANGUAGE_DEFAULT_CMD:
        return t
    # 常见别名：SQL->sql, PY->python, SCALA->scala, JAVA->java ...
    alias = {
        "sql": "sql",
        "py": "python",
        "python": "python",
        "python3": "python3",
        "scala": "scala",
        "java": "java",
        "shell": "shell",
        "bash": "bash",
        "sh": "shell",
        "r": "r",
        "node": "node",
        "go": "go",
        "julia": "julia",
        "ruby": "ruby",
        "perl": "perl",
        "php": "php",
    }
    return alias.get(t, t if t in LANGUAGE_DEFAULT_CMD else None)


def _find_executable(cmd_prefix: List[str]) -> Optional[str]:
    """在 PATH 中查找可执行文件（Windows 上自动补 .exe/.bat/.cmd）。"""
    exe = cmd_prefix[0]
    found = shutil.which(exe)
    if found:
        return found
    # Windows 常见变体
    if os.name == "nt":
        for ext in (".exe", ".bat", ".cmd", ".py"):
            candidate = exe + ext
            f = shutil.which(candidate)
            if f:
                return f
    return None


def jsonb_encode(data: Optional[dict]) -> str:
    """把 dict 编码成 JSON 字符串（用于写入 look_upon 表的 JSONB 列，payload / back_info 共用）。

    规则（业务约定）：
    - key 保留明文；
    - value 用 ``VText.toZipB64`` 压缩编码（返回 "Z:..." 或 "R:..."），
      这样大文本 / 含特殊字符的任务参数也能安全塞进 JSONB。

    Args:
        data: dict；None 返回 "{}"。

    Returns:
        JSON 字符串，如 ``{"sql": "Z:xxxx", "ds": "Z:yyy"}``。
    """
    if not data:
        return "{}"
    out = {}
    for k, v in data.items():
        if v is None:
            raw = ""
        elif isinstance(v, str):
            raw = v
        else:
            # 非字符串 value（int/float/list/dict）统一 JSON 序列化后再压缩
            raw = _json.dumps(v, ensure_ascii=False)
        out[k] = str(_VText(raw).toZipB64())
    return _json.dumps(out, ensure_ascii=False)


def jsonb_decode(raw: Any) -> dict:
    """把 JSONB 内容解回 dict（payload / back_info 共用）。

    兼容三种形态：
    - 已解析的 dict（psycopg2 JSONB）；
    - dict 的 list/tuple 包装（[ {...} ]）；
    - JSON 字符串（JVM JDBC getString 常见返回）。

    Returns:
        dict，value 已用 ``unZipB64`` 还原为原文。
    """
    data = raw
    if isinstance(data, (list, tuple)):
        data = data[0] if data else None
    if isinstance(data, str):
        try:
            data = _json.loads(data)
        except Exception:
            return {}
    if not isinstance(data, dict):
        return {}
    out = {}
    for k, v in data.items():
        out[k] = str(_VText("" if v is None else str(v)).unZipB64())
    return out


# 兼容旧名：payload 列专用别名（逻辑与 jsonb_encode / jsonb_decode 相同，旧调用不破）
payload_encode = jsonb_encode
payload_decode = jsonb_decode
__all__ = ["TaskFunctionError", "TaskAlreadyLocked", "MaxRetriesExceeded", "LookUpon",'LU',"init_tasks","add_tasks","query_tasks","run_until_done",'get_replaced_sql','run_done','run_doneEx','reset_tasks','update_failed_to_pending',
           "jsonb_encode", "jsonb_decode", "payload_encode", "payload_decode",
           "DagValidationError", "register_do", "builtin_do",
           "cli_execute", "LANGUAGE_DEFAULT_CMD", "LANGUAGE_EXTENSIONS",
           "_detect_language", "_find_executable"]
# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
class TaskFunctionError(Exception):    
    """任务函数执行异常"""    
    pass
class TaskAlreadyLocked(Exception):
    """任务已被锁定异常"""
    pass

class MaxRetriesExceeded(Exception):
    """任务重试次数超过上限异常"""
    pass


# ============================================================
# CLI 执行通道 —— 模块级函数（可脱离 LookUpon 直接调用）
# ============================================================
def cli_execute(payload: Dict[str, Any], timeout_sec: Optional[int] = None,
                capture: Optional[bool] = None) -> Dict[str, Any]:
    """用 Python subprocess 调用外部 CLI 执行任务。

    **无语言枚举限制**：task_type 是 VARCHAR(32) 自由字符串，Scala / Java / R /
    Go / Node / Shell / SQL / Python 都可跑。本函数提供 **默认命令前缀推断**
    （payload['cli']['lang'] 或顶层 task_type），找不到解释器时明确报错，不静默跳过。

    参数（payload 里取）：
        顶层（LookUpon 表字段）:
            task_type: 语言提示（如 "SCALA"/"PYTHON"/"SQL"），用于推断默认命令
            value:     任务原始参数（作为 stdin 或 argv 的一部分，见 cli.stdin_from_value）
        payload['cli'] 子 dict:
            lang:        语言名（可选，如 "scala"、"java"、"python"；比 task_type 优先）
            cmd:         完整命令字符串（可选，如 "python run.py --input x.csv"；
                         给了 cmd 就跳过 lang 推断）
            args:        参数列表（可选，追加在 cmd 后面）
            script:      内联脚本内容（可选，写入临时文件后用 lang 解释器执行）
            script_path: 已有脚本路径（可选；与 script 二选一）
            workdir:     工作目录（可选，默认当前进程 cwd）
            env:         环境变量 dict（可选，合并进当前 env）
            stdin:       stdin 输入文本（可选）
            stdin_from_value: bool，默认 True —— 把顶层 value 作为 stdin 传入
            timeout_sec: 超时秒（可选，覆盖顶层 timeout_sec）
            capture:     bool，默认 True —— 是否捕获 stdout/stderr
            shell:       bool，默认 False —— 是否用 shell 解释命令
            check:       bool，默认 False —— 退出码非 0 是否 raise（否则记录 ok=False）

    Returns:
        dict: {
            ok:        bool,
            exit_code: int | None,
            stdout:    str,
            stderr:    str,
            cmd:       str (实际执行的命令),
            duration_ms: float,
            error:     str | None (ok=False 时填失败原因),
            task_type: str | None (推断出的语言),
        }

    典型用法：
        >>> LookUpon(task_fn, dbtable, **cfg).add_tasks(
        ...     tasks=["scala_job"],
        ...     payload={"scala_job": {"cli": {"lang": "scala",
        ...                                    "args": ["--master", "local[*]"]}}},
        ... )
        >>> lu.run_until_done("w1")

        或者直接：
        >>> result = cli_execute({"cli": {"cmd": "python script.py", "args": ["--x", "1"]}})
        >>> assert result["ok"] is True
    """
    # 提取配置
    cli_cfg = payload.get("cli", {}) if isinstance(payload.get("cli", {}), dict) else {}
    task_type = payload.get("task_type", "")
    timeout_sec = cli_cfg.get("timeout_sec", timeout_sec)
    capture = cli_cfg.get("capture", capture) if capture is None else capture
    if capture is None:
        capture = True
    shell = cli_cfg.get("shell", False)
    check = cli_cfg.get("check", False)

    # 1. 组装 argv
    # 优先：显式 cmd 字符串（split 成 argv）
    # 次优：lang 推断默认命令 + args
    # 最后：报错
    cmd_str = cli_cfg.get("cmd", "")
    args_list = cli_cfg.get("args", []) or []
    lang_hint = cli_cfg.get("lang") or _detect_language(task_type)

    if cmd_str:
        # shell=True 时保留整串；否则用 shlex 拆分（不经过 shell，安全）
        if shell:
            argv = [cmd_str] + [str(a) for a in args_list]
            cmd_display = " ".join(argv)
        else:
            import shlex
            argv = shlex.split(cmd_str) + [str(a) for a in args_list]
            cmd_display = " ".join(argv)
        exe = argv[0]
    else:
        # 用 lang 推断默认命令
        if not lang_hint:
            return {
                "ok": False, "exit_code": None, "stdout": "", "stderr": "",
                "cmd": "", "duration_ms": 0.0,
                "error": "cli_execute: 无法推断命令。请设置 payload['cli']['cmd'] "
                         "或 payload['cli']['lang'] / task_type（支持 python/scala/"
                         "java/shell/sql/r/node/go/julia/ruby/perl/php/spark-submit 等）",
                "task_type": task_type,
            }
        default_prefix = LANGUAGE_DEFAULT_CMD.get(lang_hint)
        if not default_prefix:
            return {
                "ok": False, "exit_code": None, "stdout": "", "stderr": "",
                "cmd": "", "duration_ms": 0.0,
                "error": f"cli_execute: 未知语言 '{lang_hint}'。可用: {sorted(LANGUAGE_DEFAULT_CMD.keys())}",
                "task_type": task_type,
            }
        exe = _find_executable(default_prefix)
        if exe is None:
            return {
                "ok": False, "exit_code": None, "stdout": "", "stderr": "",
                "cmd": "", "duration_ms": 0.0,
                "error": f"cli_execute: 找不到解释器 '{default_prefix[0]}'（语言={lang_hint}）。"
                         f"请安装对应运行时或用 payload['cli']['cmd'] 显式指定完整命令。",
                "task_type": task_type,
            }
        argv = [exe] + list(default_prefix[1:]) + [str(a) for a in args_list]
        cmd_display = " ".join(argv)

    # 2. 内联 script 处理：写临时文件 + 追加到 argv
    tmp_path = None
    script = cli_cfg.get("script")
    script_path = cli_cfg.get("script_path")
    if script and not script_path:
        # 临时文件
        ext = LANGUAGE_EXTENSIONS.get(lang_hint or "", ".tmp")
        fd, tmp_path = tempfile.mkstemp(suffix=ext, prefix="lookupon_cli_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(script)
        except Exception:
            pass
        script_path = tmp_path
    if script_path:
        if shell:
            argv = argv + [str(script_path)]
        else:
            argv = argv + [str(script_path)]
        cmd_display = " ".join(argv)

    # 3. 工作目录
    workdir = cli_cfg.get("workdir") or None
    if workdir and not os.path.isdir(workdir):
        return {
            "ok": False, "exit_code": None, "stdout": "", "stderr": "",
            "cmd": cmd_display, "duration_ms": 0.0,
            "error": f"cli_execute: workdir 不存在: {workdir}",
            "task_type": task_type,
        }

    # 4. 环境变量
    env = os.environ.copy()
    env_overrides = cli_cfg.get("env", {}) or {}
    if isinstance(env_overrides, dict):
        for k, v in env_overrides.items():
            env[str(k)] = str(v)

    # 5. stdin
    stdin_data = cli_cfg.get("stdin")
    if stdin_data is None and cli_cfg.get("stdin_from_value", True) and payload.get("value"):
        stdin_data = str(payload.get("value"))

    # 6. 执行
    start = time.time()
    try:
        proc = subprocess.run(
            argv if not shell else " ".join(argv),
            cwd=workdir,
            env=env,
            input=stdin_data,
            capture_output=capture,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
            shell=shell,
        )
        duration_ms = (time.time() - start) * 1000
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        exit_code = proc.returncode
        ok = (exit_code == 0)
        if check and not ok:
            raise subprocess.CalledProcessError(exit_code, argv, output=stdout, stderr=stderr)
        return {
            "ok": ok,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "cmd": cmd_display,
            "duration_ms": round(duration_ms, 2),
            "error": None if ok else f"退出码非 0 ({exit_code})",
            "task_type": lang_hint or task_type,
        }
    except subprocess.TimeoutExpired as e:
        duration_ms = (time.time() - start) * 1000
        return {
            "ok": False, "exit_code": None,
            "stdout": str(e.stdout or ""), "stderr": str(e.stderr or ""),
            "cmd": cmd_display, "duration_ms": round(duration_ms, 2),
            "error": f"执行超时（{timeout_sec} 秒）",
            "task_type": lang_hint or task_type,
        }
    except subprocess.CalledProcessError as e:
        duration_ms = (time.time() - start) * 1000
        return {
            "ok": False, "exit_code": e.returncode,
            "stdout": str(e.output or ""), "stderr": str(e.stderr or ""),
            "cmd": cmd_display, "duration_ms": round(duration_ms, 2),
            "error": f"check=True 且退出码非 0 ({e.returncode})",
            "task_type": lang_hint or task_type,
        }
    except FileNotFoundError as e:
        duration_ms = (time.time() - start) * 1000
        return {
            "ok": False, "exit_code": None, "stdout": "", "stderr": str(e),
            "cmd": cmd_display, "duration_ms": round(duration_ms, 2),
            "error": f"可执行文件不存在: {e.filename}",
            "task_type": lang_hint or task_type,
        }
    except Exception as e:
        duration_ms = (time.time() - start) * 1000
        return {
            "ok": False, "exit_code": None, "stdout": "", "stderr": str(e),
            "cmd": cmd_display, "duration_ms": round(duration_ms, 2),
            "error": f"cli_execute 执行异常: {e}",
            "task_type": lang_hint or task_type,
        }
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


class LookUpon:
    # 'do' 内置 py 单参函数注册表：name -> fn(ctx: dict) -> Any
    _DO_REGISTRY: Dict[str, Callable[[dict], Any]] = {}

    @classmethod
    def register_do(cls, name: str, fn: Callable[[dict], Any]) -> Callable[[dict], Any]:
        """注册 'do' 内置 py 单参函数（payload 含非空 'do' key 时执行）。

        Args:
            name: do 名称（写入 payload 的 'do' key）。
            fn:   单参函数，签名 ``fn(ctx: dict) -> Any``；
                  ctx 为解码后的 payload（已 ``setdefault('value', value)`` 补上任务值）。

        Returns:
            原函数 fn（可兼作装饰器使用）。
        """
        if not name or not str(name).strip():
            raise ValueError("do 名称不能为空")
        cls._DO_REGISTRY[str(name).strip()] = fn
        return fn

    @classmethod
    def builtin_do(cls, name: str) -> Callable[[Callable[[dict], Any]], Callable[[dict], Any]]:
        """装饰器：把函数注册为 'do' 内置 py 单参函数。

        Example:
            @LookUpon.builtin_do('py_func')
            def py_func(ctx: dict):
                return ctx['value'] * 2
        """
        def decorator(fn: Callable[[dict], Any]) -> Callable[[dict], Any]:
            return cls.register_do(name, fn)
        return decorator

    def __init__(self, task_function: Callable[[str], Any], dbtable: str, 
                 init: bool = False, tasks: Optional[List[str]] = None,
                 url: Optional[str] = None, user: Optional[str] = None, 
                 password: Optional[str] = None, driver: Optional[str] = None, 
                 spark: Optional[SparkSession] = None, dbName: str = "public",
                 max_retries: int = 3, retry_delay_min: int = 5, drop_if_exists: bool = False):
        """
        spark: SparkSession 实例
        task_function: 用户提供的单参数函数，接受任务值作为参数
        dbtable: 数据库表名
        url: JDBC 连接URL
        user: 数据库用户名
        password: 数据库密码
        dbName: 数据库名 (默认public)
        init: 是否初始化表
        tasks: 初始任务列表
        max_retries: 任务最大重试次数
        retry_delay_min: 重试延迟时间(分钟)
        """
        # 配置Spark会话
        self.spark = spark or self.__class__._get_spark_session()
        
        self.task_function = task_function
        dct = self.__class__._get_default_properties()
        self.url = url or dct.get("url")
        self.user = user or dct.get("user")
        self.password = password or dct.get("password")
        self.driver = driver or dct.get("driver")
        self.dbName = dbName
        self.max_retries = max_retries
        self.retry_delay_min = retry_delay_min
        
        # 获取JVM环境
        self.jvm = self.spark.sparkContext._gateway.jvm
        self.jvm.Class.forName(self.driver)
        self._conn = None
        # 处理dbtable格式
        if '.' in dbtable:
            self.dbtable = dbtable
        else:
            self.dbtable = f"{self.dbName}.{dbtable}"
        
        # 初始化数据库表
        if init:
            if drop_if_exists:
                self.drop()
            self._init_table()
            if tasks:
                self.add_tasks(tasks)
        
        self._conn = None
        
    def drop(self):
        """删除任务表"""
        sql = f"DROP TABLE IF EXISTS {self.dbtable}"
        self._execute_sql(sql, commit=True)
        logger.info(f"删除表 {self.dbtable} 成功")
    
    def execute_sql(self, sql: str, params: Optional[List[Any]] = None) -> Any:
        """执行SQL语句,自动提交"""
        results = self._execute_sql(sql, params, commit=True)
        if len(results) == 1:
            return results[0]
        return results
    
    @property
    def properties(self) -> Dict[str, str]:
        """获取数据库连接属性"""
        return {
            "url": self.url,
            "user": self.user,
            "password": self.password,
            "driver": self.driver  
        }
        
    def query(self, sql: str = "") -> Any:
        """执行查询并返回DataFrame"""
        # 处理不同形式的表名
        if not sql:
            sql = f"SELECT * FROM {self.dbtable}"
        
        # 简化表名查询
        if re.match(r"^[a-z][a-z_0-9]+\.[a-z_0-9]+$", sql.lower()):
            sql = f"SELECT * FROM {sql}"
        elif re.match(r"^[a-z][a-z_0-9]+$", sql.lower()):
            sql = f"SELECT * FROM public.{sql}"
        
        properties = copy.deepcopy(self.properties)
        properties["query"] = sql
        return self.spark.read.format("jdbc").options(**properties).load()
    
    def _result_set_to_list(self, result_set) -> list:
        """将JDBC ResultSet转换为Python列表"""
        try:
            meta_data = result_set.getMetaData()
            column_count = meta_data.getColumnCount()
            
            results = []
            while result_set.next():
                row = []
                for i in range(1, column_count + 1):
                    value = result_set.getObject(i)
                    row.append(value)
                results.append(row)
            
            return results
        except Exception as e:
            logger.error(f"结果集转换失败: {str(e)}")
            return []
    
    def _get_connection(self):
        """获取数据库连接（直接连接）"""
        try:
            if not self._conn or self._conn.isClosed():
                conn = self.jvm.java.sql.DriverManager.getConnection(
                    self.url, self.user, self.password)
                logger.debug("获取数据库连接成功")
                self._conn = conn
                return conn
            return self._conn
        except Exception as e:
            logger.error(f"获取数据库连接失败: {str(e)}")
            raise e
    
    def _execute_sql(self, sql: str, params: Optional[List[Any]] = None, 
                commit: bool = False) -> List[Any]:
        """安全执行SQL语句并返回结果"""
        conn = None
        stmt = None
        try:
            conn = self._get_connection()
            conn.setAutoCommit(False)
            
            results = []
            
            # 检查是否有参数
            if params and len(params) > 0:
                # 使用参数化查询
                stmt = conn.prepareStatement(sql)
                
                # 绑定参数
                for i, param in enumerate(params, 1):
                    if isinstance(param, str):
                        stmt.setString(i, param)
                    elif isinstance(param, int):
                        stmt.setInt(i, param)
                    elif isinstance(param, float):
                        stmt.setDouble(i, param)
                    else:
                        stmt.setObject(i, param)
                
                # 执行
                if sql.strip().upper().startswith("SELECT"):
                    rs = stmt.executeQuery()
                    results = [self._result_set_to_list(rs)]
                else:
                    count = stmt.executeUpdate()
                    results = [count]
                    
                stmt.close()
            else:
                # 无参数查询
                stmt = conn.createStatement()
                if sql.strip().upper().startswith("SELECT"):
                    rs = stmt.executeQuery(sql)
                    results = [self._result_set_to_list(rs)]
                else:
                    count = stmt.executeUpdate(sql)
                    results = [count]
                stmt.close()
            
            # 提交事务
            if commit:
                conn.commit()

                
            return results
            
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"SQL执行错误: {str(e)}\nSQL: {sql}\nParams: {params}")
            raise e
        finally:
            # 注意：不要关闭连接，保持连接用于后续操作
            # 连接在close()方法中统一关闭
            if stmt is not None:
                try:
                    stmt.close()
                except Exception:
                    pass

    
    def _init_table(self):
        """初始化任务表结构（一次性建好，无 ALTER 补列）"""
        sql = f"""
        CREATE TABLE IF NOT EXISTS {self.dbtable} (
            task_id SERIAL PRIMARY KEY,
            task_name VARCHAR(256) NOT NULL UNIQUE,
            value VARCHAR(200),
            task_type VARCHAR(32) NOT NULL DEFAULT 'SQL',
            team VARCHAR(128) NOT NULL DEFAULT '',
            group_name VARCHAR(128) NOT NULL DEFAULT '',
            owner VARCHAR(64) NOT NULL DEFAULT '',
            queue VARCHAR(64) NOT NULL DEFAULT '',
            tags JSONB NOT NULL DEFAULT '[]',
            state VARCHAR(20) NOT NULL CHECK (state IN ('PENDING','LOCKED','RUNNING','COMPLETED','FAILED','RETRY_PENDING')) DEFAULT 'PENDING',
            deps INTEGER[],
            deps_task_tables JSONB,
            priority INT NOT NULL DEFAULT 0,
            timeout_min INT NOT NULL DEFAULT 60,
            retry_delay_min INT NOT NULL DEFAULT 5,
            retry_count INT NOT NULL DEFAULT 0,
            max_retries INT NOT NULL DEFAULT {self.max_retries},
            worker_id VARCHAR(50),
            lock_time TIMESTAMP,
            start_time TIMESTAMP,
            end_time TIMESTAMP,
            scheduled_at TIMESTAMP,
            expire_time TIMESTAMP,
            cancel_requested BOOLEAN NOT NULL DEFAULT FALSE,
            version INT NOT NULL DEFAULT 1,
            last_err TEXT,
            back_info JSONB,
            payload JSONB,
            extra_desc TEXT,
            push_back_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_state ON {self.dbtable}(state);
        CREATE INDEX IF NOT EXISTS idx_lock_time ON {self.dbtable}(lock_time);
        CREATE INDEX IF NOT EXISTS idx_task_name ON {self.dbtable}(task_name);
        CREATE INDEX IF NOT EXISTS idx_deps ON {self.dbtable} USING GIN (deps);
        CREATE INDEX IF NOT EXISTS idx_deps_task_tables ON {self.dbtable} USING GIN (deps_task_tables);
        CREATE INDEX IF NOT EXISTS idx_task_type ON {self.dbtable}(task_type);
        CREATE INDEX IF NOT EXISTS idx_team ON {self.dbtable}(team);
        CREATE INDEX IF NOT EXISTS idx_group_name ON {self.dbtable}(group_name);
        CREATE INDEX IF NOT EXISTS idx_owner ON {self.dbtable}(owner);
        CREATE INDEX IF NOT EXISTS idx_queue ON {self.dbtable}(queue);
        CREATE INDEX IF NOT EXISTS idx_priority ON {self.dbtable}(priority);
        CREATE INDEX IF NOT EXISTS idx_expire_time ON {self.dbtable}(expire_time);
        CREATE INDEX IF NOT EXISTS idx_scheduled_at ON {self.dbtable}(scheduled_at);
        CREATE INDEX IF NOT EXISTS idx_cancel_requested ON {self.dbtable}(cancel_requested) WHERE cancel_requested = true;
        """
        # 确保建表操作提交
        try:
            self._execute_sql(sql, commit=True)
            logger.info(f"初始化表 {self.dbtable} 完成")
            
            # 验证表是否真正创建成功
            verify_sql = f"SELECT 1 FROM {self.dbtable} LIMIT 1"
            self._execute_sql(verify_sql)
            logger.info(f"验证表 {self.dbtable} 存在成功")
            
        except Exception as e:
            logger.error(f"表初始化失败: {str(e)}")
            raise e
    
    # 在初始化后添加验证
    def _verify_table_exists(self):
        """验证表是否真正存在"""
        try:
            check_sql = f"""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_schema = '{self.dbName}' 
                AND table_name = '{self.dbtable.split('.')[1]}'
            )
            """
            result = self._execute_sql(check_sql, commit=True)
            exists = result[0][0][0] if result else False
            logger.info(f"表存在验证结果: {exists}")
            return exists
        except Exception as e:
            logger.error(f"表验证失败: {str(e)}")
            return False
    
    def add_tasks(self, tasks: List[Any], deps: Optional[Dict[str, List[int]]] = None,
                  deps_task_tables: Optional[Dict[str, Dict[str, Any]]] = None,
                  default_task_type: str = "SQL", default_team: str = "",
                  default_group: str = "", default_owner: str = "",
                  default_queue: str = "", default_priority: int = 0,
                  default_timeout_min: int = 60, default_retry_delay_min: int = 5):
        """安全添加新任务到系统。

        Args:
            tasks: 任务列表。每项可以是 str（简写，task_name=value=str，其余走默认值）
                   或 dict（完整字段：task_name 必填，value/task_type/team/group_name/owner/
                   queue/tags/priority/timeout_min/retry_delay_min/max_retries/scheduled_at/
                   expire_time/payload/deps/deps_task_tables 可选）。
            deps:  可选同表依赖映射 {task_name: [依赖 task_id, ...]}；未给出的任务 deps 为 NULL。
            deps_task_tables: 可选跨表依赖映射 {task_name: {other_table: [task_id, ...]}}；
                值为 ["all"] 表示该表所有任务须 COMPLETED 才能领取；未给出的任务为 NULL。
            default_*: 当任务 dict 里未指定这些字段时的默认值。

        Raises:
            DagValidationError: 写入后 DAG 校验失败（依赖缺失 / 存在环）。
        """
        if not tasks:
            return
        deps = deps or {}
        deps_task_tables = deps_task_tables or {}

        # 归一化 tasks 为完整 dict 列表
        normalized = []
        for t in tasks:
            if isinstance(t, str):
                normalized.append({
                    "task_name": str(t),
                    "value": str(t),
                })
            elif isinstance(t, dict):
                if not t.get("task_name"):
                    raise ValueError("add_tasks 的 dict 任务必须包含 task_name")
                normalized.append(t)
            else:
                raise TypeError(f"add_tasks 只接受 str 或 dict，收到 {type(t)}")

        # 补默认值
        for d in normalized:
            d.setdefault("value", d["task_name"])
            d.setdefault("task_type", default_task_type)
            d.setdefault("team", default_team)
            d.setdefault("group_name", default_group)
            d.setdefault("owner", default_owner)
            d.setdefault("queue", default_queue)
            d.setdefault("tags", [])
            d.setdefault("priority", default_priority)
            d.setdefault("timeout_min", default_timeout_min)
            d.setdefault("retry_delay_min", default_retry_delay_min)
            d.setdefault("max_retries", self.max_retries)

        # 获取现有任务
        existing = self._query_values(
            f"SELECT task_name FROM {self.dbtable} "
            "WHERE state NOT IN ('COMPLETED', 'FAILED')"
        )

        # 过滤新任务（按 task_name 判重）
        new_tasks = [d for d in normalized if str(d["task_name"]) not in existing]

        # 合并 deps / deps_task_tables（dict 内部字段优先，外部参数兜底）
        for d in new_tasks:
            tn = str(d["task_name"])
            if "deps" not in d and tn in deps:
                d["deps"] = deps[tn]
            if "deps_task_tables" not in d and tn in deps_task_tables:
                d["deps_task_tables"] = deps_task_tables[tn]

        if not new_tasks:
            return

        # 批量插入
        batch_size = 100
        for i in range(0, len(new_tasks), batch_size):
            batch = new_tasks[i:i + batch_size]
            self._batch_insert_tasks(batch)

        # 写入后校验 deps DAG（依赖存在性 + 无环）；校验失败直接抛出
        self._validate_deps_dag()

        logger.info(f"成功添加 {len(new_tasks)} 个新任务")

    def _batch_insert_tasks(self, tasks: List[Dict[str, Any]]):
        """执行批量插入任务（支持全部扩展字段）"""
        if not tasks:
            return
        import json as _json

        conn = None
        try:
            conn = self._get_connection()
            conn.setAutoCommit(False)

            # 完整字段 INSERT，ON CONFLICT 以 task_name 为唯一冲突目标
            sql = f"""INSERT INTO {self.dbtable}
                (task_name, value, task_type, team, group_name, owner, queue, tags,
                 deps, deps_task_tables, priority, timeout_min, retry_delay_min,
                 max_retries, scheduled_at, expire_time, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, CAST(? AS jsonb),
                        CAST(? AS integer[]), CAST(? AS jsonb), ?, ?, ?,
                        ?, ?, ?, CAST(? AS jsonb))
                ON CONFLICT (task_name) DO NOTHING"""

            stmt = conn.prepareStatement(sql)
            jt = self.jvm.java.sql.Types

            for d in tasks:
                stmt.setString(1, str(d.get("task_name")))
                stmt.setString(2, str(d.get("value", "")))
                stmt.setString(3, str(d.get("task_type", "SQL")))
                stmt.setString(4, str(d.get("team", "")))
                stmt.setString(5, str(d.get("group_name", "")))
                stmt.setString(6, str(d.get("owner", "")))
                stmt.setString(7, str(d.get("queue", "")))
                tags = d.get("tags") or []
                stmt.setString(8, _json.dumps(tags, ensure_ascii=False))
                dep_ids = d.get("deps")
                if dep_ids:
                    stmt.setString(9, "{" + ",".join(str(int(x)) for x in dep_ids) + "}")
                else:
                    stmt.setNull(9, jt.ARRAY)
                dtt = d.get("deps_task_tables")
                if dtt:
                    stmt.setString(10, _json.dumps(dtt, ensure_ascii=False))
                else:
                    stmt.setNull(10, jt.VARCHAR)
                stmt.setInt(11, int(d.get("priority", 0)))
                stmt.setInt(12, int(d.get("timeout_min", 60)))
                stmt.setInt(13, int(d.get("retry_delay_min", 5)))
                stmt.setInt(14, int(d.get("max_retries", self.max_retries)))
                sched = d.get("scheduled_at")
                if sched is not None:
                    stmt.setTimestamp(15, self._to_ts(sched))
                else:
                    stmt.setNull(15, jt.TIMESTAMP)
                exp = d.get("expire_time")
                if exp is not None:
                    stmt.setTimestamp(16, self._to_ts(exp))
                else:
                    stmt.setNull(16, jt.TIMESTAMP)
                payload = d.get("payload")
                if payload:
                    stmt.setString(17, jsonb_encode(payload))
                else:
                    stmt.setNull(17, jt.VARCHAR)
                stmt.addBatch()

            stmt.executeBatch()
            conn.commit()
            logger.debug(f"批量插入 {len(tasks)} 个任务成功")

        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"批量插入失败: {str(e)}")
            self._fallback_insert_tasks(tasks)
        finally:
            if conn:
                conn.close()

    def _fallback_insert_tasks(self, tasks: List[Dict[str, Any]]):
        """回退方法：逐条插入任务（支持全部扩展字段）"""
        for d in tasks:
            try:
                import json as _json
                sql = f"""INSERT INTO {self.dbtable}
                    (task_name, value, task_type, team, group_name, owner, queue, tags,
                     deps, deps_task_tables, priority, timeout_min, retry_delay_min,
                     max_retries, scheduled_at, expire_time, payload)
                    VALUES (?, ?, ?, ?, ?, ?, ?, CAST(? AS jsonb),
                            CAST(? AS integer[]), CAST(? AS jsonb), ?, ?, ?,
                            ?, ?, ?, CAST(? AS jsonb))
                    ON CONFLICT (task_name) DO NOTHING"""
                params = [
                    str(d.get("task_name")),
                    str(d.get("value", "")),
                    str(d.get("task_type", "SQL")),
                    str(d.get("team", "")),
                    str(d.get("group_name", "")),
                    str(d.get("owner", "")),
                    str(d.get("queue", "")),
                    _json.dumps(d.get("tags") or [], ensure_ascii=False),
                ]
                dep_ids = d.get("deps")
                if dep_ids:
                    params.append("{" + ",".join(str(int(x)) for x in dep_ids) + "}")
                else:
                    params.append(None)
                dtt = d.get("deps_task_tables")
                if dtt:
                    params.append(_json.dumps(dtt, ensure_ascii=False))
                else:
                    params.append(None)
                params.extend([
                    int(d.get("priority", 0)),
                    int(d.get("timeout_min", 60)),
                    int(d.get("retry_delay_min", 5)),
                    int(d.get("max_retries", self.max_retries)),
                ])
                sched = d.get("scheduled_at")
                params.append(self._to_ts(sched) if sched is not None else None)
                exp = d.get("expire_time")
                params.append(self._to_ts(exp) if exp is not None else None)
                payload = d.get("payload")
                params.append(jsonb_encode(payload) if payload else None)

                self._execute_sql(sql, params=params, commit=True)
            except Exception as e:
                logger.error(f"任务 {d.get('task_name')} 插入失败: {str(e)}")

    def _to_ts(self, val: Any):
        """把 datetime / 'YYYY-MM-DD HH:MM:SS' / epoch 秒 转成 Java Timestamp。"""
        if val is None:
            return None
        from datetime import datetime as _dt
        if isinstance(val, _dt):
            pass
        elif isinstance(val, str):
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
                try:
                    val = _dt.strptime(val, fmt)
                    break
                except ValueError:
                    continue
            else:
                try:
                    val = _dt.fromtimestamp(float(val))
                except Exception:
                    return None
        elif isinstance(val, (int, float)):
            val = _dt.fromtimestamp(float(val))
        else:
            return None
        # 用 java.sql.Timestamp 保证 PG JDBC 正确写入
        try:
            ts_cls = self.jvm.java.sql.Timestamp
            return ts_cls(val.year, val.month - 1, val.day,
                          val.hour, val.minute, int(val.second),
                          val.microsecond // 1000)
        except Exception:
            # 兜底：普通 datetime 也能被 psycopg2 接受
            return val
    
    def _validate_deps_dag(self) -> None:
        """校验表中已配置 deps 的任务：依赖存在性 + 无环（DFS，参考 vools.task.core.queue._validate_dag）。

        依赖规则：
        - 每个任务 deps 里引用的 dep_id 必须在表中存在；
        - 依赖关系不能成环（DFS 遍历检测）。

        Raises:
            DagValidationError: 存在缺失依赖或环时抛出。
        """
        rows = self._execute_sql(
            f"SELECT task_id, task_name, array_to_json(deps) AS deps FROM {self.dbtable} "
            "WHERE deps IS NOT NULL AND array_length(deps, 1) > 0",
            commit=True,
        )
        if not rows or not rows[0]:
            return
        
        # _execute_sql 的 SELECT 返回 [[ [task_id, task_name, deps_json], ... ]]
        id2name: Dict[int, str] = {}
        deps_map: Dict[int, List[int]] = {}
        for row in rows[0]:
            task_id, task_name, deps_json = row[0], row[1], row[2]
            id2name[int(task_id)] = str(task_name)
            try:
                dep_ids = [int(x) for x in _json.loads(str(deps_json))]
            except Exception:
                dep_ids = []
            deps_map[int(task_id)] = dep_ids
        
        # 依赖存在性校验
        for tid, dep_ids in deps_map.items():
            for dep_id in dep_ids:
                if dep_id not in id2name:
                    raise DagValidationError(
                        f"依赖任务 {dep_id} 不存在 (task {tid}: {id2name.get(tid)})"
                    )
        
        # 环检测（DFS）
        visited: set = set()
        
        def dfs(current_id: int, chain: set) -> None:
            if current_id in chain:
                raise DagValidationError(
                    f"检测到循环依赖: task {current_id} ({id2name.get(current_id)}) "
                    f"已出现在依赖链 {sorted(chain)} 中"
                )
            if current_id in visited:
                return
            visited.add(current_id)
            for dep_id in deps_map.get(current_id, []):
                dfs(dep_id, chain | {current_id})
        
        for tid in deps_map:
            dfs(tid, set())
    
    def _query_values(self, sql: str, params: Optional[List[Any]] = None) -> List[str]:
        """执行查询并返回值列表"""
        try:
            # 执行查询
            results = self._execute_sql(sql, params=params)
            if not results:
                return []
                
            # 提取值
            values = []
            for result in results:
                for row in result:
                    if row:
                        values.append(str(row[0]))
            return values
        except Exception as e:
            logger.error(f"查询错误: {str(e)}")
            return []
    
    def is_all_done(self) -> bool:
        """检查所有任务是否已完成"""
        count = self._query_values(
            f"SELECT task_name FROM {self.dbtable} "
            "WHERE state IN ('PENDING', 'LOCKED', 'RUNNING', 'RETRY_PENDING')"
        )
        return len(count) == 0
    
    @contextlib.contextmanager
    def _transaction(self):
        """事务上下文管理器"""
        conn = self._get_connection()
        conn.setAutoCommit(False)
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            # 注意：不关闭连接，保持连接活跃
            pass
    
    def _acquire_task(self, worker_id: str, timeout_min: int = 5,states: Optional[str] = None) -> Optional[str]:
        """获取并锁定一个任务（带事务管理）"""
        try:
            with self._transaction() as conn:
                # 清理过期锁
                self.clean_stale_locks(timeout_min * 2)
                states = states.split(",") if states else ['PENDING','RETRY_PENDING']
                states_str = ",".join(f"'{s}'" for s in states)
                # 查询可处理任务并锁定（deps 依赖门控：NULL/空数组视为无依赖；
                # 非空时仅当所有依赖存在且 state='COMPLETED' 才可领取；
                # deps_task_tables 跨表门控在 Python 侧校验，避免动态表名注入）
                sql = f"""
                SELECT t.task_name 
                FROM {self.dbtable} t 
                WHERE t.state IN ({states_str})
                AND (t.deps IS NULL OR NOT EXISTS (
                    SELECT 1 FROM unnest(t.deps) AS d(dep_id)
                    LEFT JOIN {self.dbtable} dep ON dep.task_id = d.dep_id
                    WHERE dep.task_id IS NULL OR dep.state <> 'COMPLETED'
                ))
                ORDER BY t.task_name
                LIMIT 1
                FOR UPDATE SKIP LOCKED
                """
                
                stmt = conn.prepareStatement(sql)
                rs = stmt.executeQuery()
                
                if not rs.next():
                    return None
                
                task_name = rs.getString(1)
                
                # 跨表依赖校验（deps_task_tables JSONB）：仅当所有其它表的依赖任务 COMPLETED 才可领取
                if not self._cross_deps_satisfied(task_name):
                    return None
                
                # 立即锁定任务
                lock_sql = f"""
                UPDATE {self.dbtable} 
                SET 
                    state = 'LOCKED',
                    lock_time = CURRENT_TIMESTAMP,
                    worker_id = ?,
                    version = version + 1
                WHERE task_name = ?
                """
                
                lock_stmt = conn.prepareStatement(lock_sql)
                lock_stmt.setString(1, worker_id)
                lock_stmt.setString(2, task_name)
                lock_stmt.executeUpdate()
                
                # 提交事务前返回任务名称
                return task_name
        except Exception as e:
            logger.error(f"获取任务失败: {str(e)}")
            return None
    
    def _cross_deps_satisfied(self, task_name: str) -> bool:
        """校验任务的跨表依赖（deps_task_tables JSONB）是否满足。

        JSONB 格式：{"other_table": [task_id, ...]}，或 {"other_table": ["all"]}。
        - "all"：该表所有任务须 COMPLETED
        - [id...]：列表中每个 task_id 在该表中须 COMPLETED
        - NULL / '{}'：视为无跨表依赖，直接放行

        Args:
            task_name: 当前任务 task_name

        Returns:
            True 表示可领取，False 表示仍有跨表依赖未完成。
        """
        rows = self._execute_sql(
            f"SELECT deps_task_tables::text FROM {self.dbtable} WHERE task_name = ?",
            params=[str(task_name)],
            commit=True,
        )
        if not rows or not rows[0]:
            return True
        dtt = rows[0][0][0] if rows[0][0] else None
        if not dtt:
            return True
        import json as _json
        try:
            mapping = _json.loads(dtt) if isinstance(dtt, str) else dtt
        except Exception:
            logger.warning(f"deps_task_tables JSONB 解析失败: {dtt!r}")
            return True
        if not mapping:
            return True
        for other_table, dep_ids in mapping.items():
            # 表名安全校验：仅允许字母数字下划线点
            if not other_table or not all(c.isalnum() or c in '._' for c in other_table):
                logger.error(f"deps_task_tables 中非法表名: {other_table!r}")
                return False
            if not isinstance(dep_ids, list) or not dep_ids:
                continue
            ids_str = ",".join(
                f"'{int(x)}'" if str(x).isdigit() else f"'{x}'"
                for x in dep_ids
            )
            if "all" in [str(x).lower() for x in dep_ids]:
                check_sql = (
                    f"SELECT COUNT(*) FILTER (WHERE state <> 'COMPLETED') "
                    f"FROM {other_table}"
                )
            else:
                check_sql = (
                    f"SELECT COUNT(*) FROM {other_table} "
                    f"WHERE state <> 'COMPLETED' AND task_id IN ({ids_str})"
                )
            try:
                res = self._execute_sql(check_sql, commit=True)
                incomplete = res[0][0][0] if res and res[0] else 0
                if incomplete:
                    return False
            except Exception as e:
                logger.error(f"跨表依赖校验失败 {other_table}: {str(e)}")
                return False
        return True
    
    def execute_task(self, task_name: str, worker_id: str, skip_states: Optional[str] = None):
        """强制执行单个任务（不论任何状态）。

        执行路径：
        - 若 payload 解码后含非空 'do' key：从 _DO_REGISTRY 取注册的 py 单参函数执行，
          ctx = 解码后 payload 并 ``setdefault('task_name', task_name)``，跳过 self.task_function；
          未注册的 do 名抛 TaskFunctionError。
        - 否则走默认路径 self.task_function(task_name)。

        结果写入：
        - 成功：last_err = NULL；task_result 为 dict → back_info=jsonb_encode(dict)；
          非 dict 非 None → back_info=jsonb_encode({"result": str(task_result)})；None → back_info = NULL。
        - 失败：last_err = 纯文本错误 str(e)；back_info = jsonb_encode({"err_desc": <压缩的完整 traceback/异常链>})。
        """
        try:
            # 开始事务
            states = skip_states.split(",") if skip_states else ['RUNNING']
            if len(states) == 0:
                cond = ""
            elif len(states) ==1:
                cond = f"and state <> '{states[0]}'"
            else:
                cond = f"and state not in {str(tuple(states))}"
            with self._transaction() as conn:
                # 更新为运行中状态
                sql = f"""
                UPDATE {self.dbtable}
                SET 
                    state = 'RUNNING',
                    start_time = CURRENT_TIMESTAMP,
                    worker_id = ?,
                    version = version + 1
                WHERE task_name = ?
                {cond}
                """
                stmt = conn.prepareStatement(sql)
                stmt.setString(1, worker_id)
                stmt.setString(2, task_name)
                stmt.executeUpdate()
            
            # 在事务外执行任务函数（避免长时间持有事务）
            # task_function 返回值可以是 dict (结构化结果)，写入 back_info
            task_result = None
            payload = self._get_payload(task_name)
            do_name = payload.get('do') if isinstance(payload, dict) else None
            has_cli = isinstance(payload, dict) and isinstance(payload.get('cli'), dict)
            if do_name:
                # 'do' 特化路径：内置 py 单参函数（跳过 self.task_function）
                do_fn = self._DO_REGISTRY.get(str(do_name))
                if do_fn is None:
                    raise TaskFunctionError(
                        f"任务 {task_name} 指定的 do '{do_name}' 未注册，请先调用 "
                        f"LookUpon.register_do('{do_name}', fn) 或 @LookUpon.builtin_do('{do_name}') 注册"
                    )
                try:
                    ctx = dict(payload)
                    ctx.setdefault('task_name', task_name)
                    task_result = do_fn(ctx)
                except Exception as e:
                    raise TaskFunctionError(f"任务 {task_name} 的 do '{do_name}' 执行失败: {str(e)}") from e
            elif has_cli:
                # CLI 特化路径：用 Python subprocess 调外部 CLI（Scala/Java/R/Go/Node/Shell 等都支持）
                # 无语言枚举限制：task_type 是 VARCHAR(32) 自由字符串。
                # 从 DB 表里取 task_type 作为 lang 提示（若 payload['cli']['lang'] 未显式给）
                try:
                    cli_payload = dict(payload)
                    cli_payload.setdefault('task_name', task_name)
                    if not cli_payload.get('cli', {}).get('lang') and not cli_payload.get('cli', {}).get('cmd'):
                        # 回填 task_type（表里查一次）
                        cur = self._query_values(
                            f"SELECT task_type FROM {self.dbtable} WHERE task_name = %s", [task_name])
                        if cur:
                            cli_payload.setdefault('task_type', cur[0])
                    cli_result = cli_execute(cli_payload)
                    if not cli_result.get('ok'):
                        raise TaskFunctionError(
                            f"任务 {task_name} CLI 执行失败: {cli_result.get('error')} "
                            f"| cmd={cli_result.get('cmd')} "
                            f"| stderr={str(cli_result.get('stderr', ''))[:500]}"
                        )
                    task_result = cli_result
                except TaskFunctionError:
                    raise
                except Exception as e:
                    raise TaskFunctionError(f"任务 {task_name} CLI 执行失败: {str(e)}") from e
            else:
                # 默认路径：self.task_function(task_name)
                try:
                    task_result = self.task_function(task_name)
                except Exception as e:
                    raise TaskFunctionError(f"任务 {task_name} 执行失败: {str(e)}") from e
            
            # 标记为已完成
            with self._transaction() as conn:
                sql = f"""
                UPDATE {self.dbtable}
                SET 
                    state = 'COMPLETED',
                    end_time = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP,
                    last_err = NULL,
                    back_info = CAST(? AS jsonb),
                    version = version + 1
                WHERE task_name = ?
                """
                stmt = conn.prepareStatement(sql)
                # 结构化结果 → back_info（成功描述）
                if isinstance(task_result, dict):
                    back_info_str = jsonb_encode(task_result)
                    stmt.setString(1, back_info_str)
                elif task_result is None:
                    stmt.setNull(1, self.jvm.java.sql.Types.VARCHAR)
                else:
                    back_info_str = jsonb_encode({"result": str(task_result)})
                    stmt.setString(1, back_info_str)
                stmt.setString(2, task_name)
                stmt.executeUpdate()
            
            return True
        except Exception as e:
            # 记录错误信息
            error_msg = str(e)
            if isinstance(e, TaskFunctionError):
                error_msg = f"任务函数执行失败: {error_msg}"
            logger.error(f"任务 {task_name} 执行失败: {error_msg}")
            
            # 构造完整错误详情（traceback + 异常链）
            import traceback
            err_detail = traceback.format_exc()
            chain_parts = []
            seen = set()
            cur = e
            while cur is not None and id(cur) not in seen:
                seen.add(id(cur))
                chain_parts.append(f"{type(cur).__name__}: {cur}")
                cur = cur.__cause__ or cur.__context__
            if chain_parts:
                err_detail = f"{err_detail}\n--- 异常链 ---\n" + "\n".join(chain_parts)
            
            # 标记为失败
            with self._transaction() as conn:
                sql = f"""
                UPDATE {self.dbtable}
                SET 
                    state = case when max_retries > retry_count then 'RETRY_PENDING' else 'FAILED' end,
                    retry_count = retry_count + 1,
                    end_time = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP,
                    last_err = ?,
                    back_info = CAST(? AS jsonb),
                    version = version + 1
                WHERE task_name = ?
                """
                stmt = conn.prepareStatement(sql)
                stmt.setString(1, error_msg)
                # 失败详情：err_desc 存压缩后的完整错误（VText.toZipB64），外层 jsonb_encode 再压缩
                back_info_str = jsonb_encode({"err_desc": str(_VText(err_detail).toZipB64())})
                stmt.setString(2, back_info_str)
                stmt.setString(3, task_name)
                stmt.executeUpdate()
            
            return False
    
    def clean_stale_locks(self, timeout_min: int = 10):
        """清理过期的任务锁"""
        sql = f"""
        UPDATE {self.dbtable}
        SET 
            state = CASE 
                WHEN state = 'LOCKED' THEN 'PENDING' 
                WHEN state = 'RUNNING' THEN 'RETRY_PENDING'
            END,
            lock_time = NULL
        WHERE 
            lock_time < CURRENT_TIMESTAMP - INTERVAL '{timeout_min} minutes'
            AND state IN ('LOCKED', 'RUNNING')
        """
        self._execute_sql(sql, commit=True)
        logger.info("已清理过期任务锁")
    
    def run_until_done(self, worker_id: str, timeout_min: int = 5, interval: int = 10,states: Optional[str] = None):
        """持续运行任务直到全部完成"""
        logger.info(f"工作节点 {worker_id} 启动")
        
        while not self.is_all_done():
            try:
                # 获取并锁定一个任务
                task_name = self._acquire_task(worker_id, timeout_min,states=states)
                
                if task_name:
                    logger.info(f"获取任务: {task_name}")
                    
                    # 执行任务（强制执行，不论状态）
                    self.execute_task(task_name, worker_id)
                    logger.info(f"任务 {task_name} 完成")
                else:
                    logger.debug("无待处理任务，等待中...")
                    time.sleep(interval)
            
            except TaskAlreadyLocked as e:
                logger.warning(str(e))
                time.sleep(interval)
            
            except MaxRetriesExceeded as e:
                logger.error(str(e))
                time.sleep(interval)
            
            except Exception as e:
                logger.exception(f"处理任务时发生未预期错误: {str(e)}")
                time.sleep(interval)
        
        logger.info("所有任务已完成")
    
    def _get_payload(self, task_name: str) -> dict:
        """从任务表读取 payload JSONB (兼容无 payload 列的情况)。

        返回的 dict 里 value 已用 ``unZipB64`` 还原为原文（与 jsonb_encode 对称）。
        """
        try:
            # 显式 CAST AS text：JDBC getObject 对 PG JSONB 列返回 PGobject，
            # jsonb_decode 无法识别；CAST 后拿到的就是 JSON 字符串。
            sql = f"SELECT CAST(payload AS text) FROM {self.dbtable} WHERE task_name = ?"
            results = self._execute_sql(sql, params=[task_name])
            if results and results[0] and results[0][0]:
                row = results[0][0]
                raw = row[0] if isinstance(row, (list, tuple)) else row
                if isinstance(raw, str):
                    return jsonb_decode(raw)
                # PGobject 兜底：取 .getValue()
                try:
                    return jsonb_decode(str(raw.getValue()))
                except Exception:
                    return jsonb_decode(str(raw))
        except Exception as e:
            logger.debug(f"读取 payload 失败 (可能表无此列): {str(e)}")
        return {}

    def set_payload(self, task_name: str, payload: Optional[dict]):
        """把任务的 payload 写入 JSONB 列（value 用 ``jsonb_encode`` 编码）。

        Args:
            task_name: 任务 key（task_name）。
            payload: dict；None 时不动（不写）。
        """
        if payload is None:
            return
        sql = f"UPDATE {self.dbtable} SET payload = CAST(? AS jsonb) WHERE task_name = ?"
        self._execute_sql(sql, params=[jsonb_encode(payload), task_name], commit=True)
        logger.debug(f"写入 payload: {task_name}")
    
    def execute_task_with_result(self, task_name: str, worker_id: str, skip_states: Optional[str] = None):
        """执行任务。
        原 execute_task 已支持 task_function 返回结构化 dict，成功写入 back_info、失败写入 last_err。
        此函数仅包装，兼容旧接口。
        """
        return self.execute_task(task_name, worker_id, skip_states=skip_states)
    
    def run_until_done_resident(self, worker_id: str, timeout_min: int = 5, 
                                interval: int = 10, states: Optional[str] = None):
        """常驻模式：任务全跑完也不退出，一直轮询新任务
        - 与原 run_until_done 区别：去掉 is_all_done 判断，while True 常驻
        - 使用 execute_task_with_result 以便成功后更新 last_err / back_info
        """
        logger.info(f"工作节点 {worker_id} 启动 (常驻模式)")
        
        while True:
            try:
                task_name = self._acquire_task(worker_id, timeout_min, states=states)
                
                if task_name:
                    logger.info(f"获取任务: {task_name}")
                    
                    # 执行任务（含成功后更新 last_err / back_info）
                    self.execute_task_with_result(task_name, worker_id)
                    logger.info(f"任务 {task_name} 完成")
                else:
                    logger.debug("无待处理任务，等待中...")
                    time.sleep(interval)
            
            except TaskAlreadyLocked as e:
                logger.warning(str(e))
                time.sleep(interval)
            
            except MaxRetriesExceeded as e:
                logger.error(str(e))
                time.sleep(interval)
            
            except Exception as e:
                logger.exception(f"处理任务时发生未预期错误: {str(e)}")
                time.sleep(interval)
    
    def close(self):
        """关闭连接"""
        if self._conn:
            self._conn.close()
            self._conn = None
            logger.info("数据库连接已关闭")

    @classmethod
    def _get_spark_session(cls) -> SparkSession:
        """获取SparkSession"""
        from .configs import pg_jar
        jar = pg_jar()
        builder = SparkSession.builder \
            .config("spark.sql.autoBroadcastJoinThreshold", "-1") \
            .config("spark.default.parallelism", "10")
        if jar:
            builder = builder \
                .config("spark.jars", jar) \
                .config("spark.driver.extraClassPath", jar)
        return builder.getOrCreate()
    
    @classmethod
    def _get_default_properties(cls) -> dict:
        # 生产 PG 连接走 pyk.configs.pg_credentials（密文 + 环境变量），代码不留明文凭据
        from .configs import pg_credentials
        url, user, password = pg_credentials()
        return {
            'url': url,
            'user': user,
            'password': password,
            'driver': os.environ.get("PYK_PG_DRIVER", "org.postgresql.Driver"),
        }
        
    @classmethod
    def query(cls,sql:str) -> Any:
        """执行查询并返回DataFrame,注意是postgresql"""
        if  re.match(r"^[a-z][a-z_0-9]+\.[a-z_0-9]+$",sql.lower()):
            sql = f"select * from {sql}"
        elif re.match(r"^[a-z][a-z_0-9]+$",sql.lower()):
            sql = f"select * from public.{sql}"
        spark = cls._get_spark_session()
        dct = cls._get_default_properties()
        dct['query'] = sql
        return spark.read.format("jdbc").options(**dct).load()


def add_tasks(dbtable:str,tasks:List[Any],deps:Optional[Dict[str, List[int]]] = None,
              deps_task_tables:Optional[Dict[str, Dict[str, Any]]] = None,
              default_task_type: str = "SQL", default_team: str = "",
              default_group: str = "", default_owner: str = "",
              default_queue: str = "", default_priority: int = 0,
              default_timeout_min: int = 60, default_retry_delay_min: int = 5) -> bool:
    """添加任务并获取任务

    Args:
        dbtable: 任务表名
        tasks: 任务列表。str 简写（task_name=value=str）或 dict 完整字段。
        deps:  可选同表依赖 {task_name: [task_id, ...]}
        deps_task_tables: 可选跨表依赖 {task_name: {other_table: [task_id, ...]}}；["all"] 表示整表须完成。
        default_*: 当任务 dict 里未指定这些字段时的默认值。
    """
    try:
        lu = LookUpon(
            task_function=None,
            dbtable=dbtable,
            init=False,
            tasks=tasks,
            max_retries=3
        )
        lu.add_tasks(
            tasks, deps=deps, deps_task_tables=deps_task_tables,
            default_task_type=default_task_type, default_team=default_team,
            default_group=default_group, default_owner=default_owner,
            default_queue=default_queue, default_priority=default_priority,
            default_timeout_min=default_timeout_min,
            default_retry_delay_min=default_retry_delay_min,
        )
        return True
    except Exception as e:
        logger.error(f"添加任务失败: {str(e)}")
        return False

def query_tasks(dbtable:str,where_cond:str = "") -> Optional[DataFrame]:
    """查询任务"""
    try:
        lu = LookUpon(
            task_function=None,
            dbtable=dbtable,
            init=False,
            tasks=[],
            max_retries=3
        )
        s =   "" if  where_cond.strip().lower().startswith("where ") else "where "
        where_cond = s + where_cond.strip() if where_cond.strip() else ""
        return lu.query(f"select * from {dbtable} {where_cond}")
    except Exception as e:
        logger.error(f"查询任务失败: {str(e)}")
        return None

def init_tasks(dbtable,tasks,drop_if_exists=False):
    """初始化任务系统"""
    return LookUpon(
        task_function=None,
        dbtable=dbtable,
        init=True,
        tasks=tasks,
        max_retries=3,
        drop_if_exists=drop_if_exists
    )

def _is_lookupon_table(dbtable:str):
    """判断表是否为LookUpon任务表"""
    lu = LookUpon(task_function=None, dbtable='lookupon', init=True)
    df = lu.query("select * from public.lookupon")
    tn = dbtable if '.' in dbtable else f"public.{dbtable}"
    tf = LookUpon.query(f"select * from {tn}")
    return df.columns == tf.columns

def run_until_done(task_function: Callable[[str], None],dbtable :str, worker_id:Optional[str] = None
                ,tasks :Optional[List[str]] =None, max_retries:int =3 
                ,timeout_min :int =5, interval :int =10,states: Optional[str] = None):
    try:
        if not _is_lookupon_table(dbtable):
            raise ValueError(f"表 {dbtable} 不是LookUpon任务表")
        task_system = LookUpon(
            task_function=task_function,
            dbtable=dbtable,
            tasks=tasks,
            init=False,
            max_retries=max_retries
        )
        if worker_id is None:
            cnt = task_system.query(f"select * from public.{dbtable} where worker_id is not null and state in ('COMPLETED', 'FAILED','RUNNING','LOCKED') ").groupBy("worker_id").count().count()
            worker_id = f"auto_wk_id_{cnt+1}"
        task_system.run_until_done(worker_id=worker_id, timeout_min=timeout_min, interval=interval,states=states)
    except Exception as e:
        logger.exception(f"运行失败: {str(e)}")
        raise e

def get_replaced_sql(ds,replace_func = None, spark=None,**kwargs):
    """当提供spark 执行sql，反之返回 str,默认 替换  文件中  {ds} 为 ds 
        replace_func =>> replace_func(sql,ds,**kwargs):pass
    """
    sql_file = upon_sql_file()
    if not sql_file:
        raise FileNotFoundError(
            "look_upon 未配置 SQL 文件：请设置环境变量 PYK_UPON_SQL_FILE，"
            "或在 pyk.configs.UPON_SQL_FILE 里显式覆写。公开库不硬编码生产路径。"
        )
    with open(sql_file, 'r', encoding="utf-8") as f:
        txt = f.read()
        run_date = kwargs.pop('run_date',None)
        if run_date :
            txt = _vicText(txt).replace_run_date(run_date).text
        sql = txt.replace(r"{ds}",ds) if replace_func is None else replace_func(txt,**{'ds':ds},**kwargs)
        return sql if spark is None else spark.sql(sql)
        
@wraps(run_until_done)
def run_done(replace_function,*args,**kwargs):
    """ privode replace_function instead  task_function 
        replace_func =>> replace_func(sql,ds,**kwargs):pass
    """
    ps = ['dbtable','worker_id','tasks','max_retries','timeout_min','interval','states'] 
    dct = { k:kwargs[k] for k in kwargs.keys() if k in ps }
    if not 'dbtable' in dct.keys():
        dct['dbtable'] = 'lookupon'
    if 'states' in dct.keys() and dct['states'] == 'FAILED':
        update_failed_to_pending(dct['dbtable'])

    kct = { k:kwargs[k] for k in kwargs.keys() if k not in ps }
    return run_until_done(partial(get_replaced_sql,replace_func=replace_function,**kct),*args,**dct)

def reset_tasks(tasks):
    """
    reset_tasks in table lookupon
    """
    lu = LookUpon((lambda x:x ),'lookupon')
    lu.execute_sql("truncate table public.lookupon ")
    lu.add_tasks(tasks)
    cnt = lu.query("select * from public.lookupon").count()
    if cnt != len(tasks):
        raise TaskFunctionError("reset_tasks failed ,please query table public.lookupon fro check !!!")
    print(f"Add {cnt} tasks Success in table public.lookupon!")

def run_doneEx(dbtable = None,**kwargs):
    """
    the value is run_date like yyyyMMdd or yyyy-MM-dd,auto replace all 'run_date' to value 
    all kwagrs is a callable function like function(run_date),to replace {ds},{end_ds}
    example:
        run_doneEx(ds = lambda x : get_week(x,0,7), end_ds = lambda x: get_month(x,0,1) )
        will replace {ds} and {end_ds}  in content from builder_sql_for_upon.sql file
    """
    dbtable = 'lookupon' if dbtable is None else dbtable
    path = kwargs.pop('path', upon_sql_file())
    if not path:
        raise FileNotFoundError(
            "look_upon 未配置 SQL 文件：请设置环境变量 PYK_UPON_SQL_FILE，"
            "或在 pyk.configs.UPON_SQL_FILE 里显式覆写。"
        )
    # with open(path,'r',encoding="utf-8") as f:
    #     txt = f.read()
    txt = _get_content(path).text
    factory = kwargs.pop('factory', get_spark())
    factory = factory.sql if isinstance(factory,SparkSession) else factory
    def do(run_date):
        sql = _vicText(txt)
        if "{run_date" in txt:
             sql = sql.replace_run_date(run_date)
        text = sql.text
        dct = dict()
        for k,v in kwargs.items():
            if '{' + k + '}' in text:
                v = v(run_date) if callable(v) else str(v)
                dct[k] = v
        if dct:
            sql = sql.build(dct)
        for s in sql.text.split(';'):
            s = s.strip()
            if s and factory :
                factory(s) 
    return run_until_done(do,dbtable)


def update_failed_to_pending(dbtable:str = None):
    dbtable = 'lookupon' if dbtable is None else dbtable
    LookUpon((lambda x:x ),dbtable).execute_sql(f"update  public.{dbtable}  set state = 'PENDING' , version = version + 1  where state = 'FAILED' ")

LU = LookUpon

if __name__ == '__main__':
    # 测试代码
    import random
    def process_task(value: str):
        """示例任务处理函数"""
        print(f"Processing task: {value}")
        # 模拟任务处理
        time.sleep(0.5)
        # 模拟随机失败
        if random.random() < 0.2:
            raise Exception("随机错误")

    # df = LookUpon.query('task_queue')
    # df.show()
    # spk = LookUpon._get_spark_session()
    # spk.sql("select 1 as id").show()
    # 创建任务系统
    task_system = LookUpon(
        task_function=process_task,
        dbtable="task_queue",
        init=True,
        tasks=[f"task_{i}" for i in range(100)],
        max_retries=3,
        drop_if_exists = True
    )

    try:
        # 启动工作节点
        task_system.run_until_done(worker_id="worker-1")
    finally:
        # 清理资源
        task_system.close()