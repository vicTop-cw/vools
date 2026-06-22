# vools 函数式编程指南

`vools` 提供了丰富的函数式编程工具：柯里化函数、管道操作、占位符、序列抽象、Result 类型等。所有 API 均适用于 Python 3.9+，当前版本 vools 0.1.18。

---

## 1. 管道操作 (pipe / compose)

`pipe` 将多个函数按顺序串联：数据从左向右流过每个函数。`compose` 则是反向组合：右侧函数先执行，结果传给左侧。

### 导入

```python
from vools.curried import pipe, compose
```

### pipe — 管道（从左到右）

```python
from vools.curried import pipe, map, filter

result = pipe(
    range(10),
    filter(lambda x: x % 2 == 0),  # [0, 2, 4, 6, 8]
    map(lambda x: x * 2),          # [0, 4, 8, 12, 16]
    sum
)
print(result)  # 40
```

### compose — 函数组合（从右到左）

```python
from vools.curried import compose

# f(g(x))
f = compose(lambda x: x + 1, lambda x: x * 2)
print(f(3))  # 7  （先 *2，再 +1）

# 更具可读性的写法：
process = compose(
    sum,
    map(lambda x: x * 2),
    filter(lambda x: x % 2 == 0),
)
print(process(range(10)))  # 40
```

> 注意 `compose` 的执行顺序是"从右到左"，最右侧的函数最先接收输入；`pipe` 则相反，最左侧最先。

---

## 2. curried 函数工具

所有柯里化函数都可以部分应用，形成新的可复用函数。

### 导入

```python
from vools.curried import map, filter, reduce, imap, ifilter
```

### map — 映射（立即求值，返回 list）

```python
from vools.curried import map

double = map(lambda x: x * 2)
print(double([1, 2, 3]))  # [2, 4, 6]

print(map(str.upper, ["hello", "world"]))  # ['HELLO', 'WORLD']
```

### filter — 过滤（立即求值，返回 list）

```python
from vools.curried import filter

only_positive = filter(lambda x: x > 0)
print(only_positive([-1, 0, 1, 2, -3]))  # [1, 2]
```

### reduce — 归约（立即求值）

```python
from vools.curried import reduce
from operator import add

sum_all = reduce(add)
print(sum_all([1, 2, 3, 4, 5]))  # 15

# 带初始值
print(reduce(add, 10, [1, 2, 3]))  # 16
```

### imap / ifilter — 惰性版本（返回迭代器）

适合处理大规模或无限序列，避免一次性消耗内存。

```python
from vools.curried import imap, ifilter

it = imap(lambda x: x ** 2, range(1_000_000))
print(type(it))        # <class 'map'>
print(next(it))        # 0
print(next(it))        # 1

only_even = ifilter(lambda x: x % 2 == 0)
for n in only_even(range(10)):
    print(n)  # 0, 2, 4, 6, 8
```

| 函数 | 返回类型 | 适用场景 |
|------|---------|---------|
| `map` | `list` | 数据量小、需立即使用结果 |
| `filter` | `list` | 同上 |
| `reduce` | 标量 | 累积归约 |
| `imap` | `map` 迭代器 | 大数据 / 无限流 |
| `ifilter` | `filter` 迭代器 | 同上 |

---

## 3. 数学运算

### 导入

```python
from vools.curried import add, mul, inc, dec
```

```python
from vools.curried import add, mul, inc, dec

# add — 柯里化加法
add5 = add(5)
print(add5(3))   # 8
print(add(2, 3))  # 5

# mul — 柯里化乘法
double = mul(2)
print(double(7))  # 14

# inc — 自增
print(inc(10))    # 11

# dec — 自减
print(dec(10))    # 9
```

---

## 4. 字符串操作

### 导入

```python
from vools.curried import join, split, lower, upper
```

```python
from vools.curried import join, split, lower, upper

# join — 柯里化 join
with_comma = join(",")
print(with_comma(["a", "b", "c"]))  # "a,b,c"

# split — 柯里化 split
split_comma = split(",")
print(split_comma("a,b,c"))         # ['a', 'b', 'c']

# lower / upper — 大小写转换
print(lower("HELLO"))   # "hello"
print(upper("hello"))   # "HELLO"
```

---

## 5. 谓词函数

谓词函数是返回 `bool` 的柯里化函数，特别适合与 `map`/`filter` 组合。

### 导入

```python
from vools.curried import is_eq, is_lt, is_in
```

```python
from vools.curried import is_eq, is_lt, is_in, filter

# is_eq — 等于判断
is_zero = is_eq(0)
print(is_zero(0))   # True
print(is_zero(1))   # False

# is_lt — 小于判断
less_than_10 = is_lt(10)
print(less_than_10(5))   # True
print(less_than_10(10))  # False

# is_in — 包含判断
in_whitelist = is_in([1, 2, 3])
print(in_whitelist(2))   # True
print(in_whitelist(5))   # False

# 与 filter 组合
print(filter(is_eq(1), [0, 1, 2, 1, 3]))  # [1, 1]
```

---

## 6. Seq 序列

`Seq` 是一个支持链式调用的懒序列容器，提供 `map`/`filter`/`reduce`/`take`/`flatmap`/`group_by` 等方法。

### 导入

```python
from vools.data import Seq
```

### 基本用法

```python
from vools.data import Seq

result = (
    Seq(range(10))
    .map(lambda x: x * 2)
    .filter(lambda x: x > 5)
    .collect()
)
print(result)  # [6, 8, 10, 12, 14, 16, 18]
```

### 常见链式方法

| 方法 | 作用 |
|------|------|
| `.map(f)` | 映射每个元素 |
| `.filter(pred)` | 按谓词过滤 |
| `.reduce(f, init?)` | 归约为单个值 |
| `.collect()` / `.as_list()` | 立即求值为列表 |
| `.take(n)` | 取前 n 个元素（保持 Seq） |
| `.take(n, action=True)` | 取前 n 个元素（返回 list） |
| `.skip(n)` | 跳过前 n 个元素 |
| `.distinct()` | 去重 |
| `.flatten()` | 扁平化一层 |
| `.flatmap(f)` | map + flatten |
| `.group_by(key?)` | 按键分组 |
| `.sort_by(key?)` | 按 key 排序（返回 Seq） |
| `.find(pred)` | 找到第一个匹配元素或 NONE |
| `.any(pred?)` / `.all(pred?)` | 存在判断 |
| `.size` | 元素个数 |
| `.join(sep)` | 字符串连接 |

### 无限序列示例

```python
from itertools import count
from vools.data import Seq

squares = (
    Seq(count())
    .map(lambda x: x * x)
    .filter(lambda x: x % 2 == 0)
    .take(5, action=True)
)
print(squares)  # [0, 4, 16, 36, 64]
```

---

## 7. VList / VText

### VList — 链式列表

`VList` 继承自 `Seq`，在内部以 `list` 形式存储数据，支持 list 原生方法并保持链式风格。

```python
from vools.data import VList

vl = VList([3, 1, 4, 1, 5, 9])
print(vl.map(lambda x: x * 2))          # VList([6, 2, 8, 2, 10, 18])
print(vl.filter(lambda x: x > 2))        # VList([3, 4, 5, 9])
print(vl.unique)                         # VList([3, 1, 4, 5, 9])
print(vl[0], vl[-1])                     # 3 9
print(len(vl))                           # 6
```

### VText — 链式字符串

`VText` 继承自 `str`，拥有字符串的全部方法，配合 `vools` 其他工具可实现更流畅的文本处理。

```python
from vools.data import VText

vt = VText("Hello, World!")
print(vt.upper())          # "HELLO, WORLD!"
print(vt.split(","))       # ['Hello', ' World!']
print(isinstance(vt, str)) # True
```

---

## 8. Result 类型

`Result[T, E]` 是一个显式表达"成功或失败"的容器类型，用来替代 `try/except` 进行函数式错误处理。

### 导入

```python
from vools.functional import Result, Success, Failure
```

### 基本用法

```python
from vools.functional import Result, Success, Failure

def safe_div(a, b):
    if b == 0:
        return Failure(ValueError("division by zero"))
    return Success(a / b)

r = safe_div(10, 2)
print(r)                           # Success(5.0)
print(r.is_success, r.is_failure)  # True False

r2 = safe_div(10, 0)
print(r2)                          # Failure(ValueError('division by zero'))
```

### 链式调用（bind / map）

```python
# map — 仅在成功时应用函数
r = Success(5).map(lambda x: x * 2)
print(r)  # Success(10)

r = Failure(ValueError("bad")).map(lambda x: x * 2)
print(r)  # Failure(ValueError('bad'))

# bind — 串联可能失败的操作
r = (
    Success(100)
    .bind(lambda x: safe_div(x, 2))
    .bind(lambda x: safe_div(x, 0))   # 这里失败，后续直接穿透
    .map(lambda x: x + 1)
)
print(r)  # Failure(ValueError('division by zero'))
```

### 提取结果

```python
# unwrap — 成功返回值，失败抛出原始异常
print(Success(42).unwrap())          # 42
# Failure(ValueError("bad")).unwrap()  # 会抛出 ValueError

# unwrap_or — 失败时返回默认值
print(Failure(ValueError("bad")).unwrap_or(0))  # 0

# unwrap_or_else — 失败时由函数计算默认值
print(Failure(ValueError("bad")).unwrap_or_else(lambda e: str(e)))
# 'bad'
```

### from_unsafe — 从可能抛异常的代码构造

```python
from vools.functional import Result

r = Result.from_unsafe(lambda: int("42"))
print(r)  # Success(42)

r = Result.from_unsafe(lambda: int("not a number"))
print(r)  # Failure(ValueError(...))
```

---

## 9. safe 装饰器

`safe` 把任意可能抛出异常的函数包装成"返回 `Result`"的安全版本。

### 导入

```python
from vools.functional import safe
```

### 基本用法

```python
from vools.functional import safe

@safe
def parse_int(s):
    return int(s)

print(parse_int("42"))        # Success(42)
print(parse_int("oops"))      # Failure(ValueError(...))

# 结合管道式处理
result = (
    parse_int("123")
    .map(lambda x: x * 2)
    .unwrap_or(0)
)
print(result)  # 246
```

### 不使用装饰器

```python
from vools.functional import safe
import json

safe_loads = safe(json.loads)
r = safe_loads('{"a": 1}')
print(r.is_success, r.unwrap())  # True {'a': 1}

r = safe_loads('not json')
print(r.is_failure)               # True
```

---

## 10. 占位符 `_` / `_1` / `_2` 与 Box

`vools` 提供了简洁的占位符系统，可以像写表达式一样构造函数。

### 导入

```python
from vools.functional import _, _1, _2, Box, g, iif
```

### 占位符构造匿名函数

```python
from vools.functional import _, _1, _2

# _ 代表第一个参数
f = _ + 1
print(f(5))    # 6

# 比较表达式
is_positive = _ > 0
print(is_positive(-3))  # False

# _1 / _2 多参数占位符
add = _1 + _2
print(add(3, 4))        # 7

# 方法调用链式表达
get_name = _.upper().replace(" ", "_")
print(get_name("hello world"))  # "HELLO_WORLD"
```

### Box — 通用 AOP 包装器

`Box` 是一个代理（Proxy）对象，将任意 Python 对象包裹起来，使其方法返回值自动再被 `Box` 包裹，从而支持无限链式调用。

```python
from vools.functional import Box

b = Box([1, 2, 3, 4])
print(b.map(lambda x: x * 2))           # Box([2, 4, 6, 8])
print(b.filter(lambda x: x > 1))        # Box([2, 3, 4])
print(b.reduce(lambda a, b: a + b, 0))  # Box(10)

# 字典的数字索引
d = Box({"a": 1, "b": 2, "c": 3})
print(d._1)  # Box(1) — 第 1 个键对应的值
print(d._2)  # Box(2)

# run 执行副作用
Box([1, 2, 3]).run(print)  # 打印 [1, 2, 3]

# 字符串表达式（通过 g）
Box([1, 2, 3, 4]).run("lambda x: sum(x) * 2")  # Box(20)
```

### iif — 条件表达式工具

`iif` 提供声明式的条件分支构造。

```python
from vools.functional import iif

# 简单用法
classify = iif(_ < 0, lambda x: "negative",
          iif(_ == 0, lambda x: "zero",
                        lambda x: "positive"))

print(classify(-5))  # "negative"
print(classify(0))   # "zero"
print(classify(5))   # "positive"
```

### g — 字符串表达式

`g` 把字符串表达式编译成可调用函数，便于在配置中动态定义逻辑。

```python
from vools.functional import g

f = g("x * 2 + 1")
print(f(5))  # 11

f2 = g("a + b")
print(f2(3, 4))  # 7
```

---

## 11. 完整示例：组合使用

```python
from vools.curried import pipe, map, filter, is_in, split, join, lower
from vools.functional import safe, Result
from vools.data import Seq

# 1) 柯里化 & 管道
clean = pipe(
    split(","),
    map(lambda s: s.strip()),
    filter(is_in(["foo", "bar", "baz"])),
    map(lower),
    join(" | "),
)
print(clean(" FOO, xxx, Bar, baz "))  # "foo | bar | baz"

# 2) Seq 链式
top3 = (
    Seq(range(1, 11))
    .map(lambda x: x * x)
    .filter(_ % 2 == 0)        # 借助占位符
    .take(3, action=True)
)
print(top3)  # [4, 16, 36]

# 3) Result + safe
@safe
def read_number(path):
    with open(path) as f:
        return int(f.read().strip())

value = read_number("nonexistent.txt").unwrap_or(0)
print(value)  # 0
```

---

## API 速查表

| 分类 | 入口 | 说明 |
|------|------|------|
| 管道 & 组合 | `vools.curried.pipe`, `compose` | 左到右 / 右到左的函数串联 |
| 柯里化迭代 | `vools.curried.map`, `filter`, `reduce` | 立即求值，返回 `list`/标量 |
| 惰性迭代 | `vools.curried.imap`, `ifilter` | 返回迭代器，避免立即物化 |
| 数学 | `vools.curried.add`, `mul`, `inc`, `dec` | 基本柯里化运算 |
| 字符串 | `vools.curried.join`, `split`, `lower`, `upper` | 柯里化字符串操作 |
| 谓词 | `vools.curried.is_eq`, `is_lt`, `is_in` | 返回 `bool` 的柯里化比较 |
| 序列 | `vools.data.Seq`, `VList`, `VText` | 链式容器 |
| 错误处理 | `vools.functional.Result`, `Success`, `Failure`, `safe` | 函数式错误处理 |
| 占位符 & 代理 | `vools.functional._`, `_1`, `_2`, `Box`, `g`, `iif` | 表达式级匿名函数与 AOP 代理 |
