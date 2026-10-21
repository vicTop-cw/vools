"""vools.rhop.task.exec - 任务执行通道（动作 / CLI / 注册处理器）+ 白名单

B 端拿到解密后的 JSON 指令，按下面的顺序派发（与 look_upon 的 payload 约定对齐，
但**默认白名单**：没被显式放行的命令一律拒绝）：

1. ``{"action": "jump.push", "payload": {...}}``  → ``vools.rhop.actions`` 注册动作；
2. ``{"cli": {"lang"/"cmd"/"args"/"script"/...}}`` → Python subprocess（无语言枚举限制，
   字段与 ``vools.pyk.look_upon.cli_execute`` 完全一致，vq 侧习惯可直接搬过来）；
3. ``{"handler": "name"}`` 或 ``task_type`` 命中 ``register_handler`` 注册的 Python 函数。

安全边界（默认配置 ``exec.allow = ["action:*"]``）：
* 代码内注册的动作（session/actions 里那套封闭集合）默认放行；
* 任意命令（``cli:*``）**必须**在 ``exec.allow`` 里显式列出；
* ``exec.allow_any = true`` 才整体放开（自担风险）；
* ``shell=True`` 需要 allow 命中 ``cli:shell`` 或 allow_any；
* 拒绝时抛 ``ExecDenied``，队列把它记成 FAILED 并保留原因。
"""

from __future__ import absolute_import

import fnmatch
import os
import shlex
import shutil
import subprocess
import tempfile
import time
from typing import Any, Callable, Dict, List, Optional

from .errors import ExecDenied

#: 各语言默认命令前缀（与 look_upon 保持一致，无枚举限制）
LANGUAGE_DEFAULT_CMD = {
    "python": ["python"], "py": ["python"], "python3": ["python3"],
    "scala": ["scala"], "sc": ["scala"],
    "java": ["java"], "javac": ["javac"],
    "shell": ["bash"], "sh": ["sh"], "bash": ["bash"], "zsh": ["zsh"],
    "sql": ["psql"], "psql": ["psql"],
    "r": ["Rscript"], "rscript": ["Rscript"],
    "node": ["node"], "js": ["node"], "javascript": ["node"],
    "go": ["go", "run"], "golang": ["go", "run"],
    "julia": ["julia"], "ruby": ["ruby"], "perl": ["perl"], "php": ["php"],
    "dotnet": ["dotnet"],
    "spark-submit": ["spark-submit"],
    "spark_sql": ["spark-sql"], "sparksql": ["spark-sql"],
}

#: 各语言脚本扩展名（内联 script 落临时文件用）
LANGUAGE_EXTENSIONS = {
    "python": ".py", "py": ".py", "python3": ".py",
    "scala": ".scala", "sc": ".scala", "java": ".java",
    "shell": ".sh", "sh": ".sh", "bash": ".sh", "zsh": ".sh",
    "sql": ".sql", "psql": ".sql",
    "r": ".r", "rscript": ".r",
    "node": ".js", "js": ".js", "javascript": ".js",
    "go": ".go", "golang": ".go", "julia": ".jl",
    "ruby": ".rb", "perl": ".pl", "php": ".php",
    "spark-submit": ".py",
}

#: 语言别名归一
_LANG_ALIASES = {
    "py": "python", "python": "python", "python3": "python3",
    "sc": "scala", "scala": "scala", "java": "java",
    "sh": "shell", "bash": "bash", "shell": "shell", "zsh": "zsh",
    "sql": "sql", "psql": "psql",
    "js": "node", "node": "node", "javascript": "node",
    "golang": "go", "go": "go",
}

#: 注册的 Python 处理器：name -> fn(payload) -> Any
HANDLERS = {}  # type: Dict[str, Callable[[dict], Any]]


def register_handler(name: str, fn: Optional[Callable[[dict], Any]] = None):
    """注册一个 Python 任务处理器。

    两种用法等价::

        register_handler("double", fn)

        @register_handler("double")
        def fn(payload):
            ...
    """
    key = str(name or "").strip()
    if not key:
        raise ValueError("handler 名称不能为空")

    def _do_register(func):
        if not callable(func):
            raise ValueError("handler 必须可调用")
        HANDLERS[key] = func
        return func

    if fn is None:
        return _do_register
    return _do_register(fn)


def get_handler(name: str) -> Optional[Callable[[dict], Any]]:
    """取注册的处理器（不存在返回 None）。"""
    return HANDLERS.get(str(name or "").strip())


def detect_language(task_type: str) -> Optional[str]:
    """把 task_type / cli.lang 归一为 LANGUAGE_DEFAULT_CMD 的规范 key。

    先走别名表（``PY``→``python``、``sc``→``scala``、``golang``→``go`` …），
    再兜底匹配默认命令表，因此 ``PY`` / ``py`` / ``python`` 得到同一个规范名。
    """
    if not task_type:
        return None
    text = str(task_type).strip().lower()
    if text in _LANG_ALIASES:
        return _LANG_ALIASES[text]
    if text in LANGUAGE_DEFAULT_CMD:
        return text
    return None


def find_executable(cmd_prefix: List[str]) -> Optional[str]:
    """在 PATH 找可执行文件（Windows 自动补 .exe/.bat/.cmd）。"""
    exe = cmd_prefix[0]
    found = shutil.which(exe)
    if found:
        return found
    if os.name == "nt":
        for ext in (".exe", ".bat", ".cmd"):
            found = shutil.which(exe + ext)
            if found:
                return found
    return None


class ExecPolicy(object):
    """执行白名单与默认执行参数。"""

    def __init__(self, allow: Optional[List[str]] = None, allow_any: bool = False,
                 workdir: str = "", env: Optional[dict] = None,
                 timeout_sec: float = 3600.0, shell: bool = False):
        #: 默认只放行「代码内注册的封闭集合」：动作与处理器；
        #: 任意命令行（cli:*）必须显式列出，或 allow_any 整体放开。
        self.allow = list(allow if allow is not None else ["action:*", "handler:*"])
        self.allow_any = bool(allow_any)
        self.workdir = str(workdir or "")
        self.env = dict(env or {})
        self.timeout_sec = float(timeout_sec or 3600.0)
        self.shell = bool(shell)

    @classmethod
    def from_cfg(cls, cfg: Optional[dict]) -> "ExecPolicy":
        """从配置里的 exec 段构造。"""
        data = dict(cfg or {})
        return cls(
            allow=data.get("allow"),
            allow_any=bool(data.get("allow_any")),
            workdir=data.get("workdir") or "",
            env=data.get("env") or {},
            timeout_sec=data.get("timeout_sec") or 3600.0,
            shell=bool(data.get("shell")),
        )

    def check(self, channel: str, name: str) -> None:
        """校验某个通道/名字是否被放行，未放行抛 ExecDenied。

        名字匹配同时尝试「原样」与「去掉 .exe/.bat/.cmd 后缀的可执行名」，
        因此 ``cli:python`` 既能放行 ``python``，也能放行 ``python.exe``。
        """
        if self.allow_any:
            return
        names = [str(name or "")]
        stem, ext = os.path.splitext(str(name or ""))
        if stem and ext.lower() in (".exe", ".bat", ".cmd", ".py"):
            names.append(stem)
        for candidate_name in names:
            candidate = "%s:%s" % (channel, candidate_name)
            for pattern in self.allow:
                if pattern == "*" or fnmatch.fnmatchcase(candidate, str(pattern)):
                    return
        candidate = "%s:%s" % (channel, str(name or ""))
        raise ExecDenied(
            "执行被白名单拒绝：%s。当前允许: %s。"
            "需要放行时在配置 exec.allow 里加 '%s'（或整条 %s:*）；"
            "要放开任意命令请显式设置 exec.allow_any=true（自担风险）。" % (
                candidate, ", ".join(str(p) for p in self.allow) or "(空)",
                candidate, channel))

    def allow_shell(self, channel: str) -> bool:
        """是否允许 shell=True（需要显式 allow 或 allow_any）。"""
        if self.allow_any:
            return True
        return any(fnmatch.fnmatchcase("cli:shell", str(p)) for p in self.allow) or self.shell

    def describe(self) -> Dict[str, Any]:
        """自描述。"""
        return {
            "allow": list(self.allow),
            "allow_any": self.allow_any,
            "workdir": self.workdir,
            "timeout_sec": self.timeout_sec,
            "shell": self.shell,
        }


def cli_execute(payload: Dict[str, Any], policy: Optional[ExecPolicy] = None,
                timeout_sec: Optional[float] = None) -> Dict[str, Any]:
    """执行 ``payload['cli']`` 描述的命令行（字段与 look_upon.cli_execute 对齐）。

    Args:
        payload:    含 ``cli`` 子 dict 的任务载荷；顶层 ``task_type`` 作语言提示
        policy:     白名单与默认 workdir/env/timeout
        timeout_sec: 额外超时覆盖

    Returns:
        dict（ok / exit_code / stdout / stderr / cmd / duration_ms / error / task_type）
    """
    policy = policy or ExecPolicy()
    cli = payload.get("cli") if isinstance(payload.get("cli"), dict) else {}
    task_type = payload.get("task_type", "")
    timeout = cli.get("timeout_sec", timeout_sec if timeout_sec is not None else policy.timeout_sec)
    capture = cli.get("capture", True)
    check = bool(cli.get("check", False))
    shell = bool(cli.get("shell", False))

    cmd_str = str(cli.get("cmd") or "").strip()
    args_list = [str(a) for a in (cli.get("args") or [])]
    lang_hint = cli.get("lang") or detect_language(task_type)

    # 1) 组装 argv
    if cmd_str:
        if shell:
            argv = [cmd_str] + args_list
        else:
            argv = shlex.split(cmd_str) + args_list
        if not argv:
            return _fail("cli.cmd 解析后为空")
        cmd_display = " ".join(argv)
        exe = argv[0]
    else:
        if not lang_hint:
            return _fail(
                "无法推断命令：请设置 payload['cli']['cmd'] 或 payload['cli']['lang'] / "
                "task_type（支持 python/scala/java/shell/sql/r/node/go/julia/ruby/perl/php/spark-submit 等）")
        prefix = LANGUAGE_DEFAULT_CMD.get(lang_hint)
        if not prefix:
            return _fail("未知语言 '%s'（可用: %s）" % (lang_hint, ", ".join(sorted(LANGUAGE_DEFAULT_CMD))))
        exe = find_executable(prefix)
        if exe is None:
            return _fail("找不到解释器 '%s'（语言=%s）：请安装运行时或用 cli.cmd 显式指定完整命令"
                         % (prefix[0], lang_hint))
        argv = [exe] + list(prefix[1:]) + args_list
        cmd_display = " ".join(argv)

    # 2) 内联 script / 已有脚本
    tmp_path = None
    script = cli.get("script")
    script_path = cli.get("script_path")
    if script and not script_path:
        ext = LANGUAGE_EXTENSIONS.get(lang_hint or "", ".tmp")
        fd, tmp_path = tempfile.mkstemp(suffix=ext, prefix="rhop_cli_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(str(script))
        except OSError as exc:
            return _fail("写临时脚本失败: %s" % exc)
        script_path = tmp_path
    if script_path:
        if shell:
            argv = argv + [str(script_path)]
        else:
            argv = argv + [str(script_path)]
        cmd_display = " ".join(argv)

    # 3) 工作目录
    workdir = cli.get("workdir") or policy.workdir or None
    if workdir and not os.path.isdir(workdir):
        return _fail("workdir 不存在: %s" % workdir)

    # 4) 环境变量
    env = os.environ.copy()
    for key, value in dict(policy.env or {}).items():
        env[str(key)] = str(value)
    for key, value in dict(cli.get("env") or {}).items():
        env[str(key)] = str(value)

    # 5) stdin
    stdin_data = cli.get("stdin")
    if stdin_data is None and cli.get("stdin_from_value", True) and payload.get("value"):
        stdin_data = str(payload.get("value"))

    # 6) 执行
    start = time.time()
    try:
        proc = subprocess.run(
            argv if not shell else " ".join(argv),
            cwd=workdir,
            env=env,
            input=stdin_data,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
            encoding="utf-8",       # Py3.6 兼容：用 encoding 进文本模式
            errors="replace",
            timeout=timeout,
            shell=shell,
        )
        duration_ms = (time.time() - start) * 1000
        ok = (proc.returncode == 0)
        result = {
            "ok": ok,
            "exit_code": proc.returncode,
            "stdout": proc.stdout or "",
            "stderr": proc.stderr or "",
            "cmd": cmd_display,
            "duration_ms": round(duration_ms, 2),
            "error": None if ok else "退出码非 0 (%s)" % proc.returncode,
            "task_type": lang_hint or task_type,
        }
        if check and not ok:
            raise subprocess.CalledProcessError(proc.returncode, argv,
                                                output=result["stdout"], stderr=result["stderr"])
        return result
    except subprocess.TimeoutExpired as exc:
        duration_ms = (time.time() - start) * 1000
        return _fail("执行超时（%s 秒）" % timeout, cmd=cmd_display,
                     duration_ms=duration_ms, task_type=lang_hint or task_type,
                     stdout=str(exc.stdout or ""), stderr=str(exc.stderr or ""))
    except subprocess.CalledProcessError as exc:
        duration_ms = (time.time() - start) * 1000
        return _fail("check=True 且退出码非 0 (%s)" % exc.returncode, cmd=cmd_display,
                     duration_ms=duration_ms, exit_code=exc.returncode,
                     stdout=str(exc.output or ""), stderr=str(exc.stderr or ""),
                     task_type=lang_hint or task_type)
    except FileNotFoundError as exc:
        return _fail("可执行文件不存在: %s" % exc, cmd=cmd_display, task_type=lang_hint or task_type)
    except Exception as exc:
        return _fail("cli_execute 异常: %s" % exc, cmd=cmd_display, task_type=lang_hint or task_type)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def _fail(error: str, cmd: str = "", duration_ms: float = 0.0, exit_code: Optional[int] = None,
          stdout: str = "", stderr: str = "", task_type: str = "") -> Dict[str, Any]:
    """统一失败返回结构。"""
    return {
        "ok": False, "exit_code": exit_code, "stdout": stdout, "stderr": stderr,
        "cmd": cmd, "duration_ms": round(duration_ms, 2), "error": error,
        "task_type": task_type,
    }


def resolve_channel(payload: dict, task_type: str = "",
                    handlers: Optional[Dict[str, Callable]] = None) -> Dict[str, Any]:
    """判断该走哪个执行通道（不做白名单校验，方便单测/诊断）。"""
    handlers = HANDLERS if handlers is None else handlers
    if not isinstance(payload, dict):
        return {"channel": None, "name": "", "reason": "载荷不是 dict"}
    action = payload.get("action")
    if action:
        return {"channel": "action", "name": str(action), "reason": ""}
    if isinstance(payload.get("cli"), dict):
        cli = payload["cli"]
        name = str(cli.get("lang") or "").strip() or _cmd_name(cli.get("cmd")) or "cmd"
        return {"channel": "cli", "name": name, "reason": ""}
    handler = payload.get("handler") or task_type or payload.get("task_type")
    if handler and get_handler(str(handler)):
        return {"channel": "handler", "name": str(handler), "reason": ""}
    return {"channel": None, "name": "",
            "reason": "无法识别指令：需要 action / cli / handler（或 task_type 命中已注册处理器）"}


def _cmd_name(cmd: Any) -> str:
    """从完整命令行取可执行名（白名单按解释器名匹配，如 cli:python）。"""
    if not cmd:
        return ""
    text = str(cmd).strip()
    if not text:
        return ""
    try:
        parts = shlex.split(text)
    except ValueError:
        parts = text.split()
    return os.path.basename(parts[0]) if parts else ""


def run_payload(payload: dict, policy: Optional[ExecPolicy] = None,
                action_cfg: Optional[dict] = None, task_type: str = "",
                handlers: Optional[Dict[str, Callable]] = None) -> Dict[str, Any]:
    """按指令派发执行，返回统一结果 dict。

    Returns:
        {
          "ok": bool, "channel": "action"|"cli"|"handler", "name": ...,
          "result": <动作/处理器返回值 或 cli_execute 结果>,
          "error": str|None,
        }

    Raises:
        ExecDenied: 白名单未放行（由调用方决定是否算失败终态）。
    """
    policy = policy or ExecPolicy()
    handlers = HANDLERS if handlers is None else handlers
    resolved = resolve_channel(payload, task_type=task_type, handlers=handlers)
    channel = resolved.get("channel")
    name = resolved.get("name") or ""
    if not channel:
        return {"ok": False, "channel": None, "name": name, "result": None,
                "error": resolved.get("reason")}

    policy.check(channel, name)

    if channel == "action":
        from ..actions import omega_unwrap, run_action
        raw = run_action(str(payload.get("action")), action_cfg or {},
                         payload.get("payload") if isinstance(payload.get("payload"), dict)
                         else payload.get("args"))
        unwrapped = omega_unwrap(raw)
        ok = unwrapped.get("status") in ("ok", "partial")
        return {"ok": ok, "channel": channel, "name": name, "result": unwrapped,
                "error": None if ok else str(unwrapped.get("omega_gate") or unwrapped.get("status"))}

    if channel == "cli":
        cli = dict(payload.get("cli") or {})
        if cli.get("shell") and not policy.allow_shell(channel):
            raise ExecDenied(
                "cli.shell=true 被拒绝：需要 exec.allow 里显式放行 'cli:shell'，"
                "或设置 exec.allow_any=true。")
        result = cli_execute(payload, policy=policy)
        return {"ok": bool(result.get("ok")), "channel": channel, "name": name,
                "result": result, "error": result.get("error")}

    handler = handlers.get(name)
    if handler is None:
        return {"ok": False, "channel": "handler", "name": name, "result": None,
                "error": "处理器 %s 未注册" % name}
    try:
        value = handler(payload)
    except Exception as exc:
        return {"ok": False, "channel": "handler", "name": name, "result": None,
                "error": "处理器异常: %s" % exc}
    return {"ok": True, "channel": "handler", "name": name, "result": value, "error": None}


__all__ = [
    "ExecPolicy",
    "ExecDenied",
    "register_handler",
    "get_handler",
    "HANDLERS",
    "detect_language",
    "find_executable",
    "cli_execute",
    "resolve_channel",
    "run_payload",
    "LANGUAGE_DEFAULT_CMD",
    "LANGUAGE_EXTENSIONS",
]