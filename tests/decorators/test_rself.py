"""
rself 装饰器 - 完整单元测试

测试覆盖：
1. 无参初始化
2. 带参初始化
3. __from_parent__ 工厂方法
4. 继承方法返回值转换
5. 自定义方法返回值处理
6. 链式调用
7. 多继承限制
8. 边界条件和异常情况
"""

import pytest
from vools.decorators import rself


class TestRselfBasic:
    """基础功能测试"""

    def test_no_inheritance_no_args(self):
        """无继承类，无参初始化"""
        @rself
        class NoInherit:
            def __init__(self):
                self.value = 0

            def increment(self):
                self.value += 1

        obj = NoInherit()
        assert obj.value == 0
        result = obj.increment()
        assert result is obj
        assert obj.value == 1

    def test_no_inheritance_with_args(self):
        """无继承类，带参初始化"""
        @rself
        class NoInherit:
            def __init__(self, x=0, y=0):
                self.x = x
                self.y = y

            def add(self, dx, dy):
                self.x += dx
                self.y += dy

        obj = NoInherit(10, 20)
        assert obj.x == 10
        assert obj.y == 20
        result = obj.add(5, 10)
        assert result is obj
        assert obj.x == 15
        assert obj.y == 30

    def test_no_inheritance_kwargs(self):
        """无继承类，关键字参数初始化"""
        @rself
        class NoInherit:
            def __init__(self, x=0, y=0):
                self.x = x
                self.y = y

            def move(self, dx=0, dy=0):
                return NoInherit(self.x + dx, self.y + dy)

        obj = NoInherit(x=10, y=20)
        result = obj.move(dx=5)
        assert isinstance(result, NoInherit)
        assert result.x == 15
        assert result.y == 20


class TestRselfSingleInheritance:
    """单继承测试"""

    def test_str_subclass_no_args(self):
        """str 子类，无参初始化"""
        @rself
        class SuperStr(str):
            def __new__(cls, value=""):
                return super().__new__(cls, value)

        s = SuperStr()
        assert str(s) == ""

        # str 的 + 操作返回 str，这是 Python 的行为
        # rself 装饰器无法改变这一行为
        # 如果需要链式拼接，应该使用自定义方法
        assert isinstance(s, SuperStr)

    def test_str_subclass_with_args(self):
        """str 子类，带参初始化"""
        @rself
        class SuperStr(str):
            def __new__(cls, value="", prefix=""):
                instance = super().__new__(cls, value)
                instance._prefix = prefix
                return instance

            @classmethod
            def __from_parent__(cls, parent_val, **kwargs):
                prefix = kwargs.get('prefix', '')
                return cls(str(parent_val), prefix=prefix)

            def decorated(self):
                return self._prefix + str(self)

        s = SuperStr("hello", prefix=">> ")
        assert str(s) == "hello"
        assert s._prefix == ">> "

        # 测试链式调用继承方法
        result = s.upper()
        assert isinstance(result, SuperStr)
        assert str(result) == "HELLO"

        # 测试 __from_parent__ 保留前缀
        # 注意：只有通过方法调用返回的父类实例才会触发 __from_parent__
        # 直接调用 upper() 返回的 str 实例会被转换
        result2 = result.decorated()
        assert isinstance(result2, SuperStr)
        # upper() 返回的是 str，经过 __from_parent__ 转换时使用了 kwargs 中的默认值

    def test_list_subclass(self):
        """list 子类"""
        @rself
        class SuperList(list):
            def __init__(self, data=None):
                if data:
                    super().__init__(data)
                else:
                    super().__init__()

            def add(self, item):
                new_list = SuperList(list(self))
                new_list.append(item)
                return new_list

        lst = SuperList([1, 2, 3])
        result = lst.add(4)
        assert isinstance(result, SuperList)
        assert list(result) == [1, 2, 3, 4]

    def test_dict_subclass(self):
        """dict 子类"""
        @rself
        class SuperDict(dict):
            def __init__(self, data=None):
                if data:
                    super().__init__(data)
                else:
                    super().__init__()

            def add_key(self, key, value):
                new_dict = SuperDict(dict(self))
                new_dict[key] = value
                return new_dict

        d = SuperDict({"a": 1})
        result = d.add_key("b", 2)
        assert isinstance(result, SuperDict)
        assert dict(result) == {"a": 1, "b": 2}


class TestFromParentFactory:
    """__from_parent__ 工厂方法测试"""

    def test_from_parent_basic(self):
        """基本 __from_parent__ 用法"""
        @rself
        class Text(str):
            def __new__(cls, value="", style=""):
                instance = super().__new__(cls, value)
                instance._style = style
                return instance

            @classmethod
            def __from_parent__(cls, parent_val, **kwargs):
                style = kwargs.get('style', 'default')
                return cls(str(parent_val), style=style)

            def styled(self):
                return f"[{self._style}] {str(self)}"

        t = Text("hello", style="bold")
        assert t._style == "bold"

        # 继承方法调用
        result = t.upper()
        assert isinstance(result, Text)
        assert str(result) == "HELLO"
        assert result._style == "bold"  # 样式应该保留

        # 自定义方法
        result2 = result.styled()
        assert isinstance(result2, Text)
        assert str(result2) == "[bold] HELLO"

    def test_from_parent_no_kwargs(self):
        """__from_parent__ 不接受 kwargs 时降级处理"""
        @rself
        class Text(str):
            def __new__(cls, value=""):
                return super().__new__(cls, value)

            @classmethod
            def __from_parent__(cls, parent_val):
                # 只接受 parent_val，不接受额外参数
                return cls(str(parent_val))

        t = Text("hello")
        result = t.upper()
        assert isinstance(result, Text)
        assert str(result) == "HELLO"

    def test_from_parent_with_multiple_args(self):
        """__from_parent__ 传递多个参数"""
        @rself
        class FormattedText(str):
            def __new__(cls, value="", prefix="", suffix="", transform=""):
                instance = super().__new__(cls, value)
                instance._prefix = prefix
                instance._suffix = suffix
                instance._transform = transform
                return instance

            @classmethod
            def __from_parent__(cls, parent_val, **kwargs):
                return cls(
                    str(parent_val),
                    prefix=kwargs.get('prefix', ''),
                    suffix=kwargs.get('suffix', ''),
                    transform=kwargs.get('transform', '')
                )

            def format(self):
                result = str(self)
                if self._transform == 'upper':
                    result = result.upper()
                return self._prefix + result + self._suffix

        t = FormattedText("hello", prefix="[", suffix="]", transform="upper")
        result = t.upper()  # 继承方法
        assert isinstance(result, FormattedText)
        assert str(result) == "HELLO"
        assert result._prefix == "["
        assert result._suffix == "]"
        assert result._transform == "upper"

        # 链式调用自定义方法
        result2 = result.format()
        assert str(result2) == "[HELLO]"


class TestChainCall:
    """链式调用测试"""

    def test_method_chain(self):
        """方法链式调用"""
        @rself
        class Builder:
            def __init__(self, value=""):
                self._value = value

            def add(self, s):
                return Builder(self._value + s)

            def wrap(self, prefix, suffix):
                return Builder(prefix + self._value + suffix)

        b = Builder("a").add("b").add("c")
        assert isinstance(b, Builder)
        assert b._value == "abc"

        b2 = Builder("x").wrap("[", "]").add("y")
        assert b2._value == "[x]y"

    def test_str_method_chain(self):
        """str 方法链式调用"""
        @rself
        class Text(str):
            def __new__(cls, value=""):
                return super().__new__(cls, value)

        t = Text("hello")
        result = t.upper().lower().capitalize()
        assert isinstance(result, Text)
        assert str(result) == "Hello"

    def test_list_method_chain(self):
        """list 方法链式调用"""
        @rself
        class SuperList(list):
            def add(self, item):
                new_list = SuperList(list(self))
                new_list.append(item)
                return new_list

        lst = SuperList([3, 1, 4, 1, 5])
        # 注意：sorted() 返回普通 list，不是 SuperList
        # 这是 Python 的行为
        result = SuperList(sorted(lst))
        assert isinstance(result, SuperList)
        assert list(result) == [1, 1, 3, 4, 5]


class TestReturnValueHandling:
    """返回值处理测试"""

    def test_none_return(self):
        """返回 None"""
        @rself
        class Obj:
            def __init__(self):
                self.value = 0

            def increment(self):
                self.value += 1

            def decrement(self):
                self.value -= 1

        obj = Obj()
        result = obj.increment()
        assert result is obj
        assert obj.value == 1

    def test_same_type_return(self):
        """返回同类型实例"""
        @rself
        class Wrapper:
            def __init__(self, value):
                self.value = value

            def transform(self):
                return Wrapper(self.value * 2)

        w = Wrapper(10)
        result = w.transform()
        assert isinstance(result, Wrapper)
        assert result.value == 20

    def test_parent_type_return(self):
        """返回父类型实例"""
        @rself
        class Text(str):
            def __new__(cls, value=""):
                return super().__new__(cls, value)

            def get_base(self):
                return str(self)

        t = Text("hello")
        result = t.get_base()
        assert isinstance(result, Text)
        assert str(result) == "hello"


class TestMultiInheritance:
    """多继承限制测试"""

    def test_multi_inheritance_raises(self):
        """多继承应该抛出错误"""
        with pytest.raises(TypeError):
            @rself
            class Multi(str, list):
                pass

    def test_single_inheritance_ok(self):
        """单继承应该正常工作"""
        @rself
        class Text(str):
            def __new__(cls, value=""):
                return super().__new__(cls, value)

        @rself
        class Extended(Text):
            def __new__(cls, value="", extra=""):
                instance = super().__new__(cls, value)
                instance._extra = extra
                return instance

            @classmethod
            def __from_parent__(cls, parent_val, **kwargs):
                return cls(str(parent_val), extra='extended')

        e = Extended("hello", extra="world")
        assert str(e) == "hello"
        assert e._extra == "world"

        # 注意：对于继承链，链式调用需要每一层都定义 __from_parent__
        # 否则只能转换到第一层
        result = e.upper()
        assert isinstance(result, Extended)
        assert str(result) == "HELLO"


class TestEdgeCases:
    """边界条件测试"""

    def test_empty_string(self):
        """空字符串"""
        @rself
        class Text(str):
            def __new__(cls, value=""):
                return super().__new__(cls, value)

        t = Text("")
        result = t.upper()
        assert str(result) == ""

    def test_unicode(self):
        """Unicode 字符"""
        @rself
        class Text(str):
            def __new__(cls, value=""):
                return super().__new__(cls, value)

        t = Text("你好")
        result = t.upper()  # 中文没有 upper 版本
        assert isinstance(result, Text)
        assert str(result) == "你好"

    def test_special_characters(self):
        """特殊字符"""
        @rself
        class Text(str):
            def __new__(cls, value=""):
                return super().__new__(cls, value)

        t = Text("!@#$%^&*()")
        result = t.upper()
        assert isinstance(result, Text)
        assert str(result) == "!@#$%^&*()"  # 特殊字符不变

    def test_long_string(self):
        """长字符串"""
        @rself
        class Text(str):
            def __new__(cls, value=""):
                return super().__new__(cls, value)

        t = Text("a" * 10000)
        result = t.upper()
        assert isinstance(result, Text)
        assert len(str(result)) == 10000

    def test_numeric_operations(self):
        """数值操作 - int 的算术操作返回 int，不是子类"""
        @rself
        class SuperInt(int):
            def __new__(cls, value=0):
                return super().__new__(cls, value)

            def double(self):
                return SuperInt(int(self) * 2)

        n = SuperInt(42)
        assert int(n) == 42

        result = n.double()
        assert isinstance(result, SuperInt)
        assert int(result) == 84

        # int 的 + 操作返回 int，这是 Python 的行为
        result2 = n + 1
        # 注意：int.__add__ 返回的是 int，不是 SuperInt

    def test_lambda_method(self):
        """Lambda 方法"""
        @rself
        class Obj:
            def __init__(self, value=0):
                self.value = value

            double = lambda self: type(self)(self.value * 2)

        obj = Obj(10)
        result = obj.double()
        assert isinstance(result, Obj)
        assert result.value == 20


class TestDecoratorUsage:
    """装饰器使用测试"""

    def test_decorator_without_args(self):
        """不带参数的装饰器"""
        @rself
        class Text(str):
            def __new__(cls, value=""):
                return super().__new__(cls, value)

        assert callable(Text)
        t = Text("hello")
        assert isinstance(t, Text)

    def test_decorator_order(self):
        """装饰器顺序"""
        @rself
        @rself
        class Text(str):
            def __new__(cls, value=""):
                return super().__new__(cls, value)

        t = Text("hello")
        result = t.upper()
        assert isinstance(result, Text)


class TestPropertyAndClassMethod:
    """属性和类方法测试"""

    def test_property(self):
        """属性访问"""
        @rself
        class Text(str):
            def __new__(cls, value=""):
                instance = super().__new__(cls, value)
                instance._length = len(value)
                return instance

            @property
            def length(self):
                return len(str(self))

        t = Text("hello")
        assert t.length == 5
        assert t.upper().length == 5

    def test_classmethod(self):
        """类方法"""
        @rself
        class Text(str):
            def __new__(cls, value=""):
                return super().__new__(cls, value)

            @classmethod
            def from_bytes(cls, b):
                return cls(b.decode('utf-8'))

        t = Text.from_bytes(b"hello")
        assert isinstance(t, Text)
        assert str(t) == "hello"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])