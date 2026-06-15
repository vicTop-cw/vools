# 键鼠监控模块 - Verification Checklist

## 数据类型层
- [x] `KeyEventType` 共 3 个成员，值 0..2，继承 IntEnum，`str()` 返回 `KEY_*` 名称
- [x] `MouseEventType` 共 9 个成员，值 0..8，继承 IntEnum，`str()` 返回 `MOVE/LEFT_DOWN/...` 名称
- [x] `KeyModifier` 继承 IntFlag，位标志 SHIFT=1 / CTRL=2 / ALT=4 / WIN=8 / CAPSLOCK=16，支持 `|` 操作
- [x] `KeyData` 支持 `to_json()` / `from_json()` 往返，key_code/sequence/tags/metadata 无损
- [x] `MouseData` 同上
- [x] `KeyData.now(...)` 工厂自动填 `timestamp=datetime.now()` 与 `sequence=next(_seq_counter)`
- [x] `KeyData` 的 `event_type` 自动从 `is_press` 推导（is_press=True → KEY_DOWN, False → KEY_UP）
- [x] `KeyData` 的 `key_name` 通过 `_vk_code_to_name()` 正确映射
- [x] `_vk_code_to_name(0x41) == 'A'`, `_vk_code_to_name(0x0D) == 'ENTER'`, `_vk_code_to_name(0x70) == 'F1'`
- [x] `_name_to_vk_code('A') == 0x41`, `_name_to_vk_code('SPACE') == 0x20`

## KeyboardDispatcher / MouseDispatcher
- [x] `KeyboardDispatcher(paths=[tmpdir], backend="polling")` 可启动，`is_running=True`，`stop()` 幂等
- [x] `backend="auto"` 在 Windows 下选择 win32，不可用时回退 polling
- [x] `backend_name` 属性返回实际后端名称（win32/polling）
- [x] `dispatch_count` / `error_count` 正确累计
- [x] `filter_self=True` 时，自我过滤有效：`self_filtered_count` 增加，`dispatch_count` 不增加
- [x] `KeyboardDispatcher.subject` 返回 `Subject[KeyData]`
- [x] `with` 块退出后后台线程终止，无资源泄漏
- [x] `press(key)` / `release(key)` / `type_text(text)` / `hotkey(*keys)` API 可调用
- [x] `move_to(x, y)` / `click(button)` / `scroll(delta)` / `double_click()` / `move_relative(dx, dy)` API 可调用

## Windows Hook（win32 后端）
- [x] `KeyboardDispatcher(backend="win32")` 能成功启动，`backend_name == "win32"`
- [x] `MouseDispatcher(backend="win32")` 同理
- [x] `stop()` 在 1s 内干净返回，后台线程全部终止，无 hanging
- [x] ctypes 函数正确设置 `argtypes` 与 `restype`，64-bit 无访问冲突

## Polling 后端
- [x] `backend="polling"` 启动成功，`backend_name == "polling"`
- [x] polling 轮询间隔 `interval` 生效（非阻塞等待）
- [x] `stop()` 1s 内返回

## KeySubject / MouseSubject
- [x] `KeySubject` 是 `Subject` 的子类（`isinstance(ks, Subject)` 为 True）
- [x] `KeySubject(backend="polling")` 可 `with` 语法使用；退出后 `is_running == False`
- [x] `KeySubject.pipe(ops.filter(...)).subscribe(...)` 可链式组合
- [x] 手动发射 KEY_DOWN/KEY_UP 事件：
  - `on_press` 收到 KEY_DOWN
  - `on_release` 收到 KEY_UP
  - 不会错触发其他回调
- [x] `KeySubject` 代理 `press()` / `type_text()` / `hotkey()` 方法
- [x] `with KeyObserver(...).attach(ks): ...` 退出后 subscription 正确取消
- [x] `KeySubject.dispatcher` 可访问，`dispatch_count` 正确累计
- [x] MouseSubject 同理

## KeyObserver / MouseObserver
- [x] `KeyObserver(on_press=fn, on_release=fn, on_any=fn)` 构造成功
- [x] `KeyObserver._on_next(KeyData(is_press=True))` → `on_press` 被调用
- [x] `KeyObserver._on_next(KeyData(is_press=False))` → `on_release` 被调用
- [x] `on_any` 每次都被调用
- [x] `on_error` / `on_completed` 回调正确触发
- [x] `MouseObserver(on_move=fn, on_click=fn, on_scroll=fn)` 构造成功
- [x] `_on_next(MouseData(event_type=MOVE))` → `on_move` 被调用
- [x] `_on_next(MouseData(event_type=LEFT_DOWN))` → `on_click` 被调用
- [x] `_on_next(MouseData(event_type=SCROLL, delta=120))` → `on_scroll` 被调用

## from_keyboard / from_mouse
- [x] `from_keyboard(backend="polling", auto_start=False)` 返回 `(observable, dispatcher)` 二元组
- [x] 返回的 dispatcher 可 `start()` / `stop()`
- [x] `from_mouse(...)` 同理
- [x] `auto_start=True` 时构造后立即启动

## write_to_keyboard / write_to_mouse
- [x] `write_to_keyboard(disp)` 在 pipe 中不抛异常
- [x] 上游 `{"key": "A"}` / `KeyData(...)` / `65` 均能被 `write_to_keyboard` 正确处理
- [x] `write_to_mouse(disp)` 在 pipe 中不抛异常
- [x] 上游 `{"x": 100, "y": 200, "event": "move"}` / `MouseData(...)` 均能被处理
- [x] 写入操作（模拟）成功，下游收到新的事件（如果模拟产生系统事件并被自身 Hook 捕获则自我过滤）

## 包导出
- [x] `from vools.reactive import KeyEventType, KeyModifier, KeyData, KeyboardDispatcher, KeySubject, KeyObserver, from_keyboard, write_to_keyboard` 无异常
- [x] `from vools.reactive import MouseEventType, MouseData, MouseDispatcher, MouseSubject, MouseObserver, from_mouse, write_to_mouse` 无异常
- [x] `vools.reactive.__all__` 包含以上所有符号

## 测试质量
- [x] `pytest tests/test_reactive_keyboard_mouse.py -v` 在 Windows 全绿（39 passed）
- [x] `pytest tests/test_reactive_keyboard_mouse.py -v` 在 WSL（Linux）全绿（polling 后端）
- [x] 每个事件类型至少有一个单元测试
- [x] 自我过滤机制有独立测试
- [x] 测试文件风格与 `tests/test_reactive_clipboard.py` 一致

## 命名与风格
- [x] 对外 API 命名前缀 `Key*` / `Mouse*`，与 `Folder*` / `File*` 系列一一对应
- [x] `KeyData` / `MouseData` 字段命名风格（`key_code`, `key_name`, `x`, `y`, `event_type`, `timestamp`, `sequence`, `tags`, `metadata`）
- [x] 不引入第三方依赖，仅标准库
- [x] 代码风格与 `clipboard.py` / `file_watcher.py` 一致

## 全量测试
- [x] `pytest tests/ -v` 584 passed, 1 skipped（WSL 环境）

## 资源与泄漏（可选验证）
- [ ] 启动-停止 100 次不产生 hook handle leak（Windows Process Hacker 检查）
- [ ] 启动-停止 100 次不产生 thread leak（进程内线程数保持恒定）
- [ ] 空闲状态 CPU 占用 < 0.1%（非 polling 后端）
