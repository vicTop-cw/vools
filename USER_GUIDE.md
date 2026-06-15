# vools 用户指南

本指南基于实际测试用例和模块代码，详细展示 vools 库的核心功能和使用方法。

> **📖 分册指南**: 此文档已被拆分为 `guide/` 目录下的多个主题文档，更方便查阅：
> - [核心功能](guide/core.md) — 占位符、重载、stuff、persist、Box、g、iif
> - [函数式编程](guide/functional.md) — curried 模块、管道操作
> - [vic 工具类](guide/vic-classes.md) — vicDate、vicText、vicList
> - [响应式编程](guide/reactive.md) — Observable、操作符、Subject
> - [编码加密与 Result](guide/extras.md) — encoding、crypto、Result

## 项目信息

- **当前版本**：v0.1.15
- **GitHub 仓库**：<https://github.com/vicTop-cw/vools>
- **联系邮箱**：<victortop921129@gmail.com>
- **PyPI 主页**：<https://pypi.org/project/vools/>

## 目录

- [安装](#安装)
- [快速开始](#快速开始)
- [占位符](#占位符)
- [重载装饰器](#重载装饰器)
- [stuff 函数](#stuff-函数)
- [persist 函数](#persist-函数)
- [box 装饰器](#box-装饰器)
- [Box 类](#box-类)
- [g 函数](#g-函数)
- [iif 函数](#iif-函数)
- [vicDate 工具类](#vicdate-工具类)
- [核心类](#核心类)
- [rself 装饰器](#rself-装饰器)
- [管道操作](#管道操作)
- [curry_decorator 装饰器](#curry_decorator-装饰器)
- [placeholder_impl 占位符实现](#placeholder_impl-占位符实现)
- [Seq 序列类](#seq-序列类)
- [curried 模块](#curried-模块)
- [reactive 模块](#reactive-模块)
- [响应式统计算子](#响应式统计算子)
- [响应式系统监控模块](#响应式系统监控模块)
- [编码模块](#编码模块)
- [加密模块](#加密模块)
- [Result 类型与 safe 装饰器](#result-类型与-safe-装饰器)
- [常见问题](#常见问题)

## 安装

### 环境要求

- Python 3.6+
- 核心依赖：`wrapt`, `attrs`（Python 3.6 使用 attrs 替代 dataclass）, `pandas`, `numpy`

### 安装方式

```bash
# 从 PyPI 安装
pip install vools==0.1.8

# 或从源码安装
git clone https://github.com/vicTop-cw/vools.git
cd vools
pip install -e .

# 安装开发依赖
pip install vools[dev]
```

## 快速开始

```python
from vools import _, _1, _2, overload, overcurry, stuff, persist, memoize

# 使用占位符
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

## vicDate 工具类

### 基本用法

`vicDate` 是一个日期处理工具类，提供日期格式化、计算和比较功能。

```python
from vools.datetime.utils import vicDate

# 使用默认日期（今天）
date = vicDate()
print(date.strftime('%Y-%m-%d'))  # 当前日期

# 使用字符串初始化
date = vicDate("2024-01-15")

# 使用 date 对象初始化
from datetime import date as dt_date
date = vicDate(dt_date(2024, 1, 15))
```

### 参数说明

| 参数 | 类型 | 说明 |
|------|------|------|
| `value` | Any | 日期值，可以是字符串、date 对象或 None |
| `fmt` | str | 输入日期格式，默认 `'%Y-%m-%d'` |

### 核心属性

| 属性 | 说明 |
|------|------|
| `year` | 年份 |
| `month` | 月份 |
| `day` | 日期 |
| `weekday` | 星期几（0-6） |
| `run_date` | 当前的 date 对象 |

### 核心方法

#### `strftime(fmt='%Y-%m-%d')`

格式化日期为字符串。

```python
date = vicDate("2024-01-15")
print(date.strftime("%Y/%m/%d"))  # "2024/01/15"
print(date.strftime("%d-%b-%Y"))  # "15-Jan-2024"
```

#### `add_days(n)`

添加天数。

```python
date = vicDate("2024-01-15")
new_date = date.add_days(5)
print(new_date.strftime('%Y%m%d'))  # "20240120"
```

#### `sub_days(n)`

减去天数。

```python
date = vicDate("2024-01-15")
new_date = date.sub_days(5)
print(new_date.strftime('%Y%m%d'))  # "20240110"
```

#### `add_months(n)`

添加月份。

```python
date = vicDate("2024-01-15")
new_date = date.add_months(1)
print(new_date.strftime('%Y%m%d'))  # "20240215"
```

#### `week_range()`

获取本周的起始和结束日期。

```python
date = vicDate("2024-01-15")
start, end = date._date_processor._get_week_range(date.date_obj.date())
print(start, end)  # 本周一和本周日
```

#### `month_range()`

获取本月的起始和结束日期。

```python
date = vicDate("2024-01-15")
start, end = date._date_processor._get_month_range(date.date_obj.date())
print(start, end)  # 本月1日和本月最后一天
```

### 日期比较

```python
date1 = vicDate("2024-01-15")
date2 = vicDate("2024-01-20")

print(date1.date_obj < date2.date_obj)   # True
print(date1.date_obj > date2.date_obj)   # False
print(date1.date_obj == date2.date_obj)  # False
```

### 边界情况处理

```python
# 闰年处理
date = vicDate("2024-02-29")
print(date.strftime('%Y%m%d'))  # "20240229"

# 月末处理
date = vicDate("2024-01-31")
new_date = date.add_days(1)
print(new_date.strftime('%Y%m%d'))  # "20240201"

# 年末处理
date = vicDate("2024-12-31")
new_date = date.add_days(1)
print(new_date.strftime('%Y%m%d'))  # "20250101"
```

### 示例代码

```python
from vools.datetime.utils import vicDate

# 创建日期对象
date = vicDate("2024-06-15")

# 获取属性
print(f"Year: {date.date_obj.year}")      # 2024
print(f"Month: {date.date_obj.month}")    # 6
print(f"Day: {date.date_obj.day}")        # 15
print(f"Weekday: {date.date_obj.weekday()}") # 5 (星期六)

# 日期计算
next_week = date.add_days(7)
last_month = date.add_months(-1)

# 格式化输出
print(date.strftime("%Y年%m月%d日"))  # "2024年06月15日"
```

## 核心类

vools 提供四个核心自定义数据类型：

### vicTools

```python
from vools import vicTools

# 日期处理
date_seq = vicTools.get_date_seq(nums=7, date_type='day', fmt='yyyyMMdd')

# 字符串处理
trimmed = vicTools.trim("  hello world  ")

# 正则表达式操作
matches = vicTools.regexp_findall(r'\d+', 'abc123def456')

# 生成随机字段名
field_name = vicTools.generate_random_field_name()
```

### vicText

```python
from vools import vicText

# 创建文本对象
txt = vicText("Hello, World!")

# 文本操作
upper_txt = txt.upper()

# 正则表达式操作
replaced = txt.regexp_replace(r'World', 'vools')

# 分割文本
parts = txt.splitEx(',')

# 写入文件
txt.write('output.txt')

# 从文件读取
read_txt = vicText.get_content_fromfile('output.txt')
```

### vicList

```python
from vools import vicList

# 创建列表对象
lst = vicList([1, 2, 3, 4, 5])

# 列表操作
slice_lst = lst.islice(1, 4)

# 集合操作
other_lst = vicList([3, 4, 5, 6, 7])
intersection = lst & other_lst  # 交集
union = lst | other_lst  # 并集

# 唯一元素
unique_lst = vicList(1, 2, 2, 3, 3, 3).unique

# 映射和过滤
result = lst.map(lambda x: x * 2).collect()
result = lst.filter(lambda x: x > 2).collect()
```

## curried 模块

vools.curried 提供了一组柯里化的函数式编程工具，与 toolz.curried API 兼容。

### 基本用法

```python
from vools.curried import map, filter, reduce, compose, pipe

# 基本柯里化调用
double = map(lambda x: x * 2)
result = double([1, 2, 3])  # [2, 4, 6]

# 管道操作
result = pipe(
    [1, 2, 3, 4, 5],
    filter(lambda x: x > 2),
    map(lambda x: x * 2),
    sum
)  # 24

# 函数组合
f = compose(lambda x: x + 1, lambda x: x * 2)
result = f(3)  # 7
```

### 惰性版本

curried 模块提供惰性版本的操作符，返回迭代器而非列表：

```python
from vools.curried import imap, ifilter, iunique

# 惰性 map - 返回 map 对象
result = imap(lambda x: x * 2, [1, 2, 3])
print(type(result))  # <class 'map'>
print(list(result))  # [2, 4, 6]

# 惰性 filter - 返回 filter 对象
result = ifilter(lambda x: x > 1, [1, 2, 3])
print(type(result))  # <class 'filter'>

# 惰性 unique - 返回 generator
result = iunique([1, 2, 2, 3])
print(type(result))  # <class 'generator'>
```

### 立即求值 vs 惰性求值

| 函数 | 立即求值 | 惰性求值 |
|------|---------|---------|
| map | 返回 list | 返回 map 对象 |
| filter | 返回 list | 返回 filter 对象 |
| unique | 返回 list | 返回 generator |

### 数学运算

```python
from vools.curried import add, mul, inc, dec

# 柯里化的数学函数
add5 = add(5)
result = add5(3)  # 8

# 增量/减量
result = inc(5)   # 6
result = dec(5)   # 4

# 乘法
double = mul(2)
result = double(5)  # 10
```

### 字符串操作

```python
from vools.curried import join, split, lower, upper

# 字符串连接
join_comma = join(',')
result = join_comma(['a', 'b', 'c'])  # "a,b,c"

# 字符串分割
split_comma = split(',')
result = split_comma("a,b,c")  # ['a', 'b', 'c']

# 大小写转换
result = lower("HELLO")  # "hello"
result = upper("hello")  # "HELLO"
```

### 谓词函数

```python
from vools.curried import is_eq, is_lt, is_in

# 相等判断
is_zero = is_eq(0)
result = is_zero(0)  # True
result = is_zero(1)  # False

# 小于判断
is_small = is_lt(10)
result = is_small(5)  # True

# 包含判断
in_list = is_in([1, 2, 3])
result = in_list(2)  # True
```

## reactive 模块

vools.reactive 是一个功能完整的响应式编程框架，实现了 Rx 4.0 规范的所有 98 个操作符。

### 基本用法

```python
from vools.reactive import Observable, ops

# 创建 Observable
obs = Observable.from_iterable([1, 2, 3])

# 订阅
obs.subscribe(
    on_next=lambda x: print(f"Next: {x}"),
    on_error=lambda e: print(f"Error: {e}"),
    on_completed=lambda: print("Completed")
)

# 使用管道操作
obs.pipe(
    ops.filter(lambda x: x > 1),
    ops.map(lambda x: x * 2)
).subscribe(on_next=print)  # 4, 6
```

### 创建操作符

```python
from vools.reactive import Observable

# 从可迭代对象创建
obs = Observable.from_iterable([1, 2, 3])

# 创建单个值
obs = Observable.just(42)
obs = Observable.of(1, 2, 3)

# 创建空序列
obs = Observable.empty()

# 创建无限序列
obs = Observable.interval(1.0)  # 每秒发射一个值
obs = Observable.timer(0.5, 1.0)  # 0.5秒后开始，每秒发射

# 延迟创建
obs = Observable.defer(lambda: Observable.just(42))
```

### 转换操作符

```python
from vools.reactive import Observable, ops

obs = Observable.from_iterable([1, 2, 3])

# map - 映射
obs.pipe(ops.map(lambda x: x * 2)).subscribe(print)  # 2, 4, 6

# flat_map - 扁平化映射
obs.pipe(
    ops.flat_map(lambda x: Observable.from_iterable([x, x*10]))
).subscribe(print)  # 1, 10, 2, 20, 3, 30

# scan - 累积扫描
obs.pipe(ops.scan(lambda acc, x: acc + x, 0)).subscribe(print)  # 1, 3, 6
```

### 过滤操作符

```python
from vools.reactive import Observable, ops

obs = Observable.from_iterable(range(10))

# filter - 过滤
obs.pipe(ops.filter(lambda x: x % 2 == 0)).subscribe(print)  # 0, 2, 4, 6, 8

# take - 取前N个
obs.pipe(ops.take(3)).subscribe(print)  # 0, 1, 2

# skip - 跳过前N个
obs.pipe(ops.skip(5)).subscribe(print)  # 5, 6, 7, 8, 9

# distinct - 去重
obs = Observable.from_iterable([1, 2, 2, 3, 3, 3])
obs.pipe(ops.distinct()).subscribe(print)  # 1, 2, 3
```

### 组合操作符

```python
from vools.reactive import Observable, ops

obs1 = Observable.from_iterable([1, 2, 3])
obs2 = Observable.from_iterable(['a', 'b', 'c'])

# zip - 拉链组合
Observable.zip(obs1, obs2).subscribe(print)  # (1, 'a'), (2, 'b'), (3, 'c')

# combine_latest - 组合最新值
obs1.pipe(ops.combine_latest(obs2)).subscribe(print)

# merge - 合并
Observable.merge(obs1, obs2).subscribe(print)  # 1, 'a', 2, 'b', 3, 'c'
```

### Subject

```python
from vools.reactive import Subject, BehaviorSubject, ReplaySubject

# Subject - 基础主题
subject = Subject()
subject.subscribe(on_next=print)
subject.on_next(1)  # 1
subject.on_next(2)  # 2

# BehaviorSubject - 保留最新值
subject = BehaviorSubject(0)  # 默认值
subject.subscribe(on_next=print)  # 立即收到 0
subject.on_next(1)  # 1

# ReplaySubject - 重放历史值
subject = ReplaySubject(2)  # 保留最近2个值
subject.on_next(1)
subject.on_next(2)
subject.on_next(3)
subject.subscribe(on_next=print)  # 2, 3
```

### 调度器

```python
from vools.reactive import Observable, schedulers, ops

# 使用调度器
obs = Observable.interval(0.1)

# 在不同线程执行
obs.pipe(
    ops.observe_on(schedulers.ThreadPoolScheduler())
).subscribe(on_next=print)

# 使用 asyncio 调度器
obs.pipe(
    ops.subscribe_on(schedulers.AsyncIOScheduler())
).subscribe(on_next=print)
```

### 错误处理

```python
from vools.reactive import Observable, ops

# catch - 捕获错误
Observable.throw(Exception("error")).pipe(
    ops.catch(lambda e: Observable.just("recovered"))
).subscribe(
    on_next=print,
    on_error=lambda e: print(f"Error: {e}")
)  # "recovered"

# retry - 重试
Observable.throw(Exception("error")).pipe(
    ops.retry(3)
).subscribe(
    on_next=print,
    on_error=lambda e: print(f"Failed after 3 retries")
)

# on_error_return - 错误时返回默认值
Observable.throw(Exception("error")).pipe(
    ops.on_error_return("default")
).subscribe(print)  # "default"
```

### 创新功能

vools.reactive 提供了一些独特的创新功能：

```python
from vools.reactive import Observable, ops

# placeholder 表达式支持
Observable.from_iterable([1, 2, 3]).pipe(
    ops.filter("_ > 1"),
    ops.map("x * 2")
).subscribe(print)  # 4, 6

# >> 管道操作符
result = Observable.from_iterable([1, 2, 3]) >> ops.filter(lambda x: x > 1) >> ops.map(lambda x: x * 2)

# p() 链式调用
Observable.from_iterable([1, 2, 3]).p() \
    .filter(lambda x: x > 1) \
    .map(lambda x: x * 2) \
    .subscribe(print)

# Subscription 上下文管理器
with Observable.from_iterable([1, 2, 3]).subscribe(on_next=print) as sub:
    # 自动清理
    pass

# retry_with_backoff - 带退避的重试
Observable.throw(Exception('err')).pipe(
    ops.retry_with_backoff(max_retries=5, initial_delay=1.0, multiplier=2.0)
).subscribe(on_error=lambda e: print(f'Failed: {e}'))

# circuit_breaker - 断路器模式
Observable.from_iterable(data).pipe(
    ops.circuit_breaker(threshold=5, reset_timeout=60.0)
).subscribe(on_next=process)
```

## 响应式统计算子

vools.reactive 提供了丰富的统计聚合扩展算子，支持数据分析场景。

### 统计聚合算子

```python
from vools.reactive import Observable

# 中位数
result = []
Observable.from_iterable([1, 2, 3, 4, 5]).p().median().subscribe(on_next=result.append)
# result: [3.0]

# 方差和标准差
result = []
Observable.from_iterable([1, 2, 3, 4, 5]).p().variance().subscribe(on_next=result.append)

# 分位数
result = []
Observable.from_iterable(range(1, 11)).p().quantile(0.5).subscribe(on_next=result.append)

# 最小/最大值索引
result = []
Observable.from_iterable([5, 3, 8, 1, 9]).p().arg_min().subscribe(on_next=result.append)  # [3]

# 唯一值计数
result = []
Observable.from_iterable([1, 2, 2, 3, 3, 3]).p().n_unique().subscribe(on_next=result.append)  # [3]
```

### 滚动窗口算子

```python
# 滚动求和（窗口大小为3）
result = []
Observable.from_iterable([1, 2, 3, 4, 5]).p().rolling_sum(3).subscribe(on_next=result.append)
# result: [1, 3, 6, 9, 12]

# 滚动最小/最大值
result = []
Observable.from_iterable([5, 3, 8, 1, 9]).p().rolling_min(3).subscribe(on_next=result.append)
# result: [5, 3, 3, 1, 1]

# 滚动均值
result = []
Observable.from_iterable([1, 2, 3, 4, 5]).p().rolling_mean(3).subscribe(on_next=result.append)
```

### 累积变换算子

```python
# 累积求和
result = []
Observable.from_iterable([1, 2, 3, 4]).p().cum_sum().subscribe(on_next=result.append)
# result: [1, 3, 6, 10]

# 累积最小/最大值
result = []
Observable.from_iterable([5, 3, 8, 1, 9]).p().cum_min().subscribe(on_next=result.append)
# result: [5, 3, 3, 1, 1]

# 累积均值
result = []
Observable.from_iterable([1, 2, 3, 4]).p().cum_mean().subscribe(on_next=result.append)
# result: [1.0, 1.5, 2.0, 2.5]

# 累积乘积
result = []
Observable.from_iterable([1, 2, 3, 4]).p().cum_prod().subscribe(on_next=result.append)
# result: [1, 2, 6, 24]
```

### 排序 Top-N 算子

```python
# 排序
result = []
Observable.from_iterable([3, 1, 4, 2]).p().sort().subscribe(on_next=result.append)
# result: [1, 2, 3, 4]

# 降序排序
result = []
Observable.from_iterable([3, 1, 4, 2]).p().sort(reverse=True).subscribe(on_next=result.append)

# Top-K
result = []
Observable.from_iterable([5, 3, 8, 1, 9, 2]).p().top_k(3).subscribe(on_next=result.append)
# result: [9, 8, 5]

# Bottom-K
result = []
Observable.from_iterable([5, 3, 8, 1, 9, 2]).p().bottom_k(3).subscribe(on_next=result.append)
# result: [1, 2, 3]
```

### None 值处理与数学工具

```python
# 过滤 None 值
result = []
Observable.from_iterable([1, None, 2, None, 3]).p().drop_none().subscribe(on_next=result.append)
# result: [1, 2, 3]

# 填充 None 值
result = []
Observable.from_iterable([1, None, 2, None, 3]).p().fill_none(0).subscribe(on_next=result.append)
# result: [1, 0, 2, 0, 3]

# 绝对值
result = []
Observable.from_iterable([-1, 2, -3, 4]).p().abs().subscribe(on_next=result.append)
# result: [1.0, 2.0, 3.0, 4.0]

# 值域限制
result = []
Observable.from_iterable([-1, 2, 5, 8]).p().clamp(0, 5).subscribe(on_next=result.append)
# result: [0.0, 2.0, 5.0, 5.0]
```

### 嵌套流展开算子

```python
# 展开嵌套列表
result = []
Observable.from_iterable([[1, 2], [3, 4], [5]]).p().explode().subscribe(on_next=result.append)
# result: [1, 2, 3, 4, 5]

# flatten 与 explode 同语义
result = []
Observable.from_iterable([[1, 2], [3, 4], [5]]).p().flatten().subscribe(on_next=result.append)
```

## 响应式系统监控模块

vools.reactive 提供了完整的系统监控能力，支持键盘、鼠标、剪贴板、文件和文件夹的实时监控。

### 1. 键鼠监控

```python
from vools.reactive import (
    KeyEventType, KeyData, KeyboardDispatcher, KeySubject, KeyObserver,
    MouseEventType, MouseData, MouseDispatcher, MouseSubject, MouseObserver,
    from_keyboard, from_mouse, write_to_keyboard, write_to_mouse,
    ops
)

# 键盘监控示例
with KeyboardDispatcher(backend="auto") as kd:
    kd.subject.pipe(
        ops.filter(lambda d: d.event_type == KeyEventType.KEY_DOWN),
        ops.map(lambda d: d.key_name)
    ).subscribe(on_next=lambda name: print(f"按下: {name}"))
    time.sleep(10)

# 键盘事件类型
# - KeyEventType.KEY_DOWN  - 按下
# - KeyEventType.KEY_UP    - 释放
# - KeyEventType.KEY_HOLD  - 保持

# 鼠标监控示例
with MouseDispatcher(backend="auto") as md:
    md.subject.pipe(
        ops.filter(lambda d: d.event_type == MouseEventType.MOVE)
    ).subscribe(on_next=lambda d: print(f"移动: ({d.x}, {d.y})"))
    time.sleep(10)

# 鼠标事件类型
# - MouseEventType.MOVE          - 移动
# - MouseEventType.LEFT_DOWN     - 左键按下
# - MouseEventType.LEFT_UP       - 左键释放
# - MouseEventType.RIGHT_DOWN    - 右键按下
# - MouseEventType.RIGHT_UP      - 右键释放
# - MouseEventType.MIDDLE_DOWN   - 中键按下
# - MouseEventType.MIDDLE_UP    - 中键释放
# - MouseEventType.SCROLL       - 滚轮滚动
# - MouseEventType.DRAG         - 拖拽

# 模拟键盘输入
write_to_keyboard("Hello, World!")

# 模拟鼠标移动和点击
write_to_mouse(move_to=(100, 200))
write_to_mouse(click="left")

# 使用观察者进行事件路由
def on_key_press(data):
    print(f"按键: {data.key_name}")

def on_key_release(data):
    print(f"释放: {data.key_name}")

observer = KeyObserver(
    on_key_down=on_key_press,
    on_key_up=on_key_release,
    on_any=lambda d: print(f"任意键事件: {d}")
)

with KeySubject(backend="auto") as ks:
    observer.attach(ks)
    time.sleep(10)
```

### 2. 剪贴板监控

```python
from vools.reactive import (
    ClipChangeType, ClipData, ClipboardDispatcher, ClipboardSubject, ClipboardObserver,
    from_clipboard, write_to_clipboard
)

# 基本用法
with ClipboardDispatcher(backend="auto") as cd:
    cd.subject.subscribe(on_next=lambda d: print(f"剪贴板变化: {d.change_type}"))
    time.sleep(10)

# 剪贴板内容类型
# - ClipChangeType.TEXT   - 纯文本
# - ClipChangeType.FILES - 文件列表
# - ClipChangeType.IMAGE  - 图片
# - ClipChangeType.HTML  - HTML片段
# - ClipChangeType.RTF   - 富文本
# - ClipChangeType.CLEAR - 清空
# - ClipChangeType.OTHER  - 其他

# 写入剪贴板
write_to_clipboard("Hello from vools!")

# 使用观察者
observer = ClipboardObserver(
    on_text=lambda d: print(f"文本: {d.content}"),
    on_files=lambda d: print(f"文件: {d.files}"),
    on_any=lambda d: print(f"任意变化")
)
```

### 3. 文件监控

```python
from vools.reactive import (
    FileClipChangeType, FileData, FileDispatcher, FileSubject, FileObserver,
    from_filesystem, write_to_filesystem
)

# 监控目录下的文件变更
with FileDispatcher(paths=["./watch_dir"], backend="auto") as fd:
    fd.subject.subscribe(on_next=lambda d: print(f"文件变化: {d.path} - {d.change_type}"))
    time.sleep(10)

# 文件变更类型
# - FileClipChangeType.CREATED  - 创建
# - FileClipChangeType.MODIFIED - 修改
# - FileClipChangeType.DELETED  - 删除
# - FileClipChangeType.RENAMED   - 重命名
# - FileClipChangeType.MOVED_IN  - 移入
# - FileClipChangeType.MOVED_OUT - 移出
# - FileClipChangeType.ACCESS    - 访问
# - FileClipChangeType.ATTRIB    - 属性变化

# 写入文件并触发事件
write_to_filesystem(fd, content="Hello, File!")

# 使用 Subject 和 Observer
with FileSubject(paths=["./watch_dir"], backend="auto") as fs:
    observer = FileObserver(
        on_created=lambda d: print(f"创建: {d.path}"),
        on_modified=lambda d: print(f"修改: {d.path}"),
        on_deleted=lambda d: print(f"删除: {d.path}")
    )
    observer.attach(fs)
    time.sleep(10)
```

### 4. 文件夹监控

```python
from vools.reactive import (
    FolderClipChangeType, FolderData, FolderDispatcher, FolderSubject, FolderObserver,
    from_foldersystem, write_to_foldersystem
)

# 监控目录下的子目录变更
with FolderDispatcher(paths=["./watch_dir"], backend="auto") as fd:
    fd.subject.subscribe(on_next=lambda d: print(f"目录变化: {d.path} - {d.change_type}"))
    time.sleep(10)

# 目录变更类型
# - FolderClipChangeType.FOLDER_CREATED  - 目录创建
# - FolderClipChangeType.FOLDER_DELETED  - 目录删除
# - FolderClipChangeType.FOLDER_RENAMED  - 目录重命名
# - FolderClipChangeType.FOLDER_MOVED_IN - 目录移入
# - FolderClipChangeType.FOLDER_MOVED_OUT - 目录移出
# - FolderClipChangeType.FOLDER_ATTRIB   - 目录属性变化
# - FolderClipChangeType.FOLDER_CONTENT  - 目录内容变化

# 创建目录并触发事件
write_to_foldersystem(fd, mode="create")
```

### 5. 后端选择

```python
# 可用的后端
# - "auto"   - 自动选择最佳后端（默认）
# - "win32"  - Windows API（Windows平台）
# - "polling" - 轮询模式（跨平台兼容）

# Windows 使用 win32 后端（事件驱动，低延迟）
kd = KeyboardDispatcher(backend="win32")

# Linux/macOS 使用 polling 后端
kd = KeyboardDispatcher(backend="polling")
```

### 6. 跨平台兼容性

所有监控模块都支持 Windows、macOS 和 Linux：

| 模块 | Windows | macOS | Linux |
|------|---------|-------|-------|
| 键盘监控 | 钩子 | 轮询 | 轮询 |
| 鼠标监控 | 钩子 | 轮询 | 轮询 |
| 剪贴板监控 | Hook | tkinter | tkinter |
| 文件监控 | ReadDirectoryChangesW | FSEvents | inotify |
| 文件夹监控 | ReadDirectoryChangesW | FSEvents | inotify |

## 函数签名缓存模块

vools.sig_cache 为大量使用 `inspect.signature()` 的场景提供高性能缓存。

### 基本用法

```python
from vools.sig_cache import get_signature, add_custom_sig, cached_getsignature

# 获取函数签名（带 LRU 缓存）
sig = get_signature(print)
print(list(sig.parameters.keys()))  # ['values', 'sep', 'end', 'file', 'flush']

# 重复调用走缓存，性能提升 100×~2000×
for _ in range(1000):
    sig = get_signature(print)  # O(1) dict 查表
```

### 手动注册自定义签名

```python
from inspect import Signature, Parameter

# 为 C 扩展函数注册签名
add_custom_sig(my_cfunc, Signature([
    Parameter('x', Parameter.POSITIONAL_OR_KEYWORD),
    Parameter('y', Parameter.KEYWORD_ONLY, default=0)
]))
```

### 装饰器用法

```python
from vools.sig_cache import cached_getsignature

@cached_getsignature
def add(a: int, b: int = 0) -> int:
    return a + b

# 签名在装饰时自动计算并缓存
print(add.__cached_sig__)  # <Signature (a: int, b: int = 0)>
```

### 缓存管理

```python
from vools.sig_cache import clear_cache, cache_info, remove_signature

# 查看缓存统计
info = cache_info()
print(f"缓存大小: {info['size']}")
print(f"命中率: {info['hit_ratio']:.2%}")

# 删除指定函数签名
remove_signature(print)

# 清空所有缓存
clear_cache()
```

## 编码模块

vools 提供统一的编码/解码接口，支持多种格式和自定义扩展。

### 基本用法

```python
from vools import (
    Encoder, Decoder, CodecRegistry,
    b64encode, b64decode,
    urlencode, urldecode,
    json_dumps, json_loads,
    gzip_compress, gzip_decompress,
    serialize, deserialize
)

# Base64 编码
encoded = b64encode('hello')
print(encoded)  # base64 编码结果
assert b64decode(encoded) == 'hello'

# URL 编码
encoded_url = urlencode('hello world')
assert urldecode(encoded_url) == 'hello world'

# JSON 序列化
data = {'key': 'value', 'number': 42}
json_str = json_dumps(data)
assert json_loads(json_str) == data

# 链式调用
result = Encoder('hello').base64().json().data
```

### 自定义编码器

```python
# 注册自定义编码器
from vools import encodable, decodable

@encodable('yaml')
def mock_yaml_encode(data):
    if isinstance(data, dict):
        return '\n'.join(f"{k}: {v}" for k, v in data.items())
    return str(data)

@decodable('yaml')  
def mock_yaml_decode(data):
    result = {}
    for line in data.strip().split('\n'):
        if ':' in line:
            key, value = line.split(':', 1)
            result[key.strip()] = value.strip()
    return result

# 使用自定义编码器
yaml_result = Encoder({'key': 'value'}).encode('yaml').data
print(yaml_result)  # 'key: value'

yaml_decoded = Decoder('key: value').decode('yaml').data
print(yaml_decoded)  # {'key': 'value'}

# 通用接口
serialized = serialize({'a': 1}, format='yaml')
deserialized = deserialize('a: 1', format='yaml')
```

### CodecRegistry 功能

```python
# 检查支持的格式
print(CodecRegistry.supported_formats())

# 格式检查
assert CodecRegistry.is_format_supported('json') == True
assert CodecRegistry.is_format_supported('yaml') == True
assert CodecRegistry.is_format_supported('unknown') == False

# 注销格式
CodecRegistry.unregister_format('yaml')
assert CodecRegistry.is_format_supported('yaml') == False

# 重新注册
CodecRegistry.register_codec('yaml', mock_yaml_encode, mock_yaml_decode)
```

## 加密模块

vools 提供统一的加密接口，支持多种哈希算法和自定义扩展。

### Hash 函数

```python
from vools import md5, sha1, sha256, sha512

test_data = 'hello world'

print(md5(test_data))    # 32 位十六进制
print(sha1(test_data))   # 40 位十六进制
print(sha256(test_data)) # 64 位十六进制
print(sha512(test_data)) # 128 位十六进制
```

### HMAC 函数

```python
from vools import hmac_md5, hmac_sha256

key = 'my_secret_key'

result = hmac_md5(test_data, key)
print(result)  # HMAC-MD5 结果

result = hmac_sha256(test_data, key)
print(result)  # HMAC-SHA256 结果
```

### Encryptor 类

```python
from vools import Encryptor

# 链式调用
result = Encryptor('hello').sha256().data
print(result)

# HMAC
result = Encryptor('data').hmac_sha256(key='secret').data
print(result)
```

### 密钥和令牌生成

```python
from vools import generate_key, generate_token

# 生成密钥
key_32 = generate_key(32)  # 32 字节 = 64 个十六进制字符
print(key_32)

key_16 = generate_key(16)  # 16 字节 = 32 个十六进制字符
print(key_16)

# 生成令牌（URL-safe base64）
token = generate_token(32)
print(token)  # 43 个字符
```

### 自定义加密器

```python
from vools import encryptable, decryptable, CryptoRegistry

@encryptable('custom_xor')
def xor_encrypt(data, key='secret'):
    if isinstance(data, str):
        data = data.encode('utf-8')
    if isinstance(key, str):
        key = key.encode('utf-8')
    result = bytearray()
    for i, byte in enumerate(data):
        result.append(byte ^ key[i % len(key)])
    return bytes(result).hex()

@decryptable('custom_xor')
def xor_decrypt(data, key='secret'):
    if isinstance(key, str):
        key = key.encode('utf-8')
    data_bytes = bytes.fromhex(data)
    result = bytearray()
    for i, byte in enumerate(data_bytes):
        result.append(byte ^ key[i % len(key)])
    return result.decode('utf-8')

# 使用自定义加密器
encrypted = xor_encrypt('hello world', key='key')
decrypted = xor_decrypt(encrypted, key='key')
assert decrypted == 'hello world'

# 使用 Encryptor 类
result = Encryptor('test').encrypt('custom_xor', key='key').data
print(result)
```

### CryptoRegistry 功能

```python
# 检查支持的算法
print(CryptoRegistry.supported_algorithms())

# 算法检查
assert CryptoRegistry.is_algorithm_supported('sha256') == True
assert CryptoRegistry.is_algorithm_supported('custom_xor') == True

# 注销算法
CryptoRegistry.unregister_algorithm('custom_xor')

# 重新注册
CryptoRegistry.register_crypto('custom_xor', xor_encrypt, xor_decrypt)
```

## Result 类型与 safe 装饰器

vools 提供函数式编程的错误处理支持。

### Result 类型

```python
from vools.functional import Result, Success, Failure, success, failure

# 创建 Result
r1 = Result.success(42)
r2 = Result.failure(ValueError('test error'))

# 检查状态
print(r1.is_success)  # True
print(r2.is_failure)  # True

# 映射操作
result = r1.map(lambda x: x * 2)
print(result)  # Success(84)

# 获取值
print(r1.unwrap())      # 42
print(r2.unwrap_or(0))  # 0
```

### safe 装饰器

```python
from vools.functional import safe

@safe
def divide(a, b):
    return a / b

# 成功情况
result = divide(10, 2)
print(result)  # Success(5.0)

# 失败情况
result = divide(10, 0)
print(result)  # Failure(ZeroDivisionError(...))
```

## 常见问题

### 1. 占位符表达式报错

**问题**：使用 `_` 占位符时出现语法错误

**解决方案**：确保使用正确的占位符语法：
- 单参数场景使用 `_`
- 多参数场景使用 `_1`, `_2`, `_3` 等
- 复杂表达式使用 `__expr__` 方法

### 2. 重载函数不匹配

**问题**：调用重载函数时没有匹配到正确的实现

**解决方案**：
- 检查参数数量是否匹配
- 在严格模式下检查参数类型是否正确
- 检查优先级设置是否正确

### 3. stuff 依赖注入失败

**问题**：参数没有被正确注入

**解决方案**：
- 确保注册函数名与参数名匹配
- 检查 `param_name` 参数是否正确设置
- 未注入的参数会保持为 `None`

### 4. persist 缓存不生效

**问题**：缓存文件没有被读取或写入

**解决方案**：
- 检查文件路径是否正确
- 确保有文件写入权限
- 检查缓存键生成函数是否正确

### 5. 管道操作报错

**问题**：使用管道操作时提示 `TypeError` 或 `NotImplemented`

**解决方案**：
- 确保右侧操作数是 `P` 实例：`lst | P(lambda x: x * 2)`
- 使用 `Ops` 工具类提供的方法：`lst | Ops.filter(lambda x: x > 0)`
- 字符串表达式需要通过 `g` 函数转换

### 6. rself 装饰器报错

**问题**：使用 `@rself` 装饰器时报错

**解决方案**：
- 确保类只继承一个基类或不继承
- 检查是否有重复的方法名
- 魔法方法不会被拦截，保持原有行为

### 7. 循环导入错误

**问题**：导入模块时出现 `ImportError: cannot import name`

**解决方案**：
- 这是已知问题，已通过延迟导入修复
- 确保使用最新版本的 vools
- 如果问题仍然存在，尝试重新安装

## 测试验证

所有功能均通过测试验证：

```python
# 运行测试
python -m pytest tests/ -v

# 测试文件列表
# - tests/test_placeholder.py        # 占位符测试
# - tests/test_stuff.py               # stuff 函数测试
# - tests/test_decorators.py          # 装饰器测试
# - tests/test_overcurry_vic.py       # overcurry 和 vic 类测试
# - tests/test_curry_overload.py      # curry 和 overload 测试
# - tests/test_box.py                 # box 装饰器和 Box 类测试
# - tests/test_g_function.py          # g 函数测试
# - tests/test_iif.py                 # iif 函数测试
# - tests/test_vicdate.py             # vicDate 工具类测试
# - tests/test_multiline.py           # 多行表达式测试
# - tests/test_rself.py               # rself 装饰器测试
# - tests/test_pipe_ops.py            # 管道操作测试
# - tests/test_viclist_pipe.py        # vicList 管道测试
# - tests/test_curry_decorator.py     # curry_decorator 测试
# - tests/test_placeholder_impl.py    # placeholder_impl 测试
# - tests/test_box_vic.py             # box 装饰器与 vic 类集成测试
```

## 性能优化建议

### Cython 加速

以下类和函数适合使用 Cython 进行性能优化：

| 模块 | 类/函数 | 优化理由 |
|------|---------|----------|
| `vools/data/seq.py` | `Seq` 类 | 序列操作是性能热点 |
| `vools/vic/viclist.py` | `vicList` 类 | 频繁的列表操作 |
| `vools/vic/victext.py` | `vicText` 类 | 字符串处理密集 |
| `vools/functional/arrow_func.py` | `g` 函数 | 表达式解析频繁调用 |
| `vools/functional/iif.py` | `iif` 函数 | 条件判断核心逻辑 |

### 使用建议

1. **避免过度使用装饰器**：装饰器会带来一定的性能开销
2. **批量操作优于逐个操作**：使用 `vicList` 的批量方法
3. **缓存计算结果**：使用 `@persist` 装饰器缓存耗时计算
4. **延迟执行**：`Seq` 的延迟执行特性可以优化性能

## 贡献指南

欢迎贡献代码！请遵循以下流程：

1. Fork 仓库
2. 创建特性分支：`git checkout -b feature/your-feature`
3. 编写代码和测试
4. 确保测试通过：`pytest tests/`
5. 提交 PR

### 代码规范

- 使用 Python 3.6+ 语法
- 遵循 PEP 8 规范
- 添加类型提示
- 编写单元测试
- 更新文档

## EnhancedDateFormatter 日期格式化器

`EnhancedDateFormatter` 是一个强大的日期格式化工具，支持动态变量更新、表达式计算和多行模板。

### 基本用法

```python
from vools.datetime import EnhancedDateFormatter

# 创建格式化器
formatter = EnhancedDateFormatter("今天是 {run_date_std}，本周开始于 {run_week_begin_std}")
result = formatter.format()
print(result)  # "今天是 2026-04-29，本周开始于 2026-04-27"
```

### 上下文变量动态更新

支持在占位符中动态更新变量：

```python
template = "{name <- \"张三\" ; age <- 30 ; city <- \"北京\" ; name + \"今年\" + str(age) + \"岁，来自\" + city}"
formatter = EnhancedDateFormatter(template)
result = formatter.format()
print(result)  # "张三今年30岁，来自北京"
```

**重要说明：模板中的变量赋值优先级高于 `set()` 方法设置的值，会覆盖通过 `formatter.set()` 设置的变量：

```python
template = "{days_ago <- 7 ; days_ago}"
formatter = EnhancedDateFormatter(template)
formatter.set(days_ago=31)  # 这个设置会被覆盖
result = formatter.format()
print(result)  # 输出 "7"，模板中的赋值优先级高
```

### 多行表达式支持

支持在花括号内书写多行表达式：

```python
template = """姓名：{name}
年龄：{age}
列表：{
    age <- 30
    ; ",".join([
        str(i)
        for i in range(age)
        if i % 5 == 0
    ])
}"""

formatter = EnhancedDateFormatter(template)
formatter.set(name="李四", age=25)
result = formatter.format()
```

### SQL 模板应用

这是一个完整的 SQL 模板应用示例：

```python
from vools.datetime import EnhancedDateFormatter

# 定义 SQL 模板
sql_template = """
SELECT 
    user_id,
    user_name,
    register_time,
    total_amount
FROM users
WHERE 
    register_time >= '{start_date}'
    AND register_time < '{end_date}'
    AND status = {status}
    AND age BETWEEN {min_age} AND {max_age}
ORDER BY register_time DESC
LIMIT {limit};
"""

# 创建格式化器
formatter = EnhancedDateFormatter(sql_template)

# 设置查询参数
formatter.set(
    start_date="2026-01-01",
    end_date="2026-05-01",
    status=1,
    min_age=18,
    max_age=60,
    limit=100
)

# 生成 SQL
sql = formatter.format()
print(sql)
```

### 高级 SQL 模板（带动态计算）

```python
from vools.datetime import EnhancedDateFormatter

# 复杂 SQL 模板
sql_template = """
-- 查询日期：{run_date_std}
-- 查询范围：{days_ago <- 7 ; days_ago} 天前至 {run_date_std}

SELECT 
    DATE_FORMAT(order_time, '%Y-%m-%d') AS date,
    COUNT(*) AS order_count,
    SUM(amount) AS total_amount,
    AVG(amount) AS avg_amount
FROM orders
WHERE 
    order_time >= DATE_SUB('{run_date_std}', INTERVAL {days_ago} DAY)
    AND order_time < '{run_date_std}'
    AND amount > {min_amount}
GROUP BY DATE_FORMAT(order_time, '%Y-%m-%d')
HAVING COUNT(*) >= {min_orders}
ORDER BY date DESC;
"""

# 创建格式化器
formatter = EnhancedDateFormatter(sql_template)

# 设置参数（部分参数动态计算）
formatter.set(
    days_ago=7,
    min_amount=100,
    min_orders=10
)

# 生成 SQL
sql = formatter.format()
print(sql)
```

### 日期变量参考

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `run_date` | 运行日期（YYYYMMDD） | 20260429 |
| `run_date_std` | 运行日期（YYYY-MM-DD） | 2026-04-29 |
| `run_week_begin` | 本周开始日期 | 20260427 |
| `run_week_end` | 本周结束日期 | 20260503 |
| `run_month_begin` | 本月开始日期 | 20260401 |
| `run_month_end` | 本月结束日期 | 20260430 |

## 许可证

vools 采用 Apache 2.0 许可证，详见 LICENSE 文件。