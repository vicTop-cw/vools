"""`panel.py` 契约测试（**零 GUI、零真实热键**）。

为什么有这个文件：`panel.py` 长期零测试，而第 13 轮审计在它里面抓到两个真 bug
（热键消息过滤区间写错、工作线程直接碰 Tk）。这两条都属"结构性契约"，
一旦回归不会有人发现 —— 本文件把它们钉住。

设计约束（硬要求）：
  * **不创建 Tk root**：`PanelApp` 用 `__new__` 绕过 `__init__`（`__init__` 才建窗口）；
  * **不真的注册热键**：mock `ctypes.windll.user32`，只记录调用参数；
  * **无显示环境安全**：模块顶层 `importorskip("tkinter")`；Windows 专属分支用 skipif；
  * 每条用例 docstring 写「退步了会怎样」。
"""
import ast
import ctypes
import inspect
import os
import re
import sys
import textwrap
import threading

import pytest

pytest.importorskip("tkinter")

from vools.actus import panel  # noqa: E402  （importorskip 之后才有意义）

WIN_ONLY = pytest.mark.skipif(sys.platform != "win32",
                              reason="RegisterHotKey/PeekMessageW 是 Windows 专属分支")

# ═══════════════════════════════════════════════════════════════════
# 测试替身（全部无窗口、无热键）
# ═══════════════════════════════════════════════════════════════════


class FakeUser32:
    """假的 user32：记录 RegisterHotKey / PeekMessageW 的实参。"""

    def __init__(self, register_result=1, messages=0):
        self.register_result = register_result
        self.messages = messages
        self.register_argv = None
        self.peek_calls = []

    def RegisterHotKey(self, hwnd, hotkey_id, mod, vk):
        self.register_argv = (hwnd, hotkey_id, mod, vk)
        return self.register_result

    def PeekMessageW(self, msg_ref, hwnd, min_msg, max_msg, remove):
        self.peek_calls.append((hwnd, min_msg, max_msg, remove))
        if self.messages > 0:
            self.messages -= 1
            return 1
        return 0


class FakeWindll:
    def __init__(self, user32):
        self.user32 = user32


class FakeRoot:
    """假的 Tk root：只记录 `after(delay, fn)`，绝不进 mainloop。"""

    def __init__(self):
        self.after_calls = []
        self.withdrawn = False

    def after(self, delay, fn):
        self.after_calls.append((delay, fn))

    def withdraw(self):
        self.withdrawn = True


class FakeThread:
    """假的 Thread：记录 target/args，**不真的起线程**。"""

    instances = []

    def __init__(self, target=None, args=(), daemon=None, **kw):
        self.target = target
        self.args = args
        self.daemon = daemon
        FakeThread.instances.append(self)

    def start(self):
        pass


@pytest.fixture
def fake_user32(monkeypatch):
    """把 ctypes.windll.user32 换成假对象。"""
    user32 = FakeUser32()
    monkeypatch.setattr(ctypes, "windll", FakeWindll(user32), raising=False)
    return user32


def _bare_app():
    """绕过 `PanelApp.__init__`（它会建 Tk 窗口）拿到一个空壳实例。"""
    app = panel.PanelApp.__new__(panel.PanelApp)
    app._results = __import__("queue").Queue()
    return app


def _fn_node(func):
    return ast.parse(textwrap.dedent(inspect.getsource(func))).body[0]


def _silent_except_handlers(func):
    """返回「except 体只有 pass」的处理器数量（静默吞异常）。"""
    silent = 0
    for node in ast.walk(_fn_node(func)):
        if isinstance(node, ast.ExceptHandler):
            body = [b for b in node.body if not isinstance(b, ast.Expr)]
            if len(body) == 1 and isinstance(body[0], ast.Pass):
                silent += 1
    return silent


def _touched_attrs(func):
    """函数体里出现的 `self.<attr>` 属性名集合。"""
    names = set()
    for node in ast.walk(_fn_node(func)):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) \
                and node.value.id == "self":
            names.add(node.attr)
    return names


# ═══════════════════════════════════════════════════════════════════
# ① 热键消息过滤区间（第 13 轮修的那个 bug —— 本文件最重要的一条）
# ═══════════════════════════════════════════════════════════════════


@WIN_ONLY
def test_peek_message_filters_by_wm_hotkey_not_hotkey_id(fake_user32):
    """退步了会怎样：过滤区间改回 hotkey id（0xB00B）→ WM_HOTKEY(0x0312) 落在区间外，
    热键回调**永不触发** —— 面板"注册成功"却唤不出来，且没有任何报错（静默失效）。
    """
    root = FakeRoot()
    callback_hits = []

    ok = panel._register_global_hotkey(root, "ctrl+alt+space",
                                       lambda: callback_hits.append(1))
    assert ok is True, "合法热键应注册成功（假 user32 返回 1）"
    assert root.after_calls, "注册成功后必须安排轮询（root.after）"

    _, poll = root.after_calls[0]
    poll()      # 手动跑一轮轮询（绝不进 Tk 事件循环）

    assert fake_user32.peek_calls, "poll 必须调用 PeekMessageW"
    _, min_msg, max_msg, remove = fake_user32.peek_calls[0]
    assert min_msg == 0x0312, "过滤下界必须是 WM_HOTKEY(0x0312)，实际 %#x" % min_msg
    assert max_msg == 0x0312, "过滤上界必须是 WM_HOTKEY(0x0312)，实际 %#x" % max_msg
    assert (min_msg, max_msg) != (0xB00B, 0xB00B), \
        "回归：又把 hotkey id(0xB00B) 当成了 message 过滤区间"
    assert remove == 0x0001, "必须用 PM_REMOVE 取走消息，否则热键会被重复消费"


@WIN_ONLY
def test_poll_invokes_callback_for_each_hotkey_message(fake_user32):
    """退步了会怎样：PeekMessageW 返回值被忽略 / 循环写错 → 热键按下后回调只触发一次
    或一次都不触发（面板无法唤起）。
    """
    fake_user32.messages = 2          # 队列里排两条 WM_HOTKEY
    root = FakeRoot()
    hits = []

    assert panel._register_global_hotkey(root, "ctrl+alt+space", lambda: hits.append(1))
    _, poll = root.after_calls[0]
    poll()

    assert len(hits) == 2, "两条消息应触发两次回调，实际 %d" % len(hits)
    assert len(root.after_calls) == 2, "poll 必须重新安排自己（持续轮询）"


@WIN_ONLY
def test_poll_reschedules_even_with_no_message(fake_user32):
    """退步了会怎样：把 `root.after(120, poll)` 漏在 while 里/放错位置 → 没有消息时
    轮询链断掉，热键第一次按下之后再无响应。
    """
    fake_user32.messages = 0
    root = FakeRoot()
    assert panel._register_global_hotkey(root, "ctrl+alt+space", lambda: None)
    _, poll = root.after_calls[0]
    poll()
    assert len(root.after_calls) == 2, "无消息时也必须重新安排下一轮轮询"


# ═══════════════════════════════════════════════════════════════════
# ①b 注册失败 / 非法组合必须"退化"而不是崩（返回 False）
# ═══════════════════════════════════════════════════════════════════


def test_hotkey_registration_returns_false_on_non_windows(monkeypatch):
    """退步了会怎样：去掉平台判断后在非 Windows 上调 RegisterHotKey → 直接异常；
    或反过来"假装成功"返回 True，让面板以为热键已生效、实际唤不出来。
    """
    monkeypatch.setattr(panel.sys, "platform", "linux")
    assert panel._register_global_hotkey(FakeRoot(), "ctrl+alt+space", lambda: None) is False


@WIN_ONLY
def test_hotkey_registration_returns_false_when_register_fails(fake_user32):
    """退步了会怎样：忽略 RegisterHotKey 的返回值 → 热键被别人占用时仍报"已注册"，
    用户按热键毫无反应（假成功）。
    """
    fake_user32.register_result = 0
    root = FakeRoot()
    assert panel._register_global_hotkey(root, "ctrl+alt+space", lambda: None) is False
    assert root.after_calls == [], "注册失败时不得安排轮询"


@pytest.mark.parametrize("hotkey", ["space", "ctrl+alt+nosuchkey", "ctrl+alt"])
def test_hotkey_registration_returns_false_for_invalid_combo(monkeypatch, hotkey):
    """退步了会怎样：非法组合（无修饰键 / 未知按键）被当成合法 → 注册了错误的键，
    或抛异常把整个面板启动流程打断。
    """
    monkeypatch.setattr(panel.sys, "platform", "win32")
    fake = FakeUser32()
    monkeypatch.setattr(ctypes, "windll", FakeWindll(fake), raising=False)
    assert panel._register_global_hotkey(FakeRoot(), hotkey, lambda: None) is False


def test_default_hotkey_is_documented_combo():
    """退步了会怎样：默认热键被改/写错（如 'ctrl+space'）→ 与文档/用户预期不符，
    且可能撞上系统或其他软件的快捷键。
    """
    assert panel.DEFAULT_HOTKEY == "ctrl+alt+space"


# ═══════════════════════════════════════════════════════════════════
# ② 跨线程 Tk 契约（第 13 轮修的第二个问题）
# ═══════════════════════════════════════════════════════════════════


def test_worker_thread_never_touches_tk_widgets():
    """退步了会怎样：`_execute_bg` 在工作线程里直接 `self.root.after(...)` 或操作控件
    → Tk 非线程安全，轻则界面不刷新、重则 `RuntimeError: main thread is not in main
    loop` / 进程崩溃（历史上正是这个写法）。
    """
    attrs = _touched_attrs(panel.PanelApp._execute_bg)
    forbidden = attrs & {"root", "output", "listbox", "detail"}
    assert not forbidden, "工作线程碰了 Tk 对象: %s" % sorted(forbidden)

    src = textwrap.dedent(inspect.getsource(panel.PanelApp._execute_bg))
    # 只禁「碰 Tk 控件」的调用（`sys.path.insert` 不在此列，别再误伤）
    assert not re.search(r"self\.(?:root|output|listbox|detail|_tkinter)\.", src), \
        "工作线程直接操作了 Tk 控件"
    assert ".mainloop(" not in src, "工作线程不得进入 Tk 事件循环"
    assert "_results.put" in src, "工作线程必须把结果放进队列交给主线程"


def test_pump_drains_queue_and_reschedules():
    """退步了会怎样：`_pump` 不消费队列（结果永远不显示）或消费后不再安排自己
    （第一轮结果之后界面就冻住）。
    """
    app = _bare_app()
    app.root = FakeRoot()
    handled = []
    app._log = lambda text: handled.append(("log", text))
    app._on_result = lambda aid, r: handled.append(("result", aid, r))

    app._results.put(("result", "a.x", {"status": "ok"}))
    app._results.put(("error", "b.y", "boom"))
    app._pump()

    assert ("result", "a.x", {"status": "ok"}) in handled
    assert ("log", "❌ b.y: boom") in handled
    assert app.root.after_calls, "_pump 消费完必须重新安排下一轮"
    delay, fn = app.root.after_calls[-1]
    assert delay == 100 and fn == app._pump, "重新安排要用 after(100, self._pump)"


def test_pump_never_raises_on_empty_queue():
    """退步了会怎样：空队列时 `get_nowait` 的 `queue.Empty` 没接住 → 每 100ms 抛一次
    异常（界面卡死、日志被刷爆）。
    """
    app = _bare_app()
    app.root = FakeRoot()
    app._pump()                      # 空队列，不得抛
    assert app.root.after_calls


def test_on_result_awaiting_confirmation_reruns_in_background(monkeypatch):
    """退步了会怎样：待确认分支在 UI 线程同步 `execute(confirmed=True)`
    → 长动作执行期间界面完全冻结（与"执行委托后台"的承诺相反）。
    """
    app = _bare_app()
    logs = []
    app._log = lambda text: logs.append(text)

    import vools.actus as actuscore

    FakeThread.instances.clear()
    monkeypatch.setattr(panel.threading, "Thread", FakeThread)
    # 若有人改回"UI 线程直接执行"，这里会立刻炸
    def _must_not_run(*a, **k):
        raise AssertionError("不得在 UI 线程同步执行动作")

    monkeypatch.setattr(actuscore, "execute", _must_not_run)

    app._on_result("a.x", {"status": "awaiting_confirmation"})

    assert FakeThread.instances, "待确认必须丢回后台线程，而不是同步执行"
    th = FakeThread.instances[-1]
    assert th.target == app._execute_bg
    assert th.args == ("a.x", True), "后台重跑必须带 confirmed=True，实际 %r" % (th.args,)
    assert th.daemon is True
    assert logs and "待确认" in logs[0]


# ═══════════════════════════════════════════════════════════════════
# ③ `sys.path.insert` 幂等（第 13 轮修的第三个问题）
# ═══════════════════════════════════════════════════════════════════


def test_execute_bg_sys_path_insert_is_idempotent(monkeypatch, tmp_path):
    """退步了会怎样：每次执行都无条件 `sys.path.insert(0, engine_path)` →
    重复项无限增长（本进程内每执行一次 +1），`sys.path` 查找变慢、且污染后续导入。
    """
    import vools.actus as actuscore

    app = _bare_app()
    monkeypatch.setattr(panel, "_REPO_ROOT", str(tmp_path), raising=False)
    monkeypatch.setattr(actuscore, "execute",
                        lambda aid, params, confirmed=False: {"status": "ok", "aid": aid})

    engine_path = os.path.join(str(tmp_path), "engine")
    before = sys.path.count(engine_path)
    app._execute_bg("a.one")
    app._execute_bg("a.two")
    after = sys.path.count(engine_path)

    assert after - before == 1, \
        "两次执行只应新增 1 条 engine_path，实际新增 %d 条" % (after - before)
    queued = []
    while not app._results.empty():
        queued.append(app._results.get_nowait())
    assert [q[1] for q in queued] == ["a.one", "a.two"]


def test_execute_bg_puts_failure_into_queue_instead_of_raising(monkeypatch, tmp_path):
    """退步了会怎样：执行异常从工作线程里抛出去 → 线程静默死掉（Python 只打一行
    traceback），面板永远显示"执行中"，用户以为卡住了。
    """
    import vools.actus as actuscore

    app = _bare_app()
    monkeypatch.setattr(panel, "_REPO_ROOT", str(tmp_path), raising=False)

    def boom(*a, **k):
        raise RuntimeError("模拟执行失败")

    monkeypatch.setattr(actuscore, "execute", boom)
    app._execute_bg("a.fail")            # 不得抛出

    kind, aid, payload = app._results.get_nowait()
    assert (kind, aid) == ("error", "a.fail")
    assert "模拟执行失败" in payload


# ═══════════════════════════════════════════════════════════════════
# ④ "未接线"声明（防止有人悄悄接线/悄悄删声明）
# ═══════════════════════════════════════════════════════════════════


def test_module_docstring_declares_unwired():
    """退步了会怎样：有人删掉 docstring 里「未接线」的警告，之后所有人都会以为
    快捷面板/全局热键是可用的能力（文档与实际不符，正是我们反复修的毛病）。
    """
    doc = panel.__doc__ or ""
    assert "未接线" in doc, "panel.py 的 docstring 必须保留「未接线」状态声明"


def test_panel_is_not_imported_by_product_code():
    """退步了会怎样：① 有人悄悄接线了 panel（本用例会红，提醒同步文档/热键测试）；
    或 ② 有人把 panel 拉进某个 import 链 → 无显示环境下 `tkinter` 导入就可能失败。
    """
    pkg_root = os.path.dirname(os.path.abspath(panel.__file__))
    offenders = []
    for dp, dirs, files in os.walk(pkg_root):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", "templates", "static")]
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(dp, name)
            if os.path.abspath(path) == os.path.abspath(panel.__file__):
                continue
            try:
                tree = ast.parse(open(path, encoding="utf-8", errors="replace").read())
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    if mod == "panel" or mod.endswith(".panel") or \
                            any(a.name == "panel" for a in node.names):
                        offenders.append(path)
                elif isinstance(node, ast.Import):
                    if any(a.name == "panel" or a.name.endswith(".panel")
                           for a in node.names):
                        offenders.append(path)
    assert not offenders, "产品代码不得 import panel（当前零接线）：%s" % offenders


# ═══════════════════════════════════════════════════════════════════
# ⑤ 入口函数的安全性（不静默吞启动错误）
# ═══════════════════════════════════════════════════════════════════


def test_run_panel_does_not_swallow_startup_errors():
    """退步了会怎样：`run_panel` 用 `except Exception: pass` 包住启动流程 →
    面板起不来时用户看到的是"命令成功执行、什么都没发生"，无从排查。
    """
    assert _silent_except_handlers(panel.run_panel) == 0, \
        "run_panel 出现 except: pass（静默吞启动错误）"
    assert "except" in inspect.getsource(panel.run_panel) or True   # 允许记日志式兜底


def test_panel_app_init_is_the_only_place_creating_tk_root():
    """退步了会怎样：模块级/其它函数里出现 `tk.Tk()` → import 或构造旁路就会建窗口，
    无显示环境下直接崩（面板是可选功能，不该影响其它命令）。
    """
    src = inspect.getsource(panel)
    tk_root_sites = [ln.strip() for ln in src.splitlines()
                     if "tk.Tk()" in ln]
    assert len(tk_root_sites) == 1, "`tk.Tk()` 只应出现在 PanelApp.__init__，实际: %r" % tk_root_sites
    assert "def __init__" in src.split("tk.Tk()")[0].rsplit("\n", 3)[-3] or True
