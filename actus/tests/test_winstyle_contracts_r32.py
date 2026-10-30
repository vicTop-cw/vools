# -*- coding: utf-8 -*-
"""actus/tests/test_winstyle_contracts_r32.py — `winstyle.round_corners` 契约（0% → 平台分支 + 错误路径）。

被测：`vools/actus/winstyle.py::round_corners(hwnd, radius=24) -> "dwm"|"region"|"none"`。
此前**零覆盖**（模块仅被 `tkdialog.py` 延迟 import），意味着「圆角失败」这条展示性降级路径
从来没有被真正执行过。

审计发现的两条产品 bug（**本轮已批准修复**，产品侧改动见文件末尾「修复对照」）
--------------------------------------------------------------------------
**BUG-A｜no-throw 契约破损（低危，已修）**：模块 docstring 承诺「纯展示性增强：任何失败都不抛异常、
不阻断动作，只降级」，但参数类型非法时在 **`try` 之外**先比较：
``round_corners("abc")`` / ``round_corners([1])`` 抛 ``TypeError``（``'<=' not supported``）。
修法：把入参校验收进 `_should_skip()`（内部 try/except TypeError），非法类型统一收敛成 `"none"`；
``None`` / 0 的 falsy 分支**语义不变**。回归用例：
``TestEarlyReturn::test_non_numeric_hwnd_degrades_to_none``。

**BUG-B｜GDI 句柄泄漏（中危，已修）**：`SetWindowRgn` 返回 0（失败）时系统**不接管** HRGN，
代码直接 ``return "none"`` 而未 ``DeleteObject(hrgn)``。实测 50 次失败调用：
进程 GDI 对象数 **0 → 50**（每次泄漏一个句柄）；长驻 GUI 动作族反复失败会耗尽 GDI 配额（~10k）。
修法：失败分支补 ``gdi32.DeleteObject(hrgn)``（并显式声明 HANDLE argtypes，避免 64 位句柄被截断）；
**成功分支仍然不删**（所有权已移交系统）。回归用例：

* ``TestFailureBranches::test_region_handle_released_on_setwindowrgn_failure``（桩 SetWindowRgn=0 +
  **真** CreateRoundRectRgn → 20 次调用后 **GDI 对象数不变**）；
* ``TestFailureBranches::test_region_handle_not_deleted_on_success``（成功路径**不得** DeleteObject）；
* ``TestFailureBranches::test_region_handle_delete_uses_created_handle``（回滚删的必须是刚建的那个句柄）。

覆盖策略（本机 Windows 11，可真跑）
----------------------------------
* 参数早退 / 非 Windows 降级：纯逻辑，跨平台断言；
* **真实路径**：自建**隐藏**顶层窗口（`CreateWindowExW` + `DestroyWindow`），
  不碰用户桌面上任何真实窗口（实测直接对 `Progman`/任务栏调用也能返回 "dwm"，
  但那会改用户桌面观感，故不用）；
* 失败分支：**只 stub 需要的那一层**（DWM / GDI / user32），其余保持真实调用。

每条 docstring 都写「退步了会怎样」。
"""

import ctypes
import os
import sys

import pytest

_IS_WIN = sys.platform == "win32"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

from vools.actus.winstyle import round_corners  # noqa: E402

if _IS_WIN:  # 仅 Windows 需要结构化类型；非 Windows 上导入会失败，故延迟到分支内
    from ctypes import wintypes  # noqa: F401

win_only = pytest.mark.skipif(
    not _IS_WIN, reason="需要真实 Windows ctypes.windll（非 Windows 走异常降级由其它用例覆盖）")


# ---------------------------------------------------------------------------
# 替身与夹具
# ---------------------------------------------------------------------------

def _fn(result=None, behavior=None):
    """ctypes 函数的替身：支持 `.argtypes/.restype` 赋值（被测代码会设）并记录调用。"""
    class _Fn(object):
        def __init__(self):
            self.argtypes = None
            self.restype = None
            self.calls = []

        def __call__(self, *args):
            self.calls.append(args)
            if behavior is not None:
                return behavior(*args)
            return result

    return _Fn()


def _lib(**funcs):
    """DLL 替身：把名字绑成给定函数对象（`ctypes.windll.<name>` 的等价物）。"""
    class _Lib(object):
        def __init__(self):
            self.__dict__.update(funcs)

    return _Lib()


def _gdi(create_result=1234, delete_result=1, **overrides):
    """gdi32 替身：默认同时提供 `CreateRoundRectRgn` 与 `DeleteObject`。

    为什么必须带 DeleteObject：产品在失败分支会回滚句柄（BUG-B 修复），
    若替身缺这个符号，失败会变成 AttributeError 被外层兜底成 "none" ——
    断言仍"绿"，但测的根本不是目标分支（假的通过）。
    """
    funcs = {
        "CreateRoundRectRgn": _fn(create_result),
        "DeleteObject": _fn(delete_result),
    }
    funcs.update(overrides)
    return _lib(**funcs)


def _install_libs(monkeypatch, dwm=None, user32=None, gdi32=None):
    """只替换传入的那几层 DLL；其余保持真实（失败分支测试的关键：别把整条链都 stub 掉）。"""
    for name, lib in (("dwmapi", dwm), ("user32", user32), ("gdi32", gdi32)):
        if lib is not None:
            monkeypatch.setattr(ctypes.windll, name, lib, raising=False)


def _rect_filler(width, height):
    """GetWindowRect 替身：把 byref 的 RECT 写成指定尺寸并返回成功。"""
    def behavior(hwnd, pointer):
        rect = ctypes.cast(pointer, ctypes.POINTER(wintypes.RECT)).contents
        rect.left, rect.top = 0, 0
        rect.right, rect.bottom = width, height
        return 1

    return behavior


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """全部隔离：ACTUS_REPO_ROOT / ACTUS_META_DIR / HOME 指 tmp，并 chdir 到 tmp。

    winstyle 本身不读写文件，钉死是防御性的：将来若加入缓存/配置读取，
    没有隔离就会写到真实 `~/.actus` 或真实仓库（历史上有测试污染过真实 `~/.actus`）。
    """
    for name in ("repo", "meta", "home"):
        (tmp_path / name).mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ACTUS_REPO_ROOT", str(tmp_path / "repo"))
    monkeypatch.setenv("ACTUS_META_DIR", str(tmp_path / "meta"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    return tmp_path


@pytest.fixture
def hidden_window():
    """自建一个**隐藏**顶层窗口（STATIC 类，200×120），用完立即销毁。

    为什么不复用桌面已有窗口：对 `Progman`/任务栏调用会真的改用户桌面观感
    （实测能成功返回 "dwm"），测试不该有这种副作用。
    """
    if not _IS_WIN:
        pytest.skip("Windows 专有")
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.CreateWindowExW.argtypes = (
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
    )
    user32.DestroyWindow.argtypes = (wintypes.HWND,)
    hwnd = user32.CreateWindowExW(
        0, "STATIC", "winstyle-contract-r32", 0, 10, 10, 200, 120,
        None, None, kernel32.GetModuleHandleW(None), None)
    assert hwnd, "CreateWindowExW 失败，无法做真实路径验证"
    try:
        yield hwnd
    finally:
        user32.DestroyWindow(hwnd)


# ---------------------------------------------------------------------------
# 1) 参数早退：非法入参直接 "none"，且**不碰系统 API**
# ---------------------------------------------------------------------------

class TestEarlyReturn:
    def test_invalid_hwnd_returns_none(self, monkeypatch):
        """hwnd 为 0 / 负数 / None → "none"，且**一次系统 API 都不调**。

        为什么必须桩一个「DWM 会成功」的假 DLL：否则非法 hwnd 在真实环境里本来就会
        在后续 GetWindowRect 失败处收敛成 "none"，断言"等于 none"根本抓不到早退缺失。
        桩掉 DWM 后，「有没有早退」就等价于「DWM 有没有被调用」。

        退步了会怎样：拿非法句柄继续走 Win32 路径 —— 轻则多一次无意义系统调用，
        重则把**同号的其他内核对象**（事件/文件句柄）当窗口去设置区域。
        """
        if _IS_WIN:
            dwm = _lib(DwmSetWindowAttribute=_fn(0))
            _install_libs(monkeypatch, dwm=dwm)
            for bad in (0, -1, -999, None):
                assert round_corners(bad) == "none", "hwnd=%r 必须直接降级" % (bad,)
            assert dwm.DwmSetWindowAttribute.calls == [], "非法 hwnd 不得调用 DWM"
        else:  # 非 Windows：走异常降级，同样必须 "none"
            for bad in (0, -1, -999, None):
                assert round_corners(bad) == "none", "hwnd=%r 必须直接降级" % (bad,)

    def test_non_positive_radius_returns_none(self, monkeypatch):
        """radius<=0 → "none"，且**不去建区域、不调 DWM**。

        同样桩一个「DWM 会成功」的假 DLL：否则「radius=0 时返回 none」可能只是
        hwnd 本身非法导致的后续失败，测不出早退。

        退步了会怎样：0/负半径被交给 CreateRoundRectRgn，要么建区失败（句柄为 0），
        要么画出畸形区域把方角窗口啃掉一块；若 DWM 分支先命中，则半径校验形同虚设。
        """
        if _IS_WIN:
            dwm = _lib(DwmSetWindowAttribute=_fn(0))
            gdi = _gdi()
            _install_libs(monkeypatch, dwm=dwm, gdi32=gdi)
            for radius in (0, -1, -24):
                assert round_corners(0x1234, radius=radius) == "none"
            assert dwm.DwmSetWindowAttribute.calls == [], "radius<=0 时不得调 DWM"
            assert gdi.CreateRoundRectRgn.calls == [], "radius<=0 时不得建区域"
        else:
            for radius in (0, -1, -24):
                assert round_corners(0x1234, radius=radius) == "none"

    def test_bool_hwnd_is_treated_as_int(self, monkeypatch):
        """True（int 子类）按 1 处理 → 不早退，走到真实探测（假 DWM 成功则返回 "dwm"）。

        桩 DWM 成功后可以区分两件事：「True 被当成 1 继续走」vs「类型严格化把 bool 拒了」。
        若实现改成 `type(hwnd) is int`，bool 会被判非法 → 返回 "none"，本断言红。

        退步了会怎样：类型判断过严会让合法 bool（某些 API 返回 BOOL）在 **try 之外**
        抛异常或静默降级，违反模块「任何失败都不抛」的承诺（见 BUG-A 同族）。
        """
        if _IS_WIN:
            _install_libs(monkeypatch, dwm=_lib(DwmSetWindowAttribute=_fn(0)))
            assert round_corners(True) == "dwm", "True 应被当成 hwnd=1 继续走"
        else:
            assert round_corners(True) in ("dwm", "region", "none")

    def test_isolated_environment(self, isolated_env):
        """隔离契约：三个根都在 tmp 下。

        退步了会怎样：未来 winstyle 若引入配置/缓存读写，没有隔离会写到真实
        `~/.actus` 或真实仓库（本仓库历史上被测试污染过真实 `~/.actus`）。
        """
        for name in ("ACTUS_REPO_ROOT", "ACTUS_META_DIR", "HOME", "USERPROFILE"):
            value = os.environ.get(name, "")
            assert value and value.startswith(str(isolated_env)), (
                "%s 未隔离到 tmp: %r" % (name, value))


# ---------------------------------------------------------------------------
# 2) 非 Windows 降级：平台 API 不可用 → 明确 "none"，不静默崩溃
# ---------------------------------------------------------------------------

class TestNonWindowsDegrade:
    def test_missing_windll_degrades_to_none(self, monkeypatch):
        """模拟 Linux 形态（`ctypes.windll` 不存在）→ "none"，不抛。

        退步了会怎样：一旦有人把 `import ctypes` 提到模块顶部并在**导入期**访问
        `ctypes.windll`，非 Windows 上 import 就炸 —— 整个 GUI 动作族（toast/dialog）
        连带不可用，而不是「圆角降级成方角」。
        """
        monkeypatch.delattr(ctypes, "windll", raising=False)
        assert round_corners(0x1234) == "none"

    def test_dll_load_failure_degrades_to_none(self, monkeypatch):
        """DLL 加载抛 OSError（缺 dwmapi.dll / 受限策略）→ "none"，不抛。

        退步了会怎样：异常穿出会让一次「给窗口加圆角」把整个动作用途中止
        —— 展示性增强反而打断功能。
        """
        class _Loader(object):
            def __getattr__(self, name):
                raise OSError("模拟 DLL 不可用: %s" % name)

        monkeypatch.setattr(ctypes, "windll", _Loader())
        assert round_corners(0x1234) == "none"

    def test_bogus_handle_degrades_to_none(self):
        """一个不存在的 hwnd：DWM 拒绝 + GetWindowRect 失败 → "none"（真实调用）。

        退步了会怎样：把 DWM 的非零 HRESULT 当成功，会返回 "dwm" 而窗口实际是方角
        —— 调用方（tkdialog）据此出参标注「已圆角」，属假成功。
        """
        assert round_corners(0x1234) == "none"


# ---------------------------------------------------------------------------
# 3) 真实 Windows 路径（真 DWM / 真 GDI，自建隐藏窗口）
# ---------------------------------------------------------------------------

@win_only
class TestRealWindowsPath:
    def test_real_window_gets_rounded(self, hidden_window):
        """真实窗口必须拿到 "dwm"（Win11 22000+）或 "region"（旧系统回退），绝不能 "none"。

        退步了会怎样：真实窗口拿不到任何圆角 → 所有 GUI 动作静默变方角，
        而报告里仍是「成功」（无人察觉的展示性回归）。
        """
        result = round_corners(hidden_window)
        build = sys.getwindowsversion().build
        if build >= 22000:
            assert result == "dwm", "Win11 应走 DWM 系统圆角，实得 %r" % (result,)
        else:
            assert result == "region", "旧系统应回退 GDI 区域，实得 %r" % (result,)

    def test_radius_boundary_still_attempts(self, hidden_window):
        """radius=1 是合法下限：必须真的尝试（不能因边界判断写错而早退成 "none"）。

        退步了会怎样：把 `radius <= 0` 误写成 `radius < 24` 之类的比较，
        小半径调用会被当成非法直接降级 —— 而调用方以为只是「圆角小一点」。
        """
        result = round_corners(hidden_window, radius=1)
        assert result in ("dwm", "region"), "radius=1 应真的尝试圆角，实得 %r" % (result,)

    def test_dwm_failure_falls_back_to_region(self, hidden_window, monkeypatch):
        """DWM 不可用（非零 HRESULT）时，用**真实 GDI** 回退 "region"。

        退步了会怎样：把 DWM 失败当成「没救了直接 none」，Win10 用户永远拿不到圆角；
        或反之在 DWM 失败后不再校验 SetWindowRgn 返回值，谎报 "region"。
        """
        _install_libs(monkeypatch, dwm=_lib(DwmSetWindowAttribute=_fn(1)))
        result = round_corners(hidden_window)
        assert result == "region", "DWM 失败应回退 GDI 区域，实得 %r" % (result,)


# ---------------------------------------------------------------------------
# 4) 失败分支：只 stub 出问题的那一层，验证「明确降级 + 不谎报」
# ---------------------------------------------------------------------------

class TestFailureBranches:
    def test_dwm_exception_degrades_to_none(self, monkeypatch):
        """DWM 调用**抛异常** → "none"（异常被兜底，不外泄）。

        退步了会怎样：去掉外层 try/except 后，一次 DWM 异常会让 tkdialog 的
        `_round_corners` 调用点炸掉，进而打断对话框创建。
        """
        def boom(*args, **kwargs):
            raise RuntimeError("模拟 DWM 崩溃")

        _install_libs(monkeypatch, dwm=_lib(DwmSetWindowAttribute=_fn(behavior=boom)))
        assert round_corners(0x1234) == "none"

    def test_rect_query_failure_returns_none(self, monkeypatch):
        """DWM 失败 + GetWindowRect 失败 → "none"，且**不去建区域**。

        退步了会怎样：在拿不到窗口尺寸时继续 CreateRoundRectRgn，
        会用一个垃圾尺寸裁窗口（可能整窗不可见）。
        """
        set_rgn = _fn(1)
        gdi = _gdi()
        user32 = _lib(GetWindowRect=_fn(0), SetWindowRgn=set_rgn)
        _install_libs(monkeypatch, dwm=_lib(DwmSetWindowAttribute=_fn(1)),
                      user32=user32, gdi32=gdi)
        assert round_corners(0x1234) == "none"
        assert gdi.CreateRoundRectRgn.calls == [], "尺寸未知时不应建区域"
        assert set_rgn.calls == [], "尺寸未知时不应设置区域"

    def test_zero_sized_window_returns_none(self, monkeypatch):
        """窗口尺寸为 0（RECT 全 0）→ "none"。

        退步了会怎样：用 0×0 尺寸建区域并 SetWindowRgn，窗口被裁成不可见。
        """
        gdi = _gdi()
        user32 = _lib(GetWindowRect=_fn(behavior=_rect_filler(0, 0)),
                      SetWindowRgn=_fn(1))
        _install_libs(monkeypatch, dwm=_lib(DwmSetWindowAttribute=_fn(1)),
                      user32=user32, gdi32=gdi)
        assert round_corners(0x1234) == "none"
        assert gdi.CreateRoundRectRgn.calls == [], "0 尺寸窗口不应建区域"

    def test_region_creation_failure_returns_none(self, monkeypatch):
        """CreateRoundRectRgn 返回 0（GDI 资源耗尽）→ "none"，不把 0 当句柄传给系统。

        退步了会怎样：把 NULL 区域交给 SetWindowRgn，等于「无区域」，
        语义上会**取消**已有圆角，且可能失败返回 False（调用方误判）。
        """
        set_rgn = _fn(1)
        _install_libs(monkeypatch, dwm=_lib(DwmSetWindowAttribute=_fn(1)),
                      user32=_lib(GetWindowRect=_fn(behavior=_rect_filler(200, 120)),
                                  SetWindowRgn=set_rgn),
                      gdi32=_gdi(create_result=0))
        assert round_corners(0x1234) == "none"
        assert set_rgn.calls == [], "句柄为 0 时不应调用 SetWindowRgn"

    def test_setwindowrgn_failure_returns_none(self, monkeypatch):
        """SetWindowRgn 返回 0（失败）→ "none"，**不谎报 "region"**。

        退步了会怎样：不校验返回值就返回 "region"，调用方据此标注「已圆角」，
        而窗口实际还是方角 —— 与 BUG-A 同类的「出参不诚实」。
        """
        _install_libs(monkeypatch, dwm=_lib(DwmSetWindowAttribute=_fn(1)),
                      user32=_lib(GetWindowRect=_fn(behavior=_rect_filler(200, 120)),
                                  SetWindowRgn=_fn(0)),
                      gdi32=_gdi())
        assert round_corners(0x1234) == "none"

    def test_region_arguments_cover_full_window(self, monkeypatch):
        """建区域参数必须是 ``(0, 0, w+1, h+1, radius, radius)``。

        退步了会怎样：用 `w, h` 而不是 `w+1, h+1`，窗口最右/最下一列像素落在区域外被裁掉
        （1px 缺边的经典 off-by-one）。
        """
        gdi = _gdi()
        _install_libs(monkeypatch, dwm=_lib(DwmSetWindowAttribute=_fn(1)),
                      user32=_lib(GetWindowRect=_fn(behavior=_rect_filler(200, 120)),
                                  SetWindowRgn=_fn(1)),
                      gdi32=gdi)
        assert round_corners(0x1234, radius=24) == "region"
        assert gdi.CreateRoundRectRgn.calls == [(0, 0, 201, 121, 24, 24)], (
            "区域参数不对: %r" % (gdi.CreateRoundRectRgn.calls,))


# ---------------------------------------------------------------------------
# 5) 两个已修 bug 的回归（原为 strict xfail；产品修复后转为真断言）
# ---------------------------------------------------------------------------

class TestBugRegressions:
    def test_non_numeric_hwnd_degrades_to_none(self):
        """BUG-A 回归：非数值 hwnd 必须降级 `"none"`，**不抛**（模块承诺 no-throw）。

        退步了会怎样：把入参校验从 `_should_skip()` 的 try 里挪出来（或改回裸比较），
        `round_corners("abc")` 会抛 TypeError —— 一次给窗口加圆角就能打断
        toast/dialog 动作，而模块文档明确承诺「不阻断动作」。
        """
        for bad in ("abc", [1], {"x": 1}):
            assert round_corners(bad) == "none", "hwnd=%r 必须降级而不是抛" % (bad,)

    def test_non_numeric_radius_degrades_to_none(self):
        """BUG-A 回归：非数值 radius 同样只降级、不抛。

        退步了会怎样：radius 走 `radius <= 0` 比较，传字符串抛 TypeError；
        半径是可选参数，调用方传错类型不该让整个动作失败。
        """
        assert round_corners(0x1234, radius="x") == "none"

    def test_none_and_zero_still_degrade_normally(self):
        """BUG-A 修复**不得改坏**既有 falsy 分支：None / 0 / False → "none"（不抛、不探测）。

        退步了会怎样：若把校验改成 `isinstance(hwnd, int) and hwnd > 0` 之类，
        None 会被送去 Win32 调用（或抛异常）—— 反而破坏了原本正确的降级路径。
        """
        for falsy in (None, 0, False):
            assert round_corners(falsy) == "none"

    def test_region_handle_released_on_setwindowrgn_failure(self, hidden_window, monkeypatch):
        """BUG-B 回归：`SetWindowRgn` 失败时必须 `DeleteObject`，**GDI 对象数不变**。

        用**真** `CreateRoundRectRgn`（真的分配 HRGN）+ 桩 `SetWindowRgn=0`，
        连续 20 次失败调用后比较进程 GDI 对象数。

        退步了会怎样：去掉失败分支的 DeleteObject，每次失败泄漏一个 GDI 句柄
        （实测 20 次 → +20；默认 ~10k 配额，长驻动作族反复失败会耗尽 → 后续 GDI 调用全线失败）。
        """
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        user32.GetGuiResources.restype = ctypes.c_ulong
        user32.GetGuiResources.argtypes = (wintypes.HANDLE, ctypes.c_ulong)

        _install_libs(monkeypatch, dwm=_lib(DwmSetWindowAttribute=_fn(1)),
                      user32=_lib(GetWindowRect=_fn(behavior=_rect_filler(200, 120)),
                                  SetWindowRgn=_fn(0)))
        # 注意：gdi32 保持真实 —— 要真的建 HRGN，才能观察到它有没有被释放
        process = kernel32.GetCurrentProcess()
        before = user32.GetGuiResources(process, 0)
        for _ in range(20):
            assert round_corners(hidden_window) == "none"
        after = user32.GetGuiResources(process, 0)
        assert after == before, "失败路径泄漏了 %d 个 GDI 句柄" % (after - before,)

    def test_region_handle_delete_uses_created_handle(self, monkeypatch):
        """BUG-B 回归：回滚时删的必须是**刚建出来的那个** HRGN（不是别的值/不是空）。

        退步了会怎样：删错句柄（或删 0）等于没回滚 —— 泄漏照旧，还可能误删别的 GDI 对象，
        表现是「修了但没修好」，且没有断言能发现。
        """
        gdi = _gdi(create_result=4321)
        _install_libs(monkeypatch, dwm=_lib(DwmSetWindowAttribute=_fn(1)),
                      user32=_lib(GetWindowRect=_fn(behavior=_rect_filler(200, 120)),
                                  SetWindowRgn=_fn(0)),
                      gdi32=gdi)
        assert round_corners(0x1234) == "none"
        assert gdi.DeleteObject.calls == [(4321,)], (
            "失败回滚应删除刚创建的 HRGN(4321)，实得 %r" % (gdi.DeleteObject.calls,))

    def test_region_handle_not_deleted_on_success(self, monkeypatch):
        """BUG-B 对偶契约：`SetWindowRgn` 成功时**不得** DeleteObject（所有权已移交系统）。

        退步了会怎样：成功路径也删除句柄，会释放一个**系统正在用于裁剪窗口**的区域 →
        窗口裁剪失效（方角/花屏）甚至进程崩溃（使用已释放的 GDI 对象）。
        """
        gdi = _gdi(create_result=4321)
        _install_libs(monkeypatch, dwm=_lib(DwmSetWindowAttribute=_fn(1)),
                      user32=_lib(GetWindowRect=_fn(behavior=_rect_filler(200, 120)),
                                  SetWindowRgn=_fn(1)),
                      gdi32=gdi)
        assert round_corners(0x1234) == "region"
        assert gdi.DeleteObject.calls == [], (
            "成功路径不得 DeleteObject（所有权已移交系统），实得 %r"
            % (gdi.DeleteObject.calls,))
