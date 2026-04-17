"""
装饰器模块测试

测试内容：
1. curry 装饰器测试
2. delay_curry 装饰器测试
3. overload 装饰器测试
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vools.decorators import (
    curry, delay_curry, is_curried,
    overload, strict,
)


def test_curry_basic():
    """测试 curry 基本功能"""
    print("\n" + "="*50)
    print("测试 curry 基本功能")
    print("="*50)
    
    @curry
    def add(a, b, c):
        return a + b + c
    
    # 测试不同的调用方式
    assert add(1)(2)(3) == 6, "测试1失败: add(1)(2)(3)"
    assert add(1, 2)(3) == 6, "测试2失败: add(1, 2)(3)"
    assert add(1)(2, 3) == 6, "测试3失败: add(1)(2, 3)"
    assert add(1, 2, 3) == 6, "测试4失败: add(1, 2, 3)"
    
    # 测试关键字参数
    assert add(b=2)(a=1)(c=3) == 6, "测试5失败: add(b=2)(a=1)(c=3)"
    
    print("✓ curry 基本功能测试通过")


def test_curry_with_varargs():
    """测试 curry 支持可变参数"""
    print("\n" + "="*50)
    print("测试 curry 可变参数")
    print("="*50)
    
    @curry
    def add(a, b, *args, **kwargs):
        return a + b + sum(args) + sum(kwargs.values())
    
    assert add(1, 2) == 3, "测试1失败"
    assert add(1)(2) == 3, "测试2失败"
    assert add(1, 2, 3, 4) == 10, "测试3失败"
    assert add(1)(2, 3, 4) == 10, "测试4失败"
    assert add(c=3, d=4)(1, 2) == 10, "测试5失败"
    
    print("✓ curry 可变参数测试通过")


def test_curry_class_method():
    """测试 curry 支持类方法"""
    print("\n" + "="*50)
    print("测试 curry 类方法")
    print("="*50)
    
    class Calculator:
        @curry
        def add(self, a, b):
            return a + b
        
        @staticmethod
        @curry
        def static_add(a, b):
            return a + b
        
        @classmethod
        @curry
        def class_add(cls, a, b):
            return a + b
    
    calc = Calculator()
    assert calc.add(1)(2) == 3, "实例方法测试失败"
    assert calc.add(1, 2) == 3, "实例方法测试失败"
    assert Calculator.static_add(1)(2) == 3, "静态方法测试失败"
    assert Calculator.class_add(1)(2) == 3, "类方法测试失败"
    
    print("✓ curry 类方法测试通过")


def test_curry_class():
    """测试 curry 支持类"""
    print("\n" + "="*50)
    print("测试 curry 类")
    print("="*50)
    
    @curry
    class Point:
        def __init__(self, x, y):
            self.x = x
            self.y = y
        
        def __eq__(self, other):
            return self.x == other.x and self.y == other.y
    
    p1 = Point(1, 2)
    p2 = Point(1)(2)
    p3 = Point(1, 2)
    
    assert p1 == p2, "测试1失败"
    assert p2 == p3, "测试2失败"
    
    print("✓ curry 类测试通过")


def test_curry_strict():
    """测试 curry 严格类型检查"""
    print("\n" + "="*50)
    print("测试 curry 严格类型检查")
    print("="*50)
    
    @curry(is_strict=True)
    def add(a: int, b: int) -> int:
        return a + b
    
    assert add(1)(2) == 3, "测试1失败"
    
    try:
        add("1")(2)  # 应该抛出 TypeError
        assert False, "应该抛出 TypeError"
    except TypeError:
        pass
    
    print("✓ curry 严格类型检查测试通过")


def test_delay_curry_basic():
    """测试 delay_curry 基本功能"""
    print("\n" + "="*50)
    print("测试 delay_curry 基本功能")
    print("="*50)
    
    @delay_curry
    def add(a, b):
        return a + b
    
    assert add(1)(2)() == 3, "测试1失败"
    assert add(1, 2)() == 3, "测试2失败"
    
    print("✓ delay_curry 基本功能测试通过")


def test_delay_curry_with_varargs():
    """测试 delay_curry 可变参数"""
    print("\n" + "="*50)
    print("测试 delay_curry 可变参数")
    print("="*50)
    
    @delay_curry
    def calculate(a, *args, b=0, **kwargs):
        return a + sum(args) * b + sum(kwargs.values())
    
    assert calculate(1)(2, 3)(b=2, c=4, d=5)() == 20, "测试失败"
    
    print("✓ delay_curry 可变参数测试通过")


def test_delay_curry_class_method():
    """测试 delay_curry 类方法"""
    print("\n" + "="*50)
    print("测试 delay_curry 类方法")
    print("="*50)
    
    class Math:
        @delay_curry
        def add(self, a, b):
            return a + b
        
        @staticmethod
        @delay_curry
        def static_add(a, b):
            return a + b
    
    math = Math()
    assert math.add(1)(2)() == 3, "实例方法测试失败"
    assert Math.static_add(1)(2)() == 3, "静态方法测试失败"
    
    print("✓ delay_curry 类方法测试通过")


def test_overload_basic():
    """测试 overload 基本功能"""
    print("\n" + "="*50)
    print("测试 overload 基本功能")
    print("="*50)
    
    @overload
    def process():
        return "无参数"
    
    @process.register
    def process_x(x):
        return f"一个参数: {x}"
    
    @process.register
    def process_xy(x, y):
        return f"两个参数: {x}, {y}"
    
    assert process() == "无参数", "测试1失败"
    assert process(10) == "一个参数: 10", "测试2失败"
    assert process(20, 30) == "两个参数: 20, 30", "测试3失败"
    
    print("✓ overload 基本功能测试通过")


def test_overload_strict():
    """测试 overload 严格模式"""
    print("\n" + "="*50)
    print("测试 overload 严格模式")
    print("="*50)
    
    @overload(is_strict=True)
    def process(a: int, b: int):
        return a + b
    
    @process.register
    def process_str(a: str, b: str):
        return a + b
    
    assert process(1, 2) == 3, "测试1失败"
    assert process("a", "b") == "ab", "测试2失败"
    
    try:
        process(1, "b")  # 应该抛出 TypeError
        assert False, "应该抛出 TypeError"
    except TypeError:
        pass
    
    print("✓ overload 严格模式测试通过")


def test_overload_priority():
    """测试 overload 优先级"""
    print("\n" + "="*50)
    print("测试 overload 优先级")
    print("="*50)
    
    @overload(priority='first')
    def process():
        return "主函数"
    
    @process.register(priority=1)
    def process_one(arg):
        return f"优先级1: {arg}"
    
    @process.register(priority=10)
    def process_high(arg):
        return f"高优先级: {arg}"
    
    assert process("hello") == "高优先级: hello", "测试1失败"
    assert process(100) == "高优先级: 100", "测试2失败"
    
    print("✓ overload 优先级测试通过")


def test_overload_class_method():
    """测试 overload 类方法"""
    print("\n" + "="*50)
    print("测试 overload 类方法")
    print("="*50)
    
    class Processor:
        def __init__(self, prefix):
            self.prefix = prefix
        
        @overload(is_strict=True)
        def process(self):
            return f"{self.prefix}: 无参数"
        
        @process.register
        def process_int(self, x: int):
            return f"{self.prefix}: 整数({x})"
        
        @process.register
        def process_str(self, x: str):
            return f"{self.prefix}: 字符串({x})"
    
    proc = Processor("测试")
    assert proc.process() == "测试: 无参数", "测试1失败"
    assert proc.process(10) == "测试: 整数(10)", "测试2失败"
    print(proc.process("text"))
    assert proc.process("text") == "测试: 字符串(text)", "测试3失败"
    
    print("✓ overload 类方法测试通过")


def test_strict():
    """测试 strict 装饰器"""
    print("\n" + "="*50)
    print("测试 strict 装饰器")
    print("="*50)
    
    @strict
    def add(a: int, b: int) -> int:
        return a + b
    
    assert add(1, 2) == 3, "测试1失败"
    
    try:
        add(1, "2")  # 应该抛出 TypeError
        assert False, "应该抛出 TypeError"
    except TypeError:
        pass
    
    print("✓ strict 装饰器测试通过")


def run_all_tests():
    """运行所有测试"""
    print("\n" + "="*70)
    print("开始运行装饰器模块测试")
    print("="*70)
    
    try:
        # curry 测试
        test_curry_basic()
        test_curry_with_varargs()
        test_curry_class_method()
        test_curry_class()
        test_curry_strict()
        
        # delay_curry 测试
        test_delay_curry_basic()
        test_delay_curry_with_varargs()
        test_delay_curry_class_method()
        
        # overload 测试
        test_overload_basic()
        test_overload_strict()
        test_overload_priority()
        test_overload_class_method()
        
        # strict 测试
        test_strict()
        
        print("\n" + "="*70)
        print("✓ 所有测试通过！")
        print("="*70)
        return True
        
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
