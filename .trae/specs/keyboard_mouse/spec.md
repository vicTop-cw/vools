# 键鼠监控模块 (Keyboard & Mouse) - Product Requirement Document

## Overview
- **Summary**: 在 `vools.reactive` 包中新增 `keyboard_mouse` 模块，提供键盘/鼠标输入监控与模拟 API，包含 `KeySubject`/`KeyObserver`、`MouseSubject`/`MouseObserver`，采用原生操作系统钩子（Windows: `SetWindowsHookExW(WH_KEYBOARD_LL/WH_MOUSE_LL)` / Linux/macOS: Polling 回退）实现真正的事件驱动，不使用轮询。
- **Purpose**: 为响应式数据流链路提供键鼠事件监控能力，支持热键组合、鼠标移动/点击/滚轮/拖拽、键鼠模拟输入。
- **Target Users**: 自动化测试工程师、桌面应用开发者、需要键鼠事件流的 Python 脚本作者。

## Goals
1. 提供 `KeySubject` + `KeyObserver` + `MouseSubject` + `MouseObserver` 响应式 API
2. 提供 `KeyEventType(IntEnum)` 和 `MouseEventType(IntEnum)` 表达键鼠事件类型
3. 提供 `KeyModifier(IntFlag)` 位标志表达修饰键（SHIFT/CTRL/ALT/WIN/CAPSLOCK）
4. 提供 `KeyData` / `MouseData` 结构化数据类，支持 JSON/Pickle 往返序列化
5. 提供事件驱动（非轮询）后端：Windows Hook（WH_KEYBOARD_LL / WH_MOUSE_LL），Linux/macOS 回退 Polling
6. 提供键盘模拟：`press(key)`, `release(key)`, `type_text(text)`, `hotkey(keys...)`
7. 提供鼠标模拟：`move_to(x, y)`, `click(button)`, `scroll(delta)`, `double_click()`, `move_relative(dx, dy)`
8. 提供 `from_keyboard()` / `from_mouse()` 工厂函数
9. 提供 `write_to_keyboard()` / `write_to_mouse()` 响应式操作符
10. 通过 Windows 与 WSL 环境下的完整测试

## Non-Goals (Out of Scope)
- 不做游戏级别的反作弊绕过
- 不实现 OCR / 图像识别辅助
- 不做跨进程的窗口过滤（仅监听全局事件）
- 不实现复杂的宏录制/回放脚本语言（保留给上层 Python）
- 不实现 macOS CGEvent API（macOS 本质回退 polling）

## Background & Context
- 现有 `vools.reactive.clipboard` 已验证 Windows Hook + 隐藏窗口消息循环的 Subject + Operator 模式
- 现有 `vools.reactive.file_watcher` 已验证 ReadDirectoryChangesW + 后端抽象架构
- Rx-Rust 项目已有 Rust/PyO3 版本的键鼠模块，设计可参考
- 用户要求「同样的模式」：Python 纯标准库实现，ctypes 调用系统 API
- Windows + WSL 两个测试环境必须通过

## Functional Requirements

### FR-1: 事件类型枚举
- `KeyEventType(IntEnum)`: `KEY_DOWN=0 / KEY_UP=1 / KEY_HOLD=2`
- `MouseEventType(IntEnum)`: `MOVE=0 / LEFT_DOWN=1 / LEFT_UP=2 / RIGHT_DOWN=3 / RIGHT_UP=4 / MIDDLE_DOWN=5 / MIDDLE_UP=6 / SCROLL=7 / DRAG=8`
- `KeyModifier(IntFlag)`: `NONE=0 / SHIFT=1 / CTRL=2 / ALT=4 / WIN=8 / CAPSLOCK=16`

### FR-2: KeyData @dataclass
- 字段: `key_code`, `key_name`, `is_press`, `modifiers`, `event_type`, `timestamp`, `sequence`, `window_title`, `tags`, `metadata`
- `.now(...)` 工厂类方法自动填充 timestamp/sequence
- `.to_dict()` / `.from_dict()` / `.to_json()` / `.from_json()` / `.to_pickle()` / `.from_pickle()` 往返转换
- `event_type` 自动从 `is_press` 推导（is_press=True → KEY_DOWN, is_press=False → KEY_UP）
- `key_name` 通过 `_vk_code_to_name()` 映射 VK_CODE → 字符串名称

### FR-3: MouseData @dataclass
- 字段: `x`, `y`, `event_type`, `button`, `delta`, `timestamp`, `sequence`, `tags`, `metadata`
- `.now(...)` 工厂类方法
- `.to_dict()` / `.from_dict()` / `.to_json()` / `.from_json()` / `.to_pickle()` / `.from_pickle()`
- `button` 自动从 `event_type` 推导（LEFT_DOWN/LEFT_UP → "left", RIGHT_* → "right", MIDDLE_* → "middle"）

### FR-4: KeyboardDispatcher
- `backend="auto"|"win32"|"polling"`
- `start()` / `stop()` / `is_running` / `backend_name` / `dispatch_count` / `error_count` / `self_filtered_count`
- `filter_self=True` 启用自我过滤（模拟操作产生的事件被丢弃）
- `subject` 属性返回 `Subject[KeyData]`
- `press(key)`, `release(key)`, `type_text(text)`, `hotkey(keys...)`, `tap(key)`
- `with KeyboardDispatcher(...) as kbd:` 上下文管理器

### FR-5: MouseDispatcher
- `backend="auto"|"win32"|"polling"`
- `start()` / `stop()` / `is_running` / `backend_name` / `dispatch_count` / `error_count` / `self_filtered_count`
- `filter_self=True` 启用自我过滤
- `subject` 属性返回 `Subject[MouseData]`
- `move_to(x, y)`, `click(button="left")`, `scroll(delta)`, `double_click(button="left")`, `move_relative(dx, dy)`
- `with MouseDispatcher(...) as mse:` 上下文管理器

### FR-6: KeySubject — 继承 Subject[KeyData]
- 内部持有 KeyboardDispatcher
- `with KeySubject(...) as ks:` 上下文管理器
- `start()` / `stop()` / `backend_name` / `dispatch_count` / `self_filtered_count`
- `press()` / `type_text()` / `hotkey()` 代理

### FR-7: MouseSubject — 继承 Subject[MouseData]
- 内部持有 MouseDispatcher
- `with MouseSubject(...) as ms:` 上下文管理器
- `move_to()` / `click()` / `scroll()` 代理

### FR-8: KeyObserver — 按 KeyEventType 路由
- `on_press`, `on_release`, `on_hold`, `on_any` 回调
- `subscribe(observable)` 返回 Subscription
- `with KeyObserver(...).attach(ks):` 链式用法

### FR-9: MouseObserver — 按 MouseEventType 路由
- `on_move`, `on_click`, `on_scroll`, `on_drag`, `on_any` 回调
- `subscribe(observable)` 返回 Subscription
- `with MouseObserver(...).attach(ms):` 链式用法

### FR-10: from_keyboard / from_mouse 工厂
- `from_keyboard(*, backend="auto", filter_self=True, auto_start=True) -> Tuple[Observable[KeyData], KeyboardDispatcher]`
- `from_mouse(*, backend="auto", filter_self=True, auto_start=True) -> Tuple[Observable[MouseData], MouseDispatcher]`

### FR-11: write_to_keyboard / write_to_mouse 操作符
- 接收上游流（KeyData/str/dict/int）
- write_to_keyboard: str → type_text, int → key_code 按下+释放, dict → {"key":"A"} 或 {"key_code":65,"is_press":true}
- write_to_mouse: dict → {"x":..,"y":..,"event":"move"|"click"|"scroll"} 或 MouseData

### FR-12: 事件驱动后端
- **Windows**: `SetWindowsHookExW(WH_KEYBOARD_LL)` + 隐藏窗口消息循环 + 后台线程；`SetWindowsHookExW(WH_MOUSE_LL)` 同理
- **Linux/macOS**: polling 后端（定期读取 `GetAsyncKeyState` / `GetCursorPos`），回退路径
- 所有后端统一回调 `on_change_key(...)` / `on_change_mouse(...)`，再通过 Dispatcher 分发

### FR-13: vools.reactive 包导出
- 在 `vools/reactive/__init__.py` 中: `KeyEventType`, `KeyModifier`, `KeyData`, `MouseEventType`, `MouseData`, `KeyboardDispatcher`, `MouseDispatcher`, `KeySubject`, `MouseSubject`, `KeyObserver`, `MouseObserver`, `from_keyboard`, `from_mouse`, `write_to_keyboard`, `write_to_mouse`

## Non-Functional Requirements

### NFR-1: 性能
- 事件分发延迟 < 50ms（Windows Hook 后端）
- 空闲状态 CPU 使用率 < 0.1%（Hook 驱动，非轮询）
- 持续 1000 事件/分钟不丢失

### NFR-2: 稳定性
- `stop()` 能在 500ms 内正确终止所有后台线程
- 不产生未关闭句柄（hook handle leak）
- 对无 GUI 环境（WSL/Linux server）优雅降级

### NFR-3: 可维护性
- 与 `clipboard.py` / `file_watcher.py` 保持一致的代码风格与模式
- 不使用任何第三方依赖，纯标准库 + ctypes

## Constraints
- **技术**: Python 3.10+，仅标准库，ctypes 访问 OS API
- **平台**: Windows 10/11，WSL2 Ubuntu，macOS 12+（后两者在可用环境中测试）
- **依赖**: `vools.reactive.subject.Subject` / `vools.reactive.observable.Observable`

## Assumptions
- Windows 用户有足够权限安装低级键盘/鼠标钩子（通常不需要管理员）
- Python 进程在桌面会话中运行（非服务/无头）
- 键鼠模拟在 Windows 上使用 `SendInput` API

## Acceptance Criteria

### AC-1: 键盘事件类型可被 Python 访问
- **Given**: 已导入 `vools.reactive`
- **When**: 检查 `int(KeyEventType.KEY_DOWN)`, `int(KeyEventType.KEY_UP)`, `int(KeyEventType.KEY_HOLD)`
- **Then**: 值为 0/1/2；`str(KeyEventType.KEY_DOWN) == "KEY_DOWN"`
- **Verification**: `programmatic`

### AC-2: KeyData 往返序列化
- **Given**: `kd = KeyData.now(key_code=65, is_press=True)`
- **When**: `j = kd.to_json(); kd2 = KeyData.from_json(j)`
- **Then**: `kd2.key_code == kd.key_code == 65`，`kd2.is_press == True`，`kd2.event_type == KeyEventType.KEY_DOWN`
- **Verification**: `programmatic`

### AC-3: MouseData 往返序列化
- **Given**: `md = MouseData.now(x=100, y=200, event_type=MouseEventType.MOVE)`
- **When**: 同上 JSON 往返
- **Then**: `md2.x == 100`，`md2.event_type == MouseEventType.MOVE`
- **Verification**: `programmatic`

### AC-4: KeySubject 生命周期 & 属性
- **Given**: `with KeySubject(backend="polling") as ks:`
- **When**: 检查 `ks.backend_name`, `isinstance(ks, Subject[KeyData])`, `ks.dispatcher` 非空
- **Then**: 全部断言通过；退出 with 块后 `ks.is_running == False`
- **Verification**: `programmatic`

### AC-5: KeyObserver 按类型路由
- **Given**: KeyObserver 已创建，`on_press` / `on_release` 回调
- **When**: 手动向 Subject 发射 `KEY_DOWN` / `KEY_UP` 两个事件
- **Then**: 分别触发 `on_press` / `on_release` 回调，不触发其他回调
- **Verification**: `programmatic`

### AC-6: MouseObserver 按类型路由
- **Given**: MouseObserver 已创建，`on_move` / `on_click` / `on_scroll` 回调
- **When**: 手动向 Subject 发射 MOVE / LEFT_DOWN / SCROLL 事件
- **Then**: 分别触发对应回调
- **Verification**: `programmatic`

### AC-7: 自我过滤
- **Given**: `KeyboardDispatcher(backend="polling", filter_self=True)`
- **When**: 注册一个签名，`_dispatch_once(KeyData(...))` 触发
- **Then**: `self_filtered_count == 1`，`dispatch_count == 0`
- **Verification**: `programmatic`

### AC-8: from_keyboard / from_mouse 工厂
- **Given**: `obs, disp = from_keyboard(backend="polling", auto_start=False)`
- **When**: `obs.subscribe(cb)`; `disp.start()`; `disp.stop()`
- **Then**: 全部方法可调用，不抛异常
- **Verification**: `programmatic`

### AC-9: write_to_keyboard / write_to_mouse 操作符
- **Given**: `write_to_keyboard(disp)` 在 pipe 中
- **When**: 上游传入 `{"key": "A"}` 或 `KeyData(...)`
- **Then**: 不抛异常（模拟操作只验证不崩溃）
- **Verification**: `programmatic`

### AC-10: vools.reactive 包导出
- **Given**: `from vools.reactive import KeyEventType, KeyData, KeyboardDispatcher, ...`
- **When**: 导入所有符号
- **Then**: 无 ImportError
- **Verification**: `programmatic`

## Open Questions
- [ ] Linux 后端是否需要 `inotify` 或 `/dev/input` 事件源？（计划 v1 只用 polling）
- [ ] 是否需要支持"按键阻止传播"（LowLevelKeyboardProc 的 eat-key）？默认不阻止
- [ ] 热键绑定（HotKey）是否作为单独 API？（计划先做原始事件流，热键在 Python 层组合）
