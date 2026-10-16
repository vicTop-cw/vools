"""
vools.bridge.core.wsl - WSL 辅助工具

为 Windows 上的桥接模块提供统一的 WSL 检测、路径转换和命令执行接口。
"""

import os
import shutil
import time
import platform
import subprocess
from typing import Optional, List

_IS_WINDOWS = platform.system() == 'Windows'

# 进程级缓存：WSL 可用性与「某命令是否在 WSL 中」在一次进程生命周期内不变。
# 不加缓存时，bridges 探测路径（configs.resolve_compiler 第 7 步 / probe 的
# 每个语言）会为每个语言各起 1 次 `wsl --version` + N 次 `wsl which`，
# 累计几十次 wsl.exe 进程（实测 resolve_compiler 全量 17.6s、
# 本机 probe 全量 36.8s，其中 dart 单语言 10.9s、freebasic 6.6s）。
# 缓存后同一进程内只探测一次 WSL 可用性，命令查询按命令名缓存。
_WSL_AVAILABLE_CACHE: Optional[bool] = None
_WSL_COMMAND_CACHE: dict = {}


def _probe_wsl(cmd, per_try_timeout: float, attempts: int = 4, backoff: float = 1.0):
    """对 WSL 命令做带退避的探测，区分「确证结果」与「超时/瞬时不可用」。

    WSL 虚拟机冷启动（例如上一个进程把 wsl.exe 杀掉后，下一次要等 VM 重新拉起）
    会让前几次调用超时。冷启动期间的超时【不是】"WSL 不可用"，若据此缓存 False，
    会在整个进程生命周期内把可用环境误判为不可用（表现为 dart/kotlin/… 的
    "compiler not available" 假 skip）。

    Returns:
        (result, definitive): result 为最后一次观察到的 bool；definitive=True 表示
        命令确实在超时之外跑出来了（可安全缓存）；definitive=False 表示每次都超时，
        属瞬时状态，不应被缓存。
    """
    for i in range(max(1, attempts)):
        try:
            r = subprocess.run(
                cmd,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=per_try_timeout,
            )
            if r.returncode == 0:
                return True, True
            # rc!=0：WSL VM 正在重启时 wsl.exe 会【快速】返回非零（不是超时），单次
            # 观测上与"工具确实没装"不可分辨。pytest 的 skipif 只在收集期求值一次，
            # 撞上一次快速非零就把整个会话标成 skip——实测多 agent 并发跑 WSL 用例
            # 时 test_swift_bridge 9 个 skip、test_shell_bridge 1 个 fail 即此形状
            # （隔离复跑立即通过）。故 rc!=0 与超时同等对待：退避重试，全部用完
            # 仍非零才判 False。
            if i < attempts - 1:
                time.sleep(backoff * (i + 1))
                continue
            return False, True
        except subprocess.TimeoutExpired:
            # 冷启动/瞬时挂起：不算确证，退避后重试
            if i < attempts - 1:
                time.sleep(backoff * (i + 1))
            continue
        except (FileNotFoundError, OSError):
            # wsl 不存在或无法启动子进程：确证不可用
            return False, True
    return False, False


def is_wsl_available() -> bool:
    """检查 WSL 是否可用（仅 Windows 上）。

    只缓存 True：WSL 冷启动/服务未就绪时的 False（超时或瞬态非零）若被缓存，
    会在整个进程生命周期内把可用环境误判为不可用（实测把 py3.11 批跑的
    test_dart_bridge 毒化成 15 个假 skip）。False 不缓存 = 每次重探，
    VM 起来后自动恢复；wsl 真不存在的机器上 `wsl --version` 立即失败，开销可忽略。
    """
    global _WSL_AVAILABLE_CACHE
    if not _IS_WINDOWS:
        return False
    if _WSL_AVAILABLE_CACHE:
        return True
    ok, _definitive = _probe_wsl(['wsl', '--version'], per_try_timeout=5)
    if ok:
        _WSL_AVAILABLE_CACHE = True
    return ok


def check_wsl_command(cmd: str) -> bool:
    """检查 WSL 中是否存在指定命令（结果按命令名缓存，且只缓存 True，理由同上）。"""
    if _WSL_COMMAND_CACHE.get(cmd):
        return True
    if not is_wsl_available():
        return False
    ok, _definitive = _probe_wsl(['wsl', 'which', cmd], per_try_timeout=10)
    if ok:
        _WSL_COMMAND_CACHE[cmd] = True
    return ok


class WSLGate:
    """惰性求值的 WSL 可用性闸门（True 后锁定，False 每次重算）。

    各语言 compiler.py 原来在【模块导入期】算 `_USE_WSL = ... and _check_wsl() ...`
    并冻结成模块常量；若那一刻恰逢 WSL 冷启动（VM 正在重启），False 就被永久
    冻结、整个测试会话假 skip。改成闸门后：`if _USE_WSL:` 等既有布尔用法不变
    （通过 __bool__ 惰性求值），而 False 不再被固化。
    """

    __slots__ = ('_compute', '_ready')

    def __init__(self, compute):
        self._compute = compute
        self._ready = False

    def __bool__(self):
        if not self._ready:
            try:
                if self._compute():
                    self._ready = True
            except Exception:
                return False
        return self._ready

    def __repr__(self):
        return '<WSLGate ready=%s>' % self._ready


def probe_wsl_cmd(args, per_try_timeout: float = 15) -> bool:
    """在 WSL 中运行 `wsl <args...>` 并判断返回码是否为 0（冷启动容错 + 退避重试）。

    给各语言桥接模块做"WSL 里有没有这个工具链"探测用（例如 `wsl dart --version`、
    `wsl bash -c "which kotlinc && which kotlin"`），替代每个模块自己写、且会把
    WSL 冷启动超时误判成"不可用"并进程级缓存的死代码。冷启动期间命令超时会退避重试。
    """
    if not is_wsl_available():
        return False
    cmd = ['wsl'] + list(args)
    ok, _definitive = _probe_wsl(cmd, per_try_timeout=per_try_timeout)
    return ok


def reset_cache() -> None:
    """清空 WSL 探测缓存（测试或环境变化后调用）。"""
    global _WSL_AVAILABLE_CACHE
    _WSL_AVAILABLE_CACHE = None
    _WSL_COMMAND_CACHE.clear()


def windows_to_wsl_path(windows_path: str) -> str:
    """将 Windows 绝对路径转换为 WSL 路径。

    例如：C:\\Users\\foo\\bar -> /mnt/c/Users/foo/bar
    """
    windows_path = os.path.abspath(windows_path)
    drive = windows_path[0].lower()
    rest = windows_path[2:].replace('\\', '/')
    return f'/mnt/{drive}{rest}'


def wsl_run(cmd_args: List[str], timeout: int = 60,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text: bool = True, **kwargs) -> subprocess.CompletedProcess:
    """通过 WSL 运行命令，自动处理编码问题"""
    wsl_cmd = ['wsl'] + cmd_args
    if text:
        result = subprocess.run(
            wsl_cmd,
            stdout=stdout, stderr=stderr,
            timeout=timeout,
        )
        result.stdout = result.stdout.decode('utf-8', errors='replace') if result.stdout else ''
        result.stderr = result.stderr.decode('utf-8', errors='replace') if result.stderr else ''
        return result
    return subprocess.run(wsl_cmd, stdout=stdout, stderr=stderr,
                          timeout=timeout, text=text, **kwargs)


def resolve_command(local_name: str) -> tuple:
    """解析命令，返回 (cmd_prefix, path_converter, use_wsl)

    检测顺序：
    1. 本地命令（PATH 或常见路径）
    2. WSL 中的同名命令

    返回：
        (cmd_prefix, path_converter, use_wsl)
        - cmd_prefix: 可传给 subprocess 的列表，如 ['ruby'] 或 ['wsl', 'ruby']
        - path_converter: 函数，将 Windows 路径转为运行时可识别的路径
        - use_wsl: 是否使用 WSL
    """
    # 1. 本地命令
    local_path = shutil.which(local_name)
    if local_path:
        return ([local_path], lambda p: p, False)

    # 2. WSL 命令
    if _IS_WINDOWS and check_wsl_command(local_name):
        return (['wsl', local_name], windows_to_wsl_path, True)

    # 3. 回退：【未经验证】地给出裸命令名。这是为了兼容执行期「让 OS 报错」
    #    的旧行为，但它【不代表命令存在】——调用方不得据此判定 available()。
    #    是否真的可用请用 command_resolves() 判断。
    return ([local_name], lambda p: p, False)


def command_resolves(local_name: str) -> bool:
    """命令是否在【本地 PATH】或【WSL】中确实可解析。

    与 resolve_command 的区别：resolve_command 第 3 分支在两处都找不到时
    仍回退裸命令名（供执行期把错误交给 OS），那个返回值不能用来回答
    「工具链可用吗」。本谓词只在 shutil.which 命中或 WSL 里 which 命中时
    返回 True，是 *_available() 的正确依据，避免「探测说有、一跑就
    FileNotFoundError」的假可用（pentad p5c 实测即此问题）。

    Args:
        local_name: 可执行文件名，如 'p5c' / 'ruby'。

    Returns:
        bool: 本地或 WSL 中能定位到该命令才 True。
    """
    if shutil.which(local_name):
        return True
    if _IS_WINDOWS and check_wsl_command(local_name):
        return True
    return False
