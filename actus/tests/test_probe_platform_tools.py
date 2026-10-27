# -*- coding: utf-8 -*-
"""actus/tests/test_probe_platform_tools.py — 平台特有能力探测器验收测试。

被测对象：``vools/actus/probe/platform_tools.py`` 里的 ``PlatformToolsProber``
（``Prober`` 子类）——探测 Windows 的 VS Build Tools / WSL / Windows Terminal、
Linux 的 systemd / 包管理器、macOS 的 Xcode CLT。

测什么 / 为什么
---------------
1. **契约**：模块导出 ``PlatformToolsProber``、是 ``Prober`` 子类、能无参实例化
   （probe() 里就是 ``ProberClass()``）、``run()`` 出结构正确的条目。
2. **跨平台安全**：用 ``sys.platform`` 打桩覆盖 win32 / linux / darwin 三分支。
   任何分支都不许抛异常；base.Prober.run 会把异常兜成条目，所以额外断言
   「报告里没有以类名命名的条目」—— 那正是被兜住的崩溃，不能当作优雅降级。
3. **干净机器假设**：把所有「机器上装了什么」的入口（which / subprocess /
   文件存在性 / glob）打桩成「什么都没有」。此时**非本源平台**的探测项必须
   报不可用，不得声称命中 —— 跨平台分支没短路、或探测不看平台，都会在这里亮红。
4. **目标平台覆盖**：在目标平台上即使一个工具都没装，也必须如实报告「探测过」
   哪些能力，且条目语义能对上 VS Build Tools / WSL / Windows Terminal、
   systemd / 包管理器、Xcode CLT（关键词匹配，容忍命名差异）。

为什么不依赖本机真装了什么
-------------------------
执行测试的机器可能是装了 VS 的 Windows 开发机，也可能是不装 WSL/Xcode 的 CI。
所有探测入口都打桩，断言只针对「映射后的行为」，不读注册表、不跑真命令。

为什么**不** reload 模块（重要，别改回去）
------------------------------------------
最初用 ``importlib.reload`` 来覆盖「模块导入时就把平台收进常量」的实现，但 reload
会重新执行模块、产生**新的类对象**，旧类仍挂在 ``Prober.__subclasses__()`` 里；
同进程里多平台参数化 reload 若干次后陈旧类会累积（实测 12 个），而
``test_probe_parallel.py`` 按子类枚举探测器 → 「跑到 10 个 / 枚举 22 个」对不上而误红
（两个文件单独跑都绿，组合起来才炸）。
现在只打桩、不 reload：
  * ``platform_tools._current_platform`` —— 产品自带的平台判定钩子（其 docstring
    明写「便于测试时替换」），决定本次跑哪一组探测；
  * ``sys.platform`` —— 模块内 / ``system_tools._find_tool`` 里直接读平台标签的
    路径（well-known 安装路径表按平台分桶）。
这样两个测试文件无论怎么组合、什么顺序跑，都不会互相污染。

模块尚未落地时（平台能力司令编写中）每个用例 skip 而不是让套件变红 ——
落地后本文件自动生效，不需要改一行。

py3.6 兼容：只用 contextlib/importlib/标准库，% 格式化，不用 f-string。
"""

import glob
import importlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
from contextlib import contextmanager

import pytest

# 与同目录其它 actus 测试一致：先跑本地源码引导，让 vools.actus 命中源码树
# 而不是 site-packages 的发布 wheel（否则测的是旧包，结论是假的）。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

from vools.actus.probe.base import ProbeItem, Prober  # noqa: E402

_MODULE_NAME = "vools.actus.probe.platform_tools"
_ALL_PLATFORMS = ("win32", "linux", "darwin")

# 每个平台的「能力关键词」：条目名/分类/path/version/extra 里至少命中一个，
# 用来证明该平台确实探测了规格要求的能力（容忍具体命名差异）。
_CAPABILITY_KEYWORDS = {
    "win32": ("vs", "visual studio", "build tools", "msbuild",
              "wsl", "terminal", "wt.exe"),
    "linux": ("systemd", "systemctl", "apt", "dnf", "yum", "pacman",
              "zypper", "apk", "pkg", "package", "snap", "flatpak"),
    "darwin": ("xcode", "xcode-select", "clt", "command line tools", "developer"),
}


# ---------------------------------------------------------------------------
# 夹具：模块可能在编写中 —— 缺模块按约定 skip，不是 fail
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def pt_module():
    """导入 platform_tools；模块文件还不存在时 skip（平台能力司令编写中）。"""
    try:
        mod = importlib.import_module(_MODULE_NAME)
    except ImportError as exc:
        missing = getattr(exc, "name", "") or ""
        if missing == _MODULE_NAME:
            pytest.skip("%s 尚未落地（平台能力司令编写中），按约定跳过" % _MODULE_NAME)
        # 模块文件在、但导入时炸了（多半是顶层无条件 import 了平台专属模块，
        # 或者把可选依赖写成了硬依赖）—— 这是真缺陷，不许 skip 掉。
        pytest.fail(
            "platform_tools.py 存在但导入失败，可能是模块顶层无条件 import 了"
            "平台专属模块 / 可选依赖：%r" % (exc,))
    if getattr(mod, "__file__", None) is None:
        pytest.skip("%s 不是真实模块文件" % _MODULE_NAME)
    return mod


@pytest.fixture(scope="module")
def prober_cls(pt_module):
    """取 PlatformToolsProber 类；模块在但没导出它同样按「未落地」skip。"""
    cls = getattr(pt_module, "PlatformToolsProber", None)
    if cls is None:
        pytest.skip("platform_tools.py 已存在但没有导出 PlatformToolsProber")
    return cls


# ---------------------------------------------------------------------------
# 打桩工具
# ---------------------------------------------------------------------------

@contextmanager
def _platform_context(module, fake_platform):
    """在假平台下调用产品：**只打桩、绝不 reload**（reload 会制造陈旧类，见模块 docstring）。

    打桩两处：
    * ``module._current_platform`` —— 产品自带的平台判定钩子，决定跑哪一组探测；
    * ``sys.platform`` —— 模块内与 ``system_tools._find_tool`` 里直接读平台标签的路径。
    退出时两处都恢复原值。
    """
    real_platform = sys.platform
    sentinel = object()
    original_hook = getattr(module, "_current_platform", sentinel)
    if original_hook is not sentinel:
        module._current_platform = lambda: fake_platform
    sys.platform = fake_platform
    try:
        yield module
    finally:
        sys.platform = real_platform
        if original_hook is not sentinel:
            module._current_platform = original_hook


def _sterile_machine(monkeypatch):
    """把「机器上装了什么」的全部入口打桩成「什么都没有」。

    * ``shutil.which`` → None（PATH 里找不到任何工具）
    * ``subprocess.run/check_output/check_call/Popen`` → 跑不起来
    * ``os.path.exists/isfile/isdir``、``pathlib.Path.exists/is_file/is_dir`` → False
      （固定安装路径一律不存在）
    * ``glob.glob`` → []（通配符安装路径一律空）

    打的是 OS 边界而不是探测器内部函数：实现怎么重构都不会让桩落空。
    """

    class _StubProcess(object):
        returncode = 1
        stdout = ""
        stderr = "stub: not installed"

    def _run_stub(*args, **kwargs):
        return _StubProcess()

    def _raise_stub(*args, **kwargs):
        raise FileNotFoundError("stub: not installed")

    monkeypatch.setattr(shutil, "which", lambda *a, **k: None)
    monkeypatch.setattr(subprocess, "run", _run_stub)
    monkeypatch.setattr(subprocess, "check_output", _raise_stub)
    monkeypatch.setattr(subprocess, "check_call", _run_stub)
    monkeypatch.setattr(subprocess, "Popen", _raise_stub)
    monkeypatch.setattr(glob, "glob", lambda *a, **k: [])
    monkeypatch.setattr(os.path, "exists", lambda *a, **k: False)
    monkeypatch.setattr(os.path, "isfile", lambda *a, **k: False)
    monkeypatch.setattr(os.path, "isdir", lambda *a, **k: False)
    monkeypatch.setattr(pathlib.Path, "exists", lambda self: False)
    monkeypatch.setattr(pathlib.Path, "is_file", lambda self: False)
    monkeypatch.setattr(pathlib.Path, "is_dir", lambda self: False)


# ---------------------------------------------------------------------------
# 结构断言
# ---------------------------------------------------------------------------

def _assert_item_shape(cls, items):
    """条目结构必须正确，且不能把崩溃伪装成结果。

    base.Prober.run 在 probe() 抛异常时会产出一个 ``name == 类名`` 的降级条目，
    正常探测不会这么命名 —— 出现即说明「优雅跳过」其实是「崩了被兜住」。
    """
    assert isinstance(items, list), "run() 必须返回 list，实得 %r" % type(items)
    assert items, "%s 在 %s 上一条结果都没有：探测项应如实报「不可用」，而不是空手而归" % (
        cls.__name__, sys.platform)
    for item in items:
        assert isinstance(item, ProbeItem), "返回了非 ProbeItem: %r" % (item,)
        assert isinstance(item.name, str) and item.name.strip(), "条目缺 name"
        assert isinstance(item.available, bool), "%s 的 available 不是 bool" % item.name
        assert item.name != cls.__name__, (
            "探测过程抛异常被 base.run 兜住了（不叫优雅跳过）：error=%r" % (item.error,))
        if item.available:
            assert item.path or item.version or item.extra, (
                "%s 声称可用却没有任何证据（path/version/extra 全空）" % item.name)
        # 报告要落缓存 / 给 LLM 消费，条目必须可 JSON 序列化
        json.dumps(item.to_dict(), ensure_ascii=False)


def _item_blob(item):
    """把条目的可读字段揉成一个 lower 串，供能力关键词匹配。"""
    parts = [str(item.name), str(item.category),
             str(item.path or ""), str(item.version or "")]
    try:
        parts.append(json.dumps(item.extra, ensure_ascii=False, default=str))
    except (TypeError, ValueError):
        parts.append(str(item.extra))
    return " ".join(parts).lower()


# ---------------------------------------------------------------------------
# 1) 契约
# ---------------------------------------------------------------------------

def test_exported_prober_is_prober_subclass(prober_cls):
    """PlatformToolsProber 必须是 Prober 子类，且能无参实例化。"""
    assert issubclass(prober_cls, Prober), \
        "%r 不是 Prober 子类（probe() 依赖 run() 模板方法做异常兜底）" % (prober_cls,)
    assert prober_cls is not Prober

    module = sys.modules.get(prober_cls.__module__)
    if module is not None and getattr(module, "__all__", None) is not None:
        assert "PlatformToolsProber" in module.__all__, \
            "__all__ 没导出 PlatformToolsProber（probe 包每个子模块都这么导出）"

    prober = prober_cls()          # probe() 里就是 ProberClass()
    assert isinstance(prober, Prober)


def test_run_returns_structured_items(prober_cls, monkeypatch):
    """本机什么都不装时，run() 也要出结构正确的条目（如实报不可用）。"""
    _sterile_machine(monkeypatch)
    items = prober_cls().run()
    _assert_item_shape(prober_cls, items)


def test_module_level_entry_points(pt_module, monkeypatch):
    """模块级便捷入口（probe() / get_platform_tools_info()）同样要能用。

    这两个名字都在模块 ``__all__`` 里（README 约定每个探测器另提供模块级入口），
    消费方会直接调它们，所以不能只有类能跑。
    """
    _sterile_machine(monkeypatch)
    cls = pt_module.PlatformToolsProber

    items = pt_module.probe()
    _assert_item_shape(cls, items)

    info = pt_module.get_platform_tools_info()
    assert isinstance(info, dict), "get_platform_tools_info() 应返回 dict"
    assert info.get("platform") == sys.platform, \
        "dict 视图的平台标签不对: %r" % (info.get("platform"),)
    features = info.get("features")
    assert isinstance(features, dict) and features, "dict 视图缺 features"
    # 每个条目都必须是「条目名 → 可 JSON 序列化的条目 dict」
    json.dumps(info, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# 2) 跨平台安全：三分支都不许崩
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fake_platform", _ALL_PLATFORMS)
def test_no_crash_on_every_platform(pt_module, monkeypatch, fake_platform):
    """win32 / linux / darwin 三分支在「什么都没有」的机器上都不得抛异常。

    base.run 会兜异常，所以这里除了「不抛」还断言报告里没有崩溃条目
    （见 _assert_item_shape）—— 否则「优雅跳过」会把真实崩溃掩盖成一条 error。
    """
    _sterile_machine(monkeypatch)
    with _platform_context(pt_module, fake_platform) as mod:
        cls = getattr(mod, "PlatformToolsProber", None)
        assert cls is not None, "reload 后丢了 PlatformToolsProber"
        items = cls().run()
        _assert_item_shape(cls, items)


# ---------------------------------------------------------------------------
# 3) 非本源平台：干净机器上不得声称命中
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fake_platform", _ALL_PLATFORMS)
def test_foreign_platform_claims_nothing_on_clean_machine(
        pt_module, monkeypatch, fake_platform):
    """假平台 ≠ 本源平台时，干净机器上任何探测项都不得报 available=True。

    这条专门抓「跨平台分支没短路」：例如在 Windows 上把 sys.platform 骗成
    'linux'，若实现仍去读注册表/固定安装路径，就会把 Windows 的工具报成
    Linux 的能力。本源平台跳过（真机可能确实装了工具，断言不成立）。
    """
    if fake_platform == sys.platform:
        pytest.skip("本源平台（%s）：真机可能确实装了工具，不做「必须不可用」断言"
                    % fake_platform)

    _sterile_machine(monkeypatch)
    with _platform_context(pt_module, fake_platform) as mod:
        cls = getattr(mod, "PlatformToolsProber", None)
        assert cls is not None
        items = cls().run()
        _assert_item_shape(cls, items)

        # 允许「范围/元信息」条目（如 platform_scope）available=True —— 它陈述的是
        # 「本次跑了哪些组、跳过了哪些组」，不是「装了某个工具」。判定：不带任何
        # 工具证据（path/version 皆空）。带证据的可用条目 = 声称装了东西。
        claimed = [(i.name, i.path, i.version) for i in items
                   if i.available and (i.path or i.version)]
        assert not claimed, (
            "在「什么都没有」的机器上把 %s 的能力报成可用（跨平台分支没短路，"
            "或探测没看平台）：%r" % (fake_platform, claimed))

        # 跨平台泄漏：可用条目里不得出现别的平台的独有能力关键词
        foreign_keywords = set()
        for other, keywords in _CAPABILITY_KEYWORDS.items():
            if other != fake_platform:
                foreign_keywords.update(keywords)
        leaked = []
        for item in items:
            if not item.available:
                continue
            blob = _item_blob(item)
            hit = [kw for kw in foreign_keywords if kw in blob]
            if hit:
                leaked.append((item.name, hit))
        assert not leaked, (
            "%s 分支的报告里出现了别的平台的能力（跨平台泄漏）: %r"
            % (fake_platform, leaked))


# ---------------------------------------------------------------------------
# 4) 目标平台：规格要求的能力必须被探测到
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fake_platform", _ALL_PLATFORMS)
def test_target_platform_reports_expected_capabilities(
        pt_module, monkeypatch, fake_platform):
    """目标平台上即使工具全没装，也必须如实报告探测过规格要求的能力。

    非本源平台跳过（那是别的 OS 的分支，不该由本机来源平台断言）。
    关键词在 name/category/path/version/extra 全字段里找，容忍命名差异。
    """
    if fake_platform != sys.platform:
        pytest.skip("非本源平台（%s）：能力覆盖只在目标平台断言" % fake_platform)

    _sterile_machine(monkeypatch)
    with _platform_context(pt_module, fake_platform) as mod:
        cls = getattr(mod, "PlatformToolsProber", None)
        assert cls is not None
        items = cls().run()
        _assert_item_shape(cls, items)

        blob = " ".join(_item_blob(i) for i in items)
        expected = _CAPABILITY_KEYWORDS[fake_platform]
        matched = [kw for kw in expected if kw in blob]
        assert matched, (
            "%s 分支没有探测任何规格要求的能力（关键词 %r 一个都没命中）"
            "；实际条目: %r" % (
                fake_platform, list(expected), [i.name for i in items]))
