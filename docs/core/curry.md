# 柯里化装饰器

> **模块路径**：`vools.decorators`
> **依赖版本**：Python 3.6+
> **平台支持**：Windows/macOS/Linux
> **测试状态**：✅ 已测试
> **编号**：#007
> **最后更新**：2026-06-30

## 概述

柯里化是将接受多个参数的函数转换为一系列接受单个参数的函数的过程，使得函数可以部分应用参数并返回新的函数。

## 导入方式

```python
from vools import curry, Curried, CurryDescriptor, is_curried
from vools import delay_curry, DelayCurried, is_lazy
from vools import curry_class
```

## @curry - 标准柯里化装饰器

### 基本用法

```python
# test_curry_basic.py
from vools import curry

@curry
def add(a, b, c):
    return a + b + c

# 完全柯里化调用
result = add(1)(2)(3)
print(f"add(1)(2)(3) = {result}")  # 输出: add(1)(2)(3) = 6

# 部分参数调用
add1 = add(1)
result = add1(2)(3)
print(f"add1(2)(3) = {result}")  # 输出: add1(2)(3) = 6

# 组合调用
result = add(1, 2)(3)
print(f"add(1, 2)(3) = {result}")  # 输出: add(1, 2)(3) = 6

result = add(1)(2, 3)
print(f"add(1)(2, 3) = {result}")  # 输出: add(1)(2, 3) = 6

# 一次性调用
result = add(1, 2, 3)
print(f"add(1, 2, 3) = {result}")  # 输出: add(1, 2, 3) = 6
```

### 带默认参数的柯里化

```python
# test_curry_defaults.py
from vools import curry

@curry
def greet(greeting, name="World", punctuation="!"):
    return f"{greeting}, {name}{punctuation}"

# 测试各种调用方式
print(f"greet('Hello')('Alice') = {greet('Hello')('Alice')}")  # 输出: greet('Hello')('Alice') = Hello, Alice!
print(f"greet('Hi', 'Bob') = {greet('Hi', 'Bob')}")              # 输出: greet('Hi', 'Bob') = Hi, Bob!
print(f"greet('Hey')(name='Carol') = {greet('Hey')(name='Carol')}")  # 输出: greet('Hey')(name='Carol') = Hey, Carol!
```

### 关键字参数

```python
# test_curry_kwargs.py
from vools import curry

@curry
def configure(name, timeout=30, debug=False, prefix=""):
    return {
        "name": name,
        "timeout": timeout,
        "debug": debug,
        "prefix": prefix
    }

# 关键字参数调用
result = configure("myservice")(timeout=60, debug=True)
print(f"configure('myservice')(timeout=60, debug=True) = {result}")
# 输出: configure('myservice')(timeout=60, debug=True) = {'name': 'myservice', 'timeout': 60, 'debug': True, 'prefix': ''}
```

### 严格模式

```python
# test_curry_strict.py
from vools import curry

@curry(is_strict=True)
def add_int(a: int, b: int) -> int:
    return a + b

# 类型正确
result = add_int(1)(2)
print(f"add_int(1)(2) = {result}")  # 输出: add_int(1)(2) = 3

# 类型错误会抛出异常
try:
    result = add_int("1")(2)
    print(f"结果: {result}")
except TypeError as e:
    print(f"类型错误: {e}")
# 输出: 类型错误: Argument 'a' expects type <class 'int'>, got <class 'str'>
```

## @delay_curry - 延迟柯里化

延迟柯里化返回 Curried 对象而不是立即执行。

```python
# test_delay_curry.py
from vools import delay_curry

@delay_curry
def multiply(a, b, c):
    return a * b * c

# 延迟调用 - 返回 Curried 对象
curried = multiply(2)
print(f"类型: {type(curried)}")  # 输出: 类型: <class 'vools.curried.core.Curried'>

# 检查状态
print(f"is_ready: {curried.is_ready}")  # 输出: is_ready: False

# 继续添加参数
curried2 = curried(3)
print(f"is_ready: {curried2.is_ready}")  # 输出: is_ready: False

# 执行
result = curried2(4)
print(f"result = {result}")  # 输出: result = 24
```

## @curry_class - 类柯里化装饰器

对类中所有非魔法实例方法进行柯里化转换，支持链式调用。

```python
# test_curry_class.py
from vools import curry_class

@curry_class
class Calculator:
    def add(self, a, b, c):
        return a + b + c
    
    def multiply(self, x, y):
        return x * y

calc = Calculator()

# 链式调用
result = calc.add(1).add(2).add(3)
print(f"calc.add(1).add(2).add(3) = {result}")  # 输出: calc.add(1).add(2).add(3) = 6

# 乘法链式调用
result = calc.multiply(5).multiply(6)
print(f"calc.multiply(5).multiply(6) = {result}")  # 输出: calc.multiply(5).multiply(6) = 30

# 组合调用
result = calc.add(1, 2).multiply(3)
print(f"calc.add(1, 2).multiply(3) = {result}")  # 输出: calc.add(1, 2).multiply(3) = 9
```

### 带可变参数的方法

```python
# test_curry_class_varargs.py
from vools import curry_class

@curry_class
class SumCalculator:
    def sum_all(self, a, b, *args):
        total = a + b + sum(args)
        return total

summer = SumCalculator()

# 可变参数方法调用
result = summer.sum_all(1, 2)
print(f"summer.sum_all(1, 2) = {result}")  # 输出: summer.sum_all(1, 2) = 3

# 使用空括号触发执行
result = summer.sum_all(1).sum_all(2).sum_all(3, 4).sum_all()
print(f"summer.sum_all(1).sum_all(2).sum_all(3, 4).sum_all() = {result}")  # 输出: = 10
```

## Curried 对象

### 属性

```python
# test_curried_props.py
from vools import curry

@curry
def add(a, b, c):
    return a + b + c

curried = add(1)

# is_ready - 检查必需参数是否已绑定
print(f"is_ready: {curried.is_ready}")  # 输出: is_ready: False

curried2 = curried(2)
print(f"is_ready: {curried2.is_ready}")  # 输出: is_ready: True

# is_full - 检查是否所有参数都已绑定
print(f"is_full: {curried2.is_full}")  # 输出: is_full: True

# func - 原始函数
print(f"func.__name__: {curried2.func.__name__}")  # 输出: func.__name__: add

# bound_args - 已绑定的参数
print(f"bound_args: {curried2.bound_args}")  # 输出: bound_args: {'a': 1, 'b': 2}
```

### 方法

```python
# test_curried_methods.py
from vools import curry

@curry
def add(a, b, c):
    return a + b + c

# 执行
curried = add(1, 2)
result = curried(3)
print(f"result = {result}")  # 输出: result = 6
```

## is_curried - 类型检查

```python
# test_is_curried.py
from vools import curry, is_curried

@curry
def curried_func(x, y):
    return x + y

def normal_func(x, y):
    return x + y

curried = curried_func(1)
print(f"is_curried(curried) = {is_curried(curried)}")  # 输出: is_curried(curried) = True
print(f"is_curried(normal_func) = {is_curried(normal_func)}")  # 输出: is_curried(normal_func) = False
```

## 装饰器参数

### @curry 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `func` | Callable | None | 要柯里化的函数 |
| `is_strict` | bool | False | 是否进行类型检查 |
| `delaied` | bool | False | 是否延迟执行 |

### @curry_class 参数

无额外参数，直接应用于类。

## 使用场景

### 函数组合

```python
# test_curry_compose.py
from vools import curry

@curry
def add(a, b):
    return a + b

@curry
def multiply(a, b):
    return a * b

@curry
def subtract(a, b):
    return a - b

# 创建计算流程
add5 = add(5)
double = multiply(2)
sub3 = subtract(3)

# 组合使用
result = double(add5(10))
print(f"double(add5(10)) = {result}")  # 输出: double(add5(10)) = 30

result = sub3(double(add5(10)))
print(f"sub3(double(add5(10))) = {result}")  # 输出: sub3(double(add5(10))) = 27
```

### 预配置函数

```python
# test_curry_partial.py
from vools import curry

@curry
def create_user(name, age, city, country):
    return {"name": name, "age": age, "city": city, "country": country}

# 预设部分参数
create_user_usa = create_user(country="USA")
create_user_ny = create_user_usa(city="New York")

# 最终调用
user = create_user_ny("Alice", 30)
print(f"user = {user}")
# 输出: user = {'name': 'Alice', 'age': 30, 'city': 'New York', 'country': 'USA'}
```

## 注意事项

1. **参数顺序**：柯里化按参数顺序绑定
2. **可选参数**：支持带默认值的参数
3. **关键字参数**：支持关键字参数调用
4. **类型检查**：可选的严格模式进行类型检查
5. **方法绑定**：实例方法自动处理 self 参数

## 相关文档

- [函数重载文档](./overload.md)
- [装饰器总览](./decorators.md)
