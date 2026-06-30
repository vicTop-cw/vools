# Result 类型

> **模块路径**：`vools.functional`
> **依赖版本**：Python 3.6+
> **平台支持**：Windows/macOS/Linux
> **测试状态**：✅ 已测试
> **编号**：#012
> **最后更新**：2026-06-30

## 概述

`Result` 类型是函数式错误处理的核心类型，封装了可能失败的操作结果。`Result` 可以是 `Success`（成功）或 `Failure`（失败），提供类型安全的错误处理方式，避免使用 try-except 块。

## Result 类

### 基本用法

```python
from vools.functional import Result, Success, Failure

# 创建成功结果
result = Result.success(42)
print(result.is_success)  # 输出: True
print(result.is_failure)  # 输出: False
print(result)             # 输出: Success(42)

# 创建失败结果
result = Result.failure(ValueError("invalid input"))
print(result.is_success)  # 输出: False
print(result.is_failure)  # 输出: True
print(result)             # 输出: Failure(ValueError('invalid input'))
```

### Success 和 Failure 子类

```python
from vools.functional import Success, Failure

# 使用便捷子类
success = Success(100)
print(success)  # 输出: Success(100)

failure = Failure(TypeError("expected int"))
print(failure)  # 输出: Failure(TypeError('expected int'))
```

## safe 装饰器

`safe` 装饰器将可能抛出异常的函数包装为返回 `Result` 的安全版本。

### 基本用法

```python
from vools.functional import safe

# 装饰可能抛出异常的函数
@safe
def divide(a, b):
    return a / b

# 正常情况
result = divide(10, 2)
print(result)  # 输出: Success(5.0)

# 异常情况
result = divide(10, 0)
print(result)  # 输出: Failure(ZeroDivisionError('division by zero'))
```

### 链式调用

```python
from vools.functional import safe

@safe
def parse_int(s):
    return int(s)

@safe
def double(x):
    return x * 2

@safe
def add_ten(x):
    return x + 10

# 链式调用
result = parse_int("42").bind(double).bind(add_ten)
print(result)  # 输出: Success(94)
# 说明: 42 -> 84 -> 94

# 链中某一步失败
result = parse_int("not_a_number").bind(double).bind(add_ten)
print(result)  # 输出: Failure(ValueError("invalid literal for int: 'not_a_number'"))
```

## map - 映射成功值

```python
from vools.functional import Result

# map: 转换成功值，失败时保持不变
result = Result.success(5)

# 映射成功值
mapped = result.map(lambda x: x * 2)
print(mapped)  # 输出: Success(10)

# 映射失败值（无效）
mapped = result.map(lambda x: x / 0)  # 不会执行，因为 result 是 Success
print(mapped)  # 输出: Success(10)

# 失败结果的 map
failure = Result.failure(ValueError("error"))
mapped = failure.map(lambda x: x * 2)
print(mapped)  # 输出: Failure(ValueError('error')) - 保持不变
```

## flat_map / bind - 链式调用

```python
from vools.functional import Result

# flat_map (同 bind): 扁平化映射
def safe_divide(a, b):
    if b == 0:
        return Result.failure(ZeroDivisionError("division by zero"))
    return Result.success(a / b)

# 使用 bind 链式调用
result = (
    Result.success(100)
    .bind(lambda x: safe_divide(x, 2))   # 100 / 2 = 50
    .bind(lambda x: safe_divide(x, 4))   # 50 / 4 = 12.5
)
print(result)  # 输出: Success(12.5)

# 链中某一步失败
result = (
    Result.success(100)
    .bind(lambda x: safe_divide(x, 0))   # 失败!
    .bind(lambda x: safe_divide(x, 2))   # 不会执行
)
print(result)  # 输出: Failure(ZeroDivisionError('division by zero'))
```

## map_err - 映射失败值

```python
from vools.functional import Result

# map_err: 转换失败值，成功时保持不变
def to_custom_error(e):
    return RuntimeError(f"Error occurred: {e}")

# 失败时转换错误
result = Result.failure(ValueError("invalid"))
mapped = result.map_err(to_custom_error)
print(mapped)  # 输出: Failure(RuntimeError('Error occurred: invalid'))

# 成功时 map_err 无效
result = Result.success(42)
mapped = result.map_err(to_custom_error)
print(mapped)  # 输出: Success(42)
```

## unwrap - 获取值

### unwrap

```python
from vools.functional import Result

# unwrap: 获取成功值，失败时抛出异常
result = Result.success(42)
value = result.unwrap()
print(value)  # 输出: 42

# 失败时 unwrap 抛出异常
result = Result.failure(KeyError("missing"))
try:
    value = result.unwrap()
except KeyError as e:
    print(f"Caught: {e}")  # 输出: Caught: 'missing'
```

### unwrap_or

```python
from vools.functional import Result

# unwrap_or: 获取成功值或默认值
result = Result.success(42)
value = result.unwrap_or(0)
print(value)  # 输出: 42

result = Result.failure(ValueError("error"))
value = result.unwrap_or(0)
print(value)  # 输出: 0
```

### unwrap_or_else

```python
from vools.functional import Result

# unwrap_or_else: 获取成功值或通过函数计算的默认值
result = Result.success(42)
value = result.unwrap_or_else(lambda e: len(str(e)) * 10)
print(value)  # 输出: 42

result = Result.failure(ValueError("error"))
value = result.unwrap_or_else(lambda e: len(str(e)) * 10)
print(value)  # 输出: 50 (len("ValueError('error')") * 10 ≈ 50)
```

## or_else - 失败时备选

```python
from vools.functional import Result

# or_else: 失败时执行备选函数
def fallback():
    return Result.success("fallback value")

# 成功时返回原 Result
result = Result.success(42)
new_result = result.or_else(fallback)
print(new_result)  # 输出: Success(42)

# 失败时执行备选函数
result = Result.failure(ValueError("error"))
new_result = result.or_else(fallback)
print(new_result)  # 输出: Success('fallback value')
```

## get_or / get_or_raise

```python
from vools.functional import Result

# get_or: 同 unwrap_or
result = Result.failure(ValueError("error"))
value = result.get_or(100)
print(value)  # 输出: 100

# get_or_raise: 失败时抛出指定异常
result = Result.failure(ValueError("original"))
try:
    value = result.get_or_raise(TypeError("custom error"))
except TypeError as e:
    print(f"Caught: {e}")  # 输出: Caught: custom error
```

## do - 副作用方法

```python
from vools.functional import Result

# do: 执行副作用操作，返回 self
result = Result.success(42)
result = result.do(lambda x: print(f"Value: {x}"))
print(result)  # 输出: Success(42)
# 输出: Value: Success(42)

# do with pre_f
result = Result.success(42)
result = result.do(
    lambda x: print(f"Got: {x}"),
    pre_f=lambda x: x.map(lambda v: v * 2)
)
# 输出: Got: Success(84)
```

## 链式操作完整示例

```python
from vools.functional import Result, safe

@safe
def parse_positive_int(s):
    value = int(s)
    if value <= 0:
        raise ValueError("must be positive")
    return value

@safe
def calculate_factorial(n):
    if n > 10:
        raise ValueError("too large for factorial")
    result = 1
    for i in range(1, n + 1):
        result *= i
    return result

@safe
def format_result(n):
    return f"Factorial: {n}"

# 完整处理流程
def process(s):
    return (
        parse_positive_int(s)
        .bind(calculate_factorial)
        .bind(format_result)
    )

# 测试用例
print(process("5"))      # 输出: Success('Factorial: 120')
print(process("0"))      # 输出: Failure(ValueError('must be positive'))
print(process("abc"))    # 输出: Failure(ValueError("invalid literal for int: 'abc'"))
print(process("20"))     # 输出: Failure(ValueError('too large for factorial'))
```

## 错误处理模式

### 模式1: 使用 map + unwrap_or

```python
from vools.functional import safe

@safe
def get_user_age(name):
    ages = {'Alice': 30, 'Bob': 25, 'Charlie': 35}
    if name not in ages:
        raise KeyError(name)
    return ages[name]

# 获取用户年龄，不存在时返回默认值
age = get_user_age("Dave").map(lambda x: x * 2).unwrap_or(0)
print(age)  # 输出: 0

age = get_user_age("Alice").map(lambda x: x * 2).unwrap_or(0)
print(age)  # 输出: 60
```

### 模式2: 使用 bind 进行条件处理

```python
from vools.functional import Result

def validate_age(age):
    if age < 0:
        return Result.failure(ValueError("age cannot be negative"))
    if age > 150:
        return Result.failure(ValueError("age is too large"))
    return Result.success(age)

def check_voting(age):
    if age >= 18:
        return Result.success("eligible to vote")
    return Result.success("not eligible to vote")

# 链式验证和处理
result = validate_age(25).bind(check_voting)
print(result)  # 输出: Success('eligible to vote')
```

### 模式3: 使用 from_unsafe

```python
from vools.functional import Result

def risky_operation(x):
    if x == 0:
        raise ValueError("division by zero")
    return 100 / x

# 使用 from_unsafe 创建 Result
result = Result.from_unsafe(lambda: risky_operation(0))
print(result)  # 输出: Failure(ValueError('division by zero'))

result = Result.from_unsafe(lambda: risky_operation(10))
print(result)  # 输出: Success(10.0)
```

## 与 Seq 结合使用

```python
from vools.functional import Result, safe
from vools.data import Seq

@safe
def safe_parse_int(s):
    return int(s)

@safe
def safe_divide(x, y):
    return x / y

# 处理字符串列表，转换为 Result 列表
strings = ["10", "20", "abc", "40", "0"]
results = Seq.of(*strings).map(safe_parse_int).collect()

# 过滤成功结果
success_values = Seq.of(*results).filter(lambda r: r.is_success).map(lambda r: r.unwrap()).collect()
print(f"成功解析: {success_values}")  # 输出: 成功解析: [10, 20, 40]

# 计算有效结果的总和
total = (
    Seq.of(*results)
    .filter(lambda r: r.is_success)
    .map(lambda r: r.unwrap())
    .reduce(lambda x, y: x + y)
)
print(f"总和: {total}")  # 输出: 70
```

## 序列化支持

```python
from vools.functional import Result
import json

# Result 支持序列化
success = Result.success({'data': [1, 2, 3]})
failure = Result.failure(ValueError("test error"))

# 序列化
print(json.dumps(success.__getstate__()))  # 输出: {"_value": {"data": [1, 2, 3]}, "_is_success": true}

# 反序列化
new_success = Result.success(None)
new_success.__setstate__({'_value': {'data': [1, 2, 3]}, '_is_success': True})
print(new_success)  # 输出: Success({'data': [1, 2, 3]})
```
