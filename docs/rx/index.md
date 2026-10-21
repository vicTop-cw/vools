# vools.reactive（rx 子项目）{#A23}

> **子项目**：`rx`（响应式编程）
> **模块路径**：`vools.reactive`
> **文档编号**：#A23
> **最后更新**：2026-10-18

---

## 简介

`vools.reactive` 是 vools 的响应式编程模块（rx 子项目），提供
Observable/Subject/Observer 模式、丰富的操作符组合，以及基于系统事件
（键盘/鼠标/剪贴板/文件/文件夹/窗口/进程）的监控流封装。

## 核心类

| 名称 | 类型 | 说明 |
|------|------|------|
| `Observable` | 类 | 可观察对象 |
| `Subject` | 类 | 主题对象 |
| `BehaviorSubject` | 类 | 行为主题（保留最新值） |
| `ReplaySubject` | 类 | 重放主题（重放历史值） |

## 操作符

- **创建**：`of`、`from_iterable`、`from_range`、`from_callable`
- **转换**：`map`、`flat_map`、`concat_map`、`switch_map`
- **过滤**：`filter`、`take`、`skip`、`debounce`、`throttle`
- **组合**：`merge`、`concat`、`zip`、`combine_latest`
- **统计**：见 `vools.reactive.operators`（统计类操作符）

## 监控源（vools.reactive.monitoring）

| 名称 | 说明 |
|------|------|
| `from_keyboard` | 键盘事件监控 |
| `from_mouse` | 鼠标事件监控 |
| `from_clipboard` | 剪贴板变化监控 |
| `from_filesystem` | 文件变化监控 |
| `from_foldersystem` | 文件夹变化监控 |
| `from_window` | 窗口焦点变化监控 |
| `from_process` | 进程启动/退出监控 |

> 监控源依赖平台特定组件（Windows 下为 `pywin32` 等），不可用时会优雅降级。

## 使用示例

```python
from vools.reactive import Observable, Subject

# 创建与订阅
obs = Observable.from_iterable([1, 2, 3])
obs.map(lambda x: x * 2).filter(lambda x: x > 3).subscribe(print)
# 输出: 4 6

# Subject 手动推送
subject = Subject()
subject.subscribe(lambda x: print(f"Value: {x}"))
subject.on_next(42)

# 文件变化监控 + 操作符组合
from vools.reactive.monitoring import from_foldersystem
from vools.reactive.operators import filter

folder_obs = from_foldersystem("path/to/folder")
folder_obs.pipe(
    filter(lambda d: d.change_type == "created")
).subscribe(lambda d: print(f"New: {d.path}"))
```

## 子包结构

| 路径 | 说明 |
|------|------|
| `vools.reactive.core` | 核心实现（Observable、Subject、Scheduler） |
| `vools.reactive.operators` | 操作符集合（标准、扩展、统计） |
| `vools.reactive.monitoring` | 系统监控（键盘、鼠标、剪贴板、文件、文件夹、窗口、进程） |

## 相关文档

- [系统监控使用说明](reactive-monitoring.md)
- [功能对比（FEATURE_COMPARISON）](../../rx/vools/reactive/FEATURE_COMPARISON.md)
