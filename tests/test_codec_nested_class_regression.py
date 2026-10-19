# -*- coding: utf-8 -*-
"""回归测试：嵌套类反序列化（BUG-205）。

codec._import_class 原用 rsplit('.', 1) 把 type_name（'module.__qualname__'）
切成模块路径 + 类名，但模块路径与嵌套 __qualname__ 都含 '.'，嵌套类（如
Outer.Inner）被误切导致导入失败返回 None，_reconstruct_object 静默降级为
dict，类型丢失且无告警。修复：逐步缩短模块前缀逐级 getattr。
"""

import sys
import types

from vools.serialize.codec import _import_class, _reconstruct_object


class Outer:
    class Inner:
        def __init__(self, v=None):
            self.v = v


_MODULE_NAME = 'vools.test_codec_nested_regression'
_MOD = types.ModuleType(_MODULE_NAME)
_MOD.Outer = Outer
sys.modules[_MODULE_NAME] = _MOD


class TestImportClassNested:
    """嵌套类必须可解析（BUG-205）。"""

    def test_flat_class(self):
        assert _import_class(f'{_MODULE_NAME}.Outer') is Outer

    def test_nested_class(self):
        cls = _import_class(f'{_MODULE_NAME}.Outer.Inner')
        assert cls is Outer.Inner

    def test_stdlib(self):
        import datetime
        assert _import_class('datetime.datetime') is datetime.datetime

    def test_non_whitelist_rejected(self):
        # 非白名单模块仍被拒（BUG-98）
        assert _import_class('os.path.join') is None

    def test_nonexistent(self):
        assert _import_class(f'{_MODULE_NAME}.DoesNotExist') is None


class TestReconstructObjectNested:
    """_reconstruct_object 不得静默降级为 dict（BUG-205）。"""

    def test_nested_reconstruct(self):
        obj = _reconstruct_object(
            f'{_MODULE_NAME}.Outer.Inner',
            {'__vools_type__': f'{_MODULE_NAME}.Outer.Inner'},
        )
        assert isinstance(obj, Outer.Inner), (
            f'expected Outer.Inner, got {type(obj).__name__}'
        )