"""loop_prompt 家族的桌面/指纹辅助（docs/25 §6.2/§6.4）。

平台库定位：编排型动作保持自身语义自包含，确定性子操作（项目指纹、
剪贴板、窗口聚焦、回放子进程）下沉到引擎库——便于单测与跨动作复用。
零第三方依赖：pyperclip/pywin32 缺失时按注释语义退化。
"""

__all__ = ['DEFAULT_IGNORE', 'fingerprint', 'clipboard_write',
           'clipboard_clear', 'focus_window', 'run_playback']

import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys

# 指纹默认排除表：目录以 / 结尾，文件为 glob（docs/25 §6.2）
DEFAULT_IGNORE = ['.git/', 'node_modules/', '__pycache__/', '*.pyc',
                  'artifacts/', '_meta/', '.venv/', 'dist/', 'build/',
                  '.loop_prompt.stop', '*.mdbuild']


def _ignored(rel: str, patterns) -> bool:
    r = rel.replace(os.sep, '/')
    for pat in patterns:
        if pat.endswith('/'):
            if r.startswith(pat):
                return True
        elif fnmatch.fnmatch(r, pat):
            return True
    return False


def _file_hash(path: str, st: os.stat_result, cache: dict) -> str:
    """内容 md5，附 (size, mtime_ns) 增量缓存：元数据未变则复用上次哈希。"""
    key = (st.st_size, st.st_mtime_ns)
    cached = cache.get(path)
    if cached and cached[0] == key:
        return cached[1]
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    digest = h.hexdigest()
    cache[path] = (key, digest)
    return digest


def fingerprint(project_dir: str, ignore_extra=None, cache: dict = None) -> str:
    """项目内容指纹：逐文件 (relpath, size, mtime_ns) 排序后总哈希。

    - cache：跨 tick 的文件哈希缓存（增量），调用方持有一个 dict 即可；
    - 附加采样 .git/HEAD 与 .git/refs 的 mtime——捕捉"纯提交不改工作区"；
    - 排除 DEFAULT_IGNORE + ignore_extra。
    """
    patterns = list(DEFAULT_IGNORE) + list(ignore_extra or ())
    cache = cache if cache is not None else {}
    parts = []
    for dirpath, dirnames, filenames in os.walk(project_dir):
        dirnames[:] = [d for d in dirnames if not _ignored(
            os.path.relpath(os.path.join(dirpath, d), project_dir) + '/',
            patterns)]
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, project_dir)
            if _ignored(rel, patterns):
                continue
            try:
                st = os.stat(full)
            except OSError:
                continue
            parts.append(
                f"{rel.replace(os.sep, '/')}|{st.st_size}|{st.st_mtime_ns}")
    git_meta = ''
    for g in (os.path.join(project_dir, '.git', 'HEAD'),
              os.path.join(project_dir, '.git', 'refs')):
        try:
            git_meta += f"|{os.stat(g).st_mtime_ns}"
        except OSError:
            pass
    return hashlib.md5(("|".join(sorted(parts)) + git_meta).encode()).hexdigest()


def clipboard_write(text: str) -> bool:
    """写剪贴板：pyperclip 优先，缺失时 Windows ctypes 退化。失败返回 False。"""
    try:
        import pyperclip
        pyperclip.copy(text)
        return True
    except ImportError:
        pass
    if sys.platform != 'win32':
        return False
    import ctypes
    CF_UNICODETEXT, GMEM_MOVEABLE = 13, 0x0002
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    if not user32.OpenClipboard(0):
        return False
    try:
        user32.EmptyClipboard()
        buf = ctypes.create_unicode_buffer(text)
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, ctypes.sizeof(buf))
        target = kernel32.GlobalLock(handle)
        ctypes.memmove(target, buf, ctypes.sizeof(buf))
        kernel32.GlobalUnlock(handle)
        return bool(user32.SetClipboardData(CF_UNICODETEXT, handle))
    finally:
        user32.CloseClipboard()


def clipboard_clear() -> None:
    """清空剪贴板（docs/25 §10 剪贴板卫生）。非 Windows 为 no-op。"""
    if sys.platform != 'win32':
        return
    import ctypes
    if ctypes.windll.user32.OpenClipboard(0):
        try:
            ctypes.windll.user32.EmptyClipboard()
        finally:
            ctypes.windll.user32.CloseClipboard()


def focus_window(title_regex: str) -> bool:
    """按标题正则枚举顶层窗口并置前；找不到返回 False。

    非 Windows 返回 True（v0.1 附着语义：假定终端已在前台，docs/25 §6.4）。
    """
    if sys.platform != 'win32':
        return True
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    found = []

    def _cb(hwnd, _lparam):
        n = user32.GetWindowTextLengthW(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if re.search(title_regex, buf.value):
                found.append(hwnd)
        return True

    CMPFUNC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(CMPFUNC(_cb), 0)
    if not found:
        return False
    hwnd = found[0]
    try:
        import win32gui  # pywin32 可用时最稳
        win32gui.ShowWindow(hwnd, 9)  # SW_RESTORE
        win32gui.SetForegroundWindow(hwnd)
        return True
    except ImportError:
        user32.ShowWindow(hwnd, 9)
        user32.SetForegroundWindow(hwnd)
        return True


def run_playback(repo_root: str, macro_params: dict, meta_base: str,
                 timeout: int = 120) -> dict:
    """经 CLI 子进程执行 macro_playback 并解包引擎出参。

    引擎外层出参为 {status, data, error}，动作自身载荷在 data 内
    （docs/03 §7.2）；本函数返回解包后的动作载荷。
    """
    env = dict(os.environ)
    env['PYTHONIOENCODING'] = 'utf-8'
    env['ACTUS_META_DIR'] = meta_base  # 子进程留痕目录对齐调用方会话
    proc = subprocess.run(
        [sys.executable, '-m', 'actus', 'run', 'actus.system.macro_playback',
         json.dumps(macro_params, ensure_ascii=False), '--confirm'],
        cwd=os.path.join(repo_root, 'engine'),
        env=env, capture_output=True, text=True, timeout=timeout)
    out = proc.stdout.strip()
    try:
        outer = json.loads(out)
    except ValueError:
        return {'status': 'failed', 'mode': None,
                'message': (out[-500:] or proc.stderr[-500:] or '回放无输出')}
    inner = outer.get('data') if isinstance(outer.get('data'), dict) else {}
    payload = dict(inner) if inner else {'status': outer.get('status')}
    if payload.get('status') != 'ok' and outer.get('error'):
        payload.setdefault('message', outer['error'].get('message', '回放失败'))
    return payload
