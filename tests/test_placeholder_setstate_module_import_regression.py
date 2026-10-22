# -*- coding: utf-8 -*-
"""回归测试：_IndexHolder.__setstate__ 不得任意导入模块（BUG-307, security）。

原实现对 state 里任何 `'__module__:<name>'` 值无条件
`importlib.import_module(name)`。该 __setstate__ 可由
`codec.vools_object_hook` → `_reconstruct_object` 触发——`_import_class`
只对**类所在模块**做白名单（`vools.` 前缀放行
`vools.functional.placeholder._IndexHolder`），**state 完全不校验**。实测构造
JSON 即可让 env 装入 os/sys 真实模块对象，绕过 BUG-98/99 的模块白名单；
配合攻击者可控 expr 构成 RCE 链。

修复（commit 6812d5f）：模块恢复改为固定白名单 `_SAFE_ENV_MODULES`；
非白名单模块名保留原字符串、不产生 import 副作用。

本测试按**白名单驱动**断言（不硬编码具体白名单内容），白名单自身增删
不会让测试误报。
"""

import json
import pickle

import pytest

import vools.functional.placeholder as _ph
from vools.serialize import loads

_SAFE = _ph._SAFE_ENV_MODULES


def _payload(env: dict):
    return {
        '__vools_obj__': True,
        'type': 'vools.functional.placeholder._IndexHolder',
        'state': {'expr': '1+1', 'env': env},
    }


def _reconstruct(env: dict):
    return loads(json.dumps(_payload(env)).encode(), backend='json')


class TestArbitraryModuleImportBlocked:
    @pytest.mark.parametrize('bad', ['os', 'sys', 'subprocess', 'socket',
                                     'importlib', 'ctypes'])
    def test_dangerous_modules_not_imported(self, bad):
        obj = _reconstruct({'m': '__module__:' + bad})
        val = getattr(obj, 'env', {}).get('m')
        # 必须是原字符串，不能是 module 对象
        assert isinstance(val, str)
        assert val == bad

    def test_os_has_no_system_attribute_after_load(self):
        obj = _reconstruct({'os': '__module__:os', 'sys': '__module__:sys'})
        env = getattr(obj, 'env', {})
        assert not hasattr(env.get('os'), 'system')
        assert not hasattr(env.get('sys'), 'modules')

    def test_whitelist_never_contains_dangerous_modules(self):
        for bad in ('os', 'sys', 'subprocess', 'socket', 'importlib',
                    'ctypes', 'builtins'):
            assert bad not in _SAFE or bad == 'builtins' and False


class TestSafeModulesStillWork:
    def test_whitelisted_modules_restore_as_modules(self):
        # 白名单里的每个模块都应能恢复成 module（whitelist 驱动，不硬编码）
        for mod in sorted(_SAFE):
            obj = _reconstruct({'m': '__module__:' + mod})
            val = getattr(obj, 'env', {}).get('m')
            assert type(val).__name__ == 'module', f'{mod} 未恢复为模块'

    def test_math_in_whitelist_and_works(self):
        if 'math' not in _SAFE:
            pytest.skip('当前白名单不含 math')
        obj = _reconstruct({'m': '__module__:math'})
        assert obj.env['m'].sqrt(9) == 3.0

    def test_pickle_roundtrip_still_restores_modules(self):
        from vools.functional.placeholder import _IndexHolder
        h = _IndexHolder('lambda x: x * 2', env={'math': __import__('math')},
                         arity=1, ix=1)
        h2 = pickle.loads(pickle.dumps(h))
        assert type(h2.env.get('math')).__name__ == 'module'