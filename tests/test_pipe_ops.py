"""
测试管道操作模块
"""

import pytest
from vools.vic import vicList
from vools.functional.pipe_ops import P, Ops, O


class TestPipeOps:
    """测试管道操作模块"""
    
    def test_p_instance_creation(self):
        """测试创建 P 实例"""
        p = P(lambda x: x * 2)
        assert str(p).startswith("pipe_func")
    
    def test_ops_filter(self):
        """测试 Ops.filter 操作"""
        numbers = vicList([1, 2, 3, 4, 5])
        result = numbers | Ops.filter(lambda x: x % 2 == 0)
        assert result == [2, 4]
    
    def test_ops_map(self):
        """测试 Ops.map 操作"""
        numbers = vicList([1, 2, 3, 4, 5])
        result = numbers | Ops.map(lambda x: x * 2)
        assert result == [2, 4, 6, 8, 10]
    
    def test_chained_pipe_operations(self):
        """测试链式管道操作"""
        numbers = vicList([1, 2, 3, 4, 5])
        result = numbers | Ops.filter(lambda x: x % 2 == 0) | Ops.map(lambda x: x * 2)
        assert result == [4, 8]
    
    def test_double_arrow_operator(self):
        """测试 >> 操作符"""
        numbers = vicList([1, 2, 3, 4, 5])
        result = numbers >> Ops.map(lambda x: x * 2)
        assert result == [2, 4, 6, 8, 10]
    
    def test_o_shortcut(self):
        """测试 O 快捷方式"""
        numbers = vicList([1, 2, 3, 4, 5])
        result = numbers | O(lambda x: list(x))
        assert result == [1, 2, 3, 4, 5]
    
    def test_ops_do(self):
        """测试 Ops.do 操作"""
        numbers = vicList([1, 2, 3, 4, 5])
        result = numbers | Ops.do(lambda x: None)
        assert result == [1, 2, 3, 4, 5]  # Ops.do 返回列表
    
    def test_ops_sum(self):
        """测试 Ops.sum 操作"""
        numbers = vicList([1, 2, 3, 4, 5])
        result = numbers | Ops.sum()
        assert result == 15
    
    def test_ops_count(self):
        """测试 Ops.count 操作"""
        numbers = vicList([1, 2, 3, 4, 5])
        result = numbers | Ops.count()
        assert result == 5
    
    def test_ops_distinct(self):
        """测试 Ops.distinct 操作"""
        numbers = vicList([1, 2, 2, 3, 3, 3, 4])
        result = numbers | Ops.distinct()
        assert result == [1, 2, 3, 4]
    
    def test_ops_take(self):
        """测试 Ops.take 操作"""
        numbers = vicList([1, 2, 3, 4, 5])
        result = numbers | Ops.take(3)
        assert result == [1, 2, 3]
    
    def test_ops_drop(self):
        """测试 Ops.drop 操作"""
        numbers = vicList([1, 2, 3, 4, 5])
        result = numbers | Ops.drop(2)
        assert result == [3, 4, 5]
    
    def test_ops_string_operations(self):
        """测试字符串操作"""
        text = "  hello world  "
        result = text | Ops.strip() | Ops.upper()
        assert result == "HELLO WORLD"
    
    def test_pipe_with_regular_function_fails(self):
        """测试普通函数不能用于管道操作"""
        numbers = vicList([1, 2, 3, 4, 5])
        
        def double_items(lst):
            return vicList([x * 2 for x in lst])
        
        with pytest.raises(TypeError):
            numbers | double_items
    
    def test_ops_filter_with_string_expression(self):
        """测试 Ops.filter 支持字符串表达式"""
        numbers = vicList([1, 2, 3, 4, 5])
        result = numbers | Ops.filter("x => x % 2 == 0")
        assert result == [2, 4]
    
    def test_ops_map_with_string_expression(self):
        """测试 Ops.map 支持字符串表达式"""
        numbers = vicList([1, 2, 3, 4, 5])
        result = numbers | Ops.map("x => x * 2")
        assert result == [2, 4, 6, 8, 10]
    
    def test_ops_with_underscore_pattern(self):
        """测试 Ops 支持下划线占位符模式"""
        numbers = vicList([1, 2, 3, 4, 5])
        result = numbers | Ops.filter("_ % 2 == 0")
        assert result == [2, 4]
    
    def test_p_instance_with_string_expression(self):
        """测试 P 实例支持字符串表达式"""
        # P 实例直接使用时，接收整个对象而非遍历元素
        p = P("x => x * 2")
        result = 5 | p
        assert result == 10
        result = [1,2,3] >> p
        assert result == [2,4,6]
    
    def test_chained_pipe_with_string_expressions(self):
        """测试链式管道操作使用字符串表达式"""
        numbers = vicList([1, 2, 3, 4, 5])
        result = numbers | Ops.filter("x => x % 2 == 0") | Ops.map("x => x * 2")
        assert result == [4, 8]
    
    def test_o_with_string_expression(self):
        """测试 O 快捷方式支持字符串表达式"""
        numbers = vicList([1, 2, 3, 4, 5])
        result = numbers | O("x => list(x)")
        assert result == [1, 2, 3, 4, 5]