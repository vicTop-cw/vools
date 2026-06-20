"""
测试 vools.utils.stuff 模块

覆盖范围:
- StuffConfig 配置类
- stuff 装饰器基础功能
- 新 API: provide / provide_with / provide_multi_params / aggregate_providers
- reset() 方法
- IndexedDict 功能
- 类方法 / 类 stuff 支持
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from vools import stuff
from vools.utils.stuff import Stuff, StuffConfig, IndexedDict, StuffExecutionError


# ============================================================================
# StuffConfig
# ============================================================================

class TestStuffConfig:
    def test_default_config(self):
        cfg = StuffConfig()
        assert cfg.cache_duration == 3
        assert cfg.max_workers is None
        assert cfg.debug is False
        assert cfg.strict is True

    def test_custom_config(self):
        cfg = StuffConfig(cache_duration=10, max_workers=4, debug=True, strict=False)
        assert cfg.cache_duration == 10
        assert cfg.max_workers == 4
        assert cfg.debug is True
        assert cfg.strict is False

    def test_config_repr(self):
        cfg = StuffConfig()
        r = repr(cfg)
        assert "cache_duration" in r
        assert "max_workers" in r
        assert "debug" in r
        assert "strict" in r

    def test_config_with_stuff(self):
        cfg = StuffConfig(cache_duration=5)
        @stuff(config=cfg)
        def add(a, b, c):
            return a + b + c
        assert add.config.cache_duration == 5


# ============================================================================
# 基础功能
# ============================================================================

class TestBasicStuff:
    def test_basic_curry(self):
        @stuff
        def add(a, b, c):
            return a + b + c
        assert add(1)(2)(3)() == 6

    def test_all_args_at_once(self):
        @stuff
        def add(a, b, c):
            return a + b + c
        assert add(1, 2, 3)() == 6

    def test_mixed_args(self):
        @stuff
        def add(a, b, c):
            return a + b + c
        assert add(1)(2, 3)() == 6

    def test_keyword_args(self):
        @stuff
        def add(a, b, c):
            return a + b + c
        assert add(a=1)(b=2)(c=3)() == 6
        assert add(b=2)(10, c=3)() == 15


# ============================================================================
# provide — 新 API
# ============================================================================

class TestProvide:
    def test_provide_positional(self):
        @stuff
        def sub(a, b, c):
            return a - b - c

        @sub.provide
        def get_a():
            return 10

        @sub.provide(for_param=2)
        def get_bc():
            return 3, 2

        assert sub() == 5

    def test_provide_keyword(self):
        @stuff
        def add(a, b, c):
            return f"a={a},b={b},c={c}"

        @add.provide(for_param='a')
        def get_a():
            return 1

        @add.provide(for_param=['b', 'c'])
        def get_bc(b, c):
            return c + 1, b + 2

        @get_bc.provide
        def get_b():
            return 2

        @get_bc.provide(for_param='c')
        def get_c():
            return 1

        assert add() == 'a=1,b=2,c=4'

    def test_provide_decorator_syntax(self):
        @stuff
        def multiply(a, b, c):
            return a * b * c

        @multiply.provide
        def get_a():
            return 2

        @multiply.provide(for_param=['b', 'c'])
        def get_bc():
            return 3, 4

        assert multiply() == 24

    def test_provide_non_callable(self):
        @stuff
        def add(a, b):
            return a + b

        add.provide(5, for_param='a')
        add.provide(10, for_param='b')
        assert add() == 15


# ============================================================================
# provide_with — 注册 + 内联参数
# ============================================================================

class TestProvideWith:
    def test_provide_with_kwargs(self):
        @stuff
        def greet(greeting, name):
            return f"{greeting}, {name}!"

        @greet.provide_with(for_param='name')
        def get_name():
            return "World"

        greet.provide_with(lambda: "Hello", for_param='greeting')
        assert greet() == "Hello, World!"


# ============================================================================
# provide_multi_params — 一个函数提供多个参数
# ============================================================================

class TestProvideMultiParams:
    def test_multi_params_positional_only(self):
        @stuff
        def calc(price, quantity, tax_rate):
            return price * quantity * (1 + tax_rate)

        calc.provide_multi_params(
            lambda: (100, 2, 0.1),
            pos_count=1,
            for_params=['quantity', 'tax_rate'],
        )
        assert calc() == pytest.approx(220.0)

    def test_multi_params_all_keyword(self):
        @stuff
        def config(db_url, redis_url, debug):
            return f"{db_url}|{redis_url}|{debug}"

        config.provide_multi_params(
            lambda: ("pg://local", "redis://local", True),
            pos_count=0,
            for_params=['db_url', 'redis_url', 'debug'],
        )
        assert config() == "pg://local|redis://local|True"


# ============================================================================
# aggregate_providers — 多个函数聚合提供同一参数
# ============================================================================

class TestAggregateProviders:
    def test_aggregate_positional(self):
        @stuff
        def sum_all(numbers):
            return sum(numbers)

        sum_all.aggregate_providers(
            lambda: 1,
            lambda: 2,
            lambda: 3,
        )
        assert sum_all() == 6

    def test_aggregate_keyword(self):
        @stuff
        def join_all(items):
            return ",".join(str(i) for i in items)

        join_all.aggregate_providers(
            lambda: "a",
            lambda: "b",
            lambda: "c",
            for_param='items',
        )
        assert join_all() == "a,b,c"


# ============================================================================
# reset()
# ============================================================================

class TestReset:
    def test_reset_clears_bindings(self):
        @stuff
        def add(a, b, c):
            return a + b + c

        add.provide(lambda: 1, for_param='a')
        add.provide(lambda: 2, for_param='b')
        # after binding only a and b, calling add() should fail
        with pytest.raises(StuffExecutionError):
            add()

        add.reset()
        assert add(1, 2, 3)() == 6

    def test_reset_keeps_config(self):
        cfg = StuffConfig(cache_duration=99)
        @stuff(config=cfg)
        def add(a, b):
            return a + b

        add.provide(lambda: 1, for_param='a')
        add.reset()
        assert add.config.cache_duration == 99

    def test_reset_without_config(self):
        cfg = StuffConfig(cache_duration=99)
        @stuff(config=cfg)
        def add(a, b):
            return a + b

        add.provide(lambda: 1, for_param='a')
        add.reset(keep_config=False)
        assert add.config.cache_duration == 3  # default


# ============================================================================
# IndexedDict
# ============================================================================

class TestIndexedDict:
    def test_basic_iteration(self):
        d = IndexedDict([10, 20, 30])
        assert list(d) == [10, 20, 30]

    def test_repeated_iteration(self):
        d = IndexedDict([1, 2, 3])
        assert list(d) == [1, 2, 3]
        assert list(d) == [1, 2, 3]  # second iteration

    def test_int_key(self):
        d = IndexedDict({"a": 1, "b": 2})
        assert d[0] == 1
        assert d[1] == 2

    def test_str_key(self):
        d = IndexedDict({"a": 1, "b": 2})
        assert d["a"] == 1
        assert d["b"] == 2

    def test_slice(self):
        d = IndexedDict([1, 2, 3, 4])
        s = d[1:3]
        assert isinstance(s, IndexedDict)
        assert list(s) == [2, 3]

    def test_len(self):
        assert len(IndexedDict([1, 2, 3])) == 3
        assert len(IndexedDict({})) == 0

    def test_with_providers(self):
        data = [1, 2, 3, 4]
        d = IndexedDict(data, providers_pos=2, providers=['x', 'y'])
        assert d[0] == 1
        assert d[1] == 2
        assert d['x'] == 3
        assert d['y'] == 4

    def test_repr(self):
        d = IndexedDict([1, 2])
        assert "IndexedDict" in repr(d)

    def test_single_value(self):
        d = IndexedDict(42)
        assert list(d) == [42]
        assert d[0] == 42

    def test_iteration_order(self):
        d = IndexedDict({"c": 3, "a": 1, "b": 2})
        assert list(d.values()) == [3, 1, 2]


# ============================================================================
# 类方法支持
# ============================================================================

class TestClassMethod:
    def test_class_method_stuff(self):
        class A:
            @stuff
            def add(self, a, b, c):
                return f"a={a},b={b},c={c}"

            def get_a(self):
                return 3

            def get_b(self):
                return 2

            def get_c(self):
                return 1

        obj = A()
        assert obj.add(1, 2, 3)() == 'a=1,b=2,c=3'
        obj.add.provide_multi_params(obj.get_a, pos_count=0, for_params=['a'])
        obj.add.provide_multi_params(obj.get_b, pos_count=0, for_params=['b'])
        obj.add.provide_multi_params(obj.get_c, pos_count=0, for_params=['c'])
        assert obj.add() == 'a=3,b=2,c=1'


# ============================================================================
# 类 Stuff 支持（@stuff 装饰类）
# ============================================================================

class TestClassStuff:
    def test_class_curry(self):
        @stuff
        class C:
            def __init__(self, a, b, c):
                self.args = (a, b, c)

            def __eq__(self, other):
                return self.args == other.args

            def __str__(self):
                return f"C<{self.args}>"

        a = C(1, 2, 3)()
        assert a.args == (1, 2, 3)
        b = C(a=2, c=3, b=4)()
        assert b.args == (2, 4, 3)
        c = C(3)(4)(5)()
        assert c.args == (3, 4, 5)

    def test_class_with_provide(self):
        @stuff
        class C:
            def __init__(self, a, b):
                self.a = a
                self.b = b

        C.provide(lambda: 10, for_param='a')
        C.provide(lambda: 20, for_param='b')
        obj = C()
        assert obj.a == 10
        assert obj.b == 20


# ============================================================================
# 复杂依赖链
# ============================================================================

class TestComplexChain:
    def test_nested_providers(self):
        @stuff
        def complex_op(a, b, c, d):
            return (a + b) * (c - d)

        @complex_op.provide(for_param='a')
        def get_a():
            return 5

        @complex_op.provide
        def get_b():
            return 3

        result = complex_op(c=10, d=2)()
        # a=5, b=3, c=10, d=2 → (5+3)*(10-2) = 64
        assert result == 64


# ============================================================================
# 错误处理
# ============================================================================

class TestErrorHandling:
    def test_stuff_execution_error(self):
        from vools.utils.stuff import StuffExecutionError

        @stuff
        def faulty():
            raise ValueError("boom")

        with pytest.raises(StuffExecutionError):
            faulty()

    def test_invalid_provider_param(self):
        @stuff
        def add(a, b):
            return a + b

        with pytest.raises(ValueError):
            from vools.utils.stuff import Stuff
            Stuff._trans(lambda x: x)  # func with required params
