"""测试 stuff 装饰器 - 新 API"""
from vools import stuff

print("=" * 60)
print("测试 stuff 装饰器（新 API）")
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

# 测试 provide 方法（单个参数）
print("\n=== 测试 provide 方法 ===")

@stuff
def multiply(a, b, c):
    return a * b * c

@multiply.provide
def get_a():
    return 2

@multiply.provide(name='b')
def get_b():
    return 3

multiply.provide(lambda: 4, name='c')

result = multiply()
print(f"multiply() = {result}")
assert result == 24

print("[OK] provide 方法测试通过")

# 测试 provide_with 方法（多个关键字参数）
print("\n=== 测试 provide_with 方法 ===")

@stuff
def calculate(price, quantity, tax_rate):
    return price * quantity * (1 + tax_rate)

@calculate.provide_with(names=['price', 'quantity'])
def get_price_and_quantity():
    return 100, 2

calculate.provide(lambda: 0.1, name='tax_rate')

result = calculate()
print(f"calculate() = {result}")
assert abs(result - 220) < 0.001

print("[OK] provide_with 方法测试通过")

# 测试 provide_multi_params 方法（多个位置参数）
print("\n=== 测试 provide_multi_params 方法 ===")

@stuff
def concat(a, b, c):
    return f"{a}-{b}-{c}"

@concat.provide_multi_params(count=2)
def get_ab():
    return "Hello", "World"

concat.provide(lambda: "Test", name='c')

result = concat()
print(f"concat() = {result}")
assert result == "Hello-World-Test"

print("[OK] provide_multi_params 方法测试通过")

# 测试 aggregate_providers 方法（聚合多个提供者）
print("\n=== 测试 aggregate_providers 方法 ===")

@stuff
def sum_all(numbers):
    return sum(numbers)

sum_all.aggregate_providers(lambda: 1, lambda: 2, lambda: 3, lambda: 4)

result = sum_all()
print(f"sum_all() = {result}")
assert result == 10

print("[OK] aggregate_providers 方法测试通过")

# 测试链式调用
print("\n=== 测试链式调用 ===")

@stuff
def chain_test(a, b, c):
    return a + b + c

chain_test.provide(lambda: 1).provide(lambda: 2).provide(lambda: 3)

result = chain_test()
print(f"chain_test() = {result}")
assert result == 6

print("[OK] 链式调用测试通过")

# 测试 reset 方法
print("\n=== 测试 reset 方法 ===")

@stuff
def reset_test(a, b):
    return a + b

reset_test.provide(lambda: 10).provide(lambda: 20)
result1 = reset_test()
print(f"reset_test() before reset = {result1}")
assert result1 == 30

reset_test.reset()
reset_test.provide(lambda: 5).provide(lambda: 7)
result2 = reset_test()
print(f"reset_test() after reset = {result2}")
assert result2 == 12

print("[OK] reset 方法测试通过")

# 测试类支持
print("\n=== 测试类支持 ===")

@stuff
class Calculator:
    def __init__(self, base, multiplier):
        self.base = base
        self.multiplier = multiplier

    def compute(self, x):
        return self.base + x * self.multiplier

calc = Calculator(10)(2)()
print(f"Calculator(10)(2)() = {calc}")
assert calc.base == 10
assert calc.multiplier == 2
result = calc.compute(5)
print(f"calc.compute(5) = {result}")
assert result == 20

print("[OK] 类支持测试通过")

print("\n" + "=" * 60)
print("[SUCCESS] 所有测试通过!")
print("=" * 60)
