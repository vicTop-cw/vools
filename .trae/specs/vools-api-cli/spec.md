# Vools API CLI Spec

## Why
将 vools 函数式编程工具集的 API 以命令行方式暴露，方便在终端快速使用库的核心功能（如 Seq、Ops、装饰器测试），无需编写 Python 代码。

## What Changes
- 新增 `vools.api` 子包，提供 CLI 化的 API 访问
- 使用 **Typer** 作为 CLI 框架（支持类型提示、自动补全）
- 命令行调用示例：`vools seq --from-range 10 --filter "x % 2 == 0" --map "x * 2"`
- **BREAKING**: 无

## Impact
- Affected specs: 无
- Affected code: 新增 `vools/api/` 目录

## ADDED Requirements

### Requirement: CLI 入口
系统 SHALL 提供 `vools api` 子命令作为入口

#### Scenario: 查看帮助
- **WHEN** 用户执行 `vools api --help`
- **THEN** 显示可用子命令列表

### Requirement: Seq 命令
系统 SHALL 提供 `vools api seq` 命令用于序列操作

#### Scenario: 基础序列操作
- **WHEN** 用户执行 `vools seq --from-range 10 --filter "lambda x: x % 2 == 0"`
- **THEN** 输出 `[0, 2, 4, 6, 8]`

#### Scenario: 链式操作
- **WHEN** 用户执行 `vools seq --from-list 1 2 3 4 5 --map "x * 2" --filter "x > 4" --collect`
- **THEN** 输出 `[6, 8, 10]`

### Requirement: Ops 命令
系统 SHALL 提供 `vools ops` 命令用于函数式管道操作

#### Scenario: 管道操作
- **WHEN** 用户执行 `vools ops --pipe "range(10)" --filter "x % 2 == 0" --map "x * 2" --sum`
- **THEN** 输出 `80`

### Requirement: Curry 装饰器测试
系统 SHALL 提供 `vools curry` 命令用于测试 curry 装饰器

#### Scenario: 测试 curry 函数
- **WHEN** 用户执行 `vools curry --func "def add(a, b): return a + b" --args 1 --args 2`
- **THEN** 输出 `3`

### Requirement: Memoize 缓存测试
系统 SHALL 提供 `vools memoize` 命令用于测试 memorize 装饰器

#### Scenario: 测试缓存
- **WHEN** 用户执行 `vools memoize --func "def heavy(x): return x**2" --args 5 --repeat 2`
- **THEN** 显示缓存命中信息

## Architecture

### 目录结构
```
vools/api/
  __init__.py      # 导出 api CLI 组
  typer_app.py     # Typer 应用实例
  seq_cmd.py       # seq 子命令
  ops_cmd.py       # ops 子命令
  curry_cmd.py     # curry 子命令
  memoize_cmd.py   # memoize 子命令
```

### 依赖
- `typer>=0.9.0` (可选依赖，CLI 专用)

## Library Choice
| 库 | 优点 | 缺点 |
|----|------|------|
| **Typer** | 类型提示、自动补全、装饰器风格 | 依赖 click |
| Fire | 自动生成 CLI、简单 | 无类型提示 |
| docopt | 文档驱动 | 较老 |
