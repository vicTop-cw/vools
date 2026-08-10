# vools.reactive

响应式编程模块，提供 Observable/Subject/Observer 模式和丰富的操作符。

## 主要功能

- **核心类**: `Observable`, `Subject`, `BehaviorSubject`, `ReplaySubject`
- **创建操作符**: `of`, `from_iterable`, `from_range`, `from_callable`
- **转换操作符**: `map`, `flat_map`, `concat_map`, `switch_map`
- **过滤操作符**: `filter`, `take`, `skip`, `debounce`, `throttle`
- **组合操作符**: `merge`, `concat`, `zip`, `combine_latest`
- **监控操作符**: `from_keyboard`, `from_mouse`, `from_clipboard`, `from_file_watcher`

## 核心类/操作符

| 名称 | 类型 | 说明 |
|------|------|------|
| `Observable` | 类 | 可观察对象 |
| `Subject` | 类 | 主题对象 |
| `BehaviorSubject` | 类 | 行为主题（保留最新值） |
| `ReplaySubject` | 类 | 重放主题（重放历史值） |

## 使用示例

```python
from vools.reactive import Observable, Subject

# 创建 Observable
obs = Observable.of(1, 2, 3)
obs.subscribe(lambda x: print(x))

# 使用操作符
obs = Observable.from_iterable([1, 2, 3])
obs.map(lambda x: x * 2).filter(lambda x: x > 3).subscribe(print)

# Subject
subject = Subject()
subject.subscribe(lambda x: print(f"Value: {x}"))
subject.on_next(42)
```

## 注意事项

- 及时取消订阅以避免内存泄漏
- 监控操作符需要平台特定依赖（如 `pywin32`）

## 子包

| 路径 | 说明 |
|------|------|
| `vools.reactive.core` | 核心实现（Observable, Subject, Scheduler） |
| `vools.reactive.operators` | 操作符集合（标准、扩展、统计） |
| `vools.reactive.monitoring` | 系统监控（键盘、鼠标、剪贴板、文件） |