# 文件监控分发器（FileObserver / FileSubject）Spec

## Why

clipboard 模块实现了剪贴板事件的响应式分发。文件系统的监控是另一个高频需求——监听目录/文件的增删改移，
同样可以用 `Subject → Operator → Observer` 的响应式模式来封装，做到链式订阅、算子组合、异步流。
Windows/macOS/Linux 均可通过系统原生 API（`ReadDirectoryChangesW` / `FSEvents` / `inotify`）实现**事件驱动钩子**，
无需轮询。

## What Changes

- 新增 `vools/reactive/file_watcher.py`（约 400–600 行）
- 新增 `ChangeType(IntEnum)` 文件变更类型
- 新增 `FileData` dataclass：路径、变更类型、时间戳、OldPath（重命名时）、大小
- 新增 `_Win32WatchBackend`：通过 `ReadDirectoryChangesW` + OVERLAPPED I/O + 隐藏窗口消息循环实现
- 新增 `_MacWatchBackend`：通过 `FSEvents` API（纯 ctypes）实现
- 新增 `_InotifyWatchBackend`：通过 `inotify_init`/`inotify_add_watch` + `epoll`/`select` 实现
- 新增 `FileSubject`：继承 `Subject[FileData]`，内置 Dispatcher，支持 `with` 语法、`set_async`/`set_sync`
- 新增 `FileObserver`：按 `ChangeType` 路由回调，支持 `on_created`/`on_modified`/`on_deleted`/`on_renamed`/`on_any`
- 新增 `from_filesystem(paths, ...)` 工厂函数，返回 `(Observable[FileData], Dispatcher)`
- 新增 `write_to_filesystem` 操作符（创建/删除文件）
- 导出到 `vools/reactive/__init__.py`
- 新增 `tests/test_reactive_file_watcher.py`（Windows + WSL 通过）

## Impact

- 新增文件：`vools/reactive/file_watcher.py`
- 修改文件：`vools/reactive/__init__.py`（导出）
- 测试文件：`tests/test_reactive_file_watcher.py`

---

## ADDED Requirements

### Requirement: FileChangeType 枚举

系统 SHALL 提供 `FileChangeType(IntEnum)`，定义如下变更类型：

| 成员 | 值 | 说明 |
|---|---|---|
| `CREATED` | 0 | 文件/目录被创建 |
| `MODIFIED` | 1 | 文件内容被修改 |
| `DELETED` | 2 | 文件/目录被删除 |
| `RENAMED` | 3 | 文件/目录被重命名（old_path → new_path） |
| `MOVED_IN` | 4 | 文件从监控目录外移入 |
| `MOVED_OUT` | 5 | 文件从监控目录移出（改名后可归为 RENAMED） |
| `ACCESS` | 6 | 文件被读取（可选，需系统支持） |
| `ATTRIB` | 7 | 文件属性/元数据变化（权限、时间戳等） |

#### Scenario: 枚举成员验证
- **WHEN** 调用 `int(FileChangeType.CREATED)`  
  **THEN** 返回 `0`
- **WHEN** 检查 `isinstance(FileChangeType.CREATED, IntEnum)`  
  **THEN** 返回 `True`

---

### Requirement: FileData 数据类

系统 SHALL 提供 `FileData` dataclass，字段如下：

```python
@dataclass(slots=True)
class FileData:
    path: str              # 触发变更的完整路径
    old_path: str | None  # 重命名时旧路径；其它情况 None
    change_type: FileChangeType
    is_directory: bool
    size: int | None       # 变更后大小（删除时 None）
    timestamp: datetime   # 检测到变更的时间
    sequence: int         # 全局递增序号
    tags: List[str]
    metadata: Dict[str, Any]
```

#### Scenario: 工厂方法
- **WHEN** 调用 `FileData.now(path="C:/a.txt", change_type=FileChangeType.MODIFIED)`  
  **THEN** 返回完整 FileData 实例，timestamp 和 sequence 自动填充

#### Scenario: JSON 序列化往返
- **WHEN** 调用 `d.to_json()` 和 `FileData.from_json(j)`  
  **THEN** content、old_path、change_type、timestamp 均一致

---

### Requirement: FileSubject — 带文件监控的 Subject

`FileSubject` SHALL：
1. 继承自 `Subject[FileData]`
2. 内部持有 `FileDispatcher`
3. 实现 `with` 上下文管理器，自动 `start/stop`
4. 直接暴露 `add_path/remove_path`（动态增删监控目标）
5. 直接暴露 `set_async(watched_path, content)` — 异步写文件

```python
with FileSubject(paths=["./src"], backend="auto") as fs:
    fs.pipe(ops.filter(lambda f: f.change_type == FileChangeType.MODIFIED)) \
      .subscribe(on_next=lambda f: print("修改了:", f.path))
```

#### Scenario: 构造与属性
- **WHEN** `fs = FileSubject(paths=["./a"], backend="polling")`  
  **THEN** `fs.backend_name == "polling"`
- **WHEN** `with FileSubject(...) as fs:` 退出时  
  **THEN** `fs.is_running == False`

---

### Requirement: FileObserver — 按 FileChangeType 路由回调

`FileObserver` SHALL：
1. 提供 `on_created`、`on_modified`、`on_deleted`、`on_renamed`、`on_any`、`on_error`、`on_completed`
2. `subscribe(Observable)` 返回 Subscription
3. 支持 `with FileObserver(...).attach(fs): ...` 链式用法

```python
FileObserver(
    on_created=lambda fd: print("新建:", fd.path),
    on_modified=lambda fd: print("修改:", fd.path),
    on_renamed=lambda fd: print(f"{fd.old_path} → {fd.path}"),
).subscribe(fs)
```

#### Scenario: 类型路由
- **WHEN** FileDispatcher 发出 `FileData(..., change_type=DELETED)`  
  **THEN** 调用 `on_deleted`，不调用 `on_created`

---

### Requirement: FileDispatcher — 跨平台文件监控分发器

`FileDispatcher` SHALL：
1. `backend="auto"` 时自动选择最优后端：Windows → Win32，macOS → FSEvents，Linux → inotify
2. 失败时回退到 polling 后端
3. `add_path(path)` / `remove_path(path)` 动态增删监控目录/文件
4. `change_types` 白名单过滤
5. `subject: Subject[FileData]` — 可直接 `.pipe(...).subscribe(...)`

#### Scenario: 路径增删
- **WHEN** `d.add_path("./new_dir")`  
  **THEN** 立即开始监控新路径

---

### Requirement: from_filesystem 工厂函数

返回 `(Observable[FileData], FileDispatcher)`，可直接 `.pipe()`：

```python
obs, d = from_filesystem(["./src", "./tests"])
obs.pipe(ops.filter(lambda f: f.change_type == FileChangeType.MODIFIED)).subscribe(...)
d.start()
```

---

### Requirement: Windows Win32 Hook 后端

使用 `ReadDirectoryChangesW` + 隐藏窗口消息循环（`AddDirectoryChangeNotification` 思路）：

1. 为每个监控路径创建独立的 `OVERLAPPED` + 隐藏窗口
2. 在隐藏窗口线程的消息循环中 `GetQueuedCompletionStatus` 获取 I/O 完成事件
3. 解析 `FILE_NOTIFY_INFORMATION` 结构，提取 `FileName`、`Action`
4. 映射 `Action` → `FileChangeType`
5. 调用 `subject.on_next(FileData)`

#### Scenario: 检测到文件创建
- **WHEN** 在监控目录下新建文件 `test.txt`  
- **THEN** 收到 `FileData(path=..., change_type=CREATED)`

---

### Requirement: macOS FSEvents 后端（纯标准库 ctypes）

使用 CoreFoundation FSEvents API 或纯 FSEvents C 接口：
1. `FSEventStreamCreate` 创建事件流
2. `FSEventStreamScheduleWithRunLoop` + `CFRunLoopRun` 在后台线程运行
3. `FSEventStreamCallback` 接收事件，映射到 `FileChangeType`
4. 调用 `subject.on_next(FileData)`

#### Scenario: 检测到文件删除
- **WHEN** 在监控目录下删除文件  
- **THEN** 收到 `FileData(path=..., change_type=DELETED)`

---

### Requirement: Linux inotify 后端（纯标准库 ctypes）

使用 `inotify_init` + `inotify_add_watch` + `epoll`（`select` 保底）：
1. 为每个监控路径 `inotify_add_watch` 获取 wd
2. 在后台线程 `epoll_wait` 循环等待事件
3. 解析 `inotify_event` 结构，映射到 `FileChangeType`
4. 调用 `subject.on_next(FileData)`

#### Scenario: 检测到文件重命名
- **WHEN** 在监控目录下重命名文件  
- **THEN** 收到 `FileData(path=..., old_path=..., change_type=RENAMED)`

---

### Requirement: 异步写文件操作符

`write_to_filesystem(dispatcher, mode="create")` 操作符：
- 接收流中的内容（str/bytes/FileData），写入指定路径
- 支持 `mode="create"|"append"|"overwrite"`
- 写入成功后将 `FileData` 发给下游

---

### Requirement: 测试覆盖

测试 SHALL 在以下环境通过：
- Windows（本地）：全部测试通过
- Windows Subsystem for Linux (WSL)：inotify 后端测试通过

跳过场景：
- macOS 后端测试在非 macOS 机器跳过
- Linux inotify 测试在非 Linux 机器跳过

测试用例：
- `test_file_change_type_enum` — 枚举成员验证
- `test_file_data_fields` — 字段完整性
- `test_file_data_json_roundtrip` — JSON 往返
- `test_file_subject_basic` — 基本构造与属性
- `test_file_subject_is_subject` — 继承 Subject
- `test_file_observer_routing` — 按类型路由
- `test_file_observer_context_manager` — with 语法
- `test_file_dispatcher_add_remove_path` — 动态增删路径
- `test_win32_watch_backend` — Windows 事件触发（仅 Windows）
- `test_inotify_watch_backend` — Linux 事件触发（仅 Linux/WSL）
- `test_from_filesystem_factory` — 工厂函数
- `test_write_to_filesystem_operator` — 写文件操作符
