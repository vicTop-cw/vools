# 键鼠监控模块 - The Implementation Plan (Decomposed and Prioritized Task List)

注意: 任务按依赖顺序排列。`backend="auto"` 在 Windows 下优先 win32，失败回退 polling。

## [x] Task 1: 数据类型基础设施（KeyEventType / MouseEventType / KeyModifier / KeyData / MouseData）
- **Priority**: P0
- **Depends On**: None
- **Description**:
  - 在 `vools/reactive/keyboard_mouse.py` 新增:
    - `KeyEventType(IntEnum)`: `KEY_DOWN=0 / KEY_UP=1 / KEY_HOLD=2`
    - `MouseEventType(IntEnum)`: `MOVE=0 / LEFT_DOWN=1 / LEFT_UP=2 / RIGHT_DOWN=3 / RIGHT_UP=4 / MIDDLE_DOWN=5 / MIDDLE_UP=6 / SCROLL=7 / DRAG=8`
    - `KeyModifier(IntFlag)`: `NONE=0 / SHIFT=1 / CTRL=2 / ALT=4 / WIN=8 / CAPSLOCK=16`
    - `@dataclass KeyData`: `key_code`, `key_name`, `is_press`, `modifiers`, `event_type`, `timestamp`, `sequence`, `window_title`, `tags`, `metadata`
    - `@dataclass MouseData`: `x`, `y`, `event_type`, `button`, `delta`, `timestamp`, `sequence`, `tags`, `metadata`
    - `.now(...)` / `.to_dict()` / `.from_dict()` / `.to_json()` / `.from_json()` / `.to_pickle()` / `.from_pickle()`
    - `_vk_code_to_name(vk_code)` 和 `_name_to_vk_code(name)` 键码映射（Windows VK codes）
    - `_make_key_signature()` / `_make_mouse_signature()` 去重签名函数
    - 全局 `_seq_counter = itertools.count(1)`
- **Acceptance Criteria Addressed**: AC-1, AC-2, AC-3
- **Test Requirements**:
  - `programmatic` TR-1.1: `int(KeyEventType.KEY_DOWN) == 0`, `int(MouseEventType.SCROLL) == 7`, `int(KeyModifier.CTRL) == 2`, `len(list(KeyEventType)) == 3`
  - `programmatic` TR-1.2: `KeyData.now(key_code=65, is_press=True)` 可创建；`event_type` 自动推导为 `KEY_DOWN`；`key_name` 非空
  - `programmatic` TR-1.3: `kd.to_json()` → `KeyData.from_json()` 往返，`key_code/sequence/tags/metadata` 一致
  - `programmatic` TR-1.4: `MouseData.now(x=100, y=200, event_type=MOVE)`，`button` 自动推导为 `"left"`（MOVE 默认）
  - `programmatic` TR-1.5: `_vk_code_to_name(0x41) == 'A'`, `_name_to_vk_code('ENTER') == 0x0D`
- **Notes**: 完全镜像 `clipboard.py` 和 `file_watcher.py` 的数据类型设计。

## [x] Task 2: 键盘模拟 I/O（Windows SendInput / Polling 保底）
- **Priority**: P0
- **Depends On**: Task 1
- **Description**:
  - Windows（`sys.platform == "win32"`）:
    - `_press_key(vk_code)`: `SendInput` 构造 KEYBDINPUT { vk_code, KEYEVENTF_KEYDOWN }
    - `_release_key(vk_code)`: KEYEVENTF_KEYUP
    - `_type_text(text)`: 遍历字符，用 `VkKeyScanW` 获取 vk_code，逐字 press+release
    - `_hotkey(*keys)`: 所有 key press → 所有 key release（中间不释放）
  - 非 Windows:
    - 空实现或 print 警告
  - `press(key: str|int)`, `release(key: str|int)`, `type_text(text: str)`, `hotkey(*keys: str)`
  - 自我过滤登记: `_register_self_signature(KeyData)`, `_pending_signatures: Dict[str, tuple]`
- **Acceptance Criteria Addressed**: AC-9
- **Test Requirements**:
  - `programmatic` TR-2.1: `press("A")` + `release("A")` 不抛异常（只验证 API 可调用，不验证实际系统行为）
  - `programmatic` TR-2.2: `type_text("abc")` 不抛异常
  - `programmatic` TR-2.3: `hotkey("Ctrl", "A")` 不抛异常
  - `human-judgment` TR-2.4: 手动打开记事本，调用 `type_text("hello")`，观察字符是否输入
- **Notes**: 参考 Rust 版本的 `io.rs` 设计，纯 ctypes 实现。

## [x] Task 3: 鼠标模拟 I/O（Windows SendInput / Polling 保底）
## [x] Task 4: 事件监控后端（Windows Hook / Polling）
## [x] Task 5: KeyboardDispatcher / MouseDispatcher
## [x] Task 6: KeySubject / MouseSubject
## [x] Task 7: KeyObserver / MouseObserver
## [x] Task 8: from_keyboard / from_mouse 工厂 + write 操作符
## [x] Task 9: vools.reactive 包导出
## [x] Task 10: 测试文件 tests/test_reactive_keyboard_mouse.py
## [x] Task 11: 端到端验证 & review
