# FolderWatcher - Verification Checklist

## 数据类型层
- [ ] `FolderChangeType` 共 7 个成员，值 0..6，继承 IntEnum，`str()` 返回 `FOLDER_*` 名称
- [ ] `FolderData` 支持 `to_json()` / `from_json()` 往返，timestamp/sequence/tags/metadata 无损
- [ ] `FolderData.now(...)` 工厂自动填 `timestamp=datetime.now()` 与 `sequence=next(_seq_counter)`
- [ ] `FolderData.from_dict({...})` 对缺失字段有合理默认值，不抛异常

## 分发器与后端
- [ ] `FolderDispatcher(paths=[tmpdir], backend="polling")` 可启动，`is_running=True`，`stop()` 幂等
- [ ] `backend="auto"` 在 Windows 下选择 win32，在 Linux 下选择 inotify，不可用时回退 polling
- [ ] `backend_name` 属性返回实际后端名称（win32/inotify/polling/macos）
- [ ] `add_path(path)` / `remove_path(path)` 动态增减监控路径后立即生效
- [ ] 对不存在路径调用 `add_path` 不抛异常，只记录 warning log
- [ ] polling 后端下 `os.mkdir(child)` 1s 内产生 FOLDER_CREATED

## Windows Hook（win32 后端）
- [ ] `FolderDispatcher(backend="win32")` 能成功启动，`backend_name == "win32"`
- [ ] `os.mkdir("x")` 产生 FOLDER_CREATED；`os.rmdir("x")` 产生 FOLDER_DELETED
- [ ] `os.rename("a", "b")` 产生 FOLDER_RENAMED，`old_path="a"`，`path="b"`
- [ ] `stop()` 在 1s 内干净返回，后台线程全部终止，无 hanging
- [ ] ctypes 函数正确设置 `argtypes` 与 `restype`，64-bit 无访问冲突

## Linux inotify 后端
- [ ] `backend="inotify"` 启动成功，`backend_name == "inotify"`（WSL/Linux）
- [ ] mkdir / rmdir / rename 分别产生对应事件
- [ ] epoll wait 非轮询（阻塞等待内核通知）
- [ ] `stop()` 1s 内返回

## FolderSubject / FolderObserver
- [ ] `FolderSubject` 是 `Subject` 的子类（`isinstance(fs, Subject)` 为 True）
- [ ] `FolderSubject(paths=[tmpdir])` 可 `with` 语法使用；退出后 `is_running == False`
- [ ] `FolderSubject.pipe(ops.filter(...)).subscribe(...)` 可链式组合
- [ ] 手动发射 FOLDER_CREATED/FOLDER_DELETED/FOLDER_RENAMED 事件：
  - 只触发对应回调
  - `on_folder_created` 收到 FOLDER_CREATED
  - `on_folder_deleted` 收到 FOLDER_DELETED
  - `on_folder_renamed` 收到 FOLDER_RENAMED（携带 old_path / path）
  - 不会错触发其他回调
- [ ] `with FolderObserver(...).attach(fs): ...` 退出后 subscription 正确取消
- [ ] `FolderSubject.dispatcher` 可访问，`dispatch_count` 正确累计

## from_foldersystem / write_to_foldersystem
- [ ] `from_foldersystem([tmpdir])` 返回 `(observable, dispatcher)` 二元组
- [ ] 返回的 dispatcher 可 `start()` / `stop()`
- [ ] `write_to_foldersystem(tmpdir)` 在 pipe 中不抛异常
- [ ] 上游 FolderData/str/dict 均能被 write_to_foldersystem 正确处理
- [ ] 写入文件成功，下游收到新的 FolderData 事件

## 包导出
- [ ] `from vools.reactive import FolderChangeType, FolderData, FolderSubject, FolderObserver, FolderDispatcher, from_foldersystem, write_to_foldersystem` 无异常
- [ ] `vools.reactive.__all__` 包含以上所有符号

## 测试质量
- [ ] `pytest tests/test_reactive_folder_watcher.py -v` 在 Windows 全绿
- [ ] `pytest tests/test_reactive_folder_watcher.py -v` 在 WSL（Linux）全绿
- [ ] 非 Windows/Linux 测试分支正确 skip，并输出 skip 理由
- [ ] 每个事件类型至少有一个真实文件系统触发的测试
- [ ] 测试文件风格与 `tests/test_reactive_file_watcher.py` 一致

## 命名与风格
- [ ] 对外 API 命名前缀 `Folder*`，与 `File*` 系列一一对应
- [ ] `FolderData` 字段命名风格（`path`, `old_path`, `change_type`, `timestamp`, `sequence`, `tags`, `metadata`）
- [ ] 不引入第三方依赖，仅标准库
- [ ] 代码风格与 `file_watcher.py` 一致

## 资源与泄漏（可选验证）
- [ ] 启动-停止 100 次不产生 file handle leak（Windows Process Hacker 或任务管理器"句柄数"检查）
- [ ] 启动-停止 100 次不产生 thread leak（进程内线程数保持恒定）
- [ ] 空闲状态 CPU 占用 < 0.1%（非 polling 后端）
