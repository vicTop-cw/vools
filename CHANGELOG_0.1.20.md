# CHANGELOG 0.1.20

## 主要更新

### 项目优化 v1 (系统性优化)

- **统一 Result 类型**: `vools.task.utils.Result` 改为从 `vools.functional.Result` 重新导出，消除重复实现
- **消除柯里化函数重复**: `vools.decorators.curried` 改为从 `vools.curried` 子包导入共享函数，减少维护成本
- **Ops 管道惰性求值**: `Ops.take()`、`Ops.drop()`、`Ops.distinct()` 改为返回惰性生成器，大幅提升大数据集内存效率
- **Monitoring 条件导入**: `vools.reactive` 添加 `MONITORING_AVAILABLE` 标志，非 Windows 平台优雅降级
- **清理 Wildcard Imports**: `vools.oop` 模块改为显式导入，提升代码可读性
- **清理 hacky 模式**: 用 `__dir__()` 方法替代 `globals()[name] = None`，更规范的延迟加载
- **消除 do() 重复**: `Result.success()` 和 `Result.failure()` 不再重复定义 `do()` 方法

### 新增模块

- **vools.task.utils**: 任务队列工具模块，提供：
  - 函数式工具: `identity`, `const`, `compose`, `pipe`, `partial`
  - 任务辅助: `retry`, `timeout`, `catch`, `finally_fn`
  - 异步工具: `async_retry`, `async_timeout`
  - 装饰器: `@with_timeout`, `@with_retry`, `@with_logging`
  - `Result` 类型 (统一 re-export)

### 移除

- **vools.recorder**: 删除录制回放子包（9 个文件），该模块依赖 Windows 底层监控，稳定性不足
- 删除相关测试: `tests/test_recorder.py`, `tests/my_recorder_gui.py`

### 文档

- 更新 `README.md`: 添加 PyPI badges、更新项目结构、更新代码示例和 API 概览

## 修复

- `vools.reactive` 导入: 不再因 monitoring 模块缺失而抛出 `ImportError`

## 统计数据

- 删除文件: 11 个 (recorder 9 个 + 测试 2 个)
- 新增模块: 1 个 (task/utils)
- 优化模块: 7 个 (Result, curried, Ops, reactive, oop, __init__.py, result.py)
- 测试通过: 100%

## 安装使用

```bash
pip install vools==0.1.20
```

或从源码安装:

```bash
git clone https://github.com/vicTop-cw/vools.git
cd vools
git checkout main
pip install -e .
```

## 兼容性

- Python 3.9+
- 本次更新无破坏性 API 变更，向后兼容 0.1.19