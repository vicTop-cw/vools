# -*- coding: utf-8 -*-
"""回归测试：方言实例缓存键无歧义、不碰撞（BUG-233）。

原 `_make_cache_key` 用无转义的 `k=v` 逗号拼接——值中含 `,` 或 `k=v` 形态
即键碰撞：`create_dialect(a='x,b=y')` 与 `create_dialect(a='x', b='y')`
生成同一键，后调用方静默拿到前者的方言实例（连接参数错误）。现实映射：
自定义方言/DSN 参数含逗号（`host='h,port=5432'`、密码含 `,`）。

修复：`repr(sorted(kwargs.items(), key=...))` 无歧义序列化（字符串自带引号
与转义）；空参数仍为 'default'，`name:` 前缀与 clear_instance_cache 匹配不变。
"""

import pytest

from vools.sql.manager import _make_cache_key, manager


class _RecorderDialect:
    """记录构造参数的测试方言（模拟带连接参数的自定义方言）。"""

    def __init__(self, **kwargs):
        self.params = dict(kwargs)


@pytest.fixture
def registered():
    manager.register('regress_dialect', _RecorderDialect)
    manager.clear_instance_cache()
    yield
    manager.clear_instance_cache('regress_dialect')


class TestCacheKeyNoCollision:
    """BUG-233 核心：不同参数组合不得撞键。"""

    def test_comma_value_vs_two_params(self):
        assert _make_cache_key({'a': 'x,b=y'}) != _make_cache_key(
            {'a': 'x', 'b': 'y'})

    def test_dsn_like_values(self):
        assert _make_cache_key({'host': 'h,port=5432'}) != _make_cache_key(
            {'host': 'h', 'port': '5432'})

    def test_password_with_comma(self):
        assert _make_cache_key({'password': 'p,q'}) != _make_cache_key(
            {'password': 'p', 'q': ''})

    def test_instances_not_collide(self, registered):
        d1 = manager.create_dialect('regress_dialect', a='x,b=y')
        d2 = manager.create_dialect('regress_dialect', a='x', b='y')
        assert d1 is not d2
        assert d1.params == {'a': 'x,b=y'}
        assert d2.params == {'a': 'x', 'b': 'y'}


class TestCacheStillWorks:
    """缓存语义保持（防修复过度）。"""

    def test_same_params_hit_same_instance(self, registered):
        d1 = manager.create_dialect('regress_dialect', a=1, b=2)
        d2 = manager.create_dialect('regress_dialect', a=1, b=2)
        assert d1 is d2

    def test_key_order_insensitive(self):
        assert _make_cache_key({'b': 2, 'a': 1}) == _make_cache_key(
            {'a': 1, 'b': 2})

    def test_empty_kwargs_default(self):
        assert _make_cache_key({}) == 'default'

    def test_clear_instance_cache(self, registered):
        d1 = manager.create_dialect('regress_dialect', a=1)
        manager.clear_instance_cache('regress_dialect')
        d2 = manager.create_dialect('regress_dialect', a=1)
        assert d1 is not d2