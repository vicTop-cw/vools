# Clipboard Monitor Dispatcher (Hook-Based + Self-Filter) - Implementation Plan

## [ ] Task 1: 定义数据类型（ChangeType 枚举 + ClipData + 序列化）
- **Priority**: high
- **Depends On**: None
- **Description**:
  - 新建 `vools/reactive/clipboard.py`，定义：
    - `ChangeType(IntEnum)`: TEXT=0, FILES=1, IMAGE=2, HTML=3, RTF=4, CLEAR=5, OTHER=6。
    - `ClipData` 使用 `@dataclass(slots=True)`，字段同 spec.md；类级 `_seq_counter = itertools.count(1)`；工厂 `ClipData.now(**kwargs)` 自动填充 `timestamp=datetime.now()` 和 `sequence=next(_seq_counter)`。
    - 序列化：`to_dict / from_dict / to_json / from_json / to_pickle / from_pickle`。JSON 下 bytes 以 base64 传输，dict 中带 `_encoding: "base64"` 标记。
    - `from_dict / from_json`：缺失字段使用默认值（空 list、空 dict、当前时间、新 sequence）；未知字段忽略；`change_type` 字段同时支持 int 和 str（`"TEXT"` 或 `0`）。
- **Acceptance Criteria Addressed**: AC-1, AC-2, AC-3, NFR-7
- **Test Requirements**:
  - `programmatic` TR-1.1: `list(ChangeType)` 返回长度 7，int 值 0~6。
  - `programmatic` TR-1.2: 文本 ClipData 的 `to_json → from_json` 往返后 content/files/change_type/tags 一致；timestamp 误差 ≤ 1s。
  - `programmatic` TR-1.3: bytes content 的 ClipData JSON 往返后 bytes 完全相等；`_encoding` 标记在 dict 中可见。
  - `programmatic` TR-1.4: pickle 往返一致。
  - `programmatic` TR-1.5: from_dict 对缺失的 `files/tags/metadata` 字段给出默认空容器；对未知字段忽略不报 KeyError。
  - `human-judgement` TR-1.6: docstring 与命名风格符合 vools.reactive。

## [ ] Task 2: 剪贴板读写 Adapter（Win ctypes + pywin32 备选 + tkinter 回退 + 写回）
- **Priority**: high
- **Depends On**: Task 1
- **Description**:
  - 内部类 `_ClipboardReader`，方法 `read(self) -> tuple[ChangeType, str|bytes|None, list[str], dict[str, Any]]`。
  - Windows 首选 ctypes 路径：
    - `user32 = ctypes.windll.user32`；`kernel32 = ctypes.windll.kernel32`
    - `OpenClipboard(0) → EnumClipboardFormats(0) 循环`；优先顺序：
      - `CF_HDROP (15)` → 使用 `DragQueryFileW` 获取文件路径列表
      - `CF_DIB (8)` → `GetClipboardData + GlobalLock/Size/Unlock` 获取原始 bytes（DIB bitmap）
      - `CF_HTML` → 需 `RegisterClipboardFormatW("HTML Format")`，读取 HTML 片段
      - `CF_RTF` → 同上 `"Rich Text Format"`
      - `CF_UNICODETEXT (13)` → 读为 str
      - `CF_TEXT (1)` → 读为 str（回退）
    - `CloseClipboard()`
  - 跨平台回退：`tkinter.Tk().withdraw()` → `clipboard_get()`；图片路径若失败则记录到 metadata.error。
  - 空剪贴板 → `ChangeType.CLEAR`；所有读取异常 → `OTHER + {"error": ...}`。
  - 内部方法 `_write(self, content, files, change_type) -> None`：
    - files 非空 → `CF_HDROP` 写入（需构造 DROPFILES + 双 null 结尾路径数组）。
    - content 为 str → `CF_UNICODETEXT` 或 tkinter `clipboard_clear/clipboard_append/update`。
    - content 为 bytes → 根据 change_type 写 `CF_DIB` 或自定义格式。
    - tkinter 路径作为最低回退。
  - 提供一个便捷函数 `_write_text(text: str)` 供测试直接写回。
  - 所有可选依赖 try/except ImportError 隔离。
- **Acceptance Criteria Addressed**: AC-5, AC-8 的前置、FR-6/FR-7、NFR-5
- **Test Requirements**:
  - `programmatic` TR-2.1: `_write_text("hello") → reader.read()` 返回 change_type=TEXT, content=="hello"。
  - `programmatic` TR-2.2: 模拟一个失败场景（比如强制关闭 clipboard 句柄）→  reader 返回 OTHER 且 metadata 含 error。
  - `programmatic` TR-2.3: `_write(files=[p1,p2])` → reader.read() 返回 FILES 且 files 列表含 p1/p2（Windows + pywin32 或 ctypes HDROP 支持）。
  - `human-judgement` TR-2.4: 所有依赖可选；非 Windows 环境也能 import 无报错。

## [ ] Task 3: 实现 Win32 Hook Backend（隐藏窗口 + AddClipboardFormatListener + 消息循环）
- **Priority**: high
- **Depends On**: Task 2
- **Description**:
  - 内部类 `_Win32HookBackend`：
    - 构造：`__init__(self, on_change: Callable[[], None])`；`_thread: Thread | None`；`_stop_event: Event`；`_hwnd: int | None`；`_wnd_class_atom: int | None`；`_running: bool`。
    - `start()`：加锁；若已 running 直接 return；启动 daemon 线程 `_thread = Thread(target=self._run, daemon=True); _thread.start()`。
    - `stop()`：加锁；`_stop_event.set()`；`PostMessageW(hwnd, WM_CLOSE, 0, 0)` 唤醒消息循环；`_thread.join(timeout=2)`（超时不阻塞）；清理 `_hwnd=None`。
    - `_run()`：线程内：
      1. 注册窗口类：`WNDCLASSEXW` + `RegisterClassExW` → 存 atom
      2. 创建窗口：`CreateWindowExW(WS_EX_TOOLWINDOW, atom, "VoolsClipboardHidden", 0, 0, 0, 0, HWND_MESSAGE, 0, 0, None)`（使用 HWND_MESSAGE 让它完全不可见）
      3. 调用 `AddClipboardFormatListener(hwnd)`
      4. 消息循环：`while GetMessageW(MSG, hwnd, 0, 0): TranslateMessage; DispatchMessageW`；或等价 PumpWaitingMessages 形式；关键是 GetMessageW 在线程外发送 WM_CLOSE 时能退出
      5. 退出时：`RemoveClipboardFormatListener(hwnd); DestroyWindow(hwnd); UnregisterClassW(atom_or_name, 0)`
    - `_wnd_proc(hwnd, msg, wparam, lparam)`：
      - msg == `WM_CLIPBOARDUPDATE (0x031D)` → `self._on_change()`；return 0
      - msg == `WM_CLOSE / WM_DESTROY` → `PostQuitMessage(0)` 触发消息循环退出；return 0
      - other → `return DefWindowProcW(hwnd, msg, wparam, lparam)`
    - `_on_change()`：简单代理到外部 on_change（由 Dispatcher 注入）。
  - 提供可选 `_Win32PyWin32Backend` 类（与上面同接口但用 win32gui/win32clipboard 实现）作为备选；自动探测并择优使用。
- **Acceptance Criteria Addressed**: AC-4, NFR-1, NFR-2, NFR-3
- **Test Requirements**:
  - `programmatic` TR-3.1: start → 写文本 → on_change 回调触发 1 次；stop 后再写文本不会触发。
  - `programmatic` TR-3.2: 连续 start/stop 5 次，无异常、不挂住；is_running 先 True 后 False 循环。
  - `programmatic` TR-3.3: 在无 pywin32 的环境中 ctypes 路径也能工作（可 monkeypatch import 测试）。

## [ ] Task 4: 实现 Polling Backend（保底路径，Event.wait 而不是 time.sleep）
- **Priority**: medium
- **Depends On**: Task 3
- **Description**:
  - 内部类 `_PollingBackend(on_change, interval)`：
    - `_thread: Thread | None`；`_stop_event: Event`；`_running: bool`
    - `start()`：daemon 线程启动 `_run`。
    - `_run()`：`while not self._stop_event.is_set(): self._on_change(); self._stop_event.wait(self._interval)`。
    - `stop()`：`_stop_event.set(); _thread.join(timeout=interval*2)`。
  - 接口与 `_Win32HookBackend` 一致：`start() / stop() / is_running`。
- **Acceptance Criteria Addressed**: FR-11, AC-4
- **Test Requirements**:
  - `programmatic` TR-4.1: 启动 polling backend → 写文本 → on_change 被调用；stop 后不再调用。
  - `programmatic` TR-4.2: stop 后线程在 `interval*2` 内实际退出（通过 `thread.is_alive()` 验证）。

## [ ] Task 5: ClipboardDispatcher 主体（多 Backend + self-filter + set_clipboard + subject 分发）
- **Priority**: high
- **Depends On**: Task 3, Task 4
- **Description**:
  - 公共类 `ClipboardDispatcher`：
    - `_lock: RLock`；`_reader: _ClipboardReader`；`_subject: Subject[ClipData]`；`_backend: _Win32HookBackend | _PollingBackend | None`；`_backend_name: str`；`_interval: float`；`_change_types_allowed: set[ChangeType] | None`；`_tags: list[str]`；`_last_signature: tuple | None`；`_self_signatures: deque[tuple]`（`maxlen=self_signature_capacity`）；`_seq_counter: itertools.count`；`_dispatch_count: int=0`；`_error_count: int=0`；`_duplicate_count: int=0`；`_self_filtered_count: int=0`；`on_change_data: Callable[[], ClipData] | None`；`filter_self: bool`；`self_filter: Callable[[ClipData], bool] | None`；`self_source: str`（默认 `f"vools:{os.getpid()}:{id(self)}"`）。
    - `__init__(**kwargs)`：按 spec.md 签名；根据 backend 参数选择实际后端（"auto" → win32 探测 → gtk 探测 → pasteboard 探测 → polling 兜底）；失败路径都 try/except。
    - `_make_signature(change_type, content, files) -> tuple`：对 str 使用 `hashlib.md5(s.encode('utf-8')).hexdigest()`；对 bytes 使用 `hashlib.md5(b).hexdigest()`；None 时 `None`；返回 `(int(change_type), hash, len(content) if content else 0, tuple(files))`。
    - `_dispatch_once()`：内部流程同 spec.md FR-9；注意：**先过 self-filter 再去过 content signature 去重**，避免"外部写了相同内容"被错误地当作 self-filter 命中。
    - `_start_backend()` / `_stop_backend()`：由 start/stop 调用。
    - `start()`：加锁；若已 running return；选择 backend + 启动；标志 `_running=True`。
    - `stop()`：加锁；backend.stop；标志 `_running=False`。
    - `is_running`：`@property` return `_running and (backend and backend.is_running if backend else False)` 简化为 `bool(_backend and _backend.is_running)`。
    - `subject`、`backend_name`、`dispatch_count`、`error_count`、`duplicate_count`、`self_filtered_count`、`self_source`、`filter_self`、`self_filter`、`on_change_data` 都作为 `@property` 或普通属性暴露。
    - `__enter__ / __exit__` 支持 `with`。
  - **`set_clipboard(content=None, files=None, change_type=None, *, source=None, tags=(), metadata=None) -> ClipData`**（核心方法）：
    1. 内部 `with self._lock`：
    2. 推断 change_type：`files` 非空 → FILES；`isinstance(content, bytes)` → IMAGE/HTML/RTF；默认 TEXT。
    3. 调用底层 `_reader._write(content, files, change_type)` 实际写到系统剪贴板。
    4. 立即再次 `reader.read()` 一次拿到系统剪贴板当前内容，计算 signature（因为"写回后系统可能做转换"，需要读取实际被系统返回的数据作为签名依据）。
    5. signature 登记进 `_self_signatures`。
    6. 构造 ClipData：metadata 合并 `{**(metadata or {}), "_source": source or self._self_source, "_owner_seq": next(self._seq_counter)}`；change_type/tags 按参数/默认合并。
    7. `self._subject.on_next(clip_data)`；`self._dispatch_count += 1`。
    8. 返回 ClipData。
- **Acceptance Criteria Addressed**: AC-5, AC-6, AC-7, AC-8, AC-10, NFR-3, NFR-6, NFR-8
- **Test Requirements**:
  - `programmatic` TR-5.1: 外部写 "hello" → subject 收到 1 条 TEXT；然后订阅者在回调中 `set_clipboard("HELLO")`；等待 ≥ 200ms；最终 `dispatch_count == 2`（1 原始 + 1 set_clipboard 直接投递）；`self_filtered_count >= 1`（系统通知命中 self-signatures 被丢弃）。
  - `programmatic` TR-5.2: `filter_self=False`；外部写 "a"；`set_clipboard("B")`；外部写 "c"；dispatch_count 可能 ≥ 3（系统通知导致重复），验证 self-filter 关闭后行为。
  - `programmatic` TR-5.3: `self_filter = lambda d: d.metadata.get("_source") == "evil"`；构造一条 `_source="evil"` 的数据并调用 set_clipboard（注意此时 signature 路径仍然会命中）；然后**手动 monkeypatch 一个新 signature 不匹配**但 metadata `_source="evil"` 的 ClipData 让它走 _dispatch_once() → 被 self_filter 丢弃 → self_filtered_count += 1。
  - `programmatic` TR-5.4: `self_source="my-app-1"`；`set_clipboard("x")` 返回的 ClipData.metadata `_source == "my-app-1"` 且 `_owner_seq > 0`。
  - `programmatic` TR-5.5: 20 线程并发 `start()/stop()/set_clipboard()` 混合，无 deadlock / RuntimeError；最终 `is_running == False`。
  - `programmatic` TR-5.6: `with ClipboardDispatcher(...) as d:` 退出后 `d.is_running == False`。
  - `programmatic` TR-5.7: `_self_signatures` deque 的 maxlen == 构造参数 `self_signature_capacity`（默认 32）；写回超过容量时最旧的会被丢弃。

## [ ] Task 6: 顶层工厂函数 from_clipboard + 响应式操作符 write_to_clipboard
- **Priority**: high
- **Depends On**: Task 5
- **Description**:
  - `from_clipboard(*, interval=0.2, backend="auto", on_change_data=None, change_types=None, tags=(), auto_start=True, filter_self=True, self_source=None) -> tuple[Observable[ClipData], ClipboardDispatcher]`：
    1. 构造 `ClipboardDispatcher(...)`
    2. 若 auto_start → `dispatcher.start()`
    3. 返回 `(dispatcher.subject → 包装为 Observable？实际 Subject 已可 pipe；这里直接返回 subject 即可)`, dispatcher)` —— 实际看现有 Subject 是否天然支持 pipe 语义；如果 Subject 有 pipe 方法则直接返回；否则在函数里再包一层 `Observable(lambda observer: subject.subscribe(observer))` 也行。
  - `write_to_clipboard(dispatcher, source=None)`：
    - 是一个操作符工厂，返回 `Callable[[Observable[In]], Observable[ClipData]]`
    - 上游可接受三种形式：
      - **ClipData** → `dispatcher.set_clipboard(data.content, data.files, data.change_type, source=source or data.metadata.get("_source"), tags=data.tags, metadata=data.metadata)`
      - **str / bytes** → `dispatcher.set_clipboard(content=item, source=source)`
      - **tuple / dict** → 解包为 `set_clipboard(**dict)` 或按位置 `(content, files, change_type, tags, metadata)`
    - 对每个上游 item：try 调 set_clipboard 拿到 ClipData 下发；except 时调 `on_error` 或计数并跳过。
  - `write_to_clipboard` 定义在 `clipboard.py` 内，也被 `vools/reactive/operators.py` 或 `vools/reactive/__init__.py` 再导出，让用户可 `rx.ops.write_to_clipboard(...)` 或 `rx.write_to_clipboard(...)`。
- **Acceptance Criteria Addressed**: AC-9, FR-13, FR-14
- **Test Requirements**:
  - `programmatic` TR-6.1: `from_clipboard(auto_start=True)` 返回 (Observable, dispatcher)，且 dispatcher.is_running == True；之后 dispatcher.stop() 变为 False。
  - `programmatic` TR-6.2: `obs.pipe(ops.filter(lambda d: d.change_type==ChangeType.TEXT), ops.map(lambda d: d.content.strip().upper()), ops.write_to_clipboard(d, source="pipe-test")).subscribe(...)` → 写 "hello" 后系统剪贴板变 "HELLO"，且不会无限循环。
  - `programmatic` TR-6.3: ops.write_to_clipboard 接收 str / bytes / ClipData / tuple / dict 五种上游形式均能成功调用 set_clipboard 并下发 ClipData。
  - `human-judgement` TR-6.4: 代码风格与现有 vools.reactive operators 保持一致。

## [ ] Task 7: 修改 vools/reactive/__init__.py 导出新符号
- **Priority**: high
- **Depends On**: Task 5, Task 6
- **Description**:
  - 在 `vools/reactive/__init__.py`：
    - `from .clipboard import ChangeType, ClipData, ClipboardDispatcher, from_clipboard, write_to_clipboard`
    - 把 `ChangeType, ClipData, ClipboardDispatcher, from_clipboard` 加到顶层命名空间和 `__all__`
    - `write_to_clipboard` 同时加入 `ops` 命名空间（查看现有 ops 如何从 operators.py 统一引入；通常需要修改 `operators.py` 让它 import clipboard 中的算子，或让 `__init__.py` 在构建 `ops` 模块后动态注入）。
- **Acceptance Criteria Addressed**: AC-9, AC-11, NFR-9
- **Test Requirements**:
  - `programmatic` TR-7.1: `from vools.reactive import ChangeType, ClipData, ClipboardDispatcher, from_clipboard`；`from vools.reactive.ops import write_to_clipboard`；都能成功。
  - `human-judgement` TR-7.2: import 顺序和分组与现有风格一致。

## [ ] Task 8: 新建测试文件 tests/test_reactive_clipboard.py
- **Priority**: high
- **Depends On**: Task 1~7
- **Description**:
  - 组织为：
    1. `class TestChangeType`
    2. `class TestClipDataSerialization`（dict/JSON/pickle + bytes + 缺失字段）
    3. `class TestClipboardReaderWriter`（读写文本/文件列表）
    4. `class TestWin32Backend`（start/stop/触发回调；skipif non-Windows）
    5. `class TestPollingBackend`（保底路径；非 Windows 默认走这个）
    6. `class TestDispatcherSelfFilter`（核心：写回不循环；filter_self=False；自定义 self_filter；self_source 元信息）
    7. `class TestDispatcherThreading`（并发 start/stop/set_clipboard；上下文管理器）
    8. `class TestFromClipboardFactoryAndOps`（顶层工厂 + write_to_clipboard 操作符 pipe 接入）
  - 提供 pytest fixture `working_dispatcher()`：自动在 teardown 时 stop，避免残留线程。
- **Acceptance Criteria Addressed**: AC-1~AC-11
- **Test Requirements**:
  - `programmatic` TR-8.1: `pytest tests/test_reactive_clipboard.py -q` 全部通过。
  - `programmatic` TR-8.2: 非 Windows 平台 / 无 pywin32 时相关测试被正确 skip，不影响整体结果。
  - `human-judgement` TR-8.3: 测试命名/结构与 tests/test_reactive.py 风格一致。

## [ ] Task 9: 风格收尾与完善（docstring / __all__ / 日志）
- **Priority**: medium
- **Depends On**: Task 1~8
- **Description**:
  - `clipboard.py` 顶部中文模块 docstring 列出公共 API 并简述工作原理（hook + self-filter）。
  - 显式 `__all__ = ["ChangeType", "ClipData", "ClipboardDispatcher", "from_clipboard", "write_to_clipboard"]`。
  - 给 Dispatcher 的 self_filter / filter_self / set_clipboard / on_change_data 写中文 docstring。
  - 考虑可选：使用 `logging.getLogger("vools.reactive.clipboard")` 对错误路径、backend 选择、self-filter 命中做 debug 级别日志（默认不输出）。
- **Acceptance Criteria Addressed**: AC-11, NFR-9
- **Test Requirements**:
  - `human-judgement` TR-9.1: 文档/注释/命名风格一致。
  - `programmatic` TR-9.2: `__all__` 中列出的名字都能被正确 import。
