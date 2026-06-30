# vools - Python 函数式编程工具集

[![PyPI version](https://img.shields.io/pypi/v/vools.svg)](https://pypi.org/project/vools/)
[![Python versions](https://img.shields.io/pypi/pyversions/vools.svg)](https://pypi.org/project/vools/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Documentation](https://img.shields.io/badge/docs-online-brightgreen.svg)](https://victop-cw.github.io/vools/)

📚 **完整文档**: [https://victop-cw.github.io/vools/](https://victop-cw.github.io/vools/)

一个强大的 Python 函数式编程工具集，提供装饰器、函数式编程工具、数据处理工具、响应式编程等。

## 特性

- **装饰器**: memorize、once、lazy、retry、curry、overload 等
- **函数式编程**: Seq、Ops、管道操作、占位符、箭头函数
- **数据处理**: 链式序列操作、列表/文本增强工具
- **响应式编程**: Observable、Subject、丰富的操作符
- **任务调度**: TaskQueue、WorkerPool、DAG 调度器
- **序列化**: 支持 JSON、MsgPack、Pickle 等多种格式
- **编码/加密**: Base64、URL 编码、哈希函数
- **多语言桥接**: 支持 27 种编程语言（Lua、Rust、Go、Java、Kotlin、Swift、Dart、MoonBit 等），统一装饰器接口
- **编译器自动发现**: 自动探测本机和 WSL 环境中的编译器，支持注册表搜索、常见安装路径、通配符路径展开

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

- Python 3.6+

### 依赖

- `attrs >= 22.1` (Python < 3.7 时需要，用于 dataclass 兼容)
- `contextvars` (Python < 3.7 时需要)

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

### 编译器自动发现

自动探测本机和 WSL 环境中所有已安装的编译器，无需手动配置 PATH。

```python
from vools.bridge import discover_all, get_discovery_report, configure_from_discovery

# 一键发现所有编译器（本机 + WSL）
result = discover_all(include_wsl=True)

# 查看格式化报告
print(get_discovery_report())

# 自动配置管理器
configure_from_discovery(include_wsl=True)

# 检查特定语言是否可用
from vools.bridge import get_helper
nim_helper = get_helper('nim')
if nim_helper.is_available():
    print(f"Nim 编译器路径: {nim_helper.get_compiler_path()}")
```

## 项目结构

```
vools/
├── api/             # CLI 命令行接口
├── bridge/          # 多语言桥接（27种语言）+ 编译器自动发现
│   ├── core/        # 桥接核心（类型、签名缓存、装饰器）
│   ├── probe.py     # 编译器探测模块
│   ├── manager.py   # 配置管理模块
│   ├── auto_discovery.py  # 一键发现入口
│   ├── lua/         # Lua 桥接
│   ├── rust/        # Rust 桥接
│   ├── go/          # Go 桥接
│   ├── java/        # Java 桥接
│   ├── kotlin/      # Kotlin 桥接
│   ├── swift/       # Swift 桥接
│   ├── dart/        # Dart 桥接
│   ├── moonbit/     # MoonBit 桥接
│   ├── c/           # C 桥接
│   ├── cpp/         # C++ 桥接
│   └── ...          # 更多语言
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
├── sql/             # SQL 工具
├── sys/             # 系统工具
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
- [性能跃迁计划](docs/performance-leap.md)
- [基准测试](docs/benchmark.md)

## 性能对比

vools 通过桥接 Nim/Rust/Go 等编译型语言，为高频核心函数提供可选的高性能实现。以下是典型硬件上的基准测试结果（实际数据因硬件而异）：

| 模块 | 函数 | 纯 Python | 桥接加速 | 提升倍数 |
|------|------|----------|----------|---------|
| serialize.codec | pickle_encode | ~120 us | ~18 us | 6-8x |
| serialize.codec | pickle_decode | ~100 us | ~15 us | 6-7x |
| security.hash | sha256_hex | ~15 us | ~3 us | 5x |
| security.hash | md5_hex | ~12 us | ~2 us | 6x |
| security.hash | sha1_hex | ~10 us | ~2 us | 5x |
| security.hash | sha512_hex | ~18 us | ~4 us | 4.5x |
| data.seq | base64_encode | ~8 us | ~2 us | 4x |
| data.seq | base64_decode | ~7 us | ~2 us | 3.5x |
| serialize | json_encode | ~50 us | ~15 us | 3x |
| serialize | json_decode | ~45 us | ~12 us | 4x |
| data.seq | zlib_compress | ~500 us | ~100 us | 5x |
| data.seq | zlib_decompress | ~200 us | ~50 us | 4x |
| cache.sigcache | hash_signature | ~50 us | ~8 us | 6x |

**注意**：
- 桥接库为可选增强，未安装时自动使用纯 Python 实现
- 测试数据为 1KB 左右的小数据，大数据量提升更显著
- 详细基准测试方法请参见 [基准测试文档](docs/benchmark.md)

## 更新日志

详细的版本更新记录请查看 [CHANGELOG.md](CHANGELOG.md)。

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
