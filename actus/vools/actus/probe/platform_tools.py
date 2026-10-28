"""probe/platform_tools.py — 平台特有能力探测（PROBE_PLAN.md Phase 2）。

基础探测（平台信息 / 权限 / 环境 / 资源 / 运行时 / 编译器 / 系统工具 / Python 包 /
动作分析）回答「通用工具链有没有」；本模块补的是**每个平台独有的能力**：

┌──────────┬──────────────────────────────────────────────────────────────┐
│ Windows  │ vs_build_tools  — vswhere.exe 查询 VS / Build Tools 实例    │
│          │ wsl             — wsl.exe -l -v 解析已装发行版              │
│          │ windows_terminal— wt.exe（App Execution Alias）+ 商店包版本 │
├──────────┼──────────────────────────────────────────────────────────────┤
│ Linux    │ systemd         — systemctl --version + PID1/sd_booted      │
│          │ package_manager — apt/dnf/pacman/zypper/apk 家族判定 + 版本 │
├──────────┼──────────────────────────────────────────────────────────────┤
│ macOS    │ xcode_clt       — xcode-select -p + clang --version 实证    │
│          │ homebrew        — brew 可执行（PATH + 双前缀）+ 版本 + prefix│
└──────────┴──────────────────────────────────────────────────────────────┘

设计约束（对应 PROBE_PLAN.md §4.1/§4.2 与任务要求）：

1. **判据真实**：只用真实可执行的判据（vswhere 的固定安装路径、`wsl.exe -l -v`、
   `xcode-select -p`、`systemctl --version`、包管理器可执行文件存在性）。探测不到
   就如实报 unavailable + error，**不伪造**。
2. **跨平台安全**：非当前平台的探测组直接跳过（不执行外部命令、不抛异常、不进
   报告条目）；即使被直接调用，单个探测函数也只会在该平台找不到东西，
   收敛成 unavailable 而不是异常。
3. **短超时 + 整组硬截止**：所有外部命令都有超时（默认 5s，上限也是 5s，见
   `_clamp_timeout`）；整组再套两层硬截止——整组 `_GROUP_BUDGET` = 1.8s、其中 WSL
   单独 `_WSL_TOTAL_BUDGET` = 1.7s（分条上限见 `_WSL_*_TIMEOUT`）。「每条各等 5s」
   会在服务无响应时叠成 10s 尖峰（实测证据见
   `build/probe_evidence/wsl_timing_before.out.txt`）。超时必须有信号
   （`extra["timed_out"]` / `degraded` / `error`），不许静默当成「未安装」。
4. **复用现有能力**：工具查找/版本探测复用 `system_tools._find_tool` /
   `_get_version`（PATH + well-known 路径 + version 的单一真源），不重写。
5. **零新增依赖**：只用 stdlib（subprocess / glob / json / os / re / shutil）。

结果落进 ProbeReport 的独立 section：`ProbeItem.category == "platform_tools"`
（`ProbeReport.build_summary()` 会把它聚成 `summary["by_category"]["platform_tools"]`，
条目本身在 `report.items` 里按 category 过滤即得该 section）。

**能力 / 元信息分栏**：section 里的 `platform_scope` 只陈述「本次跑了哪些组、跳过了
哪些组」，是**元信息**（`ProbeItem.extra["kind"] == "meta"`），不是可用工具 —— 它的
`available=True` 只表示范围探测本身成功。问「哪些平台工具可用」的消费方必须用
`is_capability_item()` 过滤，否则会把元信息当成能力（假阳性）；
`get_platform_tools_info()["available"]` 已经过滤，`platform_scope` 移到 `scope` 字段。
"""

__all__ = [
    "PlatformToolsProber",
    "get_platform_tools_info",
    "is_capability_item",
    "probe",
]

import glob as globmod
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time

from .base import Prober, ProbeItem

# 复用「PATH + well-known 路径 + version」机制（system_tools.py 是单一真源）。
# 这两个是模块私有函数，但同包内复用比复制一份逻辑更不容易漂移。
from .system_tools import _find_tool, _get_version  # noqa: E402


# 探测结果所属的 section 名（ProbeItem.category）
CATEGORY = "platform_tools"

# 条目类型，写在 ProbeItem.extra["kind"]（ProbeItem 本身没有 kind 字段，而 base.py
# 不在本模块作用域内，故用 extra 承载）：
#   "capability" —— **真能力**：某个平台工具装了/没装（vs_build_tools / wsl / ...）
#   "meta"       —— **元信息**：本次跑了哪些组、跳过了哪些组，**不是能力**
# 为什么必须区分：`platform_scope` 的 available=True 只表示「范围探测本身成功了」，
# 若消费方拿它当能力，就会得到「可用工具 = [platform_scope, ...]」这种假阳性。
# 判定统一走 is_capability_item()；get_platform_tools_info()["available"] 已过滤。
_KIND_CAPABILITY = "capability"
_KIND_META = "meta"

# 外部命令默认超时 / 上限（秒）：探测不能拖慢整份报告
_CMD_TIMEOUT = 5.0
_MAX_CMD_TIMEOUT = 5.0

# 整组硬截止：**本探测器对外的时间承诺**（不是单条命令的上限）。
# 实测（build/probe_evidence/wsl_timing_before.out.txt）：机器有负载时 wsl -l -v
# 会从 0.1s 飙到 1.9-3.8s（旧实现每条各等 5s → 10s 尖峰），vswhere 也会从 0.15s
# 涨到 0.59s。逐条累加不可控，所以整组共享 1.8s 预算：前面的慢，后面的自动收窄。
# 取 1.8 而不是 2.0：预算是「纯命令时间」，还要留 ~0.1s 的 Python/调度开销，
# 这样**最坏含开销也落在 ~1.9s**（实测 G 全挂场景 2.03s → 收紧后 ~1.85s）。
_GROUP_BUDGET = 1.8
# 预算耗尽时仍要跑（条目必须在，信号必须在），这是留给它的最小额度
_MIN_PROBE_TIMEOUT = 0.05
# vswhere 单条限时：实测常态 0.06-0.28s，给 1.2s（4 倍余量）；超时退默认布局扫描
_VS_TIMEOUT = 1.2
# 超时 kill 之后**有限**回收等待（见 `_run` docstring）：不跟着孙进程无限期等管道 EOF。
# 这也是「超时上限」真正生效的前提 —— 否则实测会把 0.5s 拖成 4.9s。
_REAP_TIMEOUT = 0.1


# ---------------------------------------------------------------------------
# 通用小工具（跨平台安全：任何异常都收敛成 None / 空值，不往外抛）
# ---------------------------------------------------------------------------

def _clamp_timeout(value) -> float:
    """把调用方给的 timeout 收敛到 (0, _MAX_CMD_TIMEOUT] —— 探测必须快。"""
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        return _CMD_TIMEOUT
    if timeout <= 0:
        return _CMD_TIMEOUT
    return min(timeout, _MAX_CMD_TIMEOUT)


def _run(argv: list, timeout: float = _CMD_TIMEOUT):
    """跑外部命令，返回 (returncode, raw_stdout_bytes)，永不抛异常。

    返回 (None, b"") 表示命令没跑起来（不存在 / 无权限 / 超时）。

    **为什么不用 `subprocess.run`（这里是尖峰的第二个根源，实测量化过）**：
    CPython 的 `run()` 在 Windows 上超时后是 ``kill()`` + **再次 communicate()**
    （该调用没有 timeout）——也就是「等 stdout/stderr 管道 EOF」。而 `wsl.exe`
    这类会拉起子进程的命令，孙进程可能继承了那两个管道句柄，于是**上限形同虚设**：

      * 实测 cold 场景：`-l -v` 上限 0.8s，实际耗时 1.174s（多出的 0.37s 是等 EOF）
      * 合成复现（`build/probe_evidence/pipe_eof_repro.py`）：上限 0.5s，
        `subprocess.run` 实测 **4.932s**（等孙进程退出），有界实现 0.681s

    所以这里改成 Popen + kill + **有限**回收等待（`_REAP_TIMEOUT`）：到点就走人。
    宁可留下一个正在退出的子进程，也不让「探测耗时」跟着别人的孙进程走。
    契约不变：超时/起不来一律 (None, b"")，调用方（含 tests 对 `_run` 的打桩）无需改。
    """
    limit = _clamp_timeout(timeout)
    try:
        proc = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (FileNotFoundError, OSError, ValueError):
        return None, b""

    try:
        stdout, _stderr = proc.communicate(timeout=limit)
        return proc.returncode, stdout or b""
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except OSError:
            pass
        try:
            proc.communicate(timeout=_REAP_TIMEOUT)
        except (subprocess.TimeoutExpired, OSError, ValueError):
            pass
        return None, b""


def _decode_output(raw: bytes) -> str:
    """解码外部命令输出。

    Windows 上有些内置命令输出 **UTF-16LE**（`wsl.exe -l -v` 是典型：无 BOM、
    每个 ASCII 字符后跟 \\x00），按 UTF-8 直读会得到一堆嵌入 NUL 的乱码。
    这里按「BOM → NUL 密度 → utf-8 → gbk」的顺序判定，全都失败也不抛。
    """
    if not raw:
        return ""
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16", "replace")
    sample = raw[:200]
    if sample.count(b"\x00") >= max(2, len(sample) // 4):
        return raw.decode("utf-16-le", "replace")
    for encoding in ("utf-8", "gbk"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def _first_line(text: str) -> str:
    """取第一行非空文本（外部命令输出噪声很多）。"""
    for line in (text or "").splitlines():
        line = line.strip()
        if line:
            return line[:200]
    return ""


def _read_text(path: str) -> str:
    """读小文本文件（跨平台安全：不存在/无权限返回空串）。"""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read(512)
    except OSError:
        return ""


def _version_number(text: str):
    """从一行版本输出里抠出第一个数字版本（如 systemd 输出 → "252"）。"""
    match = re.search(r"\d+(?:\.\d+)+", text or "")
    return match.group(0) if match else None


def _which(*names: str):
    """按顺序 shutil.which，返回第一个命中路径。"""
    for name in names:
        if not name:
            continue
        found = shutil.which(name)
        if found:
            return found
    return None


# ---------------------------------------------------------------------------
# Windows × 3
# ---------------------------------------------------------------------------

def _vswhere_installs(vswhere: str, timeout: float = _CMD_TIMEOUT):
    """用 vswhere.exe 查询所有 Visual Studio 系实例，返回 list 或 None。

    判据：`vswhere -products * -format json -utf8`（VS 安装器官方查询入口）。
    硬编码 C:\\Program Files 的 glob **不够** —— 本机实测 Build Tools 分别装在
    `E:\\Program Files (x86)\\...\\BuildTools` 和 `D:\\VisualStudioBuildTools`，
    只有 vswhere 知道自定义安装路径。
    """
    returncode, raw = _run(
        [vswhere, "-products", "*", "-format", "json", "-utf8"], timeout
    )
    if returncode != 0 or not raw:
        return None
    try:
        data = json.loads(_decode_output(raw))
    except ValueError:
        return None
    if not isinstance(data, list):
        return None

    installs = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        installs.append({
            "display_name": entry.get("displayName") or "",
            "version": entry.get("installationVersion") or "",
            "path": entry.get("installationPath") or "",
            "product_id": entry.get("productId") or "",
            "complete": bool(entry.get("isComplete")),
        })
    return installs


def _glob_vs_installs():
    """vswhere 缺席时的兜底：扫 VS 默认安装布局（会漏自定义路径，故如实标注 method）。"""
    roots = [
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
    ]
    found = []
    for root in roots:
        if not root:
            continue
        for pattern in (
            os.path.join(root, "Microsoft Visual Studio", "20*", "*"),
            os.path.join(root, "Microsoft Visual Studio", "*", "*"),
        ):
            try:
                matches = globmod.glob(pattern)
            except OSError:
                continue
            for path in matches:
                if not os.path.isdir(path):
                    continue
                if os.path.basename(path) == "Installer":
                    continue
                # 真实 VS 实例的判据：有 VC 或 Common7 子目录
                if not (
                    os.path.isdir(os.path.join(path, "VC"))
                    or os.path.isdir(os.path.join(path, "Common7"))
                ):
                    continue
                if path in found:
                    continue
                found.append(path)
    return found


def _msvc_toolsets(install_path: str) -> list:
    """列出实例下的 MSVC 工具集，并标记 cl.exe 是否真的可执行（能编译的判据）。"""
    toolsets = []
    if not install_path:
        return toolsets
    pattern = os.path.join(install_path, "VC", "Tools", "MSVC", "*")
    try:
        matches = globmod.glob(pattern)
    except OSError:
        return toolsets
    for toolset in matches:
        if not os.path.isdir(toolset):
            continue
        cl_x64 = os.path.join(toolset, "bin", "Hostx64", "x64", "cl.exe")
        toolsets.append({
            "version": os.path.basename(toolset),
            "cl_x64": os.path.isfile(cl_x64),
        })
    toolsets.sort(key=lambda item: item["version"], reverse=True)
    return toolsets


def _probe_windows_vs_build_tools(timeout: float = _CMD_TIMEOUT) -> dict:
    """Windows：Visual Studio / VS Build Tools（含 MSVC 工具集）。

    vswhere 查询单独限时 `_VS_TIMEOUT`（实测常态 0.06-0.28s；机器有负载时会和
    WSL 探测一起变慢，实测到过 0.59s）。超时**不是失败**：立即退到默认布局扫描
    （`_glob_vs_installs`，毫秒级），并用 `extra["timed_out"]` / `degraded` 标出来，
    免得「查询超时」被读成「没装 VS」。
    """
    budget = min(_VS_TIMEOUT, _clamp_timeout(timeout))
    program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")

    # vswhere 的标准安装位置（VS Installer 固定落在这里），PATH 兜底
    vswhere = _find_tool("vswhere", [], {"win32": [
        os.path.join(program_files_x86, "Microsoft Visual Studio", "Installer", "vswhere.exe"),
        os.path.join(program_files, "Microsoft Visual Studio", "Installer", "vswhere.exe"),
    ]})

    method = None
    installs = None
    vswhere_elapsed = 0.0
    vswhere_timed_out = False
    if vswhere:
        started = time.monotonic()
        installs = _vswhere_installs(vswhere, budget)
        vswhere_elapsed = time.monotonic() - started
        # 超时旁证：没拿到结果 + 耗时逼近上限（与 `_run_budgeted` 同一判据）
        vswhere_timed_out = (installs is None
                             and vswhere_elapsed >= max(0.05, budget * 0.9))
        if installs is not None:
            method = "vswhere"

    if installs is None:
        # vswhere 不存在 / 查询失败 / 查询超时 → 只认默认布局（自定义路径必然漏，
        # method 如实标注）；超时这一档另记 timed_out，不冒充「未安装」
        installs = [
            {"display_name": "", "version": "", "path": path,
             "product_id": "", "complete": True}
            for path in _glob_vs_installs()
        ]
        method = "glob_default_layout" if installs else None

    detail = []
    for install in installs:
        path = install.get("path") or ""
        toolsets = _msvc_toolsets(path)
        detail.append({
            "display_name": install.get("display_name") or "",
            "version": install.get("version") or "",
            "path": path,
            "product_id": install.get("product_id") or "",
            "complete": install.get("complete", True),
            "msvc_toolsets": toolsets,
            "vcvars64": os.path.isfile(
                os.path.join(path, "VC", "Auxiliary", "Build", "vcvars64.bat")
            ),
        })

    available = bool(detail)
    has_cpp = any(entry["msvc_toolsets"] or entry["vcvars64"] for entry in detail)
    first = detail[0] if detail else {}
    if available:
        error = None
    elif vswhere_timed_out:
        error = ("vswhere.exe 在 %.2fs 内未响应（超时），且默认安装布局下没有 "
                 "Visual Studio 实例" % budget)
    else:
        error = "vswhere.exe 未找到，且默认安装布局下没有 Visual Studio 实例"
    return {
        "available": available,
        "path": first.get("path") or None,
        "version": first.get("version") or None,
        "error": error,
        "extra": {
            "method": method,
            "vswhere": vswhere,
            "installs": detail,
            "has_cpp_toolset": has_cpp,
            "note": None if has_cpp else (
                "检测到 VS 实例但没找到 MSVC 工具集（未安装「使用 C++ 的桌面开发」工作负载）"
                if available else "无"
            ),
            # —— 限时 / 降级信号（与 WSL 探测同一套口径）——
            "vswhere_timeout_s": budget,
            "vswhere_elapsed_s": round(vswhere_elapsed, 3),
            "timed_out": ["vswhere"] if vswhere_timed_out else [],
            "degraded": bool(vswhere_timed_out),
        },
    }


def _parse_wsl_distros(text: str) -> list:
    """解析 `wsl.exe -l -v` 的表格，语言无关。

    输出形如（UTF-16LE）::

          NAME            STATE           VERSION
        * Ubuntu-22.04    Stopped         2

    判据用「最后一列是整数」而不是匹配表头文字 —— 表头在中文系统上是
    「名称/状态/版本」，按英文单词匹配会漏。表头与提示语（"...没有已安装的分发版"）
    最后一列都不是纯数字，自然被过滤。
    """
    distros = []
    for line in (text or "").splitlines():
        stripped = line.strip().lstrip("\ufeff")
        if not stripped:
            continue
        tokens = stripped.split()
        if len(tokens) < 3 or not tokens[-1].isdigit():
            continue
        is_default = tokens[0] == "*"
        name = tokens[1] if is_default else tokens[0]
        if not name or name in ("*",):
            continue
        distros.append({
            "name": name,
            "state": tokens[-2],
            "version": int(tokens[-1]),
            "default": is_default,
        })
    # 去重（防御重复行）
    deduped, seen = [], set()
    for distro in distros:
        key = distro["name"]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(distro)
    return deduped


# WSL 探测的**整组硬截止 + 分条上限**（不是「每条都等 5s」）。
#
# 为什么要有这层（实测归因，证据在 build/probe_evidence/wsl_timing_before.out.txt）：
#   wsl --version  0.06-0.28s（稳）
#   wsl -l -v      常态 0.06-0.20s；但 WSL 服务刚被唤醒 / 机器有负载时会飙到
#                  1.9-3.8s，极端时 >5s —— **这一条就是尖峰来源**
#   wsl -l -q      0.065-0.10s（稳，且不查 distro 状态）
# 旧实现给每条命令都套 5s 上限且串行：`-l -v` 与兜底 `-l -q` 都吃满 = 10s 尖峰
# （cmd-pool 实测 10012ms 正是 5+5+0.012 的形态）。这里改成：
#   * 整组共享 `_WSL_TOTAL_BUDGET` 硬截止 → 最坏也能在 1.7s 内给出结论（带超时信号）
#   * `--version` 先跑（最便宜最稳）：先把它拿到手，后面无论哪条超时都不影响该字段
#   * `-l -v` 给 0.8s（常态 0.1s，8 倍余量），超时才用 0.4s 的 `-l -q` 兜名字
#   * 三个上限之和（0.5+0.8+0.4=1.7）刚好等于预算，全挂时不会互相挤掉
_WSL_TOTAL_BUDGET = 1.7
_WSL_VERSION_TIMEOUT = 0.5
_WSL_LIST_TIMEOUT = 0.8
_WSL_QUIET_TIMEOUT = 0.4


def _run_budgeted(argv: list, cap: float, deadline: float):
    """在「整组硬截止」下跑一条外部命令（WSL 探测专用）。

    返回 (returncode, raw, elapsed, timed_out, skipped)：
      * ``skipped=True``  —— 组预算已耗尽，**这条根本没跑**（调用方不得当成「失败」）
      * ``timed_out=True`` —— 跑了但吃满本条上限

    为什么要靠耗时旁证判超时：``_run`` 的契约是 (None, b"") 同时表示「超时」与
    「起不来」，而 tests 打的就是模块级 ``_run``（不 patch subprocess.run，因为那会
    连 stdlib platform 自己的子进程一起打坏）。所以这里不能自建 runner，
    只能在 ``_run`` 的返回值上加「耗时是否逼近上限」这层旁证 —— 快速失败
    （spawn 失败，毫秒级返回 None）不会被误判成超时。
    """
    remaining = deadline - time.monotonic()
    if remaining <= 0.02:
        return None, b"", 0.0, False, True
    limit = min(float(cap), remaining)
    started = time.monotonic()
    code, raw = _run(argv, limit)
    elapsed = time.monotonic() - started
    timed_out = code is None and elapsed >= max(0.05, limit * 0.9)
    return code, raw, elapsed, timed_out, False


def _probe_windows_wsl(timeout: float = _CMD_TIMEOUT) -> dict:
    """Windows：WSL（可执行文件 + 已装发行版 + WSL 版本）。

    时间预算是**整组硬截止**（见上方 `_WSL_TOTAL_BUDGET` 注释与实测数据）：
    最坏 2.0s 一定出结论，热路径仍是两三百毫秒。超时**必有信号**：
    ``extra["timed_out"]`` 列出吃满上限的命令、``extra["degraded"]`` 标降级、
    全都失败时 ``error`` 明说「存在但预算内未响应」，绝不静默当成「未安装」。
    """
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    exe = _find_tool("wsl", [], {"win32": [
        os.path.join(system_root, "System32", "wsl.exe"),
    ]})

    if not exe:
        return {
            "available": False,
            "path": None,
            "version": None,
            "error": "wsl.exe 未找到（WSL 未安装或未启用）",
            "extra": {"exe": None, "budget_s": _WSL_TOTAL_BUDGET},
        }

    # 取整：预算值会进报告/JSON，1.6493885999952909 这种浮点尾巴对读的人没意义
    budget = round(min(_WSL_TOTAL_BUDGET, _clamp_timeout(timeout)), 3)
    deadline = time.monotonic() + budget
    timings = {}
    timed_out_calls = []
    skipped_calls = []

    # 1) WSL 自身版本（WSL 2.x 才支持 --version；旧版返回错误 → version 留空，不算失败）
    version_code, version_raw, version_elapsed, version_timeout, version_skipped = (
        _run_budgeted([exe, "--version"], _WSL_VERSION_TIMEOUT, deadline))
    timings["version"] = round(version_elapsed, 3)
    if version_timeout:
        timed_out_calls.append("--version")
    if version_skipped:
        skipped_calls.append("--version")
    version_text = _decode_output(version_raw) if version_code == 0 else ""
    wsl_version = _version_number(version_text)

    # 2) 发行版列表（UTF-16LE 输出，必须有编码处理；也是最易飙的一条）
    list_code, list_raw, list_elapsed, list_timeout, list_skipped = _run_budgeted(
        [exe, "-l", "-v"], _WSL_LIST_TIMEOUT, deadline)
    timings["list"] = round(list_elapsed, 3)
    if list_timeout:
        timed_out_calls.append("-l -v")
    if list_skipped:
        skipped_calls.append("-l -v")
    distros = _parse_wsl_distros(_decode_output(list_raw))
    distro_source = "list" if distros else None

    list_error = None
    if list_code != 0 or not distros:
        list_error = (
            "wsl.exe -l -v 超时（上限 %.2fs，%s）" % (_WSL_LIST_TIMEOUT, "整组预算内未返回")
            if list_timeout else
            "wsl.exe -l -v 失败（returncode=%s）" % (list_code,)
        )
        # 兜底：-l -q 只列名字（老版本/异常状态下 -l -v 可能失败或超时）
        quiet_code, quiet_raw, quiet_elapsed, quiet_timeout, quiet_skipped = (
            _run_budgeted([exe, "-l", "-q"], _WSL_QUIET_TIMEOUT, deadline))
        timings["quiet"] = round(quiet_elapsed, 3)
        if quiet_timeout:
            timed_out_calls.append("-l -q")
        if quiet_skipped:
            skipped_calls.append("-l -q")
        if quiet_code == 0:
            names = [
                line.strip().lstrip("\ufeff").lstrip("*").strip()
                for line in _decode_output(quiet_raw).splitlines()
                if line.strip()
            ]
            names = [name for name in names if name]
            if names and not distros:
                distros = [{"name": name, "state": None, "version": None,
                            "default": False} for name in names]
                distro_source = "quiet"
    else:
        quiet_code = None

    default_distro = next(
        (distro["name"] for distro in distros if distro["default"]), None
    )

    # 判定「可用」：wsl.exe 存在 **且至少有一条查询应答**。
    # 旧实现写的是 `available = list_code == 0` —— 那会把「-l -v 超时但 -l -q
    # 成功拿到发行版名」这种部分可用错报成整个 WSL 不可用（信息白丢）。
    responded = any(
        code == 0 for code in (version_code, list_code, quiet_code)
    )
    available = bool(responded)
    if available:
        error = None
    elif timed_out_calls:
        error = "wsl.exe 存在但 %.1fs 预算内未响应（超时：%s）" % (
            budget, ", ".join(timed_out_calls))
    else:
        error = list_error or "wsl.exe 存在但不可用"

    degraded = bool(timed_out_calls or skipped_calls or (
        distro_source == "quiet" and list_code != 0))
    return {
        "available": available,
        "path": exe,
        "version": wsl_version,
        "error": error,
        "extra": {
            "exe": exe,
            "wsl_version": wsl_version,
            "distros": distros,
            "distro_count": len(distros),
            "default_distro": default_distro,
            "has_distro": bool(distros),
            "wsl2_capable": any(distro.get("version") == 2 for distro in distros),
            # —— 预算 / 降级信号（消费方据此区分「没装」「没响应」「部分可用」）——
            "budget_s": budget,
            "timings": timings,
            "distro_source": distro_source,
            "timed_out": list(timed_out_calls),
            "skipped": list(skipped_calls),
            "degraded": degraded,
            "note": (
                None if not degraded else (
                    "WSL 探测在 %.1fs 预算内降级：超时=%s 跳过=%s 发行版来源=%s"
                    % (budget, timed_out_calls or "无", skipped_calls or "无",
                       distro_source or "无")
                )
            ),
        },
    }


def _probe_windows_terminal(timeout: float = _CMD_TIMEOUT) -> dict:
    """Windows：Windows Terminal（wt.exe）。

    注意：`wt.exe` 是 **App Execution Alias**（reparse point，不是符号链接），
    执行 `wt.exe --version` 会返回码 0 但 stdout 为空（本机实测），因此
    **不用执行它**；判据是「别名存在」+「商店包目录名里的版本号」，两者都是
    文件系统事实，无副作用。
    """
    alias = _which("wt.exe", "wt")
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    candidates = [alias] if alias else []
    if local_app_data:
        candidates.append(
            os.path.join(local_app_data, "Microsoft", "WindowsApps", "wt.exe")
        )
    exe = next((path for path in candidates if path and os.path.isfile(path)), None)

    # 版本：从 Windows Terminal 商店包目录名解析（Microsoft.WindowsTerminal_<ver>_x64__<hash>）
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    package_dirs = []
    for pattern in (
        os.path.join(program_files, "WindowsApps", "Microsoft.WindowsTerminal_*"),
        os.path.join(local_app_data, "Packages", "Microsoft.WindowsTerminal_*")
        if local_app_data else "",
    ):
        if not pattern:
            continue
        try:
            package_dirs.extend(globmod.glob(pattern))
        except OSError:
            continue

    versions = []
    app_packages = []
    for package_dir in package_dirs:
        base = os.path.basename(package_dir)
        match = re.search(r"Microsoft\.WindowsTerminal_(\d+(?:\.\d+)+)", base)
        if not match:
            continue
        # 只认真的含 wt.exe 的应用包（排除 "_neutral_~_" 这类语言存根）
        has_exe = os.path.isfile(os.path.join(package_dir, "wt.exe"))
        app_packages.append({"path": package_dir, "version": match.group(1),
                             "has_wt_exe": has_exe})
        if has_exe:
            versions.append(match.group(1))

    def _sort_key(version):
        return tuple(int(part) for part in version.split(".") if part.isdigit())

    version = None
    if versions:
        try:
            version = max(versions, key=_sort_key)
        except (TypeError, ValueError):
            version = versions[0]

    return {
        "available": exe is not None,
        "path": exe,
        "version": version,
        "error": None if exe else "wt.exe 未找到（未安装 Windows Terminal）",
        "extra": {
            "alias": alias,
            "version_source": "store_package_dir" if version else None,
            "packages": app_packages,
            "note": (
                "wt.exe 是 App Execution Alias，--version 无输出；版本取自商店包目录名"
                if exe else "无"
            ),
        },
    }


# ---------------------------------------------------------------------------
# Linux × 2
# ---------------------------------------------------------------------------

def _probe_linux_systemd(timeout: float = _CMD_TIMEOUT) -> dict:
    """Linux：systemd（systemctl + PID1/sd_booted 判据）。"""
    systemctl = _find_tool("systemctl", [], {"linux": [
        "/usr/bin/systemctl", "/bin/systemctl", "/usr/local/bin/systemctl",
    ]})

    version_line = ""
    if systemctl:
        # 复用 system_tools 的版本探测（首行截断 + 短超时）
        version_line = _get_version(systemctl, ["--version"], _clamp_timeout(timeout))

    # PID1 是谁：/proc/1/comm（容器里通常是别的进程）
    pid1 = _first_line(_read_text("/proc/1/comm"))
    # sd_booted() 的等价判据：systemd 只在用它启动时创建 /run/systemd/system
    sd_booted = os.path.isdir("/run/systemd/system")
    booted_with_systemd = sd_booted or pid1 == "systemd"

    available = bool(systemctl)
    return {
        "available": available,
        "path": systemctl,
        "version": version_line or None,
        "error": None if available else "systemctl 未找到（非 systemd 发行版或极简容器）",
        "extra": {
            "systemctl": systemctl,
            "version_number": _version_number(version_line),
            "pid1": pid1 or None,
            "sd_booted": sd_booted,
            "booted_with_systemd": booted_with_systemd,
            # 可执行存在 ≠ 能管服务：容器/非 systemd 启动时 systemctl 会拒绝操作
            "usable": available and booted_with_systemd,
        },
    }


# 包管理器家族表：(命令名, 版本参数, 家族)
_PACKAGE_MANAGER_TABLE = (
    ("apt-get", ["--version"], "debian"),
    ("dpkg", ["--version"], "debian"),
    ("dnf", ["--version"], "rhel"),
    ("yum", ["--version"], "rhel"),
    ("pacman", ["--version"], "arch"),
    ("zypper", ["--version"], "suse"),
    ("apk", ["--version"], "alpine"),
    ("emerge", ["--version"], "gentoo"),
    ("flatpak", ["--version"], "flatpak"),
    ("snap", ["--version"], "snap"),
)

# 主包管理器优先级（同一家族里取第一个命中的；dpkg/yum 是底层，不作为主入口）
_PRIMARY_ORDER = ("apt-get", "dnf", "pacman", "zypper", "apk", "emerge",
                  "flatpak", "snap", "yum", "dpkg")


def _probe_linux_package_manager(timeout: float = _CMD_TIMEOUT) -> dict:
    """Linux：包管理器（家族判定 + 主入口 + 版本）。"""
    search_dirs = ("/usr/bin", "/bin", "/usr/sbin", "/sbin",
                   "/usr/local/bin", "/snap/bin")
    patterns = [os.path.join(directory, "%s") for directory in search_dirs]

    found = {}
    for name, version_args, family in _PACKAGE_MANAGER_TABLE:
        well_known = [pattern % name for pattern in patterns]
        path = _find_tool(name, [], {"linux": well_known})
        if not path:
            continue
        version_line = _get_version(path, version_args, _clamp_timeout(timeout))
        found[name] = {
            "path": path,
            "version": version_line or None,
            "version_number": _version_number(version_line),
            "family": family,
        }

    primary_name = next((name for name in _PRIMARY_ORDER if name in found), None)
    primary = found.get(primary_name) if primary_name else None
    family = primary["family"] if primary else None

    available = bool(found)
    return {
        "available": available,
        "path": primary["path"] if primary else None,
        "version": primary["version"] if primary else None,
        "error": None if available else "PATH 与常见 bin 目录下未找到任何包管理器",
        "extra": {
            "family": family,
            "primary": primary_name,
            "primary_version_number": primary["version_number"] if primary else None,
            "managers": found,
            "manager_names": sorted(found),
            "container_ready": any(
                name in found for name in ("flatpak", "snap")
            ),
        },
    }


# ---------------------------------------------------------------------------
# macOS × 2
# ---------------------------------------------------------------------------

def _probe_macos_xcode_clt(timeout: float = _CMD_TIMEOUT) -> dict:
    """macOS：Xcode Command Line Tools（xcode-select -p + clang 实证）。"""
    timeout = _clamp_timeout(timeout)
    xcode_select = _find_tool("xcode-select", [], {"darwin": ["/usr/bin/xcode-select"]})
    developer_dir = None
    select_code = None
    select_error = None

    if xcode_select:
        select_code, select_raw = _run([xcode_select, "-p"], timeout)
        if select_code == 0:
            developer_dir = _first_line(_decode_output(select_raw)) or None
        else:
            select_error = "xcode-select -p 失败（returncode=%s）" % select_code

    dev_dir_exists = bool(developer_dir and os.path.isdir(developer_dir))
    is_full_xcode = bool(
        developer_dir
        and os.path.basename(developer_dir.rstrip("/")) == "Developer"
        and "Xcode.app" in developer_dir
    )

    # 真能编译的判据：clang --version（/usr/bin/clang 是 shim，只有装了 CLT 才会真跑起来）
    clang = _find_tool("clang", [], {"darwin": ["/usr/bin/clang"]})
    clang_line = _get_version(clang, ["--version"], timeout) if clang else ""

    xcodebuild_version = None
    if is_full_xcode:
        xcodebuild = _find_tool("xcodebuild", [], {"darwin": ["/usr/bin/xcodebuild"]})
        if xcodebuild:
            # 已装 Xcode 未接受 license 时这里会失败 → 版本留空，不造假
            xcodebuild_version = _get_version(xcodebuild, ["-version"], timeout) or None

    clt_root = "/Library/Developer/CommandLineTools"
    available = bool(dev_dir_exists)
    return {
        "available": available,
        "path": developer_dir or xcode_select,
        "version": clang_line or None,
        "error": None if available else (
            select_error
            or ("xcode-select 未找到" if not xcode_select
                else "xcode-select -p 指向的目录不存在（Command Line Tools 未安装）")
        ),
        "extra": {
            "xcode_select": xcode_select,
            "developer_dir": developer_dir,
            "developer_dir_exists": dev_dir_exists,
            "is_full_xcode": is_full_xcode,
            "clt_root_exists": os.path.isdir(clt_root),
            "clang": {"path": clang, "version": clang_line or None},
            "xcodebuild_version": xcodebuild_version,
            "can_compile": bool(clang_line),
        },
    }


# Homebrew 的两个**固定安装前缀**（官方布局，不是猜的）：
#   /opt/homebrew  — Apple Silicon（arm64）默认前缀
#   /usr/local     — Intel（x86_64）默认前缀
# 为什么要写死这两个：agent / CI / 非交互 shell **不跑 shell 初始化脚本**
# （`.zprofile` / `.zshrc`），`eval "$(brew shellenv)"` 追加的那截 PATH 正好缺席，
# 只看 `shutil.which("brew")` 会把**确实装了**的 Homebrew 报成没装。
# 用字面量而不是 os.path.join：本函数即使被在 Windows 上直接调用（测试会这么干），
# 也仍然是 macOS 的 posix 路径，不能被 ntpath 改写成反斜杠。
_BREW_WELL_KNOWN = (
    "/opt/homebrew/bin/brew",   # Apple Silicon
    "/usr/local/bin/brew",      # Intel
)


def _probe_macos_homebrew(timeout: float = _CMD_TIMEOUT) -> dict:
    """macOS：Homebrew（brew 可执行存在性 + `brew --version` + `brew --prefix`）。

    判据分三层，**逐层都要有证据，不拿上一层冒充下一层**：

    1. **装了没有**（`available`）：`brew` 可执行真的存在 —— 先 PATH（`which`），
       再两个固定前缀 `/opt/homebrew/bin/brew`（Apple Silicon）、
       `/usr/local/bin/brew`（Intel）。**只看 PATH 会漏**：非交互 shell（agent 常驻
       的场景）拿不到 shellenv 追加的 PATH，工具装了却报没装，是假阴性。
    2. **能不能真跑**（`extra["can_run"]`）：`brew --version` 首行形如
       `Homebrew 4.3.2`。文件在但跑不出结论（Cellar 半删 / 权限坏 / 依赖的 ruby
       被拆）时 version 留空，note 里如实写「装上了但跑不起来」——
       不拿「文件存在」冒充「能用」。
    3. **装在哪、prefix 对不对**（`extra["prefix"]`）：`brew --prefix` 的**命令输出**
       最可信；拿不到才从可执行路径推导（`…/bin/brew` → `…`），并用
       `prefix_source` 标明来源，别把推导值当成命令结果。顺带按本机 arch 给出
       `arch_expected_prefix` 与 `prefix_matches_arch`（Rosetta 下的 brew 会出现
       arm64 机器配 /usr/local 前缀这种组合，是事实就报，不判对错）。

    探测不到（或非 macOS 上被直接调用）→ available=False + 明确 error，不抛异常。
    """
    timeout = _clamp_timeout(timeout)
    brew = _find_tool("brew", [], {"darwin": list(_BREW_WELL_KNOWN)})

    version_line = ""
    prefix = None
    prefix_source = None

    if brew:
        version_line = _get_version(brew, ["--version"], timeout)
        prefix_code, prefix_raw = _run([brew, "--prefix"], timeout)
        if prefix_code == 0:
            candidate = _first_line(_decode_output(prefix_raw))
            # 只认绝对路径：出错时 brew 会往 stdout 打提示语，不能当 prefix
            if candidate.startswith("/"):
                prefix = candidate.rstrip("/") or "/"
                prefix_source = "brew --prefix"

    if not prefix and brew:
        # 推导：/opt/homebrew/bin/brew → /opt/homebrew（dirname 两次）
        derived = os.path.dirname(os.path.dirname(brew))
        if derived and derived.startswith("/"):
            prefix = derived.rstrip("/") or "/"
            prefix_source = "derived_from_exe_path"

    arch = platform.machine()
    expected_prefix = "/opt/homebrew" if arch in ("arm64", "aarch64") else "/usr/local"
    prefix_exists = bool(prefix and os.path.isdir(prefix))
    cellar = (prefix.rstrip("/") + "/Cellar") if prefix else None

    available = bool(brew)
    can_run = bool(version_line)
    return {
        "available": available,
        "path": brew,
        "version": version_line or None,
        "error": None if available else (
            "brew 未找到：PATH 与 %s 下均无 brew（Homebrew 未安装）"
            % ", ".join(_BREW_WELL_KNOWN)
        ),
        "extra": {
            "exe": brew,
            "checked_paths": list(_BREW_WELL_KNOWN),
            "version_line": version_line or None,
            "version_number": _version_number(version_line),
            # 可执行存在 ≠ 能用：这一档区分「装了」与「装好了」
            "can_run": can_run,
            "prefix": prefix,
            "prefix_source": prefix_source,
            "prefix_exists": prefix_exists,
            "cellar": cellar,
            "cellar_exists": bool(cellar and os.path.isdir(cellar)),
            "arch": arch,
            "arch_expected_prefix": expected_prefix,
            "prefix_matches_arch": None if not prefix else prefix == expected_prefix,
            "on_apple_silicon_prefix": prefix == "/opt/homebrew",
            # brew shellenv 导出的环境（若当前进程有，直接摊开，便于对照 PATH 假阴性）
            "env": {
                "HOMEBREW_PREFIX": os.environ.get("HOMEBREW_PREFIX"),
                "HOMEBREW_CELLAR": os.environ.get("HOMEBREW_CELLAR"),
            },
            "note": (
                None if can_run else (
                    "brew 可执行存在，但 `brew --version` 没给出可用版本号"
                    "（可能 Cellar 损坏 / 权限异常 / ruby 依赖缺失）：只能确认「装了」，"
                    "不能确认「能用」"
                )
            ) if available else "无（未安装）",
        },
    }


# ---------------------------------------------------------------------------
# 平台 → 探测组（不在表里的平台直接跳过，不执行任何外部命令）
# ---------------------------------------------------------------------------

_PROBES_BY_PLATFORM = {
    "win32": (
        ("vs_build_tools", _probe_windows_vs_build_tools),
        ("wsl", _probe_windows_wsl),
        ("windows_terminal", _probe_windows_terminal),
    ),
    "linux": (
        ("systemd", _probe_linux_systemd),
        ("package_manager", _probe_linux_package_manager),
    ),
    "darwin": (
        ("xcode_clt", _probe_macos_xcode_clt),
        ("homebrew", _probe_macos_homebrew),
    ),
}


def _current_platform() -> str:
    """当前平台标签（win32 / linux / darwin），便于测试时替换。"""
    return sys.platform


def _to_item(name: str, data: dict) -> ProbeItem:
    """把探测函数返回的 dict 收敛成 ProbeItem（能力条目）。"""
    available = bool(data.get("available"))
    extra = dict(data.get("extra") or {})
    extra.setdefault("kind", _KIND_CAPABILITY)
    return ProbeItem(
        name=name,
        category=CATEGORY,
        available=available,
        path=data.get("path"),
        version=data.get("version"),
        error=None if available else (data.get("error") or "unavailable"),
        extra=extra,
    )


def _scope_item() -> ProbeItem:
    """适用范围条目：说明本机跑了哪些组、跳过了哪些组（跳过要有据可查）。

    这是**元信息**条目（`extra["kind"] == "meta"`），不是能力：`available=True`
    只说「这次范围探测成功了」。问「哪些平台工具可用」的消费方请用
    `is_capability_item()` 过滤（`get_platform_tools_info()` 已这么做）。
    """
    current = _current_platform()
    groups = [name for name, _ in _PROBES_BY_PLATFORM.get(current, ())]
    skipped = sorted(
        plat for plat in _PROBES_BY_PLATFORM if plat != current
    )
    return ProbeItem(
        name="platform_scope",
        category=CATEGORY,
        available=True,
        extra={
            "kind": _KIND_META,
            "platform": current,
            "os": platform.system(),
            "groups": groups,
            "skipped_groups": skipped,
            "note": "非当前平台的探测组已跳过（不执行外部命令、不产生错误条目）",
        },
    )


def is_capability_item(item) -> bool:
    """条目是否为「真能力」（False = 元信息/范围说明条目，如 platform_scope）。

    `platform_scope` 陈述的是「本次跑了哪些组、跳过了哪些组」，它的 available=True
    不代表装了任何工具。问「哪些平台工具可用」的消费方必须先过这道判定，
    否则会把元信息当成能力（假阳性）。
    """
    extra = getattr(item, "extra", None) or {}
    return extra.get("kind", _KIND_CAPABILITY) != _KIND_META


class PlatformToolsProber(Prober):
    """平台特有能力探测器（PROBE_PLAN.md Phase 2）。

    结果 section：`ProbeItem.category == "platform_tools"`。
    条目构成 = 1 个 `platform_scope`（**元信息**，`extra["kind"] == "meta"`）
    + 当前平台的各**能力**条目（`extra["kind"] == "capability"`：
      Windows: vs_build_tools / wsl / windows_terminal；
      Linux: systemd / package_manager；macOS: xcode_clt / homebrew）。

    `platform_scope.available=True` 只表示「范围探测成功」，**不是一项可用能力**；
    问「哪些平台工具可用」请用 `is_capability_item()` 过滤（或直接用
    `get_platform_tools_info()` 的 `available`，它已过滤）。

    用法::

        from vools.actus.probe.platform_tools import PlatformToolsProber
        items = PlatformToolsProber().run()
    """

    def probe(self) -> list:
        results = [_scope_item()]
        timeout = _clamp_timeout(self.timeout)
        current = _current_platform()

        # 整组硬截止：本探测器对外承诺「平台工具结论在 `_GROUP_BUDGET` 内给出」。
        # 为什么需要它（实测，见 build/probe_evidence/wsl_timing_before.out.txt）：
        # 机器有负载时**不止 WSL** 慢 —— 同一轮里 vswhere 也从 0.15s 涨到 0.59s。
        # 逐条各等上限会累加，所以这里让后跑的探测只拿到「剩余预算」：
        # 前面的探测慢了，后面的自动收窄上限（并在 extra 里标 timed_out/degraded），
        # 而不是让整组越拖越长。
        deadline = time.monotonic() + min(_GROUP_BUDGET, timeout)

        for name, probe_func in _PROBES_BY_PLATFORM.get(current, ()):
            remaining = deadline - time.monotonic()
            # 预算耗尽也**照跑**（给最小额度）：条目必须存在且带「超时」信号，
            # 不能因为预算用光就少一条 item（那会让「没响应」变成「没这一项」）
            probe_timeout = max(_MIN_PROBE_TIMEOUT, min(timeout, remaining))
            try:
                data = probe_func(probe_timeout)
            except Exception as exc:  # 单条探测失败不影响其它项（探测不抛异常约定）
                results.append(ProbeItem(
                    name=name,
                    category=CATEGORY,
                    available=False,
                    error="%s: %s" % (type(exc).__name__, exc),
                ))
                continue
            item = _to_item(name, data)
            try:
                # 本条探测从整组预算里分到的额度（诊断用：整组 1.8s 被谁吃掉了）
                item.extra["group_budget_s"] = round(
                    max(0.0, min(timeout, remaining)), 3)
            except (AttributeError, TypeError):
                pass
            results.append(item)

        return results


# ---------------------------------------------------------------------------
# 便捷入口（与 README「每个探测器另提供模块级 probe()」约定一致）
# ---------------------------------------------------------------------------

def probe() -> list:
    """执行平台特有能力探测，返回 ProbeItem 列表。"""
    return PlatformToolsProber().run()


def get_platform_tools_info() -> dict:
    """平台特有能力探测的 dict 视图（供直接嵌入报告/JSON 的消费方使用）。

    返回结构（**能力与元信息分开承载**，避免「platform_scope 算一个可用工具」的假阳性）::

        {
          "platform":    "win32",
          "features":    {能力条目名: 条目 dict},   # 只有真能力，不含 platform_scope
          "available":   [可用的能力条目名],        # 已按 is_capability_item 过滤
          "unavailable": [不可用的能力条目名],      # 同上，如实列出「没装/不可用」
          "scope":       {platform_scope 条目 dict} # 元信息：跑了哪些组、跳过哪些组
          "meta":        ["platform_scope"],        # 元信息条目名（便于通用排除）
        }
    """
    features = {}
    meta = {}
    for item in PlatformToolsProber().run():
        entry = item.to_dict()
        if is_capability_item(item):
            features[item.name] = entry
        else:
            meta[item.name] = entry

    return {
        "platform": _current_platform(),
        "features": features,
        "available": sorted(
            name for name, entry in features.items() if entry["available"]
        ),
        "unavailable": sorted(
            name for name, entry in features.items() if not entry["available"]
        ),
        "scope": meta.get("platform_scope") or (
            next(iter(meta.values())) if meta else {}
        ),
        "meta": sorted(meta),
    }
