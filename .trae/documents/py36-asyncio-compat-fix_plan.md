# Python 3.6 asyncio 兼容性修复计划

## 概述
修复 vools 项目在 Python 3.6 环境下的 asyncio 兼容性问题，将 `asyncio.create_task()` 和 `asyncio.get_running_loop()` 替换为兼容层实现。

## 背景
- Python 3.6 没有 `asyncio.create_task()`（3.7+ 引入），需用 `asyncio.ensure_future()` 替代
- Python 3.6 没有 `asyncio.get_running_loop()`（3.7+ 引入），需用 `asyncio._get_running_loop()` 替代
- 项目已有兼容层 `vools.core.asyncio_compat`，提供了统一接口

## 检查结果

### 需要修改的文件
1. **vools/reactive/operators/extended_operators.py** - 6 处 `asyncio.create_task(`
2. **vools/reactive/operators/operators.py** - 2 处 `asyncio.create_task(`

### 无需修改的文件
3. **vools/reactive/core/observable.py** - 未发现 `asyncio.get_running_loop(` 使用
4. **vools/reactive/core/schedulers.py** - 未发现 `asyncio.get_running_loop(` 使用

## 修改方案

### 1. extended_operators.py
- 在 `import asyncio` 之后添加导入：
  ```python
  from vools.core.asyncio_compat import create_task as _asyncio_create_task
  ```
- 将所有 6 处 `asyncio.create_task(` 替换为 `_asyncio_create_task(`

### 2. operators.py
- 在 `import asyncio` 之后添加导入：
  ```python
  from vools.core.asyncio_compat import create_task as _asyncio_create_task
  ```
- 将所有 2 处 `asyncio.create_task(` 替换为 `_asyncio_create_task(`

### 3. observable.py
- 无需修改（未使用 `asyncio.get_running_loop(`）

### 4. schedulers.py
- 无需修改（未使用 `asyncio.get_running_loop(`）

## 验证
使用 Python 3.6 虚拟环境验证导入：
```bash
e:\py36-venv\Scripts\python.exe -c "import vools.reactive"
```

## 修改文件列表
- `vools/reactive/operators/extended_operators.py`
- `vools/reactive/operators/operators.py`
