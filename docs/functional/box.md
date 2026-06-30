# Box 包装器

> **模块路径**：`vools.functional`
> **依赖版本**：Python 3.6+
> **平台支持**：Windows/macOS/Linux
> **测试状态**：✅ 已测试
> **编号**：#011
> **最后更新**：2026-06-30

## 概述

`Box` 是一个对象包装器，提供链式属性访问、方法调用和数据操作。`box` 是装饰器/函数，用于将函数返回值自动包装为 `Box` 对象。

## Box 类

### 基本用法

```python
from vools.functional import Box

# 包装基本对象
b = Box(42)
print(b)        # 输出: 42
print(b + 10)   # 输出: 52

# 包装列表
b = Box([1, 2, 3, 4, 5])
print(b)        # 输出: [1, 2, 3, 4, 5]
print(b.map(lambda x: x * 2))  # 输出: [2, 4, 6, 8, 10]
```

### 数字索引访问

```python
from vools.functional import Box

# 列表索引访问
b = Box([10, 20, 30, 40, 50])

# 使用 _1, _2, ... 访问元素 (1-based)
print(b._1)  # 输出: 10
print(b._3)  # 输出: 30

# 使用负数索引
print(b._-1)  # 输出: 50 (最后一个)
print(b._-2)  # 输出: 40 (倒数第二个)

# 切片访问
print(b[1:3])  # 输出: Box([20, 30])
```

### 字典索引访问

```python
from vools.functional import Box

# 字典访问
b = Box({'name': 'Alice', 'age': 30, 'city': 'Beijing'})

# 访问值
print(b['name'])    # 输出: Alice
print(b['age'])     # 输出: 30

# 链式调用字典方法
b2 = b.copy()
print(b2)  # 输出: {'name': 'Alice', 'age': 30, 'city': 'Beijing'}

# 获取所有键
keys = b._get_keys()
print(keys)  # 输出: ['name', 'age', 'city']
```

## box 装饰器

### 基本用法

```python
from vools.functional import box

# 装饰器用法
@box
def get_user():
    return {'name': 'Bob', 'score': 85}

user = get_user()
print(user)           # 输出: Box({'name': 'Bob', 'score': 85})
print(user['name'])   # 输出: Bob
print(user['score'])  # 输出: 85
```

### 函数调用用法

```python
from vools.functional import box

# 函数调用用法
def create_user(name, age):
    return {'name': name, 'age': age}

user = box(create_user)('Charlie', 25)
print(user)           # 输出: Box({'name': 'Charlie', 'age': 25})
print(user['name'])   # 输出: Charlie
```

### 链式方法调用

```python
from vools.functional import box

@box
def get_data():
    return [1, 2, 3, 4, 5]

# 链式调用
result = (
    get_data()
    .map(lambda x: x * 2)      # [2, 4, 6, 8, 10]
    .filter(lambda x: x > 4)   # [6, 8, 10]
    .reduce(lambda x, y: x + y)  # 24
)
print(result)  # 输出: 24
```

## 属性链式访问

### 访问对象属性

```python
from vools.functional import Box

class User:
    def __init__(self, name, profile):
        self.name = name
        self.profile = profile

class Profile:
    def __init__(self, age, city):
        self.age = age
        self.city = city

user = User('Alice', Profile(30, 'Shanghai'))
b = Box(user)

# 链式访问嵌套属性
print(b.name)           # 输出: Alice
print(b.profile.age)    # 输出: 30
print(b.profile.city)   # 输出: Shanghai
```

### 字符串方法链

```python
from vools.functional import box

@box
def get_greeting():
    return "  hello world  "

# 链式字符串操作
result = (
    get_greeting()
    .strip()              # 去除首尾空格
    .upper()              # 转大写
    .replace('WORLD', 'PYTHON')  # 替换
)
print(result)  # 输出: HELLO PYTHON
```

### 列表方法链

```python
from vools.functional import box

@box
def get_numbers():
    return [3, 1, 4, 1, 5, 9, 2, 6]

# 链式列表操作
result = (
    get_numbers()
    .sort()               # 排序（就地修改）
)
print(result)  # 输出: [1, 1, 2, 3, 4, 5, 6, 9]
print(result._1)  # 输出: 1 (第一个元素)
```

## map / filter / reduce

### map 操作

```python
from vools.functional import Box

b = Box([1, 2, 3, 4, 5])

# map: 对每个元素应用函数
result = b.map(lambda x: x ** 2)
print(result)  # 输出: Box([1, 4, 9, 16, 25])
```

### filter 操作

```python
from vools.functional import Box

b = Box([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])

# filter: 保留满足条件的元素
result = b.filter(lambda x: x % 2 == 0)
print(result)  # 输出: Box([2, 4, 6, 8, 10])
```

### reduce 操作

```python
from vools.functional import Box

b = Box([1, 2, 3, 4, 5])

# reduce: 聚合操作
result = b.reduce(lambda x, y: x + y)
print(result)  # 输出: Box(15)

# 带初始值
result = b.reduce(lambda x, y: x + y, initial=10)
print(result)  # 输出: Box(25)
```

## run 方法

### 基本用法

```python
from vools.functional import Box

b = Box(42)

# run: 执行函数并返回结果
result = b.run(lambda x: x * 2)
print(result)  # 输出: Box(84)
```

### 字符串函数

```python
from vools.functional import Box

b = Box([1, 2, 3])

# 使用字符串指定函数
result = b.run("sum()")
print(result)  # 输出: Box(6)
```

### 解包模式

```python
from vools.functional import Box

# 解包列表
b = Box([1, 2, 3])
result = b.run(lambda *args: sum(args), unpack="*")
print(result)  # 输出: Box(6)

# 解包字典
b = Box({'a': 1, 'b': 2})
result = b.run(lambda **kwargs: sum(kwargs.values()), unpack="**")
print(result)  # 输出: Box(3)
```

### nobox 选项

```python
from vools.functional import Box

b = Box(42)

# nobox=True 返回原始值
result = b.run(lambda x: x * 2, nobox=True)
print(result)  # 输出: 84 (int, not Box)
print(type(result))  # 输出: <class 'int'>
```

## do 方法（副作用）

```python
from vools.functional import Box

# do: 执行副作用操作，返回 self 以支持链式调用
b = Box([1, 2, 3, 4, 5])

result = (
    b
    .do(lambda x: print(f"原始数据: {x}"))      # 打印原始数据
    .map(lambda x: x * 2)                        # 乘2
    .do(lambda x: print(f"乘2后: {x}"))          # 打印结果
    .filter(lambda x: x > 4)                    # 过滤
)
print(f"最终结果: {result}")
# 输出:
# 原始数据: [1, 2, 3, 4, 5]
# 乘2后: [2, 4, 6, 8, 10]
# 最终结果: [6, 8, 10]
```

## setattr_box 动态添加方法

```python
from vools.functional import Box, setattr_box

# 动态添加方法到 Box 类
def double_value(self):
    return self * 2

setattr_box(double_value, 'double')

b = Box(21)
print(b.double())  # 输出: Box(42)
```

## 与 Seq 结合使用

```python
from vools.functional import box
from vools.data import Seq

@box
def process_data():
    return [3, 1, 4, 1, 5, 9, 2, 6]

# Seq 和 Box 链式调用
result = (
    process_data()
    .filter(lambda x: x > 3)      # Box 版本
)
print(result)  # 输出: Box([4, 5, 9, 6])

# 转换为 Seq 继续处理
s = Seq(result.__wrapped__)
print(s.sort_by().as_list())  # 输出: [4, 5, 6, 9]
```

## 完整示例

```python
from vools.functional import box, Box

# 模拟电商订单处理
@box
def get_orders():
    return [
        {'id': 1, 'product': 'Book', 'price': 50, 'qty': 2},
        {'id': 2, 'product': 'Pen', 'price': 5, 'qty': 10},
        {'id': 3, 'product': 'Notebook', 'price': 30, 'qty': 3},
        {'id': 4, 'product': 'Book', 'price': 50, 'qty': 1},
        {'id': 5, 'product': 'Pen', 'price': 5, 'qty': 5},
    ]

# 计算总金额
total = (
    get_orders()
    .map(lambda o: {'id': o['id'], 'total': o['price'] * o['qty']})  # 计算单笔总额
    .filter(lambda o: o['total'] > 20)                                 # 过滤小额订单
    .reduce(lambda acc, x: acc + x['total'], initial=0)                # 求和
)
print(f"总金额: {total}")  # 输出: 总金额: 255
# 说明: (50*2) + (30*3) + (50*1) = 100 + 90 + 50 = 255
```
