# FolderWatcher - 文件夹监控分发器 - Product Requirement Document

## Overview
- **Summary**: 在 `vools.reactive` 包中新增 `folder_watcher` 模块，提供文件夹级别的事件驱动监控与响应式分发 API，包含 `FolderSubject`、`FolderObserver`、`FolderChangeType`、`FolderData`、`FolderDispatcher`，采用原生操作系统钩子（Windows: `ReadDirectoryChangesW` / macOS: `FSEvents` / Linux: `inotify`）实现真正的事件驱动，不使用轮询。
- **Purpose**: 为响应式数据流链路提供以目录为粒度的事件监控能力，聚焦目录级事件（文件夹创建/删除/重命名/移入/移出/属性变化/内容变化），弥补 `file_watcher` 在文件粒度上无法清晰表达"目录自身变更"这一语义。
- **Target Users**: 需要按目录级别追踪文件系统变化的开发者（如工程化工具、代码编辑器、配置管理系统、热更新服务）。

## Goals
1. 提供 `FolderSubject` + `FolderObserver` 响应式 API，支持在现有 reactive 链路中直接订阅目录变更
2. 提供 `FolderChangeType(IntEnum)` 表达 7+ 种目录级事件
3. 提供事件驱动（非轮询）后端，三平台均使用 OS 原生钩子
4. 提供 `from_foldersystem()` 工厂与流式 `write_to_foldersystem()` 操作符
5. 通过 Windows 与 WSL 环境下的完整测试

## Non-Goals (Out of Scope)
- 不做文件级监控（这是 `file_watcher.py` 的范围）
- 不做跨主机/分布式文件系统监控（只支持本地文件系统）
- 不做持久化事件日志（只有 in-memory event dispatch）
- 不做递归深度限制的用户配置（默认递归子目录；polling 后端按需扩展）
- 不做速率限制（throttling/debounce）交给 reactive 操作符组合

## Background & Context
- 现有 `vools.reactive.file_watcher` 已实现 `ReadDirectoryChangesW`/`FSEvents`/`inotify` 三后端
- 现有 `vools.reactive.clipboard` 已验证 Subject + Operator 模式
- 用户要求「同样的模式」: `FolderSubject`/`FolderObserver`，类似 FileSubject/FileObserver 的约定
- 需要异步支持（后台线程非阻塞），支持 `with` 语法
- Windows + WSL 两个测试环境必须通过

## Functional Requirements

### FR-1: FolderChangeType 枚举
系统 SHALL 提供 `FolderChangeType(IntEnum)`：
```
FOLDER_CREATED = 0   # 目录被创建
FOLDER_DELETED = 1   # 目录被删除
FOLDER_RENAMED = 2   # 目录被重命名（old_path → new_path）
FOLDER_MOVED_IN = 3  # 目录从外部移入
FOLDER_MOVED_OUT = 4 # 目录从监控目录中移出
FOLDER_ATTRIB = 5    # 目录属性变化 (权限、时间戳)
FOLDER_CONTENT = 6   # 目录下的内容变化（新增/删除文件，未触发以上）
```

### FR-2: FolderData @dataclass
- 字段: `path`、`old_path`、`change_type`、`file_count`、`child_folder_count`、`timestamp`、`sequence`、`tags`、`metadata`
- `.now(...)` 工厂类方法自动填充 timestamp/sequence
- `.to_dict()` / `.from_dict()` / `.to_json()` / `.from_json()` 往返转换
- bytes 字段在 JSON 中 base64 编码

### FR-3: FolderDispatcher
- `backend="auto"|"win32"|"macos"|"inotify"|"polling"`
- `add_path(path)` / `remove_path(path)` 动态增删
- `stop()` 幂等
- `subject` 属性返回 Subject[FolderData]，支持 `.pipe(...).subscribe(...)`
- `with FolderDispatcher(...) as d:` 上下文管理器

### FR-4: FolderSubject — 继承 Subject[FolderData]
- 内部持有 FolderDispatcher
- `with FolderSubject(paths=[...]) as fs: ...`
- `start()`/`stop()` 暴露 Dispatcher 的生命周期
- `backend_name` 属性透传
- `dispatch_count` 属性透传

### FR-5: FolderObserver — 按 FolderChangeType 路由
- `on_folder_created`/`on_folder_deleted`/`on_folder_renamed`/`on_folder_moved_in`/`on_folder_moved_out`/`on_folder_attrib`/`on_folder_content`/`on_any` 回调
- `subscribe(observable)` 返回 Subscription
- `with FolderObserver(...).attach(folder_subject): ...` 链式用法

### FR-6: from_foldersystem 工厂
返回 `(Observable[FolderData], FolderDispatcher)`，用法：
```python
obs, d = from_foldersystem(["./src", "./tests"])
obs.pipe(ops.filter(...)).subscribe(...)
d.start()
```

### FR-7: write_to_foldersystem 操作符
- 接收上游流（FolderData/str/dict）
- 写入到目标目录
- 产生新的 FolderData 事件发往下游
- 支持 `mode="create"|"append"|"overwrite"`

### FR-8: 事件驱动后端（三平台）
- **Windows**: `ReadDirectoryChangesW` + I/O Completion Port + 后台线程（纯 ctypes，无轮询）
- **macOS**: `FSEvents` API + 后台线程（纯 ctypes）
- **Linux/WSL**: `inotify_init` + `inotify_add_watch` + `select.epoll`（纯 ctypes，无轮询）
- 所有后端回调 `on_change(path, old_path, change_type, is_directory=True)`
- 任一后端不可用时回退到 polling 保底（仅在显式 `backend="auto"` 时）

### FR-9: vools.reactive 包导出
- 在 `vools/reactive/__init__.py` 中: `FolderChangeType`、`FolderData`、`FolderSubject`、`FolderObserver`、`FolderDispatcher`、`from_foldersystem`、`write_to_foldersystem`

## Non-Functional Requirements

### NFR-1: 性能
- 事件分发延迟 < 500 ms（从 OS 产生事件到 Subject 发出）
- 监控 1000 个目录时，内存占用 < 150 MB
- 空闲状态 CPU 使用率 < 0.1%（事件驱动，不轮询）

### NFR-2: 稳定性
- `stop()` 能在 500 ms 内正确终止所有后台线程
- 不产生未关闭句柄（file handle leak）
- 对不存在的路径和权限不足的路径优雅降级（不抛异常，记录 warning log）

### NFR-3: 可维护性
- 与 `file_watcher.py` 保持一致的代码风格与模式（可 copy pattern）
- 不使用任何第三方依赖，纯标准库 + ctypes

## Constraints
- **技术**: Python 3.10+，仅标准库，ctypes 访问 OS API
- **业务**: 需与现有 reactive 子包风格一致；命名前缀 `Folder`
- **依赖**: `vools.reactive.subject.Subject` / `vools.reactive.observable.Observable`
- **平台**: Windows 10/11，WSL2 Ubuntu，macOS 12+（后两者在可用环境中测试）

## Assumptions
- Windows hook 可正确过滤目录事件（通过 `FILE_ACTION_*` + `is_directory` 过滤，参考 FileData 已有的字段）
- Linux inotify 通过 `IN_ISDIR` 掩码位来判定目录事件
- macOS FSEvents 通过 `kFSEventStreamEventFlagItemIsDir` 判定
- 用户在 Windows 有文件系统写权限（测试用临时目录）

## Acceptance Criteria

### AC-1: FolderChangeType 枚举成员正确
- **Given**: 已导入 `vools.reactive`
- **When**: 检查 `int(FolderChangeType.FOLDER_CREATED)`、`int(FolderChangeType.FOLDER_DELETED)` 等
- **Then**: 值为 0/1/2/3/4/5/6 的预期整数；`isinstance(..., IntEnum) == True`
- **Verification**: `programmatic`

### AC-2: FolderData 往返序列化
- **Given**: 创建一个 `FolderData.now(path=...)`
- **When**: 执行 `j = fd.to_json(); fd2 = FolderData.from_json(j)`
- **Then**: `fd2.path == fd.path`，`fd2.change_type == fd.change_type`，`fd2.sequence == fd.sequence`
- **Verification**: `programmatic`

### AC-3: FolderSubject 生命周期 & 属性
- **Given**: `with FolderSubject(paths=[tmpdir], backend="polling") as fs:`
- **When**: 检查 `fs.backend_name`、`isinstance(fs, Subject[FolderData])`、`fs.dispatcher` 非空
- **Then**: 全部断言通过；退出 with 块后 `fs.is_running == False`
- **Verification**: `programmatic`

### AC-4: FolderObserver 按类型路由
- **Given**: Subject 与 Observer 已创建
- **When**: 手动向 Subject 发射 FOLDER_CREATED / FOLDER_DELETED / FOLDER_RENAMED 三个事件
- **Then**: 分别触发 on_folder_created / on_folder_deleted / on_folder_renamed 回调，不触发其他回调
- **Verification**: `programmatic`

### AC-5: Windows Hook 后端触发真实目录事件
- **Given**: Windows 环境，在临时目录下启动 FolderDispatcher(backend="win32")
- **When**: 测试代码在临时目录下 `os.mkdir("new_folder")` → `os.rmdir("new_folder")` → `os.rename("a","b")`
- **Then**: 收到 `FOLDER_CREATED` + `FOLDER_DELETED` + `FOLDER_RENAMED` 事件；stop 无阻塞
- **Verification**: `programmatic`

### AC-6: Linux inotify 后端触发真实目录事件
- **Given**: WSL/Linux 环境，临时目录 + `FolderDispatcher(backend="inotify")`
- **When**: 同上，mkdir/rmdir/rename
- **Then**: 收到对应的 FOLDER_CREATED / FOLDER_DELETED / FOLDER_RENAMED
- **Verification**: `programmatic`

### AC-7: from_foldersystem + write_to_foldersystem 工厂与操作符
- **Given**: `obs, d = from_foldersystem([tmpdir])`
- **When**: `obs.pipe(ops.filter(...), write_to_foldersystem(tmpdir, mode="create")).subscribe(...)`
- **Then**: 不抛异常，产生下游 FolderData 事件，文件写入成功
- **Verification**: `programmatic`

### AC-8: 动态 add_path / remove_path
- **Given**: 已启动 FolderDispatcher
- **When**: add_path(new_dir) → 在 new_dir 下创建子目录 → remove_path(new_dir)
- **Then**: add 后能收到新子目录事件，remove 后不再收到
- **Verification**: `programmatic`

### AC-9: 命名一致性（human review）
- **Given**: diff 文件
- **When**: 检查所有对外 API 命名（类名、字段名、枚举值）
- **Then**: 命名前缀 Folder*，与 File* 系列风格 100% 一致
- **Verification**: `human-judgment`

## Open Questions
- [ ] `FolderData` 是否需要 `file_count` / `child_folder_count` 字段？如果需要，统计发生在读取事件时（对大目录有性能代价）
- [ ] `write_to_foldersystem` 的"写入文件"语义是否与 `write_to_filesystem` 完全一致？或 FolderSubject 只关心目录级的写入？
- [ ] 是否需要在 `folder_watcher.py` 中直接引用/复用 `file_watcher.py` 的后端实现？还是完全独立的新模块（推荐，避免紧密耦合）？我倾向独立。
