"""
CLI 执行通道 — task 模块对齐 look_upon 能力面。

核心函数 `cli_execute(payload, timeout_sec, capture)`：
    用 Python subprocess 调用外部 CLI，无语言枚举限制。

支持 Python / Scala / Java / R / Go / Node / Shell / SQL 等常用语言，
`payload['cli']` 字段决定命令组装方式：

    cli.lang        语言名（python / scala / java / shell / sql / r / node / go ...）
    cli.cmd         完整命令字符串（给了就跳过 lang 推断）
    cli.args        追加参数列表
    cli.script      内联脚本（临时文件，用后删除）
    cli.script_path 已有脚本路径
    cli.workdir     工作目录
    cli.env         环境变量 dict
    cli.stdin       stdin 输入（缺省用顶层 value）
    cli.timeout_sec 超时秒（默认 600）
    cli.capture     是否捕获 stdout/stderr（默认 True）
    cli.shell       shell=True 时用 cmd 原样执行
    cli.check       check=True 时非 0 返回码视为异常

顶层 `task_type` 作为语言提示（大小写不敏感，支持别名）。

返回 dict：
    {"ok", "exit_code", "stdout", "stderr", "cmd", "duration_ms", "error", "task_type"}
"""

__all__ = ['cli_execute', 'LANGUAGE_DEFAULT_CMD', 'LANGUAGE_EXTENSIONS',
           'detect_language', 'find_executable']

import os
import shlex
import shutil
import subprocess
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple

# ============================================================
# 语言 → 默认命令前缀
# ============================================================
LANGUAGE_DEFAULT_CMD: Dict[str, List[str]] = {
    "python": ["python"],
    "py": ["python"],
    "python3": ["python3"],
    "scala": ["scala"],
    "sc": ["scala"],
    "java": ["java"],
    "javac": ["javac"],
    "shell": ["bash"],
    "sh": ["bash"],
    "bash": ["bash"],
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

# ============================================================
# 语言 → 脚本扩展名
# ============================================================
LANGUAGE_EXTENSIONS: Dict[str, str] = {
    "python": ".py",
    "py": ".py",
    "python3": ".py",
    "scala": ".scala",
    "sc": ".scala",
    "java": ".java",
    "javac": ".java",
    "shell": ".sh",
    "sh": ".sh",
    "bash": ".sh",
    "sql": ".sql",
    "psql": ".sql",
    "r": ".r",
    "rscript": ".r",
    "node": ".js",
    "js": ".js",
    "javascript": ".js",
    "go": ".go",
    "golang": ".go",
    "julia": ".jl",
    "ruby": ".rb",
    "perl": ".pl",
    "php": ".php",
    "spark-submit": ".py",
}


def detect_language(task_type: Optional[str]) -> Optional[str]:
    """把 task_type 归一化为 LANGUAGE_DEFAULT_CMD 的 key。

    大小写不敏感；找不到返回 None（调用方应明确报错，不静默跳过）。
    """
    if not task_type:
        return None
    return str(task_type).strip().lower()


def find_executable(cmd_prefix: List[str]) -> Optional[str]:
    """查找解释器可执行文件。

    Windows 自动补 .exe / .bat / .cmd。
    """
    if not cmd_prefix:
        return None
    cands = [cmd_prefix[0]]
    if os.name == "nt":
        cands += [cmd_prefix[0] + ".exe", cmd_prefix[0] + ".bat", cmd_prefix[0] + ".cmd"]
    for c in cands:
        p = shutil.which(c)
        if p:
            return p
    return None


def cli_execute(payload: Dict[str, Any], timeout_sec: Optional[float] = None,
                capture: Optional[bool] = None) -> Dict[str, Any]:
    """用 Python subprocess 调用外部 CLI。

    参数：
        payload: 任务 payload dict，含 `cli` 子 dict 与可选顶层 `value`/`task_type`。
        timeout_sec: 覆盖 cli.timeout_sec。
        capture: 覆盖 cli.capture。

    返回：
        结构化结果 dict。
    """
    cli = (payload or {}).get("cli") or {}
    task_type = payload.get("task_type") or payload.get("taskType") or ""
    value = payload.get("value")

    lang = cli.get("lang") or ""
    cmd_str = cli.get("cmd")
    args = cli.get("args") or []
    script = cli.get("script")
    script_path = cli.get("script_path")
    workdir = cli.get("workdir")
    env = cli.get("env") or {}
    stdin_val = cli.get("stdin")
    stdin_from_value = cli.get("stdin_from_value", True)
    timeout = timeout_sec if timeout_sec is not None else cli.get("timeout_sec", 600)
    cap = capture if capture is not None else cli.get("capture", True)
    shell = bool(cli.get("shell", False))
    check = bool(cli.get("check", False))
    task_type_norm = detect_language(task_type)

    t0 = time.time()
    try:
        # ---- 语言推断 ----
        lang_norm = detect_language(lang)
        if lang_norm and lang_norm not in LANGUAGE_DEFAULT_CMD:
            return _fail("未知语言 '%s'。可用: %s" % (
                lang, sorted(LANGUAGE_DEFAULT_CMD.keys())), t0, task_type_norm)

        if cmd_str:
            # 显式 cmd 优先
            if shell:
                cmd_parts: List[str] = [cmd_str]
            else:
                cmd_parts = shlex.split(cmd_str)
        elif lang_norm:
            cmd_parts = list(LANGUAGE_DEFAULT_CMD[lang_norm])
        else:
            # 尝试从 task_type 推断
            if task_type_norm and task_type_norm in LANGUAGE_DEFAULT_CMD:
                cmd_parts = list(LANGUAGE_DEFAULT_CMD[task_type_norm])
                lang_norm = task_type_norm
            else:
                return _fail(
                    "缺少 cli.cmd 且无法从 lang/task_type 推断语言。可用: %s"
                    % sorted(LANGUAGE_DEFAULT_CMD.keys()), t0, task_type_norm)

        # ---- 脚本文件 ----
        tmp_path = None
        if script:
            ext = LANGUAGE_EXTENSIONS.get(lang_norm or task_type_norm or "", ".py")
            fd, tmp_path = tempfile.mkstemp(suffix=ext)
            os.close(fd)
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(script if isinstance(script, str) else json_dumps(script))
            script_arg = tmp_path
        elif script_path:
            script_arg = script_path
        else:
            script_arg = None

        full_cmd = cmd_parts + list(args)
        if script_arg is not None and not shell:
            full_cmd.append(script_arg)

        # ---- 环境变量 ----
        run_env = os.environ.copy()
        if env:
            run_env.update({str(k): str(v) for k, v in env.items()})

        # ---- stdin ----
        stdin_data = stdin_val
        if stdin_data is None and stdin_from_value:
            stdin_data = value
        stdin_bytes = None
        if stdin_data is not None:
            stdin_bytes = str(stdin_data).encode("utf-8")

        # ---- 执行 ----
        proc = subprocess.run(
            full_cmd,
            input=stdin_bytes,
            stdout=subprocess.PIPE if cap else None,
            stderr=subprocess.PIPE if cap else None,
            timeout=timeout,
            cwd=workdir or None,
            env=run_env,
            shell=shell,
        )
        exit_code = proc.returncode
        stdout = proc.stdout.decode("utf-8", errors="replace") if proc.stdout else ""
        stderr = proc.stderr.decode("utf-8", errors="replace") if proc.stderr else ""
        duration = (time.time() - t0) * 1000.0
        return {
            "ok": (exit_code == 0) if check else True,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "cmd": full_cmd if not shell else full_cmd[0],
            "duration_ms": duration,
            "error": None,
            "task_type": task_type_norm,
        }
    except subprocess.TimeoutExpired as e:
        return _fail("执行超时（%s 秒）" % timeout, t0, task_type_norm, exit_code=None,
                     extra={"timeout": timeout, "cmd": _safe_cmd(cmd_str, lang_norm)})
    except FileNotFoundError as e:
        hint = str(e)
        if lang_norm:
            hint = ("找不到解释器 '%s'（语言=%s）。请安装对应运行时"
                    "或用 payload['cli']['cmd'] 显式指定完整命令。" % (lang_norm, lang))
        return _fail(hint, t0, task_type_norm)
    except Exception as e:
        return _fail("执行异常: %s" % e, t0, task_type_norm)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


def _fail(message: str, t0: float, task_type: Optional[str], exit_code: Optional[int] = 1,
          extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """构造失败返回。"""
    out = {
        "ok": False,
        "exit_code": exit_code,
        "stdout": "",
        "stderr": message,
        "cmd": None,
        "duration_ms": (time.time() - t0) * 1000.0,
        "error": message,
        "task_type": task_type,
    }
    if extra:
        out.update(extra)
    return out


def _safe_cmd(cmd_str, lang):
    """安全构造命令描述（失败时用）。"""
    return cmd_str or (lang or None)


def json_dumps(obj):
    """安全 JSON 序列化（不引额外依赖）。"""
    import json
    return json.dumps(obj, ensure_ascii=False)