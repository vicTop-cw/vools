from .monitor_subject import MonitorSubject
from .monitor_observer import MonitorObserver

# ── 平台专属监控模块逐个容错导入 ──
# 每个模块独立 try/except：Windows 专属模块（keyboard/mouse/clipboard/
# window）在非 Windows 平台（尤其 Python 3.6，ctypes.wintypes 导入即崩
# ValueError: _type_ 'v' not supported）应被跳过，不影响 file_watcher /
# folder_watcher 等跨平台模块的可用性。

def _monitoring_imports():
    """逐个导入平台监控子模块，返回 (可用模块名集合, 导入结果 dict)。"""
    imported = {}

    def _load(name, names):
        try:
            mod = __import__("vools.reactive.monitoring." + name, fromlist=names)
            imported[name] = {n: getattr(mod, n) for n in names}
            return True
        except Exception as exc:  # 平台缺失/版本缺陷：该模块不可用，跳过
            log = __import__("logging").getLogger("vools.monitoring")
            log.debug("monitoring 子模块 %s 导入失败（跳过）: %s", name, exc)
            return False

    _load("keyboard", ["KeyEventType", "KeyModifier", "KeyData", "KeyboardDispatcher", "KeySubject", "KeyObserver", "from_keyboard", "write_to_keyboard", "MOD_ALT", "MOD_CONTROL", "MOD_SHIFT", "MOD_WIN", "MOD_NOREPEAT"])
    _load("mouse", ["MouseEventType", "MouseData", "MouseDispatcher", "MouseSubject", "MouseObserver", "from_mouse", "write_to_mouse"])
    _load("clipboard", ["ClipChangeType", "ClipData", "ClipboardDispatcher", "ClipSubject", "ClipObserver", "from_clipboard", "write_to_clipboard"])
    _load("file_watcher", ["FileChangeType", "FileData", "FileDispatcher", "FileSubject", "FileObserver", "from_filesystem", "write_to_filesystem"])
    _load("folder_watcher", ["FolderChangeType", "FolderData", "FolderDispatcher", "FolderSubject", "FolderObserver", "from_foldersystem", "write_to_foldersystem"])
    _load("window", ["WindowChangeType", "WindowData", "WindowDispatcher", "WindowSubject", "WindowObserver", "from_window", "write_to_window"])
    _load("process", ["ProcessChangeType", "ProcessData", "ProcessDispatcher", "ProcessSubject", "ProcessObserver", "from_process", "write_to_process"])
    return imported


_MONITORING_MODS = _monitoring_imports()

if "keyboard" in _MONITORING_MODS:
    _m = _MONITORING_MODS["keyboard"]
    globals().update(
        KeyEventType=_m["KeyEventType"], KeyModifier=_m["KeyModifier"], KeyData=_m["KeyData"],
        KeyboardDispatcher=_m["KeyboardDispatcher"], KeySubject=_m["KeySubject"], KeyObserver=_m["KeyObserver"],
        from_keyboard=_m["from_keyboard"], write_to_keyboard=_m["write_to_keyboard"],
        MOD_ALT=_m["MOD_ALT"], MOD_CONTROL=_m["MOD_CONTROL"], MOD_SHIFT=_m["MOD_SHIFT"],
        MOD_WIN=_m["MOD_WIN"], MOD_NOREPEAT=_m["MOD_NOREPEAT"],
    )
if "mouse" in _MONITORING_MODS:
    _m = _MONITORING_MODS["mouse"]
    globals().update(
        MouseEventType=_m["MouseEventType"], MouseData=_m["MouseData"],
        MouseDispatcher=_m["MouseDispatcher"], MouseSubject=_m["MouseSubject"], MouseObserver=_m["MouseObserver"],
        from_mouse=_m["from_mouse"], write_to_mouse=_m["write_to_mouse"],
    )
if "clipboard" in _MONITORING_MODS:
    _m = _MONITORING_MODS["clipboard"]
    globals().update(
        ClipChangeType=_m["ClipChangeType"], ClipData=_m["ClipData"],
        ClipboardDispatcher=_m["ClipboardDispatcher"], ClipSubject=_m["ClipSubject"], ClipObserver=_m["ClipObserver"],
        from_clipboard=_m["from_clipboard"], write_to_clipboard=_m["write_to_clipboard"],
    )
if "file_watcher" in _MONITORING_MODS:
    _m = _MONITORING_MODS["file_watcher"]
    globals().update(
        FileChangeType=_m["FileChangeType"], FileData=_m["FileData"],
        FileDispatcher=_m["FileDispatcher"], FileSubject=_m["FileSubject"], FileObserver=_m["FileObserver"],
        from_filesystem=_m["from_filesystem"], write_to_filesystem=_m["write_to_filesystem"],
    )
if "folder_watcher" in _MONITORING_MODS:
    _m = _MONITORING_MODS["folder_watcher"]
    globals().update(
        FolderChangeType=_m["FolderChangeType"], FolderData=_m["FolderData"],
        FolderDispatcher=_m["FolderDispatcher"], FolderSubject=_m["FolderSubject"], FolderObserver=_m["FolderObserver"],
        from_foldersystem=_m["from_foldersystem"], write_to_foldersystem=_m["write_to_foldersystem"],
    )
if "window" in _MONITORING_MODS:
    _m = _MONITORING_MODS["window"]
    globals().update(
        WindowChangeType=_m["WindowChangeType"], WindowData=_m["WindowData"],
        WindowDispatcher=_m["WindowDispatcher"], WindowSubject=_m["WindowSubject"], WindowObserver=_m["WindowObserver"],
        from_window=_m["from_window"], write_to_window=_m["write_to_window"],
    )
if "process" in _MONITORING_MODS:
    _m = _MONITORING_MODS["process"]
    globals().update(
        ProcessChangeType=_m["ProcessChangeType"], ProcessData=_m["ProcessData"],
        ProcessDispatcher=_m["ProcessDispatcher"], ProcessSubject=_m["ProcessSubject"], ProcessObserver=_m["ProcessObserver"],
        from_process=_m["from_process"], write_to_process=_m["write_to_process"],
    )

__all__ = [
    # 基础类
    'MonitorSubject',
    'MonitorObserver',

    # 键盘监控
    'KeyEventType', 'KeyModifier', 'KeyData',
    'KeyboardDispatcher', 'KeySubject', 'KeyObserver',
    'from_keyboard', 'write_to_keyboard',
    'MOD_ALT', 'MOD_CONTROL', 'MOD_SHIFT', 'MOD_WIN', 'MOD_NOREPEAT',

    # 鼠标监控
    'MouseEventType', 'MouseData',
    'MouseDispatcher', 'MouseSubject', 'MouseObserver',
    'from_mouse', 'write_to_mouse',

    # 剪贴板监控
    'ClipChangeType', 'ClipData',
    'ClipboardDispatcher', 'ClipSubject', 'ClipObserver',
    'from_clipboard', 'write_to_clipboard',

    # 文件监控
    'FileChangeType', 'FileData',
    'FileDispatcher', 'FileSubject', 'FileObserver',
    'from_filesystem', 'write_to_filesystem',

    # 文件夹监控
    'FolderChangeType', 'FolderData',
    'FolderDispatcher', 'FolderSubject', 'FolderObserver',
    'from_foldersystem', 'write_to_foldersystem',

    # 窗口监控
    'WindowChangeType', 'WindowData',
    'WindowDispatcher', 'WindowSubject', 'WindowObserver',
    'from_window', 'write_to_window',

    # 进程监控
    'ProcessChangeType', 'ProcessData',
    'ProcessDispatcher', 'ProcessSubject', 'ProcessObserver',
    'from_process', 'write_to_process',
]