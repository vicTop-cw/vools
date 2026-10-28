# -*- coding: utf-8 -*-
"""actus/tests/test_probe_windows.py — Windows 专有探测项验收测试。

测什么 / 为什么
---------------
PROBE_PLAN.md Phase 2 里的计划文件名 `tests/test_probe_windows.py` 一直不存在
（等价覆盖散落在 `test_probe.py` 与 `test_probe_platform_tools.py`）。本文件按计划
文件名独立成篇，专测 **Windows 侧**的四类专有能力：

1. **VS / VS Build Tools** —— `platform_tools._probe_windows_vs_build_tools`
   走 `vswhere.exe -products * -format json`，解析安装实例/版本/MSVC 工具集；
2. **WSL** —— `_probe_windows_wsl` 的 `wsl.exe -l -v` 输出是 **UTF-16LE**，
   解析发行版名称/状态/版本/默认发行版，以及 WSL 自身版本；
3. **Windows Terminal** —— `_probe_windows_terminal` 的 `wt.exe` 是 App Execution
   Alias（`--version` 无输出），版本只能从商店包目录名解析；
4. **PATH / PATHEXT 判定** —— Windows 上「可执行文件」的判据是 PATHEXT 扩展名
   （`os.access(X_OK)` 在 Windows 上对任何存在的文件都为真，不能用）；覆盖
   `environment._scan_path_executables` 与 `system_tools._find_tool`（契约冻结）两处。

**不依赖本机真的装了 VS / WSL / Windows Terminal**：所有探测路径、注册表无关的
文件系统事实全部造在 `tmp_path` 下的「假 Windows 世界」里（ProgramFiles /
ProgramFiles(x86) / LOCALAPPDATA / SystemRoot 环境变量指向 tmp），外部命令一律
用 `platform_tools._run` 替身按 argv 分发 canned 输出（**不打全局 `subprocess.run`**，
否则会打坏 stdlib `platform` 自己的子进程调用，见 `_run_stub` 的注释）。本机恰好
装了 VS+WSL+Terminal，正是最容易被「假绿」掩盖的环境，所以这里连 `shutil.which`
都默认打桩成「什么都没有」，只在用例里按需返回。

**非 Windows 宿主优雅跳过**：整个文件 `skipif(sys.platform != "win32")`
（探测逻辑本身就有 `sys.platform` 分派，非 Windows 上这些条目根本不会被跑；
在非 Windows 宿主上强行打桩会把「平台分派」本身测成假的）。

为什么不用 `importlib.reload`
------------------------------
上一轮的教训：reload 会产生新的类对象并残留在 `Prober.__subclasses__()` 里，
污染其它测试文件的探测器枚举（实测「跑到 10 / 枚举 22」）。本文件只用
monkeypatch 打桩，平台分派用产品自带的 `_current_platform()` 测试钩子替换，
不 reload、不造类。
"""

import json
import os
import shutil
import sys

import pytest

# 与同目录其它 actus 测试一致：先跑本地源码引导，让 vools.actus 命中源码树
# 而不是 site-packages 的发布 wheel（否则测的是旧包，结论是假的）。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

from vools.actus.probe import environment as environment_mod  # noqa: E402
from vools.actus.probe import platform as platform_mod  # noqa: E402
from vools.actus.probe import platform_tools as platform_tools_mod  # noqa: E402
from vools.actus.probe import system_tools as system_tools_mod  # noqa: E402
from vools.actus.probe.base import ProbeItem  # noqa: E402

# Windows 专有探测项：非 Windows 宿主优雅跳过（见模块 docstring）
pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Windows 专有探测项（VS/WSL/Terminal/PATHEXT），非 Windows 宿主跳过")


# ---------------------------------------------------------------------------
# 假 Windows 世界：路径全在 tmp，外部命令全部 canned
# ---------------------------------------------------------------------------

def _run_stub(handlers):
    """构造 `platform_tools._run` 的替身：按 argv[0] 的 basename 分发 canned 输出。

    handlers: {"vswhere.exe": lambda argv: (0, b"{...}"), ...}
    返回 `(returncode, raw_bytes)`，与产品 `_run` 的契约一致；未登记的命令一律
    `(None, b"")`（= 跑不起来 / 没装），与真实 `_run` 的失败形态相同。

    **为什么打 `_run` 而不是 `subprocess.run`**：后者是全局补丁，会连 stdlib
    `platform` 自己的子进程调用一起打坏 —— 实测 `platform.win32_ver()` 拿到
    bytes stdout 后 `re.search` 抛 `TypeError`，整条探测器降级成一条 error 条目。
    更阴的是这个坑**只在「本文件先跑」的顺序下复现**（前面有别的测试把平台信息
    的 lru_cache 预热过就不复现），是最难查的顺序依赖。`_run` 是 platform_tools
    自己的唯一外部命令入口：打它既能覆盖全部解析逻辑（vswhere JSON / WSL
    UTF-16LE / 版本号），又零全局副作用。
    """

    def fake_run(argv, timeout=None):
        key = os.path.basename(str(argv[0])).lower()
        handler = handlers.get(key)
        if handler is None:
            return None, b""
        return handler(argv)

    return fake_run


@pytest.fixture
def windows_world(tmp_path, monkeypatch):
    """把「假 Windows 世界」的根目录与打桩准备好。

    * ProgramFiles / ProgramFiles(x86) / LOCALAPPDATA / APPDATA / ProgramData /
      SystemRoot 全部指向 `tmp_path` 下的空目录 —— 本机真实安装路径不会被读到；
    * `shutil.which` → None（先证明「什么都没装」，用例再按需造文件）；
    * `platform_tools._run` → 一律「跑不起来」（用例按需叠加 canned 输出）；
    * `_current_platform` → "win32"（产品自带的平台判定钩子，不 reload）。
    """
    dirs = {
        "tmp": tmp_path,
        "program_files": tmp_path / "ProgramFiles",
        "program_files_x86": tmp_path / "ProgramFilesX86",
        "local_app_data": tmp_path / "LocalAppData",
        "app_data": tmp_path / "AppData",
        "program_data": tmp_path / "ProgramData",
        "system_root": tmp_path / "Windows",
    }
    dirs["program_files"].mkdir()
    dirs["program_files_x86"].mkdir()
    dirs["local_app_data"].mkdir()
    dirs["app_data"].mkdir()
    dirs["program_data"].mkdir()
    (dirs["system_root"] / "System32").mkdir(parents=True)

    monkeypatch.setenv("ProgramFiles", str(dirs["program_files"]))
    monkeypatch.setenv("ProgramFiles(x86)", str(dirs["program_files_x86"]))
    monkeypatch.setenv("LOCALAPPDATA", str(dirs["local_app_data"]))
    monkeypatch.setenv("APPDATA", str(dirs["app_data"]))
    monkeypatch.setenv("ProgramData", str(dirs["program_data"]))
    monkeypatch.setenv("SystemRoot", str(dirs["system_root"]))

    monkeypatch.setattr(platform_tools_mod, "_current_platform", lambda: "win32")
    monkeypatch.setattr(shutil, "which", lambda *args, **kwargs: None)
    monkeypatch.setattr(platform_tools_mod, "_run", _run_stub({}))
    return dirs


def _write_file(path, content=b"stub"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _items_by_name(items):
    return {item.name: item for item in items}


def _probe_windows_items():
    """跑一次 Windows 平台探测器，返回 {条目名: ProbeItem}。"""
    items = platform_tools_mod.PlatformToolsProber().run()
    for item in items:
        assert isinstance(item, ProbeItem), "返回了非 ProbeItem: %r" % (item,)
    by_name = _items_by_name(items)
    assert "platform_scope" in by_name, "平台探测器没有产出范围条目"
    return by_name


# ---------------------------------------------------------------------------
# 1) VS / VS Build Tools：vswhere JSON → 安装实例 + MSVC 工具集
# ---------------------------------------------------------------------------

def test_vs_build_tools_parsed_from_vswhere_json(windows_world, monkeypatch):
    """vswhere 的 JSON 输出必须被解析成安装实例、版本、MSVC 工具集。"""
    vswhere = (windows_world["program_files_x86"] / "Microsoft Visual Studio"
               / "Installer" / "vswhere.exe")
    _write_file(vswhere)

    install = windows_world["tmp"] / "VS" / "BuildTools"
    toolset = install / "VC" / "Tools" / "MSVC" / "14.40.33807"
    _write_file(toolset / "bin" / "Hostx64" / "x64" / "cl.exe")
    _write_file(install / "VC" / "Auxiliary" / "Build" / "vcvars64.bat")

    payload = json.dumps([{
        "displayName": "Visual Studio Build Tools 2022",
        "installationVersion": "17.11.35312.102",
        "installationPath": str(install),
        "productId": "Microsoft.VisualStudio.Product.BuildTools",
        "isComplete": True,
    }]).encode("utf-8")
    monkeypatch.setattr(platform_tools_mod, "_run", _run_stub(
        {"vswhere.exe": lambda argv: (0, payload)}))

    items = _probe_windows_items()
    vs = items.get("vs_build_tools")
    assert vs is not None, "Windows 分支没有产出 vs_build_tools 条目"
    assert vs.available is True
    assert vs.version == "17.11.35312.102"
    assert vs.path == str(install)
    assert vs.extra["method"] == "vswhere", \
        "走 vswhere 时 method 必须如实标注，实得 %r" % (vs.extra.get("method"),)
    assert vs.extra["has_cpp_toolset"] is True
    installs = vs.extra["installs"]
    assert installs and installs[0]["path"] == str(install)
    assert installs[0]["vcvars64"] is True
    assert [t["version"] for t in installs[0]["msvc_toolsets"]] == ["14.40.33807"]
    assert installs[0]["msvc_toolsets"][0]["cl_x64"] is True


# ---------------------------------------------------------------------------
# 2) WSL：UTF-16LE 输出解析（最容易踩的编码坑）
# ---------------------------------------------------------------------------

def test_wsl_distros_parsed_from_utf16le_output(windows_world, monkeypatch):
    """`wsl.exe -l -v` 是 UTF-16LE 输出：发行版/默认发行版/WSL2 判据都要解析对。"""
    _write_file(windows_world["system_root"] / "System32" / "wsl.exe")

    listing = (
        "  NAME            STATE           VERSION\r\n"
        "* Ubuntu-22.04    Running         2\r\n"
        "  Debian          Stopped         1\r\n"
    )
    version_text = (
        "WSL version: 2.2.4.0\r\n"
        "Kernel version: 5.15.153.1-2\r\n"
    )

    def handler(argv):
        if "--version" in argv:
            return 0, version_text.encode("utf-16-le")
        return 0, listing.encode("utf-16-le")

    monkeypatch.setattr(platform_tools_mod, "_run", _run_stub({"wsl.exe": handler}))

    items = _probe_windows_items()
    wsl = items.get("wsl")
    assert wsl is not None, "Windows 分支没有产出 wsl 条目"
    assert wsl.available is True
    assert wsl.path == str(windows_world["system_root"] / "System32" / "wsl.exe")
    assert wsl.extra["wsl_version"] == "2.2.4.0"
    assert wsl.extra["distro_count"] == 2
    distros = {d["name"]: d for d in wsl.extra["distros"]}
    assert set(distros) == {"Ubuntu-22.04", "Debian"}
    assert distros["Ubuntu-22.04"]["state"] == "Running"
    assert distros["Ubuntu-22.04"]["version"] == 2
    assert distros["Debian"]["version"] == 1
    assert wsl.extra["default_distro"] == "Ubuntu-22.04"
    assert wsl.extra["wsl2_capable"] is True
    # 条目可 JSON 序列化（报告要落缓存 / 给 LLM 消费）
    json.dumps(wsl.to_dict(), ensure_ascii=False)


# ---------------------------------------------------------------------------
# 3) Windows Terminal：别名存在 + 商店包目录名取版本
# ---------------------------------------------------------------------------

def test_windows_terminal_version_from_store_package(windows_world):
    """wt.exe 别名存在即可用；版本取商店包目录名里最高的那个（排除语言存根）。"""
    alias = (windows_world["local_app_data"] / "Microsoft" / "WindowsApps" / "wt.exe")
    _write_file(alias)

    apps = windows_world["program_files"] / "WindowsApps"
    real_pkg = apps / "Microsoft.WindowsTerminal_1.18.3181.0_x64__8wekyb3d8bbwe"
    _write_file(real_pkg / "wt.exe")
    # 语言存根（neutral_~_）里没有 wt.exe，不许把它的版本算进来
    stub_pkg = apps / "Microsoft.WindowsTerminal_1.17.0.0_neutral_~_8wekyb3d8bbwe"
    _write_file(stub_pkg / "locale.pri")

    items = _probe_windows_items()
    terminal = items.get("windows_terminal")
    assert terminal is not None, "Windows 分支没有产出 windows_terminal 条目"
    assert terminal.available is True
    assert terminal.path == str(alias)
    assert terminal.version == "1.18.3181.0", \
        "版本必须来自含 wt.exe 的商店包目录，实得 %r" % (terminal.version,)
    assert terminal.extra["version_source"] == "store_package_dir"
    package_versions = {p["version"] for p in terminal.extra["packages"]}
    assert package_versions == {"1.18.3181.0", "1.17.0.0"}


# ---------------------------------------------------------------------------
# 4) 干净机器：三个 Windows 探测项都如实报不可用，不抛异常、不伪造
# ---------------------------------------------------------------------------

def test_absent_windows_tools_are_reported_unavailable(windows_world):
    """假 Windows 世界里什么都没装：三项都必须 available=False 且带原因。

    本机真实装了 VS+WSL+Terminal —— 这条用例正是「不被真机掩盖」的判据：
    所有安装根目录都在 tmp，`shutil.which` 打桩成 None，外部命令一律失败。
    """
    items = _probe_windows_items()
    for name in ("vs_build_tools", "wsl", "windows_terminal"):
        assert name in items, "Windows 分支没有产出 %r 条目" % name
        item = items[name]
        assert item.available is False, "%s 在空机器上不该被报成可用" % name
        assert item.error, "%s 不可用时必须带原因（不静默）" % name

    scope = items["platform_scope"]
    assert scope.extra["platform"] == "win32"
    assert scope.extra["groups"] == [
        "vs_build_tools", "wsl", "windows_terminal"]


# ---------------------------------------------------------------------------
# 5) PATH / PATHEXT 判定
# ---------------------------------------------------------------------------

def test_find_tool_honors_pathext(tmp_path, monkeypatch):
    """Windows 上「能不能找到工具」由 PATHEXT 决定，不是文件存在性。

    `shutil.which` 在 win32 上按 `cmd + PATHEXT扩展名` 逐个试；
    所以同一个 probetool.exe：PATHEXT 含 .EXE → 找得到，不含 → 找不到。
    """
    bindir = tmp_path / "bin"
    _write_file(bindir / "probetool.exe")
    monkeypatch.setenv("PATH", str(bindir))

    monkeypatch.setenv("PATHEXT", ".COM;.EXE;.BAT;.CMD")
    found = system_tools_mod._find_tool("probetool", [], {})
    assert found, "PATHEXT 含 .EXE 时应能找到 probetool.exe"
    assert found.lower().endswith("probetool.exe")

    monkeypatch.setenv("PATHEXT", ".BAT;.CMD")
    assert system_tools_mod._find_tool("probetool", [], {}) is None, \
        "PATHEXT 不含 .EXE 时 probetool.exe 不算可执行（这不是「文件存在性」判定）"


def test_environment_path_executables_respect_pathext(tmp_path, monkeypatch):
    """environment 的 PATH 可执行文件清单必须按 PATHEXT 过滤。

    旧实现用 `os.access(X_OK)`，而 Windows 上它对**任何存在的文件**都为真 ——
    .dll/.txt/.pdb 会全被算成「可执行文件」。判据只能是 PATHEXT。
    """
    bindir = tmp_path / "bin"
    for name in ("runme.exe", "script.bat", "go.cmd",
                 "library.dll", "notes.txt", "noext"):
        _write_file(bindir / name)
    monkeypatch.setenv("PATH", str(bindir))
    monkeypatch.setenv("PATHEXT", ".COM;.EXE;.BAT;.CMD")

    info = environment_mod.get_environment_info()
    assert set(info["path_executables"]) == {"runme.exe", "script.bat", "go.cmd"}, \
        "PATH 可执行清单被非 PATHEXT 文件污染了: %r" % (info["path_executables"],)

    # 换一份 PATHEXT：判据必须跟着环境变量走，不能写死四种扩展名
    monkeypatch.setenv("PATHEXT", ".DLL")
    info2 = environment_mod.get_environment_info()
    assert set(info2["path_executables"]) == {"library.dll"}, \
        "PATHEXT 换成 .DLL 后应按新规则过滤，实得 %r" % (
            info2["path_executables"],)


def test_pathext_filtering_is_windows_only(tmp_path, monkeypatch):
    """PATHEXT 过滤只在 win32 生效（POSIX 分支看执行位，不看扩展名）。"""
    bindir = tmp_path / "bin"
    _write_file(bindir / "runme.exe")
    monkeypatch.setenv("PATH", str(bindir))
    monkeypatch.setenv("PATHEXT", ".EXE")

    monkeypatch.setattr(sys, "platform", "linux")
    info = environment_mod.get_environment_info()
    # POSIX 判据是 stat 的执行位；Windows 上造出来的 .exe 没有 x 位 → 不算可执行
    assert info["path_executables"] == [], \
        "POSIX 分支不该按 PATHEXT 收 .exe，实得 %r" % (info["path_executables"],)


# ---------------------------------------------------------------------------
# 6) platform.py 的 Windows 字段
# ---------------------------------------------------------------------------

def test_platform_info_reports_windows_fields(windows_world):
    """`get_platform_info()` 必须带上 Windows 专有字段，且路径类字段来自环境变量。"""
    info = platform_mod.get_platform_info()
    assert info["is_windows"] is True
    assert info["platform_tag"] == "win32"
    for key in ("windows_version", "windows_build", "program_files",
                "program_files_x86", "local_app_data", "app_data", "program_data"):
        assert key in info, "Windows 专有字段缺 %r" % key
    assert info["program_files"] == str(windows_world["program_files"])
    assert info["local_app_data"] == str(windows_world["local_app_data"])
    # build 号形如 "10.0.26200"（platform.version 的来源）；拿不到时允许空串但不许 None
    assert isinstance(info["windows_build"], str)
    assert isinstance(info["windows_version"], str)


# ---------------------------------------------------------------------------
# 7) 平台分派：非 Windows 平台不跑 Windows 探测组（sys.platform 打桩）
# ---------------------------------------------------------------------------

def test_non_windows_platform_skips_windows_groups(windows_world, monkeypatch):
    """把平台判定切到 linux：报告里不得出现 Windows 三项，范围条目要如实记录跳过。"""
    monkeypatch.setattr(platform_tools_mod, "_current_platform", lambda: "linux")

    by_name = _probe_windows_items()
    for name in ("vs_build_tools", "wsl", "windows_terminal"):
        assert name not in by_name, "非 Windows 平台不许执行 %r 探测" % name
    scope = by_name["platform_scope"]
    assert scope.extra["platform"] == "linux"
    assert scope.extra["groups"] == ["systemd", "package_manager"]
    assert "win32" in scope.extra["skipped_groups"]
