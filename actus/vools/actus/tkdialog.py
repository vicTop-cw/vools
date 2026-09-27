"""等待类弹窗共用引擎（tkinter，零第三方依赖）— dialog 家族共用底座。

交互元素（A 维）：confirm / single(单选) / multi(多选) / text(输入) / form(表单)；
焦点策略（B 维）四种，与元素类型正交组合，避免动作文件组合爆炸：

  locked           全局抓取焦点 + 焦点强制循环：除非点按钮，永远等待（种类 1）
  blur_cancel      点击别处 = 取消（种类 2）
  timeout_confirm  倒计时，到时自动确认（种类 3，默认 30s）
  timeout_cancel   倒计时，到时自动取消（对称补全档）

细节沿用 Quicker 语料：
- 占焦前记录前台窗口，关闭后 best-effort 归还焦点（"恢复活动窗口"）；
- Enter=确认（多行文本/含 textarea 的表单改为 Ctrl+Enter）/ Esc=取消；
- 纯展示性增强（圆角/配色）失败一律降级不阻断；
- locked 下给 timeout_seconds 视为安全阀（到时自动取消），缺省才是永等待。

纯逻辑（validate_spec / validate_options / validate_fields）独立成函数
供 dry_run 与单测复用；真实窗口路径返回 {clicked, value, ...}，
绝不抛异常退出。

进程内弹窗互斥锁：tkinter 非线程安全，同进程并发（工作流并行节点、
多线程触发器）必须串行化，否则多 mainloop 会崩；跨进程完全并发。
"""

__all__ = ["FOCUS_POLICIES", "KIND_COLORS", "validate_spec",
           "validate_options", "validate_fields",
           "run_dialog", "run_single", "run_multi", "run_text", "run_form"]

import os
import re
import threading

# 进程内弹窗互斥锁（模态语义本就是一次一个）
_dialog_lock = threading.Lock()
# 非模态堆叠计数器（toast 等可堆叠弹窗的级联偏移）
_toast_stack = [0]  # mutable int for process-level counter

FOCUS_POLICIES = ("locked", "blur_cancel", "timeout_confirm", "timeout_cancel")

# 与 dialog_toast 同套配色：kind → (主色, 强调字色)
KIND_COLORS = {
    "info": ("#1565C0", "#FFFFFF"),
    "warning": ("#F9A825", "#1A1A1A"),
    "error": ("#C62828", "#FFFFFF"),
    "success": ("#2E7D32", "#FFFFFF"),
}

_MAX_TIMEOUT_S = 86400  # 24h 安全上限
_BG = "#FAFAFA"
_FG = "#1A1A1A"
_FG_SUB = "#555555"
_FG_HINT = "#888888"
_FONT = "Microsoft YaHei UI"
_KEY_RE = re.compile(r"^[a-z_][a-z0-9_]{0,29}$")
_FIELD_TYPES = ("text", "password", "select", "textarea", "checkbox")


def validate_spec(message, focus_policy, timeout_seconds, kind):
    """纯校验：返回 None=合法，否则结构化错误 dict（param_invalid）。"""
    if message is not None and (not isinstance(message, str) or len(message) > 2000):
        return {"code": "param_invalid", "message": "message 须为 ≤2000 字符的字符串"}
    if focus_policy not in FOCUS_POLICIES:
        return {"code": "param_invalid",
                "message": f"focus_policy 必须是 {'/'.join(FOCUS_POLICIES)} 之一，收到: {focus_policy!r}"}
    if kind not in KIND_COLORS:
        return {"code": "param_invalid",
                "message": f"kind 必须是 {'/'.join(KIND_COLORS)} 之一，收到: {kind!r}"}
    if timeout_seconds is not None:
        try:
            t = float(timeout_seconds)
        except (TypeError, ValueError):
            return {"code": "param_invalid", "message": "timeout_seconds 必须是数字"}
        if not (1 <= t <= _MAX_TIMEOUT_S):
            return {"code": "param_invalid",
                    "message": f"timeout_seconds 须在 1~{_MAX_TIMEOUT_S}s"}
    return None


def validate_options(options):
    """单选/多选选项校验：1~20 项，每项 1~60 字符。"""
    if not isinstance(options, list) or not options:
        return {"code": "param_invalid", "message": "options 必填且为非空数组"}
    if len(options) > 20:
        return {"code": "param_invalid", "message": "options 最多 20 项"}
    for i, o in enumerate(options):
        if not isinstance(o, str) or not o.strip() or len(o) > 60:
            return {"code": "param_invalid",
                    "message": f"options[{i}] 须为 1~60 字符的非空字符串"}
    return None


def validate_fields(fields):
    """表单字段校验：1~12 个字段，key/label/type/options/default 合法。"""
    if not isinstance(fields, list) or not fields:
        return {"code": "param_invalid", "message": "fields 必填且为非空数组"}
    if len(fields) > 12:
        return {"code": "param_invalid", "message": "fields 最多 12 个字段"}
    seen = set()
    for i, f in enumerate(fields):
        if not isinstance(f, dict):
            return {"code": "param_invalid", "message": f"fields[{i}] 须为对象"}
        key = f.get("key")
        if not isinstance(key, str) or not _KEY_RE.match(key):
            return {"code": "param_invalid",
                    "message": f"fields[{i}].key 须匹配 ^[a-z_][a-z0-9_]{{0,29}}$，收到: {key!r}"}
        if key in seen:
            return {"code": "param_invalid", "message": f"fields[{i}].key 重复: {key}"}
        seen.add(key)
        label = f.get("label")
        if not isinstance(label, str) or not label.strip() or len(label) > 30:
            return {"code": "param_invalid",
                    "message": f"fields[{i}].label 须为 1~30 字符"}
        ftype = f.get("type", "text")
        if ftype not in _FIELD_TYPES:
            return {"code": "param_invalid",
                    "message": f"fields[{i}].type 须是 {'/'.join(_FIELD_TYPES)} 之一，收到: {ftype!r}"}
        options = f.get("options")
        if ftype == "select":
            err = validate_options(options)
            if err:
                return {"code": err["code"],
                        "message": f"fields[{i}].options: {err['message']}"}
        default = f.get("default")
        if ftype == "checkbox":
            if default is not None and not isinstance(default, bool):
                return {"code": "param_invalid",
                        "message": f"fields[{i}].default（checkbox）须为布尔"}
        elif default is not None:
            if ftype == "select" and default not in options:
                return {"code": "param_invalid",
                        "message": f"fields[{i}].default 不在 options 中"}
            if ftype != "select" and (not isinstance(default, str) or len(default) > 500):
                return {"code": "param_invalid",
                        "message": f"fields[{i}].default 须为 ≤500 字符的字符串"}
    return None


# ── Tk 根复用与状态清理（Windows 上反复创建/销毁解释器有 Tcl 竞态）──

def _get_root():
    import time
    import tkinter as tk
    root = getattr(tk, "_actus_dialog_root", None)
    if root is not None:
        try:
            if root.winfo_exists():
                return root
        except tk.TclError:
            pass
        tk._actus_dialog_root = None
    last = None
    for _attempt in range(3):
        try:
            root = tk.Tk()
            root.withdraw()
            tk._actus_dialog_root = root
            return root
        except tk.TclError as e:
            last = e
            time.sleep(0.3)
    raise last


def _reset_root_state(root):
    """复用根：清理上一轮残留（控件/pending after 回调/键盘绑定）。"""
    import tkinter as tk
    for w in root.winfo_children():
        w.destroy()
    try:
        for aid in root.tk.call("after", "info"):
            root.after_cancel(aid)
    except Exception:
        pass
    for seq in ("<Return>", "<Escape>", "<FocusOut>", "<Control-Return>"):
        try:
            root.unbind(seq)
        except tk.TclError:
            pass


def _resolve_focus_poll(explicit=None):
    """locked 抓焦拉回间隔（ms）：参数 > env > 默认 400，下限钳 50。"""
    if explicit is None:
        try:
            explicit = int(os.environ.get("ACTUS_DIALOG_FOCUS_POLL_MS", "400"))
        except (TypeError, ValueError):
            explicit = 400
    return max(50, explicit)


class _Ctx:
    """build_body 与通用核心之间的桥。"""

    __slots__ = ("root", "body", "countdown_var", "status_var",
                 "focus_widget", "_flash_after")

    def __init__(self, root, body, countdown_var, status_var):
        self.root = root
        self.body = body
        self.countdown_var = countdown_var
        self.status_var = status_var
        self.focus_widget = None
        self._flash_after = None

    def flash(self, msg):
        """按钮区上方闪现提示（如"请先选择一项"），2.5s 自动清除。"""
        self.status_var.set(msg)
        if self._flash_after is not None:
            try:
                self.root.after_cancel(self._flash_after)
            except Exception:
                pass
        self._flash_after = self.root.after(2500,
                                            lambda: self.status_var.set(""))


def _screen_hidden() -> bool:
    """无头模式：真建控件、真跑倒计时与 collect，只是**不把窗口映射到屏幕**。

    为什么不是「直接返回假响应」的桩：那样 timeout 自动档、focus 安全阀、
    collect/validate 这些真逻辑就全被绕过了，测试绿得没有意义（弹窗也确实不弹了，
    但同时测的也不是同一条路）。这里只掐掉 deiconify，其余照旧。

    开关：ACTUS_DIALOG_HEADLESS=1/true/yes；缺省关闭（人用的时候要看得见）。
    tests/conftest.py 在整个会话里开启，所以跑验证不会再弹一堆窗。
    """
    return (os.environ.get('ACTUS_DIALOG_HEADLESS') or '').strip().lower() \
        in ('1', 'true', 'yes', 'on')


def run_modal(message, focus_policy, timeout_seconds, kind, title,
              width, confirm_text, cancel_text, build_body,
              enter_confirms=True, show_cancel=True, focus_poll_ms=None,
              modal=True):
    """通用弹窗核心（阻塞至用户响应或倒计时结束）。

    modal=True（默认）：进程内串行化（_dialog_lock），占焦直到响应。
    modal=False：非模态，不抢焦，自动消失，可多实例堆叠（toast 用）。

    build_body(ctx) -> (collect, validate)：
      collect()   提取当前值（确认/自动确认时调用）；
      validate()  确认前校验，返回错误文案（None=通过）。
    show_cancel=False 时隐藏取消按钮（alert 类：任意关闭=确认知悉），
    此时 Esc 同样按确认处理（Quicker msgbox 语义）。
    返回 {"clicked", "value", "elapsed_ms", "corner_style"}。
    """
    import time
    import tkinter as tk

    err = validate_spec(message, focus_policy, timeout_seconds, kind)
    if err:
        return {"clicked": "error", "value": None, "message": err["message"]}

    bg, fg = KIND_COLORS[kind]
    t0 = time.monotonic()

    # ── 占焦前记录前台窗口（Quicker"恢复活动窗口"）─────────────
    prev_hwnd = 0
    try:
        import sys
        if sys.platform == "win32":
            import ctypes
            prev_hwnd = int(ctypes.windll.user32.GetForegroundWindow())
    except Exception:
        prev_hwnd = 0

    root = _get_root()
    _reset_root_state(root)
    result = {"clicked": "cancel", "value": None}
    state = {"collect": lambda: None, "validate": lambda: None}

    def do_confirm():
        try:
            verr = state["validate"]()
            if verr:
                ctx.flash(verr)
                return
            state["value"] = state["collect"]()
        except Exception:
            state["value"] = None
        finish("confirm")

    def finish(clicked):
        if clicked == "confirm":
            do_confirm()
            return
        result["clicked"] = clicked
        try:
            root.grab_release()
        except Exception:
            pass
        try:
            root.withdraw()
            root.quit()  # 退出 mainloop（根保留复用，非 destroy）
        except tk.TclError:
            pass

    # ── 窗口外观：无边框 + 圆角 + 左侧色条（与 toast 同视觉语言）──
    root.title(title)
    root.configure(bg=_BG)
    root.overrideredirect(True)
    root.attributes("-topmost", True)

    body = tk.Frame(root, bg=_BG, padx=26, pady=20)
    body.pack(fill="both", expand=True)
    accent = tk.Frame(root, bg=bg, width=10)
    accent.pack(side="left", fill="y")
    hdr = tk.Label(body, text=title, bg=_BG, fg=_FG_SUB,
                   font=(_FONT, 10), anchor="w")
    hdr.pack(fill="x")
    if message and message.strip():
        tk.Label(body, text=message.strip(), bg=_BG, fg=_FG,
                 justify="left", font=(_FONT, 12),
                 wraplength=width - 110, pady=14).pack(fill="x")

    countdown_var = tk.StringVar(value="")
    status_var = tk.StringVar(value="")
    tk.Label(body, textvariable=status_var, bg=_BG, fg="#B3261E",
             font=(_FONT, 9)).pack(fill="x")
    tk.Label(body, textvariable=countdown_var, bg=_BG, fg=_FG_HINT,
             font=(_FONT, 9)).pack(fill="x")

    btn_row = tk.Frame(body, bg=_BG)
    btn_row.pack(fill="x", pady=(6, 0))
    if show_cancel:
        tk.Button(btn_row, text=cancel_text, width=10, relief="flat",
                  bg="#EEEEEE", fg="#333333", cursor="hand2",
                  command=lambda: finish("cancel")).pack(side="right", padx=(8, 0))
    tk.Button(btn_row, text=confirm_text, width=10, relief="flat",
              bg=bg, fg=fg, cursor="hand2",
              command=do_confirm).pack(side="right")

    ctx = _Ctx(root, body, countdown_var, status_var)
    collect, validate = build_body(ctx)
    state["collect"], state["validate"] = collect, validate

    # 无边框窗口：标题区拖动（手动实现，tkinter 无内置拖动）
    drag_anchor = [0, 0]

    def _press(event):
        drag_anchor[0], drag_anchor[1] = event.x, event.y

    def _move(event):
        root.geometry(f"+{event.x_root - drag_anchor[0]}"
                      f"+{event.y_root - drag_anchor[1]}")

    for w in (hdr, body):
        w.bind("<ButtonPress-1>", _press)
        w.bind("<B1-Motion>", _move)

    # 键盘：Enter（或 Ctrl+Enter）=确认 / Esc=取消（alert 类 Esc=确认知悉）
    root.bind("<Return>" if enter_confirms else "<Control-Return>",
              lambda e: do_confirm())
    root.bind("<Escape>",
              lambda e: do_confirm() if not show_cancel else finish("cancel"))

    # ── 居中 + 自适应高度（屏 1/3 宽，上限给定宽）────────────────
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    width = min(width, max(420, screen_w // 3))
    root.update_idletasks()
    height = max(150, root.winfo_reqheight())
    x, y = (screen_w - width) // 2, max(0, (screen_h - height) // 3)
    # 级联偏移：多任务多弹窗按进程错开，避免完美重叠无法分辨
    import os as _os
    if not modal:
        # 非模态（toast 等）：按堆叠计数器偏移（40px/档，6 档循环）
        _stack_pos = _toast_stack[0] % 6
        _toast_stack[0] += 1
        _cascade = _stack_pos * 40
    else:
        _cascade = (_os.getpid() % 6) * 28
    x, y = min(x + _cascade, max(0, screen_w - width)), \
        min(y + _cascade, max(0, screen_h - height))
    root.geometry(f"{width}x{height}+{x}+{y}")
    if _screen_hidden():
        root.withdraw()          # 无头：控件/定时器/collect 全走真路径，只是不映射到屏幕
    else:
        root.deiconify()  # 复用根处于 withdraw 态，重新映射

    done_flag = [False]

    # ── 倒计时（timeout_confirm / timeout_cancel；locked 安全阀同用）──
    effective_timeout = timeout_seconds
    deadline = (t0 + effective_timeout) if effective_timeout else None

    def tick():
        if done_flag[0]:
            return
        remain = deadline - time.monotonic()
        if remain <= 0:
            if focus_policy == "timeout_confirm":
                try:
                    state["value"] = state["collect"]()  # 尽力取当前值
                except Exception:
                    state["value"] = None
                finish_confirm_only()
            else:
                finish("timeout_cancel")
            return
        countdown_var.set(f"{int(remain) + 1}s 后自动"
                          f"{'确认' if focus_policy == 'timeout_confirm' else '取消'}")
        root.after(200, tick)

    def finish_confirm_only():
        # timeout_confirm 不走 do_confirm 的校验（自动接受当前值）
        result["clicked"] = "timeout_confirm"
        try:
            root.grab_release()
        except Exception:
            pass
        try:
            root.withdraw()
            root.quit()
        except tk.TclError:
            pass

    # ── 焦点策略接线 ─────────────────────────────────────────
    if focus_policy == "locked":
        try:
            root.grab_set_global()
        except tk.TclError:
            try:
                root.grab_set()
            except tk.TclError:
                pass

        # 抓焦拉回间隔：参数 > ACTUS_DIALOG_FOCUS_POLL_MS env > 默认 400ms
        #（实测手感调优钩子：拉得太频繁可调大，或设很大值近似只提醒一次）
        focus_poll_ms = _resolve_focus_poll(focus_poll_ms)

        def enforce_focus():
            if done_flag[0]:
                return
            if _screen_hidden():
                return           # 无头下不抢焦，也不把窗口重新映射回屏幕
            try:
                focused = root.focus_get()
                if focused is None or focused.winfo_toplevel() is not root:
                    root.deiconify()
                    root.lift()
                    root.focus_force()
                    if ctx.focus_widget is not None:
                        ctx.focus_widget.focus_set()
            except Exception:
                pass
            root.after(focus_poll_ms, enforce_focus)
    else:
        enforce_focus = None

    if focus_policy == "blur_cancel":
        def on_blur(event):
            if not done_flag[0]:
                finish("blur_cancel")
        root.bind("<FocusOut>", on_blur)

    def after_show():
        done_flag[0] = False
        root.focus_force()
        if ctx.focus_widget is not None:
            try:
                ctx.focus_widget.focus_set()
            except Exception:
                pass
        if enforce_focus is not None:
            enforce_focus()
        if deadline is not None:
            tick()
        elif focus_policy == "locked":
            countdown_var.set("等待操作…")

    # ── 圆角（DWM 优先，region 回退，失败降级方角）──────────────
    corner_style = "none"
    try:
        import sys as _sys
        if _sys.platform == "win32":
            import ctypes
            from .winstyle import round_corners
            wid = root.winfo_id()
            hwnd = ctypes.windll.user32.GetParent(wid) or wid
            root.update()
            corner_style = round_corners(hwnd, radius=20)
    except Exception:
        corner_style = "none"

    # ── 淡入动画 ──
    def _fade_in(step=0):
        if step > 10:
            return
        try:
            root.attributes('-alpha', step / 10.0)
        except Exception:
            pass
        root.after(20, lambda: _fade_in(step + 1))

    def _do_show():
        done_flag[0] = False
        if not modal:
            root.attributes('-alpha', 0.0)  # 非模态：从透明开始
            root.after(10, _fade_in)
        if modal:
            root.focus_force()
        if ctx.focus_widget is not None and modal:
            try:
                ctx.focus_widget.focus_set()
            except Exception:
                pass
        if enforce_focus is not None and modal:
            enforce_focus()
        if deadline is not None:
            tick()
        elif focus_policy == "locked":
            countdown_var.set("等待操作…")

    root.after(60, _do_show)   # 映射完成后再抢焦/启动计时

    def _cleanup():
        done_flag[0] = True
        try:
            root.grab_release()
        except Exception:
            pass
        try:
            for aid in root.tk.call("after", "info"):
                root.after_cancel(aid)
        except Exception:
            pass
        try:
            root.withdraw()
        except Exception:
            pass

    def _fade_out_and_cleanup(step=10):
        """淡出动画，完成后清理。"""
        if step <= 0:
            _cleanup()
            return
        try:
            root.attributes('-alpha', step / 10.0)
        except Exception:
            pass
        root.after(15, lambda: _fade_out_and_cleanup(step - 1))

    if modal:
        # 模态：进程内串行化，持锁整个弹窗生命周期
        with _dialog_lock:
            try:
                root.mainloop()
            except Exception:
                pass
            finally:
                _cleanup()
        # 归还焦点
        try:
            import sys as _sys
            if _sys.platform == "win32" and prev_hwnd:
                import ctypes
                ctypes.windll.user32.SetForegroundWindow(prev_hwnd)
        except Exception:
            pass
    else:
        # 非模态：不持锁，不抢焦，自动消失后淡出
        try:
            root.mainloop()
        except Exception:
            pass
        finally:
            _fade_out_and_cleanup()

    return {"clicked": result["clicked"], "value": state.get("value"),
            "elapsed_ms": int((time.monotonic() - t0) * 1000),
            "corner_style": corner_style}


# ── 各交互元素 ────────────────────────────────────────────────

def run_dialog(message, focus_policy, timeout_seconds=None, kind="info",
               title="Actus", confirm_text="确认", cancel_text="取消",
               show_cancel=True, focus_poll_ms=None):
    """确认弹窗（confirm 元素）：value ∈ True（确认）/ None。

    show_cancel=False 即 alert 形态（仅确认按钮，Esc=知悉）。
    """

    def build_body(ctx):
        return (lambda: True, lambda: None)

    r = run_modal(message, focus_policy, timeout_seconds, kind, title,
                  560, confirm_text, cancel_text, build_body,
                  enter_confirms=True, show_cancel=show_cancel,
                  focus_poll_ms=focus_poll_ms)
    if r["clicked"] in ("confirm", "timeout_confirm"):
        r["value"] = True
    return r


def run_single(message, options, default=None, focus_policy="locked",
               timeout_seconds=None, kind="info", title="Actus",
               confirm_text="确认", cancel_text="取消"):
    """单选弹窗：确认须已选（未选闪现提示）；value=所选选项或 None。"""
    import tkinter as tk

    def build_body(ctx):
        var = tk.StringVar(value=default if default in options else "")
        for opt in options:
            tk.Radiobutton(ctx.body, text=opt, value=opt, variable=var,
                           bg=_BG, fg=_FG, font=(_FONT, 11), anchor="w",
                           cursor="hand2").pack(fill="x")

        def collect():
            return var.get() or None

        def validate():
            return None if var.get() else "请先选择一项"

        return collect, validate

    return run_modal(message, focus_policy, timeout_seconds, kind, title,
                     520, confirm_text, cancel_text, build_body)


def run_multi(message, options, defaults=None, focus_policy="locked",
              timeout_seconds=None, kind="info", title="Actus",
              confirm_text="确认", cancel_text="取消"):
    """多选弹窗：允许空选（返回 []）；value=所选列表或 None。"""
    import tkinter as tk
    defaults = defaults or []

    def build_body(ctx):
        vars_ = {o: tk.BooleanVar(value=o in defaults) for o in options}
        for opt in options:
            tk.Checkbutton(ctx.body, text=opt, variable=vars_[opt],
                           bg=_BG, fg=_FG, font=(_FONT, 11), anchor="w",
                           cursor="hand2").pack(fill="x")

        def collect():
            return [o for o in options if vars_[o].get()]

        return collect, (lambda: None)

    return run_modal(message, focus_policy, timeout_seconds, kind, title,
                     520, confirm_text, cancel_text, build_body)


def run_text(message, default="", multiline=False, password=False,
             placeholder="", focus_policy="locked", timeout_seconds=None,
             kind="info", title="Actus", confirm_text="确认",
             cancel_text="取消"):
    """文本输入弹窗；value=输入文本（自动确认时取当前内容）或 None。"""
    import tkinter as tk

    def build_body(ctx):
        if multiline:
            txt = tk.Text(ctx.body, height=6, font=(_FONT, 11), wrap="word",
                          bg="#FFFFFF", fg=_FG, relief="flat",
                          highlightthickness=1,
                          highlightbackground="#CCCCCC")
            txt.pack(fill="x", pady=(4, 0))
            if default:
                txt.insert("1.0", default)
            ctx.focus_widget = txt
            txt.bind("<Return>", lambda e: "break")  # 换行，不冒泡成确认

            def collect():
                return txt.get("1.0", "end-1c")

            return collect, (lambda: None)

        entry = tk.Entry(ctx.body, font=(_FONT, 12), relief="flat",
                         show="•" if password else "",
                         bg="#FFFFFF", fg=_FG,
                         highlightthickness=1,
                         highlightbackground="#CCCCCC")
        entry.pack(fill="x", pady=(4, 0))
        ph_on = [False]
        if not default and placeholder:
            entry.insert(0, placeholder)
            entry.config(fg=_FG_HINT)
            ph_on[0] = True

            def on_focus_in(_e):
                if ph_on[0]:
                    entry.delete(0, "end")
                    entry.config(fg=_FG)
                    ph_on[0] = False

            def on_focus_out(_e):
                if not entry.get():
                    entry.insert(0, placeholder)
                    entry.config(fg=_FG_HINT)
                    ph_on[0] = True

            entry.bind("<FocusIn>", on_focus_in)
            entry.bind("<FocusOut>", on_focus_out)
        elif default:
            entry.insert(0, default)
        ctx.focus_widget = entry

        def collect():
            if ph_on[0]:
                return ""
            return entry.get()

        return collect, (lambda: None)

    return run_modal(message, focus_policy, timeout_seconds, kind, title,
                     560, confirm_text, cancel_text, build_body,
                     enter_confirms=not multiline)


def run_form(message, fields, focus_policy="locked", timeout_seconds=None,
             kind="info", title="Actus", confirm_text="确认",
             cancel_text="取消"):
    """表单弹窗：value={key: value}（checkbox 为布尔）或 None。

    含 textarea 的表单 Enter=换行、Ctrl+Enter=确认；否则 Enter=确认。
    required 字段为空时确认被拦截并闪现提示。
    """
    import tkinter as tk
    import tkinter.ttk as ttk
    has_textarea = any(f.get("type") == "textarea" for f in fields)

    def build_body(ctx):
        rows = tk.Frame(ctx.body, bg=_BG)
        rows.pack(fill="x", pady=(2, 0))
        rows.columnconfigure(0, weight=0, minsize=96)
        rows.columnconfigure(1, weight=1)
        widgets = {}
        for i, f in enumerate(fields):
            ftype = f.get("type", "text")
            tk.Label(rows, text=f["label"] + (" *" if f.get("required") else ""),
                     bg=_BG, fg=_FG_SUB, font=(_FONT, 10), anchor="e"
                     ).grid(row=i, column=0, sticky="ew", padx=(0, 10), pady=5)
            cell = tk.Frame(rows, bg=_BG)
            cell.grid(row=i, column=1, sticky="ew", pady=5)
            if ftype == "select":
                cb = ttk.Combobox(cell, values=f["options"],
                                  state="readonly", font=(_FONT, 10))
                if f.get("default"):
                    cb.set(f["default"])
                cb.pack(fill="x")
                widgets[f["key"]] = ("select", cb)
            elif ftype == "checkbox":
                v = tk.BooleanVar(value=bool(f.get("default")))
                tk.Checkbutton(cell, text=f.get("placeholder", ""),
                               variable=v, bg=_BG, fg=_FG,
                               font=(_FONT, 10), anchor="w",
                               cursor="hand2").pack(fill="x")
                widgets[f["key"]] = ("checkbox", v)
            elif ftype == "textarea":
                t = tk.Text(cell, height=4, font=(_FONT, 10), wrap="word",
                            bg="#FFFFFF", fg=_FG, relief="flat",
                            highlightthickness=1,
                            highlightbackground="#CCCCCC")
                t.pack(fill="x")
                if f.get("default"):
                    t.insert("1.0", f["default"])
                t.bind("<Return>", lambda e: "break")
                widgets[f["key"]] = ("textarea", t)
            else:  # text / password
                e = tk.Entry(cell, font=(_FONT, 11), relief="flat",
                             show="•" if ftype == "password" else "",
                             bg="#FFFFFF", fg=_FG,
                             highlightthickness=1,
                             highlightbackground="#CCCCCC")
                e.pack(fill="x")
                if f.get("default"):
                    e.insert(0, f["default"])
                if ctx.focus_widget is None:
                    ctx.focus_widget = e
                widgets[f["key"]] = (ftype, e)

        def collect():
            out = {}
            for key, (ftype, w) in widgets.items():
                if ftype == "checkbox":
                    out[key] = bool(w.get())
                elif ftype == "textarea":
                    out[key] = w.get("1.0", "end-1c")
                else:
                    out[key] = w.get()
            return out

        def validate():
            for f in fields:
                if not f.get("required"):
                    continue
                v = collect().get(f["key"])
                if v is None or v == "" or (isinstance(v, str) and not v.strip()):
                    return f"「{f['label']}」为必填项"
            return None

        return collect, validate

    return run_modal(message, focus_policy, timeout_seconds, kind, title,
                     620, confirm_text, cancel_text, build_body,
                     enter_confirms=not has_textarea)
