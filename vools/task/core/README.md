# vools.task.core — 任务队列核心

数据模型、SQLite 存储、队列管理和 Worker 实现。

## 核心组件

| 名称 | 说明 |
|------|------|
| `Task` | 任务数据模型（含 dependencies 支持 DAG） |
| `TaskStatus` | 任务状态枚举（PENDING, READY, RUNNING, SUCCESS, FAILED, SKIPPED, CANCEL） |
| `TaskStorage` | SQLite 存储层（含 DAG 依赖表） |
| `TaskQueue` | 任务队列管理器（提交、状态查询、结果获取） |
| `Worker` | 单 Worker 执行器 |
| `WorkerPool` | 多进程 Worker 池 |
| `ThreadPool` | 多线程 Worker 池 |
