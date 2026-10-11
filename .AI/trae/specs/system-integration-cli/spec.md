# System Integration CLI Spec

## Why
提供命令行工具调用系统中已安装的程序（如编译器、解释器、DLL），以及 vools 内置的 Nim 加速模块，实现跨语言集成和工作流自动化。

## What Changes
- 新增 `vools.sys` 子包，提供系统命令调用能力
- 使用 **Fire** 作为 CLI 框架（自动从类/函数生成 CLI）
- 命令示例：
  - `vools sys run --dll vools_crypto --func md5 --args "hello"`
  - `vools sys compile --lang nim --file algo.nim --output algo.dll`
  - `vools sys dll --list` 查看可用 DLL
- **BREAKING**: 无

## Impact
- Affected specs: 无
- Affected code: 新增 `vools/sys/` 目录

## ADDED Requirements

### Requirement: CLI 入口
系统 SHALL 提供 `vools sys` 子命令作为入口

#### Scenario: 查看帮助
- **WHEN** 用户执行 `vools sys --help`
- **THEN** 显示可用子命令列表

### Requirement: DLL 管理
系统 SHALL 提供 `vools sys dll` 命令管理动态库

#### Scenario: 列出可用 DLL
- **WHEN** 用户执行 `vools sys dll --list`
- **THEN** 显示 vools 可用的 Nim 加速 DLL 列表

#### Scenario: 调用 DLL 函数
- **WHEN** 用户执行 `vools sys dll --dll vools_crypto --func md5 --args "hello"`
- **THEN** 输出 md5 哈希结果

### Requirement: 编译器调用
系统 SHALL 提供 `vools sys compile` 命令调用语言编译器

#### Scenario: 编译 Nim 文件
- **WHEN** 用户执行 `vools sys compile --lang nim --file algo.nim --output algo.dll`
- **THEN** 调用 Nim 编译器生成 DLL

#### Scenario: 编译 C 文件
- **WHEN** 用户执行 `vools sys compile --lang c --file algo.c --output algo.dll`
- **THEN** 调用 C 编译器生成 DLL

### Requirement: 程序执行
系统 SHALL 提供 `vools sys run` 命令执行外部程序

#### Scenario: 执行 Python 脚本
- **WHEN** 用户执行 `vools sys run --python script.py --args "--help"`
- **THEN** 执行 Python 脚本

#### Scenario: 执行系统命令
- **WHEN** 用户执行 `vools sys run --shell "dir"`
- **THEN** 在系统 shell 中执行命令

### Requirement: 环境探测
系统 SHALL 提供 `vools sys env` 命令查看系统环境

#### Scenario: 查看 PATH
- **WHEN** 用户执行 `vools sys env --path`
- **THEN** 显示系统 PATH 环境变量

#### Scenario: 查看 Python 信息
- **WHEN** 用户执行 `vools sys env --python`
- **THEN** 显示 Python 版本和路径

## Architecture

### 目录结构
```
vools/sys/
  __init__.py      # 导出 sys CLI 组
  fire_app.py      # Fire 应用实例
  dll_cmd.py       # dll 子命令
  compile_cmd.py   # compile 子命令
  run_cmd.py       # run 子命令
  env_cmd.py       # env 子命令
```

### 依赖
- `fire>=0.5.0` (可选依赖，CLI 专用)

## Library Choice
| 库 | 优点 | 缺点 |
|----|------|------|
| Typer | 类型提示、自动补全 | 需要额外定义命令 |
| **Fire** | 自动从类/函数生成 CLI、极简 | 无类型提示 |
| docopt | 文档驱动 | 较老 |
