# Tasks

## system-integration-cli 子包

- [x] Task 1: 创建 vools/sys 目录结构和基础文件
  - [x] SubTask 1.1: 创建 `vools/sys/__init__.py`
  - [x] SubTask 1.2: 创建 `vools/sys/fire_app.py` (Fire 应用实例)
  - [x] SubTask 1.3: 在 `pyproject.toml` 添加 fire 可选依赖

- [x] Task 2: 实现 dll 命令
  - [x] SubTask 2.1: 创建 `vools/sys/dll_cmd.py`
  - [x] SubTask 2.2: 实现 `--list` 列出可用 DLL
  - [x] SubTask 2.3: 实现 `--dll`、`--func`、`--args` 调用 DLL 函数
  - [x] SubTask 2.4: 复用 vools.bridge.nim 的 DLL 加载机制

- [x] Task 3: 实现 compile 命令
  - [x] SubTask 3.1: 创建 `vools/sys/compile_cmd.py`
  - [x] SubTask 3.2: 实现 `--lang` 参数支持 nim/c
  - [x] SubTask 3.3: 实现 `--file`、`--output` 参数
  - [x] SubTask 3.4: 调用对应编译器

- [x] Task 4: 实现 run 命令
  - [x] SubTask 4.1: 创建 `vools/sys/run_cmd.py`
  - [x] SubTask 4.2: 实现 `--python` 执行 Python 脚本
  - [x] SubTask 4.3: 实现 `--shell` 执行系统命令
  - [x] SubTask 4.4: 实现 `--args` 传递参数

- [x] Task 5: 实现 env 命令
  - [x] SubTask 5.1: 创建 `vools/sys/env_cmd.py`
  - [x] SubTask 5.2: 实现 `--path` 显示 PATH 环境变量
  - [x] SubTask 5.3: 实现 `--python` 显示 Python 信息
  - [x] SubTask 5.4: 实现 `--nim` 显示 Nim 信息（若已安装）

- [x] Task 6: 更新 vools/__main__.py 集成 sys 子命令
  - [x] SubTask 6.1: 导入 sys CLI 组
  - [x] SubTask 6.2: 注册为 `vools sys` 子命令

- [x] Task 7: 编写集成测试
  - [x] SubTask 7.1: 测试 `vools sys dll --list` 命令
  - [x] SubTask 7.2: 测试 `vools sys compile --lang nim` 命令
  - [x] SubTask 7.3: 测试 `vools sys run --shell` 命令
  - [x] SubTask 7.4: 测试 `vools sys env` 命令

## Task Dependencies
- Task 6 依赖 Task 1-5 完成
- Task 7 依赖 Task 6 完成
