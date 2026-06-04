"""
测试柯里化类装饰器模块 curry_decorator.py
"""

import pytest
from vools.decorators.curry_decorator import curry_class, CurriedMethod


@curry_class
class Calculator:
    """测试用的计算器类"""
    
    def __init__(self):
        self.total = 0
    
    def add(self, a: int, b: int, c: int) -> int:
        """三个数相加"""
        self.total = a + b + c
        return self.total
    
    def multiply(self, x: int, y: int) -> int:
        """两个数相乘"""
        self.total = x * y
        return self.total
    
    def power(self, base: int, exponent: int) -> int:
        """幂运算"""
        self.total = base ** exponent
        return self.total
    
    def sum_all(self, a: int, b: int, *args, **kwargs) -> int:
        """可变参数求和"""
        total = a + b + sum(args)
        if kwargs:
            total += sum(kwargs.values())
        self.total = total
        return total
    
    def __call__(self, x: int, y: int, z: int) -> int:
        """调用方法"""
        self.total = x * y + z
        return self.total
    
    def __add__(self, a: int, b: int) -> int:
        """加法运算符"""
        self.total = a + b
        return self.total
    
    def __getitem__(self, index: int, default=None):
        """获取列表项"""
        data = [10, 20, 30, 40, 50]
        if index < len(data):
            return data[index]
        return default


class TestCurryClass:
    """测试 @curry_class 装饰器"""
    
    def test_basic_chained_call(self):
        """测试基本链式调用"""
        calc = Calculator()
        result = calc.add(1).add(2).add(3)
        assert result == 6
    
    def test_grouped_args(self):
        """测试分组参数调用"""
        calc = Calculator()
        result = calc.add(1, 2).add(3)
        assert result == 6
    
    def test_direct_call(self):
        """测试直接调用"""
        calc = Calculator()
        result = calc.add(1, 2, 3)
        assert result == 6
    
    def test_keyword_args(self):
        """测试关键字参数"""
        calc = Calculator()
        result = calc.add(a=1).add(b=2).add(c=3)
        assert result == 6
    
    def test_mixed_args(self):
        """测试混合位置参数和关键字参数"""
        calc = Calculator()
        result = calc.add(1).add(b=2, c=3)
        assert result == 6
    
    def test_mixed_args_order(self):
        """测试先关键字后位置参数"""
        calc = Calculator()
        result = calc.add(a=1).add(2, c=3)
        assert result == 6
    
    def test_multiply_method(self):
        """测试乘法方法"""
        calc = Calculator()
        result = calc.multiply(5).multiply(6)
        assert result == 30
    
    def test_multiply_keyword(self):
        """测试乘法方法关键字参数"""
        calc = Calculator()
        result = calc.multiply(x=7).multiply(y=8)
        assert result == 56
    
    def test_power_method(self):
        """测试幂运算"""
        calc = Calculator()
        result = calc.power(2).power(3)
        assert result == 8


class TestVarargsMethods:
    """测试可变参数方法"""
    
    def test_varargs_basic(self):
        """测试可变参数基础调用"""
        calc = Calculator()
        result = calc.sum_all(1, 2)
        assert result == 3
    
    def test_varargs_chained_with_empty_call(self):
        """测试可变参数链式调用（使用空括号触发执行）"""
        calc = Calculator()
        result = calc.sum_all(1).sum_all(2).sum_all(3, 4).sum_all()
        assert result == 10
    
    def test_varargs_with_keyword(self):
        """测试可变参数带关键字参数"""
        calc = Calculator()
        result = calc.sum_all(1, 2, 3, x=4, y=5)
        assert result == 15
    
    def test_varargs_chained_keyword(self):
        """测试可变参数链式关键字参数"""
        calc = Calculator()
        result = calc.sum_all(1).sum_all(2, x=3).sum_all(y=4).sum_all()
        assert result == 10


class TestMagicMethods:
    """测试魔法方法"""
    
    def test_call_method(self):
        """测试 __call__ 方法"""
        calc = Calculator()
        result = calc.__call__(2, 3, 4)
        assert result == 10
    
    def test_call_chained(self):
        """测试 __call__ 链式调用"""
        calc = Calculator()
        result = calc.__call__(2).__call__(3).__call__(4)
        assert result == 10
    
    def test_add_method(self):
        """测试 __add__ 方法"""
        calc = Calculator()
        result = calc.__add__(5).__add__(3)
        assert result == 8
    
    def test_getitem_method(self):
        """测试 __getitem__ 方法"""
        calc = Calculator()
        result = calc.__getitem__(2)
        assert result == 30
    
    def test_getitem_with_default(self):
        """测试 __getitem__ 带默认值"""
        calc = Calculator()
        result = calc.__getitem__(10, -1)
        assert result == -1


class TestCurriedMethodClass:
    """测试 CurriedMethod 类"""
    
    def test_check_params_complete(self):
        """测试参数检查"""
        def test_func(self, a, b, c):
            return a + b + c
        
        curried = CurriedMethod(
            test_func, None,
            required_params=['a', 'b', 'c'],
            has_varargs=False,
            has_varkw=False,
            all_param_names=['a', 'b', 'c'],
            method_name='test_func',
            collected_args=[1, 2],
            collected_kwargs={}
        )
        
        assert not curried._check_params_complete()
        
        curried2 = CurriedMethod(
            test_func, None,
            required_params=['a', 'b', 'c'],
            has_varargs=False,
            has_varkw=False,
            all_param_names=['a', 'b', 'c'],
            method_name='test_func',
            collected_args=[1, 2, 3],
            collected_kwargs={}
        )
        
        assert curried2._check_params_complete()


class TestErrorHandling:
    """测试错误处理"""
    
    def test_non_class_decoration(self):
        """测试装饰非类对象"""
        with pytest.raises(TypeError):
            @curry_class
            def not_a_class():
                pass


class TestIntegration:
    """集成测试"""
    
    def test_integration_with_seq(self):
        """测试与 Seq 的集成"""
        from vools.data.seq import Seq
        
        calc = Calculator()
        
        # 使用柯里化方法作为 Seq 的函数参数
        result = Seq.of((1, 2), (3, 4), (5, 6)).map(lambda x: calc.multiply(x[0]).multiply(x[1])).as_list()
        assert result == [2, 12, 30]