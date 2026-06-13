"""测试新添加的功能"""

from vools.curried import pluck, pluck_attr, walk, mapcat, compact, merge, merge_with, get_in, set_in, update_in
from vools.functional import Result, Success, Failure, success, failure, safe

# 测试 pluck
print('=== 测试 pluck ===')
data = [{'name': 'Alice', 'age': 25}, {'name': 'Bob', 'age': 30}]
print(f'pluck("name", data) = {pluck("name")(data)}')

# 测试 pluck_attr
print('\n=== 测试 pluck_attr ===')
class Person:
    def __init__(self, name):
        self.name = name
print(f'pluck_attr("name", [Person("Alice"), Person("Bob")]) = {pluck_attr("name")([Person("Alice"), Person("Bob")])}')

# 测试 mapcat
print('\n=== 测试 mapcat ===')
print(f'mapcat(lambda x: [x, x*2], [1, 2, 3]) = {mapcat(lambda x: [x, x*2])([1, 2, 3])}')

# 测试 compact
print('\n=== 测试 compact ===')
print(f'compact([1, None, 2, False, 3, "", 4]) = {compact([1, None, 2, False, 3, "", 4])}')

# 测试 merge
print('\n=== 测试 merge ===')
print(f'merge({{"a": 1}}, {{"b": 2}}, {{"a": 3}}) = {merge({"a": 1}, {"b": 2}, {"a": 3})}')

# 测试 merge_with
print('\n=== 测试 merge_with ===')
print(f'merge_with(lambda *args: sum(args))({{"a": 1}}, {{"a": 2}}, {{"a": 3}}) = {merge_with(lambda *args: sum(args))({"a": 1}, {"a": 2}, {"a": 3})}')

# 测试 get_in
print('\n=== 测试 get_in ===')
nested = {'a': {'b': {'c': 42}}}
print(f'get_in(["a", "b", "c"], nested) = {get_in(["a", "b", "c"])(nested)}')
print(f'get_in(["a", "x"], nested, default="not found") = {get_in(["a", "x"], default="not found")(nested)}')

# 测试 set_in
print('\n=== 测试 set_in ===')
print(f'set_in(["a", "b", "c"], 100, nested) = {set_in(["a", "b", "c"], 100)(nested)}')

# 测试 update_in
print('\n=== 测试 update_in ===')
print(f'update_in(["a", "b"], lambda x: x*2, {{"a": {{"b": 10}}}}) = {update_in(["a", "b"], lambda x: x*2)({"a": {"b": 10}})}')

# 测试 Result
print('\n=== 测试 Result ===')
r1 = Result.success(42)
r2 = Result.failure(ValueError('test error'))
print(f'Result.success(42) = {r1}')
print(f'Result.failure(error) = {r2}')
print(f'r1.is_success = {r1.is_success}')
print(f'r2.is_failure = {r2.is_failure}')
print(f'r1.map(lambda x: x*2) = {r1.map(lambda x: x*2)}')
print(f'r1.unwrap() = {r1.unwrap()}')
print(f'r2.unwrap_or(0) = {r2.unwrap_or(0)}')

# 测试 safe 装饰器
print('\n=== 测试 safe 装饰器 ===')
@safe
def divide(a, b):
    return a / b
print(f'safe_divide(10, 2) = {divide(10, 2)}')
print(f'safe_divide(10, 0) = {divide(10, 0)}')

print('\n所有测试通过!')
