# rself 装饰器 API 文档

## 概述

`rself` 是一个 Python 类装饰器，用于实现链式调用支持。当创建继承自不可变类型（如 `str`、`int`）的子类时，父类方法通常返回的是父类实例而非子类实例。`rself` 装饰器自动处理这种类型转换，使得链式调用能够正常工作。

## 安装

```python
from vools.decorators import rself
```

## 核心功能

### 1. 方法返回值自动转换

- **返回 `None`** → 返回自身实例
- **返回父类实例** → 转换为子类实例
- **返回同类实例** → 保持原返回值

### 2. 自定义初始化支持（新增）

通过定义 `__from_parent__` 类方法，可以自定义父类实例到子类的转换逻辑，支持传递额外参数。

## API 参考

### `@rself`

类装饰器，实现链式调用支持。

**参数**: 无

**返回值**: 装饰后的类

### `__from_parent__`（可选）

自定义工厂方法，用于控制父类实例到子类的转换逻辑。

**签名**:
```python
@classmethod
def __from_parent__(cls, parent_val, **kwargs) -> 'SubClass':
    """
    参数:
        cls: 类本身
        parent_val: 父类实例的值
        **kwargs: 初始化时传入的额外参数
    返回:
        子类实例
    """
```

## 使用示例

### 基础用法

```python
from vools.decorators import rself

@rself
class SuperText(str):
    """扩展的字符串类"""
    def __new__(cls, value=""):
        return super().__new__(cls, value)

# 使用
s = SuperText("hello")
result = s.upper()  # 返回 SuperText 类型
print(type(result))  # <class 'SuperText'>
print(str(result))    # "HELLO"
```

### 自定义初始化（高级）

当子类有额外的初始化参数时，使用 `__from_parent__` 来保留这些参数：

```python
from vools.decorators import rself

@rself
class StyledText(str):
    """带样式的字符串类"""
    def __new__(cls, value="", prefix="", suffix=""):
        instance = super().__new__(cls, value)
        instance._prefix = prefix
        instance._suffix = suffix
        return instance

    @classmethod
    def __from_parent__(cls, parent_val, **kwargs):
        """自定义转换逻辑"""
        prefix = kwargs.get('prefix', '')
        suffix = kwargs.get('suffix', '')
        return cls(str(parent_val), prefix=prefix, suffix=suffix)

    def format(self):
        """返回带前后缀的字符串"""
        return f"{self._prefix}{str(self)}{self._suffix}"

# 使用
s = StyledText("hello", prefix=">> ", suffix=" <<")
print(s.format())  # ">> hello <<"

# 链式调用
result = s.upper()
print(type(result))  # <class 'StyledText'>
print(result.format())  # ">> HELLO <<"
```

### 无继承类

```python
@rself
class Builder:
    """无继承的构建器类"""
    def __init__(self, value=""):
        self._value = value

    def add(self, s):
        """添加内容"""
        return Builder(self._value + s)

# 使用
b = Builder("a").add("b").add("c")
print(b._value)  # "abc"
```

### 继承链支持

```python
from vools.decorators import rself

@rself
class Text(str):
    def __new__(cls, value=""):
        return super().__new__(cls, value)

@rself
class ExtendedText(Text):
    def __new__(cls, value="", style=""):
        instance = super().__new__(cls, value)
        instance._style = style
        return instance

    @classmethod
    def __from_parent__(cls, parent_val, **kwargs):
        return cls(str(parent_val), style=kwargs.get('style', 'default'))

# 使用
e = ExtendedText("hello", style="bold")
result = e.upper()
print(type(result))  # <class 'ExtendedText'>
```

## 限制

### 继承限制

`@rself` 仅支持单继承或不继承，不支持多继承。

```python
# 错误用法 - 会抛出 TypeError
@rself
class Multi(str, list):  # TypeError: @rself 仅支持单继承或不继承
    pass
```

### 魔法方法

以下成员不受装饰器影响：
- 魔法方法（如 `__init__`、`__getattr__`、`__add__` 等）
- 以下划线开头的成员

### 不可变类型

对于 `str`、`int`、`bool` 等不可变类型：
- 算术运算符（如 `+`）仍然返回基类型
- 使用方法链式调用（如 `s.upper()`）可以正常工作

## 内部机制

### kwargs 存储

装饰器通过以下方式存储初始化参数：

1. **可变类型**（如 `list`、`dict`）：在 `__init__` 中存储到 `_rself_kwargs` 属性
2. **不可变类型**（如 `str`、`int`）：在 `__new__` 中存储到 `_rself_kwargs` 属性

### 类型转换流程

```
1. 调用方法（如 s.upper()）
2. __getattribute__ 拦截方法调用
3. 执行原始方法，返回父类实例
4. _wrap_return_value 处理返回值：
   a. 如果返回 None → 返回 self
   b. 如果已是自己 → 直接返回
   c. 如果是父类实例：
      - 尝试从 self._rself_kwargs 获取 kwargs
      - 调用 __from_parent__(value, **kwargs)
      - 或使用默认的 cls(value)
```

## 完整测试覆盖

详见 `tests/test_rself.py`，包含以下测试类别：

- 基础功能测试
- 单继承测试
- `__from_parent__` 工厂方法测试
- 链式调用测试
- 返回值处理测试
- 多继承限制测试
- 边界条件测试
- 装饰器使用测试
- 属性和类方法测试

## 性能注意事项

- 装饰器在方法调用时增加了轻微的包装开销
- 对于性能敏感的场景，建议谨慎使用
- kwargs 存储会增加少量内存开销

## 错误处理

| 错误类型 | 原因 | 解决方案 |
|---------|------|---------|
| `TypeError: @rself 仅支持单继承` | 使用了多继承 | 改用单继承 |
| `TypeError: 构造函数不支持...` | 构造函数需要额外参数但没有 `__from_parent__` | 定义 `__from_parent__` 方法 |

## 版本历史

- **0.1.16**: 新增 `__from_parent__` 支持，可自定义初始化逻辑