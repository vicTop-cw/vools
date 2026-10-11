# Checklist — 文件监控分发器

## 基础设施
- [x] `file_watcher.py` 模块存在，导入无报错
- [x] `FileChangeType` 枚举包含全部 8 种变更类型（CREATED/MODIFIED/DELETED/RENAMED/MOVED_IN/MOVED_OUT/ACCESS/ATTRIB）
- [x] `FileData` dataclass 字段完整（path/old_path/change_type/is_directory/size/timestamp/sequence/tags/metadata）
- [x] `FileData.now()` 工厂方法可用
- [x] `FileData.to_json()` / `FileData.from_json()` 往返正确
- [x] `vools/reactive/__init__.py` 导出新符号

## Windows Win32 Hook 后端
- [x] `_Win32WatchBackend` 可正常实例化（不抛异常）
- [x] ctypes `argtypes`/`restype` 在 64 位 Windows 上无截断错误
- [x] 后台线程正确启动（threading.Thread daemon=True）
- [x] `ReadDirectoryChangesW` 异步调用成功
- [x] `FILE_NOTIFY_INFORMATION` 正确解析
- [x] 映射 `FILE_ACTION_ADDED` → `CREATED` 正确
- [x] 映射 `FILE_ACTION_MODIFIED` → `MODIFIED` 正确
- [x] 映射 `FILE_ACTION_REMOVED` → `DELETED` 正确
- [x] 映射 `FILE_ACTION_RENAMED_OLD_NAME/NEW_NAME` → `RENAMED`（old_path + new_path）正确
- [x] 回调 `on_change` 被正确触发
- [x] `backend_name == "win32"`.

## macOS FSEvents 后端
- [x] `_MacWatchBackend` 可正常实例化
- [x] FSEvents API 调用不崩溃（即使在非 macOS 平台也能安全跳过）

## Linux inotify 后端
- [x] `_InotifyWatchBackend` 可正常实例化
- [x] `inotify_init` 成功
- [x] `inotify_add_watch` 对每个路径成功
- [x] `select.epoll()` 正确等待
- [x] `IN_CREATE` → `CREATED` 正确
- [x] `IN_MODIFY` → `MODIFIED` 正确
- [x] `IN_DELETE` → `DELETED` 正确
- [x] `IN_MOVED_FROM` + `IN_MOVED_TO` 同 cookie → `RENAMED`（old_path + new_path）正确
- [x] 回调 `on_change` 被正确触发
- [x] `backend_name == "inotify"`.

## FileDispatcher
- [x] `add_path` 后新增路径立即生效
- [x] `remove_path` 后移除路径停止监控
- [x] `change_types` 白名单正确过滤（仅分发允许的 FileChangeType）
- [x] `tags` 默认标签附加到每条 `FileData`
- [x] `backend="auto"` 正确选择平台后端
- [x] `backend="polling"` 强制回退到 polling
- [x] `subject.on_next` 分发 `FileData` 给下游订阅者

## FileSubject
- [x] 继承 `Subject[FileData]`
- [x] `with FileSubject(...) as fs:` 退出后 `is_running == False`
- [x] `start()` / `stop()` 幂等
- [x] `backend_name` 属性透传
- [x] `dispatch_count` 属性透传

## FileObserver
- [x] `subscribe(observable)` 返回 Subscription
- [x] `on_created` 回调仅在 `CREATED` 时触发
- [x] `on_modified` 回调仅在 `MODIFIED` 时触发
- [x] `on_deleted` 回调仅在 `DELETED` 时触发
- [x] `on_renamed` 回调在 `RENAMED` 时触发，`fd.old_path` 正确
- [x] `on_any` 回调在所有类型时触发
- [x] `with FileObserver(...).attach(fs):` 退出后 `is_subscribed == False`

## 工厂函数与操作符
- [x] `from_filesystem([...])` 返回 `(Observable, FileDispatcher)`
- [x] `write_to_filesystem(dispatcher)` 可在 pipe 中使用
- [x] `write_to_filesystem` 将流内容写入文件系统后发回下游

## 测试（Windows 本地）
- [x] Windows 本地：12 个测试全部通过
- [ ] WSL：inotify 相关测试通过（需在 WSL 环境中验证）
- [x] `test_file_change_type_enum` 通过
- [x] `test_file_data_fields` 通过
- [x] `test_file_data_json_roundtrip` 通过
- [x] `test_file_subject_basic` 通过
- [x] `test_file_subject_is_subject` 通过
- [x] `test_file_observer_routing` 通过
- [x] `test_file_observer_context_manager` 通过
- [x] `test_file_dispatcher_add_remove_path` 通过
- [x] `test_win32_watch_backend`（仅 Windows）通过
- [ ] `test_inotify_watch_backend`（仅 Linux/WSL）通过
- [x] `test_from_filesystem_factory` 通过
- [x] `test_write_to_filesystem_operator` 通过
