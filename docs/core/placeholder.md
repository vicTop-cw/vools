# 占位符

> **模块路径**：`vools.functional`
> **依赖版本**：Python 3.6+
> **平台支持**：Windows/macOS/Linux
> **测试状态**：✅ 已测试
> **编号**：#005
> **最后更新**：2026-06-30

## 概述

占位符是 vools 函数式编程模块的核心功能，提供了一种声明式的方式来定义函数和表达式。支持单例占位符 `_`、`_1`、`_2` 等多种形式。

## 导入方式

```python
from vools.functional import _, _1, _2, _3, _4, _5, _6, _7, _8, _9, _10
from vools.functional import magic, f, to_holder, F, g
from vools.functional.placeholder import hd  # hd 是 _ 的别名
```

## 单例占位符

### `_` - 第一个参数占位符

```python
# test_placeholder_basic.py
from vools.functional import _, _1, _2, _3

# 加法：(_ + 5) 等价于 lambda x: x + 5
add5 = _ + 5
result = add5(10)
print(f"add5(10) = {result}")  # 输出: add5(10) = 15

# 乘法：(_ * 2) 等价于 lambda x: x * 2
double = _ * 2
result = double(7)
print(f"double(7) = {result}")  # 输出: double(7) = 14

# 链式调用
result = ((_ + 10) * 2)(5)
print(f"((_ + 10) * 2)(5) = {result}")  # 输出: ((_ + 10) * 2)(5) = 30
```

### `_1`, `_2`, `_3` 等 - 多参数占位符

```python
# test_indexed_placeholder.py
from vools.functional import _1, _2, _3

# 两数相加：(_1 + _2) 等价于 lambda x, y: x + y
add = _1 + _2
result = add(3, 5)
print(f"add(3, 5) = {result}")  # 输出: add(3, 5) = 8

# 三数相加
add3 = _1 + _2 + _3
result = add3(1, 2, 3)
print(f"add3(1, 2, 3) = {result}")  # 输出: add3(1, 2, 3) = 6

# 复杂表达式
complex_expr = (_1 + _2) * _3
result = complex_expr(1, 2, 3)
print(f"(1 + 2) * 3 = {result}")  # 输出: (1 + 2) * 3 = 9
```

## 属性访问

### `.` 属性访问

```python
# test_attr_access.py
from vools.functional import _

# 获取属性：_.name 等价于 lambda obj: obj.name
class Person:
    def __init__(self, name, age):
        self.name = name
        self.age = age

person = Person("Alice", 30)

get_name = _.name
result = get_name(person)
print(f"person.name = {result}")  # 输出: person.name = Alice

# 链式属性访问
get_age = _.age
result = get_age(person)
print(f"person.age = {result}")  # 输出: person.age = 30
```

## 索引访问

### `[]` 索引访问

```python
# test_index_access.py
from vools.functional import _

# 列表索引：(_[0]) 等价于 lambda lst: lst[0]
first_item = _[0]
result = first_item([10, 20, 30])
print(f"first_item([10, 20, 30]) = {result}")  # 输出: first_item([10, 20, 30]) = 10

# 字典索引
get_key = _["key"]
result = get_key({"key": "value", "other": "x"})
print(f"get_key(...) = {result}")  # 输出: get_key(...) = value

# 嵌套索引
nested = _[0][1]
data = [[1, 2, 3], [4, 5, 6]]
result = nested(data)
print(f"nested([[1,2,3],[4,5,6]]) = {result}")  # 输出: nested([[1,2,3],[4,5,6]]) = 2
```

## 箭头函数 `g`

### 基本用法

```python
# test_g_arrow.py
from vools.functional import g

# 标准箭头函数：x => x + 1
inc = g("x => x + 1")
result = inc(5)
print(f"inc(5) = {result}")  # 输出: inc(5) = 6

# 多参数箭头函数
add = g("x, y => x + y")
result = add(3, 5)
print(f"add(3, 5) = {result}")  # 输出: add(3, 5) = 8

# 带条件表达式
max_val = g("x, y => x if x > y else y")
result = max_val(10, 20)
print(f"max_val(10, 20) = {result}")  # 输出: max_val(10, 20) = 20
```

### 带分号的箭头函数

```python
# test_g_multistmt.py
from vools.functional import g

# 多语句箭头函数
process = g("x => x = x * 2; x + 1")
result = process(5)
print(f"process(5) = {result}")  # 输出: process(5) = 11

# 带局部变量
calc = g("x, y => sum = x + y; prod = x * y; sum + prod")
result = calc(3, 4)
print(f"calc(3, 4) = {result}")  # 输出: calc(3, 4) = 19 (3+4 + 3*4 = 7+12)
```

### 下划线占位符模式

```python
# test_g_underscore.py
from vools.functional import g

# 单下划线按顺序对应参数
add = g("_ + _")
result = add(3, 5)
print(f"add(3, 5) = {result}")  # 输出: add(3, 5) = 8

# 带索引的下划线
expr = g("_1 + _2 * _3")
result = expr(1, 2, 3)
print(f"expr(1, 2, 3) = {result}")  # 输出: expr(1, 2, 3) = 7 (1 + 2 * 3)
```

## 函数转换

### `to_holder` - 函数转占位符

```python
# test_to_holder.py
from vools.functional import to_holder, _

# 将普通函数转换为占位符函数
def multiply(a, b, c):
    return a * b * c

curried_mult = to_holder(multiply, arity=3)
result = curried_mult(2)(3)(4)
print(f"curried_mult(2)(3)(4) = {result}")  # 输出: curried_mult(2)(3)(4) = 24

# 部分应用
mult_by_2 = curried_mult(2)
result = mult_by_2(3)(4)
print(f"mult_by_2(3)(4) = {result}")  # 输出: mult_by_2(3)(4) = 24
```

### `f` - 构造函数表达式

```python
# test_f_func.py
from vools.functional import f, _

# 构造复合函数表达式
expr = f(lambda x: x + 1)
result = expr(_ + 2)
final = result(5)
print(f"result(5) = {final}")  # 输出: result(5) = 8 ((5+2)+1)
```

## 占位符操作

### 数学运算

```python
# test_math_ops.py
from vools.functional import _1, _2

# 加减乘除
add = _1 + _2
sub = _1 - _2
mul = _1 * _2
div = _1 / _2

print(f"add(10, 5) = {add(10, 5)}")   # 输出: add(10, 5) = 15
print(f"sub(10, 5) = {sub(10, 5)}")   # 输出: sub(10, 5) = 5
print(f"mul(10, 5) = {mul(10, 5)}")   # 输出: mul(10, 5) = 50
print(f"div(10, 5) = {div(10, 5)}")   # 输出: div(10, 5) = 2.0

# 幂运算
power = _1 ** _2
print(f"power(2, 3) = {power(2, 3)}")  # 输出: power(2, 3) = 8

# 取模
mod = _1 % _2
print(f"mod(10, 3) = {mod(10, 3)}")    # 输出: mod(10, 3) = 1
```

### 比较运算

```python
# test_compare_ops.py
from vools.functional import _1, _2

# 比较运算
gt = _1 > _2
lt = _1 < _2
ge = _1 >= _2
le = _1 <= _2
eq = _1 == _2

print(f"gt(5, 3) = {gt(5, 3)}")    # 输出: gt(5, 3) = True
print(f"lt(5, 3) = {lt(5, 3)}")    # 输出: lt(5, 3) = False
print(f"ge(5, 3) = {ge(5, 3)}")    # 输出: ge(5, 3) = True
print(f"le(5, 3) = {le(5, 3)}")    # 输出: le(5, 3) = False
print(f"eq(5, 3) = {eq(5, 3)}")    # 输出: eq(5, 3) = False
```

### 逻辑运算

```python
# test_logical_ops.py
from vools.functional import _1, _2

# 逻辑与或非
and_result = (_1 > 0) & (_2 > 0)
or_result = (_1 < 0) | (_2 < 0)
not_result = ~(_1 > 0)

print(f"and_result(1, 2) = {and_result(1, 2)}")  # 输出: and_result(1, 2) = True
print(f"or_result(-1, 2) = {or_result(-1, 2)}")   # 输出: or_result(-1, 2) = True
print(f"not_result(5) = {not_result(5)}")          # 输出: not_result(5) = False
```

### 包含运算

```python
# test_contain_ops.py
from vools.functional import _1, _2

# in 操作
contains = _1.contains(_2)
result = contains([1, 2, 3], 2)
print(f"contains([1,2,3], 2) = {result}")  # 输出: contains([1,2,3], 2) = True

# 类型检查
isinstance_check = _1.instance_of(str)
print(f"isinstance_check('hello') = {isinstance_check('hello')}")  # 输出: isinstance_check('hello') = True
```

## 类型转换方法

```python
# test_type_convert.py
from vools.functional import _

# 类型转换
to_str = _.toString()
to_int = _.toInt()
to_float = _.toFloat()
to_bool = _.toBool()

print(f"to_str(123) = {to_str(123)}")       # 输出: to_str(123) = 123
print(f"to_int('456') = {to_int('456')}")   # 输出: to_int('456') = 456
print(f"to_float('3.14') = {to_float('3.14')}")  # 输出: to_float('3.14') = 3.14
print(f"to_bool('True') = {to_bool('True')}")    # 输出: to_bool('True') = True
```

## 使用示例

### 与内置函数配合

```python
# test_with_builtins.py
from vools.functional import _, _1, _2

# map
result = list(map(_ * 2, [1, 2, 3, 4]))
print(f"map(_ * 2, [1,2,3,4]) = {result}")  # 输出: map(_ * 2, [1,2,3,4]) = [2, 4, 6, 8]

# filter
result = list(filter(_ > 5, [1, 3, 6, 8, 10]))
print(f"filter(_ > 5, [1,3,6,8,10]) = {result}")  # 输出: filter(_ > 5, [6, 8, 10])

# sorted
result = sorted([(1, 3), (3, 1), (2, 2)], key=_1)
print(f"sorted by first = {result}")  # 输出: sorted by first = [(1, 3), (2, 2), (3, 1)]
```

## 注意事项

1. **占位符是不可变的**：创建后不能修改
2. **参数顺序**：`_` 总是代表第一个参数，`_1`、`_2` 按索引对应
3. **链式调用**：支持复杂表达式的链式构建
4. **性能**：内部使用 `lru_cache` 优化 `eval` 结果

## 相关文档

- [箭头函数文档](./arrow_func.md)
- [管道操作文档](./pipe_ops.md)
