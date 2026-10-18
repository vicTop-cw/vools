"""BUG-99 回归测试：_resolve_singleton 允许从任意模块取全局

原实现 importlib.import_module + getattr，攻击者可通过构造
{'__vools_singleton__': 'os:system'} 从反序列化数据获取 os.system、
builtins.print 等任意 callable，构成潜在 RCE 向量。

修复：复用 BUG-98 的白名单 _is_allowed_module()，危险模块直接拒绝。
"""
import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vools.serialize.codec import _resolve_singleton
from vools.serialize.sentinel import NONE


class TestResolveSingleton:
    """_resolve_singleton 白名单校验"""

    def test_normal_singleton(self):
        result = _resolve_singleton('vools.serialize.sentinel:NONE')
        assert result is NONE

    def test_dotted_normal(self):
        result = _resolve_singleton('vools.serialize.sentinel.NONE')
        assert result is NONE

    def test_reject_os_system(self):
        with pytest.raises(ValueError, match='module not allowed'):
            _resolve_singleton('os:system')

    def test_reject_subprocess_popen(self):
        with pytest.raises(ValueError, match='module not allowed'):
            _resolve_singleton('subprocess.Popen')

    def test_reject_builtins_print(self):
        with pytest.raises(ValueError, match='module not allowed'):
            _resolve_singleton('builtins:print')

    def test_reject_sys_modules(self):
        with pytest.raises(ValueError, match='module not allowed'):
            _resolve_singleton('sys:modules')

    def test_reject_invalid_format(self):
        with pytest.raises(ValueError, match='Invalid singleton reference'):
            _resolve_singleton('no-dot')

    def test_reject_nonexistent_attr(self):
        with pytest.raises(ValueError, match='Cannot resolve singleton'):
            _resolve_singleton('vools.serialize.sentinel:NONEXISTENT_ATTR')