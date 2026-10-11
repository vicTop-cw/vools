# Tasks — 文件监控分发器

## 阶段 1：基础设施（无依赖，可并行）

- [x] Task 1.1: 创建 `vools/reactive/file_watcher.py`，写好模块头注释，定义 `FileChangeType(IntEnum)`
- [x] Task 1.2: 定义 `FileData` dataclass（含 `slots=True`、工厂方法 `now()`、JSON/Bytes 序列化）
- [x] Task 1.3: 在 `vools/reactive/__init__.py` 导入并导出 `FileChangeType`、`FileData`、`FileSubject`、`FileObserver`、`from_filesystem`、`write_to_filesystem`

## 阶段 2：Windows Win32 Hook 后端（Win32API 事件驱动）

- [x] Task 2.1: 初始化 ctypes：`_kernel32`、`_user32`
- [x] Task 2.2: 实现 `_Win32WatchBackend`：ReadDirectoryChangesW + I/O Completion Port + 后台线程
- [x] Task 2.3: 正确设置 ctypes `argtypes`/`restype`，处理 64 位指针

## 阶段 3：macOS FSEvents 后端（纯 ctypes）

- [x] Task 3.1: 实现 `_MacWatchBackend`（stub，回退 polling）

## 阶段 4：Linux inotify 后端（纯 ctypes + epoll）

- [x] Task 4.1: 实现 `_InotifyWatchBackend`：inotify_init + inotify_add_watch + select.epoll + 手动解析 inotify_event

## 阶段 5：FileDispatcher 分发器

- [x] Task 5.1: 实现 `FileDispatcher`：add_path/remove_path, change_types 白名单, 后端选择策略
- [x] Task 5.2: 实现 `FileSubject`：继承 Subject[FileData]，封装 Dispatcher，`with` 语法
- [x] Task 5.3: 实现 `FileObserver`：按 FileChangeType 路由，支持 `with` 语法
- [x] Task 5.4: 实现 `from_filesystem(paths, ...)` 工厂函数
- [x] Task 5.5: 实现 `write_to_filesystem(dispatcher, mode)` 操作符

## 阶段 6：测试

- [x] Task 6.1: 创建 `tests/test_reactive_file_watcher.py`，写全部 12 个测试用例
- [x] Task 6.2: Windows 本地运行全部测试，确保通过（12/12）
- [ ] Task 6.3: WSL 环境中运行 inotify 相关测试，确保通过

---

# Task Dependencies

```
Task 1.1 → Task 1.2
Task 1.2 → Task 1.3
Task 2.1 → Task 2.2 → Task 2.3
Task 2.3 → Task 5.1 (Windows 路径)
Task 3.1 → Task 5.1 (macOS 路径)
Task 4.1 → Task 5.1 (Linux 路径)
Task 5.1 → Task 5.2 → Task 5.3 → Task 5.4 → Task 5.5
Task 5.5 → Task 6.1
Task 6.1 → Task 6.2
Task 6.1 → Task 6.3
```
