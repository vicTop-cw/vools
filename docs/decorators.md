# 装饰器模块

vools 提供了一系列强大的装饰器，用于增强函数和类的功能。

## 目录

- [缓存装饰器](#缓存装饰器)
  - [memorize](#memorize)
  - [once](#once)
  - [persist](#persist)
- [控制流装饰器](#控制流装饰器)
  - [repeat](#repeat)
  - [retry](#retry)
  - [rerun](#rerun)
- [柯里化装饰器](#柯里化装饰器)
  - [curry](#curry)
  - [delay_curry](#delay_curry)
- [重载装饰器](#重载装饰器)
  - [overload](#overload)
- [自引用装饰器](#自引用装饰器)
  - [rself](#rself)
- [快捷工具装饰器](#快捷工具装饰器)

---

## 缓存装饰器

### memorize

函数结果缓存装饰器，缓存函数结果一段时间。

**参数：**
- `duration`: 缓存持续时间（秒），默认 3 秒

**示例：**

```python
from vools import memorize

# 基本用法
@memorize
def expensive_function(x):
    return x ** 2

# 带参数
@memorize(duration=5)
def another_function(x):
    return x ** 3

# 类方法
class MyClass:
    @memorize(duration=5)
    def method(self, x):
        return x * 2
```

### once

单次执行装饰器，确保函数或类只执行/初始化一次。

**功能：**
- 对于函数：第一次调用时执行并缓存结果，后续调用直接返回缓存结果
- 对于类：转换为单例模式
- 支持 `force=True` 强制重新执行

**参数：**
- `force_default`: 默认的 force 参数值（可选）

**示例：**

```python
from vools import once

@once
def initialize():
    print("Initializing...")
    return 42

initialize()  # 输出: Initializing... 返回 42
initialize()  # 不输出，返回 42（缓存）
initialize(force=True)  # 强制重新执行

# 单例模式
@once
class Singleton:
    def __init__(self, value):
        self.value = value

s1 = Singleton(1)
s2 = Singleton(2)
assert s1 is s2  # 同一个实例
```

### persist

持久化缓存装饰器，将函数的执行结果缓存到本地文件。

**参数：**
- `file_key`: 缓存文件名（不含扩展名），默认使用函数名
- `force`: 是否强制重新执行，默认 False
- `force_when`: 条件函数，返回 True 时强制刷新
- `target_folder`: 缓存文件所在目录

**示例：**

```python
from vools import persist

@persist
def fetch_data():
    return {"data": "value"}

# 带参数
@persist(file_key="custom_cache", target_folder="/tmp/cache")
def fetch_data_with_config():
    return {"data": "value"}

# 条件刷新
@persist(force_when=lambda result, start, end: time.time() - end > 3600)
def fetch_weather(city):
    return {"temp": 25}
```

---

## 控制流装饰器

### repeat

重复执行装饰器，支持指定次数或条件控制。

**参数：**
- `cnt`: 重复次数或停止条件
  - `int > 0`: 执行指定次数
  - `int < 0`: 无限循环
  - `int = 0`: 不执行
  - 可调用对象：返回 False 时停止
- `delay`: 每次调用后的延迟时间（秒）

**返回：** 生成器迭代器

**示例：**

```python
from vools import repeat

# 执行 3 次
@repeat(cnt=3, delay=0.5)
def greet(name):
    return f"Hello, {name}!"

for result in greet("Alice"):
    print(result)

# 无限循环（需要手动停止）
@repeat(cnt=-1)
def infinite_task():
    return "running"

# 条件控制
@repeat(cnt=lambda: should_continue())
def conditional_task():
    return "task"
```

### retry

重试装饰器，支持多种重试条件和灵活的重试逻辑。

**参数：**
- `tries`: 最大重试次数（包括首次执行），默认 3
- `delay`: 初始延迟时间（秒），默认 1
- `backoff`: 延迟时间倍增因子，默认 2
- `exceptions`: 需要捕获并重试的异常类型，默认 Exception
- `check_func`: 返回值检查函数（可选）
- `logic`: 重试条件逻辑组合方式 ('or', 'and', 'xor')，默认 'or'
- `logger`: 日志记录器实例（可选）

**示例：**

```python
from vools import retry

# 基本用法
@retry
def unreliable_request():
    import random
    if random.random() < 0.8:
        raise ConnectionError("网络连接失败")
    return "请求成功"

# 带参数
@retry(tries=3, delay=0.5, backoff=2)
def another_request():
    return "请求成功"

# 返回值检查
@retry(tries=5, check_func=lambda x: x is not None)
def get_data():
    return data

# 严格逻辑
@retry(tries=3, logic='and', check_func=lambda x: x > 0)
def strict_retry():
    return value
```

### rerun

周期性执行函数直到满足终止条件或超时。

**参数：**
- `until`: 检查函数返回值的谓词函数，返回 True 时停止
- `interval`: 重试间隔时间（秒），默认 5
- `time_out`: 总超时时间（秒），默认 300

**异常：** TimeoutError - 当超过 time_out 时间仍未满足条件时抛出

**示例：**

```python
from vools import rerun

# 基本用法
@rerun
def check_status():
    return {'status': 'success'}

# 带条件
@rerun(until=lambda x: x.get('status') == 'success', interval=1, time_out=10)
def check_status_with_condition():
    import random
    if random.random() < 0.7:
        return {'status': 'pending'}
    return {'status': 'success'}
```

---

## 柯里化装饰器

### curry

柯里化装饰器，将多参数函数转换为可逐步应用参数的函数。

**参数：**
- `is_strict`: 是否启用严格类型检查，默认 False
- `delaied`: 是否延迟执行，默认 False

**示例：**

```python
from vools import curry

# 基本用法
@curry
def add(a, b, c):
    return a + b + c

add(1)(2)(3)  # 6
add(1, 2)(3)  # 6
add(1)(2, 3)  # 6

# 严格类型检查
@curry(is_strict=True)
def typed_add(a: int, b: int) -> int:
    return a + b

typed_add(1)(2)  # 3
typed_add('1')(2)  # TypeError

# 延迟执行
@curry(delaied=True)
def delayed_add(a, b):
    return a + b

f = delayed_add(1)(2)
f()  # 3（显式调用执行）
```

### delay_curry

延迟柯里化装饰器，必须显式调用空参数才能执行。

**示例：**

```python
from vools import delay_curry

@delay_curry
def compute(a, b, c):
    return a + b + c

f = compute(1)(2)(3)
f()  # 显式执行
```

---

## 重载装饰器

### overload

函数重载装饰器，支持基于参数数量和类型的重载。

**参数：**
- `is_strict`: 是否使用严格类型检查
- `priority`: 全局优先级 ('first' 或 'last')
- `check`: 自定义参数匹配规则

**示例：**

```python
from vools import overload

# 基本用法
@overload
def process():
    return "无参数"

@process.register
def process(x: int):
    return f"一个参数: {x}"

@process.register
def process(x: int, y: str):
    return f"两个参数: {x}, {y}"

process()          # "无参数"
process(10)        # "一个参数: 10"
process(10, "hi")  # "两个参数: 10, hi"

# 严格类型检查
@overload(is_strict=True)
def strict_process(x: int):
    return f"整数: {x}"

@strict_process.register
def strict_process(x: str):
    return f"字符串: {x}"

# 优先级控制
@overload(priority='first')
def priority_process():
    return "高优先级"
```

---

## 自引用装饰器

### rself

类装饰器，实现链式调用支持，自动将父类方法的返回值转换为子类实例。

**功能：**
1. 限制继承方式为最多单继承或不继承
2. 返回值处理：
   - 返回 None → 返回自身实例
   - 返回父类实例 → 转换为子类实例
3. 自定义初始化支持：通过 `__from_parent__` 类方法

**示例：**

```python
from vools import rself

@rself
class SuperText(str):
    """扩展的字符串类，支持链式调用"""
    
    def decorated(self):
        return ">> " + self

s = SuperText("hello")
result = s.upper().decorated()  # 链式调用
# result 是 SuperText 类型，不是 str

@rself
class SuperList(list):
    """增强版列表类"""
    
    def add(self, item):
        new_list = SuperList(self)
        new_list.append(item)
        return new_list

lst = SuperList([1, 2])
lst.add(3).add(4)  # 链式调用

# 自定义初始化
@rself
class SuperTextWithFactory(str):
    @classmethod
    def __from_parent__(cls, parent_val, **kwargs):
        prefix = kwargs.get('prefix', '>> ')
        return cls(str(parent_val), prefix=prefix)
```

---

## 快捷工具装饰器

### timeit

计时装饰器，测量函数执行时间。

```python
from vools import timeit

@timeit
def slow_function():
    time.sleep(1)
```

### safe

安全执行装饰器，捕获异常并返回默认值。

```python
from vools import safe

@safe(default=None)
def risky_function():
    raise ValueError("错误")
```

### throttle

节流装饰器，限制函数调用频率。

```python
from vools import throttle

@throttle(seconds=1)
def frequent_function():
    return "result"
```

### debounce

防抖装饰器，延迟执行直到停止调用一段时间后。

```python
from vools import debounce

@debounce(seconds=0.5)
def input_handler(value):
    process(value)
```

### singleton

单例装饰器，确保类只有一个实例。

```python
from vools import singleton

@singleton
class Database:
    def __init__(self):
        self.connection = connect()
```

### deprecated

弃用警告装饰器。

```python
from vools import deprecated

@deprecated(message="请使用 new_function 替代")
def old_function():
    pass
```

### validate

参数验证装饰器。

```python
from vools import validate

@validate(lambda x: x > 0, "x 必须为正数")
def positive_function(x):
    return x
```

### rate_limit

速率限制装饰器。

```python
from vools import rate_limit

@rate_limit(calls=10, period=60)
def api_call():
    return "result"
```

### cache_with_ttl

带 TTL 的缓存装饰器。

```python
from vools import cache_with_ttl

@cache_with_ttl(seconds=300)
def cached_api_call():
    return fetch_data()
```

### hybrid_method

混合方法装饰器，支持类和实例调用。

```python
from vools import hybrid_method

class MyClass:
    @hybrid_method
    def method(cls_or_self):
        if isinstance(cls_or_self, type):
            return "类调用"
        return "实例调用"
```

### classproperty

类属性装饰器。

```python
from vools import classproperty

class MyClass:
    @classproperty
    def name(cls):
        return cls.__name__
```

### enumize

枚举装饰器。

```python
from vools import enumize

@enumize
class Status:
    PENDING = "pending"
    ACTIVE = "active"
    DONE = "done"
```