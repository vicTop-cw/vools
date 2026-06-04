"""
测试 vicList 管道操作（只支持 P 实例）
"""

import pytest
from vools.vic import vicList
from vools.functional.pipe_ops import P, Ops, O


class TestVicListPipe:
    """测试 vicList 管道操作"""
    
    def test_pipe_with_p_instance(self):
        """测试使用 P 实例进行管道操作"""
        numbers = vicList([1, 2, 3, 4, 5])
        result = numbers | Ops.filter(lambda x: x % 2 == 0)
        assert result == [2, 4]
    
    def test_pipe_with_double_arrow(self):
        """测试使用 >> 操作符进行管道操作"""
        numbers = vicList([1, 2, 3, 4, 5])
        result = numbers >> Ops.map(lambda x: x * 2)
        assert result == [2, 4, 6, 8, 10]
    
    def test_chained_pipe(self):
        """测试链式管道操作"""
        numbers = vicList([1, 2, 3, 4, 5])
        result = numbers | Ops.filter(lambda x: x % 2 == 0) | Ops.map(lambda x: x * 2)
        assert result == [4, 8]
    
    def test_set_operation_still_works(self):
        """测试集合操作仍然正常工作"""
        numbers = vicList([1, 2, 3, 4, 5])
        other = vicList([4, 5, 6, 7])
        result = numbers | other
        assert set(result) == {1, 2, 3, 4, 5, 6, 7}
    
    def test_regular_function_not_allowed(self):
        """测试普通函数不能用于管道操作"""
        numbers = vicList([1, 2, 3, 4, 5])
        
        def double_items(lst):
            return vicList([x * 2 for x in lst])
        
        with pytest.raises(TypeError):
            numbers | double_items
        
        with pytest.raises(TypeError):
            numbers >> double_items
    
    def test_p_instance_required(self):
        """测试管道操作必须使用 P 实例"""
        numbers = vicList([1, 2, 3, 4, 5])
        
        # 使用 Ops 是可以的（返回 P 实例）
        result = numbers | Ops.do(lambda x: x)
        assert result is not None
        
        # 使用 O 也是可以的（返回 P 实例）
        result = numbers | O(lambda x: x)
        assert result is not None