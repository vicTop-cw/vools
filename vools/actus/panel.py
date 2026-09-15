"""Quicker 风格快捷面板（docs/02 架构中的「薄壳」层）。

铁律（docs/02 §3）：面板不解析动作、不判定 trust、不管产物、不维护依赖图，
只做「展示动作清单 → 触发执行核心 → 呈现结果 / 收集确认」。

- 全局热键（默认 Ctrl+Alt+Space）唤起/隐藏面板（Windows RegisterHotKey）；
- 面板网格列出全部 valid 动作（读 _meta/actions.index.json 只读视图）；
- 双击/回车执行动作：audit 级弹确认对话框（人类确认通道，docs/07 §2），
  trusted 直接执行，结果以文本窗呈现；
- 无第三方依赖：tkinter + ctypes（Windows）；macOS/Linux 热键不可用时退化为
  常驻小窗。
"""

__all__ = ['run_panel', 'PanelApp']

import json
import os
import sys
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
META_DIR = os.path.join(_REPO_ROOT, '_meta')

DEFAULT_HOTKEY = 'ctrl+alt+space'


def _load_actions() -> list:
    """只读视图：读取索引（无索引时构建一次）。"""
    path = os.path.join(META_DIR, 'actions.index.json')
    if not os.path.exists(path):
        import vools.actus
        actuscore.build_index()
    with open(path, 'r', encoding='utf-8') as f:
        idx = json.load(f)
    rows = []
    for aid, b in idx.get('actions', {}).items():
        if aid.startswith('_invalid:') or b.get('status') != 'valid':
            continue
        if b.get('deprecated'):
            continue
        rows.append(b)
    rows.sort(key=lambda b: b.get('id', ''))
    return rows


class PanelApp:
    """主窗口：动作网格 + 详情 + 输出区。"""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title('Actus 快捷面板')
        self.root.geometry('780x520')
        self.root.minsize(640, 420)
        self.root.configure(bg='#1e1f24')
        self._actions = []
        self._build_ui()
        self._reload()

    # ── UI 构建 ──
    def _build_ui(self):
        top = tk.Frame(self.root, bg='#1e1f24')
        top.pack(fill='x', padx=10, pady=(10, 4))
        tk.Label(top, text='Actus', font=('Segoe UI', 14, 'bold'),
                 fg='#7ee787', bg='#1e1f24').pack(side='left')
        tk.Label(top, text='  AI 动作快捷面板（双击执行 · R 刷新 · Esc 收起）',
                 fg='#8b949e', bg='#1e1f24').pack(side='left')

        body = tk.Frame(self.root, bg='#1e1f24')
        body.pack(fill='both', expand=True, padx=10, pady=4)

        # 动作网格（Listbox 双列感：id + 描述）
        list_frame = tk.Frame(body, bg='#1e1f24')
        list_frame.pack(side='left', fill='both', expand=True)
        self.listbox = tk.Listbox(list_frame, bg='#25272e', fg='#e6edf3',
                                  selectbackground='#2d4f2d', font=('Microsoft YaHei UI', 10),
                                  activestyle='none')
        self.listbox.pack(fill='both', expand=True)
        self.listbox.bind('<Double-Button-1>', lambda e: self.run_selected())
        self.listbox.bind('<Return>', lambda e: self.run_selected())
        self.listbox.bind('<<ListboxSelect>>', lambda e: self.show_detail())

        # 详情 / 输出区
        right = tk.Frame(body, bg='#1e1f24', width=340)
        right.pack(side='right', fill='both', expand=False)
        right.pack_propagate(False)

        self.detail = tk.Label(right, text='', justify='left', anchor='nw',
                               fg='#e6edf3', bg='#1e1f24', wraplength=320,
                               font=('Microsoft YaHei UI', 9))
        self.detail.pack(fill='x', pady=(0, 6))

        self.output = scrolledtext.ScrolledText(right, bg='#14161a', fg='#c9d1d9',
                                                font=('Consolas', 9), height=12)
        self.output.pack(fill='both', expand=True)
        self.output.insert('end', '执行输出将显示在这里。\n')
        self.output.configure(state='disabled')

        bottom = tk.Frame(self.root, bg='#1e1f24')
        bottom.pack(fill='x', padx=10, pady=(2, 10))
        tk.Button(bottom, text='执行 ▶', command=self.run_selected,
                  bg='#2ea043', fg='white', relief='flat',
                  font=('Microsoft YaHei UI', 10, 'bold')).pack(side='right')
        tk.Button(bottom, text='刷新 ↻', command=self._reload,
                  bg='#30363d', fg='#e6edf3', relief='flat').pack(side='right', padx=6)

        self.root.bind('<r>', lambda e: self._reload())
        self.root.bind('<Escape>', lambda e: self.root.iconify())

    def _reload(self):
        self._actions = _load_actions()
        self.listbox.delete(0, 'end')
        for b in self._actions:
            trust_icon = {'trusted': '✅', 'audit': '🖐', 'sandbox': '🧪'}.get(
                b.get('trust'), '·')
            desc = (b.get('description') or '')[:36]
            self.listbox.insert('end', f'{trust_icon}  {b["id"]:<28} {desc}')
        if self._actions:
            self.listbox.selection_set(0)
            self.show_detail()

    def _selected(self):
        sel = self.listbox.curselection()
        if not sel:
            return None
        return self._actions[sel[0]]

    def show_detail(self):
        b = self._selected()
        if not b:
            return
        lines = [
            f"id: {b.get('id')}",
            f"名称: {b.get('name')}  v{b.get('version')}",
            f"trust: {b.get('trust')}",
            f"作者: {b.get('author', '-')}",
            '',
            b.get('description') or '',
            '',
            f"权限: {', '.join(b.get('permissions') or []) or '无声明'}",
        ]
        self.detail.configure(text='\n'.join(lines))

    # ── 执行 ──
    def run_selected(self):
        b = self._selected()
        if not b:
            return
        aid = b['id']
        trust = b.get('trust')

        # 人类确认通道（docs/07 §2）：audit 级执行前必须明确确认
        if trust == 'audit':
            ops = '\n'.join(f"· {p}" for p in (b.get('permissions') or []) or ['执行动作代码块'])
            ok = messagebox.askyesno(
                '确认执行（audit）',
                f'动作 {aid} 为 audit 级，将产生以下副作用：\n\n{ops}\n\n确定执行？',
                icon='warning')
            if not ok:
                self._log(f'⏹ {aid}: 已取消（人类未确认）')
                return

        self._log(f'▶ {aid} 执行中…')
        threading.Thread(target=self._execute_bg, args=(aid,), daemon=True).start()

    def _execute_bg(self, aid: str):
        # 薄壳原则：执行全权委托 actuscore，面板不实现任何执行语义
        def work():
            import vools.actus
            r = actuscore.execute(aid, {}, confirmed=False)
            self.root.after(0, lambda: self._on_result(aid, r))

        try:
            sys.path.insert(0, os.path.join(_REPO_ROOT, 'engine'))
            work()
        except Exception as e:  # noqa: BLE001
            self.root.after(0, lambda: self._log(f'❌ {aid}: {e}'))

    def _on_result(self, aid: str, r: dict):
        status = r.get('status')
        if status == 'awaiting_confirmation':
            # 面板内确认后重跑（confirmed=True 闭环）
            import vools.actus
            r2 = actuscore.execute(aid, {}, confirmed=True)
            self._on_result(aid, r2)
            return
        icon = '✅' if status == 'ok' else '❌'
        data = json.dumps(r.get('data'), ensure_ascii=False, indent=2) if r.get('data') else ''
        err = json.dumps(r.get('error'), ensure_ascii=False, indent=2) if r.get('error') else ''
        self._log(f'{icon} {aid} → {status}'
                  + (f'\n{data}' if data else '')
                  + (f'\n{err}' if err else ''))

    def _log(self, text: str):
        self.output.configure(state='normal')
        self.output.insert('end', text + '\n' + '─' * 48 + '\n')
        self.output.see('end')
        self.output.configure(state='disabled')

    def run(self):
        self.root.mainloop()


def _register_global_hotkey(root: tk.Tk, hotkey: str, callback) -> bool:
    """Windows 全局热键（ctypes RegisterHotKey）。失败返回 False（退化常驻）。"""
    if sys.platform != 'win32':
        return False
    try:
        import ctypes
        from ctypes import wintypes

        mods = {'ctrl': 0x0002, 'alt': 0x0001, 'shift': 0x0004, 'win': 0x0008}
        vk_codes = {'space': 0x20, 'a': 0x41, 'q': 0x51, 'k': 0x4B, 'p': 0x50}

        parts = hotkey.split('+')
        key = parts[-1].strip().lower()
        mod = 0
        for p in parts[:-1]:
            mod |= mods.get(p.strip().lower(), 0)
        vk = vk_codes.get(key) or (ord(key.upper()) if len(key) == 1 else None)
        if vk is None or mod == 0:
            return False

        user32 = ctypes.windll.user32
        HOTKEY_ID = 0xB00B
        if not user32.RegisterHotKey(None, HOTKEY_ID, mod, vk):
            return False

        # 轮询消息（tkinter 无原生消息泵，用 after 轮询 PeekMessage）
        PM_REMOVE = 0x0001
        msg = wintypes.MSG()

        def poll():
            while user32.PeekMessageW(ctypes.byref(msg), None,
                                      0xB00B, 0xB00B, PM_REMOVE):
                callback()
            root.after(120, poll)

        root.after(120, poll)
        return True
    except Exception:
        return False


def run_panel(hotkey: str = DEFAULT_HOTKEY):
    """入口：注册全局热键成功 → 面板启动即最小化；失败 → 常驻窗口。"""
    app = PanelApp()
    ok = _register_global_hotkey(app.root, hotkey, app.root.deiconify)
    if ok:
        app._log(f'全局热键 {hotkey} 已注册：任意界面按热键唤起面板')
        app.root.withdraw()
    else:
        app._log(f'（{sys.platform}）全局热键不可用，面板以常驻窗口运行')
    app.run()


if __name__ == '__main__':
    run_panel(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_HOTKEY)
