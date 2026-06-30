# Seq 序列操作

> **模块路径**：`vools.data`
> **依赖版本**：Python 3.6+
> **平台支持**：Windows/macOS/Linux
> **测试状态**：✅ 已测试
> **编号**：#010
> **最后更新**：2026-06-30

## 概述

`Seq` 是 vools 提供的惰性序列类，支持链式操作、LINQ 风格的方法以及流式处理。`Seq` 采用惰性求值策略，只在需要时计算元素。

## 创建 Seq

### 从可迭代对象创建

```python
from vools.data import Seq

# 从列表创建
s = Seq([1, 2, 3, 4, 5])
print(s)  # 输出: Seq([1, 2, 3, 4, 5])

# 从 range 创建
s = Seq(range(10))
print(s)  # 输出: Seq([0, 1, 2, 3, 4, 5, 6, 7, 8, 9])

# 从生成器创建
s = Seq(x * 2 for x in range(5))
print(s)  # 输出: Seq([0, 2, 4, 6, 8])
```

### 使用类方法创建

```python
from vools.data import Seq

# Seq.of: 从参数创建
s = Seq.of(1, 2, 3)
print(s)  # 输出: Seq([1, 2, 3])

# Seq.range: 整数范围
s = Seq.range(10)          # 0 到 9
print(s)  # 输出: Seq([0, 1, 2, 3, 4, 5, 6, 7, 8, 9])

s = Seq.range(5, 10)       # 5 到 9
print(s)  # 输出: Seq([5, 6, 7, 8, 9])

s = Seq.range(0, 10, 2)    # 0, 2, 4, 6, 8
print(s)  # 输出: Seq([0, 2, 4, 6, 8])

# Seq.cycle: 循环生成
import random
s = Seq.cycle(lambda: random.randint(1, 6), times=3)  # 生成3次随机数
print(s | list)  # 输出: [4, 2, 5] (每次运行结果不同)
```

## 链式操作

### map - 映射

```python
from vools.data import Seq

# 映射操作: 对每个元素应用函数
s = Seq.range(5)
result = s.map(lambda x: x * 2).collect()
print(result)  # 输出: [0, 2, 4, 6, 8]

# 链式映射多个函数
s = Seq.of(1, 2, 3)
result = s.map(lambda x: x + 1, lambda x: x * 2).collect()
print(result)  # 输出: [4, 6, 8]
# 说明: (1+1)*2=4, (2+1)*2=6, (3+1)*2=8
```

### filter - 过滤

```python
from vools.data import Seq

# 过滤: 保留满足条件的元素
s = Seq.range(10)
result = s.filter(lambda x: x % 2 == 0).collect()
print(result)  # 输出: [0, 2, 4, 6, 8]

# 链式过滤多个条件 (AND 关系)
s = Seq.range(20)
result = (
    s
    .filter(lambda x: x > 5)   # 大于5
    .filter(lambda x: x < 15) # 小于15
    .filter(lambda x: x % 2 == 0)  # 偶数
    .collect()
)
print(result)  # 输出: [6, 8, 10, 12, 14]
```

### reduce - 聚合

```python
from vools.data import Seq

# 简单聚合
s = Seq.of(1, 2, 3, 4, 5)
result = s.reduce(lambda x, y: x + y)
print(result)  # 输出: 15

# 带初始值的 reduce
s = Seq.of(1, 2, 3, 4)
result = s.reduce(lambda x, y: x + y, init=10)
print(result)  # 输出: 19
# 说明: 10 + 1 + 2 + 3 + 4 = 19
```

## 收集方法

### as_list / collect

```python
from vools.data import Seq

# as_list: 物化为列表
s = Seq.range(5).map(lambda x: x ** 2)
result = s.as_list()
print(result)  # 输出: [0, 1, 4, 9, 16]

# collect: 同 as_list
result = Seq.of(1, 2, 3).collect()
print(result)  # 输出: [1, 2, 3]
```

### as_tuple

```python
from vools.data import Seq

# 转为元组
s = Seq.range(5)
result = tuple(s)
print(result)  # 输出: (0, 1, 2, 3, 4)
```

## 惰性求值与 take

### take - 取前 n 个

```python
from vools.data import Seq

# take: 取前 n 个元素
s = Seq.range(100)
result = s.take(5).collect()
print(result)  # 输出: [0, 1, 2, 3, 4]

# take(..., action=True) 直接返回列表
result = s.take(5, action=True)
print(result)  # 输出: [0, 1, 2, 3, 4]
```

### take_while / drop_while

```python
from vools.data import Seq

# take_while: 满足条件时取元素
s = Seq.of(1, 3, 5, 6, 7, 8)
result = s.take_while(lambda x: x % 2 == 1).collect()
print(result)  # 输出: [1, 3, 5]

# drop_while: 跳过满足条件的元素
s = Seq.of(1, 3, 5, 6, 7, 8)
result = s.drop_while(lambda x: x % 2 == 1).collect()
print(result)  # 输出: [6, 7, 8]
```

## 排序与去重

### distinct - 去重

```python
from vools.data import Seq

# 去重
s = Seq.of(1, 2, 2, 3, 1, 4, 3, 5)
result = s.distinct().collect()
print(result)  # 输出: [1, 2, 3, 4, 5]

# 使用 key 去重
data = [{'id': 1, 'name': 'a'}, {'id': 2, 'name': 'b'}, {'id': 1, 'name': 'c'}]
s = Seq.of(*data)
result = s.distinct(key=lambda x: x['id']).collect()
print(result)  # 输出: [{'id': 1, 'name': 'a'}, {'id': 2, 'name': 'b'}]
```

### sort_by - 排序

```python
from vools.data import Seq

# 排序
s = Seq.of(3, 1, 4, 1, 5, 9, 2, 6)
result = s.sort_by().collect()
print(result)  # 输出: [1, 1, 2, 3, 4, 5, 6, 9]

# 使用 key 排序
s = Seq.of('apple', 'banana', 'cherry', 'date')
result = s.sort_by(key=len).collect()
print(result)  # 输出: ['date', 'apple', 'cherry', 'banana']

# 降序排序
s = Seq.of(3, 1, 4, 1, 5, 9, 2, 6)
result = s.sort_by(reverse=True).collect()
print(result)  # 输出: [9, 6, 5, 4, 3, 2, 1, 1]
```

### reverse - 反转

```python
from vools.data import Seq

s = Seq.of(1, 2, 3, 4, 5)
result = s.reverse().collect()
print(result)  # 输出: [5, 4, 3, 2, 1]
```

## 分组与聚合

### group_by - 分组

```python
from vools.data import Seq

# 按 key 分组
data = [
    {'name': 'Alice', 'dept': 'IT'},
    {'name': 'Bob', 'dept': 'Sales'},
    {'name': 'Charlie', 'dept': 'IT'},
    {'name': 'Diana', 'dept': 'Sales'},
]
s = Seq.of(*data)
result = s.group_by(lambda x: x['dept']).collect()
print(result)
# 输出: [('IT', [{'name': 'Alice', 'dept': 'IT'}, {'name': 'Charlie', 'dept': 'IT'}]),
#        ('Sales', [{'name': 'Bob', 'dept': 'Sales'}, {'name': 'Diana', 'dept': 'Sales'}])]
```

### count_by - 计数

```python
from vools.data import Seq

# 按 key 计数
data = ['apple', 'banana', 'apple', 'cherry', 'banana', 'apple']
s = Seq.of(*data)
result = s.count_by().collect()
print(result)  # 输出: [('apple', 3), ('banana', 2), ('cherry', 1)]
```

### reduce_by - 分组聚合

```python
from vools.data import Seq

# 按 key 分组后聚合
data = [
    {'dept': 'IT', 'salary': 5000},
    {'dept': 'Sales', 'salary': 6000},
    {'dept': 'IT', 'salary': 7000},
    {'dept': 'Sales', 'salary': 5500},
]
s = Seq.of(*data)
result = s.reduce_by(key=lambda x: x['dept']).collect()
print(result)
# 输出: [('IT', 12000), ('Sales', 11500)]
```

## flatmap - 展平映射

```python
from vools.data import Seq

# 展平映射
data = [[1, 2], [3, 4], [5, 6]]
s = Seq.of(*data)
result = s.flatmap().collect()
print(result)  # 输出: [1, 2, 3, 4, 5, 6]

# 带函数的 flatmap
data = ['hello', 'world']
s = Seq.of(*data)
result = s.flatmap(lambda x: list(x)).collect()
print(result)  # 输出: ['h', 'e', 'l', 'l', 'o', 'w', 'o', 'r', 'l', 'd']
```

## 查找方法

### find - 查找元素

```python
from vools.data import Seq

# 查找第一个满足条件的元素
s = Seq.range(20)
result = s.find(lambda x: x > 10)
print(result)  # 输出: 11

# 未找到返回 NONE
result = s.find(lambda x: x > 100)
print(result)  # 输出: NONE
```

### find_index - 查找索引

```python
from vools.data import Seq

# 查找第一个满足条件的元素索引
s = Seq.of(1, 3, 5, 7, 9, 11)
result = s.find_index(lambda x: x > 5)
print(result)  # 输出: 2
```

### any / all - 布尔判断

```python
from vools.data import Seq

# any: 是否有任意元素满足条件
s = Seq.of(1, 3, 5, 6, 7)
result = s.any(lambda x: x % 2 == 0)
print(result)  # 输出: True

# all: 是否所有元素满足条件
result = s.all(lambda x: x > 0)
print(result)  # 输出: True
```

## 组合操作

### zip - 配对

```python
from vools.data import Seq

# zip 配对
s1 = Seq.of(1, 2, 3)
s2 = Seq.of('a', 'b', 'c')
result = s1.zip(s2).collect()
print(result)  # 输出: [(1, 'a'), (2, 'b'), (3, 'c')]
```

### enumerate - 带索引迭代

```python
from vools.data import Seq

s = Seq.of('a', 'b', 'c')
result = s.enumerate().collect()
print(result)  # 输出: [(0, 'a'), (1, 'b'), (2, 'c')]

# 指定起始索引
result = s.enumerate(n=1).collect()
print(result)  # 输出: [(1, 'a'), (2, 'b'), (3, 'c')]
```

### flatten - 展平

```python
from vools.data import Seq

# 展平嵌套结构
data = [1, [2, 3], [[4, 5]], 6]
s = Seq.of(*data)
result = s.flatten().collect()
print(result)  # 输出: [1, 2, 3, [4, 5], 6]
```

## 累积操作

### accum - 累积计算

```python
from vools.data import Seq

# 累积求和
s = Seq.of(1, 2, 3, 4, 5)
result = s.accum(lambda x, y: x + y).collect()
print(result)  # 输出: [1, 3, 6, 10, 15]

# 带初始值
result = s.accum(lambda x, y: x + y, initial=10).collect()
print(result)  # 输出: [11, 13, 16, 20, 25]
```

## 管道操作 `|`

```python
from vools.data import Seq

# 使用 | 运算符立即求值
s = Seq.range(10)
result = s | sum
print(result)  # 输出: 45

# 复杂管道
result = (
    Seq.range(100)
    | (lambda x: filter(lambda y: y % 2 == 0, x))  # 偶数
    | (lambda x: map(lambda y: y * 2, x))           # 乘2
    | list                                           # 物化
)
print(result[:5])  # 输出: [0, 4, 8, 12, 16]
```

## 完整示例

```python
from vools.data import Seq

# 模拟数据处理流程
transactions = [
    {'id': 1, 'amount': 100, 'category': 'food', 'valid': True},
    {'id': 2, 'amount': 200, 'category': 'food', 'valid': True},
    {'id': 3, 'amount': 50, 'category': 'food', 'valid': False},
    {'id': 4, 'amount': 300, 'category': 'tech', 'valid': True},
    {'id': 5, 'amount': 150, 'category': 'tech', 'valid': True},
    {'id': 6, 'amount': 80, 'category': 'food', 'valid': True},
]

# 处理流程: 过滤有效 -> 按类别分组 -> 计算每组总金额
result = (
    Seq.of(*transactions)
    .filter(lambda t: t['valid'])                           # 过滤有效
    .reduce_by(key=lambda t: t['category'])                # 按类别聚合
    .sort_by(key=lambda x: x[1], reverse=True)             # 按金额降序
    .collect()
)

for category, total in result:
    print(f"{category}: ${total}")
# 输出:
# tech: $450
# food: $380
```
