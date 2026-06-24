# vools.api — API 命令行工具

`vools.api` 是 vools 库的命令行接口子包，基于 Typer 框架构建，提供函数式编程相关操作的 CLI 工具，包括序列操作、管道操作、函数柯里化和函数记忆化等功能。

---

## 目录

- [子包概述](#子包概述)
- [子命令说明](#子命令说明)
- [快速开始](#快速开始)
- [API 速查](#api-速查)

---

## 子包概述

`vools.api` 提供以下核心子命令：

- **`seq`** — Seq 序列操作（range、filter、map、collect 等）
- **`ops`** — Ops 管道操作（pipe、filter、map、sum、min、max 等）
- **`curry`** — 函数柯里化操作
- **`memoize`** — 函数记忆化与性能基准测试

### 设计理念

- **声明式接口**：通过子命令和选项组织功能，符合 CLI 使用习惯
- **类型安全**：基于 Typer 的类型注解自动生成参数解析和帮助信息
- **灵活输入**：支持 lambda 表达式字符串作为操作函数
- **实用工具**：提供性能测量、缓存效果展示等实用功能

---

## 子命令说明

### seq - 序列操作

基于 `vools.data.Seq` 的惰性序列操作命令。

**可用命令：**

| 命令 | 说明 |
|------|------|
| `from-range` | 从范围创建序列 |
| `from-list` | 从列表创建序列 |
| `filter-cmd` | 过滤序列元素 |
| `map-cmd` | 映射序列元素 |
| `collect-cmd` | 收集序列为列表 |

**常用选项：**

| 选项 | 说明 |
|------|------|
| `--filter, -f` | 过滤表达式（lambda） |
| `--map, -m` | 映射表达式（lambda） |
| `--limit, -l` | 限制结果数量 |
| `--collect/--no-collect` | 是否立即收集结果 |

**示例：**

```bash
# 生成 0-9 的序列，过滤偶数，平方后收集
vools api seq from-range 10 --filter "lambda x: x % 2 == 0" --map "lambda x: x ** 2" --collect

# 从列表创建序列
vools api seq from-list 1 2 3 4 5 --map "lambda x: x * 2" --collect
```

---

### ops - 管道操作

基于 `vools.functional.Ops` 的管道操作命令，使用 `|` 运算符进行链式操作。

**可用命令：**

| 命令 | 说明 |
|------|------|
| `pipe` | 管道操作（支持多种聚合操作） |
| `filter-op` | 管道过滤操作 |
| `map-op` | 管道映射操作 |
| `sum-op` | 管道求和操作 |

**常用选项：**

| 选项 | 说明 |
|------|------|
| `--filter, -f` | 过滤表达式（lambda） |
| `--map, -m` | 映射表达式（lambda） |
| `--sum/--no-sum` | 求和操作 |
| `--min/--no-min` | 最小值操作 |
| `--max/--no-max` | 最大值操作 |
| `--count/--no-count` | 计数操作 |
| `--collect/--no-collect` | 收集为列表 |

**示例：**

```bash
# 管道操作：过滤偶数 + 映射 + 求和
vools api ops pipe 1 2 3 4 5 6 7 8 9 10 \
    --filter "lambda x: x % 2 == 0" \
    --map "lambda x: x ** 2" \
    --sum

# 简单过滤
vools api ops filter-op 1 2 3 4 5 "lambda x: x > 2"
```

---

### curry - 函数柯里化

基于 `vools.decorators.curry` 的函数柯里化命令。

**可用命令：**

| 命令 | 说明 |
|------|------|
| `call` | 调用柯里化函数 |
| `curry-func` | 将函数柯里化并显示 |

**常用选项：**

| 选项 | 说明 |
|------|------|
| `--kwargs, -k` | 关键字参数（格式：key=value） |

**示例：**

```bash
# 调用柯里化函数
vools api curry call "lambda x, y: x + y" 5 10

# 带关键字参数
vools api curry call "lambda a, b, c: a * b + c" 2 3 --kwargs c=10

# 查看柯里化函数
vools api curry curry-func "lambda x, y, z: x + y + z"
```

---

### memoize - 函数记忆化

基于 `vools.cache.memorize` 的函数记忆化命令，支持性能测量和基准测试。

**可用命令：**

| 命令 | 说明 |
|------|------|
| `call` | 调用记忆化函数并测量性能 |
| `benchmark` | 基准测试记忆化函数 |

**常用选项：**

| 选项 | 说明 |
|------|------|
| `--repeat, -r` | 重复调用次数 |
| `--show-cache/--no-show-cache` | 显示缓存状态 |
| `--iterations, -n` | 基准测试迭代次数 |

**示例：**

```bash
# 调用记忆化函数，重复 5 次观察缓存效果
vools api memoize call "lambda x: x * 2" 5 --repeat 5

# 基准测试
vools api memoize benchmark "lambda x: x ** 2" 100 --iterations 1000
```

---

## 快速开始

### 查看帮助

```bash
# 查看所有子命令
vools api --help

# 查看具体子命令帮助
vools api seq --help
vools api ops --help
vools api curry --help
vools api memoize --help
```

### 显示 API 工具信息

```bash
vools api info
```

### Python 中使用

```python
from vools.api import typer_app, main, info

# 显示信息
info()

# 运行 CLI 应用
typer_app()
```

---

## API 速查

### 顶层导出

```python
from vools.api import typer_app, main, info
```

### 子命令应用实例

```python
from vools.api.seq_cmd import seq_app
from vools.api.ops_cmd import ops_app
from vools.api.curry_cmd import curry_app
from vools.api.memoize_cmd import memoize_app
```

### 核心依赖

| 子命令 | 依赖模块 | 说明 |
|--------|---------|------|
| `seq` | `vools.data.Seq` | 惰性序列 |
| `ops` | `vools.functional.Ops` | 管道操作 |
| `curry` | `vools.decorators.curry` | 函数柯里化 |
| `memoize` | `vools.cache.memorize` | 函数记忆化 |
