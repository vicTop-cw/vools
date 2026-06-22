# vools 核心功能指南（v0.1.18）

本指南覆盖 vools 中最常用的核心组件：占位符、重载装饰器、`stuff`、`persist`、`Box`、`g`、`iif` 以及 `Result`/`safe`。所有示例均可运行。

> Python 3.9+ 支持

---

## 1. 快速示例

```python
from vools import _, _1, _2, overload, stuff, persist

# 占位符：简单匿名函数
f = _ + 1
print(f(2))              # 3

f = _1 + _2
print(f(1, 2))           # 3

# 基于参数数量的重载
@overload
def process():
    return "无参数"

@process.register
def process(x):
    return f"一个参数: {x}"

print(process())         # 无参数
print(process(10))       # 一个参数: 10

# stuff 柯里化延迟调用
@stuff
def add(a, b, c):
    return a + b + c

print(add(1)(2)(3)())    # 6
print(add(1, 2, 3)())     # 6

# persist: 结果缓存到本地 JSON 文件
@persist
def expensive(x):
    return x ** 2

print(expensive(5))      # 25（第 1 次会写入 __persist__/expensive.json）
print(expensive(5))      # 25（第 2 次直接从缓存读取）

# Box：将返回值包装为可扩展的容器
from vools.functional import Box, box

data = Box([10, 20, 30])
print(data.map(lambda x: x * 2))   # [20, 40, 60]

# g：用字符串生成函数
from vools.functional import g
f = g("x, y => x * y + 1")
print(f(3, 4))                     # 13

# iif：条件表达式
from vools.functional import iif
print(iif(True, "yes", "no"))      # yes
```

---

## 2. 占位符（`_` / `_1` / `_2`）

通过运算符重载构造匿名函数，省去 `lambda`。

### 基本运算符

```python
from vools.functional import _, _1, _2

# 单参数
f = _ + 10
assert f(5) == 15

f = _ * _
assert f(3, 3) == 9
```

### 数字索引占位符（`_1` / `_2` / `_3`…）

`_n` 表示第 n 个位置参数，适合多参数函数调用：

```python
f = _1 + _2
assert f(3, 4) == 7

f = _1 * (_2 + _2)
assert f(2, 3) == 12
```

### 属性访问

属性访问返回一个可调用对象，需要再次 `()` 求值：

```python
f = _.upper
assert f("hello")() == "HELLO"

f = _.split
assert f("a,b,c")(",") == ["a", "b", "c"]
```

### 下标访问

```python
f = _[0]
assert f([10, 20, 30]) == 10

f = _1[1]
assert f([1, 2, 3]) == 2
```

### 复杂表达式

```python
f = (_1 + _2) * _3
assert f(2, 3, 4) == 20
```

---

## 3. 重载装饰器

vools 提供三种重载机制，分别适用于不同场景。

### 3.1 `@overload` — 基于参数数量 / 类型的重载

这是推荐用法。`@overload` 把函数转换为一个 `OverloadManager`，通过 `.register(...)` 注册不同参数数量的实现。调用时根据传入参数数量选择分支。

```python
from vools import overload

@overload
def process():
    return "无参数"

@process.register
def process(x):
    return f"一个参数: {x}"

@process.register
def process(x, y):
    return f"两个参数: {x}, {y}"

assert process() == "无参数"
assert process(10) == "一个参数: 10"
assert process(10, 20) == "两个参数: 10, 20"
```

用于类方法时按同样模式注册（默认按参数数量匹配）：

```python
class Calc:
    @overload
    def compute(self, x: int):
        return x * 2

    @compute.register
    def compute(self, x: str):
        return len(x)

    @compute.register
    def compute(self, x: list):
        return sum(x)

c = Calc()
assert c.compute(5) == 10
assert c.compute("hello") == 5
assert c.compute([1, 2, 3]) == 6
```

> 提示：每个 `@xxx.register` 下面的函数名不要求与主函数同名，内部按注册顺序尝试匹配。

### 3.2 `@overcurry` — 柯里化 + 重载

`@overcurry` 把每个注册的函数视为自动柯里化。可以一段一段地给参数，收集到足够参数后再执行；也可以直接一次性传入全部参数。

```python
from vools import overcurry

@overcurry
def add(a, b):
    return a + b

@add.register
def add(a, b, c):
    return a + b + c

@add.register
def add(a, b, c, d):
    return a + b + c + d

# 柯里化：分多次给参数
assert add(1)(2) == 3
# 一次性给足参数
assert add(1, 2, 3) == 6
assert add(1, 2, 3, 4) == 10
```

它内部按"实际提供的参数数量"选择合适的分支执行。

### 3.3 `@overloads` — 同名函数重载（已弃用）

`@overloads` 目前仅作为 `@overload` 的别名存在，**建议直接使用 `@overload` + `.register`** 的模式。若仍然使用它，将触发 `DeprecationWarning`。

### 3.4 三种重载方式对比

| 特性 | `@overload` | `@overcurry` | `@overloads`（弃用） |
|---|---|---|---|
| 柯里化支持 | 否 | 是 | 否 |
| 按参数数量匹配 | 是 | 是 | 是 |
| 注册方式 | `.register` | `.register` | 同名函数 |
| 推荐等级 | ★★★ | ★★ | ★ |

---

## 4. `stuff` 函数 — 延迟柯里化执行

`@stuff` 把一个普通函数包装成可分步传参的 `Stuff` 实例：每次调用 `(...)` 都会累积参数，最后以 `()` 触发实际执行。

```python
from vools import stuff

@stuff
def add(a, b, c):
    return a + b + c

# 分步传入
assert add(1)(2)(3)() == 6
# 一次传入
assert add(1, 2, 3)() == 6
# 混合
assert add(1, 2)(3)() == 6
```

> 注意：不要在目标函数的关键字参数中使用 `Stuff` 内部保留的参数绑定语法；正常调用时只需关注"未传够参数前返回新的 `Stuff`，传够后用 `()` 触发"这一规则。

---

## 5. `persist` 装饰器 — 本地文件缓存

把函数执行结果缓存为 JSON 文件，后续以相同参数调用时直接返回缓存值。

### 基本用法

```python
from vools import persist

@persist
def expensive_computation(x):
    return x ** 2

# 第一次执行，结果写入 __persist__/expensive_computation.json
assert expensive_computation(5) == 25
# 第二次执行，命中缓存直接返回
assert expensive_computation(5) == 25
# 强制刷新（忽略已有缓存）
assert expensive_computation(5, force=True) == 25
```

### 可用的关键字参数

| 参数 | 类型 | 说明 |
|---|---|---|
| `file_key` | `str` | 缓存文件名（不含 `.json`），默认使用函数名 |
| `force` | `bool` | 是否忽略缓存，强制重新执行，默认 `False` |
| `force_when` | `Callable[[result, start, end], bool]` | 自定义刷新条件：入参分别为上次缓存结果、上次执行开始时间戳、上次执行结束时间戳。返回 `True` 时重新执行 |
| `target_folder` | `str` | 缓存目录路径；默认在被装饰函数所在文件同级目录下创建 `__persist__` |

### 更完整示例

```python
import time, tempfile

tmp = tempfile.mkdtemp()

@persist
def fetch_weather(city):
    # 模拟耗时操作
    return {"city": city, "temperature": 25}

# 不同参数用不同 file_key 区分缓存
weather = fetch_weather("Beijing", file_key="weather_bj", target_folder=tmp)
weather = fetch_weather("Beijing", file_key="weather_bj", target_folder=tmp)

# 超过 1 小时则刷新
weather = fetch_weather(
    "Beijing",
    file_key="weather_bj",
    target_folder=tmp,
    force_when=lambda result, start, end: time.time() - end > 3600,
)
```

### 约束

- 函数返回值必须可 JSON 序列化（`dict` / `list` / `str` / `int` / `float` / `bool` / `None` 及其嵌套）。
- 缓存文件为 JSON，包含 `result`、`start_time`、`end_time`。
- 文件写入使用简单的跨平台文件锁，避免并发写入竞争。

---

## 6. `Box` 类与 `box` 装饰器

`Box` 是基于 `wrapt.ObjectProxy` 的通用包装容器，为任意对象附加 `map` / `filter` / `reduce` / `run` 等函数式操作，并允许按数字索引访问元素。`@box` 则把函数返回值自动包装成 `Box`。

### `Box(dict_or_list)`

```python
from vools.functional import Box

# 包装字典 — 通过 dict 方法访问
d = Box({"name": "Alice", "age": 30})
print(d.items())       # dict_items([('name', 'Alice'), ('age', 30)])
print(d.get("name"))    # Alice

# 数字索引访问（按插入顺序：_1 第一个，_2 第二个…）
print(d._1)             # Alice
print(d._2)             # 30

# 包装列表 — 可链式调用
l = Box([10, 20, 30, 40])
print(l.map(lambda x: x * 2))         # [20, 40, 60, 80]
print(l.filter(lambda x: x > 15))      # [20, 30, 40]
print(l.reduce(lambda a, b: a + b))    # 100

# 通过下标/切片访问
print(l[0])     # 10
print(l[1:3])   # [20, 30]
```

### `@box` 装饰器

```python
from vools.functional import box

@box
def get_user():
    return {"username": "alice", "score": [10, 20, 30]}

result = get_user()
# result 是 Box 包装的 dict，可访问 items() / keys() / ._1 / ._2 等
print(result._1)          # alice（第一个键对应的值）
print(result._2)          # [10, 20, 30]
```

> 注意：`Box` 并不像 `dataclass` / `SimpleNamespace` 那样直接把字典键当成对象属性使用（例如 `data.name` 不工作）。需要按键或 `_1` / `_2` 等数字索引读取。

---

## 7. `g` 函数 — 从字符串生成函数

`g(expr)` 支持多种写法，按顺序识别：标准 `lambda ...`、箭头函数 `a, b => ...`、下划线占位符表达式。

### 箭头函数格式

```python
from vools.functional import g

f = g("x, y => x + y")
assert f(3, 4) == 7

f = g("x => x ** 2 + 1")
assert f(5) == 26
```

### 下划线占位符

```python
# 每个独立的 _ 按顺序对应一个参数
f = g("_ + 2 * _")
assert f(3, 4) == 11

# 使用 _1 / _2 / ... 显式指定参数位置
f = g("_1 + _2 * 2")
assert f(3, 4) == 11
```

### 标准 lambda 写法

```python
f = g("lambda x: x + 1")
assert f(5) == 6
```

### 无参函数 / 常值

```python
f = g("42")
assert f() == 42
```

### 多语句

以分号分隔的多条语句，最后一条为返回值：

```python
f = g("x => sq = x * x; sq + 1")
assert f(3) == 10
```

---

## 8. `iif` 函数 — 条件表达式 / 模式匹配

`iif` 提供两种形态：
- 三目式：`iif(cond, true_val, false_val)`
- 链式匹配：通过 `ConditionBuilder(value).case(...)` / `.when(...)` / `.otherwise(...)` 构造

### 基础条件表达式

```python
from vools.functional import iif

assert iif(True, "yes", "no") == "yes"
assert iif(False, "yes", "no") == "no"
```

### 可调用条件 — 无 data 参数

当条件是可调用对象时，`true_body` / `false_body` 也可以是可调用或普通值：

```python
result = iif(lambda: len([1, 2, 3]) > 2, "long", "short")
assert result == "long"
```

### 链式匹配

```python
from vools.functional import iif, ConditionBuilder

value = 3

# .case(值, 结果) — 相等比较
r = ConditionBuilder(value).case(1, "one").case(2, "two").case(3, "three").otherwise("other")
assert r() == "three"

# .when(条件, 结果) — 条件可以是 lambda 或表达式
r = ConditionBuilder(value).when(lambda x: x > 10, "big").otherwise("small")
assert r() == "small"

# 当 otherwise 未被调用且没有任何条件成立时，返回 None
r = ConditionBuilder(100).case(1, "one").case(2, "two")
assert r() is None

# 使用 data 参数：条件表达式对 data 求值
r = iif(lambda v: v > 10, "big", "small", data=15)
assert r == "big"
```

> 注意：链式调用通过 `()` 触发最终求值。

---

## 9. `Result` 类型与 `safe` 装饰器

### `Result` / `Success` / `Failure`

`Result` 是一个"成功/失败"二选一的容器。成功时持有结果值，失败时持有异常对象。

```python
from vools.functional import Result, Success, Failure

# 构造
ok = Result.success(42)
bad = Result.failure(ValueError("非法输入"))

assert ok.is_success is True
assert bad.is_failure is True

# map — 只对成功值转换
assert ok.map(lambda x: x * 2).unwrap() == 84
assert bad.map(lambda x: x * 2).is_failure is True

# 解包
assert ok.unwrap() == 42
assert ok.unwrap_or(0) == 42
assert bad.unwrap_or(0) == 0

# bind — 以 Result 为返回值的链式组合
step = ok.bind(lambda v: Result.success(v + 1))
assert step.unwrap() == 43

# 便捷子类
s = Success(10)
f = Failure(ValueError("bad"))
assert s.is_success and f.is_failure
```

### `@safe` 装饰器 — 把异常转换为 `Result`

```python
from vools.functional import safe

@safe
def divide(a, b):
    return a / b

r1 = divide(10, 2)
assert r1.is_success and r1.unwrap() == 5

r2 = divide(1, 0)
assert r2.is_failure
assert isinstance(r2.unwrap_or(0), int)        # 0
```

使用 `@safe` 可以将任意可能抛出异常的函数转换为"返回 `Result`"的安全版本，避免 `try/except` 层层嵌套。
