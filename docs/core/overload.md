# 函数重载装饰器

> **模块路径**：`vools.decorators`
> **依赖版本**：Python 3.6+
> **平台支持**：Windows/macOS/Linux
> **测试状态**：✅ 已测试
> **编号**：#006
> **最后更新**：2026-06-30

## 概述

vools 提供基于模式标志的函数重载系统，支持优先级模式、严格类型检查、模糊匹配等多种重载策略。

## 导入方式

```python
from vools import overload, overcurry, overloads
from vools import OverloadMode, Priority, Strict, AllowSyncName, Ambiguous
```

## @overload - 基础重载装饰器

### 基本用法

```python
# test_overload_basic.py
from vools import overload

@overload
def add(a, b):
    """基础加法 - 处理任意类型"""
    return a + b

@add.register
def add_int(a: int, b: int):
    """整数加法"""
    return a + b

@add.register
def add_str(a: str, b: str):
    """字符串拼接"""
    return a + b

# 测试
print(f"add(1, 2) = {add(1, 2)}")      # 输出: add(1, 2) = 3
print(f"add('a', 'b') = {add('a', 'b')}")  # 输出: add('a', 'b') = ab
print(f"add(1.5, 2.5) = {add(1.5, 2.5)}")  # 输出: add(1.5, 2.5) = 4.0
```

### 带优先级的重载

```python
# test_overload_priority.py
from vools import overload

@overload
def process(x):
    """默认处理器 - 最低优先级"""
    return f"默认: {x}"

@process.register(priority=1)
def process_int(x: int):
    """整数处理器 - 更高优先级"""
    return f"整数: {x * 2}"

@process.register(priority=2)
def process_positive(x: int):
    """正整数处理器 - 最高优先级"""
    if x > 0:
        return f"正整数: {x}"
    return None  # 返回 None 时不匹配，继续尝试其他

# 测试
print(f"process(5) = {process(5)}")      # 输出: process(5) = 正整数: 5
print(f"process(-3) = {process(-3)}")     # 输出: process(-3) = 整数: -6
print(f"process('hello') = {process('hello')}")  # 输出: process('hello') = 默认: hello
```

### 严格类型检查

```python
# test_overload_strict.py
from vools import overload, Strict

@overload(mode=Strict)
def calculate(a, b):
    """混合类型处理"""
    return f"混合: {a}, {b}"

@calculate.register
def calculate_int_float(a: int, b: float):
    """整数+浮点数"""
    return a + b

@calculate.register
def calculate_str_int(a: str, b: int):
    """字符串+整数"""
    return a * b

# 测试
print(f"calculate(10, 3.14) = {calculate(10, 3.14)}")  # 输出: calculate(10, 3.14) = 13.14
print(f"calculate('Hi', 3) = {calculate('Hi', 3)}")    # 输出: calculate('Hi', 3) = HiHiHi
```

## @overcurry - 柯里化重载

结合了 curry 和 overload 的特性，支持链式参数收集。

```python
# test_overcurry.py
from vools import overcurry

@overcurry
def add(a, b):
    """两数相加"""
    return a + b

@add.register
def add3(a, b, c):
    """三数相加"""
    return a + b + c

# 柯里化调用
print(f"add(1)(2) = {add(1)(2)}")        # 输出: add(1)(2) = 3
print(f"add(1)(2)(3) = {add(1)(2)(3)}")  # 输出: add(1)(2)(3) = 6

# 混合调用
print(f"add(1, 2) = {add(1, 2)}")        # 输出: add(1, 2) = 3
print(f"add(1)(2, 3) = {add(1)(2, 3)}")  # 输出: add(1)(2, 3) = 6
```

### 注册多个重载

```python
# test_overcurry_multi.py
from vools import overcurry

@overcurry
def multiply(a, b):
    """两数相乘"""
    return a * b

@multiply.register
def multiply3(a, b, c):
    """三数相乘"""
    return a * b * c

# 测试各种调用方式
print(f"multiply(2)(3) = {multiply(2)(3)}")          # 输出: multiply(2)(3) = 6
print(f"multiply(2)(3)(4) = {multiply(2)(3)(4)}")    # 输出: multiply(2)(3)(4) = 24
print(f"multiply(2, 3)(4) = {multiply(2, 3)(4)}")    # 输出: multiply(2, 3)(4) = 24
```

## @overloads - 多函数选择器

基于参数类型/数量自动选择匹配的函数。

```python
# test_overloads.py
from vools import overloads

@overloads
def operate(*args):
    """默认处理器"""
    return f"默认: {args}"

@operate.register
def operate2(a, b):
    """两个参数"""
    return f"2参数: {a}, {b}"

@operate.register
def operate3(a, b, c):
    """三个参数"""
    return f"3参数: {a}, {b}, {c}"

# 测试
print(f"operate(1) = {operate(1)}")                      # 输出: operate(1) = 默认: (1,)
print(f"operate(1, 2) = {operate(1, 2)}")                # 输出: operate(1, 2) = 2参数: 1, 2
print(f"operate(1, 2, 3) = {operate(1, 2, 3)}")          # 输出: operate(1, 2, 3) = 3参数: 1, 2, 3
```

### 带类型注解的选择

```python
# test_overloads_typed.py
from vools import overloads

@overloads
def format_value(value):
    """默认格式化"""
    return str(value)

@format_value.register
def format_int(value: int):
    """整数格式化 - 二进制"""
    return bin(value)

@format_value.register
def format_str(value: str):
    """字符串格式化 - 大写"""
    return value.upper()

# 测试
print(f"format_value(42) = {format_value(42)}")        # 输出: format_value(42) = 101010
print(f"format_value('hello') = {format_value('hello')}")  # 输出: format_value('hello') = HELLO
print(f"format_value(3.14) = {format_value(3.14)}")    # 输出: format_value(3.14) = 3.14
```

## 重载模式详解

### OverloadMode 标志

```python
# test_overload_mode.py
from vools import OverloadMode, Priority, Strict, AllowSyncName, Ambiguous

# 默认模式：Priority | Strict | AllowSyncName
default_mode = Priority | Strict | AllowSyncName

# 仅 Priority
priority_only = Priority

# Priority + Ambiguous（允许多个候选匹配）
fuzzy_mode = Priority | Ambiguous

# 严格模式
strict_mode = Priority | Strict
```

### 模式说明

| 模式 | 说明 |
|------|------|
| `Priority` | 按 priority 属性排序匹配，允许多个候选 |
| `AllowSyncName` | 允许函数名与原始函数不同（需配合 Priority） |
| `Strict` | 按参数类型注解精确匹配 |
| `Ambiguous` | 多个候选时取第一个，而非报错 |

## register 方法

### 链式注册

```python
# test_register_chain.py
from vools import overload

@overload
def calculate(x):
    return x

manager = calculate.register(lambda x: f"lambda: {x}", priority=0)
manager.register(lambda x: f"int: {x}", priority=1)

# 等价于
@overload
def calculate2(x):
    return x

@calculate2.register(priority=0)
def calculate2_0(x):
    return f"lambda: {x}"

@calculate2.register(priority=1)
def calculate2_1(x):
    return f"int: {x}"
```

### export_mode 参数

```python
# test_export_mode.py
from vools import overload, OverloadMode

# 返回原函数（默认）
@overload(export_mode=None)
def func1(x):
    return x

# 返回新管理器
@overload(export_mode='manager')
def func2(x):
    return x
```

## 装饰器参数

### @overload 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `func` | Callable | None | 被装饰的函数 |
| `mode` | OverloadMode | Priority \| Strict \| AllowSyncName | 重载模式 |
| `priority` | int | 0 | 主函数优先级 |
| `export_mode` | str | None | register 返回策略 |

### @overload.register 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `func` | Callable | None | 要注册的函数 |
| `priority` | int | 0 | 优先级 |
| `export_mode` | str | None | 返回策略 |

## 注意事项

1. **类型检查**：Strict 模式下会检查参数类型注解
2. **优先级**：数值越大优先级越高
3. **命名约束**：非 Priority 模式下注册函数必须同名
4. **序列化**：OverloadManager 支持 pickle 序列化

## 相关文档

- [柯里化文档](./curry.md)
- [装饰器总览](./decorators.md)
