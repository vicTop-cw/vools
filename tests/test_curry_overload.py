"""测试 curry 和 overload 装饰器"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vools import curry, overload, overloads
from vools.decorators import strict,curry as curry_decorator

print("=" * 60)
print("测试 smart_partial 和 overload 装饰器")
print("=" * 60)

# 测试 smart_partial
print("\n=== 测试 smart_partial ===")

@curry_decorator
def add(a, b, c):
    return a + b + c

result = add(1)(2)(3)
print(f"add(1)(2)(3) = {result}")
assert result == 6

result = add(1, 2)(3)
print(f"add(1, 2)(3) = {result}")
assert result == 6

print("[OK] smart_partial 测试通过")

# 测试 overload
print("\n=== 测试 overload ===")

@overload
def process():
    return "无参数"

@process.register
def process(x):
    return f"一个参数: {x}"

@process.register
def process(x, y):
    return f"两个参数: {x}, {y}"

result1 = process()
result2 = process(10)
result3 = process(10, 20)

print(f"process() = {result1}")
print(f"process(10) = {result2}")
print(f"process(10, 20) = {result3}")

assert result1 == "无参数"
assert result2 == "一个参数: 10"
assert result3 == "两个参数: 10, 20"

print("[OK] overload 测试通过")

# 测试 strict
print("\n=== 测试 strict ===")

@strict
def multiply(a: int, b: int) -> int:
    return a * b

result = multiply(3, 4)
print(f"multiply(3, 4) = {result}")
assert result == 12

try:
    multiply(3, "4")
    assert False, "应该抛出 TypeError"
except TypeError as e:
    print(f"正确捕获类型错误: {e}")

print("[OK] strict 测试通过")

print("\n" + "=" * 60)
print("[SUCCESS] 所有测试通过!")
print("=" * 60)




def test_overloads():
    """测试 overloads 装饰器"""
    @overload
    def process():
        return "无参数"
        
    @process.register
    def process(x):
        return f"一个参数: {x}"
    
        
    @process.register
    def process(x, y):
        return f"两个参数: {x}, {y}"

    result1 = process()
    result2 = process(10)
    result3 = process(10, 20)

    assert result1 == "无参数"
    assert result2 == "一个参数: 10"
    assert result3 == "两个参数: 10, 20"


    class Test:
        def __init__(self, a, b):
            self.a = a
            self.b = b
        
        @overload
        def process(self):
            return f"一个参数: {self.a}, {self.b}"
        
        @process.register
        def process(self, x):
            return f"两个参数: {self.a}, {self.b}, {x}"
        
        @process.register
        def process(self, x, y):
            return f"三个参数: {self.a}, {self.b}, {x}, {y}"
        
    test = Test(1, 2)
    result1 = test.process()
    result2 = test.process(3)
    result3 = test.process(4, 5)
    
    assert result1 == "一个参数: 1, 2"
    assert result2 == "两个参数: 1, 2, 3"
    assert result3 == "三个参数: 1, 2, 4, 5"


    @overload
    def process2(x:int, y:int):
        return f"两个参数: {x}, {y},type:{type(x)},{type(y)}"
    
    @process2.register
    def process2(x:str, y:str):
        return f"两个参数: {x}, {y},type:{type(x)},{type(y)}"
    
    result1 = process2(10, 20)
    result2 = process2("10", "20")
    # print(result1)
    # print(result2)
    assert result1 == "两个参数: 10, 20,type:<class 'int'>,<class 'int'>"
    assert result2 == "两个参数: 10, 20,type:<class 'str'>,<class 'str'>"

    



test_overloads()



def test_curry_decorator():
    """测试 curry_decorator 装饰器"""
    @curry_decorator
    def process(a, b, c):
        return a + b + c
    
    result = process(1)(2)(3)
    print(f"process(1)(2)(3) = {result}")
    assert result == 6

    process.delaied = True

    rs = process(1)(2)(3)
    print(f"process(1)(2)(3) = {rs}")
    assert rs() == 6


    
    print("[OK] curry_decorator 测试通过")


test_curry_decorator()