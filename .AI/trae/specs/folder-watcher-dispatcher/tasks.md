# FolderWatcher - Implementation Plan

注意: 任务按依赖顺序排列。`backend="auto"` 在 Windows 下优先 win32，失败回退 polling。

## [ ] Task 1: 数据类型基础设施（FolderChangeType / FolderData）
- **Priority**: P0
- **Depends On**: None
- **Description**:
  - 在 `vools/reactive/folder_watcher.py` 新增 `FolderChangeType(IntEnum)`: `FOLDER_CREATED=0 / FOLDER_DELETED=1 / FOLDER_RENAMED=2 / FOLDER_MOVED_IN=3 / FOLDER_MOVED_OUT=4 / FOLDER_ATTRIB=5 / FOLDER_CONTENT=6`
  - 新增 `@dataclass FolderData(path, old_path, change_type, file_count, child_folder_count, timestamp, sequence, tags, metadata)`
  - 提供 `FolderData.now(...)` / `.to_dict()` / `.from_dict()` / `.to_json()` / `.from_json()`
  - 全局 `_seq_counter = itertools.count(1)` 保证 sequence 单调递增
- **Acceptance Criteria Addressed**: AC-1, AC-2
- **Test Requirements**:
  - `programmatic` TR-1.1: `int(FolderChangeType.FOLDER_CREATED) == 0`, `int(FolderChangeType.FOLDER_CONTENT) == 6`, `len(list(FolderChangeType)) == 7`
  - `programmatic` TR-1.2: `FolderData.now(path="/tmp/a", change_type=FOLDER_CREATED)` 可创建；所有字段非 None 默认值合理
  - `programmatic` TR-1.3: `fd.to_json()` → `FolderData.from_json()` 往返，`path/change_type/sequence/tags/metadata` 一致
  - `programmatic` TR-1.4: `FolderData.from_dict({...})` 能容错缺失字段（使用合理默认值）
- **Notes**: 完全镜像 FileData 的设计模式，但字段按目录语义调整。

## [ ] Task 2: Dispatcher 框架（FolderDispatcher + 后端选择器 + polling 保底）
- **Priority**: P0
- **Depends On**: Task 1
- **Description**:
  - `FolderDispatcher(on_change_folder=None, paths=(), backend="auto")`
  - `add_path(path)` / `remove_path(path)` / `stop()` / `start()` / `is_running` / `backend_name` / `subject` / `dispatch_count`
  - 上下文管理器 `with FolderDispatcher(...) as d: ...`
  - `_PollingBackend`: 每 `interval` 秒检查目录列表差异（通过 `os.listdir` + hash），不触发 CPU 过高
  - 所有后端统一回调内部 `_emit(event: FolderData)`，再通过 `on_change_folder` 和 `Subject.on_next` 分发
- **Acceptance Criteria Addressed**: AC-3, AC-8
- **Test Requirements**:
  - `programmatic` TR-2.1: `FolderDispatcher(paths=[tmpdir], backend="polling")` 能启动、`is_running=True`，`stop()` 后 `is_running=False`
  - `programmatic` TR-2.2: polling 后端下，`os.mkdir(child)` 能在 1s 内产生一条 FOLDER_CREATED FolderData
  - `programmatic` TR-2.3: `with` 块退出后后台线程终止，`dispatch_count` 计数正确
  - `programmatic` TR-2.4: 对不存在路径调用 `add_path` 不抛异常，记录 warning log（pytest caplog）
- **Notes**: polling 后端使用 `threading.Event` + `interval=0.2`，同 FileDispatcher 风格。

## [ ] Task 3: Windows Hook 后端（ReadDirectoryChangesW + IOCP）
- **Priority**: P0
- **Depends On**: Task 2
- **Description**:
  - `_Win32WatchBackend`: `ReadDirectoryChangesW(FILE_NOTIFY_CHANGE_DIR_NAME | FILE_NOTIFY_CHANGE_ATTRIBUTES | FILE_NOTIFY_CHANGE_LAST_WRITE)` + I/O Completion Port
  - 过滤仅处理目录事件（检查 `FILE_ACTION_ADDED`/`FILE_ACTION_REMOVED`/`FILE_ACTION_MODIFIED`/`FILE_ACTION_RENAMED_OLD_NAME`/`FILE_ACTION_RENAMED_NEW_NAME`）
  - 通过 `FILE_NOTIFY_CHANGE_DIR_NAME` 过滤目录相关事件，通过 `os.path.isdir(path)` 二次确认
  - 在 64-bit Windows 上正确设置 `argtypes`/`restype`
- **Acceptance Criteria Addressed**: AC-5
- **Test Requirements**:
  - `programmatic` TR-3.1 (Windows only): `FolderDispatcher(paths=[tmpdir], backend="win32")` 能成功启动，`backend_name == "win32"`
  - `programmatic` TR-3.2 (Windows only): mkdir/rmdir/rename 分别产生 FOLDER_CREATED/FOLDER_DELETED/FOLDER_RENAMED
  - `programmatic` TR-3.3 (Windows only): `stop()` 能在 1s 内干净返回，无未释放句柄
- **Notes**: 参考 `file_watcher.py` 的 `_Win32WatchBackend` 实现，复制模式并改为过滤目录。

## [ ] Task 4: Linux inotify 后端
- **Priority**: P0
- **Depends On**: Task 2
- **Description**:
  - `_InotifyWatchBackend`: `inotify_init()` + `inotify_add_watch(IN_ISDIR | IN_CREATE | IN_DELETE | IN_MOVED_FROM | IN_MOVED_TO | IN_ATTRIB)` + `select.epoll`
  - 读取 `inotify_event` 结构（`struct.inotify_event` + variable-length name）
  - 过滤 `IN_ISDIR` 位，目录事件才派发
- **Acceptance Criteria Addressed**: AC-6
- **Test Requirements**:
  - `programmatic` TR-4.1 (Linux/WSL only): `backend="inotify"` 能启动，`backend_name == "inotify"`
  - `programmatic` TR-4.2 (Linux/WSL only): mkdir/rmdir/rename 分别产生 FOLDER_CREATED/FOLDER_DELETED/FOLDER_RENAMED
  - `programmatic` TR-4.3 (Linux/WSL only): `stop()` 能在 1s 内返回，无 hanging thread
- **Notes**: 参考 `file_watcher.py` 的 `_InotifyWatchBackend`。

## [ ] Task 5: macOS FSEvents 后端（stub + 最佳努力实现）
- **Priority**: P1
- **Depends On**: Task 2
- **Description**:
  - `_MacWatchBackend`: 基于 `FSEvents` API（`FSEventStreamCreate` / `FSEventStreamStart`），检测 `kFSEventStreamEventFlagItemIsDir` 标志
  - 若不可用则 `backend="auto"` 下回退 polling
- **Test Requirements**:
  - `human-judgment` TR-5.1: macOS 代码路径存在（import 时不抛异常），在非 macOS 自动降级
- **Notes**: 由于测试环境可能没有 macOS，此任务属 P1。核心实现可参考 `file_watcher.py` 的 `_MacWatchBackend`。

## [ ] Task 6: FolderSubject / FolderObserver（响应式 API）
- **Priority**: P0
- **Depends On**: Task 1-5
- **Description**:
  - `FolderSubject(paths=(), *, on_change_folder=None, backend="auto", interval=0.2)`: 继承 `Subject[FolderData]`，内部持有 FolderDispatcher
  - `FolderSubject.start()`/`stop()`/`dispatcher`/`is_running`/`backend_name`/`dispatch_count` 公开属性
  - `with FolderSubject(...) as fs:` 上下文管理器
  - `FolderObserver(on_folder_created=None, on_folder_deleted=None, on_folder_renamed=None, on_folder_moved_in=None, on_folder_moved_out=None, on_folder_attrib=None, on_folder_content=None, on_any=None)`
  - `FolderObserver.subscribe(observable)` 返回 `Subscription`
  - `FolderObserver.attach(observable)` 返回 self，支持 `with FolderObserver(...).attach(fs): ...`
- **Acceptance Criteria Addressed**: AC-3, AC-4
- **Test Requirements**:
  - `programmatic` TR-6.1: `isinstance(FolderSubject(...), Subject)` 为 True；`FolderSubject(backend="polling").is_running` 启动后为 True
  - `programmatic` TR-6.2: 手动向 FolderSubject 发射 FOLDER_CREATED/FOLDER_DELETED/FOLDER_RENAMED 三个事件，FolderObserver 分别触发三个对应回调，互不串台
  - `programmatic` TR-6.3: `with FolderObserver(...).attach(fs): ...` 退出 with 后 subscription 已取消（无崩溃）
  - `programmatic` TR-6.4: `FolderSubject` 能通过 `.pipe(ops.filter(...)).subscribe(...)` 链式组合
- **Notes**: 完全镜像 FileSubject/FileObserver 设计。

## [ ] Task 7: from_foldersystem 工厂 + write_to_foldersystem 操作符
- **Priority**: P1
- **Depends On**: Task 6
- **Description**:
  - `from_foldersystem(paths=(), *, on_change_folder=None, backend="auto", interval=0.2) -> Tuple[Observable[FolderData], FolderDispatcher]`
  - `write_to_foldersystem(target_dir: str, *, mode: str = "create", tags: Iterable[str] = (), metadata: Dict[str, Any] | None = None) -> Operator`
    - mode: `create` / `append` / `overwrite`
    - 上游事件: FolderData / str / dict
    - 写回磁盘并产生新的 FolderData 事件
- **Acceptance Criteria Addressed**: AC-7
- **Test Requirements**:
  - `programmatic` TR-7.1: `from_foldersystem([tmpdir])` 返回 (observable, dispatcher)；dispatcher 可 `start()`/`stop()`
  - `programmatic` TR-7.2: `obs.pipe(write_to_foldersystem(tmpdir)).subscribe(...)` 不抛异常，写入新文件/子目录成功
  - `programmatic` TR-7.3: `write_to_foldersystem` 对上游 `FolderData(path=...)` 能正确转写
  - `human-judgment` TR-7.4: 操作符命名与行为和 `write_to_filesystem` 风格一致

## [ ] Task 8: vools.reactive 包导出
- **Priority**: P0
- **Depends On**: Task 7
- **Description**:
  - 在 `vools/reactive/__init__.py` 中新增导入与 `__all__` 条目: `FolderChangeType`, `FolderData`, `FolderSubject`, `FolderObserver`, `FolderDispatcher`, `from_foldersystem`, `write_to_foldersystem`
- **Test Requirements**:
  - `programmatic` TR-8.1: `from vools.reactive import FolderSubject, FolderObserver, FolderChangeType, FolderData, FolderDispatcher, from_foldersystem, write_to_foldersystem` 不抛异常
  - `programmatic` TR-8.2: `__all__` 中包含所有新增符号

## [ ] Task 9: 测试文件 tests/test_reactive_folder_watcher.py
- **Priority**: P0
- **Depends On**: Task 8
- **Description**:
  - 覆盖 Task 1-8 测试要求（即 TR-1.* 到 TR-8.*）
  - 与 `tests/test_reactive_file_watcher.py` 风格一致
  - 测试只在 Windows 与 WSL 下必须全部通过
  - 对非 Windows 平台使用 `backend="polling"` 作为保底路径
- **Test Requirements**:
  - `programmatic` TR-9.1: `pytest tests/test_reactive_folder_watcher.py -v` 全绿（Windows / WSL）
  - `programmatic` TR-9.2: 所有 skip 平台分支有合理的 skip 理由（如 `sys.platform != "win32"`）
  - `human-judgment` TR-9.3: 测试用例命名清晰，可读可维护

## [ ] Task 10: 端到端验证 & 命名一致性 review
- **Priority**: P2
- **Depends On**: Task 9
- **Description**:
  - 在 Windows + WSL 运行端到端流: 创建→删除→重命名→订阅→写回→验证
  - 命名一致性检查 (human review)
- **Test Requirements**:
  - `programmatic` TR-10.1: 端到端流能跑通并产生正确 FolderData 序列
  - `human-judgment` TR-10.2: 代码风格与 File* 系列保持一致（字段命名、dataclass 结构、subject/observer 继承）
