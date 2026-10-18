# -*- coding: utf-8 -*-
"""tests/serialize/test_type_registry_enum_safety.py — 枚举反序列化沙箱安全（钉 BUG-96）

BUG-96: _deserialize_enum 用 ``__import__(module_path, fromlist=[cls_name])``
动态导入任意模块，再 ``getattr(mod, cls_name)`` 并调用。攻击者可构造
``{'type': 'os.system', 'value': 'echo PWNED > marker'}`` 直接 RCE。

修复：getattr 后校验 ``issubclass(cls, enum.Enum)`` 才放行，
非枚举类型一律 ValueError。
"""

import enum
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from vools.serialize.type_registry import _deserialize_enum, _serialize_enum  # noqa: E402


class Color(enum.Enum):
    RED = 1
    GREEN = 2
    BLUE = 3


class TestEnumDeserializeRCE:
    """_deserialize_enum 不得 RCE"""

    def test_os_system_call_blocked(self, tmp_path):
        marker = tmp_path.as_posix() + "/pwned.txt"
        state = {
            'type': 'os.system',
            'name': 'PWNED',
            'value': f'echo PWNED > "{marker}"'
        }
        with pytest.raises(ValueError):
            _deserialize_enum(state)
        assert not os.path.exists(marker), "RCE via os.system should be blocked"

    def test_os_popen_blocked(self):
        state = {'type': 'os.popen', 'name': 'X', 'value': 'id'}
        with pytest.raises(ValueError):
            _deserialize_enum(state)

    def test_arbitrary_module_blocked(self):
        state = {'type': 'subprocess.check_call', 'name': 'X', 'value': 'echo'}
        with pytest.raises(ValueError):
            _deserialize_enum(state)


class TestEnumDeserializeNormal:
    """正常枚举反序列化不受影响"""

    def test_roundtrip_enum(self):
        state = _serialize_enum(Color.RED)
        result = _deserialize_enum(state)
        assert result == Color.RED

    def test_roundtrip_green(self):
        state = _serialize_enum(Color.GREEN)
        result = _deserialize_enum(state)
        assert result == Color.GREEN

    def test_unknown_module_raises(self):
        """不存在的模块路径仍抛错"""
        state = {'type': 'nonexistent_module.NonexistentClass',
                 'name': 'X', 'value': 1}
        with pytest.raises(Exception):
            _deserialize_enum(state)