"""测试 curry 和 overload 装饰器"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vools import curry, overload
from vools.decorators import strict, curry as curry_decorator
from vools.decorators.overload import (
    reset_registry, ParentMode, Strict, Ambiguous
)


def test_overload_default():
    """测试 overload 基本功能（默认模式）"""
    reset_registry()

    @overload
    def process():
        return "无参数"

    @process.register(export_mode=ParentMode)
    def process_one(x):
        return f"一个参数: {x}"

    @process.register(export_mode=ParentMode)
    def process_two(x, y):
        return f"两个参数: {x}, {y}"

    assert process() == "无参数"
    assert process(10) == "一个参数: 10"
    assert process(10, 20) == "两个参数: 10, 20"


def test_overload_class_method():
    """测试 overload 类方法"""
    reset_registry()

    class Test:
        def __init__(self, a, b):
            self.a = a
            self.b = b

        @overload
        def process(self):
            return f"一个参数: {self.a}, {self.b}"

        @process.register(export_mode=ParentMode)
        def process_one(self, x):
            return f"两个参数: {self.a}, {self.b}, {x}"

        @process.register(export_mode=ParentMode)
        def process_two(self, x, y):
            return f"三个参数: {self.a}, {self.b}, {x}, {y}"

    test = Test(1, 2)
    assert test.process() == "一个参数: 1, 2"
    assert test.process(3) == "两个参数: 1, 2, 3"
    assert test.process(4, 5) == "三个参数: 1, 2, 4, 5"


def test_overload_strict():
    """测试 overload 严格模式"""
    reset_registry()

    @overload(mode=Strict | Ambiguous)
    def process2(x: int, y: int):
        return f"两个参数: {x}, {y},type:{type(x)},{type(y)}"

    @process2.register(export_mode=ParentMode)
    def process2(x: str, y: str):  # 同名函数
        return f"两个参数: {x}, {y},type:{type(x)},{type(y)}"

    assert process2(10, 20) == "两个参数: 10, 20,type:<class 'int'>,<class 'int'>"
    assert process2("10", "20") == "两个参数: 10, 20,type:<class 'str'>,<class 'str'>"


def test_curry_decorator():
    """测试 curry_decorator 装饰器"""
    @curry_decorator
    def process(a, b, c):
        return a + b + c

    assert process(1)(2)(3) == 6

    process.delaied = True
    rs = process(1)(2)(3)
    assert rs() == 6


def test_strict_decorator():
    """测试 strict 装饰器"""
    @strict
    def multiply(a: int, b: int) -> int:
        return a * b

    assert multiply(3, 4) == 12

    try:
        multiply(3, "4")
        assert False, "应该抛出 TypeError"
    except TypeError:
        pass


if __name__ == '__main__':
    print("=" * 60)
    print("测试 curry 和 overload 装饰器")
    print("=" * 60)

    print("\n=== 测试 curry_decorator ===")
    test_curry_decorator()
    print("[OK]")

    print("\n=== 测试 overload ===")
    test_overload_default()
    test_overload_class_method()
    test_overload_strict()
    print("[OK]")

    print("\n=== 测试 strict ===")
    test_strict_decorator()
    print("[OK]")

    print("\n" + "=" * 60)
    print("[SUCCESS] 所有测试通过!")
    print("=" * 60)
