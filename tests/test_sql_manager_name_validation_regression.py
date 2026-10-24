# -*- coding: utf-8 -*-
"""回归测试：sql 方言管理器入口的名称/类校验（BUG-411）。

`DialectManager` 的五个公开入口都直接 `name.lower()`：

    register(123, Dialect)        # AttributeError: 'int' object has no attribute 'lower'
    unregister(None)              # 同样的 AttributeError
    get_config(None) / set_config(None, {}) / is_available(None)
    register('q', 'not-a-class')  # 接受（类校验只在 core.register_dialect 里有）

而 `vools.sql.core.dialect.register_dialect` 早已（BUG-348）做了「名称非空
字符串 + dialect_class 是类」的校验 —— 两个入口口径不一致。

修复：管理器内部统一走 `_norm_name()`（非空 str → 去空白 + lower，否则
ValueError），`register` 额外要求 `dialect_class` 是类（其余入口的未知名称仍
按原契约返回 None/False）。

注意：`register` 会写全局方言注册表，测试用的临时方言在 fixture 中注销。
"""

import pytest

import vools.sql.manager as sm

# 模块通过 PEP 562 __getattr__ 动态暴露管理器方法，`from ... import name`
# 不可靠，这里显式取属性。
register = sm.register
unregister = sm.unregister
get_config = sm.get_config
set_config = sm.set_config
is_available = sm.is_available
list_dialects = sm.list_dialects
from vools.sql.sqlite.dialect import SqliteDialect

_TEST_NAMES = ('_probe411_a', '_probe411_b')


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    for name in _TEST_NAMES:
        try:
            unregister(name)
        except Exception:
            pass


class TestNameValidation:
    @pytest.mark.parametrize('bad', [None, 123, '', '   ', 1.5, ['x']])
    def test_register_name(self, bad):
        with pytest.raises(ValueError) as ei:
            register(bad, SqliteDialect)
        assert '方言名称' in str(ei.value)

    @pytest.mark.parametrize('bad', [None, 123, ''])
    def test_unregister_name(self, bad):
        with pytest.raises(ValueError):
            unregister(bad)

    @pytest.mark.parametrize('bad', [None, 123, ''])
    def test_get_config_name(self, bad):
        with pytest.raises(ValueError):
            get_config(bad)

    @pytest.mark.parametrize('bad', [None, 123, ''])
    def test_set_config_name(self, bad):
        with pytest.raises(ValueError):
            set_config(bad, {})

    @pytest.mark.parametrize('bad', [None, 123, ''])
    def test_is_available_name(self, bad):
        with pytest.raises(ValueError):
            is_available(bad)


class TestDialectClassValidation:
    @pytest.mark.parametrize('bad', ['not-a-class', 123, None, SqliteDialect()])
    def test_non_class_rejected(self, bad):
        with pytest.raises(TypeError) as ei:
            register('_probe411_a', bad)
        assert 'dialect_class' in str(ei.value)


class TestNormalBehaviourUnchanged:
    def test_register_and_unregister(self):
        assert register('_probe411_a', SqliteDialect) is None
        assert '_probe411_a' in list_dialects()
        assert get_config('_probe411_a') is not None
        assert unregister('_probe411_a') is True
        assert '_probe411_a' not in list_dialects()
        assert unregister('_probe411_a') is False

    def test_name_case_insensitive(self):
        register('_probe411_b', SqliteDialect)
        assert get_config('_PROBE411_B') is not None
        assert is_available('_Probe411_B') in (True, False)  # 只关心不抛错

    def test_set_config_dict_creates_config(self):
        register('_probe411_a', SqliteDialect)
        assert set_config('_probe411_a', {'driver': 'sqlite3'}) is True
        cfg = get_config('_probe411_a')
        assert cfg is not None and cfg.driver == 'sqlite3'

    def test_set_config_unknown_dialect_returns_false(self):
        assert set_config('_probe411_zzz', {'driver': 'x'}) is False

    def test_unknown_queries_return_defaults(self):
        assert get_config('_probe411_zzz') is None
        assert is_available('_probe411_zzz') is False
        assert unregister('_probe411_zzz') is False