# vools 常见问题文档 (FAQ)

本文档收集了 vools 库使用过程中的常见问题、解决方案和最佳实践。

---

## 目录

- [装饰器使用问题](#装饰器使用问题)
- [函数式工具使用问题](#函数式工具使用问题)
- [响应式编程问题](#响应式编程问题)
- [迁移指南](#迁移指南)

---

## 装饰器使用问题

### 1. 占位符表达式报错

**问题描述**

使用 `_` 占位符时出现语法错误或结果不符合预期。

```python
# 错误示例
f = _ + _  # 期望 f(1, 2) == 3，但实际行为可能不符合预期
```

**解决方案**

确保使用正确的占位符语法：

| 场景 | 正确用法 | 说明 |
|------|----------|------|
| 单参数 | `f = _ + 1` | `_` 表示第一个参数 |
| 多参数 | `f = _1 + _2` | `_1`, `_2`, `_3` 表示不同位置的参数 |
| 复杂表达式 | `f = _.__expr__("_1 + _2 * _3")` | 使用 `__expr__` 方法 |

```python
# 正确示例
from vools import _, _1, _2, _3

# 单参数场景
f = _ + 1
assert f(2) == 3

# 多参数场景 - 使用索引占位符
f = _1 + _2
assert f(1, 2) == 3

# 复杂表达式
f = _.__expr__("_1 * (_2 + _3)")
assert f(2, 3, 4) == 14
```

**最佳实践**

- 单参数场景优先使用 `_`
- 多参数场景必须使用 `_1`, `_2`, `_3` 等索引占位符
- 复杂表达式推荐使用 `g` 函数或 `__expr__` 方法

---

### 2. 重载函数不匹配

**问题描述**

调用重载函数时没有匹配到正确的实现，或出现 `TypeError`。

```python
# 错误示例
@overload(is_strict=True)
def add(a: int, b: int):
    return a + b

@add.register
def add_str(a: str, b: str):
    return a + b

add(1, "2")  # TypeError: 类型不匹配
```

**解决方案**

检查以下几点：

1. **参数数量是否匹配**：确保调用的参数数量与某个注册函数匹配
2. **类型检查**：在严格模式下，参数类型必须完全匹配
3. **优先级设置**：检查优先级是否正确设置

```python
from vools import overload

# 非严格模式 - 按参数数量匹配
@overload
def process():
    return "无参数"

@process.register
def process_x(x):
    return f"一个参数: {x}"

@process.register
def process_xy(x, y):
    return f"两个参数: {x}, {y}"

# 正确调用
process()      # 匹配无参数版本
process(10)    # 匹配单参数版本
process(10, 20) # 匹配双参数版本

# 严格模式 - 按类型匹配
@overload(is_strict=True)
def add(a: int, b: int):
    return a + b

@add.register
def add_str(a: str, b: str):
    return a + b

# 正确调用
add(1, 2)      # 匹配 int 版本
add("a", "b")  # 匹配 str 版本
```

**三种重载方式对比**

| 特性 | @overload | @overcurry | @overloads |
|------|-----------|------------|------------|
| 柯里化支持 | 否 | 是 | 否 |
| 类型检查 | 支持 | 支持 | 支持 |
| 优先级控制 | 支持 | 否 | 否 |
| 类方法支持 | 是 | 是 | 是 |
| 注册方式 | `.register` | `.register` | 同名方法 |

---

### 3. 装饰器调用方式混淆

**问题描述**

不清楚装饰器应该使用 `@decorator` 还是 `@decorator(params)` 调用方式。

```python
# 混淆示例
@memorize(duration=60)  # 正确
def func1(): pass

@memorize  # 也正确！
def func2(): pass
```

**解决方案**

vools 所有装饰器都统一支持两种调用方式：

```python
from vools import memorize, once, persist, retry, curry

# 方式一：直接调用（使用默认参数）
@memorize
def func1():
    pass

# 方式二：带参数调用
@memorize(duration=60)
def func2():
    pass

# 其他装饰器示例
@once                    # 直接调用
@once(force_default=True)  # 带参数调用

@persist                 # 直接调用
@persist(file_key="cache")  # 带参数调用

@retry                   # 直接调用（默认 tries=3）
@retry(tries=5, delay=1.0)  # 带参数调用

@curry                   # 直接调用
@curry(is_strict=True)   # 带参数调用
```

**统一实现模式**

所有装饰器采用以下模式：

```python
def decorator(func=None, *, param=default):
    if func is None:
        # @decorator(params) 带参数调用
        return decorator_impl
    else:
        # @decorator 直接调用
        return decorator_impl(func)
```

---

### 4. stuff 依赖注入失败

**问题描述**

使用 `@stuff` 装饰器时，参数没有被正确注入。

```python
# 错误示例
@stuff
def connect(host, port):
    return f"{host}:{port}"

@connect.register
def get_host():
    return "localhost"

connect()  # port 为 None，可能导致错误
```

**解决方案**

确保注册函数名与参数名匹配：

```python
from vools import stuff

@stuff
def connect(host, port, timeout):
    return f"连接到 {host}:{port}，超时 {timeout} 秒"

# 方式一：函数名与参数名匹配
@connect.register
def host():  # 函数名 "host" 匹配参数名
    return "localhost"

# 方式二：使用 param_name 显式指定
@connect.register(param_name='port')
def get_port():  # 显式指定注入到 port 参数
    return 8080

# 方式三：批量注入多个参数
@connect.register(param_name=['host', 'port'])
def get_config():
    return "192.168.1.1", 8080

# 正确调用
result = connect(timeout=30)
# 输出: "连接到 localhost:8080，超时 30 秒"
```

**注意事项**

- 未注入的参数会保持为 `None`
- 调用时可以覆盖注入的参数
- 注册函数返回值数量必须与 `param_name` 指定的参数数量匹配

---

### 5. persist 缓存不生效

**问题描述**

使用 `@persist` 装饰器时，缓存没有被正确读取或写入。

**解决方案**

检查以下几点：

1. **文件路径权限**：确保缓存目录有写入权限
2. **返回值序列化**：函数返回值必须可 JSON 序列化
3. **缓存键冲突**：使用 `file_key` 区分不同参数的缓存

```python
from vools import persist
import tempfile

# 基本用法
@persist
def expensive_computation(x):
    return x ** 2

# 使用 file_key 区分不同参数的缓存
@persist
def fetch_weather(city):
    return {"city": city, "temp": 25}

# 不同参数使用不同缓存文件
fetch_weather("Beijing", file_key="weather_beijing")
fetch_weather("Shanghai", file_key="weather_shanghai")

# 强制刷新缓存
fetch_weather("Beijing", file_key="weather_beijing", force=True)

# 指定缓存目录
temp_dir = tempfile.mkdtemp()
fetch_weather("Beijing", file_key="weather_beijing", target_folder=temp_dir)
```

**支持的缓存参数**

| 参数 | 说明 |
|------|------|
| `file_key` | 缓存文件名（不含扩展名） |
| `force` | 强制重新执行，忽略缓存 |
| `force_when` | 条件刷新函数 |
| `target_folder` | 缓存目录 |

---

### 6. rself 装饰器报错

**问题描述**

使用 `@rself` 装饰器时出现错误。

**解决方案**

- 确保类只继承一个基类或不继承
- 检查是否有重复的方法名
- 魔法方法不会被拦截，保持原有行为

```python
from vools import rself

# 正确用法
@rself
class MyClass:
    def method(self, x):
        return x * 2

# 错误用法 - 多继承可能导致问题
@rself
class BadClass(Base1, Base2):  # 避免多继承
    pass
```

---

### 7. 循环导入错误

**问题描述**

导入模块时出现 `ImportError: cannot import name`。

**解决方案**

- 确保使用最新版本的 vools（v0.1.6+ 已修复此问题）
- 如果问题仍然存在，尝试重新安装

```bash
pip install --upgrade vools
```

---

## 函数式工具使用问题

### 1. 如何正确使用 curry

**问题描述**

不清楚柯里化函数的正确调用方式。

```python
from vools import curry

@curry
def add(a, b, c):
    return a + b + c

# 如何调用？
```

**解决方案**

柯里化函数支持两种调用方式：

```python
from vools import curry

@curry
def add(a, b, c):
    return a + b + c

# 方式一：逐步调用
result = add(1)(2)(3)  # 返回 6

# 方式二：批量调用
result = add(1, 2, 3)  # 返回 6

# 方式三：混合调用
result = add(1)(2, 3)  # 返回 6

# 部分应用
add5 = add(5)  # 创建部分应用函数
result = add5(2, 3)  # 返回 10
```

**curried 模块**

vools.curried 提供预柯里化的函数式工具：

```python
from vools.curried import map, filter, compose, pipe

# 柯里化调用
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

---

### 2. 立即求值 vs 惰性求值

**问题描述**

不清楚何时使用立即求值版本和惰性求值版本。

**解决方案**

| 场景 | 推荐版本 | 说明 |
|------|----------|------|
| 小数据集 | 立即求值 (`map`, `filter`) | 结果直接可用 |
| 大数据集 | 惰性求值 (`imap`, `ifilter`) | 减少内存占用 |
| 流式处理 | 惰性求值 | 支持增量处理 |

```python
from vools.curried import map, filter, imap, ifilter

# 立即求值 - 返回 list
result = map(lambda x: x * 2, [1, 2, 3])
print(type(result))  # <class 'list'>

# 惰性求值 - 返回迭代器
result = imap(lambda x: x * 2, [1, 2, 3])
print(type(result))  # <class 'map'>
print(list(result))  # [2, 4, 6]

# 大数据集推荐惰性求值
import sys
large_data = range(1000000)

# 惰性处理 - 内存友好
result = imap(lambda x: x * 2, large_data)
for x in result:
    if x > 100:
        break  # 提前终止，节省内存
```

---

### 3. 管道操作报错

**问题描述**

使用管道操作时提示 `TypeError` 或 `NotImplemented`。

```python
# 错误示例
lst = [1, 2, 3]
result = lst | lambda x: x * 2  # TypeError
```

**解决方案**

确保使用正确的管道操作方式：

```python
from vools import Pipe, Ops, P

# 方式一：使用 Pipe 包装
lst = [1, 2, 3]
result = lst | Pipe(lambda x: [i * 2 for i in x])
print(result)  # [2, 4, 6]

# 方式二：使用 Ops 工具类
result = lst | Ops.map(lambda x: x * 2) | Ops.filter(lambda x: x > 2)
print(result)  # [4, 6]

# 方式三：使用 P 包装函数
result = lst | P(lambda x: x * 2)
```

---

### 4. 如何处理占位符冲突

**问题描述**

占位符 `_` 与 Python 内置的 `_`（上次结果）冲突。

**解决方案**

使用明确的导入和命名：

```python
# 方式一：明确导入
from vools.functional.placeholder import _ as placeholder

f = placeholder + 1
result = f(2)  # 3

# 方式二：使用索引占位符
from vools import _1, _2

f = _1 + _2
result = f(1, 2)  # 3

# 方式三：使用 g 函数（字符串表达式）
from vools import g

f = g("_1 + _2")
result = f(1, 2)  # 3
```

---

## 响应式编程问题

### 1. 如何调试响应式数据流

**问题描述**

响应式数据流出现问题，难以定位错误位置。

**解决方案**

使用以下调试技巧：

```python
from vools.reactive import Observable, ops

# 方式一：添加 do 操作符打印中间值
Observable.from_iterable([1, 2, 3]).pipe(
    ops.do(lambda x: print(f"输入: {x}")),
    ops.map(lambda x: x * 2),
    ops.do(lambda x: print(f"映射后: {x}")),
    ops.filter(lambda x: x > 2),
    ops.do(lambda x: print(f"过滤后: {x}"))
).subscribe(on_next=print)

# 方式二：使用 on_error 回调捕获错误
Observable.from_iterable([1, 2, 3]).pipe(
    ops.map(lambda x: x / 0 if x == 2 else x)  # 故意制造错误
).subscribe(
    on_next=lambda x: print(f"值: {x}"),
    on_error=lambda e: print(f"错误: {e}"),
    on_completed=lambda: print("完成")
)

# 方式三：使用 catch 捕获并恢复
Observable.throw(Exception("error")).pipe(
    ops.catch(lambda e: Observable.just("recovered"))
).subscribe(on_next=print)  # 输出: recovered

# 方式四：使用 on_error_return 返回默认值
Observable.throw(Exception("error")).pipe(
    ops.on_error_return("default")
).subscribe(on_next=print)  # 输出: default
```

---

### 2. Subject 使用问题

**问题描述**

Subject 的行为不符合预期，如订阅者没有收到值。

**解决方案**

了解三种 Subject 的区别：

```python
from vools.reactive import Subject, BehaviorSubject, ReplaySubject

# Subject - 基础主题（无初始值，不保留历史）
subject = Subject()
subject.on_next(1)
subject.subscribe(on_next=print)  # 不会收到 1
subject.on_next(2)  # 输出: 2

# BehaviorSubject - 保留最新值（有初始值）
subject = BehaviorSubject(0)  # 默认值
subject.subscribe(on_next=print)  # 立即输出: 0
subject.on_next(1)  # 输出: 1
new_subscriber = subject.subscribe(on_next=print)  # 输出: 1（最新值）

# ReplaySubject - 重放历史值
subject = ReplaySubject(2)  # 保留最近 2 个值
subject.on_next(1)
subject.on_next(2)
subject.on_next(3)
subject.subscribe(on_next=print)  # 输出: 2, 3
```

---

### 3. 表达式字符串解析问题

**问题描述**

使用字符串表达式作为操作符参数时无法正确解析。

```python
# 错误示例
Observable.from_iterable([1, 2, 3]).pipe(
    ops.map("x * 2")  # 可能无法正确解析
).subscribe(print)
```

**解决方案**

确保表达式格式正确：

```python
from vools.reactive import Observable, ops

# 正确格式一：使用变量名
Observable.from_iterable([1, 2, 3]).pipe(
    ops.map("x * 2")  # x 表示输入值
).subscribe(print)  # 2, 4, 6

# 正确格式二：使用占位符
Observable.from_iterable([1, 2, 3]).pipe(
    ops.filter("_ > 1")  # _ 表示输入值
).subscribe(print)  # 2, 3

# 推荐方式：使用 lambda（更明确）
Observable.from_iterable([1, 2, 3]).pipe(
    ops.map(lambda x: x * 2),
    ops.filter(lambda x: x > 1)
).subscribe(print)
```

---

### 4. PipeBuilder 缓存问题

**问题描述**

多次调用 PipeBuilder 导致订阅了不同的 Observable 实例。

**解决方案**

v0.1.16 已修复此问题，确保使用最新版本：

```python
from vools.reactive import Observable, ops

# v0.1.16+ 已修复缓存问题
builder = Observable.from_iterable([1, 2, 3]).p()
builder.map(lambda x: x * 2)

# 多次调用返回相同实例
sub1 = builder.subscribe(on_next=print)
sub2 = builder.subscribe(on_next=print)
# 两个订阅者订阅的是同一个 Observable
```

---

### 5. 监控模块后端选择

**问题描述**

不清楚应该使用哪个监控后端。

**解决方案**

根据平台选择合适的后端：

```python
from vools.reactive import KeyboardDispatcher, MouseDispatcher

# 自动选择最佳后端（推荐）
kd = KeyboardDispatcher(backend="auto")

# Windows 平台 - 使用原生钩子（低延迟）
kd = KeyboardDispatcher(backend="win32")

# 跨平台兼容 - 使用轮询模式
kd = KeyboardDispatcher(backend="polling")

# 后端对比
# | 模块 | Windows | macOS | Linux |
# |------|---------|-------|-------|
# | 键盘 | win32 钩子 | polling | polling |
# | 鼠标 | win32 钩子 | polling | polling |
# | 剪贴板 | Hook | polling | polling |
# | 文件 | ReadDirectoryChangesW | FSEvents | inotify |
```

---

### 6. 自我过滤机制

**问题描述**

监控模块触发自身写入的事件，导致循环触发。

**解决方案**

使用 `filter_self=True` 参数：

```python
from vools.reactive import ClipSubject, write_to_clipboard

# 启用自我过滤
cs = ClipSubject(filter_self=True)

# 写入操作不会触发自己的监控
cs.set_text("test")  # 不会触发 on_next

# 订阅者只会收到外部写入的事件
cs.subscribe(on_next=lambda d: print(f"外部写入: {d.content}"))
```

---

## 迁移指南

### 从 v0.1.14 迁移到 v0.1.15

**新增功能**

v0.1.15 新增以下模块，无需迁移，直接使用：

- 响应式键鼠监控模块 (`keyboard_mouse.py`)
- 响应式剪贴板监控模块 (`clipboard.py`)
- 响应式文件系统监控模块 (`file_watcher.py`)
- 响应式文件夹监控模块 (`folder_watcher.py`)
- 函数签名缓存模块 (`sig_cache/`)

**兼容性**

- 所有 API 向后兼容
- 支持 Python 3.6+
- Windows / macOS / Linux 全平台支持

---

### 从 v0.1.15 迁移到 v0.1.16

**结构变更**

v0.1.16 对 `vools/reactive` 子包进行了结构重组：

```
vools/reactive/
├── core/          # 基础核心（Observable、Subject、Scheduler）
├── monitoring/    # 监控类（键盘、鼠标、剪贴板、文件、目录）
└── operators/     # 操作符（核心、扩展、统计、监控）
```

**迁移步骤**

1. **更新导入路径**（如果使用了内部模块）：

```python
# 旧版本（v0.1.15）
from vools.reactive.keyboard_mouse import KeyboardDispatcher

# 新版本（v0.1.16）- 推荐使用统一入口
from vools.reactive import KeyboardDispatcher

# 或使用新路径
from vools.reactive.monitoring.keyboard import KeyboardDispatcher
```

2. **删除的文件**：

- `keyboard_mouse.py` 已拆分为 `keyboard.py` 和 `mouse.py`

**兼容性**

- 所有原有 API 通过 `vools.reactive.__init__.py` 导出，保持兼容
- 无需修改现有代码

---

### 弃用功能替代方案

目前 vools 没有弃用的功能。所有 API 保持向后兼容。

---

## 性能优化建议

### 1. 使用惰性求值处理大数据

```python
from vools.curried import imap, ifilter

# 大数据集使用惰性版本
large_data = range(1000000)
result = imap(lambda x: x * 2, large_data)
# 按需处理，节省内存
```

### 2. 使用 persist 缓存耗时计算

```python
from vools import persist

@persist
def expensive_computation(x):
    # 耗时计算...
    return result

# 第二次调用直接返回缓存
```

### 3. 使用 sig_cache 加速签名获取

```python
from vools.sig_cache import get_signature

# 重复调用走缓存，性能提升 100×~2000×
for _ in range(1000):
    sig = get_signature(print)  # O(1) dict 查表
```

### 4. 响应式性能优势

vools.reactive 在性能上显著优于 reactivex：

- 简单操作（map/filter/scan）：快 1.1-3.8x
- 复杂操作（distinct/flat_map/buffer）：快 5-893x
- 总体平均性能比：37.04x

---

## 获取帮助

- **GitHub 仓库**：https://github.com/vicTop-cw/vools
- **问题反馈**：在 GitHub Issues 中提交
- **用户指南**：参考 `USER_GUIDE.md` 和 `guide/` 目录下的文档
- **测试验证**：运行 `python -m pytest tests/ -v` 验证功能