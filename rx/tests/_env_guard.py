"""rx 测试用的环境探针（共享）。

把「需要可交互 Win32 剪贴板」这类【环境前置条件】集中一处，供多个测试
模块 / conftest 复用，避免每个剪贴板集成测试各自写一份 OpenClipboard 探测、
也避免在 headless / 非交互会话里误判成库缺陷。
"""

import sys


def clipboard_usable():
    """当前会话能否真正打开 Win32 剪贴板。

    Returns:
        bool: 非 Windows 恒 False；Windows 下试开一次剪贴板，能打开才 True。
        session 0 / 服务账户 / 某些远程或 headless 会话里 OpenClipboard 会失败。
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        user32 = ctypes.windll.user32
        opened = bool(user32.OpenClipboard(0))
        if opened:
            user32.CloseClipboard()
        return opened
    except Exception:
        return False


CLIPBOARD_SKIP_REASON = "无可交互剪贴板（headless / 非交互桌面会话），跳过集成测试"
