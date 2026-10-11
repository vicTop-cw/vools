# Clipboard Monitor Dispatcher (Hook-Based + Self-Filter) - PRD

## Overview
- **Summary**: 在 `vools.reactive` 子包中新增一个**事件驱动**的剪贴板监控数据分发器（Clipboard Dispatcher）。它通过操作系统的剪贴板变更通知钩子（Windows `AddClipboardFormatListener` + Linux/macOS 回退到 polling）捕获变更事件，将每次变化封装为结构化的 `ClipData`，并通过 `on_change_data` 回调 + `Subject[ClipData]` 响应式流分发给下游。**关键能力**：下游通过 `set_clipboard()` / `ops.write_to_clipboard()` 写回剪贴板后，Dispatcher 默认自动过滤掉"自己写的那段内容"，避免循环触发；同时保留用户自定义过滤策略。
- **Purpose**: 解决"读→处理→写回剪贴板"这一常见自动化流程中的**循环触发**问题；提供一套标准的读写 API，避免用户自行调用 tkinter / win32clipboard 而导致的重复实现与兼容性问题。
- **Target Users**: 使用 `vools` 做 Python 自动化、响应式编程、文本处理流水线的开发者。

## Goals
- **G-1**: Windows 使用 `AddClipboardFormatListener` + 隐藏窗口做事件驱动 hook；Linux/macOS 走可选 GTK/pasteboard hook 或 `Event.wait(interval)` 保底。
- **G-2**: 提供标准写回 API `ClipboardDispatcher.set_clipboard(content, files=None, change_type=None, *, source=None, metadata=None) -> ClipData`。
- **G-3**: 默认开启 **self-filter**：通过 `set_clipboard()` 写入的内容会被 Dispatcher 记录为"自己人"，随后系统 hook 再次触发时，若内容 signature 匹配"自己人"，则丢弃不分发。
- **G-4**: 提供可插拔的 `self_filter: Callable[[ClipData], bool]` 回调，用户可自定义"哪些是自己人的"判断规则。
- **G-5**: 提供响应式操作符 `ops.write_to_clipboard(dispatcher, source=None)`，让下游能 `.pipe(ops.map(...), ops.write_to_clipboard(d))` 无缝接入。
- **G-6**: `ClipData` 支持 JSON / pickle 双向序列化；`ChangeType` 枚举明确。
- **G-7**: `vools/reactive/__init__.py` 显式导出新符号，保持与现有模块风格一致。

## Non-Goals (Out of Scope)
- 不提供 GUI（不做剪贴板管理器界面）。
- 不实现跨进程/跨机器剪贴板同步协议。
- 不做 OCR。
- 不实现云同步与历史数据库（但 `ClipData.metadata` 预留扩展字段）。
- 不强制用户使用某一过滤策略；`filter_self=False` 时行为与"纯观察者"一致。

## Background & Context

### 循环触发问题
```
用户 Ctrl+C → WM_CLIPBOARDUPDATE → Dispatcher 分发 ClipData("abc")
  → 下游 on_next("abc") → 调用 d.set_clipboard("ABC") → 系统剪贴板变化
    → WM_CLIPBOARDUPDATE 再次触发 → Dispatcher 又读到 "ABC" → 又分发给下游
      → 下游又写回 → 死循环 ♾️
```

标准解法有三类，本方案同时支持，默认启用最简单的 A：

| 方案 | 实现方式 | 适用场景 |
|---|---|---|
| **A. 签名簿（signature book）** | `set_clipboard()` 写回时计算 `(change_type, content_hash, len, tuple(files))` 登记进 `_self_signatures: deque[signature]`；`_dispatch_once()` 读取时命中就丢弃 | 简单、准确、不依赖 OS 特性 |
| **B. 自定义剪贴板格式** | 写回时额外注册一个私有 format（如 `"VoolsClipboardSource"`），读时检测该格式存在且 source 匹配即丢弃 | 更强的"我写的"识别，但 Win/Linux/mac 格式机制不同 |
| **C. 临时静默窗口** | 写回期间短暂 `RemoveClipboardFormatListener`，写后恢复 | 竞态风险，且期间真实用户操作会丢 |

本方案默认**方案 A**，并用 metadata `_source` / `_owner_seq` 作为**方案 A+** 的双保险（用户可写 `self_filter` 逻辑使用 metadata 做更复杂判断）。方案 B 留作未来扩展。

## Functional Requirements

- **FR-1**: `ChangeType(IntEnum)`: TEXT=0, FILES=1, IMAGE=2, HTML=3, RTF=4, CLEAR=5, OTHER=6。
- **FR-2**: `ClipData(@dataclass, slots=True)`：content(str\|bytes\|None)、files(list[str])、change_type、tags(list[str])、metadata(dict[str, Any])、timestamp(datetime)、sequence(int)。metadata 中 `_source`、`_owner_seq` 为保留字段，由 set_clipboard 自动写入；`_encoding: "base64"` 在 JSON 序列化 bytes 时自动写入。
- **FR-3**: `ClipData` 提供 `to_dict / from_dict / to_json / from_json / to_pickle / from_pickle`；`from_dict / from_json` 对缺失字段给默认值，未知字段忽略。
- **FR-4**: `ClipboardDispatcher(
  *, on_change_data=None, interval=0.2, change_types=None, tags=(),
  backend: Literal["auto","win32","gtk","pasteboard","polling"] = "auto",
  filter_self: bool = True, self_filter: Callable[[ClipData], bool] | None = None,
  self_source: str | None = None,
  self_signature_capacity: int = 32,
)`
  - `backend="auto"` 时按顺序尝试：win32 → gtk → pasteboard → polling。
  - 提供 `start() / stop() / is_running / subject / dispatch_count / error_count / duplicate_count / backend_name / self_source` 属性。
  - `on_change_data: Callable[[], ClipData] | None` 可读写属性；未设置或失败时回退默认实现。
  - `filter_self: bool` 可读写：True 时启用"signature 命中即丢弃"的自过滤（默认 True）。
  - `self_filter: Callable[[ClipData], bool] | None` 可读写：若设置，每次 `_dispatch_once()` 除 signature 判断外，额外调用此函数；返回 True 的 ClipData 被丢弃。
  - `self_source: str` 可读写：由 `set_clipboard()` 自动写入到 ClipData.metadata `_source` 字段；默认自动生成 `f"vools:{pid}:{id(self)}"`。
  - `self_signature_capacity: int` 可通过构造设置：`_self_signatures` 的 deque 最大容量（默认 32，FIFO）。
  - 支持上下文管理器 `with ClipboardDispatcher(...) as d:`。
- **FR-5 (Win32 Hook Backend)**: 在后台线程内：创建隐藏窗口 → `AddClipboardFormatListener(hwnd)` → `GetMessage` 循环；`WM_CLIPBOARDUPDATE` 到来时调用 `_dispatch_once()`；停止时 `RemoveClipboardFormatListener → DestroyWindow → UnregisterClass → 线程退出`。**ctypes 为首选实现**（零第三方依赖），pywin32 为备选。
- **FR-6 (Polling Backend)**: `Event.wait(interval)` 循环，每轮读一次剪贴板，调用 `_dispatch_once()`。
- **FR-7 (读取)**: 内部 `_ClipboardReader.read() -> (change_type, content, files, metadata)`；Windows 下优先枚举 CF_HDROP / CF_DIB / CF_HTML / CF_RTF / CF_UNICODETEXT；失败回落到 tkinter；再失败返回 `OTHER + {error}`。
- **FR-8 (signature 计算)**: `_make_signature(change_type, content, files) -> tuple`，用于 self-filter 去重。推荐实现：`(change_type, _stable_hash(content), len(content) if content else 0, tuple(files))`，其中 `_stable_hash` 对 str 使用 `hashlib.md5(s.encode('utf-8')).hexdigest()`，对 bytes 使用 `hashlib.md5(b).hexdigest()`，对 None 为 None。
- **FR-9 (self-filtering 机制)**:
  - `set_clipboard(...)` 写回时：① 调用底层写入；② 读取当前 signature；③ 把 signature 登记进 `_self_signatures`（deque，超过容量自动丢弃最旧）；④ 构造 ClipData，metadata 写入 `_source=self_source, _owner_seq=next(_seq_counter)`；⑤ **不通过 hook 路径**，直接把该 ClipData 投递到 subject（行为：写回即通知订阅者，但 self-filter 不会让"自己写的"再被 hook 二次分发）。
  - `_dispatch_once()` 流程：读取剪贴板 → 计算 signature → 若 `filter_self` 且 signature 在 `_self_signatures` 中 → 移除该签名并 return（`_self_filtered_count++`）→ 若 `self_filter` 已设置且返回 True → return（同上计数）→ 与上次 signature 比较（原去重）→ 构造 ClipData（优先 `on_change_data()`）→ subject.on_next → `dispatch_count++`。
- **FR-10**: `ClipboardDispatcher.set_clipboard(
  content: str | bytes | None = None,
  files: list[str] | None = None,
  change_type: ChangeType | None = None,
  *,
  source: str | None = None,
  tags: Iterable[str] = (),
  metadata: dict[str, Any] | None = None,
) -> ClipData`
  - 写回系统剪贴板；若 `change_type is None` 由 content/files 推断；若 `files` 非空则写 CF_HDROP；
  - 返回构造好的 `ClipData`（metadata 含 `_source`、`_owner_seq`）；
  - 写回的 signature 自动登记进 `_self_signatures`；
  - 写回后 **直接投递到 subject**（不走 hook → 读 → 分发路径），这样下游若监听 subject 也能立即收到"这是下游自己写回的"一条；但该条的 signature 已在 _self_signatures 中，随后 hook 触发 _dispatch_once() 会命中丢弃，不会导致 2 条或无限循环。
- **FR-11**: `_self_filtered_count: int` 只读属性（通过 `stats` 或直接属性暴露），记录被 self_filter 丢弃的次数，便于排障。
- **FR-12**: 顶层工厂函数 `from_clipboard(interval=..., backend="auto", on_change_data=None, change_types=None, tags=(), auto_start=True, filter_self=True, self_source=None) -> tuple[Observable[ClipData], ClipboardDispatcher]`。
- **FR-13**: 提供响应式操作符 `write_to_clipboard(dispatcher, source=None)`（Operator）：是一个 `Callable[[Observable[ClipData | str | tuple[...]]], Observable[ClipData]]`，它接收上游的 `ClipData` / `str` / `(content, files, change_type, tags, metadata)` tuple 等方便形式，内部调用 `dispatcher.set_clipboard(...)`，并把返回的 ClipData 继续向下游传递。
- **FR-14**: 与 `vools.reactive.ops.*` 所有现有算子完全兼容。

## Non-Functional Requirements
- **NFR-1 (低延迟)**: `WM_CLIPBOARDUPDATE` 到达 → subject 推送 P95 ≤ 10ms；polling 后端 ≤ 50ms。
- **NFR-2 (零空转)**: win32 后端空闲 CPU ≈ 0；仅系统消息触发时唤醒。
- **NFR-3 (线程安全)**: start/stop/subject/set_clipboard/属性访问内部 `RLock` 保护；不允许重复启动；stop 后可再次 start；内部线程干净退出。
- **NFR-4 (跨平台)**: Windows 上 win32 backend 默认完备；Linux/macOS 走 polling 路径正常运行。
- **NFR-5 (可选依赖)**: `pywin32 / PyGObject / pyobjc` 都是可选依赖；缺失不影响 `import vools.reactive`。
- **NFR-6 (可观测)**: `dispatch_count / error_count / duplicate_count / self_filtered_count` 计数器；`backend_name / self_source` 可查。
- **NFR-7 (序列化鲁棒)**: from_dict/from_json 缺失字段默认值，未知字段忽略；bytes JSON 往返一致。
- **NFR-8 (self-filter 鲁棒)**: `_self_signatures` deque 容量有限可配置，避免无限增长；重复命中同一 signature 也能正确移除。
- **NFR-9 (API 风格一致)**: `from __future__ annotations`、中文 docstring、`__slots__` 优先。

## Constraints
- **Technical**: Python ≥ 3.9；新增文件 `vools/reactive/clipboard.py`；新增 operator 一个到 `vools/reactive/operators.py`（或在 `clipboard.py` 定义再由 `operators.py` import 转发）；必须使用 `vools.reactive.Subject` 作为输出流。
- **Business**: 纯库能力，不引入常驻进程。
- **Dependencies**: 标准库 ctypes/threading/dataclasses/enum/json/pickle/base64/datetime/hashlib/collections.deque；可选 pywin32/PyGObject/pyobjc。

## Assumptions
- Windows ≥ Vista（支持 `AddClipboardFormatListener`）。
- 每次剪贴板变化都会触发 `WM_CLIPBOARDUPDATE` 1 次或多次（"先清空再写入"会触发 2 次），由 self-filter + content signature 去重共同处理。
- 用户 `on_change_data` 回调轻量；抛异常不中断消息线程。
- 外部恰好写入**完全相同**内容的概率极低，可接受被误判为 self（误判时丢弃该条）；用户可随时 `filter_self=False` 或写 `self_filter` 自定义规则。

## Acceptance Criteria

### AC-1: ChangeType 枚举完备
- **Given**: 安装 vools
- **When**: `from vools.reactive import ChangeType; list(ChangeType)`
- **Then**: TEXT/FILES/IMAGE/HTML/RTF/CLEAR/OTHER 共 7 个；int 值 0~6；可与 int 互相转换。
- **Verification**: `programmatic`

### AC-2: ClipData JSON 往返
- **Given**: 含文本 + 文件路径列表 + tags + bytes content 的 ClipData
- **When**: `ClipData.from_json(d.to_json())`
- **Then**: content/files/change_type/tags 一致；timestamp 毫秒精度不丢失；metadata `_source`、`_owner_seq` 字段可还原。
- **Verification**: `programmatic`

### AC-3: ClipData pickle 往返
- **Given**: 含 bytes content 的 ClipData
- **When**: pickle 往返
- **Then**: bytes content 完全一致。
- **Verification**: `programmatic`

### AC-4: Dispatcher 可启动与停止
- **Given**: Windows 环境
- **When**: `d = ClipboardDispatcher(); d.start(); d.stop()`
- **Then**: `d.backend_name == "win32"`；is_running 先 True 后 False；stop 后线程干净退出，无残留 HWND。
- **Verification**: `programmatic`

### AC-5: 写回 → 不循环触发（核心）
- **Given**: 已启动的 Dispatcher + 订阅者计数
- **When**: 外部写入 "hello"（触发 1 条）→ 订阅者调用 `d.set_clipboard("HELLO")`（写回）→ 等待 ≥ 200ms 确保系统通知已到
- **Then**: subject 最终总共只收到 2 条 ClipData：① content="hello"（原始）② content="HELLO"（由 set_clipboard 直接投递）；self_filtered_count ≥ 1；dispatch_count == 2；不会出现第 3、第 4 条。
- **Verification**: `programmatic`

### AC-6: filter_self=False 时不做自过滤
- **Given**: `d = ClipboardDispatcher(filter_self=False)` 已启动
- **When**: 写 "a" → `set_clipboard("B")` → 写 "c"
- **Then**: subject 可能收到 3 条以上（系统写回通知会被当作新事件）；即 self-filter 关闭后行为退化为"纯观察者"。
- **Verification**: `programmatic`

### AC-7: self_filter 自定义回调生效
- **Given**: `d.self_filter = lambda data: data.metadata.get("_source") == "evil"` 已设置
- **When**: 构造一条 metadata `_source="evil"` 的内容并通过 set_clipboard 写入
- **Then**: 该条即使 signature 不命中，也会被 self_filter 丢弃，`self_filtered_count += 1`。
- **Verification**: `programmatic`

### AC-8: 自定义 self_source
- **Given**: `d = ClipboardDispatcher(self_source="my-app-1")`
- **When**: `d.set_clipboard("x")`
- **Then**: 返回的 ClipData.metadata `_source == "my-app-1"`；`_owner_seq` 是单调整数。
- **Verification**: `programmatic`

### AC-9: ops.write_to_clipboard 可管道式接入
- **Given**: `import vools.reactive as rx; obs, d = rx.from_clipboard()`
- **When**: `obs.pipe(rx.ops.filter(lambda x: x.change_type == ChangeType.TEXT), rx.ops.map(lambda x: x.content.strip().upper()), rx.ops.write_to_clipboard(d, source="upper-pipe")).subscribe()`
- **Then**: 外部复制 "hello" 后，系统剪贴板变为 "HELLO"；subject 只收到 1 条原始 + 1 条写回，不再循环。
- **Verification**: `programmatic`

### AC-10: 线程安全 / 上下文管理器
- **Given**: 多线程并发 start/stop/set_clipboard 20 次
- **When**: 运行
- **Then**: 无 deadlock，无 RuntimeError；最终 `is_running == False`。
- **Verification**: `programmatic`

### AC-11: 代码风格一致
- **Given**: 代码评审者审查 `clipboard.py` 与 `__init__.py` 修改
- **Then**: `from __future__ annotations`；中文 docstring；公共 API 显式 `__all__`；可选依赖 try/except 隔离。
- **Verification**: `human-judgment`

## Open Questions
- [ ] `_self_signatures` 默认容量 32 是否合适？要不要做更聪明的"只保留最近 N 秒"的策略？
- [ ] 是否需要实现"方案 B"自定义剪贴板格式（更强的 self 识别，但跨平台复杂度高）？
- [ ] `set_clipboard()` 返回的 ClipData 是否应该**默认投递到 subject**（当前规划是投递），还是只做"静默写回"？
- [ ] 是否提供 `d.reset_stats()` 用于测试或日志轮转？

## 对外 API 速查（给实现者的最终接口表）

```python
# 位于 vools/reactive/clipboard.py，由 __init__.py 再导出
class ChangeType(IntEnum):
    TEXT = 0; FILES = 1; IMAGE = 2; HTML = 3; RTF = 4; CLEAR = 5; OTHER = 6

@dataclass(slots=True)
class ClipData:
    content: str | bytes | None
    files: list[str]
    change_type: ChangeType
    tags: list[str]
    metadata: dict[str, Any]
    timestamp: datetime
    sequence: int

    # 类方法 / 实例方法
    @classmethod
    def now(cls, content=None, files=None, change_type=ChangeType.TEXT, tags=(), metadata=None) -> ClipData: ...
    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, d: dict) -> ClipData: ...
    def to_json(self, **kw) -> str: ...
    @classmethod
    def from_json(cls, s: str, **kw) -> ClipData: ...
    def to_pickle(self, path: str) -> None: ...
    @classmethod
    def from_pickle(cls, path: str) -> ClipData: ...

class ClipboardDispatcher:
    def __init__(
        self, *,
        on_change_data: Callable[[], ClipData] | None = None,
        interval: float = 0.2,
        change_types: Iterable[ChangeType] | None = None,
        tags: Iterable[str] = (),
        backend: Literal["auto", "win32", "gtk", "pasteboard", "polling"] = "auto",
        filter_self: bool = True,
        self_filter: Callable[[ClipData], bool] | None = None,
        self_source: str | None = None,
        self_signature_capacity: int = 32,
    ): ...

    # 生命周期
    def start(self) -> None: ...
    def stop(self) -> None: ...
    @property
    def is_running(self) -> bool: ...
    def __enter__(self) -> ClipboardDispatcher: ...
    def __exit__(self, exc_type, exc, tb) -> None: ...

    # 写回
    def set_clipboard(
        self, content: str | bytes | None = None,
        files: list[str] | None = None,
        change_type: ChangeType | None = None,
        *, source: str | None = None,
        tags: Iterable[str] = (),
        metadata: dict[str, Any] | None = None,
    ) -> ClipData: ...

    # 响应式输出
    @property
    def subject(self) -> Subject[ClipData]: ...

    # 可配置（运行时可改）
    on_change_data: Callable[[], ClipData] | None
    filter_self: bool
    self_filter: Callable[[ClipData], bool] | None
    self_source: str

    # 诊断
    @property
    def backend_name(self) -> str: ...
    @property
    def dispatch_count(self) -> int: ...
    @property
    def error_count(self) -> int: ...
    @property
    def duplicate_count(self) -> int: ...
    @property
    def self_filtered_count(self) -> int: ...

# 顶层工厂
def from_clipboard(
    *, interval=0.2, backend="auto", on_change_data=None,
    change_types=None, tags=(), auto_start=True,
    filter_self=True, self_source=None,
) -> tuple[Observable[ClipData], ClipboardDispatcher]: ...

# 响应式操作符（同目录 operators.py 或 clipboard.py 内定义，由 __init__.py 再导出）
def write_to_clipboard(
    dispatcher: ClipboardDispatcher, source: str | None = None,
) -> Callable[[Observable[Any]], Observable[ClipData]]: ...
```
