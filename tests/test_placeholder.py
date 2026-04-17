#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
直接测试 placeholder 模块的功能
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vools.functional.placeholder import _ , _1, _2, _3, f, magic, hd


def test_basic_placeholder():
    """测试基本占位符功能"""
    print("=== 测试基本占位符功能 ===")
    
    # 测试基本运算符
    f = _ + 1
    assert f(2) == 3
    print("[OK] 基本运算符测试通过")
    
    # 测试二元运算符
    f = _ + _
    assert f(1, 2) == 3
    print("[OK] 二元运算符测试通过")
    
    # 测试索引占位符
    f = _1 + _2
    assert f(1, 2) == 3
    print("[OK] 索引占位符测试通过")
    
    # 测试属性访问
    f = _.upper
    assert f("hello")() == "HELLO"
    print("[OK] 属性访问测试通过")
    
    # 测试索引访问
    f = _[0]
    assert f([1, 2, 3]) == 1
    print("[OK] 索引访问测试通过")
    
    # 测试复杂表达式
    f = _1 * (_2 + _3)
    assert f(2, 3, 4) == 14
    print("[OK] 复杂表达式测试通过")


def test_expr_method():
    """测试 __expr__ 方法"""
    print("\n=== 测试 __expr__ 方法 ===")
    
    # 测试单行表达式
    f1 = _.__expr__("_ + 1")
    assert f1(2) == 3
    print("[OK] 单行表达式测试通过")
    
    # 测试索引表达式
    f2 = _.__expr__("_1 + _2 * _3")
    assert f2(1, 2, 3) == 7
    print("[OK] 索引表达式测试通过")

def test_f_function():
    """测试 f 函数"""
    print("\n=== 测试 f 函数 ===")
    
    def add(a, b):
        return a + b
    
    # 测试基本用法
    f1 = f(add, _, _)
    assert f1(1, 2) == 3
    print("[OK] f 函数基本用法测试通过")


if __name__ == "__main__":
    try:
        test_basic_placeholder()
        test_expr_method()
        test_f_function()
        print("\n[OK] 所有测试通过！")
    except Exception as e:
        print(f"\n[ERROR] 测试失败: {e}")
        import traceback
        traceback.print_exc()
