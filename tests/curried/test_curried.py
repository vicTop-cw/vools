#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vools.curried 完整测试套件

包含单元测试、集成测试和边界条件测试。
"""

import sys
import os
import time
import gc
import threading
from typing import List, Dict, Any, Callable
from functools import reduce
from collections import OrderedDict
import pytest


# ============================================================================
# 测试配置
# ============================================================================

class TestConfig:
    """测试配置"""
    MAX_TEST_TIME = 5  # 单个测试最大执行时间（秒）
    PERFORMANCE_ITERATIONS = 10000  # 性能测试迭代次数
    STRESS_ITERATIONS = 100000  # 压力测试迭代次数


# ============================================================================
# 测试辅助函数
# ============================================================================

def assert_equal(actual, expected, msg=""):
    """断言相等"""
    assert actual == expected, f"{msg}: expected {expected}, got {actual}"


def assert_true(condition, msg=""):
    """断言为真"""
    assert condition, msg


def assertRaises(exc_type, callable_obj, *args, **kwargs):
    """断言抛出异常"""
    try:
        callable_obj(*args, **kwargs)
        pytest.fail(f"Expected {exc_type.__name__} to be raised")
    except exc_type:
        pass


# ============================================================================
# Test Core Functions - 核心函数测试
# ============================================================================

class TestIdentity:
    """测试 identity 函数"""

    def test_identity_basic(self):
        """测试基本功能"""
        from vools.curried import identity
        assert identity(5) == 5
        assert identity("hello") == "hello"
        assert identity([1, 2, 3]) == [1, 2, 3]

    def test_identity_none(self):
        """测试 None"""
        from vools.curried import identity
        assert identity(None) is None

    def test_identity_boolean(self):
        """测试布尔值"""
        from vools.curried import identity
        assert identity(True) is True
        assert identity(False) is False

    def test_identity_complex_types(self):
        """测试复杂类型"""
        from vools.curried import identity
        d = {"a": 1, "b": 2}
        assert identity(d) is d  # 同一对象

        class Obj:
            pass
        o = Obj()
        assert identity(o) is o


class TestConst:
    """测试 const 函数"""

    def test_const_basic(self):
        """测试基本功能"""
        from vools.curried import const
        always_five = const(5)
        assert always_five(10) == 5
        assert always_five("anything") == 5
        assert always_five(None) == 5

    def test_const_with_currying(self):
        """测试柯里化使用"""
        from vools.curried import const
        assert const("hello")("world") == "hello"

    def test_const_preserves_first_arg(self):
        """测试保留第一个参数"""
        from vools.curried import const
        result = const(1, 2)
        assert result == 1


class TestFlip:
    """测试 flip 函数"""

    def test_flip_basic(self):
        """测试基本功能"""
        from vools.curried import flip
        divide = lambda a, b: a / b
        flipped = flip(divide)
        assert flipped(2, 6) == 3.0

    def test_flip_subtraction(self):
        """测试减法翻转"""
        from vools.curried import flip
        sub = lambda a, b: a - b
        flipped_sub = flip(sub)
        assert flipped_sub(1, 5) == 4

    def test_flip_curried(self):
        """测试柯里化"""
        from vools.curried import flip, curry
        @curry
        def divide(a, b):
            return a / b
        flipped = flip(divide)
        assert flipped(2)(6) == 3.0


# ============================================================================
# Test Iteration Functions - 迭代函数测试
# ============================================================================

class TestMap:
    """测试 map 函数"""

    def test_map_basic(self):
        """测试基本功能"""
        from vools.curried import map
        double = lambda x: x * 2
        assert map(double, [1, 2, 3]) == [2, 4, 6]

    def test_map_square(self):
        """测试平方"""
        from vools.curried import map
        assert map(lambda x: x ** 2, range(5)) == [0, 1, 4, 9, 16]

    def test_map_string(self):
        """测试字符串操作"""
        from vools.curried import map
        assert map(str.upper, ['a', 'b', 'c']) == ['A', 'B', 'C']

    def test_map_empty(self):
        """测试空列表"""
        from vools.curried import map
        assert map(lambda x: x * 2, []) == []

    def test_map_curried(self):
        """测试柯里化"""
        from vools.curried import map
        double = map(lambda x: x * 2)
        assert double([1, 2, 3]) == [2, 4, 6]


class TestFilter:
    """测试 filter 函数"""

    def test_filter_basic(self):
        """测试基本功能"""
        from vools.curried import filter
        is_even = lambda x: x % 2 == 0
        assert filter(is_even, range(10)) == [0, 2, 4, 6, 8]

    def test_filter_positive(self):
        """测试正数过滤"""
        from vools.curried import filter
        assert filter(lambda x: x > 0, [-1, 0, 1, 2, -3]) == [1, 2]

    def test_filter_empty(self):
        """测试空列表"""
        from vools.curried import filter
        assert filter(lambda x: True, []) == []

    def test_filter_curried(self):
        """测试柯里化"""
        from vools.curried import filter
        positives = filter(lambda x: x > 0)
        assert positives([-1, 0, 1, 2, -3]) == [1, 2]


class TestReduce:
    """测试 reduce 函数"""

    def test_reduce_basic(self):
        """测试基本功能"""
        from vools.curried import reduce
        add = lambda x, y: x + y
        assert reduce(add, [1, 2, 3]) == 6

    def test_reduce_with_initializer(self):
        """测试带初始值"""
        from vools.curried import reduce
        add = lambda x, y: x + y
        assert reduce(add, [1, 2, 3], 10) == 16

    def test_reduce_product(self):
        """测试连乘"""
        from vools.curried import reduce
        mul = lambda x, y: x * y
        assert reduce(mul, [1, 2, 3, 4]) == 24

    def test_reduce_empty_with_initializer(self):
        """测试空列表带初始值"""
        from vools.curried import reduce
        assert reduce(lambda x, y: x + y, [], 10) == 10

    def test_reduce_string(self):
        """测试字符串连接"""
        from vools.curried import reduce
        assert reduce(lambda x, y: x + y, ['a', 'b', 'c']) == 'abc'


class TestCompose:
    """测试 compose 函数"""

    def test_compose_basic(self):
        """测试基本功能"""
        from vools.curried import compose
        double = lambda x: x * 2
        add_one = lambda x: x + 1
        composed = compose(add_one, double)
        assert composed(5) == 11

    def test_compose_three_funcs(self):
        """测试三个函数组合"""
        from vools.curried import compose
        add_one = lambda x: x + 1
        double = lambda x: x * 2
        square = lambda x: x ** 2
        # compose 从右到左: square(double(add_one(5))) = square(12) = 144
        composed = compose(square, double, add_one)
        assert composed(5) == 144

    def test_compose_empty(self):
        """测试空组合"""
        from vools.curried import compose
        composed = compose()
        assert composed(5) == 5


class TestPipe:
    """测试 pipe 函数"""

    def test_pipe_basic(self):
        """测试基本功能"""
        from vools.curried import pipe
        double = lambda x: x * 2
        add_one = lambda x: x + 1
        assert pipe(5, double, add_one) == 11

    def test_pipe_three_funcs(self):
        """测试三个函数管道"""
        from vools.curried import pipe
        add_one = lambda x: x + 1
        double = lambda x: x * 2
        square = lambda x: x ** 2
        # pipe 从左到右: square(double(add_one(5))) = square(12) = 144
        assert pipe(5, add_one, double, square) == 144


# ============================================================================
# Test Collection Functions - 集合函数测试
# ============================================================================

class TestUnique:
    """测试 unique 函数"""

    def test_unique_basic(self):
        """测试基本功能"""
        from vools.curried import unique
        assert unique([1, 2, 2, 3, 1, 4]) == [1, 2, 3, 4]

    def test_unique_preserves_order(self):
        """测试保持顺序"""
        from vools.curried import unique
        assert unique([3, 1, 2, 1, 3]) == [3, 1, 2]

    def test_unique_with_key(self):
        """测试带键函数"""
        from vools.curried import unique
        assert unique(['a', 'A', 'b'], key=str.lower) == ['a', 'b']

    def test_unique_empty(self):
        """测试空列表"""
        from vools.curried import unique
        assert unique([]) == []

    def test_unique_strings(self):
        """测试字符串"""
        from vools.curried import unique
        assert unique(['a', 'b', 'a', 'c', 'b']) == ['a', 'b', 'c']


class TestGroupby:
    """测试 groupby 函数"""

    def test_groupby_basic(self):
        """测试基本功能"""
        from vools.curried import groupby
        result = groupby(lambda x: x % 2, range(5))
        assert result == {0: [0, 2, 4], 1: [1, 3]}

    def test_groupby_string_key(self):
        """测试字符串键函数"""
        from vools.curried import groupby
        result = groupby(str.lower, ['A', 'b', 'C', 'a', 'B'])
        assert result == {'a': ['A', 'a'], 'b': ['b', 'B'], 'c': ['C']}

    def test_groupby_empty(self):
        """测试空列表"""
        from vools.curried import groupby
        assert groupby(lambda x: x, []) == {}


class TestPartition:
    """测试 partition 函数"""

    def test_partition_basic(self):
        """测试基本功能"""
        from vools.curried import partition
        assert partition(3, range(10)) == [[0, 1, 2], [3, 4, 5], [6, 7, 8], [9]]

    def test_partition_even_split(self):
        """测试完全分割"""
        from vools.curried import partition
        assert partition(2, ['a', 'b', 'c', 'd']) == [['a', 'b'], ['c', 'd']]

    def test_partition_remainder(self):
        """测试有余数"""
        from vools.curried import partition
        assert partition(2, ['a', 'b', 'c']) == [['a', 'b'], ['c']]

    def test_partition_empty(self):
        """测试空列表"""
        from vools.curried import partition
        assert partition(3, []) == []


class TestFirstSecondLast:
    """测试 first, second, last 函数"""

    def test_first_basic(self):
        """测试 first 基本功能"""
        from vools.curried import first
        assert first(range(10)) == 0

    def test_first_empty(self):
        """测试空列表"""
        from vools.curried import first
        assert first([]) is None

    def test_first_default(self):
        """测试默认值"""
        from vools.curried import first
        assert first([], default=-1) == -1

    def test_second_basic(self):
        """测试 second 基本功能"""
        from vools.curried import second
        assert second(range(10)) == 1

    def test_last_basic(self):
        """测试 last 基本功能"""
        from vools.curried import last
        assert last(range(10)) == 9

    def test_last_empty(self):
        """测试 last 空列表"""
        from vools.curried import last
        assert last([]) is None


class TestNth:
    """测试 nth 函数"""

    def test_nth_basic(self):
        """测试基本功能"""
        from vools.curried import nth
        assert nth(0, range(10)) == 0
        assert nth(5, range(10)) == 5
        assert nth(9, range(10)) == 9

    def test_nth_out_of_bounds(self):
        """测试越界"""
        from vools.curried import nth
        assert nth(10, range(5)) is None
        assert nth(10, range(5), default=-1) == -1

    def test_nth_negative(self):
        """测试负索引"""
        from vools.curried import nth
        assert nth(-1, range(10)) == 9


# ============================================================================
# Test Math Functions - 数学函数测试
# ============================================================================

class TestMathBasic:
    """测试基础数学函数"""

    def test_add(self):
        """测试加法"""
        from vools.curried import add
        assert add(1, 2) == 3
        assert add(1)(2) == 3
        assert add(1.5, 2.5) == 4.0

    def test_sub(self):
        """测试减法"""
        from vools.curried import sub
        assert sub(5, 2) == 3
        assert sub(5)(2) == 3

    def test_mul(self):
        """测试乘法"""
        from vools.curried import mul
        assert mul(2, 3) == 6
        assert mul(2)(3) == 6

    def test_div(self):
        """测试除法"""
        from vools.curried import div
        assert div(6, 2) == 3.0
        assert div(6)(2) == 3.0

    def test_floordiv(self):
        """测试整除"""
        from vools.curried import floordiv
        assert floordiv(7, 2) == 3
        assert floordiv(7)(2) == 3

    def test_mod(self):
        """测试取模"""
        from vools.curried import mod
        assert mod(7, 2) == 1
        assert mod(7)(2) == 1

    def test_pow(self):
        """测试幂"""
        from vools.curried import pow
        assert pow(2, 3) == 8
        assert pow(2)(3) == 8
        assert pow(9)(0.5) == 3.0


class TestMathIncDec:
    """测试 inc, dec, neg, abs 函数"""

    def test_inc(self):
        """测试 inc"""
        from vools.curried import inc
        assert inc(5) == 6
        assert inc(-3) == -2

    def test_dec(self):
        """测试 dec"""
        from vools.curried import dec
        assert dec(5) == 4
        assert dec(-3) == -4

    def test_neg(self):
        """测试 neg"""
        from vools.curried import neg
        assert neg(5) == -5
        assert neg(-3) == 3

    def test_abs(self):
        """测试 abs"""
        from vools.curried import abs
        assert abs(-5) == 5
        assert abs(3) == 3


class TestMathMinMaxSum:
    """测试 min, max, sum 函数"""

    def test_sum(self):
        """测试 sum"""
        from vools.curried import sum
        assert sum([1, 2, 3, 4, 5]) == 15

    def test_product(self):
        """测试连乘"""
        from vools.curried import product
        assert product([1, 2, 3, 4]) == 24

    def test_mean(self):
        """测试平均值"""
        from vools.curried import mean
        assert mean([1, 2, 3, 4, 5]) == 3.0

    def test_median_odd(self):
        """测试奇数中位数"""
        from vools.curried import median
        assert median([1, 2, 3, 4, 5]) == 3

    def test_median_even(self):
        """测试偶数中位数"""
        from vools.curried import median
        assert median([1, 2, 3, 4]) == 2.5


# ============================================================================
# Test String Functions - 字符串函数测试
# ============================================================================

class TestStringBasic:
    """测试基础字符串函数"""

    def test_join(self):
        """测试 join"""
        from vools.curried import join
        assert join('-', ['a', 'b', 'c']) == 'a-b-c'
        assert join(', ', ['apple', 'banana']) == 'apple, banana'

    def test_split(self):
        """测试 split"""
        from vools.curried import split
        assert split('-', 'a-b-c') == ['a', 'b', 'c']

    def test_lower(self):
        """测试 lower"""
        from vools.curried import lower
        assert lower('HELLO') == 'hello'

    def test_upper(self):
        """测试 upper"""
        from vools.curried import upper
        assert upper('hello') == 'HELLO'

    def test_capitalize(self):
        """测试 capitalize"""
        from vools.curried import capitalize
        assert capitalize('hello world') == 'Hello world'

    def test_title(self):
        """测试 title"""
        from vools.curried import title
        assert title('hello world') == 'Hello World'


class TestStringReplace:
    """测试字符串替换函数"""

    def test_replace(self):
        """测试 replace"""
        from vools.curried import replace
        assert replace('o', '0', 'hello') == 'hell0'
        assert replace('o', '0', 'hello', count=1) == 'hell0'

    def test_replace_all(self):
        """测试全部替换"""
        from vools.curried import replace
        assert replace('a', 'b', 'aaa') == 'bbb'


class TestStringStrip:
    """测试字符串去空格函数"""

    def test_strip(self):
        """测试 strip"""
        from vools.curried import strip
        assert strip('  hello  ') == 'hello'
        assert strip('...hello...', '.') == 'hello'

    def test_lstrip(self):
        """测试 lstrip"""
        from vools.curried import lstrip
        assert lstrip('  hello') == 'hello'

    def test_rstrip(self):
        """测试 rstrip"""
        from vools.curried import rstrip
        assert rstrip('hello  ') == 'hello'


# ============================================================================
# Test Predicate Functions - 谓词函数测试
# ============================================================================

class TestPredicateBasic:
    """测试基础谓词函数"""

    def test_is_none(self):
        """测试 is_none"""
        from vools.curried import is_none
        assert is_none(None) is True
        assert is_none(0) is False

    def test_is_not_none(self):
        """测试 is_not_none"""
        from vools.curried import is_not_none
        assert is_not_none(None) is False
        assert is_not_none(0) is True

    def test_is_eq(self):
        """测试 is_eq"""
        from vools.curried import is_eq
        assert is_eq(5)(5) is True
        assert is_eq(5)(3) is False

    def test_is_ne(self):
        """测试 is_ne"""
        from vools.curried import is_ne
        assert is_ne(5)(3) is True
        assert is_ne(5)(5) is False


class TestPredicateComparison:
    """测试比较谓词函数"""

    def test_is_lt(self):
        """测试 is_lt"""
        from vools.curried import is_lt
        assert is_lt(3)(5) is True
        assert is_lt(5)(3) is False

    def test_is_gt(self):
        """测试 is_gt"""
        from vools.curried import is_gt
        assert is_gt(5)(3) is True
        assert is_gt(3)(5) is False

    def test_is_le(self):
        """测试 is_le"""
        from vools.curried import is_le
        assert is_le(3)(5) is True
        assert is_le(5)(3) is False
        assert is_le(5)(5) is True

    def test_is_ge(self):
        """测试 is_ge"""
        from vools.curried import is_ge
        assert is_ge(5)(3) is True
        assert is_ge(3)(5) is False
        assert is_ge(5)(5) is True


class TestPredicateIn:
    """测试 in 谓词函数"""

    def test_is_in(self):
        """测试 is_in"""
        from vools.curried import is_in
        assert is_in([1, 2, 3])(2) is True
        assert is_in([1, 2, 3])(5) is False

    def test_is_not_in(self):
        """测试 is_not_in"""
        from vools.curried import is_not_in
        assert is_not_in([1, 2, 3])(5) is True
        assert is_not_in([1, 2, 3])(2) is False


class TestIsinstance:
    """测试 isinstance 函数"""

    def test_isinstance_basic(self):
        """测试基本功能"""
        from vools.curried import isinstance_
        assert isinstance_(int)(5) is True
        assert isinstance_(str)(5) is False

    def test_isinstance_tuple(self):
        """测试元组类型"""
        from vools.curried import isinstance_
        assert isinstance_((int, float))(5) is True


# ============================================================================
# Test Composition Functions - 组合函数测试
# ============================================================================

class TestJuxt:
    """测试 juxt 函数"""

    def test_juxt_basic(self):
        """测试基本功能"""
        from vools.curried import juxt
        double = lambda x: x * 2
        triple = lambda x: x * 3
        result = juxt(double, triple, lambda x: x + 1)(5)
        assert result == [10, 15, 6]

    def test_juxt_single_func(self):
        """测试单个函数"""
        from vools.curried import juxt
        result = juxt(lambda x: x * 2)(5)
        assert result == [10]


class TestMemoize:
    """测试 memoize 函数"""

    def test_memoize_basic(self):
        """测试基本功能"""
        from vools.curried import memoize
        call_count = [0]

        @memoize
        def expensive(x):
            call_count[0] += 1
            return x * 2

        assert expensive(5) == 10
        assert expensive(5) == 10  # 缓存命中
        assert call_count[0] == 1


class TestTap:
    """测试 tap 函数"""

    def test_tap_basic(self):
        """测试基本功能"""
        from vools.curried import tap
        result = []
        value = tap(lambda x: result.append(x), 5)
        assert value == 5
        assert result == [5]


# ============================================================================
# Test Integration Tests - 集成测试
# ============================================================================

class TestIntegration:
    """集成测试"""

    def test_map_filter_reduce(self):
        """测试 map, filter, reduce 组合"""
        from vools.curried import map, filter, reduce

        result = reduce(
            lambda x, y: x + y,
            map(
                lambda x: x * 2,
                filter(lambda x: x > 0, [-1, 0, 1, 2, 3])
            )
        )
        assert result == 12  # (1*2 + 2*2 + 3*2) = 6 + 6 = 12

    def test_compose_with_pipe(self):
        """测试 compose 和 pipe 组合"""
        from vools.curried import compose, pipe, map, filter

        transform = compose(
            lambda x: x * 2,
            sum,
            lambda x: filter(lambda v: v > 0, x)
        )

        result = transform([-2, -1, 0, 1, 2, 3])
        assert result == 12

    def test_groupby_unique(self):
        """测试 groupby 和 unique 组合"""
        from vools.curried import groupby, unique, map

        data = [1, 2, 2, 3, 3, 3, 4, 4, 4, 4]
        # 先分组，再统计每组个数
        result = map(len, groupby(lambda x: x, data).values())
        assert result == [1, 2, 3, 4]


# ============================================================================
# Test Edge Cases - 边界条件测试
# ============================================================================

class TestEdgeCases:
    """边界条件测试"""

    def test_empty_iterables(self):
        """测试空可迭代对象"""
        from vools.curried import map, filter, reduce, unique, groupby

        assert map(lambda x: x * 2, []) == []
        assert filter(lambda x: x > 0, []) == []
        assert reduce(lambda x, y: x + y, []) is None
        assert unique([]) == []
        assert groupby(lambda x: x, []) == {}

    def test_single_element(self):
        """测试单元素"""
        from vools.curried import map, filter, reduce, first, last, nth

        assert map(lambda x: x * 2, [5]) == [10]
        assert filter(lambda x: x > 0, [5]) == [5]
        assert reduce(lambda x, y: x + y, [5]) == 5
        assert first([5]) == 5
        assert last([5]) == 5
        assert nth(0, [5]) == 5

    def test_large_numbers(self):
        """测试大数"""
        from vools.curried import add, sub, mul, div

        assert add(10**10, 10**10) == 2 * 10**10
        assert mul(10**5, 10**5) == 10**10

    def test_negative_numbers(self):
        """测试负数"""
        from vools.curried import add, sub, mul, filter

        assert add(-5, -3) == -8
        assert sub(-5, 3) == -8
        assert mul(-5, -3) == 15
        assert filter(lambda x: x < 0, [-3, -2, 0, 1, 2]) == [-3, -2]


# ============================================================================
# Test Thread Safety - 线程安全测试
# ============================================================================

class TestThreadSafety:
    """线程安全测试"""

    def test_concurrent_memoize(self):
        """测试 memoize 并发访问"""
        from vools.curried import memoize

        @memoize
        def expensive(x):
            time.sleep(0.01)
            return x * 2

        results = []
        def worker(x):
            results.append(expensive(x))

        threads = [threading.Thread(target=worker, args=(5,)) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(r == 10 for r in results)


# ============================================================================
# 运行测试
# ============================================================================

def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("vools.curried 测试套件")
    print("=" * 60)

    test_classes = [
        TestIdentity,
        TestConst,
        TestFlip,
        TestMap,
        TestFilter,
        TestReduce,
        TestCompose,
        TestPipe,
        TestUnique,
        TestGroupby,
        TestPartition,
        TestFirstSecondLast,
        TestNth,
        TestMathBasic,
        TestMathIncDec,
        TestMathMinMaxSum,
        TestStringBasic,
        TestStringReplace,
        TestStringStrip,
        TestPredicateBasic,
        TestPredicateComparison,
        TestPredicateIn,
        TestIsinstance,
        TestJuxt,
        TestMemoize,
        TestTap,
        TestIntegration,
        TestEdgeCases,
        TestThreadSafety,
    ]

    total_tests = 0
    passed_tests = 0
    failed_tests = []

    for test_class in test_classes:
        print(f"\n{test_class.__name__}:")
        instance = test_class()
        methods = [m for m in dir(instance) if m.startswith('test_')]

        for method_name in methods:
            total_tests += 1
            method = getattr(instance, method_name)
            try:
                method()
                print(f"  [OK] {method_name}")
                passed_tests += 1
            except Exception as e:
                print(f"  [FAIL] {method_name}: {e}")
                failed_tests.append((test_class.__name__, method_name, str(e)))

    print("\n" + "=" * 60)
    print(f"测试结果: {passed_tests}/{total_tests} 通过")
    print(f"覆盖率: {passed_tests/total_tests*100:.1f}%")
    print("=" * 60)

    if failed_tests:
        print("\n失败的测试:")
        for cls_name, method_name, error in failed_tests:
            print(f"  {cls_name}.{method_name}: {error}")
        return False

    return True


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
