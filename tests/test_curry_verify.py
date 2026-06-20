"""验证 curry 装饰器在被 get_signature 替换后是否工作"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from vools.decorators import curry
from vools.cache import clear_cache

clear_cache()

@curry
def add(a, b, c):
    return a + b + c

result = add(1)(2)(3)
assert result == 6, f"Expected 6, got {result}"

result2 = add(1, 2)(3)
assert result2 == 6, f"Expected 6, got {result2}"

print("curry 测试通过:", result, result2)

# 测试 overload
from vools.decorators import overload, strict

@overload
def process():
    return "none"

@process.register
def process(x):
    return f"one: {x}"

@process.register
def process(x, y):
    return f"two: {x}, {y}"

assert process() == "none"
assert process(10) == "one: 10"
assert process(10, 20) == "two: 10, 20"
print("overload 测试通过")

# 测试 placeholder signature
from vools.functional.placeholder import _, X
sig = _.signature  # should work
print("placeholder 测试通过")

print()
print("=== ALL CORE TESTS PASSED ===")
