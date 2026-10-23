"""BUG-98 回归测试：反序列化 _import_class 允许任意模块导入

原实现 _import_class 从反序列化数据中的 type_name 导入任意模块并 getattr，
攻击者可通过构造恶意 JSON 数据（如 {'__vools_obj__': True, 'type': 'subprocess.Popen',
'state': {...}}）触发任意模块导入/对象创建。

虽然当前 __setstate__ 路径未直接 RCE，但允许导入任意模块仍是纵深防御缺口。

修复：白名单校验（vools.* + 常用 stdlib）+ 必须是 type 类型。
"""
import datetime
import pathlib
import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vools.serialize.codec import (
    _import_class,
    _is_allowed_module,
    _reconstruct_object,
)


class TestAllowedModule:
    """白名单校验"""

    @pytest.mark.parametrize('module_path, expected', [
        ('vools', True),
        ('vools.cache', True),
        ('vools.cache.persist', True),
        ('vools.data.seq', True),
        ('vools.serialize.type_registry', True),
        ('datetime', True),
        ('decimal', True),
        ('fractions', True),
        ('pathlib', True),
        ('enum', True),
        ('collections', True),
        ('collections.abc', True),
        ('typing', True),
        # 危险模块必须拒绝
        ('os', False),
        ('subprocess', False),
        ('_io', False),
        ('socket', False),
        ('shutil', False),
        ('sys', False),
        ('builtins', False),
        ('posix', False),
        ('ctypes', False),
        ('multiprocessing', False),
    ])
    def test_is_allowed_module(self, module_path, expected):
        assert _is_allowed_module(module_path) is expected


class TestImportClass:
    """_import_class 白名单与类型校验"""

    def test_import_normal_class(self):
        cls = _import_class('datetime.datetime')
        assert cls is datetime.datetime

    def test_import_vools_class(self):
        cls = _import_class('vools.cache.persist.FileLock')
        assert cls is not None
        assert isinstance(cls, type)

    def test_import_pathlib_class(self):
        cls = _import_class('pathlib.PurePath')
        assert cls is pathlib.PurePath

    def test_reject_dangerous_module(self):
        """os.system 不能作为类导入"""
        cls = _import_class('os.system')
        assert cls is None

    def test_reject_subprocess_module(self):
        cls = _import_class('subprocess.Popen')
        assert cls is None

    def test_reject_non_class_attribute(self):
        """即使模块在白名单，非 type 的 attr 也要拒绝"""
        cls = _import_class('vools.serialize.codec._import_class')
        assert cls is None

    def test_reject_malformed_type_name(self):
        cls = _import_class('no-dot-here')
        assert cls is None


class TestReconstructObject:
    """_reconstruct_object 安全性"""

    def test_normal_datetime(self):
        # datetime.__new__ 需要参数，测试仅验证白名单放行
        cls = _import_class('datetime.datetime')
        assert cls is datetime.datetime

    def test_reject_os_popen(self):
        """尝试通过 __vools_obj__ 创建 subprocess.Popen 应失败"""
        # BUG-332: 不再静默返回 state，改为显式 ValueError（白名单拒绝可见）
        with pytest.raises(ValueError):
            _reconstruct_object('subprocess.Popen', {'args': ['echo', 'x']})

    def test_reject_fileio(self):
        with pytest.raises(ValueError):
            _reconstruct_object('_io.FileIO', {'name': 'x.txt'})

    def test_normal_vools_class(self):
        from vools.cache.persist import FileLock
        result = _reconstruct_object('vools.cache.persist.FileLock', {})
        assert isinstance(result, FileLock)