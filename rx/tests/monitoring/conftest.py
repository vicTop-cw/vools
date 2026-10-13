"""monitoring/ 子目录测试的环境守卫。

本目录用例都要真实操作 Win32 剪贴板。无可交互桌面会话时在收集期统一
skip（而不是让每个用例跑到一半抛 OSError）。探针复用 tests/_env_guard。
"""

import os
import sys

import pytest

_TESTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

from _env_guard import clipboard_usable, CLIPBOARD_SKIP_REASON  # noqa: E402

if not clipboard_usable():
    pytest.skip(reason=CLIPBOARD_SKIP_REASON, allow_module_level=True)
