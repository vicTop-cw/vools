#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试 curried 模块中的柯里化函数
"""

import sys
import os

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vools.decorators import (
    curried_map, curried_filter, curried_reduce, compose, pipe, curried_pipe,
    add, mul, sub, div,
    and_, or_, not_,
    identity, const, flip, apply, curried_apply
)


def test_higher_order_functions():
    """测试高阶函数"""
    print("=== 测试高阶函数 ===")
    
    # 测试 curried_map
    double = lambda x: x * 2
    assert curried_map(double, [1, 2, 3]) == [2, 4, 6]
    assert curried_map(double)([1, 2, 3]) == [2, 4, 6]
    print("[OK] curried_map 测试通过")
    
    # 测试 curried_filter
    is_even = lambda x: x % 2 == 0
    assert curried_filter(is_even, [1, 2, 3, 4]) == [2, 4]
    assert curried_filter(is_even)([1, 2, 3, 4]) == [2, 4]
    print("[OK] curried_filter 测试通过")
    
    # 测试 curried_reduce
    add_func = lambda x, y: x + y
    assert curried_reduce(add_func, [1, 2, 3]) == 6
    assert curried_reduce(add_func)([1, 2, 3]) == 6
    assert curried_reduce(add_func, [1, 2, 3], 10) == 16
    print("[OK] curried_reduce 测试通过")
    
    # 测试 compose
    add_one = lambda x: x + 1
    composed = compose(add_one, double)
    assert composed(5) == 11
    print("[OK] compose 测试通过")
    
    # 测试 pipe
    result = pipe(5, double, add_one)
    assert result == 11
    print("[OK] pipe 测试通过")
    
    # 测试 curried_pipe
    result = curried_pipe(5, double, add_one)
    assert result == 11
    assert curried_pipe(5)(double, add_one) == 11
    print("[OK] curried_pipe 测试通过")


def test_math_functions():
    """测试数学函数"""
    print("\n=== 测试数学函数 ===")
    
    # 测试 add
    assert add(1, 2) == 3
    assert add(1)(2) == 3
    print("[OK] add 测试通过")
    
    # 测试 mul
    assert mul(2, 3) == 6
    assert mul(2)(3) == 6
    print("[OK] mul 测试通过")
    
    # 测试 sub
    assert sub(5, 2) == 3
    assert sub(5)(2) == 3
    print("[OK] sub 测试通过")
    
    # 测试 div
    assert div(6, 2) == 3.0
    assert div(6)(2) == 3.0
    print("[OK] div 测试通过")


def test_logic_functions():
    """测试逻辑函数"""
    print("\n=== 测试逻辑函数 ===")
    
    # 测试 and_
    assert and_(True, False) is False
    assert and_(True)(True) is True
    print("[OK] and_ 测试通过")
    
    # 测试 or_
    assert or_(True, False) is True
    assert or_(False)(False) is False
    print("[OK] or_ 测试通过")
    
    # 测试 not_
    assert not_(True) is False
    assert not_(False) is True
    print("[OK] not_ 测试通过")


def test_util_functions():
    """测试工具函数"""
    print("\n=== 测试工具函数 ===")
    
    # 测试 identity
    assert identity(5) == 5
    assert identity("hello") == "hello"
    print("[OK] identity 测试通过")
    
    # 测试 const
    always_five = const(5)
    assert always_five(10) == 5
    assert const("hello", "world") == "hello"
    print("[OK] const 测试通过")
    
    # 测试 flip
    subtract = lambda a, b: a - b
    flipped_subtract = flip(subtract)
    assert flipped_subtract(2, 5) == 3  # 相当于 subtract(5, 2)
    print("[OK] flip 测试通过")
    
    # 测试 apply
    add_func = lambda a, b: a + b
    assert apply(add_func, 1, 2) == 3
    print("[OK] apply 测试通过")
    
    # 测试 curried_apply
    assert curried_apply(add_func, 1, 2) == 3
    assert curried_apply(add_func)(1, 2) == 3
    print("[OK] curried_apply 测试通过")


if __name__ == "__main__":
    try:
        test_higher_order_functions()
        test_math_functions()
        test_logic_functions()
        test_util_functions()
        print("\n[SUCCESS] 所有测试通过！")
    except Exception as e:
        print(f"\n[ERROR] 测试失败: {e}")
        import traceback
        traceback.print_exc()
