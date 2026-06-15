# 键鼠模块 (keyboard_mouse.py) 安全审计与代码优化报告

> **审计对象**: `vools/reactive/keyboard_mouse.py` (2260 行)
> **审计范围**: 数据类型层、Win32 Hook 后端、Polling 后端、SendInput 模拟 I/O、事件分发器、Subject/Observer 层、顶层操作符
> **审计方法**: 静态代码分析 + 逻辑推理 + 运行时行为分析

---

## 目录

1. [安全漏洞 (Security Vulnerabilities)](#1-安全漏洞)
2. [优化机会 (Optimization Opportunities)](#2-优化机会)
3. [代码质量与可维护性](#3-代码质量与可维护性)
4. [测试策略建议](#4-测试策略建议)

---

## 1. 安全漏洞

### V1: Pickle 反序列化 —— 任意代码执行  [严重]

**位置**: `KeyData.from_pickle()` (L379-384)、`MouseData.from_pickle()` (L484-489)

**描述**: `pickle.loads()` 在不可信数据上调用可导致任意代码执行。当前直接透传调用者的字节流，没有任何限制。

```python
# 现状 (L382-384)
@classmethod
def from_pickle(cls, b: bytes) -> "KeyData":
    return pickle.loads(b)  # 危险！可执行任意代码
```

**风险**: 如果用户通过 `from_pickle` 加载了外部来源的 pickle 数据（如从网络、文件、IPC 接收），攻击者可构造恶意 pickle payload，在 `pickle.loads()` 过程中执行任意系统命令。

**影响**: 远程代码执行 (RCE) | CVSS 9.8

**修复建议**:

```python
import pickle as _pickle

# 选项 A: 添加安全警告并约束 unpickler
_UNTRUSTED_PICKLE_WARNED = False

@classmethod
def from_pickle(cls, b: bytes, *, trusted: bool = False) -> "KeyData":
    if not trusted:
        global _UNTRUSTED_PICKLE_WARNED
        if not _UNTRUSTED_PICKLE_WARNED:
            log.warning("from_pickle(trusted=False) 对不可信数据不安全")
            _UNTRUSTED_PICKLE_WARNED = True
    return _pickle.loads(b)
```

### V2: 全局低级键盘/鼠标钩子 —— 隐私与横向移动风险  [高]

**位置**: `_KeyboardHookBackend._run()` (L689-720)、`_MouseHookBackend._run()` (L788-819)

**描述**: `SetWindowsHookExW(WH_KEYBOARD_LL)` 和 `SetWindowsHookExW(WH_MOUSE_LL)` 安装的是**全局低级钩子**，捕获**所有**进程的键鼠事件，包括密码输入、聊天内容、银行转账等敏感信息。

```python
# L696 - 全局键盘钩子，无需 DLL，在当前进程的消息循环中处理
hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, callback, None, 0)
```

**风险**:
- 该模块的任何使用者都可能无意中记录用户密码、信用卡号等
- 恶意 Python 脚本可借此实现隐蔽的键盘记录器
- 杀毒软件可能将使用该模块的脚本标记为恶意软件

**影响**: 信息泄露 | CVSS 7.5

**缓解建议**:

```python
# 在文档首部增加醒目警告
"""
.. warning::
    keyboard_mouse 模块在 Windows 下使用全局低级钩子 (WH_KEYBOARD_LL / WH_MOUSE_LL)
    来捕获键鼠事件。**该钩子会捕获所有进程的键盘输入和鼠标操作**。

    请勿在以下场景使用:
    - 需要处理密码、支付信息的应用
    - 用户未明确同意的监控场景
    - 生产环境的服务/守护进程

    使用此模块的开发者应在用户文档中披露此行为。
"""

# hook_proc 中不应记录或持久化按键内容
def _hook_proc(self, nCode: int, wParam: int, lParam: int) -> int:
    if nCode >= 0:
        # 仅转发，不记录、不持久化
        ...
```

### V3: 自过滤签名竞争条件  [中]

**位置**: `KeyboardDispatcher._dispatch_once()` (L1297-1324)、`_register_self_signature()` (L1327-1330)

**描述**: 自过滤签名队列的 `in` 检查和 `remove()` 之间没有原子锁，且 `_dispatch_once` 在 Hook 回调线程中调用，`_register_self_signature` 在用户线程调用。

```python
# 线程 A (hook 回调线程): _dispatch_once
if self.filter_self and sig in self._self_signatures:
    try:
        self._self_signatures.remove(sig)  # ← 可能被线程 B 先移除
    except ValueError:
        pass                              # ← 静默吞异常
    self._self_filtered_count += 1
    return

# 线程 B (用户线程): press
with self._lock:
    kd = KeyData.now(...)
    self._register_self_signature(kd)  # ← 不持有锁
    _send_key(vk, True)
```

**风险**: 竞态窗口导致:
1. 事件被错误地自过滤（签名已被消费，但新事件撞上残留签名）
2. 事件未被过滤（本应丢弃的事件被放行，导致"自己触发的回调仍然触发"）
3. `remove()` 抛 ValueError 但被 `except: pass` 静默吞掉，诊断困难

**影响**: 事件丢失或重复 | 功能性缺陷

**修复建议**:

```python
# 方案: 对 _self_signatures 的访问全部纳入 _lock
def _dispatch_once(self, kd: KeyData) -> None:
    sig = _make_key_signature(kd)

    with self._lock:  # ← 统一锁定队列访问
        # 自过滤
        if self.filter_self and sig in self._self_signatures:
            self._self_signatures.remove(sig)
            self._self_filtered_count += 1
            return

        # 自定义 self_filter
        if self.self_filter is not None:
            try:
                if self.self_filter(kd):
                    self._self_filtered_count += 1
                    return
            except Exception as e:
                log.debug("self_filter 异常: %s", e)
                self._error_count += 1

        try:
            self._subject.on_next(kd)
        except Exception as e:
            log.debug("subject.on_next 异常: %s", e)
            self._error_count += 1
        self._dispatch_count += 1
```

### V4: 签名时间窗口过粗导致误过滤  [中]

**位置**: `_make_key_signature()` (L512-514)

**描述**: 签名中的 `timestamp // 500` 将时间分辨率降低到 500ms 窗口。如果用户在 500ms 内连续按下/释放同一个键，第二次会被误判为"自己发出的"而丢弃。

```python
def _make_key_signature(kd: KeyData) -> Tuple:
    return (kd.key_code, kd.is_press, kd.timestamp // 500)  # 500ms 窗口！
```

**影响**: 快速连击时事件被错误过滤

**修复建议**: 引入自增序号代替模糊时间戳

```python
_SIG_COUNTER: "itertools.count" = itertools.count(1)

def _register_self_signature(self, kd: KeyData) -> None:
    # 使用唯一序号而非时间戳窗口
    sig = (kd.key_code, kd.is_press, next(_SIG_COUNTER))
    self._self_signatures.append(sig)
```

### V5: `_send_mouse_click` 按钮条件恒成立  [低]

**位置**: `_send_mouse_click()` (L1135-1141)

**描述**: `if button in ("left", "left")` —— 两个值都是 `"left"`，第二个条件是死代码。同样 `"right"` 也重复。这意味着**所有按钮条件都会匹配第一个分支**，鼠标右键/中键点击实际发送的是左键事件。

```python
def _send_mouse_click(button: str) -> None:
    if button in ("left", "left"):       # ← 恒等于 if button == "left"
        down_flag = MOUSEEVENTF_LEFTDOWN
        up_flag = MOUSEEVENTF_LEFTUP
    elif button in ("right", "right"):   # ← 永远进不来
        ...
    elif button in ("middle", "middle"): # ← 永远进不来
        ...
```

**影响**: 右键/中键点击功能被静默破坏（退化为左键） | 功能性 Bug

**修复**:

```python
def _send_mouse_click(button: str) -> None:
    down_flag = up_flag = 0
    if button == "left":
        down_flag, up_flag = MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP
    elif button == "right":
        down_flag, up_flag = MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
    elif button == "middle":
        down_flag, up_flag = MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP
    else:
        return
    ...
```

### V6: SendInput 无错误处理  [低]

**位置**: `_send_key()` (L1069-1076)、`_send_mouse_move()` (L1115-1126)、`_send_mouse_click()` (L1129-1153)、`_send_mouse_scroll()` (L1156-1162)

**描述**: `SendInput` 的返回值（实际注入的事件数）被完全忽略。在 UAC 提权对话框、锁屏、远程桌面等场景下，`SendInput` 可能被 UIPI (User Interface Privilege Isolation) 拦截或者返回 0，调用者不会得知模拟失败。

```python
user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))
# 返回值被丢弃，无法感知注入失败
```

**风险**: 模拟操作静默失败，自动化流程以为操作成功实际未执行

**修复建议**:

```python
def _send_key(vk_code: int, is_press: bool) -> bool:
    if sys.platform != "win32" or user32 is None:
        return False
    flags = 0 if is_press else KEYEVENTF_KEYUP
    ki = _KEYBDINPUT(wVk=vk_code, wScan=0, dwFlags=flags, time=0, dwExtraInfo=None)
    inp = _INPUT(type=INPUT_KEYBOARD, u=_INPUT_UNION(ki=ki))
    result = user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))
    if result == 0:
        log.debug("SendInput 失败 (UIPI 拦截或权限不足): VK=%d", vk_code)
    return result > 0
```

---

## 2. 优化机会

### O1: Polling 后端 CPU 占用过高  [性能]

**位置**: `_KeyboardPollingBackend._run()` (L906-945)

**描述**: 每 50ms 遍历 254 个虚拟键码调用 `GetAsyncKeyState`。在低负载系统上：
- 每秒 20 次 × 254 = 5080 次 Win32 API 调用
- 每次遍历都重新创建 `kd = KeyData.now(...)` 对象
- 即使在非 Windows 平台也创建线程并空转（尽管不产生事件）

```python
vk_range = list(range(1, 255))       # 硬编码全部键码
while not self._stop.is_set():
    for vk in vk_range:               # 每 50ms 扫描 254 个键
        state = user32.GetAsyncKeyState(vk) & 0x8000
```

**优化方案**:

```python
# 方案: 使用可变时间间隔 + 仅扫描"活跃"键
# 1. 初始只扫描用户订阅过的键（按需注册）
# 2. 空闲时每 200ms 扫描一次，检测到事件后加速到 30ms
# 3. 3 秒无事件后恢复低频率

class _KeyboardPollingBackend:
    def __init__(self, ...):
        self._active_keys: Set[int] = set()   # 只扫描这些键
        self._idle_interval = 0.2     # 空闲时
        self._active_interval = 0.03  # 有事件时
        self._last_event_time = 0.0

    def watch_key(self, vk: int) -> None:
        self._active_keys.add(vk)

    @property
    def _current_interval(self) -> float:
        if time.time() - self._last_event_time < 3.0:
            return self._active_interval
        return self._idle_interval
```

### O2: KeyboardHook/MouseHook 大量代码重复  [可维护性]

**位置**: `_KeyboardHookBackend` (L650-744) 与 `_MouseHookBackend` (L750-860)

**描述**: 两个后端除了 hook 类型、钩子过程和 MSG 结构外，线程管理、start/stop、消息循环完全一致。~110 行重复代码。

```python
# 所有代码行除了 WH_xxx 常量和 callback 名之外完全重复
self._thread = threading.Thread(target=self._run, daemon=True, name="kbd-hook")
# vs
self._thread = threading.Thread(target=self._run, daemon=True, name="mouse-hook")
```

**优化方案**: 抽取公共基类

```python
class _BaseWin32HookBackend(ABC):
    """共享的 Win32 Hook 基类"""

    def __init__(self, callback, hook_type: int, thread_name: str):
        self._callback = callback
        self._hook_type = hook_type
        self._thread_name = thread_name
        self._hook = None
        self._thread_id = None
        self._thread = None
        self._running = False
        self._stop_event = threading.Event()

    def start(self) -> None:
        ...  # 共用 start 逻辑

    def stop(self) -> None:
        ...  # 共用 stop 逻辑

    def _run(self) -> None:
        ...  # 共用消息循环 (L689-720 + L788-819 合并)

    @abstractmethod
    def _hook_proc(self, nCode: int, wParam: int, lParam: int) -> int:
        ...


class _KeyboardHookBackend(_BaseWin32HookBackend):
    def __init__(self, on_key_event):
        super().__init__(on_key_event, WH_KEYBOARD_LL, "kbd-hook")

    def _hook_proc(self, nCode, wParam, lParam):
        ...  # 仅键盘特有逻辑
```

### O3: `type_text` 中每字符循环加锁  [性能]

**位置**: `KeyboardDispatcher.type_text()` (L1358-1375)

**描述**: 文本输入的每个字符都执行 `with self._lock` 进入/退出临界区两次（按下+释放）。输入长文本（如 "hello world" 12 字符）需要 24 次锁操作。

```python
for ch in text:
    if isinstance(ch, str) and len(ch) == 1:
        vk = _name_to_vk_code(ch)
        if vk:
            with self._lock:       # ← 每字符锁两次
                ...
                with self._lock:   # ← 二次加锁
                    ...
```

**优化方案**: 锁外查表，锁内批量注册

```python
def type_text(self, text: str) -> None:
    # 预计算所有 key_data（不持锁）
    entries = []
    for ch in text:
        if isinstance(ch, str) and len(ch) == 1:
            vk = _name_to_vk_code(ch)
            if vk:
                entries.append((vk, True))
                entries.append((vk, False))
            else:
                # Unicode fallback
                _send_text(ch)
                continue

    # 批量签名注册（一次锁）
    with self._lock:
        for vk, is_press in entries:
            kd = KeyData.now(key_code=vk, is_press=is_press)
            self._register_self_signature(kd)

    # 免锁发送（持锁会导致 SendInput 被 IO 延迟阻塞）
    for vk, is_press in entries:
        _send_key(vk, is_press)
        time.sleep(0.01)
```

### O4: `_send_text` 的 O(n) 查表  [性能]

**位置**: `_send_text()` (L1079-1112)

**描述**: 对每个非字母数字字符遍历整个 `_VK_CODE_NAMES` 字典（~60 项）。构建反向映射可降到 O(1)。

```python
for code, name in _VK_CODE_NAMES.items():  # O(n) 查表
    if name == ch.upper():
        ...
```

**优化方案**: 构建反向映射表

```python
# 模块级预计算
_NAME_TO_VK: Dict[str, int] = {v: k for k, v in _VK_CODE_NAMES.items()}

def _send_text(text: str) -> None:
    for ch in text:
        vk = _NAME_TO_VK.get(ch.upper())  # O(1)
        if vk is not None:
            ...
```

### O5: Subject → Dispatcher 订阅缺少资源清理  [资源泄漏]

**位置**: `KeySubject.__init__()` (L1881-1898)、`MouseSubject.__init__()` (L1966-1982)

**描述**: Subject 构造时订阅了 dispatcher 的事件流，但在 `stop()` 或 `__exit__()` 中没有清理这个内部 `_sub` 订阅。Subject 被 GC 前 dispatcher 可能仍然持有对 Subject 的引用。

```python
def __init__(self, ...):
    super().__init__()
    self._dispatcher = KeyboardDispatcher(...)
    self._sub = self._dispatcher.subject.subscribe(  # ← 永远不会 unsubscribe
        on_next=self.on_next,
        on_error=self.on_error,
    )
```

**影响**: 循环引用导致内存泄漏，GC 无法回收

**修复**:

```python
def stop(self) -> None:
    if self._sub is not None:
        try:
            self._sub.unsubscribe()
        except Exception:
            pass
        self._sub = None
    self._dispatcher.stop()

def __del__(self) -> None:
    try:
        self.stop()
    except Exception:
        pass
```

### O6: `_get_window_title` 每次调用分配缓冲区  [微优化]

**位置**: `_get_window_title()` (L258-270)

**描述**: 每次创建新的 1024 宽字符缓冲区。在 Hook 路径中（每按键/鼠标事件一次）产生显著 GC 压力。

```python
buf = ctypes.create_unicode_buffer(length)  # 每次分配 2KB
user32.GetWindowTextW(hwnd, buf, length)
```

**优化方案**: 使用线程局部缓存

```python
import threading

_WINDOW_TITLE_BUF = threading.local()

def _get_window_title() -> str:
    if sys.platform != "win32":
        return ""
    try:
        buf = getattr(_WINDOW_TITLE_BUF, "buf", None)
        if buf is None or len(buf) < 1024:
            buf = ctypes.create_unicode_buffer(1024)
            _WINDOW_TITLE_BUF.buf = buf

        hwnd = user32.GetForegroundWindow()
        user32.GetWindowTextW(hwnd, buf, 1024)
        return buf.value or ""
    except Exception:
        return ""
```

---

## 3. 代码质量与可维护性

### 3.1 已发现问题

| ID | 类型 | 位置 | 问题 | 严重性 |
|----|------|------|------|--------|
| Q1 | 死代码 | `_send_mouse_click` L1135-1141 | `button in ("left", "left")` 重复条件 | 中 |
| Q2 | 死代码 | `KeyboardDispatcher.type_text` L1361 | `isinstance(ch, str)` 在 `for ch in text` 中恒为 True | 低 |
| Q3 | 类型提示 | `MouseDispatcher.drag` L1606 | `button` 参数持锁不一致：`self.move_to()` 内部持锁，但 `_send_mouse_click` 后手动释放 | 低 |
| Q4 | 日志级别 | 全部 hook_proc | 异常仅 `log.debug` 记录，生产环境不可见 | 低 |
| Q5 | 未达标 | `_KeyboardHookBackend._run` L696 | `SetWindowsHookExW` 返回 `HHOOK` 类型但存为 `Optional[int]` | 低 |
| Q6 | 未达标 | `KeyboardDispatcher.press` L1338 | `if not vk: return` 静默空返回，用户不知输入无效 | 低 |

---

## 4. 测试策略建议

### 4.1 安全漏洞验证测试

```python
# test_security.py — 安全专项测试

def test_pickle_untrusted_safety():
    """V1: 验证 pickle 加载不可信数据时给出警告"""
    kd = KeyData(key_code=65, is_press=True)
    pk = kd.to_pickle()

    import warnings
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        kd2 = KeyData.from_pickle(pk, trusted=False)
        assert any("不安全" in str(msg.message) for msg in w), \
            "should warn about untrusted pickle"

def test_hook_scope_documented():
    """V2: 验证模块文档包含 Hook 风险披露"""
    import inspect
    doc = inspect.getdoc(KeyboardDispatcher)
    assert "WH_KEYBOARD_LL" in doc or "全局" in doc, \
        "module doc must disclose global hook risk"

def test_signature_race_condition():
    """V3: 测试自过滤签名在高并发下的正确性"""
    from concurrent.futures import ThreadPoolExecutor
    d = KeyboardDispatcher(backend="polling", filter_self=True)
    results = []

    def simulate_user_press(vk):
        kd = KeyData.now(key_code=vk, is_press=True)
        d._register_self_signature(kd)
        d._dispatch_once(kd)
        results.append(d.self_filtered_count)

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(simulate_user_press, 65 + i) for i in range(20)]

    # 所有 20 次都应被过滤
    assert d.self_filtered_count == 20, \
        f"Expected 20 filtered, got {d.self_filtered_count}"
```

### 4.2 功能正确性测试

```python
# test_correctness.py

def test_send_mouse_click_all_buttons():
    """V5: 验证所有鼠标按钮点击功能"""
    from unittest.mock import patch
    with patch("vools.reactive.keyboard_mouse._send_mouse_click") as mock:
        d = MouseDispatcher(backend="polling")
        d.click("right")
        mock.assert_called_with("right")

def test_self_filter_exact_timing():
    """V4: 验证连续快速按键不被误过滤"""
    d = KeyboardDispatcher(backend="polling", filter_self=True)
    # 模拟 10ms 间隔的两次按键
    kd1 = KeyData(key_code=65, is_press=True, timestamp=1000)
    kd2 = KeyData(key_code=65, is_press=True, timestamp=1010)

    d._register_self_signature(kd1)
    d._dispatch_once(kd1)    # 应被过滤
    assert d.self_filtered_count == 1

    d._dispatch_once(kd2)    # 新事件不应被过滤（签名已消费）
    assert d.dispatch_count == 1, \
        f"Second press should NOT be filtered, got dispatch={d.dispatch_count}"
```

### 4.3 性能基准测试

```python
# test_benchmark.py

def test_polling_cpu_overhead():
    """O1: 验证 polling 后端 CPU 占用在合理范围"""
    import psutil
    import os

    proc = psutil.Process(os.getpid())
    cpu_start = proc.cpu_percent(interval=0.5)

    d = KeyboardDispatcher(backend="polling", interval=0.05)
    d.start()
    time.sleep(1.0)
    cpu_peak = proc.cpu_percent(interval=0.5)
    d.stop()

    assert cpu_peak - cpu_start < 5.0, \
        f"CPU spike too high: {cpu_peak - cpu_start:.1f}%"

def test_unicode_text_throughput():
    """O3: 验证 Unicode 文本输入吞吐量"""
    d = KeyboardDispatcher(backend="polling")
    text = "你好世界! @#$%^&*()" * 10  # ~200 chars

    start = time.perf_counter()
    d.type_text(text)
    elapsed = time.perf_counter() - start

    # 200 字符应该在 5 秒内完成（单线程模拟）
    assert elapsed < 5.0, \
        f"type_text too slow: {elapsed:.2f}s for {len(text)} chars"
```

### 4.4 回归测试清单

| 场景 | 测试点 | 优先级 |
|------|--------|--------|
| Windows Hook 启动/停止 | 重复 start/stop 不崩溃 | P0 |
| Polling 后端非 Windows | 在 Linux/macOS 下不崩溃 | P0 |
| 自过滤机制 | 模拟操作不触发本分发的回调 | P0 |
| 右键模拟 | `MouseDispatcher.click("right")` 实际触发右键 | P0 |
| 连续按键 | 50ms 内两次按 A，第二次不被过滤 | P1 |
| 长文本 | 1000 字符 Unicode 输入不抛异常 | P1 |
| 并发订阅 | 10 线程同时 subscribe/dispose | P1 |
| 内存泄漏 | Subject 析构后 dispatcher 线程被回收 | P2 |
| Hook 异常恢复 | Hook 安装失败后自动切换到 polling | P2 |

---

## 总结

| 级别 | 数量 | 关键项 |
|------|:----:|--------|
| 🔴 严重 | 1 | V1: Pickle RCE |
| 🟠 高 | 1 | V2: 全局 Hook 隐私风险 |
| 🟡 中 | 2 | V3: 竞态条件、V4: 签名窗口误过滤 |
| 🟢 低 | 4 | V5: 按钮坏代码、V6: SendInput 无反馈、Q1-Q2 |
| ⚡ 优化 | 6 | O1-O6 性能、内存、可维护性优化 |

**建议优先级**: 先修复 V5 (右键功能 Bug) 和 V3 (竞态条件) 的功能问题，再进行 V1 (Pickle) 和 V2 (文档披露) 的安全加固，最后实施 O1-O6 的性能优化。
