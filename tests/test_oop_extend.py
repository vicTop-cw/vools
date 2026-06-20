"""
extend.py / clone 装饰器单元测试
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from vools.oop import clone


class TestCloneBasic(unittest.TestCase):
    """clone 基础功能测试"""

    def test_position_args_attributes(self):
        """位置参数设置类属性"""
        @clone(None, 'name:TestName', 'age:18', 'pi:3.14', 'flag:True')
        class MyClass:
            pass

        obj = MyClass()
        self.assertEqual(obj.name, 'TestName')
        self.assertEqual(obj.age, 18)
        self.assertEqual(obj.pi, 3.14)
        self.assertEqual(obj.flag, True)

    def test_negative_number_and_hex(self):
        """负数、十六进制等字面量解析"""
        @clone(None, 'negative:-5', 'hex_value:0x1a')
        class MyClass:
            pass

        obj = MyClass()
        self.assertEqual(obj.negative, -5)
        self.assertEqual(obj.hex_value, 26)

    def test_expression_property(self):
        """=> 表达式属性"""
        @clone(None,
               'first:Hello',
               'last:World',
               'full => self.first + " " + self.last')
        class MyClass:
            pass

        obj = MyClass()
        self.assertEqual(obj.full, 'Hello World')

    def test_expression_property_with_type(self):
        """带类型转换的 => 表达式属性"""
        @clone(None,
               'count:10',
               'double:int => self.count * 2')
        class MyClass:
            pass

        obj = MyClass()
        self.assertEqual(obj.double, 20)

    def test_none_attr(self):
        """以分号结尾的表达式返回 None"""
        @clone(None,
               'name:Test',
               'none_attr => self.name;')
        class MyClass:
            pass

        obj = MyClass()
        self.assertIsNone(obj.none_attr)


class TestCloneCustomMethods(unittest.TestCase):
    """自定义方法测试"""

    def test_dict_method(self):
        """字典类型自定义方法"""
        @clone(None,
               append={'return': 'self'})
        class MyClass(list):
            pass

        obj = MyClass()
        result = obj.append(1)
        self.assertEqual(result, obj)
        self.assertEqual(obj, [1])

    def test_dict_method_with_args(self):
        """字典类型自定义方法带固定参数"""
        @clone(None,
               insert={'args': (0, 99), 'return': 'self'})
        class MyClass(list):
            pass

        obj = MyClass()
        result = obj.insert()
        self.assertEqual(result, obj)
        self.assertEqual(obj, [99])

    def test_function_method(self):
        """函数类型自定义方法"""
        def greet(self, name):
            return f'Hello, {name}'

        @clone(None, greet=greet)
        class MyClass:
            pass

        obj = MyClass()
        self.assertEqual(obj.greet('Alice'), 'Hello, Alice')

    def test_string_lambda_method(self):
        """字符串类型 lambda 方法"""
        @clone(None, add='a, b => a + b')
        class MyClass:
            pass

        obj = MyClass()
        self.assertEqual(obj.add(3, 4), 7)

    def test_string_method_with_semicolon(self):
        """字符串类型方法含分号"""
        @clone(None, calc='a, b => x = a + b; y = x * 2; y')
        class MyClass:
            pass

        obj = MyClass()
        self.assertEqual(obj.calc(3, 4), 14)


class TestCloneCopyFrom(unittest.TestCase):
    """copy_from 功能测试"""

    def test_copy_from_class(self):
        """从类复制单个方法"""
        class Source:
            def multiply(self, a, b):
                return a * b

        @clone(None, copy_from=(Source, 'multiply'))
        class MyClass:
            pass

        obj = MyClass()
        self.assertEqual(obj.multiply(4, 5), 20)

    def test_copy_from_with_return_result(self):
        """从类复制方法并处理返回值"""
        class Source:
            def multiply(self, a, b):
                return a * b

        @clone(None, copy_from=(Source, 'multiply', None, None, '=> result *= 2; result + 10'))
        class MyClass:
            pass

        obj = MyClass()
        # 4*5=20 -> 20*2=40 -> 40+10=50
        self.assertEqual(obj.multiply(4, 5), 50)

    def test_copy_from_instance(self):
        """从实例复制方法"""
        class Source:
            def __init__(self, factor):
                self.factor = factor
            def scale(self, x):
                return x * self.factor

        @clone(None, copy_from=(Source(3), 'scale'))
        class MyClass:
            pass

        obj = MyClass()
        self.assertEqual(obj.scale(5), 15)


class TestCloneCopyListFrom(unittest.TestCase):
    """copy_list_from 功能测试"""

    def test_copy_list_from_methods(self):
        """批量从类复制方法"""
        class Source:
            def add(self, a, b):
                return a + b
            def sub(self, a, b):
                return a - b

        @clone(None, copy_list_from=(Source, ['add', 'sub']))
        class MyClass:
            pass

        obj = MyClass()
        self.assertEqual(obj.add(5, 3), 8)
        self.assertEqual(obj.sub(5, 3), 2)

    def test_copy_list_from_with_dir_filter(self):
        """使用 dir_filter 批量复制方法"""
        class Source:
            def add(self, a, b):
                return a + b
            def sub(self, a, b):
                return a - b
            def _private(self):
                return 'private'

        @clone(None, copy_list_from=(Source, lambda x: not x.startswith('_')))
        class MyClass:
            pass

        obj = MyClass()
        self.assertEqual(obj.add(1, 2), 3)
        self.assertEqual(obj.sub(1, 2), -1)
        self.assertFalse(hasattr(obj, '_private'))

    def test_copy_list_from_with_return_result(self):
        """批量复制方法并处理返回值"""
        class Source:
            def add(self, a, b):
                return a + b

        @clone(None, copy_list_from=(Source, ['add'], None, None, '=> temp = result + 10; temp * 2'))
        class MyClass:
            pass

        obj = MyClass()
        # 2+3=5 -> 5+10=15 -> 15*2=30
        self.assertEqual(obj.add(2, 3), 30)


class TestCloneResultShell(unittest.TestCase):
    """result_shell 功能测试"""

    def test_result_shell(self):
        """批量处理方法返回结果"""
        @clone(None, result_shell=(lambda result: f'[{result}]', lambda x: x.startswith('get_')))
        class MyClass:
            def get_value(self):
                return 42
            def normal(self):
                return 'normal'

        obj = MyClass()
        self.assertEqual(obj.get_value(), '[42]')
        self.assertEqual(obj.normal(), 'normal')

    def test_result_shell_expression(self):
        """result_shell 返回表达式字符串"""
        @clone(None, result_shell=(lambda result: '=> result + 1', lambda x: x.startswith('get_')))
        class MyClass:
            def get_value(self):
                return 41

        obj = MyClass()
        self.assertEqual(obj.get_value(), 42)


class TestCloneEdgeCases(unittest.TestCase):
    """边界情况测试"""

    def test_clone_without_none(self):
        """不使用 None 直接装饰类"""
        @clone('name:Direct')
        class MyClass:
            pass

        obj = MyClass()
        self.assertEqual(obj.name, 'Direct')

    def test_clone_with_base_class(self):
        """从基类继承属性"""
        class Base:
            def __init__(self):
                self.value = 10

        @clone(None, 'doubled => self.value * 2')
        class MyClass(Base):
            pass

        obj = MyClass()
        self.assertEqual(obj.doubled, 20)

    def test_clone_list_attr(self):
        """列表字面量属性"""
        @clone(None, 'items:[1, 2, 3]')
        class MyClass:
            pass

        obj = MyClass()
        self.assertEqual(obj.items, [1, 2, 3])

    def test_clone_dict_attr(self):
        """字典字面量属性"""
        @clone(None, 'config:{"a": 1, "b": 2}')
        class MyClass:
            pass

        obj = MyClass()
        self.assertEqual(obj.config, {'a': 1, 'b': 2})


if __name__ == '__main__':
    unittest.main()
