"""
测试占位符实现模块 placeholder_impl.py
"""

import pytest
from vools.functional.placeholder_impl import X, _X, _MethodWrapper, _ChainedResult


class TestXPlaceholder:
    """测试 X 占位符类"""
    
    def test_singleton(self):
        """测试单例特性"""
        instance1 = _X()
        instance2 = _X()
        assert instance1 is instance2
        assert X is instance1
    
    def test_attr_access(self):
        """测试属性访问返回缓存的方法包装器"""
        wrapper1 = X.strip
        wrapper2 = X.strip
        assert wrapper1 is wrapper2
    
    def test_empty_call_returns_identity(self):
        """测试 X() 返回恒等函数"""
        identity = X()
        assert identity('hello') == 'hello'
        assert identity(42) == 42
    
    def test_bound_value_chained_call(self):
        """测试绑定值后的链式调用"""
        result = X('  hello  ').strip().val
        assert result == 'hello'
    
    def test_complex_chained_call(self):
        """测试复杂链式调用"""
        result = X('  hello,world  ').strip().split(',').val
        assert result == ['hello', 'world']


class TestMethodWrapper:
    """测试方法包装器"""
    
    def test_equality(self):
        """测试 X.strip == X.strip()"""
        assert X.strip == X.strip()
    
    def test_hash(self):
        """测试哈希值"""
        wrapper1 = X.strip
        wrapper2 = X.strip
        assert hash(wrapper1) == hash(wrapper2)
    
    def test_no_args_call(self):
        """测试无参数调用返回缓存的lambda"""
        fn = X.strip()
        assert fn('  hello  ') == 'hello'
    
    def test_with_args_call(self):
        """测试带参数调用返回新的lambda"""
        fn = X.strip(',')
        assert fn(',hello,') == 'hello'
    
    def test_parameterized_call_does_not_affect_cache(self):
        """测试带参数调用不影响缓存"""
        X.strip(',')  # 带参数调用
        fn = X.strip()  # 获取无参版本
        assert fn('  hello  ') == 'hello'
    
    def test_various_methods(self):
        """测试各种方法"""
        assert X.upper()('hello') == 'HELLO'
        assert X.lower()('HELLO') == 'hello'
        assert X.replace('l', 'r')('hello') == 'herro'
    
    def test_split_methods(self):
        """测试 split 方法"""
        assert X.split()('a b c') == ['a', 'b', 'c']
        assert X.split(',')('a,b,c') == ['a', 'b', 'c']


class TestChainedResult:
    """测试链式结果包装器"""
    
    def test_val_property(self):
        """测试 val 属性获取最终值"""
        result = _ChainedResult(42)
        assert result.val == 42
    
    def test_str_repr(self):
        """测试字符串表示"""
        result = _ChainedResult('hello')
        assert str(result) == 'hello'
        assert repr(result) == "'hello'"
    
    def test_chained_method_call(self):
        """测试链式方法调用"""
        result = _ChainedResult('  hello  ')
        wrapped = result.strip
        assert isinstance(wrapped, _MethodWrapper)
        final = wrapped().val
        assert final == 'hello'


class TestIntegration:
    """集成测试"""
    
    def test_integration_with_seq(self):
        """测试与 Seq 的集成"""
        from vools.data.seq import Seq
        
        # 使用 X 作为映射函数
        result = Seq.of('  a  ', '  b  ', '  c  ').map(X.strip()).as_list()
        assert result == ['a', 'b', 'c']
        
        # 使用带参数的 X
        result2 = Seq.of(',a,', ',b,', ',c,').map(X.strip(',')).as_list()
        assert result2 == ['a', 'b', 'c']
    
    def test_curried_usage(self):
        """测试柯里化用法"""
        from vools.decorators.curried import curried_map
        
        # 使用 X 作为 curried_map 的参数
        result = curried_map(X.strip())(['  hello  ', '  world  '])
        assert result == ['hello', 'world']