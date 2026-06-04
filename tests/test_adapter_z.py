#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试适配器 Z：智能切换 X 和 _ 的行为
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from vools.functional.adapter_z import Z
from vools.functional.placeholder_impl import _MethodWrapper, _ChainedResult
from vools.functional.placeholder import _IndexHolder


class TestAdapterZ:
    """测试适配器 Z 的功能"""
    
    def test_z_is_singleton(self):
        """测试 Z 是单例"""
        from vools.functional.adapter_z import Z as Z2
        assert Z is Z2
    
    def test_z_attr_access_returns_method_wrapper(self):
        """测试属性访问返回 _MethodWrapper（X 风格）"""
        result = Z.upper
        assert isinstance(result, _MethodWrapper)
    
    def test_z_method_call_x_style(self):
        """测试方法调用走 X 风格"""
        # Z.upper() 返回无参函数
        upper_fn = Z.upper()
        result = upper_fn('hello')
        assert result == 'HELLO'
        
        # Z.strip() 返回无参函数
        strip_fn = Z.strip()
        result = strip_fn('  hello  ')
        assert result == 'hello'
    
    def test_z_method_with_args_x_style(self):
        """测试带参数的方法调用走 X 风格"""
        # Z.split(',') 返回带参函数
        split_fn = Z.split(',')
        result = split_fn('a,b,c')
        assert result == ['a', 'b', 'c']
        
        # Z.replace() 返回需要完整参数的函数
        replace_fn = Z.replace()
        result = replace_fn('hello', 'l', 'r')
        assert result == 'herro'
        
        # Z.replace('l', 'r') 返回带部分参数的函数
        replace_fn2 = Z.replace('l', 'r')
        result = replace_fn2('hello')
        assert result == 'herro'
    
    def test_z_method_equality_x_style(self):
        """测试方法等值比较（X 风格）"""
        assert Z.strip == Z.strip()
    
    def test_z_arithmetic_operations_underscore_style(self):
        """测试数学运算走 _ 风格"""
        # Z + 1
        add_fn = Z + 1
        assert isinstance(add_fn, _IndexHolder)
        result = add_fn(5)
        assert result == 6
        
        # Z * 2
        mul_fn = Z * 2
        assert isinstance(mul_fn, _IndexHolder)
        result = mul_fn(5)
        assert result == 10
        
        # Z - 1
        sub_fn = Z - 1
        assert isinstance(sub_fn, _IndexHolder)
        result = sub_fn(5)
        assert result == 4
    
    def test_z_comparison_operations_underscore_style(self):
        """测试比较运算走 _ 风格"""
        # Z > 5
        gt_fn = Z > 5
        assert isinstance(gt_fn, _IndexHolder)
        result = gt_fn(10)
        assert result == True
        result = gt_fn(3)
        assert result == False
        
        # Z == 'test'
        eq_fn = Z == 'test'
        assert isinstance(eq_fn, _IndexHolder)
        result = eq_fn('test')
        assert result == True
        result = eq_fn('hello')
        assert result == False
    
    def test_z_index_access_underscore_style(self):
        """测试索引访问走 _ 风格"""
        # Z[0]
        get_first = Z[0]
        assert isinstance(get_first, _IndexHolder)
        result = get_first([1, 2, 3])
        assert result == 1
        
        # Z['key']
        get_key = Z['name']
        assert isinstance(get_key, _IndexHolder)
        result = get_key({'name': 'Alice', 'age': 30})
        assert result == 'Alice'
    
    def test_z_call_with_value_x_style(self):
        """测试调用绑定值走 X 风格"""
        # Z(value) 返回绑定值的包装器
        chained = Z('  hello,world  ')
        assert isinstance(chained, _ChainedResult)
        
        # 继续链式调用
        result = chained.strip().split(',').val
        assert result == ['hello', 'world']
    
    def test_z_call_empty_returns_identity(self):
        """测试 Z() 返回恒等函数"""
        identity = Z()
        result = identity('hello')
        assert result == 'hello'
        result = identity(42)
        assert result == 42
    
    def test_z_chained_method_calls(self):
        """测试链式方法调用"""
        # Z(value).method().method().val 风格
        result = Z('  hello,world  ').strip().split(',').val
        assert result == ['hello', 'world']
        
        # 更复杂的链式调用
        result = Z('Hello World').lower().replace('world', 'vools').val
        assert result == 'hello vools'
    
    def test_z_mixed_usage(self):
        """测试混合使用场景"""
        # 先用 _ 风格构建表达式，再用 X 风格调用方法
        # 这是两个独立的使用模式，不能直接混合
        # 但可以分别使用各自的功能
        
        # _ 风格：构建表达式
        add_fn = Z + 1
        result = add_fn(5)
        assert result == 6
        
        # X 风格：方法调用
        upper_fn = Z.upper()
        result = upper_fn('hello')
        assert result == 'HELLO'
    
    def test_z_with_vic_classes(self):
        """测试 Z 与 vic 类的配合使用"""
        from vools import vicList, vicText
        
        # 使用 Z 的 _ 风格与 vicList 配合
        lst = vicList([1, 2, 3, 4, 5])
        filtered = lst.filter(Z > 2)
        assert list(filtered._data) == [3, 4, 5]
        
        # 使用 Z 的 X 风格与 vicText 配合
        txt = vicText('hello world')
        # 注意：vicText 已经有 upper 方法，不需要用 Z
        result = txt.upper()
        assert str(result) == 'HELLO WORLD'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
