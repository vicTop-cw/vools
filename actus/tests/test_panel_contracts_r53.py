"""panel.py 契约测试（Round 49）。

契约:
- _load_actions: 只读索引过滤（invalid/deprecated）+ 按 id 排序 + 无索引时构建
- PanelApp: _reload/_selected/show_detail/run_selected/_pump/_on_result/_log
- run_selected: audit 级确认通道（取消/确认）
- _execute_bg: 成功/异常入队
- _on_result: awaiting_confirmation → 后台重跑 confirmed=True
- _register_global_hotkey: 解析/注册/非法输入/异常
- run_panel: 入口
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import _ai_local_bootstrap  # noqa: F401  # 先于 vools 绑定名字：bootstrap 幂等重建保证 from-import 与字符串 patch 同源（防 split-brain 挂死）
import pytest

tk = pytest.importorskip("tkinter")

import vools.actus.panel as panel_mod
from vools.actus.panel import PanelApp, _load_actions, _register_global_hotkey, run_panel


@pytest.fixture
def index_dir(tmp_path, monkeypatch):
    """构建一个索引目录并让 panel 模块的 META_DIR 指向它。"""
    idx = {
        "actions": {
            "beta": {"id": "beta", "name": "Beta", "version": "1.0.0", "trust": "audit",
                     "description": "beta desc", "author": "alice",
                     "permissions": ["file.write"], "status": "valid"},
            "alpha": {"id": "alpha", "name": "Alpha", "version": "0.1.0", "trust": "trusted",
                      "description": "alpha desc", "author": "bob",
                      "permissions": [], "status": "valid"},
            "_invalid:bad": {"id": "_invalid:bad", "status": "invalid"},
            "stale": {"id": "stale", "trust": "trusted", "status": "valid", "deprecated": True},
        }
    }
    (tmp_path / "actions.index.json").write_text(json.dumps(idx), encoding="utf-8")
    monkeypatch.setattr(panel_mod, "META_DIR", str(tmp_path))
    return tmp_path


class TestLoadActions:
    """_load_actions 过滤 + 排序。"""

    def test_filter_and_sort(self, index_dir):
        rows = _load_actions()
        assert [r["id"] for r in rows] == ["alpha", "beta"]

    def test_skips_invalid(self, index_dir):
        rows = _load_actions()
        assert all(not r["id"].startswith("_invalid:") for r in rows)

    def test_skips_deprecated(self, index_dir):
        rows = _load_actions()
        assert all(r["id"] != "stale" for r in rows)

    def test_builds_index_when_missing(self, tmp_path, monkeypatch):
        """无索引文件 → 调 build_index 再读。"""
        monkeypatch.setattr(panel_mod, "META_DIR", str(tmp_path))
        with patch("vools.actus.indexer.build_index") as bi:
            def fake_build():
                idx = {"actions": {"a": {"id": "a", "trust": "trusted", "status": "valid"}}}
                (tmp_path / "actions.index.json").write_text(json.dumps(idx), encoding="utf-8")
            bi.side_effect = fake_build
            rows = _load_actions()
        bi.assert_called_once()
        assert [r["id"] for r in rows] == ["a"]


@pytest.fixture(scope="module")
def shared_root():
    """模块级共享 Tk root：Store Python 沙箱下多次 Tk() 会重读 init.tcl 失败。"""
    root = tk.Tk()
    root.withdraw()
    yield root
    try:
        root.destroy()
    except tk.TclError:
        pass


class TestPanelApp:
    """PanelApp UI 方法。"""

    @pytest.fixture
    def app(self, index_dir, shared_root):
        """PanelApp 复用共享 root（patch tk.Tk 返回它），测试后清掉子控件。"""
        with patch.object(panel_mod.tk, "Tk", return_value=shared_root):
            a = PanelApp()
        yield a
        for child in list(shared_root.winfo_children()):
            try:
                child.destroy()
            except tk.TclError:
                pass

    def test_init_loads_actions(self, app):
        assert len(app._actions) == 2
        assert app.listbox.size() == 2

    def test_reload(self, app):
        app._reload()
        assert app.listbox.size() == 2

    def test_selected_none(self, app):
        app.listbox.selection_clear(0, tk.END)
        assert app._selected() is None

    def test_selected_first(self, app):
        app.listbox.selection_set(0)
        assert app._selected()["id"] == "alpha"

    def _select(self, app, idx):
        """清空已有选择后选中指定行（_reload 默认选中第 0 行，直接 set 会叠加）。"""
        app.listbox.selection_clear(0, tk.END)
        app.listbox.selection_set(idx)
        app.listbox.activate(idx)

    def test_show_detail(self, app):
        self._select(app, 0)
        app.show_detail()
        text = app.detail.cget("text")
        assert "id: alpha" in text
        assert "trust: trusted" in text
        assert "无声明" in text

    def test_show_detail_with_permissions(self, app):
        self._select(app, 1)  # beta
        app.show_detail()
        text = app.detail.cget("text")
        assert "file.write" in text

    def test_show_detail_no_selection(self, app):
        app.listbox.selection_clear(0, tk.END)
        app.show_detail()  # 不应抛错

    def test_run_selected_no_selection(self, app):
        app.listbox.selection_clear(0, tk.END)
        app.run_selected()  # 不应抛错

    def test_run_selected_trusted_starts_thread(self, app):
        app.listbox.selection_set(0)  # alpha: trusted
        with patch("threading.Thread") as th:
            app.run_selected()
        th.assert_called_once()
        args, kwargs = th.call_args
        assert kwargs["args"][0] == "alpha"
        assert kwargs["args"][1] is False

    def test_run_selected_audit_confirm_yes(self, app):
        self._select(app, 1)  # beta: audit
        with patch("vools.actus.panel.messagebox.askyesno", return_value=True), \
             patch("threading.Thread") as th:
            app.run_selected()
        th.assert_called_once()
        assert th.call_args.kwargs["args"][1] is True

    def test_run_selected_audit_confirm_no(self, app):
        self._select(app, 1)  # beta: audit
        with patch("vools.actus.panel.messagebox.askyesno", return_value=False), \
             patch("threading.Thread") as th:
            app.run_selected()
        th.assert_not_called()
        content = app.output.get("1.0", "end")
        assert "已取消" in content

    def test_execute_bg_success(self, app):
        app._execute_bg("alpha", confirmed=False)
        kind, aid, r = app._results.get_nowait()
        assert kind == "result"
        assert aid == "alpha"

    def test_execute_bg_exception(self, app):
        with patch("vools.actus.execute", side_effect=RuntimeError("boom")):
            app._execute_bg("alpha", confirmed=False)
        kind, aid, payload = app._results.get_nowait()
        assert kind == "error"
        assert "boom" in payload

    def test_on_result_ok(self, app):
        app._on_result("alpha", {"status": "ok", "data": {"x": 1}})
        content = app.output.get("1.0", "end")
        assert "✅ alpha" in content
        assert '"x": 1' in content

    def test_on_result_error_status(self, app):
        app._on_result("alpha", {"status": "error", "error": {"msg": "bad"}})
        content = app.output.get("1.0", "end")
        assert "❌ alpha" in content

    def test_on_result_awaiting_confirmation(self, app):
        with patch("threading.Thread") as th:
            app._on_result("alpha", {"status": "awaiting_confirmation"})
        th.assert_called_once()
        assert th.call_args.kwargs["args"][1] is True

    def test_pump_drains_queue(self, app):
        app._results.put(("result", "alpha", {"status": "ok"}))
        app._results.put(("error", "beta", "bad thing"))
        # 停掉 reschedule 以便断言
        with patch.object(app.root, "after"):
            app._pump()
        content = app.output.get("1.0", "end")
        assert "✅ alpha" in content
        assert "❌ beta" in content

    def test_pump_empty(self, app):
        with patch.object(app.root, "after") as after:
            app._pump()
        after.assert_called_once()

    def test_log_separator(self, app):
        app._log("hello")
        content = app.output.get("1.0", "end")
        assert "hello" in content
        assert "─" * 48 in content

    def test_bind_keys(self, app):
        """热键绑定存在（r 刷新 / Esc 收起）。"""
        bindings = str(app.root.bind("<r>"))
        assert bindings
        bindings_esc = str(app.root.bind("<Escape>"))
        assert bindings_esc


class TestRegisterGlobalHotkey:
    """_register_global_hotkey 解析与注册。"""

    def test_non_windows_returns_false(self, monkeypatch):
        monkeypatch.setattr(panel_mod.sys, "platform", "linux")
        assert _register_global_hotkey(MagicMock(), "ctrl+alt+space", lambda: None) is False

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_valid_hotkey_registers(self):
        root = MagicMock()
        result = _register_global_hotkey(root, "ctrl+alt+space", lambda: None)
        # 注册成功或失败都可能（依赖环境），但返回必须是 bool 且不抛错
        assert isinstance(result, bool)

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_invalid_key_char_returns_false(self):
        """多字符键不在 vk_codes 且长度 > 1 → False。"""
        root = MagicMock()
        assert _register_global_hotkey(root, "ctrl+alt+f1", lambda: None) is False

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_no_mod_returns_false(self):
        """只有键没有修饰符 → mod == 0 → False。"""
        root = MagicMock()
        assert _register_global_hotkey(root, "space", lambda: None) is False

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_single_letter_key(self):
        """单字母键走 ord() 分支（p → 0x50）。"""
        root = MagicMock()
        result = _register_global_hotkey(root, "ctrl+alt+p", lambda: None)
        assert isinstance(result, bool)

    def test_exception_returns_false(self, monkeypatch):
        """ctypes 注册抛异常 → False。"""
        monkeypatch.setattr(panel_mod.sys, "platform", "win32")
        # 让 import ctypes 抛错
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *a, **kw):
            if name == "ctypes":
                raise OSError("no ctypes")
            return real_import(name, *a, **kw)
        monkeypatch.setattr(builtins, "__import__", fake_import)
        assert _register_global_hotkey(MagicMock(), "ctrl+alt+space", lambda: None) is False


class TestRunPanel:
    """run_panel 入口。"""

    def test_run_panel_hotkey_fail_resident(self, monkeypatch):
        """热键注册失败 → 常驻窗口（不 withdraw）。"""
        app = MagicMock()
        app.run = MagicMock()
        # 对象寻址（panel_mod 与 from-import 同源）而非字符串寻址：
        # bootstrap 收集期重建 sys.modules['vools.actus.*'] 后，字符串 patch
        # 会打到新模块而 run_panel 闭包持有旧模块 → 真 mainloop 挂死。
        monkeypatch.setattr(panel_mod, "PanelApp", MagicMock(return_value=app))
        monkeypatch.setattr(panel_mod, "_register_global_hotkey", lambda *a, **k: False)
        run_panel("ctrl+alt+space")
        app.root.withdraw.assert_not_called()
        app.run.assert_called_once()

    def test_run_panel_hotkey_ok_withdraws(self, monkeypatch):
        """热键注册成功 → withdraw + 日志。"""
        app = MagicMock()
        app.run = MagicMock()
        monkeypatch.setattr(panel_mod, "PanelApp", MagicMock(return_value=app))
        monkeypatch.setattr(panel_mod, "_register_global_hotkey", lambda *a, **k: True)
        run_panel("ctrl+alt+space")
        app.root.withdraw.assert_called_once()
        app._log.assert_called_once()


class TestModuleExports:
    """模块导出。"""

    def test_all(self):
        assert panel_mod.__all__ == ["run_panel", "PanelApp"]
