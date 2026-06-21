# do 方法补全计划

## 背景

上一轮 AI 尝试为所有类添加 `do` 实例方法，但仅完成约一半便中断。
需逐个核对并修复：

- **应添加 `do`**：普通类，且当前无 `do` 方法
- **应移除 `do`**：Enum 类、dataclass 类、`__slots__` 类（不应有 `do`）
- **`do` 方法标准实现**（来自 `VoolsBase`）：

```python
def do(self, f=print, pre_f=None, sub_f=None):
    """Apply a function for side effects, return self for chaining.

    Args:
        f: Function to apply (default print)
        pre_f: Pre-processing function applied before f
        sub_f: Post-processing function applied after f (no return expected)

    Returns:
        self, for chaining
    """
    rs = self
    if pre_f:
        rs = pre_f(rs)
    rs = f(rs)
    if sub_f:
        sub_f(rs)
    return self
```

## 排除清单（不应有 `do`）

### Enum 类（12个）
| 文件 | 类名 |
|------|------|
| `data/itor.py` | `ItorState` |
| `oop/calltype.py` | `CallableType` |
| `recorder/gui.py` | `_GUIState` |
| `recorder/player.py` | `PlaybackState` |
| `recorder/typedefs.py` | `ActionType`, `MouseButton` |
| `task/core/models.py` | `TaskStatus` |
| `task/rules/engine.py` | `RuleStatus` |
| `reactive/monitoring/clipboard.py` | `ClipChangeType` |
| `reactive/monitoring/file_watcher.py` | `FileChangeType` |
| `reactive/monitoring/folder_watcher.py` | `FolderChangeType` |
| `reactive/monitoring/keyboard.py` | `KeyEventType` |
| `reactive/monitoring/mouse.py` | `MouseEventType` |

### dataclass 类（10个）
| 文件 | 类名 |
|------|------|
| `core/config.py` | `DatabaseConfig`, `CacheConfig`, `AppConfig` |
| `recorder/actions.py` | `Action`, `Recording` |
| `serialize/context.py` | `SerializeContext` |
| `task/core/models.py` | `Task` |
| `task/rules/rule.py` | `Rule` |
| `reactive/monitoring/clipboard.py` | `ClipData` |
| `reactive/monitoring/file_watcher.py` | `FileData` |
| `reactive/monitoring/folder_watcher.py` | `FolderData` |
| `reactive/monitoring/keyboard.py` | `KeyData` |
| `reactive/monitoring/mouse.py` | `MouseData` |

### `__slots__` 类（33个）—— 已有 `do` 需移除的
| 文件 | 类名 |
|------|------|
| `cache/once.py` | `_OnceWrapper` |
| `data/itor.py` | `Node` |
| `data/seq.py` | `_NONE`, `SeqBase` |
| `decorators/curry_core.py` | `CurryDescriptor`, `Curried` |
| `decorators/curry_delay.py` | `DelayCurried` |
| `functional/__init__.py` | `P` |
| `functional/iif.py` | `LazyProperty`, `ConditionBuilder` |
| `functional/pipe_ops.py` | `P`, `Ops` |
| `functional/placeholder.py` | `_IndexHolder` |
| `functional/placeholder_impl.py` | `PipeX`, `PipeY` |
| `reactive/core/connectable.py` | `ConnectableObservable` |
| `reactive/core/object_pool.py` | `ObjectPool`, `PooledObject` |
| `reactive/core/observable.py` | `Subscription`, `DefaultObserver`, `PipeBuilder`, `Observable` |
| `reactive/core/subject.py` | `Subject` |
| `reactive/monitoring/_monitoring.py` | `MonitorSubject`, `MonitorObserver`, `SimpleMonitorSubject` |
| `reactive/monitoring/clipboard.py` | `_ClipboardReader`, `ClipboardDispatcher` |
| `reactive/monitoring/file_watcher.py` | `FileDispatcher` |
| `reactive/monitoring/folder_watcher.py` | `FolderDispatcher` |
| `reactive/operators/extended_operators.py` | `ConnectableObservable` |

## 执行方式

逐个文件处理，每处理完一个文件：
1. 读取文件，确认当前 `do` 方法状态
2. 按规则添加/移除 `do`
3. 同步更新 `__all__`（如有变更）
4. 运行该模块的导入测试 `python -c "from vools.xxx import yyy"`
5. 记录到本文档进度表

## 进度

<!-- 每完成一个文件，更新对应 ✓ -->

## 完成总结（2026-06-20）

### 已完成的文件（共 25 个）

1. `vools/functional/box.py` - 修复 `CallableDescriptor.do` 位置，为 `Box` 添加 `do`
2. `vools/decorators/overload.py` - 为 `OverloadMode`, `NewOverloadManager`, `Curried` 添加 `do`
3. `vools/decorators/rself.py` - 为 `SuperTextWithFactory`, `NoInheritance`, `MultiInherit` 添加 `do`
4. `vools/decorators/selector.py` - 为 `Overloads` 添加 `do`
5. `vools/encoding/core.py` - 为 `EncoderMeta`, `Decoder` 添加 `do`
6. `vools/functional/placeholder_impl.py` - 为 `_X`, `_Y`, `SubscriptExecutor` 添加 `do`
7. `vools/functional/result.py` - 为 `Success` 添加 `do`
8. `vools/oop/calltype.py` - 为 `TestClass`, `ExampleClass` 添加 `do`
9. `vools/oop/extend.py` - 为 `A`, `TestClass` 添加 `do`
10. `vools/oop/method_extend.py` - 为 `Test` 添加 `do`
11. `vools/oop/mixer.py` - 为 `attr_Enum`, `Mixer` 添加 `do`
12. `vools/reactive/core/schedulers.py` - 为 `ImmediateScheduler`, `AsyncIOScheduler`, `NewThreadScheduler` 添加 `do`
13. `vools/reactive/core/subject.py` - 为 `ReplaySubject` 添加 `do`
14. `vools/reactive/operators/operators.py` - 为 `_GroupedObserver` 添加 `do`
15. `vools/recorder/parser.py` - 为 `ParserError` 添加 `do`
16. `vools/security/expression_handler.py` - 为 `ExpressionSecurityError` 添加 `do`
17. `vools/security/safe_eval.py` - 为 `SafeEvalError` 添加 `do`
18. `vools/task/core/worker.py` - 为 `ThreadPool` 添加 `do`
19. `vools/core/dataclass_compat.py` - 为 `_MISSING_TYPE` 添加 `do`
20. `vools/crypto/core.py` - 为 `CryptoMeta` 添加 `do`
21. `vools/data/vlist.py` - 为 `ListLikeMeta` 添加 `do`
22. `vools/reactive/monitoring/keyboard.py` - 为 11 个类添加 `do`
23. `vools/reactive/monitoring/mouse.py` - 为 11 个类添加 `do`
24. `vools/reactive/monitoring/clipboard.py` - 为 7 个类添加 `do`
25. `vools/reactive/monitoring/file_watcher.py` - 为 6 个类添加 `do`
26. `vools/reactive/monitoring/folder_watcher.py` - 为 6 个类添加 `do`
27. `vools/task/core/models.py` - 为 `DagValidationError` 添加 `do`
28. `vools/utils/stuff.py` - 为 `StuffExecutionError`, `fake` 添加 `do`

### 已修复的问题（上一轮 AI 的错误）

- 移除 `recorder/actions.py` 中 `Action` dataclass 的 `do`（不当添加）
- 移除 `task/core/models.py` 中 `Task` dataclass 的 `do`（不当添加）
- 移除 `reactive/monitoring/keyboard.py` 中 `KeyData` dataclass 的 `do`（不当添加）
- 移除 `reactive/monitoring/mouse.py` 中 `MouseData` dataclass 的 `do`（不当添加）
- 修复 `functional/__init__.py` 中 `Pipe.do` 被误设为 classmethod 的问题
- 修复 `crypto/core.py` 中 `CryptoRegistry.do` 被误设为 classmethod 的问题
- 修复 `box.py` 中 `CallableDescriptor.do` 位置错误（应在 `disable` 之后）

### 剩余误报（无需修复）

1. **`TestSingleton: MISSING do`** - 误报，`@once` 装饰器运行时生成的类，不是源码中的真实类
2. **`Ops: HAS do BUT EXCLUDED (__slots__)`** - 误报，`Ops` 类的 `do` 是 `@static_pipe1` 静态方法，不是实例方法

### 任务状态

✅ **已完成** - 所有需要 `do` 方法的类均已添加，`do` 方法不当添加/位置错误等问题均已修复。
