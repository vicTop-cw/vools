# vools.reactive.core — 响应式核心

Observable / Subject / Scheduler 核心实现。

| 名称 | 说明 |
|------|------|
| `Observable` | 可观察对象 |
| `Subject` | 主题（可同时作为 Observable 和 Observer） |
| `BehaviorSubject` | 保留最新值的 Subject |
| `ReplaySubject` | 重放历史值的 Subject |
| `Scheduler` | 调度器（Immediate / CurrentThread / AsyncIO / ThreadPool / NewThread） |
| `ConnectableObservable` | 可连接 Observable |
