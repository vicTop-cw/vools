"""_proc.py — vools.actus 内部的进程树安全 subprocess 包装。

与 `bridges/vools/bridge/probe._run_cmd_timeout` 同族，供本包内所有需要
`subprocess.run(timeout=N)` 的模块共用，避免每处重复写 kill-tree 逻辑。

**为什么单独一个模块**：dependency.py / repo.py / publisher.py 等都会起
`pip install` / `git` / `npx` 这类会 spawn 子进程的命令；超时后若只 kill
父进程，孙进程会变孤儿。统一在这里收口，改一处全包生效。

**行为契约**（与 `subprocess.run` 对齐，但超时不抛 `TimeoutExpired`）：
- 正常返回：`CompletedProcess(cmd, returncode, stdout, stderr)`，与 subprocess 一致
- 超时：先杀进程树（Windows：psutil 递归 kill，失败回落 `taskkill /T /F`；
  POSIX：`killpg`），再回收 stdio，返回 `CompletedProcess(cmd, -9, stdout, stderr)`
- spawn 失败：返回 `CompletedProcess(cmd, -1, '', str(exc))`，不抛

**杀进程树为什么用 psutil，而不是 Job Object**（2026-10 实测，见
`build/probe_evidence/measure_kill_tree.py`）：
- 同步 `taskkill /F /T` 实测 **~400ms**（真实 pnpm 超时路径 320ms）——它就是
  Windows 上「超时后清理」的主要开销来源之一；
- psutil 递归 kill 实测 **~14ms（合成）/ 50~70ms（真实 pnpm 链路）**，孤儿 0；
- Windows Job Object（`TerminateJobObject`）理论最优（0.1ms），但要处理
  assign 竞态（`CREATE_SUSPENDED` + `ResumeThread`）与**嵌套 Job**（本进程
  自身可能已处于 DSH 的 Job runner 里），复杂度/风险与收益不成比例 ——
  先拿 psutil 这份确定性收益，Job Object 留作后续可选优化。
- 只 kill 直接子进程（0.5ms）**不可取**：实测会留下孤儿孙进程，正是超时后
  「管道被孙进程握着、communicate 继续阻塞」那类问题的根源。

**零硬依赖**：`pyproject.toml` 没有声明 psutil，所以这里**懒导入**；psutil
不可用或递归 kill 抛异常时，**回落**到原来的 `taskkill /T /F` 路径（行为与
改造前一致，绝不因为新路径失败而不杀进程）。回落不是静默的：`KILL_TREE_STATS`
计数 + `logging` 记录（`psutil_unavailable` 只记一次，避免刷屏）。
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from typing import Any, Optional, Sequence, Union

__all__ = ['run_cmd_safe', 'kill_tree', 'KILL_TREE_STATS']

CmdType = Union[str, Sequence[str]]

_log = logging.getLogger(__name__)

# 可查的健康计数（非静默）：走了哪条清理路径、psutil 失败/缺失过几次。
KILL_TREE_STATS = {
    'psutil': 0,            # psutil 递归 kill 成功
    'psutil_failed': 0,     # psutil 路径抛异常 → 回落 taskkill
    'psutil_unavailable': 0,  # 环境里没有 psutil → 回落 taskkill
    'taskkill': 0,          # 实际执行了 taskkill 回落路径
    'posix': 0,             # POSIX killpg 路径
}

# 复扫窗口（秒）：`children(recursive=True)` 的枚举与 kill 之间不是原子的，
# 窗口期内可能有新派生的孙进程；30ms 足够覆盖这种极小概率的竞争。
_KILL_RESWEEP_SEC = 0.03

# taskkill 回落路径自身的上限（与改造前一致）。
_TASKKILL_TIMEOUT_SEC = 5

# 超时后回收管道的宽限（秒）：**宽限只是兜底、不是等待策略** —— 若孙进程还
# 握着管道，继续等会把"超时"变成"超时+5s"（system_tools 侧踩过这个坑）。
_REAP_GRACE_SEC = 0.2

# "psutil 不可用"只记一次日志，避免每次超时都刷屏。
_psutil_unavailable_logged = False


def _load_psutil():
    """懒导入 psutil（`_proc` 必须保持零硬依赖：pyproject 未声明 psutil）。"""
    try:
        import psutil  # noqa: F401  — 刻意懒导入
    except Exception:  # noqa: BLE001  — ImportError 之外（极少数环境损坏）也算不可用
        return None
    return psutil


def _psutil_kill_tree(proc, psutil) -> bool:
    """psutil 递归 kill：**先杀子孙（叶子先死），最后杀父**，30ms 内复扫一次。

    先子后父是刻意的：父在的时候会继续派生新子进程；先把父杀掉反而会让
    「边杀边生」的窗口变成孤儿。最后 30ms 复扫补杀窗口期内新派生/没死透的。

    返回 True 表示「psutil 路径已尽力处理」（不需要回落）；False 表示 psutil
    无法接手（父进程句柄打不开等），交给调用方回落 taskkill。
    """
    pid = getattr(proc, 'pid', None)
    if not pid:
        return False
    try:
        parent = psutil.Process(pid)
    except Exception:  # noqa: BLE001
        # 进程已经退出：没有可杀的父进程；它的子孙也早就脱离树，taskkill /T
        # 同样追不到 —— 视为已处理，不做无意义的回落。
        return True

    try:
        children = parent.children(recursive=True)
    except Exception:  # noqa: BLE001
        children = []

    # ① 先杀子孙（children 一般是「父→子」序，反转后先动最深的）
    for child in reversed(children):
        try:
            child.kill()
        except Exception:  # noqa: BLE001
            pass

    # ② 再杀父
    try:
        parent.kill()
    except Exception:  # noqa: BLE001
        pass

    # ③ 30ms 复扫：补杀窗口期内新派生 / 没死透的子孙
    deadline = time.monotonic() + _KILL_RESWEEP_SEC
    pending = list(children)
    while pending and time.monotonic() < deadline:
        still_alive = []
        for child in pending:
            try:
                if child.is_running():
                    still_alive.append(child)
            except Exception:  # noqa: BLE001
                pass
        if not still_alive:
            break
        for child in still_alive:
            try:
                child.kill()
            except Exception:  # noqa: BLE001
                pass
        pending = still_alive
        time.sleep(0.005)
    return True


def kill_tree(proc: subprocess.Popen) -> None:
    """杀掉 proc 及其整棵进程树（Windows psutil 递归 kill，回落 taskkill /T；POSIX killpg）。

    供 run_cmd_safe 内部与 Popen 管线（如 jump.py 的 tar|ssh）共用。
    **签名与语义保持一字不变**：调用方一个都不用改；清理路径不许再抛异常。
    """
    try:
        if os.name != 'nt':
            # POSIX：保持改造前的行为（killpg → 兜底 proc.kill）
            KILL_TREE_STATS['posix'] += 1
            try:
                os.killpg(os.getpgid(proc.pid), 15)
            except Exception:  # noqa: BLE001
                proc.kill()
            return

        psutil = _load_psutil()
        if psutil is None:
            global _psutil_unavailable_logged
            KILL_TREE_STATS['psutil_unavailable'] += 1
            if not _psutil_unavailable_logged:
                _psutil_unavailable_logged = True
                _log.debug('kill_tree: 环境无 psutil，回落 taskkill /T /F')
        else:
            try:
                if _psutil_kill_tree(proc, psutil):
                    KILL_TREE_STATS['psutil'] += 1
                    return
            except Exception:  # noqa: BLE001  — 任何异常都不许冒出清理路径
                KILL_TREE_STATS['psutil_failed'] += 1
                _log.debug('kill_tree: psutil 递归 kill 失败，回落 taskkill /T /F',
                           exc_info=True)

        # 回落：改造前的 taskkill 路径（行为一字不变）
        KILL_TREE_STATS['taskkill'] += 1
        subprocess.Popen(
            ['taskkill', '/F', '/T', '/PID', str(proc.pid)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ).wait(timeout=_TASKKILL_TIMEOUT_SEC)
    except Exception:  # noqa: BLE001  — 清理路径不许抛
        try:
            proc.kill()
        except Exception:  # noqa: BLE001
            pass


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
        kill_tree(proc)
        # 宽限只作兜底：树杀干净后管道会立刻关闭；若仍有孙进程握管，
        # 继续等会把"超时"放大成"超时+5s"（system_tools 侧实测过 8.8s）。
        try:
            stdout, stderr = proc.communicate(timeout=_REAP_GRACE_SEC)
        except Exception:  # noqa: BLE001
            for stream in (getattr(proc, 'stdout', None),
                           getattr(proc, 'stderr', None)):
                try:
                    if stream is not None:
                        stream.close()
                except Exception:  # noqa: BLE001
                    pass
            stdout, stderr = '', ''
        return subprocess.CompletedProcess(
            cmd, -9, stdout or '', stderr or '',
        )
