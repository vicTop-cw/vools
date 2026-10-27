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
└──────────┴──────────────────────────────────────────────────────────────┘

设计约束（对应 PROBE_PLAN.md §4.1/§4.2 与任务要求）：

1. **判据真实**：只用真实可执行的判据（vswhere 的固定安装路径、`wsl.exe -l -v`、
   `xcode-select -p`、`systemctl --version`、包管理器可执行文件存在性）。探测不到
   就如实报 unavailable + error，**不伪造**。
2. **跨平台安全**：非当前平台的探测组直接跳过（不执行外部命令、不抛异常、不进
   报告条目）；即使被直接调用，单个探测函数也只会在该平台找不到东西，
   收敛成 unavailable 而不是异常。
3. **短超时**：所有外部命令都有超时（默认 5s，上限也是 5s，见 `_clamp_timeout`）。
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
    """
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            timeout=_clamp_timeout(timeout),
        )
        return completed.returncode, completed.stdout or b""
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError, ValueError):
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
    """Windows：Visual Studio / VS Build Tools（含 MSVC 工具集）。"""
    program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")

    # vswhere 的标准安装位置（VS Installer 固定落在这里），PATH 兜底
    vswhere = _find_tool("vswhere", [], {"win32": [
        os.path.join(program_files_x86, "Microsoft Visual Studio", "Installer", "vswhere.exe"),
        os.path.join(program_files, "Microsoft Visual Studio", "Installer", "vswhere.exe"),
    ]})

    method = None
    installs = None
    if vswhere:
        installs = _vswhere_installs(vswhere, timeout)
        if installs is not None:
            method = "vswhere"

    if installs is None:
        # vswhere 不存在或查询失败 → 只认默认布局（自定义路径必然漏，method 如实标注）
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
    return {
        "available": available,
        "path": first.get("path") or None,
        "version": first.get("version") or None,
        "error": None if available else "vswhere.exe 未找到，且默认安装布局下没有 Visual Studio 实例",
        "extra": {
            "method": method,
            "vswhere": vswhere,
            "installs": detail,
            "has_cpp_toolset": has_cpp,
            "note": None if has_cpp else (
                "检测到 VS 实例但没找到 MSVC 工具集（未安装「使用 C++ 的桌面开发」工作负载）"
                if available else "无"
            ),
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


def _probe_windows_wsl(timeout: float = _CMD_TIMEOUT) -> dict:
    """Windows：WSL（可执行文件 + 已装发行版 + WSL 版本）。"""
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
            "extra": {"exe": None},
        }

    # WSL 自身版本（WSL 2.x 才支持 --version，旧版返回错误 → version 留空，不算失败）
    version_code, version_raw = _run([exe, "--version"], timeout)
    version_text = _decode_output(version_raw) if version_code == 0 else ""
    wsl_version = _version_number(version_text)

    # 发行版列表：UTF-16LE 输出，必须有编码处理
    list_code, list_raw = _run([exe, "-l", "-v"], timeout)
    distros = _parse_wsl_distros(_decode_output(list_raw))
    list_error = None
    if list_code != 0 or not distros:
        # 兜底：-l -q 只列名字（-l -v 在老版本/异常状态可能失败）
        quiet_code, quiet_raw = _run([exe, "-l", "-q"], timeout)
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
        elif list_code != 0:
            list_error = "wsl.exe -l -v 失败（returncode=%s）" % list_code

    default_distro = next(
        (distro["name"] for distro in distros if distro["default"]), None
    )
    available = list_code == 0
    return {
        "available": available,
        "path": exe,
        "version": wsl_version,
        "error": None if available else (list_error or "wsl.exe 存在但不可用"),
        "extra": {
            "exe": exe,
            "wsl_version": wsl_version,
            "distros": distros,
            "distro_count": len(distros),
            "default_distro": default_distro,
            "has_distro": bool(distros),
            "wsl2_capable": any(distro.get("version") == 2 for distro in distros),
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
# macOS × 1
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
      Linux: systemd / package_manager；macOS: xcode_clt）。

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

        for name, probe_func in _PROBES_BY_PLATFORM.get(current, ()):
            try:
                data = probe_func(timeout)
            except Exception as exc:  # 单条探测失败不影响其它项（探测不抛异常约定）
                results.append(ProbeItem(
                    name=name,
                    category=CATEGORY,
                    available=False,
                    error="%s: %s" % (type(exc).__name__, exc),
                ))
                continue
            results.append(_to_item(name, data))

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
