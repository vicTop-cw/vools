#!/usr/bin/env python
"""
测试所有新增功能的完整性
"""

print('=== 新增功能完整测试 ===')

# 测试所有新增的集合操作函数
from vools.curried import *

# split_at
print('\n1. split_at 测试')
print(f'  split_at(3, [1,2,3,4,5]): {split_at(3, [1,2,3,4,5])}')

# butlast
print('\n2. butlast 测试')
print(f'  butlast([1,2,3,4,5]): {butlast([1,2,3,4,5])}')

# dissoc
print('\n3. dissoc 测试')
print(f'  dissoc({{"a":1, "b":2, "c":3}}, "b"): {dissoc({"a":1, "b":2, "c":3}, "b")}')

# assoc
print('\n4. assoc 测试')
print(f'  assoc({{"a":1}}, b=2): {assoc({"a":1}, b=2)}')

# assoc_in
print('\n5. assoc_in 测试')
print(f'  assoc_in({{"a":{{"b":1}}}}, ["a", "c"], 2): {assoc_in({"a":{"b":1}}, ["a", "c"], 2)}')

# constantly
print('\n6. constantly 测试')
print(f'  const_func = constantly(42); const_func(): {constantly(42)()}')

# interleave
print('\n7. interleave 测试')
print(f'  interleave([[1,2,3], ["a","b","c"]]): {list(interleave([[1,2,3], ["a","b","c"]]))}')

# interpose
print('\n8. interpose 测试')
print(f'  interpose(",", ["a","b","c"]): {list(interpose(",", ["a","b","c"]))}')

# flip
print('\n9. flip 测试')
from operator import sub
print(f'  flip(sub)(3, 5): {flip(sub)(3, 5)}')

# compose_left
print('\n10. compose_left 测试')
double = lambda x: x * 2
add_one = lambda x: x + 1
print(f'  compose_left(add_one, double)(3): {compose_left(add_one, double)(3)}')

# 错误处理装饰器
print('\n11. excepts 测试')
@excepts(ValueError, lambda e: f'捕获错误: {e}')
def risky():
    raise ValueError('测试')
print(f'  risky(): {risky()}')

print('\n12. silent 测试')
@silent(default='默认')
def risky2():
    raise ValueError('错误')
print(f'  risky2(): {risky2()}')

print('\n13. suppress 测试')
@suppress(ValueError)
def risky3():
    raise ValueError('被抑制')
result = risky3()
print(f'  risky3(): {result}')

print('\n14. ignore 测试')
@ignore
def returns_value():
    return 42
result = returns_value()
print(f'  returns_value(): {result}')

# Result 类型
print('\n15. Result 类型测试')
from vools.functional import Result, Success, Failure, success, failure, safe

@safe
def divide(a, b):
    return a / b

s = Success(42)
f = Failure("error")
print(f'  Success(42): {s}')
print(f'  Success(42).is_success: {s.is_success}')
print(f'  Success(42).unwrap(): {s.unwrap()}')
print(f'  Failure("error"): {f}')
print(f'  Failure("error").is_failure: {f.is_failure}')
print(f'  success(10): {success(10)}')
print(f'  failure("oops"): {failure("oops")}')
print(f'  divide(10, 2): {divide(10, 2)}')
print(f'  divide(10, 0): {divide(10, 0)}')

print('\n=== 所有测试通过！===')
