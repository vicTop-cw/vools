# vools 核心功能

本指南涵盖占位符、重载装饰器、stuff、persist、box、g、iif 等核心模块。

---

## 快速示例

```python
from vools import _, _1, _2, overload, stuff, persist

# 占位符
f = _ + 1
print(f(2))  # 输出: 3

f = _1 + _2
print(f(1, 2))  # 输出: 3

# 使用重载
@overload
def process():
    return "无参数"

@process.register
def process(x):
    return f"一个参数: {x}"

print(process())     # 输出: 无参数
print(process(10))   # 输出: 一个参数: 10

# 使用 stuff
@stuff
def add(a, b, c):
    return a + b + c

result = add(1)(2)(3)()
print(result)  # 输出: 6

# 使用 persist
@persist(filepath='cache.pkl')
def expensive_computation(x):
    return x ** 2

result = expensive_computation(5)
print(result)  # 输出: 25
```

## 占位符

占位符提供了一种简洁的方式来创建匿名函数，特别适合函数式编程场景。

### 基本用法

```python
from vools.functional.placeholder import _, _1, _2, _3, f, magic, hd

# 基本运算符
f = _ + 1
assert f(2) == 3

# 二元运算符
f = _ + _
assert f(1, 2) == 3

# 索引占位符
f = _1 + _2
assert f(1, 2) == 3

# 属性访问
f = _.upper
assert f("hello")() == "HELLO"

# 索引访问
f = _[0]
assert f([1, 2, 3]) == 1

# 复杂表达式
f = _1 * (_2 + _3)
assert f(2, 3, 4) == 14
```

### __expr__ 方法

```python
# 单行表达式
f1 = _.__expr__("_ + 1")
assert f1(2) == 3

# 索引表达式
f2 = _.__expr__("_1 + _2 * _3")
assert f2(1, 2, 3) == 7
```

### f 函数

```python
def add(a, b):
    return a + b

# 使用 f 函数构造占位符表达式
f1 = f(add, _, _)
assert f1(1, 2) == 3
```

### magic 对象

magic 对象提供了一系列魔法方法的快捷访问：

```python
# 使用 magic 方法
result = magic.map([1, 2, 3], lambda x: x * 2)
# 支持的方法包括：map, filter, reduce, fold, compose, pipe, curry 等
```

### 转换方法

```python
# 类型转换
f = _.toString
assert f(123) == "123"

f = _.toInt
assert f("123") == 123

f = _.toList
assert f(range(3)) == [0, 1, 2]
```

### 逻辑操作

```python
# 逻辑运算
f = _.and_(_ > 0, _ < 10)
assert f(5) == True

f = _.or_(_ == 0, _ == 1)
assert f(0) == True
```

## 重载装饰器

vools 提供三种不同的重载装饰器实现，适用于不同场景。

### 1. @overload - 基于参数数量的重载

```python
from vools import overload, strict

# 基本用法
@overload
def process():
    return "无参数"

@process.register
def process_x(x):
    return f"一个参数: {x}"

@process.register
def process_xy(x, y):
    return f"两个参数: {x}, {y}"

assert process() == "无参数"
assert process(10) == "一个参数: 10"
assert process(20, 30) == "两个参数: 20, 30"

# 严格模式（类型检查）
@overload(is_strict=True)
def add(a: int, b: int):
    return a + b

@add.register
def add_str(a: str, b: str):
    return a + b

assert add(1, 2) == 3
assert add("a", "b") == "ab"

# 优先级控制
@overload(priority='first')
def process():
    return "主函数"

@process.register(priority=1)
def process_one(arg):
    return f"优先级1: {arg}"

@process.register(priority=10)
def process_high(arg):
    return f"高优先级: {arg}"

assert process("hello") == "高优先级: hello"

# 类方法重载
class Processor:
    def __init__(self, prefix):
        self.prefix = prefix
    
    @overload(is_strict=True)
    def process(self):
        return f"{self.prefix}: 无参数"
    
    @process.register
    def process_int(self, x: int):
        return f"{self.prefix}: 整数({x})"
    
    @process.register
    def process_str(self, x: str):
        return f"{self.prefix}: 字符串({x})"

proc = Processor("测试")
assert proc.process() == "测试: 无参数"
assert proc.process(10) == "测试: 整数(10)"
assert proc.process("text") == "测试: 字符串(text)"
```

### 2. @overcurry - 柯里化与重载结合

```python
from vools import overcurry

# 基本用法
@overcurry
def add(a, b):
    return a + b

@add.register
def add_3(a, b, c):
    return a + b + c

@add.register
def add_4(a, b, c, d):
    return a + b + c + d

# 柯里化调用
assert add(1)(2) == 3
assert add(1, 2, 3) == 6
assert add(1, 2, 3, 4) == 10

# 严格模式（类型检查）
@overcurry(is_strict=True)
def process(a: int, b: int):
    return a + b

@process.register
def process_str(a: str, b: str):
    return a + b

assert process(1)(2) == 3
assert process("hello")(" world") == "hello world"
```

### 3. @overloads - 同名方法重载

```python
from vools import overloads

class Calculator:
    @overloads
    def compute(self, x: int):
        return x * 2
    
    @overloads
    def compute(self, x: str):
        return len(x)
    
    @overloads
    def compute(self, x: list):
        return sum(x)

calc = Calculator()
assert calc.compute(5) == 10
assert calc.compute("hello") == 5
assert calc.compute([1, 2, 3]) == 6
```

### 三种重载方式对比

| 特性 | @overload | @overcurry | @overloads |
|------|-----------|------------|------------|
| 柯里化支持 | 否 | 是 | 否 |
| 类型检查 | 支持 | 支持 | 支持 |
| 优先级控制 | 支持 | 否 | 否 |
| 类方法支持 | 是 | 是 | 是 |
| 注册方式 | register | register | 同名方法 |

## stuff 函数

stuff 函数是一个强大的依赖注入装饰器，允许函数参数在运行时自动解析。

### 基本用法

```python
from vools import stuff

@stuff
def add(a, b, c):
    return a + b + c

# 柯里化调用
result = add(1)(2)(3)()
assert result == 6

# 批量参数
result = add(1, 2, 3)()
assert result == 6
```

### 参数依赖注入

```python
@stuff
def multiply(a, b, c):
    return a * b * c

@multiply.register
def get_a():
    return 2

@multiply.register(param_name=['b', 'c'])
def get_bc():
    return 3, 4

# 自动注入参数
result = multiply()
assert result == 24
```

### 高级用法

```python
@stuff
def connect(host, port, timeout):
    return f"连接到 {host}:{port}，超时 {timeout} 秒"

@connect.register
def host():
    return "localhost"

@connect.register(param_name='port')
def get_port():
    return 8080

# 覆盖注入参数
result = connect(timeout=30)
assert result == "连接到 localhost:8080，超时 30 秒"

# 部分注入
result = connect(host="192.168.1.1")
assert result == "连接到 192.168.1.1:8080，超时 None 秒"
```

## persist 装饰器

`persist` 装饰器将函数的执行结果缓存到本地文件，并提供灵活的刷新控制，引擎重启后缓存仍然有效。

### 基本用法

```python
from vools import persist

@persist
def expensive_computation(x):
    import time
    time.sleep(1)  # 模拟耗时计算
    return x ** 2

# 第一次执行，保存结果
result = expensive_computation(5)  # 耗时约 1 秒
assert result == 25

# 第二次执行，直接返回缓存（跳过计算）
result = expensive_computation(5)  # 几乎立即返回
assert result == 25
```

### 调用时的关键字参数

被装饰的函数会自动获得以下关键字参数：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `file_key` | str | None | 缓存文件名（不含扩展名），默认使用函数名 |
| `force` | bool | False | 是否强制重新执行，忽略缓存 |
| `force_when` | Callable | None | 当 `force=False` 时，若此函数返回 `True` 则强制刷新 |
| `target_folder` | str | None | 缓存文件所在目录，默认与被装饰函数所在文件同级的 `__persist__` 目录 |

### 高级用法

```python
# 使用 file_key 指定缓存文件名
@persist
def fetch_weather(city):
    import random
    print(f"[执行] 正在获取 {city} 的天气...")
    return random.randint(20, 30)

# 使用 file_key 区分不同参数的缓存
temp = fetch_weather("Beijing", file_key="weather_beijing")
temp = fetch_weather("Shanghai", file_key="weather_shanghai")

# 强制刷新缓存
temp = fetch_weather("Beijing", file_key="weather_beijing", force=True)

# 使用 force_when 条件刷新
# 示例：距离上次执行超过 5 秒或温度高于 27 度时刷新
import time
temp = fetch_weather(
    "Beijing",
    file_key="weather_beijing",
    force_when=lambda result, start, end: time.time() - end > 5 or result > 27
)

# 指定缓存目录
import tempfile
temp_dir = tempfile.mkdtemp()
temp = fetch_weather("Beijing", file_key="weather_beijing", target_folder=temp_dir)
```

### force_when 参数说明

`force_when` 函数接收三个参数：

| 参数 | 类型 | 说明 |
|------|------|------|
| `result` | Any | 缓存的结果值 |
| `start` | float | 上次执行的开始时间戳 |
| `end` | float | 上次执行的结束时间戳 |

返回 `True` 时强制重新执行，返回 `False` 时使用缓存。

### 注意事项

- 函数返回值必须可 JSON 序列化（基本类型、列表、字典、None）
- 缓存文件保存为 JSON 格式，包含 `result`、`start_time`、`end_time`
- 默认缓存目录为与被装饰函数所在文件同级的 `__persist__` 目录

## box 装饰器

### 基本用法

`box` 装饰器用于将函数的返回值包装成 `Box` 对象，提供链式调用能力。

```python
from vools.functional.box import box

@box
def get_user():
    return {"name": "Alice", "age": 30}

result = get_user().name.upper()
# 结果: "ALICE"
```

### 参数说明

| 参数 | 类型 | 说明 |
|------|------|------|
| `func` | Callable | 要包装的函数 |
| `cover` | bool | 是否覆盖已存在的属性，默认 `True` |

### 返回值

返回一个包装后的函数，其返回值会被自动包装成 `Box` 对象。

### 示例代码

```python
from vools.functional.box import box

@box
def calculate():
    return {"value": 42}

result = calculate().value * 2
print(result)  # 84
```

## Box 类

### 基本用法

`Box` 类是一个通用包装器，允许以属性访问的方式访问字典的键。

```python
from vools.functional.box import Box

data = Box({"name": "Bob", "age": 25})
print(data.name)  # "Bob"
print(data.age)   # 25
```

### 核心方法

#### `run(func, *args, **kwargs)`

执行函数并可选地展开包装的值作为参数。

```python
box = Box([1, 2, 3])
result = box.run(sum)
print(result)  # 6
```

#### `copy()`

创建一个浅拷贝。

```python
original = Box({"a": 1})
copied = original.copy()
```

### 属性访问

`Box` 支持通过 `.` 操作符访问属性：

```python
data = Box({"user": {"name": "Charlie"}})
print(data.user.name)  # "Charlie"
```

### 边界情况

```python
# 访问不存在的属性返回 None
data = Box({})
print(data.nonexistent)  # None

# 包装 None 值
data = Box(None)
print(data.value)  # None
```

## g 函数

### 基本用法

`g` 函数是一个通用函数生成器，支持多种表达式格式。

```python
from vools.functional.arrow_func import g

# lambda 表达式格式
f1 = g("x, y => x + y")
print(f1(3, 4))  # 7

# 下划线占位符格式
f2 = g("_ + 2 * _")
print(f2(3, 4))  # 11

# 带索引的下划线格式
f3 = g("_1 + _2")
print(f3(3, 4))  # 7

# 标准 lambda 表达式
f4 = g("lambda x: x + 1")
print(f4(5))  # 6
```

### 参数说明

| 参数 | 类型 | 说明 |
|------|------|------|
| `expr` | str | 字符串表达式 |
| `env` | Dict | 执行环境变量字典，可选 |

### 支持的表达式格式

1. **箭头函数格式**: `x, y => x + y`
2. **下划线占位符**: `_ + 2 * _`
3. **索引下划线**: `_1 + _2`
4. **标准 lambda**: `lambda x: x + 1`
5. **三元表达式**: `_ > 0 ? _ : -_`

### 返回值

返回生成的函数对象。

### 示例代码

```python
from vools.functional.arrow_func import g

# 复杂表达式
f = g("_1 ** 2 + _2 ** 2")
print(f(3, 4))  # 25

# 使用环境变量
env = {"PI": 3.14}
f = g("_ * PI", env)
print(f(2))  # 6.28

# 无参数函数
f = g("3 + 5")
print(f())  # 8
```

## iif 函数

### 基本用法

`iif` 函数提供条件表达式支持，类似 Excel 的 `IF` 函数。

```python
from vools.functional.iif import iif

# 基本条件判断
result = iif(True, "yes", "no")
print(result)  # "yes"

result = iif(False, "yes", "no")
print(result)  # "no"
```

### 参数说明

| 参数 | 类型 | 说明 |
|------|------|------|
| `base` | Any | 条件值或表达式 |
| `true_body` | Any | 条件为真时的返回值 |
| `false_body` | Any | 条件为假时的返回值 |
| `comp` | str | 比较运算符，默认 `'=='` |
| `cases` | Iterable | 案例列表 |
| `whens` | Iterable | 条件列表 |
| `supp` | bool | 是否支持补充运算符，默认 `True` |

### 返回值

根据条件返回 `true_body` 或 `false_body`，或返回一个 `ConditionBuilder` 对象。

### 使用 ConditionBuilder

```python
from vools.functional.iif import iif

# 使用链式调用
result = iif(5).when(lambda x: x > 10, "big").otherwise("small")
print(result())  # "small"

# 使用 case 方法
result = iif(3).case(1, "one").case(2, "two").case(3, "three").otherwise("other")
print(result())  # "three"

# 使用 whens 参数
result = iif(15, whens=[(lambda x: x > 10, "big"), (lambda x: x <= 10, "small")])
print(result)  # "big"
```

### 支持的运算符

| 运算符 | 说明 |
|--------|------|
| `==`, `=` | 等于 |
| `!=` | 不等于 |
| `>` | 大于 |
| `<` | 小于 |
| `>=` | 大于等于 |
| `<=` | 小于等于 |
| `in` | 包含 |
| `not in` | 不包含 |
| `is` | 身份判断 |
| `is not` | 非身份判断 |

### 示例代码

```python
from vools.functional.iif import iif

# 可调用条件
result = iif(lambda: len([1, 2, 3]) > 2, "long", "short")
print(result)  # "long"

# 表达式模式
result = iif("5 > 3", true_body="yes", false_body="no", supp=True)
print(result)  # "yes"

# None 条件被视为 False
result = iif(None, "yes", "no")
print(result)  # "no"
```
