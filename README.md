# vools - Python 函数式编程工具集

[![PyPI version](https://img.shields.io/pypi/v/vools.svg)](https://pypi.org/project/vools/)
[![Python versions](https://img.shields.io/pypi/pyversions/vools.svg)](https://pypi.org/project/vools/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

一个强大的 Python 函数式编程工具集，提供装饰器、函数式编程工具、数据处理工具、响应式编程等。

## 特性

- **装饰器**: memorize、once、lazy、retry、curry、overload 等
- **函数式编程**: Seq、Ops、管道操作、占位符、箭头函数
- **数据处理**: 链式序列操作、列表/文本增强工具
- **响应式编程**: Observable、Subject、丰富的操作符
- **任务调度**: TaskQueue、WorkerPool、DAG 调度器
- **序列化**: 支持 JSON、MsgPack、Pickle 等多种格式
- **编码/加密**: Base64、URL 编码、哈希函数

## 安装

```bash
pip install vools
```

或从源码安装：

```bash
git clone https://github.com/vicTop-cw/vools.git
cd vools
pip install .
```

### 环境要求

- Python 3.9+

### 依赖

- `wrapt >= 1.14`
- `attrs >= 22.1`

## 快速开始

### 装饰器

```python
from vools import memorize, once, retry, overload

# 缓存装饰器
@memorize(duration=60)
def expensive_function(x):
    return x ** 2

# 只执行一次
@once
def initialize():
    return 42

# 重试装饰器
@retry(times=3, delay=1)
def risky_operation():
    pass

# 函数重载
@overload
def process(x: int) -> int:
    return x * 2

@process.register
def process(x: str) -> str:
    return x.upper()
```

### 函数式编程

```python
from vools import Seq, Ops, _, g, iif, pipe

# Seq 链式操作
result = Seq(range(10)).filter(lambda x: x % 2 == 0).map(lambda x: x * 2).collect()
# [0, 4, 8, 12, 16]

# Ops 管道操作
result = range(10) | Ops.filter(lambda x: x > 3) | Ops.map(lambda x: x * 2) | Ops.sum()
# 84

# 占位符
f = _ + 1
print(f(2))  # 3

# 箭头函数
f = g("x, y => x + y")
print(f(3, 4))  # 7

# 条件表达式
result = iif(True, "yes", "no")  # "yes"
```

### 柯里化

```python
from vools import curry, stuff

@curry
def add(a, b, c):
    return a + b + c

print(add(1)(2)(3))  # 6

@stuff
def multiply(a, b):
    return a * b

result = multiply(2)(3)()
print(result)  # 6
```

### 响应式编程

```python
from vools import Observable

# 创建 Observable
obs = Observable.from_iterable([1, 2, 3, 4, 5])

# 链式操作符
result = []
obs.pipe(
    Ops.filter(lambda x: x % 2 == 0),
    Ops.map(lambda x: x * 2),
    Ops.take(2)
).subscribe(lambda x: result.append(x))

print(result)  # [4, 8]
```

## 项目结构

```
vools/
├── cache/           # 缓存装饰器
│   ├── memorize     # 时间缓存
│   ├── once         # 单次执行
│   ├── persist      # 持久化缓存
│   └── sigcache     # 签名缓存
├── core/            # 核心模块
├── crypto/          # 加密模块
├── curried/         # 柯里化函数库
│   ├── collection   # 集合操作
│   ├── composition  # 函数组合
│   ├── iteration    # 迭代操作
│   ├── math         # 数学运算
│   ├── predicate    # 谓词函数
│   └── string       # 字符串操作
├── data/            # 数据处理
│   ├── seq          # Seq 序列操作
│   ├── vlist        # VList 增强列表
│   └── vtext        # VText 增强文本
├── datetime/        # 日期时间工具
├── decorators/      # 装饰器
├── encoding/        # 编码解码
├── functional/      # 函数式工具
│   ├── box          # Box 包装器
│   ├── pipe_ops     # 管道操作符
│   ├── placeholder  # 占位符
│   └── result       # Result 类型
├── oop/             # OOP 工具
├── reactive/        # 响应式编程
│   ├── core         # Observable、Subject
│   ├── monitoring   # 系统监控
│   └── operators    # 操作符
├── recorder/        # 录制回放
├── security/        # 安全模块
├── serialize/       # 序列化
├── task/           # 任务调度
└── utils/          # 通用工具
```

## API 概览

### 装饰器

| 装饰器 | 说明 |
|--------|------|
| `memorize(duration=N)` | 时间缓存 |
| `once()` | 单次执行 |
| `lazy()` | 延迟执行 |
| `repeat(cnt, delay)` | 重复执行 |
| `retry(times, delay)` | 失败重试 |
| `curry()` | 柯里化 |
| `overload()` | 函数重载 |
| `stuff()` | 分步柯里化 |

### 函数式工具

| 工具 | 说明 |
|------|------|
| `Seq(iterable)` | 链式序列操作 |
| `Ops` | 管道操作符 |
| `P(func)` | 管道函数包装 |
| `_`, `_1`, `_2`, `_3` | 占位符 |
| `g("x, y => ...")` | 箭头函数 |
| `iif(cond, t, f)` | 条件表达式 |
| `Box(obj)` | 对象包装器 |

### 数据类型

| 类型 | 说明 |
|------|------|
| `VList(list)` | 增强列表 |
| `VText(str)` | 增强文本 |
| `VDate` | 日期处理 |

### 响应式

| 类型 | 说明 |
|------|------|
| `Observable` | 可观察对象 |
| `Subject` | 主题 |
| `BehaviorSubject` | 行为主题 |
| `ReplaySubject` | 回放主题 |

## 详细文档

- [用户指南](USER_GUIDE.md)
- [快速入门](docs/quickstart.md)
- [函数式编程](docs/functional.md)
- [响应式编程](docs/reactive.md)
- [装饰器](docs/decorators.md)

## 更新日志

详细的版本更新记录请查看 [changelog](changelog/) 目录。

## 贡献

欢迎提交 Issue 和 Pull Request！

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 打开 Pull Request

## 许可证

Apache License 2.0 - 详见 [LICENSE](LICENSE) 文件

## 联系方式

- 作者: Victor
- 邮箱: victortop921129@gmail.com
- 项目: https://github.com/vicTop-cw/vools
