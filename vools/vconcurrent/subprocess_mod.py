"""
vools.concurrent.subprocess_mod - subprocess 高级封装

对标准库 ``subprocess`` 进行高级封装，提供：

- :class:`VProcess`  : 子进程封装类，支持启动、获取输出/错误/返回码、超时控制、流式读取
- :class:`Pipeline`  : 管道，支持 ``|`` 语法链式命令执行
- :func:`run_command`: 一次性执行命令，返回 ``(returncode, stdout, stderr)``
- :func:`run_command_async`: 异步执行命令，返回 :class:`VProcess` 对象用于后续控制
- :func:`capture_output`: 捕获命令输出，支持实时回调
- :func:`which`: 查找可执行文件路径

典型用法::

    from vools.concurrent.subprocess_mod import run_command, Pipeline, VProcess

    # 一次性执行
    rc, out, err = run_command(["echo", "hello"])

    # 管道
    pipe = Pipeline(["echo", "hello"]) | ["tr", "a-z", "A-Z"]
    rc, out, err = pipe.run()

    # 异步执行 + 流式读取
    proc = run_command_async(["python", "-c", "for i in range(3): print(i)"])
    for line in proc.iter_stdout():
        print("line:", line)
    proc.wait()
"""

from __future__ import annotations

import sys
import shlex
import shutil
import subprocess
import threading
import time
from typing import (
    Any,
    Callable,
    Dict,
    IO,
    Iterator,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Union,
)

__all__ = [
    "VProcess",
    "Pipeline",
    "run_command",
    "run_command_async",
    "capture_output",
    "which",
]

# 命令描述类型：可以是字符串（会通过 shlex.split 拆分）或字符串序列
Command = Union[str, Sequence[str]]
# 回调类型
OutputCallback = Callable[[str, str], None]


def _normalize_command(cmd: Command, shell: bool = False) -> Union[str, List[str]]:
    """将命令归一化为 subprocess 可接受的形态。

    - 当 ``shell=True`` 时返回字符串
    - 当 ``shell=False`` 时返回 list[str]
    """
    if shell:
        if isinstance(cmd, (list, tuple)):
            return " ".join(shlex.quote(str(c)) for c in cmd)
        return str(cmd)
    if isinstance(cmd, str):
        return shlex.split(cmd)
    return [str(c) for c in cmd]


def _normalize_env(env: Optional[Mapping[str, str]]) -> Optional[Dict[str, str]]:
    """归一化环境变量字典为 ``Dict[str, str]``。"""
    if env is None:
        return None
    return {str(k): str(v) for k, v in env.items()}


class VProcess:
    """子进程封装类。

    封装 ``subprocess.Popen``，提供：

    - 启动命令（list 或 str）
    - stdin 输入
    - 环境变量、工作目录设置
    - 超时控制（wait/communicate 超时则杀死进程）
    - 流式读取 stdout / stderr
    - 获取返回码、stdout、stderr

    Args:
        cmd: 要执行的命令，字符串或字符串序列。
        stdin: 传入子进程 stdin 的内容。``None`` 表示不写入。
        env: 环境变量映射；``None`` 继承父进程。
        cwd: 工作目录；``None`` 使用当前目录。
        shell: 是否通过 shell 执行。
        timeout: 默认超时（秒），仅用于 :meth:`wait` / :meth:`communicate` 默认值。
        text: 是否以文本模式读写管道（默认 True）。
        encoding: 文本模式编码，``None`` 使用平台默认。
        hide_window: Windows 下是否隐藏控制台窗口（默认 True）。

    示例::

        proc = VProcess(["echo", "hi"])
        proc.wait()
        print(proc.returncode, proc.stdout)
    """

    def __init__(
        self,
        cmd: Command,
        stdin: Optional[Union[str, bytes]] = None,
        env: Optional[Mapping[str, str]] = None,
        cwd: Optional[str] = None,
        shell: bool = False,
        timeout: Optional[float] = None,
        text: bool = True,
        encoding: Optional[str] = None,
        hide_window: bool = True,
    ) -> None:
        self._cmd: Command = cmd
        self._shell: bool = shell
        self._timeout: Optional[float] = timeout
        self._text: bool = text
        self._encoding: Optional[str] = encoding
        self._hide_window: bool = hide_window

        self._stdin_data: Optional[Union[str, bytes]] = stdin
        self._env: Optional[Dict[str, str]] = _normalize_env(env)
        self._cwd: Optional[str] = cwd

        self._proc: Optional[subprocess.Popen] = None
        self._stdout: Optional[str] = None
        self._stderr: Optional[str] = None
        self._returncode: Optional[int] = None
        self._started: bool = False
        self._killed: bool = False

        # 自动启动
        self.start()

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def start(self) -> "VProcess":
        """启动子进程。重复调用时若已启动则直接返回自身。"""
        if self._started:
            return self
        args = _normalize_command(self._cmd, shell=self._shell)

        kwargs: Dict[str, Any] = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "stdin": subprocess.PIPE if self._stdin_data is not None else None,
            "shell": self._shell,
            "env": self._env,
            "cwd": self._cwd,
        }
        if self._text:
            kwargs["text"] = True
            kwargs["universal_newlines"] = True
            if self._encoding is not None:
                kwargs["encoding"] = self._encoding
        # Windows 隐藏控制台窗口
        if self._hide_window and sys.platform == "win32" and not self._shell:
            # CREATE_NO_WINDOW = 0x08000000
            kwargs["creationflags"] = kwargs.get("creationflags", 0) | 0x08000000

        self._proc = subprocess.Popen(args, **kwargs)
        self._started = True
        return self

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------
    @property
    def pid(self) -> Optional[int]:
        """子进程 PID，未启动时为 None。"""
        if self._proc is None:
            return None
        return self._proc.pid

    @property
    def returncode(self) -> Optional[int]:
        """返回码；未结束时为 None。"""
        if self._returncode is not None:
            return self._returncode
        if self._proc is not None:
            rc = self._proc.poll()
            if rc is not None:
                self._returncode = rc
            return rc
        return None

    @property
    def stdout(self) -> Optional[str]:
        """已 communicate 拿到的 stdout 内容。"""
        return self._stdout

    @property
    def stderr(self) -> Optional[str]:
        """已 communicate 拿到的 stderr 内容。"""
        return self._stderr

    @property
    def is_running(self) -> bool:
        """进程是否仍在运行。"""
        return self.returncode is None

    @property
    def process(self) -> Optional[subprocess.Popen]:
        """底层 ``Popen`` 对象（可能为 None）。"""
        return self._proc

    # ------------------------------------------------------------------
    # 交互
    # ------------------------------------------------------------------
    def wait(self, timeout: Optional[float] = None) -> int:
        """等待进程结束，返回返回码。

        Args:
            timeout: 超时秒数，``None`` 使用构造时的 ``timeout``。超时会杀死进程并抛出
                :class:`subprocess.TimeoutExpired`。
        """
        if self._proc is None:
            raise RuntimeError("Process not started")
        eff_timeout = timeout if timeout is not None else self._timeout
        try:
            rc = self._proc.wait(timeout=eff_timeout)
            self._returncode = rc
            return rc
        except subprocess.TimeoutExpired:
            self.kill()
            raise

    def communicate(
        self, timeout: Optional[float] = None
    ) -> Tuple[Optional[str], Optional[str]]:
        """与子进程交互：写入 stdin（如有）并读取全部 stdout/stderr。

        超时会杀死进程并抛出 :class:`subprocess.TimeoutExpired`。
        """
        if self._proc is None:
            raise RuntimeError("Process not started")
        eff_timeout = timeout if timeout is not None else self._timeout
        input_data = self._stdin_data
        try:
            out, err = self._proc.communicate(input=input_data, timeout=eff_timeout)
        except subprocess.TimeoutExpired:
            self.kill()
            out, err = self._proc.communicate()
            self._stdout = out
            self._stderr = err
            raise
        self._stdout = out
        self._stderr = err
        self._returncode = self._proc.returncode
        return out, err

    def kill(self) -> None:
        """强制杀死进程（先 terminate 再 kill）。"""
        if self._proc is None or self._killed:
            return
        try:
            self._proc.terminate()
        except Exception:
            pass
        try:
            self._proc.wait(timeout=1)
        except Exception:
            try:
                self._proc.kill()
            except Exception:
                pass
        self._killed = True
        self._returncode = self._proc.returncode

    def terminate(self) -> None:
        """发送终止信号（SIGTERM / Windows TerminateProcess）。"""
        if self._proc is None:
            return
        try:
            self._proc.terminate()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 流式读取
    # ------------------------------------------------------------------
    def iter_stdout(self, timeout: Optional[float] = None) -> Iterator[str]:
        """逐行迭代 stdout。

        注意：使用本方法时请确保子进程已启动且尚未 communicate。
        """
        if self._proc is None or self._proc.stdout is None:
            return
        stream = self._proc.stdout
        if timeout is not None:
            # 用线程读取避免阻塞超时
            import queue

            q: "queue.Queue[Optional[str]]" = queue.Queue()

            def _reader() -> None:
                try:
                    for line in stream:
                        q.put(line)
                finally:
                    q.put(None)

            t = threading.Thread(target=_reader, daemon=True)
            t.start()
            deadline = time.monotonic() + timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self.kill()
                    return
                try:
                    item = q.get(timeout=remaining)
                except Exception:
                    self.kill()
                    return
                if item is None:
                    return
                yield item
        else:
            for line in stream:
                yield line

    def iter_stderr(self) -> Iterator[str]:
        """逐行迭代 stderr。"""
        if self._proc is None or self._proc.stderr is None:
            return
        for line in self._proc.stderr:
            yield line

    def read_stdout(self) -> Optional[str]:
        """读取 stdout 已缓冲的内容（非阻塞，仅在 communicate 后有值）。"""
        return self._stdout

    def read_stderr(self) -> Optional[str]:
        """读取 stderr 已缓冲的内容。"""
        return self._stderr

    # ------------------------------------------------------------------
    # 上下文管理
    # ------------------------------------------------------------------
    def __enter__(self) -> "VProcess":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._proc is not None and self.is_running:
            self.kill()
        else:
            try:
                self.wait(timeout=0)
            except Exception:
                pass

    def __repr__(self) -> str:
        return (
            f"<VProcess cmd={self._cmd!r} pid={self.pid} "
            f"returncode={self.returncode}>"
        )


# ============================================================================
# Pipeline
# ============================================================================


class Pipeline:
    """命令管道，支持 ``|`` 语法链式执行。

    示例::

        pipe = Pipeline(["echo", "hello world"]) | ["tr", "a-z", "A-Z"]
        rc, out, err = pipe.run()

        # 也支持字符串
        pipe = Pipeline("echo hi") | "tr a-z A-Z"
    """

    def __init__(self, cmd: Command, shell: bool = False) -> None:
        self._stages: List[Tuple[Command, bool]] = [(cmd, shell)]
        self._env: Optional[Dict[str, str]] = None
        self._cwd: Optional[str] = None
        self._timeout: Optional[float] = None

    # ------------------------------------------------------------------
    # 配置
    # ------------------------------------------------------------------
    def env(self, env: Mapping[str, str]) -> "Pipeline":
        """设置所有阶段的环境变量。"""
        self._env = _normalize_env(env)
        return self

    def cwd(self, cwd: str) -> "Pipeline":
        """设置所有阶段的工作目录。"""
        self._cwd = cwd
        return self

    def timeout(self, seconds: float) -> "Pipeline":
        """设置总超时（仅作用于最终 run 阶段读取）。"""
        self._timeout = seconds
        return self

    # ------------------------------------------------------------------
    # 链式
    # ------------------------------------------------------------------
    def __or__(self, other: Command) -> "Pipeline":
        """``pipe | cmd`` 追加一阶段。"""
        if isinstance(other, Pipeline):
            self._stages.extend(other._stages)
            return self
        self._stages.append((other, False))
        return self

    def stage(self, cmd: Command, shell: bool = False) -> "Pipeline":
        """追加一阶段。"""
        self._stages.append((cmd, shell))
        return self

    # ------------------------------------------------------------------
    # 执行
    # ------------------------------------------------------------------
    def run(
        self, timeout: Optional[float] = None
    ) -> Tuple[int, str, str]:
        """执行整条管道，返回 ``(returncode, stdout, stderr)``。

        任一阶段失败（返回码非 0）则中断管道并返回该阶段结果。
        """
        if not self._stages:
            return 0, "", ""

        stages = self._stages
        procs: List[subprocess.Popen] = []
        prev_stdout: Optional[IO[Any]] = None
        try:
            for cmd, shell in stages:
                args = _normalize_command(cmd, shell=shell)
                kwargs: Dict[str, Any] = {
                    "stdin": prev_stdout if prev_stdout is not None else subprocess.PIPE,
                    "stdout": subprocess.PIPE,
                    "stderr": subprocess.PIPE,
                    "shell": shell,
                    "env": self._env,
                    "cwd": self._cwd,
                    "text": True,
                    "universal_newlines": True,
                }
                # Windows 隐藏控制台
                if sys.platform == "win32" and not shell:
                    kwargs["creationflags"] = 0x08000000
                proc = subprocess.Popen(args, **kwargs)
                procs.append(proc)
                prev_stdout = proc.stdout

            # 向第一阶段写空 stdin（避免阻塞）
            if procs[0].stdin is not None:
                try:
                    procs[0].stdin.close()
                except Exception:
                    pass

            # 收集最后一阶段输出
            last = procs[-1]
            eff_timeout = timeout if timeout is not None else self._timeout
            try:
                out, err = last.communicate(timeout=eff_timeout)
            except subprocess.TimeoutExpired:
                for p in procs:
                    try:
                        p.kill()
                    except Exception:
                        pass
                raise

            # 等待前序阶段结束（避免僵尸）
            for p in procs[:-1]:
                try:
                    p.wait(timeout=5)
                except Exception:
                    try:
                        p.kill()
                    except Exception:
                        pass

            return last.returncode or 0, out or "", err or ""
        finally:
            # 确保异常路径下关闭所有进程
            for p in procs:
                if p.poll() is None:
                    try:
                        p.kill()
                    except Exception:
                        pass

    def __repr__(self) -> str:
        cmds = [repr(c) for c, _ in self._stages]
        return f"<Pipeline {' | '.join(cmds)}>"


# ============================================================================
# 函数式 API
# ============================================================================


def run_command(
    cmd: Command,
    stdin: Optional[Union[str, bytes]] = None,
    env: Optional[Mapping[str, str]] = None,
    cwd: Optional[str] = None,
    shell: bool = False,
    timeout: Optional[float] = None,
    encoding: Optional[str] = None,
    hide_window: bool = True,
) -> Tuple[int, str, str]:
    """一次性执行命令，返回 ``(returncode, stdout, stderr)``。

    Args:
        cmd: 命令，字符串或字符串序列。
        stdin: 传入 stdin 的内容。
        env: 环境变量映射。
        cwd: 工作目录。
        shell: 是否通过 shell 执行。
        timeout: 超时秒数，超时会杀死进程并抛出 :class:`subprocess.TimeoutExpired`。
        encoding: 文本编码；``None`` 使用平台默认。
        hide_window: Windows 下是否隐藏控制台窗口。

    Returns:
        Tuple[int, str, str]: ``(returncode, stdout, stderr)``。

    示例::

        rc, out, err = run_command(["echo", "hello"])
    """
    proc = VProcess(
        cmd,
        stdin=stdin,
        env=env,
        cwd=cwd,
        shell=shell,
        timeout=timeout,
        text=True,
        encoding=encoding,
        hide_window=hide_window,
    )
    out, err = proc.communicate(timeout=timeout)
    return proc.returncode or 0, out or "", err or ""


def run_command_async(
    cmd: Command,
    stdin: Optional[Union[str, bytes]] = None,
    env: Optional[Mapping[str, str]] = None,
    cwd: Optional[str] = None,
    shell: bool = False,
    timeout: Optional[float] = None,
    encoding: Optional[str] = None,
    hide_window: bool = True,
) -> VProcess:
    """异步执行命令，立即返回 :class:`VProcess` 对象用于后续控制。

    示例::

        proc = run_command_async(["ping", "127.0.0.1"])
        for line in proc.iter_stdout():
            print(line.strip())
        proc.wait(timeout=10)
    """
    return VProcess(
        cmd,
        stdin=stdin,
        env=env,
        cwd=cwd,
        shell=shell,
        timeout=timeout,
        text=True,
        encoding=encoding,
        hide_window=hide_window,
    )


def capture_output(
    cmd: Command,
    callback: Optional[OutputCallback] = None,
    env: Optional[Mapping[str, str]] = None,
    cwd: Optional[str] = None,
    shell: bool = False,
    timeout: Optional[float] = None,
    encoding: Optional[str] = None,
    hide_window: bool = True,
) -> Tuple[int, str, str]:
    """捕获命令输出，支持实时回调。

    Args:
        cmd: 命令。
        callback: 实时回调 ``callback(line, stream)``，``stream`` 为 ``"stdout"`` 或 ``"stderr"``。
        env: 环境变量。
        cwd: 工作目录。
        shell: 是否通过 shell 执行。
        timeout: 超时秒数。
        encoding: 文本编码。
        hide_window: Windows 下是否隐藏控制台窗口。

    Returns:
        Tuple[int, str, str]: ``(returncode, stdout, stderr)``。

    示例::

        def cb(line, stream):
            print(f"[{stream}] {line.rstrip()}")

        rc, out, err = capture_output(["python", "-c", "print(1); print(2)"], callback=cb)
    """
    proc = VProcess(
        cmd,
        stdin=None,
        env=env,
        cwd=cwd,
        shell=shell,
        timeout=timeout,
        text=True,
        encoding=encoding,
        hide_window=hide_window,
    )
    stdout_lines: List[str] = []
    stderr_lines: List[str] = []
    stdout_thread: Optional[threading.Thread] = None
    stderr_thread: Optional[threading.Thread] = None

    def _read_stream(
        stream: Optional[IO[Any]], buf: List[str], name: str
    ) -> None:
        if stream is None:
            return
        try:
            for line in stream:
                buf.append(line)
                if callback is not None:
                    try:
                        callback(line, name)
                    except Exception:
                        pass
        except Exception:
            pass

    if proc.process is not None:
        stdout_thread = threading.Thread(
            target=_read_stream,
            args=(proc.process.stdout, stdout_lines, "stdout"),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=_read_stream,
            args=(proc.process.stderr, stderr_lines, "stderr"),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()

    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        if stdout_thread is not None:
            stdout_thread.join(timeout=1)
        if stderr_thread is not None:
            stderr_thread.join(timeout=1)
        raise

    if stdout_thread is not None:
        stdout_thread.join(timeout=5)
    if stderr_thread is not None:
        stderr_thread.join(timeout=5)

    return (
        proc.returncode or 0,
        "".join(stdout_lines),
        "".join(stderr_lines),
    )


def which(
    cmd: str, path: Optional[str] = None
) -> Optional[str]:
    """查找可执行文件路径。

    包装 :func:`shutil.which`，返回绝对路径或 ``None``。

    Args:
        cmd: 可执行文件名。
        path: 自定义搜索路径（``os.pathsep`` 分隔）；``None`` 使用 ``PATH``。

    Returns:
        Optional[str]: 找到的绝对路径，未找到为 ``None``。

    示例::

        python_path = which("python")
    """
    return shutil.which(cmd, path=path)
