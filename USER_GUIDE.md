# vools 用户指南

本指南基于实际测试用例和模块代码，详细展示 vools 库的核心功能和使用方法。

## 项目信息

- **当前版本**：v1.0.5
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
- [核心类](#核心类)
- [常见问题](#常见问题)

## 安装

```bash
# 从 PyPI 安装
pip install vools==1.0.5

# 或从源码安装
git clone https://github.com/vicTop-cw/vools.git
cd vools
pip install -e .
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

## persist 函数

persist 函数提供持久化缓存功能，将函数结果保存到文件中。

### 基本用法

```python
from vools import persist

@persist(filepath='data.pkl')
def expensive_computation(x):
    import time
    time.sleep(1)  # 模拟耗时计算
    return x ** 2

# 第一次执行，保存结果
result = expensive_computation(5)  # 耗时约 1 秒
assert result == 25

# 第二次执行，从文件读取（跳过计算）
result = expensive_computation(5)  # 几乎立即返回
assert result == 25
```

### 参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `filepath` | str | None | 持久化文件路径 |
| `key` | callable | None | 自定义缓存键生成函数 |
| `serialize` | callable | pickle.dump | 序列化函数 |
| `deserialize` | callable | pickle.load | 反序列化函数 |

### 高级用法

```python
# 自定义缓存键
@persist(filepath='data.pkl', key=lambda args, kwargs: args[0])
def process_user(user_id):
    return f"用户 {user_id} 的数据"

# 使用 JSON 序列化
import json

@persist(
    filepath='data.json',
    serialize=lambda obj, f: json.dump(obj, f, indent=2),
    deserialize=lambda f: json.load(f)
)
def get_config():
    return {"timeout": 30, "retries": 3}

# 手动清除缓存
@persist(filepath='cache.pkl')
def fetch_data(url):
    import requests
    return requests.get(url).json()

# 清除缓存
fetch_data.clear_cache()
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

### vicDate

```python
from vools import vicDate

# 创建日期对象
now = vicDate()

# 解析日期字符串
date = vicDate('20230101', fmt='yyyyMMdd')

# 获取指定周的日期
week_date = date.get_week(num=1, weekday=1)  # 上周周一

# 获取指定月的日期
month_date = date.get_month(num=1, last_day=True)  # 上月末

# 日期运算
tomorrow = now + 1
yesterday = now - 1
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
```

## 许可证

vools 采用 Apache 2.0 许可证，详见 LICENSE 文件。