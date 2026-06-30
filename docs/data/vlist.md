# VList 文档

> **模块路径**：`vools.data`
> **依赖版本**：Python 3.6+
> **平台支持**：Windows/macOS/Linux
> **测试状态**：✅ 已测试
> **编号**：#017
> **最后更新**：2026-06-30

## 概述

VList 是 vools 提供的链式列表类，继承自 `Seq`，提供丰富的列表处理方法。支持集合运算、LINQ 风格的链式操作、管道操作等。

## 创建 VList

```python
from vools.data import VList

# 从可迭代对象创建
vl1 = VList([1, 2, 3, 4, 5])
print(vl1)  # 输出: VList([1, 2, 3, 4, 5])

# 从多个独立元素创建
vl2 = VList(1, 2, 3, 4, 5)
print(vl2)  # 输出: VList([1, 2, 3, 4, 5])

# 从字符串创建（字符串作为单个元素）
vl3 = VList("hello")
print(vl3)  # 输出: VList(['hello'])

# 从生成器创建
vl4 = VList(range(5))
print(vl4)  # 输出: VList([0, 1, 2, 3, 4])
```

## 基础属性

```python
from vools.data import VList

vl = VList([1, 2, 3, 4, 5])

# 长度
print(len(vl))  # 输出: 5

# 判空
print(vl.is_empty)  # 输出: False

# 获取长度（size 属性）
print(vl.size)  # 输出: 5

# unique 属性 - 去重
vl2 = VList([1, 2, 2, 3, 3, 3])
print(vl2.unique)  # 输出: VList([1, 2, 3])
```

## 链式操作方法

### filter / where - 过滤

```python
from vools.data import VList

vl = VList([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])

# 使用 lambda 过滤偶数
even = vl.filter(lambda x: x % 2 == 0)
print(even)  # 输出: VList([2, 4, 6, 8, 10])

# 使用表达式字符串过滤（安全）
odd = vl.filter('x % 2 == 1')
print(odd)  # 输出: VList([1, 3, 5, 7, 9])

# where 是 filter 的别名
result = vl.where(lambda x: x > 5)
print(result)  # 输出: VList([6, 7, 8, 9, 10])
```

### map / select - 映射

```python
from vools.data import VList

vl = VList([1, 2, 3, 4, 5])

# 使用 lambda 映射
doubled = vl.map(lambda x: x * 2)
print(doubled)  # 输出: VList([2, 4, 6, 8, 10])

# 使用表达式字符串映射
squared = vl.map('x ** 2')
print(squared)  # 输出: VList([1, 4, 9, 16, 25])

# select 是 map 的别名
result = vl.select(lambda x: x + 1)
print(result)  # 输出: VList([2, 3, 4, 5, 6])
```

### flat_map / flatmap - 扁平化映射

```python
from vools.data import VList

vl = VList([1, 2, 3])

# 每个元素映射为一个列表，然后合并
result = vl.flat_map(lambda x: [x, x * 10])
print(result)  # 输出: VList([1, 10, 2, 20, 3, 30])

# 使用表达式字符串
result2 = vl.flat_map('str(x) * 2')
print(result2)  # 输出: VList(['11', '22', '33'])
```

### filterfalse - 反向过滤

```python
from vools.data import VList

vl = VList([1, 2, 3, 4, 5])

# 返回不满足条件的元素
result = vl.filterfalse(lambda x: x % 2 == 0)
print(result)  # 输出: VList([1, 3, 5])
```

### wherenot - 反向过滤

```python
from vools.data import VList

vl = VList([1, 2, 3, 4, 5])

# wherenot 是 filterfalse 的别名
result = vl.wherenot(lambda x: x > 3)
print(result)  # 输出: VList([1, 2, 3])
```

### sort_by / sorted - 排序

```python
from vools.data import VList

vl = VList([3, 1, 4, 1, 5, 9, 2, 6])

# 默认升序排序
sorted_vl = vl.sort_by()
print(sorted_vl)  # 输出: VList([1, 1, 2, 3, 4, 5, 6, 9])

# 降序排序
sorted_desc = vl.sort_by(reverse=True)
print(sorted_desc)  # 输出: VList([9, 6, 5, 4, 3, 2, 1, 1])

# 使用键函数排序
vl2 = VList(['apple', 'banana', 'cherry', 'date'])
sorted_len = vl2.sort_by(key_func=lambda x: len(x))
print(sorted_len)  # 输出: VList(['date', 'apple', 'cherry', 'banana'])

# sorted 是 sort_by 的别名
result = vl.sorted(reverse=True)
print(result)  # 输出: VList([9, 6, 5, 4, 3, 2, 1, 1])
```

### reverse - 反转

```python
from vools.data import VList

vl = VList([1, 2, 3, 4, 5])

# 就地反转，返回自身
vl.reverse()
print(vl)  # 输出: VList([5, 4, 3, 2, 1])
```

### take - 获取前 n 个元素

```python
from vools.data import VList

vl = VList([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])

# 获取前 5 个元素
result = vl.take(5)
print(result)  # 输出: VList([1, 2, 3, 4, 5])

# 获取前 3 个元素，返回普通列表
result_list = vl.take(3, action=True)
print(result_list)  # 输出: [1, 2, 3]
```

### tail - 获取后 n 个元素

```python
from vools.data import VList

vl = VList([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])

# 获取后 3 个元素
result = vl.tail(3)
print(result)  # 输出: VList([8, 9, 10])
```

### prepend - 在开头插入元素

```python
from vools.data import VList

vl = VList([1, 2, 3, 4, 5])

# 在开头插入 0
result = vl.prepend(0)
print(result)  # 输出: VList([0, 1, 2, 3, 4, 5])
```

### islice - 切片操作

```python
from vools.data import VList

vl = VList([0, 1, 2, 3, 4, 5, 6, 7, 8, 9])

# 切片：start=1, stop=6, step=2
result = vl.islice(1, 6, 2)
print(result)  # 输出: VList([1, 3, 5])

# 省略 stop：start=2, step=1
result2 = vl.islice(2)
print(result2)  # 输出: VList([2, 3, 4, 5, 6, 7, 8, 9])
```

### enumerate - 带索引枚举

```python
from vools.data import VList

vl = VList(['a', 'b', 'c'])

# 起始索引为 0
result = vl.enumerate()
print(result)  # 输出: VList([(0, 'a'), (1, 'b'), (2, 'c')])

# 起始索引为 1
result2 = vl.enumerate(1)
print(result2)  # 输出: VList([(1, 'a'), (2, 'b'), (3, 'c')])
```

### group_by - 分组

```python
from vools.data import VList

data = VList([
    {'name': 'Alice', 'age': 25},
    {'name': 'Bob', 'age': 25},
    {'name': 'Charlie', 'age': 30},
    {'name': 'Diana', 'age': 30},
    {'name': 'Eve', 'age': 35}
])

# 按 age 分组
result = data.group_by(lambda x: x['age'])
print(result)  # 输出: {25: VList([{...}, {...}]), 30: VList([{...}, {...}]), 35: VList([{...}])}

# 使用表达式字符串
result2 = data.group_by("x['age']")
print(list(result2.keys()))  # 输出: [25, 30, 35]
```

### count_by - 分组计数

```python
from vools.data import VList

data = VList(['apple', 'banana', 'apple', 'cherry', 'banana', 'apple'])

# 计数每个元素出现的次数
result = data.count_by(lambda x: x)
print(result)  # 输出: {'apple': 3, 'banana': 2, 'cherry': 1}
```

### reduce_by - 分组聚合

```python
from vools.data import VList

data = VList([1, 2, 3, 4, 5, 6])

# 按奇偶分组，计算每组总和
result = data.reduce_by(lambda x: 'even' if x % 2 == 0 else 'odd', lambda a, b: a + b)
print(result)  # 输出: {'odd': 9, 'even': 12}
```

## 集合操作

### 交集（&）

```python
from vools.data import VList

vl1 = VList([1, 2, 3, 4, 5])
vl2 = VList([4, 5, 6, 7, 8])

# 交集
result = vl1 & vl2
print(result)  # 输出: VList([4, 5])
```

### 并集（|）

```python
from vools.data import VList

vl1 = VList([1, 2, 3, 4, 5])
vl2 = VList([4, 5, 6, 7, 8])

# 并集
result = vl1 | vl2
print(result)  # 输出: VList([1, 2, 3, 4, 5, 6, 7, 8])
```

### 差集（-）

```python
from vools.data import VList

vl1 = VList([1, 2, 3, 4, 5])
vl2 = VList([4, 5, 6, 7, 8])

# 差集：vl1 - vl2
result = vl1 - vl2
print(result)  # 输出: VList([1, 2, 3])
```

### 对称差集（^）

```python
from vools.data import VList

vl1 = VList([1, 2, 3, 4, 5])
vl2 = VList([4, 5, 6, 7, 8])

# 对称差集
result = vl1 ^ vl2
print(result)  # 输出: VList([1, 2, 3, 6, 7, 8])
```

## 添加和删除元素

### add / push - 添加元素

```python
from vools.data import VList

vl = VList([1, 2, 3])

# 添加单个元素到末尾
vl.add(4)
print(vl)  # 输出: VList([1, 2, 3, 4])

# push 是 add 的别名
vl.push(5)
print(vl)  # 输出: VList([1, 2, 3, 4, 5])
```

### pop - 弹出末尾元素

```python
from vools.data import VList

vl = VList([1, 2, 3, 4, 5])

# 弹出并返回末尾元素
popped = vl.pop()
print(popped)  # 输出: 5
print(vl)  # 输出: VList([1, 2, 3, 4])
```

### shift - 弹出第一个元素

```python
from vools.data import VList

vl = VList([1, 2, 3, 4, 5])

# 弹出并返回第一个元素
shifted = vl.shift()
print(shifted)  # 输出: 1
print(vl)  # 输出: VList([2, 3, 4, 5])
```

### unshift - 在开头插入元素

```python
from vools.data import VList

vl = VList([1, 2, 3, 4, 5])

# 在开头插入元素
vl.unshift(0)
print(vl)  # 输出: VList([0, 1, 2, 3, 4, 5])
```

## 链式调用示例

```python
from vools.data import VList

# 完整链式操作示例
result = (
    VList(range(1, 21))                        # [1, 2, 3, ..., 20]
    .filter(lambda x: x % 2 == 0)               # [2, 4, 6, ..., 20]
    .map(lambda x: x ** 2)                     # [4, 16, 36, ..., 400]
    .filter(lambda x: x > 100)                 # [144, 196, 256, 324, 400]
    .sort_by(reverse=True)                     # [400, 324, 256, 196, 144]
    .take(3)                                   # [400, 324, 256]
)

print(result)  # 输出: VList([400, 324, 256])

# 计算链式结果的总和
total = result.map(lambda x: x).run(sum)
print(total)  # 输出: 980
```

## 特殊方法

### distinct - 去重

```python
from vools.data import VList

vl = VList([1, 2, 2, 3, 3, 3, 4, 4, 4, 4])

# 去重（保持顺序）
result = vl.distinct()
print(result)  # 输出: VList([1, 2, 3, 4])
```

### any_equal / all_equal - 条件判断

```python
from vools.data import VList

vl = VList([2, 4, 6, 8, 10])

# 检查是否存在偶数（默认 bool）
print(vl.any_equal())  # 输出: True

# 使用自定义条件
print(vl.any_equal(lambda x: x > 10))  # 输出: False

# 检查是否所有元素都大于 0
print(vl.all_equal(lambda x: x > 0))  # 输出: True

# 检查是否所有元素都是偶数
print(vl.all_equal(lambda x: x % 2 == 0))  # 输出: True
```

### quantify - 统计满足条件的数量

```python
from vools.data import VList

vl = VList([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])

# 统计偶数数量
count = vl.quantify(lambda x: x % 2 == 0)
print(count)  # 输出: 5

# 统计大于 5 的数量
count2 = vl.quantify(lambda x: x > 5)
print(count2)  # 输出: 5
```

### sizeEx - 条件计数

```python
from vools.data import VList

vl = VList([1, 2, 3, 4, 5])

# 无条件：返回列表长度
print(vl.sizeEx())  # 输出: 5

# 有条件：返回满足条件的元素数量
print(vl.sizeEx(lambda x: x > 3))  # 输出: 2
```

### collect - 物化为普通列表

```python
from vools.data import VList

vl = VList([1, 2, 3, 4, 5])

# 转换为普通列表
result = vl.collect()
print(result)  # 输出: [1, 2, 3, 4, 5]
print(type(result))  # 输出: <class 'list'>
```

### run - 对整个列表执行函数

```python
from vools.data import VList

vl = VList([1, 2, 3, 4, 5])

# 对整个列表执行函数
result = vl.run(sum)
print(result)  # 输出: 15

# 使用表达式字符串
result2 = vl.run('sum(x)')
print(result2)  # 输出: 15
```

### show - 打印列表

```python
from vools.data import VList

vl = VList([1, 2, 3, 4, 5])

# 打印列表
vl.show()  # 输出: VList([1, 2, 3, 4, 5])

# 自定义打印函数
vl.show(lambda x: print(f"列表长度: {len(x)}"))  # 输出: 列表长度: 5
```

## 索引访问

```python
from vools.data import VList

vl = VList([1, 2, 3, 4, 5])

# 整数索引
print(vl[0])  # 输出: 1
print(vl[-1])  # 输出: 5

# 切片访问（返回 VList）
print(vl[1:4])  # 输出: VList([2, 3, 4])
```

## 与普通列表的兼容性

```python
from vools.data import VList

# VList 可以直接用于普通列表操作
vl = VList([1, 2, 3, 4, 5])

# 转换为列表
plain_list = list(vl)
print(plain_list)  # 输出: [1, 2, 3, 4, 5]

# isinstance 检查
print(isinstance(vl, list))  # 输出: True
print(isinstance([1, 2, 3], VList))  # 输出: True
```

## 管道操作

```python
from vools.data import VList
from vools.functional.pipe_ops import P, Ops

vl = VList([1, 2, 3, 4, 5])

# 使用 | 管道操作
result = vl | P.filter(lambda x: x % 2 == 0) | P.map(lambda x: x * 10)
print(result)  # 输出: [20, 40]

# 使用 Ops 类
result2 = vl | Ops.filter(lambda x: x > 2) | Ops.map(lambda x: x ** 2)
print(result2)  # 输出: [9, 16, 25]
```
