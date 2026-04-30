# vools 用户指南

本指南基于实际测试用例和模块代码，详细展示 vools 库的核心功能和使用方法。

## 项目信息

- **当前版本**：v0.1.7
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
- [常见问题](#常见问题)

## 安装

### 环境要求

- Python 3.6+
- 核心依赖：`wrapt`, `attrs`（Python 3.6 使用 attrs 替代 dataclass）, `pandas`, `numpy`

### 安装方式

```bash
# 从 PyPI 安装
pip install vools==0.1.7

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

### 5. 测试运行失败

**问题**：运行测试时提示导入错误或测试失败

**解决方案**：
- 确保在项目目录中运行测试：`cd vools && python -m pytest tests/`
- 检查是否安装了 site-packages 中的旧版本 vools，如果有，先卸载：`pip uninstall vools -y`

## 测试验证

所有功能均通过测试验证：

```python
# 运行测试
python -m pytest tests/ -v

# 测试文件列表
# - tests/test_placeholder.py    # 占位符测试
# - tests/test_stuff.py           # stuff 函数测试
# - tests/test_decorators.py      # 装饰器测试
# - tests/test_overcurry_vic.py   # overcurry 和 vic 类测试
# - tests/test_curry_overload.py  # curry 和 overload 测试
# - tests/test_box.py             # box 装饰器和 Box 类测试
# - tests/test_g_function.py      # g 函数测试
# - tests/test_iif.py             # iif 函数测试
# - tests/test_vicdate.py         # vicDate 工具类测试
# - tests/test_multiline.py        # 多行表达式测试
```

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