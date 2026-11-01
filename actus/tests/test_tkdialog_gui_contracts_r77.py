# -*- coding: utf-8 -*-
"""tkdialog GUI 层契约测试（Round 70）。

headless 模式：ACTUS_DIALOG_HEADLESS=1 —— 真建控件、真跑倒计时/collect/validate，
只是不把窗口映射到屏幕。共享一个会话级 Tk root（tk._actus_dialog_root 注入）。

关键机制：run_modal 开头 _reset_root_state 会取消所有 pending after，
所以外部预调度的 after 会被清掉 —— 必须通过包装 td.run_modal 把驱动
（点击/事件注入）塞进 build_body 生命周期内再调度。

BUG-T1（critical，佐证未修）：do_confirm (tkdialog.py:284) 调
finish("confirm")，finish(:288) 又调 do_confirm —— 无限互递归。
所有确认路径（按钮/Enter/Esc-alert/Ctrl+Return）触发 RecursionError：
- invoke 驱动：异常同步冲出 invoke；
- event_generate 驱动：异常走 Tcl 后台错误（stderr）。
两种情况下 mainloop 都继续跑 → 弹窗卡到超时。timeout_confirm /
timeout_cancel / blur_cancel / 取消按钮 / Esc(有取消钮) 不经过该路径，正常。
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import _ai_local_bootstrap  # noqa: F401  必须在 vools 之前

import tkinter as tk

import vools.actus.tkdialog as td


@pytest.fixture(scope="module")
def tk_root():
    """会话级共享 root：Store Python 沙箱下第二个真 Tk() 会卡死 mainloop
    （init.tcl 重读问题），故全程复用一个——优先 tk 缓存，其次复用本进程
    已存在的 _default_root（panel 测试先跑时留下的），最后才新建。"""
    for cand in (getattr(tk, "_actus_dialog_root", None),
                 getattr(tk, "_default_root", None)):
        if cand is not None:
            try:
                if cand.winfo_exists():
                    tk._actus_dialog_root = cand
                    yield cand
                    return
            except tk.TclError:
                pass
    root = tk.Tk()
    root.withdraw()
    tk._actus_dialog_root = root
    yield root
    # 不 unset 缓存、不 destroy：后续模块的 run_modal 复用同一 root，
    # 避免本会话内出现第二个真 Tk。


@pytest.fixture(autouse=True)
def _env(monkeypatch, tk_root):
    monkeypatch.setenv("ACTUS_DIALOG_HEADLESS", "1")
    monkeypatch.setenv("NO_PROMPT", "1")
    tk._actus_dialog_root = tk_root       # _get_root 直接命中缓存
    yield tk_root
    for w in tk_root.winfo_children():    # 排空残留控件
        w.destroy()


def _with_driver(monkeypatch, root, driver, delay=150):
    """包装 td.run_modal：把 driver(root) 的调度注入 build_body 内
    （build_body 在 _reset_root_state 之后执行，after 才能存活）。"""
    orig = td.run_modal

    def wrapped(message, focus_policy, timeout_seconds, kind, title,
                width, confirm_text, cancel_text, build_body, **kw):
        def bb(ctx):
            root.after(delay, lambda: driver(root))
            return build_body(ctx)
        return orig(message, focus_policy, timeout_seconds, kind, title,
                    width, confirm_text, cancel_text, bb, **kw)

    monkeypatch.setattr(td, "run_modal", wrapped)


def _find_widgets(widget, cls, text=None):
    """BFS 收集 cls 类型（可选按 text 过滤 Button）的子控件。"""
    found = []
    for w in widget.winfo_children():
        if isinstance(w, cls):
            if text is None or (hasattr(w, "cget") and _text_of(w) == text):
                found.append(w)
        found.extend(_find_widgets(w, cls, text))
    return found


def _text_of(w):
    try:
        return w.cget("text")
    except Exception:
        return ""


def _click_cancel(root):
    btns = _find_widgets(root, tk.Button, "取消")
    assert btns, "找不到取消按钮"
    btns[0].invoke()


class TestBugT1ConfirmPath:
    """BUG-T1：确认路径 do_confirm↔finish 无限互递归（佐证现状）。

    按钮命令由 Tk 回调执行：RecursionError 走 Tcl bgerror（stderr），
    invoke() 正常返回；mainloop 不中断 → 弹窗保持打开直到超时/取消。
    """

    def test_confirm_button_recurses(self, tk_root, monkeypatch):
        def _driver(r):
            try:
                _find_widgets(r, tk.Button, "确认")[0].invoke()
            except RecursionError:
                pass  # 递归耗尽深度可能同步冲出 invoke（深度时刻不定），弹窗仍未关
            _click_cancel(r)               # 弹窗未关，补一刀取消
        _with_driver(monkeypatch, tk_root, _driver)
        r = td.run_dialog("确认吗？", "locked", timeout_seconds=4)
        assert r["clicked"] == "cancel"    # 确认从未生效（递归走 Tcl bgerror）
        # 不断言 value is None：T1 bug 的无限互递归中 collect()=True 可能在
        # 深度耗尽前已执行（递归深度耗尽点非确定，--cov 追踪帧会改变落点，
        # 见窗口复跑），value=True 只是 bug 残留不是确认生效——生效与否以
        # clicked（弹窗以哪个按钮收场）为准。

    def test_enter_key_recurses(self, tk_root, monkeypatch):
        def _driver(r):
            r.event_generate("<Return>")   # 递归异常走 Tcl 后台错误
            _click_cancel(r)
        _with_driver(monkeypatch, tk_root, _driver)
        r = td.run_dialog("确认吗？", "locked", timeout_seconds=4)
        assert r["clicked"] == "cancel"

    def test_alert_escape_recurses_and_stuck(self, tk_root, monkeypatch):
        def _driver(r):
            r.event_generate("<Escape>")   # show_cancel=False → Esc=确认 → 递归
            # alert 无取消钮：无法补救 → 只能等超时（弹窗卡死佐证）
        _with_driver(monkeypatch, tk_root, _driver)
        r = td.run_dialog("知悉", "locked", timeout_seconds=1, show_cancel=False)
        assert r["clicked"] == "timeout_cancel"

    def test_ctrl_return_recurses(self, tk_root, monkeypatch):
        def _driver(r):
            r.event_generate("<Control-Return>")
            _click_cancel(r)
        _with_driver(monkeypatch, tk_root, _driver)
        r = td.run_text("多行", multiline=True, timeout_seconds=4)
        assert r["clicked"] == "cancel"


class TestHelpers:
    def test_screen_hidden_env_matrix(self, monkeypatch):
        for v in ("1", "true", "yes", "on", "TRUE"):
            monkeypatch.setenv("ACTUS_DIALOG_HEADLESS", v)
            assert td._screen_hidden() is True
        monkeypatch.setenv("ACTUS_DIALOG_HEADLESS", "0")
        assert td._screen_hidden() is False
        monkeypatch.delenv("ACTUS_DIALOG_HEADLESS")
        assert td._screen_hidden() is False

    def test_resolve_focus_poll(self, monkeypatch):
        assert td._resolve_focus_poll(30) == 50            # 下限钳 50
        assert td._resolve_focus_poll(500) == 500          # 显式参数直通
        monkeypatch.setenv("ACTUS_DIALOG_FOCUS_POLL_MS", "250")
        assert td._resolve_focus_poll() == 250             # env 次之
        monkeypatch.setenv("ACTUS_DIALOG_FOCUS_POLL_MS", "abc")
        assert td._resolve_focus_poll() == 400             # 坏 env 回默认
        monkeypatch.delenv("ACTUS_DIALOG_FOCUS_POLL_MS")
        assert td._resolve_focus_poll() == 400             # 缺省 400

    def test_get_root_reuses_and_recovers(self, tk_root):
        assert td._get_root() is tk_root                   # 缓存命中
        dead = tk.Tk()
        dead.withdraw()
        dead.destroy()                                     # 摧毁后 winfo_exists→False
        tk._actus_dialog_root = dead
        r2 = td._get_root()
        assert r2 is not dead and r2.winfo_exists()        # 重建并替换缓存
        tk._actus_dialog_root = tk_root

    def test_reset_root_state(self, tk_root):
        tk_root.bind("<Return>", lambda e: None)
        aid = tk_root.after(9999, lambda: None)
        fr = tk.Frame(tk_root)
        fr.pack()
        td._reset_root_state(tk_root)
        assert not fr.winfo_exists()                       # 子控件销毁
        assert str(aid) not in tk_root.tk.call("after", "info")   # after 清空
        assert tk_root.bind("<Return>") in ("", ())        # 键绑定解除

    def test_ctx_flash_and_reflash(self, tk_root):
        var, status = tk.StringVar(value=""), tk.StringVar(value="")
        ctx = td._Ctx(tk_root, None, var, status)
        ctx.flash("第一条")
        assert status.get() == "第一条"
        assert ctx._flash_after is not None
        ctx.flash("第二条")                                # 走 after_cancel 分支
        assert status.get() == "第二条"
        tk_root.after_cancel(ctx._flash_after)             # 清场

    def test_validate_error_short_circuit(self):
        r = td.run_modal("msg", "locked", None, "bogus-kind", "t",
                         560, "确", "取", lambda ctx: (lambda: None, lambda: None))
        assert r["clicked"] == "error" and r["value"] is None
        assert r["message"]


class TestWorkingPaths:
    """不经过 BUG-T1 路径的：取消 / 超时 / blur / 非模态。"""

    def test_escape_cancels(self, tk_root, monkeypatch):
        _with_driver(monkeypatch, tk_root,
                     lambda r: r.event_generate("<Escape>"))
        r = td.run_dialog("确认吗？", "locked", timeout_seconds=3)
        assert r["clicked"] == "cancel" and r["value"] is None

    def test_cancel_button(self, tk_root, monkeypatch):
        _with_driver(monkeypatch, tk_root, _click_cancel)
        r = td.run_dialog("确认吗？", "locked", timeout_seconds=3)
        assert r["clicked"] == "cancel" and r["value"] is None

    def test_timeout_cancel(self, tk_root):
        r = td.run_dialog("确认吗？", "locked", timeout_seconds=1)
        assert r["clicked"] == "timeout_cancel" and r["value"] is None

    def test_timeout_confirm(self, tk_root):
        r = td.run_dialog("确认吗？", "timeout_confirm", timeout_seconds=1)
        assert r["clicked"] == "timeout_confirm" and r["value"] is True

    def test_blur_cancel_event(self, tk_root, monkeypatch):
        _with_driver(monkeypatch, tk_root,
                     lambda r: r.event_generate("<FocusOut>"))
        r = td.run_modal("m", "blur_cancel", 3, "info", "t", 560,
                         "确认", "取消",
                         lambda ctx: (lambda: None, lambda: None))
        assert r["clicked"] == "blur_cancel"

    def test_nonmodal_timeout_and_fade(self, tk_root):
        r = td.run_modal("m", "locked", 1, "info", "t", 560, "确认", "取消",
                         lambda ctx: (lambda: None, lambda: None),
                         modal=False)
        assert r["clicked"] == "timeout_cancel"
        assert r["elapsed_ms"] >= 900


class TestWidgetsAndValidators:
    """控件构建/占位/校验拦截/collect 语义（确认动作本身见 BUG-T1）。"""

    def test_single_select_validate_blocks_empty(self, tk_root, monkeypatch):
        def _driver(r):
            btn = _find_widgets(r, tk.Button, "确认")[0]
            btn.invoke()                   # 未选 → validate 拦截 + flash（不 finish）
            btn.invoke()                   # 二次 → after_cancel 分支
            _click_cancel(r)
        _with_driver(monkeypatch, tk_root, _driver)
        r = td.run_single("选一个", ["a", "b"], timeout_seconds=4)
        assert r["clicked"] == "cancel" and r["value"] is None

    def test_radiobuttons_built(self, tk_root, monkeypatch):
        def _driver(r):
            rbs = _find_widgets(r, tk.Radiobutton)
            assert len(rbs) == 3
            rbs[1].invoke()                # 选中第二项（var 更新）
            _click_cancel(r)
        _with_driver(monkeypatch, tk_root, _driver)
        r = td.run_single("选一个", ["a", "b", "c"], timeout_seconds=4)
        assert r["clicked"] == "cancel"

    def test_default_preselected_and_timeout_collect(self, tk_root):
        r = td.run_single("选一个", ["x", "y"], default="y",
                          focus_policy="timeout_confirm", timeout_seconds=1)
        assert r["clicked"] == "timeout_confirm" and r["value"] == "y"

    def test_checkboxes_collect_via_timeout(self, tk_root, monkeypatch):
        def _driver(r):
            cbs = _find_widgets(r, tk.Checkbutton)
            assert len(cbs) == 3
            cbs[0].invoke(); cbs[2].invoke()
            # 不点确认（BUG-T1）——用 timeout_confirm 收集当前值
        _with_driver(monkeypatch, tk_root, _driver)
        r = td.run_multi("多选", ["m1", "m2", "m3"],
                         focus_policy="timeout_confirm", timeout_seconds=1)
        assert r["clicked"] == "timeout_confirm" and r["value"] == ["m1", "m3"]

    def test_empty_selection_returns_empty_list(self, tk_root):
        r = td.run_multi("多选", ["m1", "m2"],
                         focus_policy="timeout_confirm", timeout_seconds=1)
        assert r["clicked"] == "timeout_confirm" and r["value"] == []

    def test_defaults_checked(self, tk_root):
        r = td.run_multi("多选", ["m1", "m2"], defaults=["m2"],
                         focus_policy="timeout_confirm", timeout_seconds=1)
        assert r["value"] == ["m2"]

    def test_entry_typing_and_placeholder_lifecycle(self, tk_root, monkeypatch):
        def _driver(r):
            entry = _find_widgets(r, tk.Entry)[0]
            assert entry.get() == "your name"              # 占位已插入
            assert entry.bind("<FocusIn>")                 # 聚焦清空/失焦回填处理已挂
            assert entry.bind("<FocusOut>")
            # withdrawn 窗口不投递合成 Focus 事件 → handler 走不到；
            # ph_on=True ⇒ collect 恒 ''（占位即空值语义）
        _with_driver(monkeypatch, tk_root, _driver)
        r = td.run_text("输入", placeholder="your name",
                        focus_policy="timeout_confirm", timeout_seconds=1)
        assert r["clicked"] == "timeout_confirm" and r["value"] == ""

    def test_password_masked_and_default(self, tk_root, monkeypatch):
        def _driver(r):
            entry = _find_widgets(r, tk.Entry)[0]
            assert entry.cget("show") == "•"               # 掩码
        _with_driver(monkeypatch, tk_root, _driver)
        r = td.run_text("口令", default="s3cret", password=True,
                        focus_policy="timeout_confirm", timeout_seconds=1)
        assert r["clicked"] == "timeout_confirm" and r["value"] == "s3cret"

    def test_multiline_return_breaks_insert(self, tk_root, monkeypatch):
        def _driver(r):
            txt = _find_widgets(r, tk.Text)[0]
            txt.insert("1.0", "line1")
            txt.event_generate("<Return>")                 # 绑定 return 'break'
            assert txt.get("1.0", "end-1c") == "line1"     # 未插入换行
        _with_driver(monkeypatch, tk_root, _driver)
        r = td.run_text("多行", multiline=True,
                        focus_policy="timeout_confirm", timeout_seconds=1)
        assert r["clicked"] == "timeout_confirm" and r["value"] == "line1"

    def test_multiline_timeout_collect(self, tk_root):
        r = td.run_text("多行", multiline=True, default="abc",
                        focus_policy="timeout_confirm", timeout_seconds=1)
        assert r["clicked"] == "timeout_confirm" and r["value"] == "abc"

    def test_form_widgets_collect_via_timeout(self, tk_root, monkeypatch):
        import tkinter.ttk as ttk
        fields = [
            {"key": "name", "label": "姓名", "type": "text", "required": True},
            {"key": "pw", "label": "口令", "type": "password"},
            {"key": "env", "label": "环境", "type": "select",
             "options": ["dev", "prod"], "default": "dev"},
            {"key": "ok", "label": "同意", "type": "checkbox", "default": True},
            {"key": "note", "label": "备注", "type": "textarea", "default": "hi"},
        ]

        def _driver(r):
            entries = _find_widgets(r, tk.Entry)
            entries[0].insert(0, "张三")                            # 第一个 Entry=姓名
            cbs = _find_widgets(r, ttk.Combobox)
            assert cbs and cbs[0].get() == "dev"                    # select 默认值
            cbs[0].set("prod")
            _find_widgets(r, tk.Checkbutton)[0].invoke()            # True→False
        _with_driver(monkeypatch, tk_root, _driver)
        r = td.run_form("表单", fields,
                        focus_policy="timeout_confirm", timeout_seconds=1)
        assert r["clicked"] == "timeout_confirm"
        assert r["value"]["name"] == "张三"
        assert r["value"]["pw"] == ""                               # password 空串
        assert r["value"]["env"] == "prod"
        assert r["value"]["ok"] is False                            # checkbox 已切换
        assert r["value"]["note"] == "hi"                           # textarea 默认

    def test_form_required_blocks_confirm_with_flash(self, tk_root, monkeypatch):
        fields = [{"key": "name", "label": "姓名", "type": "text",
                   "required": True}]

        def _driver(r):
            btn = _find_widgets(r, tk.Button, "确认")[0]
            btn.invoke()                   # 必填空 → validate 拦截 + flash（不 finish）
            btn.invoke()                   # 二次 → after_cancel 分支
            _click_cancel(r)
        _with_driver(monkeypatch, tk_root, _driver)
        r = td.run_form("表单", fields, timeout_seconds=4)
        assert r["clicked"] == "cancel" and r["value"] is None

    def test_validate_exception_swallowed_then_recursion(self, tk_root, monkeypatch):
        def _bad_validate():
            raise RuntimeError("boom")

        def _driver(r):
            _find_widgets(r, tk.Button, "确认")[0].invoke()   # validate 异常吞掉
            _click_cancel(r)               # → finish → BUG-T1 递归 → bgerror
        _with_driver(monkeypatch, tk_root, _driver)
        r = td.run_modal("m", "locked", 4, "info", "t", 560, "确认", "取消",
                         lambda ctx: (lambda: "v", _bad_validate))
        assert r["clicked"] == "cancel"
        assert r["value"] is None          # validate 异常 → value 置 None（:282-283）

    def test_drag_bindings_no_crash(self, tk_root, monkeypatch):
        def _driver(r):
            body = _find_widgets(r, tk.Frame)[0]
            body.event_generate("<ButtonPress-1>", x=3, y=3)
            body.event_generate("<B1-Motion>", x=6, y=6)
            _click_cancel(r)
        _with_driver(monkeypatch, tk_root, _driver)
        r = td.run_modal("m", "locked", 3, "info", "t", 560, "确认", "取消",
                         lambda ctx: (lambda: None, lambda: None))
        assert r["clicked"] == "cancel"

    def test_corner_style_real_and_error_fallback(self, tk_root, monkeypatch):
        import vools.actus.winstyle as ws

        def _driver(r):
            _click_cancel(r)
        _with_driver(monkeypatch, tk_root, _driver)
        r = td.run_modal("m", "locked", 3, "info", "t", 560, "确认", "取消",
                         lambda ctx: (lambda: None, lambda: None))
        assert r["corner_style"] in ("rounded", "region", "none", "dwm")

        def _boom(hwnd, radius=20):
            raise RuntimeError("no dwm")
        monkeypatch.setattr(ws, "round_corners", _boom)
        _with_driver(monkeypatch, tk_root, _driver)
        r2 = td.run_modal("m", "locked", 3, "info", "t", 560, "确认", "取消",
                          lambda ctx: (lambda: None, lambda: None))
        assert r2["corner_style"] == "none"

    def test_width_clamped_to_screen_third(self, tk_root, monkeypatch):
        _with_driver(monkeypatch, tk_root, _click_cancel)
        r = td.run_modal("m", "locked", 3, "info", "t", 9999, "确认", "取消",
                         lambda ctx: (lambda: None, lambda: None))
        assert r["clicked"] == "cancel"          # width 被钳到屏 1/3 不炸
