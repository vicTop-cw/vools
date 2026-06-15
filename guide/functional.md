# vools 函数式编程

curried 模块提供柯里化函数、管道操作、函数组合等函数式编程工具。

---

## curried 模块

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

