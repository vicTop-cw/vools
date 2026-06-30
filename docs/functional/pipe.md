# Pipe 管道操作

> **模块路径**：`vools.functional`
> **依赖版本**：Python 3.6+
> **平台支持**：Windows/macOS/Linux
> **测试状态**：✅ 已测试
> **编号**：#009
> **最后更新**：2026-06-30

## 概述

`vools.functional` 模块提供了函数式编程工具集，包含 Ops 操作符集合、管道操作符 `|`、`P()` 函数包装器等核心组件。

## Ops 工具类

`Ops` 类提供常用的函数式操作，支持管道操作符 `|` 连接。

### 基本操作

```python
from vools.functional import Ops

# 过滤偶数，乘以2，求和
result = range(10) | Ops.filter(lambda x: x % 2 == 0) | Ops.map(lambda x: x * 2) | Ops.sum()
print(result)  # 输出: 40
# 说明: range(10) = [0,1,2,3,4,5,6,7,8,9]
#       filter 偶数 = [0,2,4,6,8]
#       map 乘以2 = [0,4,8,12,16]
#       sum = 40
```

### 集合操作

```python
from vools.functional import Ops

# take: 取前n个元素
result = range(100) | Ops.take(5)
print(list(result))  # 输出: [0, 1, 2, 3, 4]

# drop: 丢弃前n个元素
result = range(10) | Ops.drop(3) | Ops.as_list()
print(result)  # 输出: [3, 4, 5, 6, 7, 8, 9]

# distinct: 去重
result = [1, 2, 2, 3, 1, 4] | Ops.distinct
print(result)  # 输出: [1, 2, 3, 4]
```

### 字符串操作

```python
from vools.functional import Ops

# 字符串方法链
result = "hello world" | Ops.upper | Ops.split()
print(result)  # 输出: ['HELLO', 'WORLD']

# replace: 替换
result = "hello world" | Ops.replace("world", "python")
print(result)  # 输出: hello python
```

### 数学运算

```python
from vools.functional import Ops

# min/max
result = [3, 1, 4, 1, 5, 9] | Ops.min()
print(result)  # 输出: 1

result = [3, 1, 4, 1, 5, 9] | Ops.max()
print(result)  # 输出: 9

# prod: 连乘
result = [1, 2, 3, 4] | Ops.prod()
print(result)  # 输出: 24
```

### 正则表达式操作

```python
from vools.functional import Ops

# regexp_replace: 正则替换
result = "hello123world456" | Ops.regexp_replace(r'\d+', 'NUM')
print(result)  # 输出: helloNUMworldNUM

# regexp_findall: 正则查找
result = "hello123world456" | Ops.regexp_findall(r'\d+')
print(result)  # 输出: ['123', '456']
```

## 管道操作符 `|`

管道操作符 `|` 将左侧值传递给右侧函数，实现数据流的链式处理。

### 基本用法

```python
# 使用 lambda
result = [1, 2, 3, 4, 5] | (lambda x: [i * 2 for i in x]) | sum
print(result)  # 输出: 30
# 说明: [1,2,3,4,5] -> [2,4,6,8,10] -> sum = 30
```

### 与 Ops 结合

```python
from vools.functional import Ops

# 复杂的数据处理管道
data = range(20)

result = (
    data
    | Ops.filter(lambda x: x % 3 == 0)  # 3的倍数
    | Ops.map(lambda x: x ** 2)          # 平方
    | Ops.take(5)                         # 取前5个
    | Ops.as_list()                      # 转为列表
)
print(result)  # 输出: [0, 9, 36, 81, 144]
```

### `>>` 批量操作

```python
from vools.functional import Ops

# >> 操作符对可迭代对象的每个元素执行管道操作
numbers = [1, 2, 3, 4, 5]
result = numbers >> Ops.map(lambda x: x * 2) >> Ops.filter(lambda x: x > 4)
print(list(result))  # 输出: [6, 8, 10]
```

## `P()` 函数包装器

`P()` 将普通函数包装为可管道化函数，支持指定参数位置。

### 参数位置说明

| ix 值 | 说明 |
|-------|------|
| 1 (默认) | 管道值作为第一个参数 |
| 2 | 管道值作为第二个参数 |
| 3 | 管道值作为第三个参数 |
| -1 | 管道值作为最后一个参数 |
| -2 | 管道值作为倒数第二个参数 |
| -3 | 管道值作为倒数第三个参数 |

### 基本示例

```python
from vools.functional import P

# ix=1: 管道值作为第一个参数 (默认)
result = [1, 2, 3, 4] | P(sum)
print(result)  # 输出: 10
# 说明: sum([1,2,3,4]) = 10

# ix=2: 管道值作为第二个参数
result = 5 | P(lambda a, b: a + b, 3, ix=2)
print(result)  # 输出: 8
# 说明: lambda a,b: a+b, 其中 a=3, b=5

# ix=-1: 管道值作为最后一个参数
result = "hello" | P(lambda *args: "-".join(args), "a", "b", ix=-1)
print(result)  # 输出: a-b-hello
```

### 与 Ops 组合

```python
from vools.functional import Ops, P

# 自定义函数通过 P() 参与管道
def add_suffix(s, suffix):
    return s + suffix

result = "hello" | P(add_suffix, " world", ix=1)
print(result)  # 输出: hello world

# 使用 P() 调用 Ops 方法
result = [1, 2, 3] | Ops.map(lambda x: x * 2) | Ops.filter(lambda x: x > 3) | Ops.as_list()
print(result)  # 输出: [4, 6]
```

### 字符串函数解析

```python
from vools.functional import P

# P() 支持字符串形式的函数表达式
result = [1, 2, 3, 4, 5] | P("sum()")
print(result)  # 输出: 15

result = "hello world" | P("upper()")
print(result)  # 输出: HELLO WORLD
```

## Pipe 类

`Pipe` 类支持链式调用和 `>>` 操作符。

### 基本用法

```python
from vools.functional import Pipe

# 创建管道
pipe = Pipe(lambda x: x * 2) | Pipe(lambda x: x + 1)
result = 5 | pipe
print(result)  # 输出: 11
# 说明: 5 * 2 + 1 = 11

# 使用 >> 批量操作
result = range(5) >> Pipe(lambda x: x * 2)
print(list(result))  # 输出: [0, 2, 4, 6, 8]
```

## do() 副作用方法

所有管道操作对象都支持 `do()` 方法用于执行副作用操作。

```python
from vools.functional import Ops

# 在管道中执行打印等副作用操作
result = (
    range(5)
    | Ops.map(lambda x: x * 2)
    | Ops.do(lambda x: print(f"DEBUG: {x}"))  # 打印但不中断管道
    | Ops.sum()
)
print(f"SUM: {result}")
# 输出:
# DEBUG: 0
# DEBUG: 2
# DEBUG: 4
# DEBUG: 6
# DEBUG: 8
# SUM: 20
```

## 完整示例

```python
from vools.functional import Ops, P

# 数据清洗完整流程
data = [
    {"name": "Alice", "age": 30, "score": 85},
    {"name": "Bob", "age": 25, "score": 92},
    {"name": "Charlie", "age": 35, "score": 78},
    {"name": "Diana", "age": 28, "score": 95},
]

# 过滤年龄大于25，分数大于80，按分数降序排序
result = (
    data
    | Ops.filter(lambda x: x["age"] > 25)           # 年龄 > 25
    | Ops.filter(lambda x: x["score"] > 80)          # 分数 > 80
    | Ops.sort_by(lambda x: x["score"], reverse=True)  # 按分数降序
    | Ops.as_list()                                  # 转为列表
)

for item in result:
    print(f"{item['name']}: age={item['age']}, score={item['score']}")
# 输出:
# Diana: age=28, score=95
# Alice: age=30, score=85
```
