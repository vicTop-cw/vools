"""
测试整合后的 rself 类装饰器
"""

import pytest
from vools.decorators.rself import rself


@rself
class SuperText(str):
    """增强版字符串类，支持链式调用"""
    
    def append(self, text: str):
        """追加文本"""
        return SuperText(self + text)
    
    def prepend(self, text: str):
        """前置文本"""
        return SuperText(text + self)


@rself
class SuperList(list):
    """增强版列表类，支持链式调用"""
    
    def add(self, item):
        """添加元素"""
        new_list = SuperList(self)
        new_list.append(item)
        return new_list


@rself
class NoInheritance:
    """无继承的类"""
    
    def __init__(self):
        self.value = 0
    
    def increment(self):
        """增加值"""
        self.value += 1
    
    @property
    def doubled(self):
        """返回值的两倍"""
        return self.value * 2


class TestRselfDecorator:
    """测试 rself 装饰器"""
    
    def test_supertext_returns_subclass(self):
        """测试 SuperText 方法返回子类实例"""
        s = SuperText("hello")
        
        # upper() 应该返回 SuperText 类型
        result = s.upper()
        assert isinstance(result, SuperText)
        assert result == "HELLO"
        
        # 链式调用
        chained = SuperText("hello").upper().append(" WORLD")
        assert isinstance(chained, SuperText)
        assert chained == "HELLO WORLD"
    
    def test_superlist_returns_subclass(self):
        """测试 SuperList 方法返回子类实例"""
        lst = SuperList([1, 2, 3])
        
        # add() 应该返回 SuperList 类型
        result = lst.add(4)
        assert isinstance(result, SuperList)
        assert result == [1, 2, 3, 4]
    
    def test_no_inheritance_none_returns_self(self):
        """测试无继承类方法返回 None 时返回自身"""
        obj = NoInheritance()
        
        # increment() 返回 None，应该返回自身
        result = obj.increment()
        assert result is obj
        assert obj.value == 1
    
    def test_no_inheritance_returns_original_type(self):
        """测试无继承类属性返回原类型"""
        obj = NoInheritance()
        
        # doubled 属性返回 int，应该保持不变
        result = obj.doubled
        assert isinstance(result, int)
        assert result == 0  # 初始值为 0，0*2=0
    
    def test_multi_inheritance_raises_error(self):
        """测试多继承抛出错误"""
        with pytest.raises(TypeError):
            @rself
            class MultiInherit(str, list):
                pass


class TestReturnValues:
    """测试返回值处理"""
    
    def test_none_returns_self(self):
        """测试返回 None 时返回自身"""
        @rself
        class Demo:
            def do_nothing(self):
                pass
        
        obj = Demo()
        result = obj.do_nothing()
        assert result is obj
    
    def test_base_instance_returns_subclass(self):
        """测试返回父类实例时转换为子类"""
        @rself
        class SuperInt(int):
            def add(self, other):
                return self + other
        
        obj = SuperInt(5)
        result = obj.add(3)
        assert isinstance(result, SuperInt)
        assert result == 8
    
    def test_other_types_unchanged(self):
        """测试其他类型保持不变"""
        @rself
        class Demo:
            def return_list(self):
                return [1, 2, 3]
            
            def return_dict(self):
                return {"key": "value"}
        
        obj = Demo()
        assert obj.return_list() == [1, 2, 3]
        assert obj.return_dict() == {"key": "value"}


class TestChainedCalls:
    """测试链式调用"""
    
    def test_supertext_chained_calls(self):
        """测试 SuperText 链式调用"""
        result = SuperText("hello").upper().prepend("HI ").append("!")
        assert isinstance(result, SuperText)
        assert result == "HI HELLO!"
    
    def test_superlist_chained_calls(self):
        """测试 SuperList 链式调用"""
        result = SuperList([1, 2]).add(3).add(4)
        assert isinstance(result, SuperList)
        assert result == [1, 2, 3, 4]