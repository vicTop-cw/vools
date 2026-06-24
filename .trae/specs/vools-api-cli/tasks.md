# Tasks

## vools-api-cli 子包

- [x] Task 1: 创建 vools/api 目录结构和基础文件
  - [x] SubTask 1.1: 创建 `vools/api/__init__.py`
  - [x] SubTask 1.2: 创建 `vools/api/typer_app.py` (Typer 应用实例)
  - [x] SubTask 1.3: 在 `pyproject.toml` 添加 typer 可选依赖

- [x] Task 2: 实现 seq 命令
  - [x] SubTask 2.1: 创建 `vools/api/seq_cmd.py`
  - [x] SubTask 2.2: 实现 `--from-range`、`--from-list` 参数
  - [x] SubTask 2.3: 实现 `--filter`、`--map`、`--collect` 操作
  - [x] SubTask 2.4: 集成 vools.Seq 功能

- [x] Task 3: 实现 ops 命令
  - [x] SubTask 3.1: 创建 `vools/api/ops_cmd.py`
  - [x] SubTask 3.2: 实现 `--pipe` 参数
  - [x] SubTask 3.3: 实现管道操作链
  - [x] SubTask 3.4: 集成 vools.Ops 功能

- [x] Task 4: 实现 curry 命令
  - [x] SubTask 4.1: 创建 `vools/api/curry_cmd.py`
  - [x] SubTask 4.2: 实现 `--func`、`--args` 参数
  - [x] SubTask 4.3: 支持多参数 curry 调用

- [x] Task 5: 实现 memoize 命令
  - [x] SubTask 5.1: 创建 `vools/api/memoize_cmd.py`
  - [x] SubTask 5.2: 实现 `--func`、`--args`、`--repeat` 参数
  - [x] SubTask 5.3: 显示缓存命中/未命中信息

- [x] Task 6: 更新 vools/__main__.py 集成 api 子命令
  - [x] SubTask 6.1: 导入 api CLI 组
  - [x] SubTask 6.2: 注册为 `vools api` 子命令

- [x] Task 7: 编写集成测试
  - [x] SubTask 7.1: 测试 `vools api seq` 命令
  - [x] SubTask 7.2: 测试 `vools api ops` 命令
  - [x] SubTask 7.3: 测试 `vools api curry` 命令
  - [x] SubTask 7.4: 测试 `vools api memoize` 命令

## Task Dependencies
- Task 6 依赖 Task 1-5 完成
- Task 7 依赖 Task 6 完成
