"""
derive.py 单元测试

覆盖 create_derive 工厂、四种 kind（instance / static / property / class）、
名称推断、错误检测等。
"""
import unittest

from vools.oop.derive import (
    create_derive,
    derive,
    property_derive,
    static_derive,
    class_derive,
    descriptor_derive,
)


# =========================================================================
# 辅助函数 / 类
# =========================================================================
def add(self, x):
    """实例方法样例：self.x + x"""
    return self.x + x


def greet(cls):
    """类方法样例：返回类名问候"""
    return f"Hello from {cls.__name__}"


def compute(a, b):
    """静态方法样例：纯计算"""
    return a * b + 1


def get_value(self):
    """属性样例：返回 self._value * 2"""
    return self._value * 2


# =========================================================================
# 基础功能测试
# =========================================================================
class TestCreateDeriveFactory(unittest.TestCase):
    """create_derive 工厂函数测试"""

    def test_default_kind_is_instance(self):
        """默认 kind 为 instance"""
        d = create_derive()
        self.assertIsNotNone(d)

    def test_all_valid_kinds(self):
        """所有合法 kind 都能创建装饰器"""
        for kind in ('instance', 'static', 'property', 'class'):
            with self.subTest(kind=kind):
                d = create_derive(kind)
                self.assertIsNotNone(d)

    def test_invalid_kind_raises(self):
        """非法 kind 抛出 ValueError"""
        with self.assertRaises(ValueError):
            create_derive('invalid')

    def test_invalid_kind_raises_empty(self):
        """空字符串 kind 抛出 ValueError"""
        with self.assertRaises(ValueError):
            create_derive('')


class TestInstanceDerive(unittest.TestCase):
    """实例方法扩展测试"""

    def test_positional_arg_method(self):
        """位置参数：自动推断方法名"""
        @derive(add)
        class Foo:
            def __init__(self, x):
                self.x = x

        obj = Foo(10)
        self.assertEqual(obj.add(5), 15)

    def test_kwarg_method(self):
        """关键字参数：key 作为方法名"""
        @derive(add=add)
        class Foo:
            def __init__(self, x):
                self.x = x

        obj = Foo(10)
        self.assertEqual(obj.add(3), 13)

    def test_multiple_methods(self):
        """同时扩展多个方法"""
        def sub(self, x):
            return self.x - x

        @derive(add, sub=sub)
        class Foo:
            def __init__(self, x):
                self.x = x

        obj = Foo(10)
        self.assertEqual(obj.add(5), 15)
        self.assertEqual(obj.sub(3), 7)

    def test_method_has_correct_name(self):
        """扩展后的方法 __name__ 与原函数一致"""
        @derive(add)
        class Foo:
            x = 0

        self.assertEqual(Foo.add.__name__, 'add')

    def test_instance_method_receives_self(self):
        """实例方法正确接收 self"""
        seen = {}

        def capture_self(self):
            seen['self'] = self
            return self

        @derive(capture_self)
        class Foo:
            pass

        obj = Foo()
        result = obj.capture_self()
        self.assertIs(result, obj)
        self.assertIs(seen['self'], obj)


class TestPropertyDerive(unittest.TestCase):
    """属性扩展测试"""

    def test_property_access(self):
        """property 作为属性访问，不需要括号"""
        @property_derive(get_value)
        class Foo:
            def __init__(self, v):
                self._value = v

        obj = Foo(21)
        self.assertEqual(obj.get_value, 42)

    def test_property_is_readonly(self):
        """property 默认只读"""
        @property_derive(get_value)
        class Foo:
            _value = 10

        obj = Foo()
        with self.assertRaises(AttributeError):
            obj.get_value = 99

    def test_property_kwarg_name(self):
        """关键字参数指定属性名"""
        @property_derive(double=get_value)
        class Foo:
            _value = 5

        self.assertEqual(Foo().double, 10)


class TestWritablePropertyDerive(unittest.TestCase):
    """可写属性扩展测试"""

    def test_writable_property_getter_setter(self):
        """(getter, setter) 元组创建可写属性"""
        def get_x(self):
            return self._x

        def set_x(self, value):
            self._x = value

        @property_derive(x=(get_x, set_x))
        class Foo:
            def __init__(self, v):
                self._x = v

        obj = Foo(10)
        self.assertEqual(obj.x, 10)
        obj.x = 20
        self.assertEqual(obj.x, 20)
        self.assertEqual(obj._x, 20)

    def test_writable_property_with_validation(self):
        """setter 中进行值验证"""
        def get_age(self):
            return self._age

        def set_age(self, value):
            if value < 0:
                raise ValueError("age cannot be negative")
            self._age = value

        @property_derive(age=(get_age, set_age))
        class Person:
            def __init__(self, age):
                self._age = age

        p = Person(25)
        self.assertEqual(p.age, 25)
        p.age = 30
        self.assertEqual(p.age, 30)
        with self.assertRaises(ValueError):
            p.age = -1

    def test_writable_property_with_deleter(self):
        """(getter, setter, deleter) 三元组支持删除"""
        deleted = []

        def get_x(self):
            return self._x

        def set_x(self, value):
            self._x = value

        def del_x(self):
            deleted.append(id(self))
            del self._x

        @property_derive(x=(get_x, set_x, del_x))
        class Foo:
            def __init__(self):
                self._x = 100

        obj = Foo()
        self.assertEqual(obj.x, 100)
        obj.x = 200
        self.assertEqual(obj.x, 200)
        del obj.x
        # 验证 deleter 被调用
        self.assertIn(id(obj), deleted)
        # 实例属性 _x 被删除
        self.assertFalse(hasattr(obj, '_x'))

    def test_writable_property_setter_none(self):
        """setter 为 None 时只读"""
        def get_x(self):
            return self._x

        @property_derive(x=(get_x, None))
        class Foo:
            _x = 42

        obj = Foo()
        self.assertEqual(obj.x, 42)
        with self.assertRaises(AttributeError):
            obj.x = 99

    def test_writable_property_only_setter(self):
        """只有 setter 没有 getter（getter=None）"""
        _store = {}

        def set_x(self, value):
            _store[id(self)] = value

        @property_derive(x=(None, set_x))
        class Foo:
            pass

        obj = Foo()
        obj.x = 42
        self.assertEqual(_store[id(obj)], 42)

    def test_writable_property_inheritance(self):
        """可写属性被子类继承"""
        def get_x(self):
            return self._x

        def set_x(self, value):
            self._x = value * 2

        @property_derive(x=(get_x, set_x))
        class Base:
            _x = 0

        class Child(Base):
            pass

        obj = Child()
        obj.x = 10
        self.assertEqual(obj._x, 20)  # setter 被调用

    def test_writable_property_kwarg_multiple(self):
        """多个可写属性同时定义"""
        def get_a(self):
            return self._a

        def set_a(self, v):
            self._a = v

        def get_b(self):
            return self._b

        def set_b(self, v):
            self._b = v

        @property_derive(a=(get_a, set_a), b=(get_b, set_b))
        class Foo:
            _a = 1
            _b = 2

        obj = Foo()
        self.assertEqual(obj.a, 1)
        self.assertEqual(obj.b, 2)
        obj.a = 10
        obj.b = 20
        self.assertEqual(obj.a, 10)
        self.assertEqual(obj.b, 20)

    def test_writable_property_class_level_access_returns_descriptor(self):
        """类级别访问返回 property 描述符"""
        def get_x(self):
            return self._x

        def set_x(self, v):
            self._x = v

        @property_derive(x=(get_x, set_x))
        class Foo:
            pass

        # 类级别访问应该返回 property 对象
        self.assertIsInstance(Foo.__dict__['x'], property)


class TestPropertyTupleValidation(unittest.TestCase):
    """property 元组验证测试"""

    def test_invalid_tuple_length_raises(self):
        """元组长度不为 2 或 3 抛出 TypeError"""
        def get_x(self):
            return self._x

        with self.assertRaises(TypeError):
            @property_derive(x=(get_x,))
            class Foo:
                pass

        with self.assertRaises(TypeError):
            @property_derive(x=(get_x, get_x, get_x, get_x))
            class Foo:
                pass

    def test_invalid_tuple_content_raises(self):
        """元组中包含非 callable 且非 None 的元素抛出 TypeError"""
        def get_x(self):
            return self._x

        with self.assertRaises(TypeError):
            @property_derive(x=(get_x, "not callable"))
            class Foo:
                pass


class TestStaticDerive(unittest.TestCase):
    """静态方法扩展测试"""

    def test_static_method(self):
        """静态方法无需 self/cls"""
        @static_derive(compute)
        class Foo:
            pass

        self.assertEqual(Foo.compute(3, 4), 13)

    def test_static_on_instance(self):
        """通过实例也能调用静态方法"""
        @static_derive(compute)
        class Foo:
            pass

        obj = Foo()
        self.assertEqual(obj.compute(2, 5), 11)

    def test_static_kwarg_name(self):
        """关键字参数指定静态方法名"""
        @static_derive(calc=compute)
        class Foo:
            pass

        self.assertEqual(Foo.calc(3, 3), 10)


class TestClassDerive(unittest.TestCase):
    """类方法扩展测试"""

    def test_class_method(self):
        """类方法接收 cls"""
        @class_derive(greet)
        class Bar:
            pass

        self.assertEqual(Bar.greet(), 'Hello from Bar')

    def test_class_method_on_instance(self):
        """通过实例也能调用类方法"""
        @class_derive(greet)
        class Bar:
            pass

        obj = Bar()
        self.assertEqual(obj.greet(), 'Hello from Bar')

    def test_class_method_sees_subclass(self):
        """类方法在子类上调用时 cls 是子类"""
        @class_derive(greet)
        class Base:
            pass

        class Child(Base):
            pass

        self.assertEqual(Child.greet(), 'Hello from Child')

    def test_class_kwarg_name(self):
        """关键字参数指定类方法名"""
        @class_derive(hi=greet)
        class Baz:
            pass

        self.assertEqual(Baz.hi(), 'Hello from Baz')


# =========================================================================
# 名称推断测试
# =========================================================================
class TestNameInference(unittest.TestCase):
    """_infer_name 名称推断测试"""

    def test_named_function(self):
        """具名函数使用 __name__"""
        def my_func(self):
            pass

        @derive(my_func)
        class Foo:
            pass

        self.assertTrue(hasattr(Foo, 'my_func'))

    def test_lambda_with_non_self_param(self):
        """lambda 推断最后一个非 self/cls 参数名"""
        # lambda self, value: ...  -> 应推断为 'value'
        @derive(lambda self, value: value * 2)
        class Foo:
            pass

        obj = Foo()
        self.assertEqual(obj.value(5), 10)

    def test_lambda_only_self_falls_back(self):
        """只有 self 的 lambda 回退到 fallback 名"""
        @derive(lambda self: 42)
        class Foo:
            pass

        obj = Foo()
        # 回退名 derived_0
        self.assertEqual(obj.derived_0(), 42)

    def test_kwarg_overrides_inferred_name(self):
        """关键字参数名优先于推断名"""
        @derive(my_alias=lambda self, x: x)
        class Foo:
            pass

        obj = Foo()
        self.assertEqual(obj.my_alias(99), 99)


# =========================================================================
# 错误处理测试
# =========================================================================
class TestErrorHandling(unittest.TestCase):
    """错误检测测试"""

    def test_non_callable_positional_arg(self):
        """非可调用位置参数抛出 TypeError"""
        with self.assertRaises(TypeError):
            @derive(123)
            class Foo:
                pass

    def test_non_callable_kwarg(self):
        """非可调用关键字参数抛出 TypeError"""
        with self.assertRaises(TypeError):
            @derive(bad='not callable')
            class Foo:
                pass

    def test_duplicate_name_raises(self):
        """重复方法名抛出 ValueError"""
        def method_a(self):
            pass

        with self.assertRaises(ValueError):
            @derive(method_a, method_a)
            class Foo:
                pass

    def test_duplicate_name_kwarg_conflicts_positional(self):
        """关键字参数与位置参数同名抛出 ValueError"""
        def action(self):
            pass

        with self.assertRaises(ValueError):
            @derive(action, action=action)
            class Foo:
                pass

    def test_decorating_non_class_raises(self):
        """装饰非类对象抛出 TypeError"""
        with self.assertRaises(TypeError):
            derive(add)(42)

    def test_decorating_non_class_raises_kwarg(self):
        """装饰非类对象（关键字形式）抛出 TypeError"""
        with self.assertRaises(TypeError):
            derive(add=add)("not a class")


# =========================================================================
# 预置装饰器测试
# =========================================================================
class TestPredefinedDecorators(unittest.TestCase):
    """预置 derive / property_derive / static_derive / class_derive 测试"""

    def test_derive_is_instance_kind(self):
        """derive 等价于 create_derive('instance')"""
        @derive(add)
        class Foo:
            def __init__(self, x):
                self.x = x

        obj = Foo(10)
        self.assertEqual(obj.add(5), 15)

    def test_property_derive_is_property_kind(self):
        """property_derive 等价于 create_derive('property')"""
        @property_derive(get_value)
        class Foo:
            _value = 7

        self.assertEqual(Foo().get_value, 14)

    def test_static_derive_is_static_kind(self):
        """static_derive 等价于 create_derive('static')"""
        @static_derive(compute)
        class Foo:
            pass

        self.assertEqual(Foo.compute(2, 3), 7)

    def test_class_derive_is_class_kind(self):
        """class_derive 等价于 create_derive('class')"""
        @class_derive(greet)
        class Foo:
            pass

        self.assertEqual(Foo.greet(), 'Hello from Foo')


# =========================================================================
# 边界情况测试
# =========================================================================
class TestEdgeCases(unittest.TestCase):
    """边界情况测试"""

    def test_empty_decorator(self):
        """空装饰器不添加任何方法"""
        @derive()
        class Foo:
            x = 1

        obj = Foo()
        self.assertEqual(obj.x, 1)

    def test_method_does_not_leak_to_other_classes(self):
        """扩展方法不会泄漏到其他类"""
        @derive(add)
        class Foo:
            x = 10

        class Bar:
            x = 100

        self.assertFalse(hasattr(Bar, 'add'))
        self.assertTrue(hasattr(Foo, 'add'))

    def test_inheritance_gets_derived_methods(self):
        """子类继承父类的扩展方法"""
        @derive(add)
        class Base:
            def __init__(self, x):
                self.x = x

        class Child(Base):
            pass

        obj = Child(20)
        self.assertEqual(obj.add(5), 25)

    def test_override_derived_method_in_subclass(self):
        """子类可以覆盖扩展方法"""
        @derive(add)
        class Base:
            x = 10

        class Child(Base):
            def add(self, x):
                return self.x - x

        obj = Child()
        self.assertEqual(obj.add(3), 7)

    def test_property_with_lambda(self):
        """property 支持 lambda（只有 self 参数，回退到 derived_0）"""
        @property_derive(lambda self: self._x + 1)
        class Foo:
            _x = 99

        self.assertEqual(Foo().derived_0, 100)

    def test_static_with_lambda(self):
        """static 支持 lambda（推断最后一个参数名）"""
        @static_derive(lambda a, b: a ** b)
        class Foo:
            pass

        self.assertEqual(Foo.b(2, 10), 1024)

    def test_class_with_lambda(self):
        """class 支持 lambda（只有 cls 参数，回退到 derived_0）"""
        @class_derive(lambda cls: cls.__name__)
        class MyClass:
            pass

        self.assertEqual(MyClass.derived_0(), 'MyClass')


# =========================================================================
# 描述符扩展测试
# =========================================================================
class TypedDescriptor:
    """类型检查描述符（用于测试）"""
    def __init__(self, name, expected_type):
        self.name = name
        self.expected_type = expected_type
        self._values = {}  # id(obj) -> value

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return self._values.get(id(obj))

    def __set__(self, obj, value):
        if not isinstance(value, self.expected_type):
            raise TypeError(f"{self.name} must be {self.expected_type.__name__}")
        self._values[id(obj)] = value

    def __delete__(self, obj):
        self._values.pop(id(obj), None)


class AutoNamedDescriptor:
    """自动命名描述符（用于测试类自动实例化）"""
    def __init__(self, name='default'):
        self.name = name
        self._values = {}

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return self._values.get(id(obj))

    def __set__(self, obj, value):
        self._values[id(obj)] = value


class TestDescriptorDerive(unittest.TestCase):
    """描述符扩展测试"""

    def test_descriptor_instance_positional(self):
        """位置参数传入描述符实例"""
        @descriptor_derive(TypedDescriptor('age', int))
        class Person:
            pass

        p = Person()
        p.age = 25
        self.assertEqual(p.age, 25)

    def test_descriptor_instance_kwarg(self):
        """关键字参数传入描述符实例"""
        @descriptor_derive(age=TypedDescriptor('age', int))
        class Person:
            pass

        p = Person()
        p.age = 30
        self.assertEqual(p.age, 30)

    def test_descriptor_class_auto_instantiate(self):
        """描述符类自动用属性名实例化"""
        @descriptor_derive(age=AutoNamedDescriptor)
        class Person:
            pass

        p = Person()
        p.age = 25
        self.assertEqual(p.age, 25)
        # 验证描述符的 name 被正确设置
        self.assertEqual(Person.__dict__['age'].name, 'age')

    def test_descriptor_type_checking(self):
        """描述符执行类型检查"""
        @descriptor_derive(age=TypedDescriptor('age', int))
        class Person:
            pass

        p = Person()
        with self.assertRaises(TypeError):
            p.age = "not an int"

    def test_descriptor_delete(self):
        """描述符支持删除"""
        @descriptor_derive(data=TypedDescriptor('data', str))
        class Foo:
            pass

        obj = Foo()
        obj.data = "hello"
        self.assertEqual(obj.data, "hello")
        del obj.data
        self.assertIsNone(obj.data)

    def test_descriptor_class_level_access(self):
        """类级别访问返回描述符实例"""
        desc = TypedDescriptor('value', int)

        @descriptor_derive(value=desc)
        class Foo:
            pass

        # 类级别访问应该返回描述符对象
        self.assertIs(Foo.__dict__['value'], desc)

    def test_descriptor_independent_per_instance(self):
        """每个实例有独立的描述符存储"""
        @descriptor_derive(x=TypedDescriptor('x', int))
        class Foo:
            pass

        a = Foo()
        b = Foo()
        a.x = 10
        b.x = 20
        self.assertEqual(a.x, 10)
        self.assertEqual(b.x, 20)

    def test_descriptor_multiple(self):
        """多个描述符同时定义"""
        @descriptor_derive(
            name=TypedDescriptor('name', str),
            age=TypedDescriptor('age', int)
        )
        class Person:
            pass

        p = Person()
        p.name = "Alice"
        p.age = 30
        self.assertEqual(p.name, "Alice")
        self.assertEqual(p.age, 30)

    def test_descriptor_inheritance(self):
        """描述符被子类继承"""
        @descriptor_derive(value=TypedDescriptor('value', int))
        class Base:
            pass

        class Child(Base):
            pass

        obj = Child()
        obj.value = 42
        self.assertEqual(obj.value, 42)

    def test_descriptor_without_setter_allows_shadow(self):
        """没有 __set__ 的描述符（非数据描述符）可以被实例属性覆盖"""
        class NonDataDesc:
            def __init__(self, name):
                self.name = name
            def __get__(self, obj, objtype=None):
                return "from descriptor"

        @descriptor_derive(x=NonDataDesc('x'))
        class Foo:
            pass

        obj = Foo()
        # 初始值来自描述符
        self.assertEqual(obj.x, "from descriptor")
        # 非数据描述符不阻止实例属性覆盖
        obj.x = "shadowed"
        self.assertEqual(obj.x, "shadowed")


class TestDescriptorValidation(unittest.TestCase):
    """描述符验证测试"""

    def test_non_descriptor_raises(self):
        """非描述符对象抛出 TypeError"""
        with self.assertRaises(TypeError):
            @descriptor_derive(123)
            class Foo:
                pass

    def test_non_descriptor_kwarg_raises(self):
        """非描述符关键字参数抛出 TypeError"""
        with self.assertRaises(TypeError):
            @descriptor_derive(x="not a descriptor")
            class Foo:
                pass

    def test_descriptor_class_without_name_param(self):
        """描述符类没有 name 参数时回退到无参实例化"""
        class SimpleDesc:
            def __init__(self):
                self._values = {}
            def __get__(self, obj, objtype=None):
                if obj is None:
                    return self
                return self._values.get(id(obj))
            def __set__(self, obj, value):
                self._values[id(obj)] = value

        @descriptor_derive(data=SimpleDesc)
        class Foo:
            pass

        obj = Foo()
        obj.data = "test"
        self.assertEqual(obj.data, "test")

    def test_descriptor_class_cannot_instantiate_raises(self):
        """无法自动实例化的描述符类抛出 TypeError"""
        class BadDesc:
            def __init__(self, required_arg):
                pass
            def __get__(self, obj, objtype=None):
                pass

        with self.assertRaises(TypeError):
            @descriptor_derive(x=BadDesc)
            class Foo:
                pass


class TestCreateDeriveWithDescriptor(unittest.TestCase):
    """create_derive 工厂与 descriptor kind 测试"""

    def test_descriptor_kind_accepted(self):
        """descriptor 是合法的 kind"""
        d = create_derive('descriptor')
        self.assertIsNotNone(d)

    def test_descriptor_kind_in_all_kinds(self):
        """所有合法 kind 包含 descriptor"""
        for kind in ('instance', 'static', 'property', 'class', 'descriptor'):
            with self.subTest(kind=kind):
                d = create_derive(kind)
                self.assertIsNotNone(d)

    def test_predefined_descriptor_derive(self):
        """预置 descriptor_derive 可用"""
        @descriptor_derive(age=TypedDescriptor('age', int))
        class Person:
            pass

        p = Person()
        p.age = 25
        self.assertEqual(p.age, 25)


if __name__ == '__main__':
    unittest.main()
