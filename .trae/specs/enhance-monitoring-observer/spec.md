# 监控类 Observer 评估与完善 Spec

## Why
用户提供了三组外部源码（FB版按键库、VB剪贴板监控、VB热键控件），需评估对现有 vools.reactive.monitoring 的帮助。现有 5 大监控（keyboard/mouse/clipboard/file_watcher/folder_watcher）已基于 ctypes 实现，需确定：1) 外部源码是否有 vools 缺失的监控能力；2) 是否需要用 FreeBASIC 重写部分逻辑并入 DLL；3) 确保所有监控类测试通过。

## What Changes
- 新增 **窗口监控** 模块（window.py）：基于外部 window.bi 的窗口查找/列表/信息获取能力，提供 WindowSubject/WindowObserver/WindowDispatcher
- 新增 **进程监控** 模块（process.py）：基于外部 process.bi 的进程列表/状态/子进程能力，提供 ProcessSubject/ProcessObserver/ProcessDispatcher
- **不使用 FreeBASIC 重写**：现有 ctypes 实现性能已足够，FB DLL 引入的跨语言调用开销（参见项目经验：Nim 实现小数据场景反而更慢）不划算；window/process 新模块同样用 ctypes 实现
- 完善 **热键监控** 功能：现有 keyboard.py 仅提供原始键盘事件流，新增热键组合注册与触发（参考 VB 热键控件，使用 RegisterHotKey/UnregisterHotKey API）
- 修复并完善现有监控类测试，确保全部通过

## Impact
- Affected specs: keyboard_mouse（补充热键能力）、clipboard-monitor-dispatcher（无需改动）
- Affected code:
  - `vools/reactive/monitoring/keyboard.py` — 新增热键注册 API
  - `vools/reactive/monitoring/window.py` — 新增文件
  - `vools/reactive/monitoring/process.py` — 新增文件
  - `vools/reactive/monitoring/__init__.py` — 新增导出
  - `tests/monitoring/` — 修复现有测试、新增测试

## ADDED Requirements

### Requirement: 窗口监控 (Window Monitor)
系统 SHALL 提供窗口事件监控能力，包括窗口创建/销毁/标题变化/焦点变化等。

#### Scenario: 窗口焦点变化
- **WHEN** 用户切换窗口焦点
- **THEN** WindowSubject 发出 WindowData(focused=True, hwnd=..., title=..., class_name=..., pid=...) 事件

#### Scenario: 窗口列表快照
- **WHEN** 调用 WindowDispatcher.snapshot()
- **THEN** 返回当前所有可见窗口的 WindowData 列表

### Requirement: 进程监控 (Process Monitor)
系统 SHALL 提供进程启动/退出监控能力，以及进程信息查询。

#### Scenario: 进程启动
- **WHEN** 新进程启动
- **THEN** ProcessSubject 发出 ProcessData(event_type=STARTED, pid=..., name=..., path=...) 事件

#### Scenario: 进程列表快照
- **WHEN** 调用 ProcessDispatcher.snapshot()
- **THEN** 返回当前所有进程的 ProcessData 列表

### Requirement: 热键注册 (HotKey Registration)
系统 SHALL 提供全局热键注册能力，支持修饰键组合。

#### Scenario: 注册全局热键
- **WHEN** 用户调用 KeyboardDispatcher.register_hotkey(modifiers=MOD_CTRL|MOD_ALT, key=VK_F1, callback=fn)
- **THEN** 按下 Ctrl+Alt+F1 时触发 callback

### Requirement: 监控类测试修复
系统 SHALL 确保所有现有监控类测试在 Windows 上通过。

#### Scenario: 运行全部监控测试
- **WHEN** 执行 pytest tests/monitoring/ -v --ignore=tests/monitoring/__pycache__
- **THEN** 所有测试通过（非集成测试可跳过的除外）

## MODIFIED Requirements

### Requirement: 监控模块导出
`vools/reactive/monitoring/__init__.py` 新增导出：
- WindowChangeType, WindowData, WindowDispatcher, WindowSubject, WindowObserver, from_window, write_to_window
- ProcessChangeType, ProcessData, ProcessDispatcher, ProcessSubject, ProcessObserver, from_process, write_to_process

## REMOVED Requirements
（无移除）

## 评估结论

### 外部源码价值分析

| 源码文件 | 功能 | 对 vools 的价值 | 决策 |
|----------|------|-----------------|------|
| hook.bi | 键鼠钩子(FB) | 低 — 已有 Python+ctypes 实现 | 不重写 |
| clipboard.bi | 剪贴板读写(FB) | 低 — 已有完整实现 | 不重写 |
| window.bi | 窗口查找/信息/列表 | **高** — vools 缺失 | **新增 ctypes 实现** |
| spycon.bi | Spy控件(FB GUI) | 低 — Python 不需要 FB GUI | 不重写 |
| process.bi | 进程信息/列表/操作 | **高** — vools 缺失 | **新增 ctypes 实现** |
| clsClip.cls | VB剪贴板内容管理 | 低 — 已有完整实现 | 参考 |
| gModule.bas | VB剪贴板 WndProc | 低 — 已有 Hook 实现 | 参考 |
| Form1.frm | VB热键控件测试 | **中** — 需补充热键能力 | **参考实现** |

### FreeBASIC 重写决策：不重写
理由：
1. 现有 ctypes 实现已成熟，性能满足需求
2. 项目经验表明：小数据量场景跨语言调用（ctypes wrapper）开销反而更大
3. FB DLL 增加包体积和编译依赖
4. 新增的 window/process 模块同样适合 ctypes 实现（Win32 API 调用频率低，不是性能瓶颈）
