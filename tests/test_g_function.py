"""
g 函数的单元测试
"""
import sys
import os

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from vools.functional.arrow_func import g, arrow_func, gene_lambda_func


class TestGFunctionBasic:
    """测试 g 函数的基本功能"""
    
    def test_g_arrow_expression(self):
        """测试箭头表达式"""
        f = g("x, y => x + y")
        assert f(3, 4) == 7
    
    def test_g_single_underscore(self):
        """测试单一下划线模式"""
        f = g("_ + 2 * _")
        assert f(3, 4) == 11
    
    def test_g_indexed_underscore(self):
        """测试索引下划线模式"""
        f = g("_1 + _2")
        assert f(3, 4) == 7
    
    def test_g_lambda_expression(self):
        """测试标准 lambda 表达式"""
        f = g("lambda x: x + 1")
        assert f(5) == 6
    
    def test_g_no_params(self):
        """测试无参数表达式"""
        f = g("3 + 5")
        assert f() == 8
    
    def test_g_single_param(self):
        """测试单参数"""
        f = g("_ * 2")
        assert f(5) == 10
    
    def test_g_multiple_params(self):
        """测试多参数"""
        f = g("_1 * _2 + _3")
        assert f(2, 3, 4) == 10


class TestGFunctionAdvanced:
    """测试 g 函数的高级功能"""
    
    def test_g_with_env(self):
        """测试使用环境变量"""
        env = {"multiplier": 3}
        f = g("_1 * multiplier", env=env)
        assert f(5) == 15
    
    def test_g_complex_expression(self):
        """测试复杂表达式"""
        f = g("_1 ** 2 + _2 ** 2")
        assert f(3, 4) == 25
    
    def test_g_with_semicolon(self):
        """测试分号分隔的多语句"""
        f = g("x = _1 + _2; y = x * 2; y")
        assert f(3, 4) == 14
    
    def test_g_ternary_operator(self):
        """测试三元运算符"""
        f = g("_1 > _2 ? _1 ! _2")
        assert f(5, 3) == 5
        assert f(2, 7) == 7
    
    def test_g_varargs(self):
        """测试可变参数"""
        f = g("*args => sum(args)")
        assert f(1, 2, 3, 4) == 10
    
    def test_g_kwargs(self):
        """测试关键字参数"""
        f = g("**kwargs => sum(kwargs.values())")
        assert f(a=1, b=2, c=3) == 6
    
    def test_g_mixed_params(self):
        """测试混合参数"""
        f = g("a, b, *args, **kwargs => a + b + sum(args) + sum(kwargs.values())")
        assert f(1, 2, 3, 4, x=5, y=6) == 21


class TestGFunctionEdgeCases:
    """测试边界情况"""
    
    def test_g_empty_expression(self):
        """测试空表达式 - 实际行为是抛出 SyntaxError"""
        with pytest.raises(SyntaxError):
            g("")
    
    def test_g_invalid_expression(self):
        """测试无效表达式 - 实际行为是返回无参函数"""
        f = g("x => ")
        assert f() is None
    
    def test_g_mixed_underscore_patterns(self):
        """测试混合下划线模式（应该报错）"""
        with pytest.raises(ValueError):
            g("_ + _1")
    
    def test_g_callable_input(self):
        """测试输入已经是函数"""
        def add(a, b):
            return a + b
        
        f = g(add)
        assert f is add
        assert f(2, 3) == 5


class TestArrowFunc:
    """测试 arrow_func 函数"""
    
    def test_arrow_func_basic(self):
        """测试基本箭头函数"""
        f = arrow_func("x => x + 1")
        assert f(5) == 6
    
    def test_arrow_func_multi_param(self):
        """测试多参数"""
        f = arrow_func("x, y => x * y")
        assert f(3, 4) == 12
    
    def test_arrow_func_varargs(self):
        """测试可变参数"""
        f = arrow_func("*args => sum(args)")
        assert f(1, 2, 3) == 6
    
    def test_arrow_func_kwargs(self):
        """测试关键字参数"""
        f = arrow_func("**kwargs => sum(kwargs.values())")
        assert f(a=1, b=2) == 3
    
    def test_arrow_func_with_env(self):
        """测试使用环境变量"""
        env = {"base": 10}
        f = arrow_func("x => x + base", env=env)
        assert f(5) == 15
    
    def test_arrow_func_empty_body(self):
        """测试空函数体"""
        f = arrow_func(" => ")
        assert f() is None


class TestGeneLambdaFunc:
    """测试 gene_lambda_func 函数"""
    
    def test_gene_lambda_single_mode(self):
        """测试 single 模式"""
        f = gene_lambda_func("_ + _", mode='single')
        assert f(2, 3) == 5
    
    def test_gene_lambda_indexed_mode(self):
        """测试 indexed 模式"""
        f = gene_lambda_func("_1 + _2", mode='indexed')
        assert f(2, 3) == 5
    
    def test_gene_lambda_with_semicolon(self):
        """测试分号分隔的语句"""
        f = gene_lambda_func("x = _1 + _2; y = x * 2; y", mode='indexed')
        assert f(3, 4) == 14
    
    def test_gene_lambda_empty_params(self):
        """测试无参数"""
        f = gene_lambda_func("3 + 5", mode='single')
        assert f() == 8


if __name__ == "__main__":
    pytest.main([__file__, "-v"])