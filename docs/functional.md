# 函数式工具模块

vools 提供了丰富的函数式编程工具，支持管道操作、占位符表达式、箭头函数等。

## 目录

- [Pipe 管道操作](#pipe-管道操作)
- [P 可管道化函数](#p-可管道化函数)
- [Ops 操作符集合](#ops-操作符集合)
- [占位符](#占位符)
- [箭头函数 g](#箭头函数-g)
- [iif 条件表达式](#iif-条件表达式)
- [Box 类型](#box-类型)
- [Result 类型](#result-类型)
- [其他工具函数](#其他工具函数)

---

## Pipe 管道操作

`Pipe` 类支持链式管道操作，使用 `|` 操作符连接函数。

**示例：**

```python
from vools.functional import Pipe

# 基本用法
result = range(10) | Pipe(lambda x: [i * 2 for i in x])
print(result)  # [0, 2, 4, 6, 8, 10, 12, 14, 16, 18]

# 链式调用
result = range(10) | Pipe(lambda x: filter(lambda i: i % 2 == 0, x)) | Pipe(list)
print(result)  # [0, 2, 4, 6, 8]

# compose 组合函数
composed = Pipe.compose(
    lambda x: x * 2,
    lambda x: x + 1,
    lambda x: str(x)
)
composed(5)  # "11"
```

---

## P 可管道化函数

`P` 类包装函数使其可管道化，支持指定参数位置。

**参数：**
- `func`: 要包装的函数
- `args`: 预置参数
- `kwargs`: 预置关键字参数
- `ix`: 管道参数位置（1, 2, 3 或 -1, -2, -3）

**示例：**

```python
from vools.functional import P

# 基本用法 - 管道值作为第一个参数
result = [1, 2, 3] | P(sum)
print(result)  # 6

# 管道值作为第二个参数
result = [1, 2, 3] | P(lambda x, y: x + y, ix=2)
print(result)  # 需要额外参数

# 管道值作为最后一个参数
result = "hello" | P(lambda prefix, suffix: prefix + suffix, ix=-1)
print(result)  # 需要额外参数

# 预置参数
add_five = P(lambda x, y: x + y, 5)
result = 10 | add_five
print(result)  # 15
```

---

## Ops 操作符集合

`Ops` 类提供常用的函数式操作符。

**示例：**

```python
from vools.functional import Ops

# 链式操作
result = range(10) | Ops.filter(lambda x: x % 2 == 0) | Ops.map(lambda x: x * 2) | Ops.sum()
print(result)  # 40

# 常用操作符
result = range(10) | Ops.take(5) | Ops.as_list()
print(result)  # [0, 1, 2, 3, 4]

result = [1, 2, 2, 3, 3, 3] | Ops.distinct() | Ops.as_list()
print(result)  # [1, 2, 3]

# 副作用操作
result = range(5) | Ops.do(lambda x: print(f"处理: {x}")) | Ops.as_list()
# 输出: 处理: 0, 处理: 1, ...

# 数学操作
result = [1, 2, 3, 4, 5] | Ops.min()
print(result)  # 1

result = [1, 2, 3, 4, 5] | Ops.max()
print(result)  # 5
```

**可用操作符：**

| 操作符 | 说明 |
|--------|------|
| `filter(pred)` | 过滤元素 |
| `map(func)` | 映射元素 |
| `sum()` | 求和 |
| `all()` | 全部为真 |
| `any()` | 任一为真 |
| `min()` | 最小值 |
| `max()` | 最大值 |
| `take(n)` | 取前 n 个 |
| `drop(n)` | 丢弃前 n 个 |
| `distinct()` | 去重 |
| `count()` | 计数 |
| `as_list()` | 转为列表 |
| `do(func)` | 执行副作用 |

---

## 占位符

vools 提供多种占位符用于构建简洁的函数表达式。

### `_` - 通用占位符

```python
from vools.functional import _

# 基本运算
f = _ + 2
f(5)  # 7

f = _ * 2 + 1
f(3)  # 7

# 比较
f = _ > 5
f(10)  # True
f(3)   # False

# 属性访问
f = _.name
f(person)  # person.name

# 方法调用
f = _.upper()
f("hello")  # "HELLO"

# 索引访问
f = _[0]
f([1, 2, 3])  # 1

# 类型检查
f = _ @ int
f(5)  # True
f("5")  # False
```

### `_1`, `_2`, `_3` - 多参数占位符

```python
from vools.functional import _1, _2, _3

# 多参数函数
f = _1 + _2
f(3, 4)  # 7

f = _1 * _2 + _3
f(2, 3, 4)  # 10

# 参数位置
f = _2 - _1  # 第二个参数减第一个
f(5, 10)  # 5
```

### `_n` - 索引占位符

支持 `_1` 到 `_20`，表示第 n 个参数。

```python
from vools.functional import _5

f = _5 * 2
f(1, 2, 3, 4, 5)  # 10
```

### 占位符组合

```python
# 逻辑组合
f = (_ > 0) & (_ < 10)
f(5)  # True
f(15)  # False

# 集合操作
f = _.in_([1, 2, 3])
f(2)  # True

f = _.contains([1, 2])
f([1, 2, 3])  # True

# 类型转换
f = _.toString()
f(123)  # "123"

f = _.toInt()
f("123")  # 123
```

---

## 箭头函数 g

`g` 函数支持多种表达式格式，快速创建函数。

**支持的格式：**
- `"x,y => x + y"` : Lambda 表达式格式
- `"x + y"` : 使用 `_` 占位符
- `"lambda x: x + 1"` : 标准 Lambda 表达式

**示例：**

```python
from vools.functional import g

# Lambda 格式
f = g("x, y => x + y")
f(3, 4)  # 7

# 占位符格式
f = g("_ + 2 * _")
f(3, 4)  # 11

# 索引占位符
f = g("_1 + _2")
f(3, 4)  # 7

# 标准 Lambda
f = g("lambda x: x + 1")
f(5)  # 6

# 多语句
f = g("x, y => result = x * y; result + 10")
f(3, 4)  # 22

# 三元运算符（类 C 格式）
f = g("x => x > 0 ? 'positive' ! 'negative'")
f(5)   # "positive"
f(-5)  # "negative"

# 自定义环境
import math
f = g("x => math.sqrt(x)", env={'math': math})
f(16)  # 4.0
```

---

## iif 条件表达式

`iif` 提供灵活的条件判断功能。

**基本用法：**

```python
from vools.functional import iif

# 简单条件
result = iif(True, "yes", "no")
print(result)  # "yes"

# 函数条件
result = iif(lambda x: x > 5, "大", "小", data=10)
print(result)  # "大"

# 字符串条件
result = iif("x > 5", "大", "小", data=10)
print(result)  # "大"
```

### ConditionBuilder

链式条件构建器。

```python
from vools.functional import ConditionBuilder

# 链式条件
cb = ConditionBuilder(10)
result = cb.case(5, "小").case(10, "中").case(15, "大").default("未知")
print(result.evaluate())  # "中"

# 批量条件
cb = ConditionBuilder()
cb.cases({5: "小", 10: "中", 15: "大"})
result = cb.evaluate(10)  # "中"

# 组合条件
cb1 = ConditionBuilder(10).case(lambda x: x > 5, "大于5")
cb2 = ConditionBuilder(10).case(lambda x: x < 15, "小于15")
combined = cb1 | cb2

# 逻辑组合
cb = ConditionBuilder(10)
cb.when(lambda x: x > 5, "大于5", logic='and')
cb.when(lambda x: x < 15, "且小于15")
```

### LazyProperty

延迟属性装饰器。

```python
from vools.functional import LazyProperty

class MyClass:
    @LazyProperty
    def expensive_property(self):
        # 只在首次访问时计算
        return compute_expensive_value()

obj = MyClass()
obj.expensive_property  # 计算并缓存
obj.expensive_property  # 返回缓存值
```

---

## Box 类型

`Box` 是一个增强的包装类型，支持链式调用和自动类型转换。

**示例：**

```python
from vools.functional import Box, box

# 创建 Box
b = Box([1, 2, 3])

# 链式调用
result = b.map(lambda x: x * 2).filter(lambda x: x > 2)
print(result)  # Box([4, 6])

# reduce 操作
result = b.reduce(lambda x, y: x + y)
print(result)  # 6

# 索引访问
b = Box({'a': 1, 'b': 2})
print(b._1)  # 1（第一个值）
print(b['a'])  # 1

# run 方法 - 执行副作用
b = Box([1, 2, 3])
b.run(print)  # 打印 [1, 2, 3]
b.run("*")  # 解包执行
```

### box 装饰器

将函数包装为返回 Box 的函数。

```python
from vools.functional import box

@box
def get_data():
    return [1, 2, 3]

result = get_data()
result.map(lambda x: x * 2)  # 链式调用
```

---

## Result 类型

`Result` 类型提供函数式错误处理。

**示例：**

```python
from vools.functional import Result, Success, Failure, success, failure, safe

# 创建结果
ok = success(42)
err = failure(ValueError("错误"))

# 判断状态
ok.is_success  # True
err.is_failure  # True

# 链式调用
result = success(5).map(lambda x: x * 2).map(lambda x: x + 1)
result.unwrap()  # 11

# bind 链式操作
result = success(5).bind(lambda x: success(x * 2))
result.unwrap()  # 10

# 失败时保持
result = failure(ValueError("错误")).map(lambda x: x * 2)
result.is_failure  # True

# 获取值
result = success(42)
result.unwrap()  # 42
result.unwrap_or(0)  # 42

result = failure(ValueError("错误"))
result.unwrap_or(0)  # 0
result.unwrap_or_else(lambda e: -1)  # -1

# or_else 备选
result = failure(ValueError("错误")).or_else(lambda e: success(0))
result.unwrap()  # 0

# safe 包装函数
safe_divide = safe(lambda x, y: x / y)
result = safe_divide(10, 2)  # Success(5)
result = safe_divide(10, 0)  # Failure(ZeroDivisionError)
```

---

## 其他工具函数

### flip

翻转函数参数顺序。

```python
from vools.functional import flip

f = flip(lambda x, y: x - y)
f(5, 10)  # 10 - 5 = 5
```

### apply

应用函数到参数。

```python
from vools.functional import apply

result = apply(lambda x, y: x + y, 3, 4)
print(result)  # 7
```

### F

将函数转换为占位符函数。

```python
from vools.functional import F

f = F(len)
f([1, 2, 3])  # 3
```

### to_holder

将函数转换为占位符。

```python
from vools.functional import to_holder

f = to_holder(lambda x, y: x + y)
f(3)(4)  # 7
```

### for_ / foreach

循环执行函数。

```python
from vools.functional import for_, foreach

# for 循环
for_(range(5), lambda i: print(i))

# foreach 集合遍历
foreach([1, 2, 3], lambda x: print(x * 2))
```

### build / build_text

构建字符串。

```python
from vools.functional import build, build_text

result = build("Hello", " ", "World")
print(result)  # "Hello World"

result = build_text(["Line1", "Line2"], separator="\n")
print(result)  # "Line1\nLine2"
```

### waiter

等待函数。

```python
from vools.functional import waiter

# 等待条件满足
waiter(lambda: check_condition(), timeout=10)
```