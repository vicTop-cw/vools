"""测试 stuff 装饰器"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vools import stuff

print("=" * 60)
print("测试 stuff 装饰器")
print("=" * 60)

# 测试基本功能
print("\n=== 测试基本功能 ===")

@stuff
def add(a, b, c):
    return a + b + c

result = add(1)(2)(3)()
print(f"add(1)(2)(3)() = {result}")
assert result == 6

result = add(1, 2, 3)()
print(f"add(1, 2, 3)() = {result}")
assert result == 6

print("[OK] 基本功能测试通过")

# 测试参数依赖注入
print("\n=== 测试参数依赖注入 ===")

@stuff
def multiply(a, b, c):
    return a * b * c

@multiply.register
def get_a():
    return 2

@multiply.register(param_name=['b', 'c'])
def get_bc():
    return 3, 4

result = multiply()
print(f"multiply() = {result}")
assert result == 24

print("[OK] 参数依赖注入测试通过")

print("\n" + "=" * 60)
print("[SUCCESS] 所有测试通过!")
print("=" * 60)
