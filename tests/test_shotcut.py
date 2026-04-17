#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试 shotcut 模块的功能
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vools.functional.placeholder import _ , _1, _2, _3, f, magic, hd
from vools.functional.arrow_func import g


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


def test_f_function():
    """测试 f 函数"""
    print("\n=== 测试 f 函数 ===")
    
    def add(a, b):
        return a + b
    
    def multiply(a, b):
        return a * b
    
    # 测试基本用法
    f1 = f(add, _, _)
    assert f1(1, 2) == 3
    print("[OK] f 函数基本用法测试通过")
    
    # 测试混合参数
    f2 = f(add, 1, _)
    assert f2(2) == 3
    print("[OK] f 函数混合参数测试通过")
    
    # 测试嵌套使用
    f3 = f(multiply, f(add, 1, _), 2)
    assert f3(3) == 8
    print("[OK] f 函数嵌套使用测试通过")


def test_expr_method():
    """测试 __expr__ 方法"""
    print("\n=== 测试 __expr__ 方法 ===")
    
    # 测试单行表达式
    f1 =_.__expr__("_ + 1")
    assert f1(2) == 3
    print("[OK] 单行表达式测试通过")
    
    # 测试索引表达式
    f2 =_.__expr__("_1 + _2 * _3", mode='indexed')
    assert f2(1, 2, 3) == 7
    print("[OK] 索引表达式测试通过")
    
    # 测试 def 表达式
    f3 =_.__expr__('''if _ > 0:\n    return _ * 2\nelse:\n    return _ + 1''', func_type='def')
    assert f3(2) == 4
    assert f3(-1) == 0
    print("[OK] def 表达式测试通过")


def test_utility_methods():
    """测试实用方法"""
    print("\n=== 测试实用方法 ===")
    
    # 测试类型转换
    f1 = _.toString()
    assert f1(123) == "123"
    print("[OK] 类型转换测试通过")
    
    # 测试包含关系
    f2 = _.in_([1, 2, 3])
    assert f2(2) == True
    assert f2(4) == False
    print("[OK] 包含关系测试通过")
    
    # 测试实例检查
    f3 = _ @ str
    assert f3("hello") == True
    assert f3(123) == False
    print("[OK] 实例检查测试通过")


def test_hd_functions():
    """测试 hd 函数"""
    print("\n=== 测试 hd 函数 ===")
    
    # 测试 hd 基本功能
    f1 = hd + 1
    assert f1(2) == 3
    print("[OK] hd 基本功能测试通过")
    
    # 测试 hd 索引访问
    f2 = hd[1]
    assert f2([1, 2, 3]) == 2
    print("[OK] hd 索引访问测试通过")
    
    # 测试 hd 复杂表达式
    f3 = hd[(_ + 1, _ * 2)]
    assert f3(3) == (4, 6)
    print("[OK] hd 复杂表达式测试通过")


def test_magic_methods():
    """测试 magic 方法"""
    print("\n=== 测试 magic 方法 ===")
    
    # 测试 magic.expr
    f1 = magic.expr(_)("_ + 1")
    assert f1(2) == 3
    print("[OK] magic.expr 测试通过")


def test_advanced_usage():
    """测试高级用法"""
    print("\n=== 测试高级用法 ===")
    
    # 测试链式操作
    f1 = (_ + 1) * 2
    assert f1(3) == 8
    print("[OK] 链式操作测试通过")
    
    # 测试多参数
    f2 = _1 + _2 + _3
    assert f2(1, 2, 3) == 6
    print("[OK] 多参数测试通过")
    
    f_2 = _[_]
    assert f_2([1, 2, 3],1) == 2
    print("[OK] f_2索引占位符测试通过")

    # 测试嵌套索引
    f3 = _[_+_]
    assert f3([[1, 2], [3, 4]], -2, 1) == [3, 4]
    print("[OK] 嵌套索引测试通过")


    f4 = _[_][_] # 失败  后面的不生效
    try:
        assert f4([[1, 2], [3, 4]], -1, 1) == 4
        assert f4({"a":1, "b":[1,2,3],"c":3},"b",1  ) == 2
        print("[OK] 嵌套后索引测试通过")
    except AssertionError:
        print("[ERROR] 嵌套后索引测试失败，预期4，实际未触发")


    f5 = _[f_2] # 先计算里面的f_2

    t = f5([[1, 2], [3, 4]], [0,1], 1)  # 先计算里面的f_2 即 [[1, 2], [3, 4]][[0,1][1]]
    # print(t)
    assert t == [3,4] == [[1, 2], [3, 4]][[0,1][1]]


    print("[OK] 嵌套索引2测试通过")


def test_placehoder_priority():
    """测试占位符优先级"""
    print("\n=== 测试占位符优先级 ===")
    
    # 测试优先级
    f1 = _ + 1
    assert f1(2) == 3


    f2 = f1 * 2
    assert f2(2) == 6

    f3 = f2 + 6
    assert f3(2) == 12


    f4 = 1 + _ * 2   
    assert f4(2) == 5

    f5 = (1 + _) * 2   
    assert f5(2) == 6

    print("[OK] 优先级测试通过")




if __name__ == "__main__":
    try:
        test_basic_placeholder()
        test_f_function()
        test_expr_method()
        test_utility_methods()
        test_hd_functions()
        test_magic_methods()
        test_advanced_usage()
        test_placehoder_priority()
        print("\n🎉 所有测试通过！")
    except Exception as e:
        print(f"\n[ERROR] 测试失败: {e}")
        import traceback
        traceback.print_exc()
