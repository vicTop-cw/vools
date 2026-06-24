# Project Optimization v1 Spec

## Why
vools 项目经过多轮迭代，积累了一些技术债务：代码重复、API 不一致、内存效率问题、跨平台兼容性不足。这是 v0.1.20 前的系统性优化。

## What Changes
- 消除重复代码（Result 类型、柯里化函数）
- 统一 API 风格（命名、管道操作惰性求值）
- 提升性能和内存效率（`__slots__`、惰性求值）
- 修复跨平台导入问题（monitoring 模块条件导入）
- 清理代码风格（wildcard imports、hacky 模式）

## Impact
- Affected specs: N/A（新优化计划）
- Affected code: `vools/functional/`, `vools/decorators/`, `vools/curried/`, `vools/reactive/`, `vools/oop/`, `vools/task/utils/`, `vools/__init__.py`

---

## ADDED Requirements

### Requirement: 统一 Result 类型
系统 SHALL 提供单一的 `Result` 类型，消除 `vools/functional/result.py` 和 `vools/task/utils/__init__.py` 之间的重复实现。

#### Scenario: 从 functional 导入 Result
- **WHEN** 用户执行 `from vools.functional import Result`
- **THEN** 获得功能完整的 Result 类型（含 `bind`, `map`, `map_err`, `unwrap`, `unwrap_or`, `unwrap_or_else`, `or_else`, `from_unsafe`）

#### Scenario: 从 task.utils 导入 Result
- **WHEN** 用户执行 `from vools.task.utils import Result`
- **THEN** 获得与 `vools.functional.Result` 相同的类型（通过 re-export）

### Requirement: 消除柯里化函数重复
系统 SHALL 将 `vools/decorators/curried.py` 中的柯里化函数迁移到 `vools/curried/` 子包，decorators 模块仅做 re-export。

#### Scenario: 从 decorators 导入柯里化函数（向后兼容）
- **WHEN** 用户执行 `from vools.decorators import add, mul, identity`
- **THEN** 仍能正常导入（通过 re-export）

### Requirement: Ops 管道操作惰性求值
`Ops.take` 和 `Ops.drop` 等操作 SHALL 返回惰性生成器而非物化列表，与 `Seq` 行为一致。

#### Scenario: Ops.take 惰性
- **WHEN** 用户执行 `range(1000000) | Ops.take(5) | Ops.as_list`
- **THEN** 仅消耗前 5 个元素，无内存膨胀

### Requirement: Monitoring 模块条件导入
`vools/reactive/__init__.py` SHALL 在导入 monitoring 模块时进行条件检查，Windows 平台不可用时优雅降级，不抛出 ImportError。

#### Scenario: 非 Windows 平台导入
- **WHEN** 用户在 Linux/Mac 上执行 `from vools.reactive import Observable`
- **THEN** Observable 正常导入，monitoring 功能不可用但无异常

### Requirement: `__slots__` 内存优化
热路径类（Pipe, P, Ops 子类）SHALL 使用 `__slots__` 以减少内存开销。

#### Scenario: Pipe 实例创建
- **WHEN** 创建 10000 个 Pipe 实例
- **THEN** 内存占用比无 `__slots__` 版本减少约 50%

---

## MODIFIED Requirements

### Requirement: 清理 Wildcard Imports
**Before**: `functional/__init__.py` 使用 `from .placeholder import *`，`oop/__init__.py` 使用多个 `from .xxx import *`  
**After**: 显式导入所有名称，`__all__` 列表完整

### Requirement: 清理 `__init__.py` hacky 模式
**Before**: `vools/__init__.py` 中存在 `for name in __all__: globals()[name] = None` 的 hack 模式  
**After**: 移除该模式，使用更清晰的延迟加载方式

### Requirement: 消除 `result.py` 中的 `do()` 重复代码
**Before**: `Result`, `Success`, `Failure` 三个类中各自定义了相同的 `do()` 方法  
**After**: 仅在 `Result` 基类中定义 `do()`，子类继承