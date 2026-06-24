# Tasks: Project Optimization v1

- [ ] Task 1: 统一 Result 类型
  - [ ] SubTask 1.1: 将 `vools/task/utils/__init__.py` 中的 Result 改为 re-export `vools.functional.Result`
  - [ ] SubTask 1.2: 确保 `vools.functional.Result` 包含 `task/utils` 版本的所有方法（`get_or`, `get_or_raise`, `flat_map`）
  - [ ] SubTask 1.3: 验证 `from vools.task.utils import Result` 与 `from vools.functional import Result` 是同一类型

- [ ] Task 2: 消除柯里化函数重复
  - [ ] SubTask 2.1: 将 `vools/decorators/curried.py` 改为 re-export `vools/curried/` 子包中的函数
  - [ ] SubTask 2.2: 确保 `from vools.decorators import add, mul, identity, compose, pipe` 等向后兼容
  - [ ] SubTask 2.3: 验证测试通过

- [ ] Task 3: Ops 管道操作惰性求值
  - [ ] SubTask 3.1: 修改 `Ops.take(n)` 返回生成器而非列表
  - [ ] SubTask 3.2: 修改 `Ops.drop(n)` 返回生成器而非列表
  - [ ] SubTask 3.3: 修改 `Ops.distinct()` 使用生成器逐步产出
  - [ ] SubTask 3.4: 验证 `range(1000000) | Ops.take(5) | Ops.as_list` 内存效率

- [ ] Task 4: Monitoring 模块条件导入
  - [ ] SubTask 4.1: 修改 `vools/reactive/__init__.py`，将 monitoring 导入包裹在 try/except 中
  - [ ] SubTask 4.2: 添加 `MONITORING_AVAILABLE` 标志
  - [ ] SubTask 4.3: 验证 `from vools.reactive import Observable` 跨平台可用

- [ ] Task 5: `__slots__` 内存优化
  - [ ] SubTask 5.1: 为 `Pipe` 类添加 `__slots__`
  - [ ] SubTask 5.2: 为 `P` 类添加 `__slots__`
  - [ ] SubTask 5.3: 验证不影响现有功能（属性赋值、pickle 等）

- [ ] Task 6: 清理 Wildcard Imports
  - [ ] SubTask 6.1: 替换 `functional/__init__.py` 中的 `from .placeholder import *` 为显式导入
  - [ ] SubTask 6.2: 替换 `oop/__init__.py` 中的 `from .extend import *` 等为显式导入
  - [ ] SubTask 6.3: 更新 `__all__` 列表确保完整

- [ ] Task 7: 清理 `__init__.py` hacky 模式
  - [ ] SubTask 7.1: 移除 `vools/__init__.py` 中的 `for name in __all__: globals()[name] = None`
  - [ ] SubTask 7.2: 验证 `import vools` 和 `dir(vools)` 正常

- [ ] Task 8: 消除 `result.py` 中的 `do()` 重复代码
  - [ ] SubTask 8.1: 从 `Success` 和 `Failure` 类中移除重复的 `do()` 方法
  - [ ] SubTask 8.2: 确保 `do()` 仅定义在 `Result` 基类中

- [ ] Task 9: 运行测试验证
  - [ ] SubTask 9.1: 运行 `pytest tests/ -m "not integration and not windows_only"` 确保全部通过
  - [ ] SubTask 9.2: 修复任何因优化引入的回归

# Task Dependencies
- Task 1 和 Task 2 独立，可并行
- Task 3 独立，可并行
- Task 4 独立，可并行
- Task 5 依赖 Task 3（修改同一个 `functional/__init__.py`）
- Task 6 独立，可并行
- Task 7 独立，可并行
- Task 8 独立，可并行
- Task 9 依赖所有任务完成