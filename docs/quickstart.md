# vools 快速入门指南（10 分钟）

## 简介

**vools** 是一个强大的 Python 函数式编程工具集，提供：

- **装饰器**：柯里化、重试、缓存、重载等
- **函数式工具**：占位符、管道操作、箭头函数
- **响应式编程**：Observable、Subject、操作符
- **数据处理**：Seq 序列、vic 工具类
- **系统监控**：键盘、鼠标、剪贴板、文件监控

> 当前版本：v0.1.16 | 许可证：Apache 2.0

---

## 安装

```bash
# 从 PyPI 安装
pip install vools

# 从源码安装（开发版）
git clone https://github.com/vicTop-cw/vools.git
cd vools
pip install -e .
```

**环境要求**：Python 3.6+

---

## 快速示例

### 1. curry 柯里化装饰器

将多参数函数转换为可分步调用的形式：

```python
from vools import curry

@curry
def add(a, b, c):
    return a + b + c

# 三种调用方式，结果相同
result = add(1, 2, 3)      # 6
result = add(1)(2)(3)      # 6（柯里化）
result = add(1, 2)(3)      # 6（混合调用）

# 创建偏函数
add_five = add(5)
result = add_five(3, 2)    # 10
```

### 2. retry 重试装饰器

自动重试失败的操作：

```python
from vools import retry

@retry(times=3, delay=1.0)
def fetch_data(url):
    """网络请求失败时自动重试 3 次，每次间隔 1 秒"""
    import requests
    response = requests.get(url)
    return response.json()

# 即使偶尔失败，也能成功获取数据
data = fetch_data("https://api.example.com/data")
```

### 3. Pipe 管道操作

链式处理数据流：

```python
from vools import Pipe, Ops

# 使用 Pipe 包装函数
result = [1, 2, 3, 4, 5] | Pipe(lambda x: [i * 2 for i in x])
# 结果: [2, 4, 6, 8, 10]

# 使用 Ops 操作符集合
result = [1, 2, 3, 4, 5] | Ops.filter(lambda x: x > 2) | Ops.map(lambda x: x * 2) | Ops.sum()
# 结果: 24 (3*2 + 4*2 + 5*2)

# 链式调用
result = range(10) | Ops.filter(lambda x: x % 2 == 0) | Ops.map(lambda x: x ** 2) | Ops.collect()
# 结果: [0, 4, 16, 36, 64]
```

### 4. Observable 响应式编程

创建和操作数据流：

```python
from vools.reactive import Observable, ops

# 创建 Observable
obs = Observable.from_iterable([1, 2, 3, 4, 5])

# 使用管道操作
obs.pipe(
    ops.filter(lambda x: x > 2),      # 过滤大于 2 的值
    ops.map(lambda x: x * 2),          # 映射乘以 2
    ops.take(2)                        # 只取前 2 个
).subscribe(on_next=print)             # 输出: 6, 8

# Subject - 可手动推送数据
from vools.reactive import Subject

subject = Subject()
subject.subscribe(on_next=lambda x: print(f"收到: {x}"))
subject.on_next(1)  # 输出: 收到: 1
subject.on_next(2)  # 输出: 收到: 2
```

### 5. Seq 序列处理

惰性序列操作：

```python
from vools import Seq

# 创建序列
seq = Seq([1, 2, 3, 4, 5])

# 链式操作（惰性执行）
result = seq.map(lambda x: x * 2).filter(lambda x: x > 5).collect()
# 结果: [6, 8, 10]

# 更多操作
result = Seq(range(10)).filter(lambda x: x % 2 == 0).take(3).collect()
# 结果: [0, 2, 4]

# 统计操作
result = Seq([1, 2, 3, 4, 5]).reduce(lambda a, b: a + b, 0)
# 结果: 15
```

### 6. 占位符表达式

简洁的匿名函数创建：

```python
from vools import _, _1, _2

# 单参数占位符
f = _ + 1
result = f(5)           # 6

# 多参数占位符
f = _1 + _2
result = f(10, 20)      # 30

# 复合表达式
f = _1 * (_2 + _3)
result = f(2, 3, 4)     # 14 (2 * (3 + 4))

# 属性访问
f = _.upper
result = f("hello")()   # "HELLO"
```

### 7. memorize 缓存装饰器

缓存函数结果，避免重复计算：

```python
from vools import memorize

@memorize(duration=60)  # 缓存 60 秒
def expensive_calc(n):
    """模拟耗时计算"""
    import time
    time.sleep(1)
    return n ** 2

# 第一次调用（耗时约 1 秒）
result = expensive_calc(100)  # 10000

# 第二次调用（立即返回缓存）
result = expensive_calc(100)  # 10000（秒级返回）
```

### 8. g 箭头函数

从字符串生成函数：

```python
from vools import g

# 箭头函数语法
add = g("x, y => x + y")
result = add(3, 4)      # 7

# 下划线语法
double = g("_ * 2")
result = double(5)      # 10

# 索引下划线
f = g("_1 + _2 * _3")
result = f(1, 2, 3)     # 7 (1 + 2*3)
```

### 9. overload 函数重载

根据参数数量/类型选择不同实现：

```python
from vools import overload

@overload
def process():
    return "无参数"

@process.register
def process(x):
    return f"单参数: {x}"

@process.register
def process(x, y):
    return f"双参数: {x}, {y}"

print(process())        # 无参数
print(process(10))      # 单参数: 10
print(process(1, 2))    # 双参数: 1, 2
```

### 10. iif 条件表达式

函数式条件判断：

```python
from vools import iif

# 基本用法
result = iif(True, "yes", "no")     # "yes"
result = iif(5 > 3, "大", "小")      # "大"

# 链式条件
result = iif(15).when(lambda x: x > 10, "大").otherwise("小")
# 结果: "大"

# 多条件匹配
result = iif(3).case(1, "一").case(2, "二").case(3, "三").otherwise("其他")
# 结果: "三"
```

---

## 功能速查表

| 功能 | 用途 | 示例 |
|------|------|------|
| `@curry` | 柯里化函数 | `add(1)(2)(3)` |
| `@retry` | 自动重试 | `@retry(times=3)` |
| `@memorize` | 结果缓存 | `@memorize(duration=60)` |
| `Pipe` | 管道操作 | `data | Pipe(func)` |
| `Ops` | 操作符集合 | `data | Ops.filter(f)` |
| `Seq` | 惰性序列 | `Seq(data).map(f).collect()` |
| `Observable` | 响应式流 | `Observable.from_iterable(data)` |
| `_`, `_1`, `_2` | 占位符 | `(_ + 1)(5)` |
| `g` | 箭头函数 | `g("x => x * 2")` |
| `@overload` | 函数重载 | 多参数版本选择 |
| `iif` | 条件表达式 | `iif(cond, yes, no)` |

---

## 下一步

深入了解各模块的详细用法：

| 文档 | 内容 |
|------|------|
| [核心功能](../guide/core.md) | 占位符、重载、stuff、persist、Box、g、iif |
| [函数式编程](../guide/functional.md) | curried 模块、管道操作、Seq 序列 |
| [响应式编程](../guide/reactive.md) | Observable、Subject、操作符、系统监控 |
| [vic 工具类](../guide/vic-classes.md) | vicDate、vicText、vicList 数据处理 |
| [编码加密](../guide/extras.md) | encoding、crypto、Result 类型 |
| [完整用户指南](../USER_GUIDE.md) | 所有功能的详细说明 |

---

## 常见问题

### Q: 如何选择 Pipe vs Seq vs Observable？

- **Pipe**：简单的链式数据处理
- **Seq**：需要惰性执行或复杂序列操作
- **Observable**：事件流、异步数据、需要订阅机制

### Q: curry 和 stuff 有什么区别？

- `@curry`：纯柯里化，支持分步调用
- `@stuff`：柯里化 + 依赖注入，可自动解析参数

### Q: 如何运行测试？

```bash
python -m pytest tests/ -v
```

---

**GitHub**: https://github.com/vicTop-cw/vools  
**PyPI**: https://pypi.org/project/vools/  
**许可证**: Apache 2.0