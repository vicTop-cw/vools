"""rx 测试用的环境探针（共享）。

把「需要可交互 Win32 剪贴板」这类【环境前置条件】集中一处，供多个测试
模块 / conftest 复用，避免每个剪贴板集成测试各自写一份 OpenClipboard 探测、
也避免在 headless / 非交互会话里误判成库缺陷。
"""

import sys
import time


def clipboard_usable(retries: int = 5, delay: float = 0.1):
    """当前会话能否真正打开 Win32 剪贴板。

    Returns:
        bool: 非 Windows 恒 False；Windows 下试开剪贴板，能打开才 True。
        session 0 / 服务账户 / 某些远程或 headless 会话里 OpenClipboard 会失败。

    注意瞬时争用：OpenClipboard 在剪贴板被别的线程/进程【短暂】持有时也会返回
    失败，这并不代表当前是 headless 会话。若不重试，全量运行里前一个剪贴板测试
    的 hook 线程可能仍短暂占着剪贴板，导致这里误判为"不可用"，进而让
    clipboard_or_degrade 走进降级分支——随后降级契约再次探测时争用已解除、
    OpenClipboard 又成功，就出现 `not clipboard_usable()` 断言翻转的时序 flaky。
    这里做有限重试：只要有一次能打开就判为可用。
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        user32 = ctypes.windll.user32
        for i in range(max(1, retries)):
            opened = bool(user32.OpenClipboard(0))
            if opened:
                user32.CloseClipboard()
                return True
            if i < retries - 1:
                time.sleep(delay)
        return False
    except Exception:
        return False


CLIPBOARD_SKIP_REASON = "无可交互剪贴板（headless / 非交互桌面会话），跳过集成测试"
