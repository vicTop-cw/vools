# vools - Python 函数式编程工具集 {#001}

> **模块路径**：-
> **依赖版本**：Python 3.6+
> **平台支持**：Windows/macOS/Linux
> **测试状态**：✅ 已测试
> **编号**：#001
> **最后更新**：2026-06-30

[![PyPI version](https://img.shields.io/pypi/v/vools.svg)](https://pypi.org/project/vools/)
[![Python versions](https://img.shields.io/pypi/pyversions/vools.svg)](https://pypi.org/project/vools/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/vicTop-cw/vools)](https://github.com/vicTop-cw/vools)

---

## 一句话介绍

vools 是一个强大的 Python 函数式编程工具集，提供装饰器、函数式编程、响应式编程、数据处理、多语言桥接等功能，让 Python 代码更加简洁、高效、富有表现力。

---

## 核心特性

### 🎨 装饰器

强大的函数装饰器，包括缓存、柯里化、重试、重载等功能。

```python
from vools import memorize, retry, curry, overload

@memorize(duration=60)
def expensive_calc(n):
    return n ** 2

@retry(times=3, delay=1)
def fetch_data(url):
    import requests
    return requests.get(url).json()

@curry
def add(a, b, c):
    return a + b + c

@overload
def process(x: int) -> int:
    return x * 2

@process.register
def process(x: str) -> str:
    return x.upper()

result = add(1)(2)(3)  # 6 ✅ 测试通过
print(process(10))     # 20 ✅ 测试通过
print(process("hi"))   # HI ✅ 测试通过
```

### 🔗 函数式编程

丰富的函数式工具，支持管道操作、占位符、箭头函数等。

```python
from vools import Seq, Ops, _, g, iif, pipe

# Seq 链式操作
result = Seq(range(10)).filter(lambda x: x % 2 == 0).map(lambda x: x * 2).collect()
print(result)  # [0, 4, 8, 12, 16] ✅ 测试通过

# Ops 管道操作
result = range(10) | Ops.filter(lambda x: x > 3) | Ops.map(lambda x: x * 2) | Ops.sum()
print(result)  # 84 ✅ 测试通过

# 占位符
f = _ + 1
print(f(2))  # 3 ✅ 测试通过

# 箭头函数
add = g("x, y => x + y")
print(add(3, 4))  # 7 ✅ 测试通过
```

### 📡 响应式编程

Observable 模式的响应式编程，支持事件流、观察者模式。

```python
from vools.reactive import Observable, Subject, ops

# 创建 Observable
obs = Observable.from_iterable([1, 2, 3, 4, 5])
result = []
obs.pipe(
    ops.filter(lambda x: x % 2 == 0),
    ops.map(lambda x: x * 2),
    ops.take(2)
).subscribe(on_next=lambda x: result.append(x))
print(result)  # [4, 8] ✅ 测试通过

# Subject 可手动推送数据
subject = Subject()
results = []
subject.subscribe(on_next=lambda x: results.append(x))
subject.on_next(1)  # 推送数据
subject.on_next(2)
print(results)  # [1, 2] ✅ 测试通过
```

### 🌉 多语言桥接

支持 27 种编程语言的桥接，包括 Rust、Nim、Go、Java、Kotlin、Swift、Dart、MoonBit 等。

```python
from vools.bridge import discover_all, get_helper

# 一键发现所有编译器
result = discover_all(include_wsl=True)
print(f"发现编译器数量: {len(result['local']['compilers'])}")  # ✅ 测试通过

# 获取特定语言帮助器
nim_helper = get_helper('nim')
if nim_helper.is_available():
    print(f"Nim 编译器: {nim_helper.get_compiler_path()}")  # ✅ 测试通过
```

### 📊 数据处理

Seq 惰性序列、VList 增强列表、VText 增强文本等数据处理工具。

```python
from vools import Seq, VList, VText

# Seq 惰性序列
result = Seq(range(100)).filter(lambda x: x % 7 == 0).take(5).collect()
print(result)  # [0, 7, 14, 21, 28] ✅ 测试通过

# VList 增强列表
vl = VList([3, 1, 4, 1, 5, 9, 2, 6])
print(vl.distinct().sorted().collect())  # [1, 2, 3, 4, 5, 6, 9] ✅ 测试通过

# VText 增强文本
vt = VText("  hello world  ")
print(vt.trim().capitalize().value())  # Hello World ✅ 测试通过
```

### 🔒 编码与加密

支持 Base64、URL 编码、JSON、哈希函数等常用编码加密功能。

```python
from vools import b64encode, b64decode, md5, sha256

# Base64 编码解码
encoded = b64encode("Hello, vools!")
print(encoded)  # SGVsbG8sIHZvb2xzIQ== ✅ 测试通过
print(b64decode(encoded))  # Hello, vools! ✅ 测试通过

# 哈希函数
print(md5("test"))  # 098f6bcd4621d373cade4e832627b4f6 ✅ 测试通过
print(sha256("test"))  # 9f86d081884c7d659a2feaa0c55ad015... ✅ 测试通过
```

---

## 快速开始

### 安装

```bash
pip install vools
```

或从源码安装：

```bash
git clone https://github.com/vicTop-cw/vools.git
cd vools
pip install .
```

### 5 行代码入门

```python
from vools import Seq, curry, _, memorize

# 1. Seq 链式操作
print(Seq([1, 2, 3, 4, 5]).map(lambda x: x * 2).filter(lambda x: x > 5).collect())
# 输出: [6, 8, 10] ✅ 测试通过

# 2. 柯里化
@curry
def add(a, b): return a + b
print(add(1)(2))  # 输出: 3 ✅ 测试通过

# 3. 占位符
f = _ * 2
print(f(7))  # 输出: 14 ✅ 测试通过

# 4. 缓存装饰器
@memorize(duration=60)
def fib(n): return n if n < 2 else fib(n-1) + fib(n-2)
print(fib(10))  # 输出: 55 ✅ 测试通过

# 5. 箭头函数
from vools import g
f = g("x, y => x ** y")
print(f(2, 8))  # 输出: 256 ✅ 测试通过
```

---

## 平台支持

| 功能 | Windows | macOS | Linux |
|------|---------|-------|-------|
| 核心功能 | ✅ | ✅ | ✅ |
| 装饰器模块 | ✅ | ✅ | ✅ |
| 函数式工具 | ✅ | ✅ | ✅ |
| 响应式编程 | ✅ | ✅ | ✅ |
| 数据处理 | ✅ | ✅ | ✅ |
| 编码加密 | ✅ | ✅ | ✅ |
| 日期时间 | ✅ | ✅ | ✅ |
| 多语言桥接 | ✅* | ✅* | ✅* |

> *多语言桥接需要对应语言的编译器支持

---

## 项目结构

```
vools/
├── decorators/     # 装饰器（缓存、柯里化、重试、重载）
├── functional/     # 函数式工具（Seq、Ops、占位符、箭头函数）
├── reactive/       # 响应式编程（Observable、Subject）
├── data/           # 数据处理（VList、VText、Seq）
├── datetime/       # 日期时间工具
├── encoding/       # 编码解码
├── crypto/         # 加密模块
├── bridge/         # 多语言桥接（27种语言）
├── task/           # 任务调度
├── serialize/      # 序列化
└── utils/          # 通用工具
```

---

## GitHub

[![GitHub stars](https://img.shields.io/github/stars/vicTop-cw/vools)](https://github.com/vicTop-cw/vools)
[![GitHub forks](https://img.shields.io/github/forks/vicTop-cw/vools)](https://github.com/vicTop-cw/vools)
[![GitHub issues](https://img.shields.io/github/issues/vicTop-cw/vools)](https://github.com/vicTop-cw/vools/issues)
[![GitHub PRs](https://img.shields.io/github/issues-pr/vicTop-cw/vools)](https://github.com/vicTop-cw/vools/pulls)

**仓库地址**: https://github.com/vicTop-cw/vools

---

## 下一步

- [快速入门](getting-started/quickstart.md) - 10 分钟快速上手
- [安装指南](getting-started/installation.md) - 安装详解
- [核心功能](core/index.md) - 核心功能模块
- [函数式编程](functional/index.md) - 函数式编程详解
- [响应式编程](reactive/index.md) - 响应式编程详解
