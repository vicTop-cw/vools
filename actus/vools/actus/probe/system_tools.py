"""probe/system_tools.py — 系统工具探测。

通过 shutil.which + subprocess 探测已知工具表中的每个工具。

并行化（工具表涨到 65 条后的性能收口）
--------------------------------------
改前：串行 for 循环，65 个工具逐个「查 PATH/已知路径 → 起子进程取版本」。
单项成本 = 查找 10~190ms（PATH 扫不中时最贵）+ 起进程取版本 0~900ms，
串行累加成整条 probe 的耗时地板（实测 SystemToolsProber 10.7~15.3s，
probe 并行池总墙钟 11.1s 里它一个人占 11.1s）。

改后：同一 ThreadPoolExecutor 内分两阶段并发 ——
  阶段 1「查找」：PATH 只 listdir 一遍建索引，65 个工具从索引里取（附 os.access 复核）；
  阶段 2「取版本」：只对**找到的**工具并发跑 version 命令。
两阶段不是额外等待，而是把「找不到」与「找到了但版本取不到」分开归因；
改后阶段 1 是几十毫秒级，barrier 成本可以忽略。

为什么阶段 1 不能只是「多线程调 shutil.which」
----------------------------------------------
本机 PATH 有 89 个目录、1.7 万个文件，而 65 个工具里 42 个根本不存在；
`shutil.which` 对每个不存在的名字都要把 89 个目录 × PATHEXT 试一遍
（实测单次 ~110ms，42 次 ≈ 4.6s，8 线程只压到 1.5s —— 瓶颈是 stat 风暴不是等待）。
把每个 PATH 目录 listdir 一次只要 52ms，之后每个候选只是集合查找 + 命中后
用 os.access 复核一次，**候选名与目录的尝试顺序仍与 which 相同**。

等价性（硬要求）：结果按 TOOL_TABLE **原下标回填**，再顺序取出 —— items 的
顺序与内容与串行版逐字一致，并发只影响墙钟。单个工具的异常被关在自己的
future 里（串行版里它会抛穿整个探测器），不影响其它 64 条。

总预算：整批给一个上限（`total_budget`，默认 15.0s，病态兜底性质，不是达标手段）。
超预算时阶段 1 未完成的工具记「未探测到」、阶段 2 未完成的记「找到了、版本未取到」，
两种都带 error 说明原因（**不静默**），排队中的 future 会被 cancel 不再起新进程。
单个工具卡死由它自己的 subprocess timeout（5s/10s）兜底，正常路径实测 ~1.5s，
预算不参与达标；卡太紧反而会把「机器一时慢」变成假阴性（见常量处注释）。

内层/外层并发争用：内层线程数**自适应**（`_resolve_workers`）—— 主线程单跑用 16，
被 probe() 外层池调用时降到 8（受控实验：嵌套墙钟 16→2.87s、8→2.04s）。
曾试过「跨探测器共享信号量限流」，实测更慢（只约束自己、不约束别人的探测器），
故默认关闭，只保留旋钮（见 `set_inner_concurrency_limit`）。

子进程隔离：版本探测子进程的 cwd 一律指向探测临时目录（`_probe_tmpdir`），
防止 JVM 之类的工具把崩溃转储（hs_err_pid*.log / replay_pid*.log）写进用户
项目目录；命中崩溃特征串记 version_error_kind="crashed"，进程退出时清理临时目录。

契约冻结：`_find_tool` / `_get_version` 同时被 platform_tools.py 复用
（`from .system_tools import _find_tool, _get_version`）。
  * `_find_tool(name, aliases, well_known_paths)`：三参调用**行为逐字不变**
    （仍走 shutil.which）；索引是新增的**可选第四参**，只有本模块传入。
  * `_get_version`：返回值必须仍是 str、失败仍须是 ""（它按 `if version_line:` 判定）；
    需要失败原因的下游改用新增的 `_get_version_detail`。
"""


__all__ = [
    "SystemToolsProber",
]

import atexit
import bisect
import concurrent.futures
import contextlib
import glob as globmod
import locale
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

from .base import Prober, ProbeItem
from .TOOL_TABLE import TOOL_TABLE


# ── 版本探测子进程的工作目录：临时目录（防止副产物污染用户工作区）──
# 为什么必须做：JVM 崩溃时把 hs_err_pid*.log / replay_pid*.log 写到**当前工作
# 目录**，而子进程默认继承探针进程的 cwd（= 用户执行 `actus probe` 时所在的目录）。
# 实测仓库 actus/ 下出现过 4 个 hs_err_pid*.log —— 一条只读 probe 把垃圾留在了
# 用户项目里，还可能被误提交。现在所有版本探测子进程的 cwd 都指到临时目录，
# 副产物落在系统临时区，进程退出时整目录删掉（`cleanup_probe_tmpdir`）。
_PROBE_TMPDIR = None
_PROBE_TMPDIR_LOCK = threading.Lock()

# JVM/Runtime 崩溃的特征串。
# 两类都要覆盖：HotSpot「崩溃转储」（fatal error + hs_err_pid*.log）与
# 「初始化期就分配不到内存」（实测这台机器上 4 个 hs_err 就是这个形态：
#  insufficient memory ... mmap failed / Error occurred during initialization of VM）。
_CRASH_MARKERS = (
    "A fatal error has been detected",
    "An unexpected error has been detected",
    "EXCEPTION_ACCESS_VIOLATION",
    "SIGSEGV",
    "hs_err_pid",
    "replay_pid",
    "insufficient memory for the Java Runtime Environment",
    "Error occurred during initialization of VM",
    "Could not reserve enough space",
)


def _probe_tmpdir():
    """懒创建本进程统一的探测临时 cwd（全进程复用同一个目录）。"""
    global _PROBE_TMPDIR
    with _PROBE_TMPDIR_LOCK:
        if _PROBE_TMPDIR is None:
            try:
                _PROBE_TMPDIR = tempfile.mkdtemp(prefix="actus-probe-")
            except OSError:
                return None          # 建不出来就退回继承 cwd（不阻塞探测）
        return _PROBE_TMPDIR


def cleanup_probe_tmpdir():
    """删除探测临时 cwd（进程退出时自动执行，也可手工调用）。"""
    global _PROBE_TMPDIR
    with _PROBE_TMPDIR_LOCK:
        directory, _PROBE_TMPDIR = _PROBE_TMPDIR, None
    if directory:
        shutil.rmtree(directory, ignore_errors=True)


atexit.register(cleanup_probe_tmpdir)


def _crash_marker(*texts):
    """在输出里找崩溃特征串，命中返回它（用于 version_error_kind="crashed"）。"""
    for text in texts:
        if not text:
            continue
        for marker in _CRASH_MARKERS:
            if marker in text:
                return marker
    return None


# 并发度：65 个工具绝大多数时间花在「起子进程」的等待上（IO 型）；
# 本机实测 16 与 24 打平、8 明显更慢（见交付报告的单探测器耗时对比）。
# 16 = 本机实测最优点；可在构造时覆盖。
_DEFAULT_MAX_WORKERS = 16

# 内层并发闸门（**默认关闭**，保留旋钮）：
# 一开始按「一次只允许 N 个内层任务起子进程」实现，实测**反而更慢** ——
# 闸门只约束「我的 3 个探测器」，不约束 python_pkgs / platform_tools 等别人的
# 探测器，所以它等于只给自己戴镣铐：受控实验（3 探测器并发 + 4 个背景子进程
# 风暴线程）里 off=2.15s、limit 8=2.81s、limit 24=2.86s、limit 64=3.19s。
# 结论：争用要靠「降内层线程数」（见 `_resolve_workers`），不能靠闸门。
# 旋钮保留给「需要把总并发钉死」的场景；<=0（默认）表示不设闸门。
_MAX_CONCURRENT_INNER_TASKS = 0
_INNER_SEMAPHORE = None
_INNER_SEMAPHORE_LOCK = threading.Lock()

# 内层并发度自适应（实测数据见 `_resolve_workers`）
_NESTED_MAX_WORKERS = 8


def _resolve_workers(override=None):
    """按「是否被外层线程池调用」给内层并发度分档。

    * 主线程（用户直接跑单个探测器 / 单测）：`_DEFAULT_MAX_WORKERS` = 16。
      单跑实测 16 → 1.22s，8 → 1.41s（16 更好）。
    * 非主线程（= 被 probe() 的 8 线程外层池调用）：降档到 8。
      受控实验（3 个探测器并发，背景 4 个「起子进程」风暴线程）：
        内层 16 → 嵌套墙钟 2.87s；内层 8 → 2.04s（-29%）；
        内层 4/6 → 2.07/2.00s（与 8 打平，不必再降）
      即：外层已经并发了 8~9 个探测器时，内层再开满 16 只是互相踩。
    """
    if override is not None:
        return int(override)
    if threading.current_thread() is threading.main_thread():
        return _DEFAULT_MAX_WORKERS
    return _NESTED_MAX_WORKERS


def set_inner_concurrency_limit(limit):
    """调整内层并发闸门（默认关闭；<=0 表示不设上限）。"""
    global _INNER_SEMAPHORE, _MAX_CONCURRENT_INNER_TASKS
    with _INNER_SEMAPHORE_LOCK:
        _MAX_CONCURRENT_INNER_TASKS = int(limit)
        _INNER_SEMAPHORE = (threading.BoundedSemaphore(int(limit))
                            if int(limit) > 0 else None)


@contextlib.contextmanager
def _inner_slot():
    """占用一个内层并发槽位（异常安全释放；闸门关闭时是空操作）。"""
    semaphore = _INNER_SEMAPHORE
    if semaphore is None:
        yield
        return
    semaphore.acquire()
    try:
        yield
    finally:
        semaphore.release()

# 整批上限（秒，病态兜底）：**不是**达标手段，只是防「一批工具集体卡死」的闸门。
# 第一道防线是每个工具自己的 subprocess timeout（5s/10s，见 TOOL_TABLE）——
# 单个卡死工具最多把整批拖到它自己的 timeout，用不着这个闸门。
# 取值宽松（= 3 倍单工具超时）的理由：本机负载会剧烈抖动（同一条命令实测
# 1.5s ~ 6s+），预算卡太紧会把「机器一时慢」误判成「工具没探到」，制造假阴性；
# 宁可慢也要如实报。<=0 表示不设上限。
_DEFAULT_TOTAL_BUDGET = 15.0

# 版本串只保留首行 + 200 字符（与改前逐字一致）。本轮目标是并发化，
# 版本串的截断形态保持不动 —— 顺手改它会让「并发等价性」的对比失去基准。


# ---------------------------------------------------------------------------
# 查找：PATH 索引（可选加速） + 原封不动的 which/glob 语义
# ---------------------------------------------------------------------------

def _path_dirs():
    """当前 PATH 目录序列（与 shutil.which 的口径一致）。"""
    raw = os.environ.get("PATH")
    if raw is None:
        raw = os.defpath
    if not raw:
        return []          # PATH='' 时 which 也认为找不到任何东西
    return raw.split(os.pathsep)


def _build_path_index():
    """把 PATH 每个目录 listdir 一次，得到 [(目录, 小写文件名升序元组), ...]（保序）。

    成本实测 52ms（89 个目录 / 1.7 万个文件），换掉 42 次「全 PATH × PATHEXT」的
    stat 风暴（≈4.6s）。索引**只用来缩小 which 要扫的目录范围**，判据仍由
    `shutil.which` 自己给（见 `_lookup_in_path_index`）。

    不做跨 probe 的进程级缓存：工具可能在进程存活期间被装上（PATH 未变），
    缓存会让新装工具探不到 —— 每次 probe 重建 52ms，换掉这个风险值得。
    """
    index = []
    for directory in _path_dirs():
        scan = directory if directory else os.curdir
        try:
            names = tuple(sorted(entry.lower() for entry in os.listdir(scan)))
        except OSError:
            names = ()
        index.append((directory, names))
    return index


def _dirs_possibly_containing(cmd, path_index):
    """用「小写文件名前缀」筛出可能含 cmd 的 PATH 目录（**保序**）。

    为什么是前缀：which 在 win32 上试的候选名一定是 `cmd + PATHEXT扩展名`
    （以及扩展名已在 PATHEXT 里时的裸 cmd），所以任何能命中的文件名都以 cmd
    开头。按前缀筛是**可靠的超集**：只会多带几个目录（多扫几下，无害），
    绝不漏掉 which 可能命中的目录 —— 候选名的具体生成规则仍交给 which，
    本模块不重写它（重写才是真正的分歧来源）。
    """
    prefix = cmd.lower()
    out = []
    for directory, names in path_index:
        if not names:
            continue
        position = bisect.bisect_left(names, prefix)
        if position < len(names) and names[position].startswith(prefix):
            out.append(directory)
    return out


def _lookup_in_path_index(cmd, path_index, mode=os.F_OK | os.X_OK):
    """在 PATH 索引筛出的目录里做 which：判据与全 PATH which 等价、目录少得多。"""
    if not cmd:
        return None
    if os.path.dirname(cmd):
        # 含目录成分的 cmd：which 直接查该路径、根本不看 PATH（索引不参与）
        return shutil.which(cmd, mode)
    narrowed = _dirs_possibly_containing(cmd, path_index)
    if not narrowed:
        return None
    return shutil.which(cmd, mode, path=os.pathsep.join(narrowed))


def _find_tool(name, aliases, well_known_paths, path_index=None):
    """查找工具可执行文件，返回路径或 None。

    path_index=None（**platform_tools.py 的三参调用**）→ 与改前逐字等价：
    走 shutil.which + 已知路径 glob。
    path_index=...（本模块自己的调用）→ 先用索引把 which 的搜索范围缩到可能命中的
    那几个目录（判据仍是 which 本体），未命中再走已知路径 glob；结果与三参版一致。
    """
    aliases = list(aliases or [])

    # 1) PATH 搜索
    for cmd in [name] + aliases:
        if path_index is None:
            path = shutil.which(cmd)
        else:
            path = _lookup_in_path_index(cmd, path_index)
        if path:
            return path

    # 2) 已知路径搜索（两种模式共用，行为不变）
    sys_platform = sys.platform
    patterns = (well_known_paths or {}).get(sys_platform, [])
    for pattern in patterns:
        matches = globmod.glob(pattern, recursive=True)
        if matches:
            return matches[0]

    return None


# ---------------------------------------------------------------------------
# 取版本：失败必须留痕（不静默），取值必须取到**版本号**而不是用法文本
# ---------------------------------------------------------------------------

# 版本号形态：1.2 / 1.2.3 / 1.2.3.4（不含日期的 "1990-2008" 这种连字符形态）
_VERSION_PATTERN = re.compile(r"\d+\.\d+(?:\.\d+)*")


def _decode_output(raw):
    """子进程输出 bytes → (text, 解码档位)。档位：utf-8 / locale / replace。

    为什么要显式回退链：工具的版本输出编码并不固定 —— 实测 cl.exe 会在 GBK 与
    UTF-8 之间抖动。改前用 subprocess 的 text=True 走 locale 解码，遇到 UTF-8
    输出就得到一整串 mojibake（'鐢ㄦ硶...' 这种），而且**没有任何信号**，报告里
    看起来就像「版本号本来就是这串乱码」。

    现在按 utf-8 严格 → locale（cp936/GBK 等）→ utf-8 errors='replace' 逐级降级，
    并把降级档位记进 extra["version_decode"]（**只在降级时记**，正常路径不多塞字段）。
    """
    if raw is None:
        return "", "utf-8"
    if isinstance(raw, str):       # 有些桩/包装器会直接把文本递进来
        return raw, "utf-8"
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass
    try:
        return raw.decode(locale.getpreferredencoding(False) or "utf-8"), "locale"
    except (UnicodeDecodeError, LookupError):
        pass
    return raw.decode("utf-8", "replace"), "replace"


def _first_line_with_version(lines):
    """返回第一条含版本号形态的行（已 strip），没有则 None。"""
    for line in lines:
        text = line.strip()
        if text and _VERSION_PATTERN.search(text):
            return text
    return None


def _get_version_detail(path, version_args, timeout=5):
    """取版本，并把失败原因一并带回来（`_get_version` 的带诊断版本）。

    返回 (version, error, extra)：
      * 成功：("Python 3.13.14", None, {})
      * 失败：("", "version probe timeout after 5s (per-tool timeout)", {...})

    为什么需要它：改前这里是 `except Exception: pass` —— 超时、进程起不来、
    编码炸掉、并发下的资源竞争，一律把「版本号」悄悄变成空串，报告里看不出
    发生过失败（实测 8 次并行探测里出现过 1 次 cl 版本为空）。

    取值顺序（改前是 `(stdout or stderr)` 直接拿首行，会把**用法文本**当版本）：
      1. stdout 首行含版本号形态 → 用它（与改前逐字一致）；
      2. stdout 后面某行含版本号形态 → 用那一行（首行常常只是横幅/版权）；
      3. stderr 里有版本号形态 → 用那一行（cl 这类：stdout 是用法，真版本在 stderr）；
      4. 都没有 → **不再把 usage 文本塞进 version**：version="" 且记
         version_error_kind="no_version_pattern"（附两边首行样本便于诊断）。

    `extra` 里键名统一带 `version_` 前缀；`version_decode` 只在解码降级时出现。

    子进程 cwd 一律指到探测临时目录（`_probe_tmpdir()`）：有些运行时/工具在崩溃时
    会把转储文件写到**当前工作目录**（JVM 的 hs_err_pid*.log / replay_pid*.log），
    不隔离就会把垃圾留在用户的项目目录里。命中崩溃特征串时记
    version_error_kind="crashed"；非零退出码也会在 extra 里留 version_returncode。
    """
    try:
        cmd = [path] + list(version_args or ())
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout,
                              cwd=_probe_tmpdir())
    except subprocess.TimeoutExpired:
        return "", "version probe timeout after %ss (per-tool timeout)" % (timeout,), {
            "version_error_kind": "timeout",
            "version_timeout_s": timeout,
        }
    except (subprocess.SubprocessError, OSError) as exc:
        return "", "version probe failed to run (%s): %s" % (
            type(exc).__name__, exc), {
            "version_error_kind": "spawn_error",
            "version_exception": type(exc).__name__,
        }
    except Exception as exc:       # 兜底但**不静默**：未知异常同样留痕
        return "", "version probe failed (%s): %s" % (
            type(exc).__name__, exc), {
            "version_error_kind": "unexpected",
            "version_exception": type(exc).__name__,
        }

    stdout_text, stdout_decode = _decode_output(proc.stdout)
    stderr_text, stderr_decode = _decode_output(proc.stderr)
    extra = {}
    decode = stdout_decode if stdout_decode != "utf-8" else stderr_decode
    if decode != "utf-8":
        extra["version_decode"] = decode

    stdout_lines = [line for line in stdout_text.splitlines() if line.strip()]
    stderr_lines = [line for line in stderr_text.splitlines() if line.strip()]

    # 崩溃优先：子进程崩了，输出里的东西都不能当「成功版本号」看待
    crash = _crash_marker(stdout_text, stderr_text)
    if crash:
        extra["version_error_kind"] = "crashed"
        extra["version_crash_marker"] = crash
        extra["version_returncode"] = proc.returncode
        hit = (_first_line_with_version(stdout_lines)
               or _first_line_with_version(stderr_lines))
        return (hit[:200] if hit else ""), (
            "version probe crashed (%s, exit=%s)" % (crash, proc.returncode)), extra

    if not stdout_lines and not stderr_lines:
        extra["version_error_kind"] = "empty_output"
        extra["version_returncode"] = proc.returncode
        return "", "version probe produced no output (exit=%s)" % (
            proc.returncode,), extra

    if proc.returncode != 0:
        # 非零退出码即使拿到版本也标出来（"能报版本但退出码不对"值得看见）
        extra["version_returncode"] = proc.returncode

    # 1) stdout 首行就带版本号 → 与改前逐字一致
    if stdout_lines and _VERSION_PATTERN.search(stdout_lines[0]):
        return stdout_lines[0].strip()[:200], None, extra

    # 2) stdout 靠后的行带版本号；3) stderr 带版本号
    hit = _first_line_with_version(stdout_lines)
    if hit is None:
        hit = _first_line_with_version(stderr_lines)
    if hit is not None:
        return hit[:200], None, extra

    # 4) 两边都没有版本号形态：不静默塞 usage 文本
    extra["version_stdout_sample"] = (stdout_lines[0].strip()[:120]
                                      if stdout_lines else "")
    extra["version_stderr_sample"] = (stderr_lines[0].strip()[:120]
                                      if stderr_lines else "")
    if proc.returncode != 0:
        # 非零退出 + 无版本号：这是「命令本身失败」，比 no_version_pattern 更准确
        extra["version_error_kind"] = "nonzero_exit"
        return "", "version command failed (exit=%s, no version pattern)" % (
            proc.returncode,), extra

    extra["version_error_kind"] = "no_version_pattern"
    return "", "no version pattern in stdout/stderr (usage text not used as version)", extra


def _get_version(path, version_args, timeout=5):
    """获取工具版本信息（失败返回 ""）。

    **契约冻结**：platform_tools.py 直接 import 本函数，返回值必须仍是 str、
    失败仍须是 ""。要失败原因用 `_get_version_detail`，别在这里改返回类型。
    """
    return _get_version_detail(path, version_args, timeout)[0]


# ---------------------------------------------------------------------------
# 工作单元（在工作线程里跑，异常一律就地收口）
# ---------------------------------------------------------------------------

def _entry_label(entry):
    """表项 → 便于人读的名字（表项本身坏掉时也不能让整批炸）。"""
    try:
        label = entry[0]
    except (TypeError, IndexError, KeyError):
        label = None
    if isinstance(label, str) and label:
        return label
    return "<invalid TOOL_TABLE entry>"


def _lookup_one(entry, path_index=None):
    """阶段 1 工作单元：解表项 + 查找可执行文件。"""
    try:
        name, aliases, version_cmd, well_known_paths, timeout = entry
    except (TypeError, ValueError) as exc:
        return {
            "name": _entry_label(entry),
            "state": "invalid",
            "error": "invalid TOOL_TABLE entry (%s): %s" % (type(exc).__name__, exc),
        }

    try:
        path = _find_tool(name, aliases, well_known_paths, path_index)
    except Exception as exc:        # 串行版这里会抛穿整个探测器
        return {
            "name": name,
            "state": "error",
            "error": "lookup failed (%s): %s" % (type(exc).__name__, exc),
        }

    return {
        "name": name,
        "state": "ok",
        "path": path,
        "version_cmd": version_cmd,
        "timeout": timeout,
    }


def _version_one(path, version_args, timeout):
    """阶段 2 工作单元：取版本（占一个跨探测器共享的内层并发槽位）。"""
    with _inner_slot():
        try:
            version, error, extra = _get_version_detail(path, version_args, timeout)
        except Exception as exc:    # _get_version_detail 自己不会抛，纯兜底
            return {
                "version": "",
                "error": "version probe wrapper crashed (%s): %s" % (
                    type(exc).__name__, exc),
                "extra": {},
            }
    return {"version": version, "error": error, "extra": extra}


def _wait_for(futures_map, deadline):
    """在 deadline 之前尽量收结果；返回 (results, failures, expired)。

    results: {key: 返回值}；failures: {key: 异常}；expired: [key, ...]
    超预算的**排队**任务会被 cancel（不再起新进程）；已 in-flight 的留给它
    自己的 subprocess 超时收尾 —— 这里**不 wait** 它们，否则「总预算」就失效
    （实测卡死工具会把整批拖回串行耗时）。
    """
    if not futures_map:
        return {}, {}, []

    if deadline is None:
        timeout = None
    else:
        timeout = deadline - time.monotonic()
        if timeout < 0:
            timeout = 0.0

    done, not_done = concurrent.futures.wait(list(futures_map), timeout=timeout)

    results = {}
    failures = {}
    for future in done:
        key = futures_map[future]
        try:
            results[key] = future.result()
        except Exception as exc:    # future 内部已收口，这里是双保险
            failures[key] = exc

    expired = []
    for future in not_done:
        expired.append(futures_map[future])
        future.cancel()
    return results, failures, expired


class SystemToolsProber(Prober):
    """系统工具探测器（表内工具并发探测，结果按原下标保序）。

    新增可选旋钮（都有默认值，probe() 侧 `SystemToolsProber()` 调用不变）：
      * max_workers: 阶段内并发度。**自适应**：主线程（直接跑单个探测器）16，
        被 probe() 外层线程池调用时 8 —— 实测外层 8~9 个探测器并发时内层开满
        反而互相踩（嵌套墙钟 16→2.87s vs 8→2.04s）。显式传值可覆盖。
      * total_budget: 整批墙钟上限秒数，默认 15.0（病态兜底，不是达标手段；
        <=0 表示不设上限）。
    `last_stats`（只读诊断，不进报告）记录本次并发/预算/索引的落地情况。
    """

    def __init__(self, timeout=5, max_workers=None, total_budget=None):
        Prober.__init__(self, timeout=timeout)
        # 主线程 16 / 被外层池调用时 8（见 _resolve_workers 的实测数据）
        self.max_workers = _resolve_workers(max_workers)
        self.total_budget = (_DEFAULT_TOTAL_BUDGET if total_budget is None
                             else float(total_budget))
        self.last_stats = {}

    def probe(self):
        started = time.monotonic()
        budget = self.total_budget
        deadline = None if budget <= 0 else started + budget

        entries = list(TOOL_TABLE)
        total = len(entries)
        stats = {
            "entries": total,
            "workers": 0,
            "budget_s": budget,
            "path_index_ms": 0.0,
            "path_index_dirs": 0,
            "lookup_ok": 0,
            "lookup_missing": 0,
            "lookup_failed": 0,
            "lookup_expired": 0,
            "version_ok": 0,
            "version_failed": 0,
            "version_expired": 0,
        }
        if total == 0:
            self.last_stats = stats
            return []

        # 索引在主线程建好再并发使用（只读，无需加锁）
        index_started = time.monotonic()
        path_index = _build_path_index()
        stats["path_index_ms"] = round((time.monotonic() - index_started) * 1000.0, 1)
        stats["path_index_dirs"] = len(path_index)

        items = [None] * total
        workers = max(1, min(self.max_workers, total))
        stats["workers"] = workers
        budget_note = ("%.1fs total probe budget exhausted" % budget
                       if budget > 0 else "total probe budget exhausted")

        executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix="probe-systools")
        try:
            # ── 阶段 1：并发查找（索引命中判定，不存在的工具也很快）──
            lookups = {}
            for index, entry in enumerate(entries):
                lookups[executor.submit(_lookup_one, entry, path_index)] = index
            found, failed_lookup, expired_lookup = _wait_for(lookups, deadline)
            expired_lookup = set(expired_lookup)

            # 找到的进阶段 2；其余先按「未探测到 + 原因」落定（不静默）
            resolved = {}
            version_jobs = {}
            for index in range(total):
                if index in found:
                    info = found[index]
                elif index in failed_lookup:
                    exc = failed_lookup[index]
                    items[index] = ProbeItem(
                        name=_entry_label(entries[index]),
                        category="system_tools",
                        available=False,
                        error="lookup crashed (%s): %s" % (type(exc).__name__, exc),
                    )
                    stats["lookup_failed"] += 1
                    continue
                else:
                    # 预算内没轮到 / 没跑完
                    items[index] = ProbeItem(
                        name=_entry_label(entries[index]),
                        category="system_tools",
                        available=False,
                        error="not probed: " + budget_note,
                    )
                    stats["lookup_expired"] += 1
                    continue

                state = info.get("state")
                if state == "invalid" or state == "error":
                    items[index] = ProbeItem(
                        name=info.get("name") or _entry_label(entries[index]),
                        category="system_tools",
                        available=False,
                        error=info.get("error") or "lookup failed",
                    )
                    stats["lookup_failed"] += 1
                    continue

                path = info.get("path")
                if not path:
                    # 与串行版逐字一致：找不到就是 not found
                    items[index] = ProbeItem(
                        name=info.get("name") or _entry_label(entries[index]),
                        category="system_tools",
                        available=False,
                        error="not found",
                    )
                    stats["lookup_missing"] += 1
                    continue

                stats["lookup_ok"] += 1
                resolved[index] = (info.get("name"), path)
                timeout = info.get("timeout")
                if not timeout:
                    timeout = self.timeout
                version_jobs[executor.submit(
                    _version_one, path, info.get("version_cmd"), timeout)] = index

            # ── 阶段 2：并发取版本（只对找到的工具）──
            versions, crashed_version, _expired_version = _wait_for(
                version_jobs, deadline)   # 超预算的那批在下面的 else 分支里标记

            for index in sorted(resolved):
                name, path = resolved[index]
                if index in versions:
                    info = versions[index]
                    error = info.get("error")
                    extra = info.get("extra") or {}
                    if error:
                        # 工具在、版本没取到：available 仍为 True（path 有效），
                        # 但 error 与串行版的「静默空串」不同 —— 留下原因与诊断。
                        stats["version_failed"] += 1
                        items[index] = ProbeItem(
                            name=name,
                            category="system_tools",
                            available=True,
                            path=path,
                            version=info.get("version") or "",
                            error=error,
                            extra=extra,
                        )
                    else:
                        stats["version_ok"] += 1
                        items[index] = ProbeItem(
                            name=name,
                            category="system_tools",
                            available=True,
                            path=path,
                            version=info.get("version") or "",
                            extra=extra,
                        )
                elif index in crashed_version:
                    exc = crashed_version[index]
                    stats["version_failed"] += 1
                    items[index] = ProbeItem(
                        name=name,
                        category="system_tools",
                        available=True,
                        path=path,
                        version="",
                        error="version probe crashed (%s): %s" % (
                            type(exc).__name__, exc),
                    )
                else:
                    stats["version_expired"] += 1
                    items[index] = ProbeItem(
                        name=name,
                        category="system_tools",
                        available=True,
                        path=path,
                        version="",
                        error="version not probed: " + budget_note,
                    )

            # 防御：任何漏网的槽位都落成显式条目，绝不返回 None
            for index, item in enumerate(items):
                if item is None:
                    items[index] = ProbeItem(
                        name=_entry_label(entries[index]),
                        category="system_tools",
                        available=False,
                        error="probe produced no result",
                    )
        finally:
            # 关键：不 wait。in-flight 的工作线程由各自的 subprocess 超时收尾；
            # 这里若 wait=True，一个卡死工具就会把整条 probe 拖回串行耗时。
            executor.shutdown(wait=False)

        stats["elapsed_ms"] = round((time.monotonic() - started) * 1000.0, 1)
        self.last_stats = stats
        return items
