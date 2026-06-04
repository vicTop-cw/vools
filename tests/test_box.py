"""
Box 组件和 box 装饰器的单元测试
"""
import sys
import os

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from datetime import datetime, date
from vools.functional.box import box, Box, setattr_box


class TestBoxBasic:
    """测试 Box 类的基本功能"""
    
    def test_box_wrap_int(self):
        """测试包装整数"""
        b = Box(42)
        assert b.__wrapped__ == 42
        assert int(b) == 42
    
    def test_box_wrap_str(self):
        """测试包装字符串"""
        b = Box("hello")
        assert b.__wrapped__ == "hello"
        assert str(b) == "hello"
    
    def test_box_wrap_dict(self):
        """测试包装字典"""
        d = {"a": 1, "b": 2}
        b = Box(d)
        assert b.__wrapped__ == d
    
    def test_box_wrap_list(self):
        """测试包装列表"""
        lst = [1, 2, 3]
        b = Box(lst)
        assert b.__wrapped__ == lst
    
    def test_box_copy(self):
        """测试复制功能"""
        b = Box([1, 2, 3])
        b_copy = b.copy()
        assert b_copy.__wrapped__ == [1, 2, 3]
        assert b_copy is not b
    
    def test_box_dir(self):
        """测试 __dir__ 方法"""
        b = Box([1, 2, 3])
        dir_result = b.__dir__()
        assert 'append' in dir_result
        assert 'pop' in dir_result
    
    def test_box_hasattr(self):
        """测试 __hasattr__ 方法"""
        b = Box("hello")
        assert b.__hasattr__('upper')
        assert not b.__hasattr__('nonexistent_method')
    
    def test_box_getattr(self):
        """测试 __getattr__ 方法"""
        b = Box("hello")
        upper_func = b.upper
        result = upper_func()
        assert result.__wrapped__ == "HELLO"
    
    def test_box_getattr_not_found(self):
        """测试访问不存在的属性"""
        b = Box("hello")
        with pytest.raises(AttributeError):
            _ = b.nonexistent_method
    
    def test_box_callable(self):
        """测试调用包装的函数"""
        def add(a, b):
            return a + b
        
        b = Box(add)
        result = b(2, 3)
        assert result.__wrapped__ == 5
    
    def test_box_not_callable(self):
        """测试调用非可调用对象"""
        b = Box(42)
        with pytest.raises(TypeError):
            b()


class TestBoxRunMethod:
    """测试 Box.run 方法"""
    
    def test_run_basic(self):
        """测试基本运行功能"""
        b = Box([1, 2, 3])
        result = b.run(sum)
        assert result.__wrapped__ == 6
    
    def test_run_with_func_string(self):
        """测试使用字符串函数"""
        b = Box(5)
        result = b.run("x => x * 2")
        assert result.__wrapped__ == 10
    
    def test_run_unpack_star(self):
        """测试 * 解包"""
        b = Box([1, 2, 3])
        result = b.run(lambda x, y, z: x + y + z, unpack="*")
        assert result.__wrapped__ == 6
    
    def test_run_unpack_kwargs(self):
        """测试 ** 解包"""
        b = Box({"a": 1, "b": 2})
        result = b.run(lambda a, b: a + b, unpack="**")
        assert result.__wrapped__ == 3
    
    def test_run_rerun(self):
        """测试 rerun 模式"""
        b = Box([1, 2, 3])
        result = b.run(lambda x: x * 2, unpack="*", rerun=True)
        # 现在返回的是 vicList，需要转换为列表进行比较
        assert list(result.__wrapped__) == [2, 4, 6]
    
    def test_run_nobox(self):
        """测试 nobox 参数"""
        b = Box(5)
        result = b.run(lambda x: x + 1, nobox=True)
        assert result == 6  # 不包装结果
    
    def test_run_invalid_func(self):
        """测试无效函数参数"""
        b = Box(5)
        with pytest.raises(TypeError):
            b.run(123)


class TestBoxDecorator:
    """测试 box 装饰器"""
    
    def test_box_decorator_basic(self):
        """测试基本装饰器用法"""
        @box
        def add(a, b):
            return a + b
        
        result = add(2, 3)
        assert isinstance(result, Box)
        assert result.__wrapped__ == 5
    
    def test_box_decorator_returns_none(self):
        """测试返回 None"""
        @box
        def do_nothing():
            return None
        
        result = do_nothing()
        assert result is None
    
    def test_box_decorator_chained(self):
        """测试链式调用"""
        @box
        def add_one(x):
            return x + 1
        
        @box
        def multiply_by_two(x):
            return x * 2
        
        result = multiply_by_two(add_one(5))
        assert result.__wrapped__ == 12


class TestSetattrBox:
    """测试 setattr_box 函数"""
    
    def test_setattr_box_basic(self):
        """测试添加方法到 Box 类"""
        def custom_method(self):
            return self.__wrapped__ * 2
        
        setattr_box(custom_method, 'double')
        b = Box(5)
        result = b.double()
        assert result.__wrapped__ == 10
    
    def test_setattr_box_cover_false(self):
        """测试 cover=False 时已存在的属性"""
        with pytest.raises(AttributeError):
            setattr_box(lambda x: x, 'copy', cover=False)
    
    def test_setattr_box_invalid_attr(self):
        """测试无效属性 - 实际行为是返回None"""
        result = setattr_box(123, 'invalid')
        assert result is None


class TestBoxEdgeCases:
    """测试边界情况"""
    
    def test_box_empty_string(self):
        """测试空字符串"""
        b = Box("")
        assert b.__wrapped__ == ""
    
    def test_box_empty_list(self):
        """测试空列表"""
        b = Box([])
        assert b.__wrapped__ == []
    
    def test_box_empty_dict(self):
        """测试空字典"""
        b = Box({})
        assert b.__wrapped__ == {}
    
    def test_box_none_value(self):
        """测试 None 值"""
        b = Box(None)
        assert b.__wrapped__ is None
    
    def test_box_nested_box(self):
        """测试嵌套 Box"""
        b = Box(Box(5))
        assert b.__wrapped__ == 5  # 应该自动解包
    
    def test_box_datetime(self):
        """测试 datetime 对象"""
        now = datetime.now()
        b = Box(now)
        assert b.__wrapped__ == now
    
    def test_box_bytes(self):
        """测试字节串"""
        b = Box(b"hello")
        assert b.__wrapped__ == b"hello"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
