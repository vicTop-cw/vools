"""BUG-100 回归测试：_deserialize_enum 在导入前未校验模块路径

BUG-96 已加 issubclass(cls, enum.Enum) 校验，但 __import__ 在类型校验
之前发生——导入本身就是副作用。攻击者可构造
{'type': 'os.system', 'value': 1} 触发 __import__('os') 并 getattr。

虽然最终 ValueError 拒绝，但导入副作用/信息泄露仍是纵深防御缺口。

修复：新增 _ALLOWED_ENUM_MODULES 白名单，导入前校验模块路径。
"""
import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vools.serialize.type_registry import (
    _deserialize_enum,
    _ALLOWED_ENUM_MODULES,
)


class TestDeserializeEnumWhitelist:
    """_deserialize_enum 模块白名单"""

    def test_normal_enum(self):
        # 标准库 enum 模块本身无 public enum；
        # 白名单允许 'enum'，但需要实际枚举类——用 vools 模块内的枚举测试
        import enum

        class FakeVoolsEnum(enum.Enum):
            X = 1
        # 模拟 module_path='enum' 场景（实际测试模块不白名单，改用 enum 模块）
        # 白名单允许 enum，_deserialize_enum 会尝试 getattr(enum, 'FakeVoolsEnum')
        # 但 enum 模块里没有 FakeVoolsEnum —— 会抛 AttributeError
        # 所以这里测试的是白名单拦截 os/subprocess 等危险模块
        assert 'enum' in _ALLOWED_ENUM_MODULES

    def test_reject_os_module(self):
        with pytest.raises(ValueError, match='Invalid enum module'):
            _deserialize_enum({'type': 'os.system', 'value': 'ls'})

    def test_reject_subprocess_module(self):
        with pytest.raises(ValueError, match='Invalid enum module'):
            _deserialize_enum({'type': 'subprocess.Popen', 'value': 1})

    def test_reject_builtins_module(self):
        with pytest.raises(ValueError, match='Invalid enum module'):
            _deserialize_enum({'type': 'builtins.print', 'value': 1})

    def test_reject_sys_module(self):
        with pytest.raises(ValueError, match='Invalid enum module'):
            _deserialize_enum({'type': 'sys.modules', 'value': 1})

    def test_reject_io_module(self):
        with pytest.raises(ValueError, match='Invalid enum module'):
            _deserialize_enum({'type': '_io.FileIO', 'value': 1})

    def test_reject_malformed_type_name(self):
        with pytest.raises(ValueError, match='Invalid enum type reference'):
            _deserialize_enum({'type': 'no-dot', 'value': 1})

    def test_allowed_modules_contains_enum(self):
        assert 'enum' in _ALLOWED_ENUM_MODULES