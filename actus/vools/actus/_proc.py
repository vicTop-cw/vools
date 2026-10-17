"""_proc.py — vools.actus 内部的进程树安全 subprocess 包装。

与 `bridges/vools/bridge/probe._run_cmd_timeout` 同族，供本包内所有需要
`subprocess.run(timeout=N)` 的模块共用，避免每处重复写 kill-tree 逻辑。

**为什么单独一个模块**：dependency.py / repo.py / publisher.py 等都会起
`pip install` / `git` / `npx` 这类会 spawn 子进程的命令；超时后若只 kill
父进程，孙进程会变孤儿。统一在这里收口，改一处全包生效。

**行为契约**（与 `subprocess.run` 对齐，但超时不抛 `TimeoutExpired`）：
- 正常返回：`CompletedProcess(cmd, returncode, stdout, stderr)`，与 subprocess 一致
- 超时：先杀进程树（Windows `taskkill /T /F`；POSIX `pkill -TERM` / killpg），
  再回收 stdio，返回 `CompletedProcess(cmd, -9, stdout, stderr)`
- spawn 失败：返回 `CompletedProcess(cmd, -1, '', str(exc))`，不抛
"""

from __future__ import annotations

import os
import subprocess
from typing import Any, Optional, Sequence, Union

__all__ = ['run_cmd_safe']

CmdType = Union[str, Sequence[str]]


def run_cmd_safe(
    cmd: CmdType,
    *,
    timeout: int,
    cwd: Optional[str] = None,
    shell: bool = False,
    env: Optional[dict] = None,
    input: Optional[str] = None,
) -> subprocess.CompletedProcess:
    """进程树安全的 subprocess 包装（超时杀树，从不抛 TimeoutExpired）。

    支持 `input=`（等价 subprocess.run 的 stdin 注入），
    支持 `env=`、`cwd=`、`shell=`。
    """
    is_win = os.name == 'nt'
    creationflags = 0
    if is_win:
        creationflags = getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
    try:
        proc = subprocess.Popen(
            cmd,
            shell=shell,
            cwd=cwd,
            env=env,
            stdin=subprocess.PIPE if input is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
            creationflags=creationflags,
        )
    except Exception as exc:  # noqa: BLE001
        return subprocess.CompletedProcess(cmd, -1, '', str(exc))
    try:
        stdout, stderr = proc.communicate(input=input, timeout=timeout)
        return subprocess.CompletedProcess(
            cmd, proc.returncode,
            stdout or '', stderr or '',
        )
    except subprocess.TimeoutExpired:
        # 超时：杀整棵进程树
        try:
            if is_win:
                subprocess.Popen(
                    ['taskkill', '/F', '/T', '/PID', str(proc.pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                ).wait(timeout=5)
            else:
                try:
                    os.killpg(os.getpgid(proc.pid), 15)
                except Exception:  # noqa: BLE001
                    proc.kill()
        except Exception:  # noqa: BLE001
            try:
                proc.kill()
            except Exception:  # noqa: BLE001
                pass
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except Exception:  # noqa: BLE001
            stdout, stderr = '', ''
        return subprocess.CompletedProcess(
            cmd, -9, stdout or '', stderr or '',
        )