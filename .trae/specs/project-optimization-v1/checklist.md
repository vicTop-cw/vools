# Checklist: Project Optimization v1

- [ ] `from vools.task.utils import Result` 返回 `vools.functional.Result` 类型
- [ ] `from vools.functional import Result` 包含 `get_or`, `get_or_raise`, `flat_map` 方法
- [ ] `from vools.decorators import add, mul, identity, compose, pipe` 正常导入
- [ ] `range(1000000) | Ops.take(5) | Ops.as_list` 返回值正确且内存高效
- [ ] `Ops.drop(n)` 返回生成器
- [ ] `Ops.distinct()` 返回生成器
- [ ] `from vools.reactive import Observable` 在任意平台正常导入
- [ ] `vools.reactive.MONITORING_AVAILABLE` 标志存在且正确
- [ ] `Pipe` 类有 `__slots__`
- [ ] `P` 类有 `__slots__`
- [ ] `functional/__init__.py` 无 `from .placeholder import *`
- [ ] `oop/__init__.py` 无 `from .xxx import *`
- [ ] `vools/__init__.py` 无 `globals()[name] = None` hack
- [ ] `Success` 和 `Failure` 类无各自的 `do()` 方法定义
- [ ] `pytest tests/ -m "not integration and not windows_only"` 全部通过
- [ ] `import vools` 成功，`dir(vools)` 包含所有预期导出