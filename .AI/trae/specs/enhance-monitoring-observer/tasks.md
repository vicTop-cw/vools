# Tasks

- [x] Task 1: 重构监控类测试为双进程架构
  - [x] 1.1 创建 tests/monitoring/simulators/ 目录结构
  - [x] 1.2 实现 utils.py：控制文件读写、日志记录、进程管理公共函数
  - [x] 1.3 实现 keyboard_sim.py：使用 keybd_event 模拟按键
  - [x] 1.4 实现 mouse_sim.py：使用 SendInput 模拟鼠标移动/点击/滚轮
  - [x] 1.5 实现 clipboard_sim.py：使用 SetClipboardData 模拟剪贴板写入
  - [x] 1.6 实现 file_sim.py：文件创建/修改/删除模拟
  - [x] 1.7 实现 folder_sim.py：文件夹创建/删除模拟
  - [x] 1.8 将现有集成测试标记为 legacy（添加 @pytest.mark.skip 或移动到 legacy/ 目录）
  - [x] 1.9 编写新的双进程集成测试（test_keyboard_integration.py 等）
  - [x] 1.10 确认 pytest tests/monitoring/ -v -m "not integration" 全部通过

- [x] Task 2: 新增窗口监控模块 (window.py)
  - [x] 2.1 定义 WindowChangeType(IntEnum): FOCUSED/CREATED/DESTROYED/TITLE_CHANGED/MOVED/SIZED/OTHER
  - [x] 2.2 定义 WindowData dataclass: hwnd/title/class_name/pid/path/rect/event_type/timestamp/sequence/tags/metadata
  - [x] 2.3 实现 WindowDispatcher（Win32 后端：SetWinEventHook + 回调；polling 后端保底）
  - [x] 2.4 实现 WindowSubject(MonitorSubject) 和 WindowObserver(MonitorObserver)
  - [x] 2.5 实现 from_window() 工厂和 write_to_window() 操作符
  - [x] 2.6 实现 snapshot() 快照方法（EnumWindows + GetWindowText + GetWindowThreadProcessId 等）
  - [x] 2.7 实现 window_sim.py：使用 CreateWindowEx 创建临时窗口
  - [x] 2.8 编写 test_window.py 单元测试
  - [x] 2.9 编写 test_window_integration.py 双进程集成测试

- [x] Task 3: 新增进程监控模块 (process.py)
  - [x] 3.1 定义 ProcessChangeType(IntEnum): STARTED/EXITED/MODIFIED/OTHER
  - [x] 3.2 定义 ProcessData dataclass: pid/ppid/name/path/cmdline/status/event_type/timestamp/sequence/tags/metadata
  - [x] 3.3 实现 ProcessDispatcher（Win32 后端：WMI 进程事件通知 或轮询快照对比；polling 后端保底）
  - [x] 3.4 实现 ProcessSubject(MonitorSubject) 和 ProcessObserver(MonitorObserver)
  - [x] 3.5 实现 from_process() 工厂和 write_to_process() 操作符
  - [x] 3.6 实现 snapshot() 快照方法（CreateToolhelp32Snapshot + Process32First/Next）
  - [x] 3.7 实现 process_sim.py：启动/终止子进程
  - [x] 3.8 编写 test_process.py 单元测试
  - [x] 3.9 编写 test_process_integration.py 双进程集成测试

- [x] Task 4: 为 keyboard.py 新增热键注册功能
  - [x] 4.1 在 KeyboardDispatcher 中新增 register_hotkey(modifiers, key, callback) 方法
  - [x] 4.2 在 KeyboardDispatcher 中新增 unregister_hotkey(id) 方法
  - [x] 4.3 使用 RegisterHotKey/UnregisterHotKey Win32 API + 专用线程消息循环
  - [x] 4.4 编写热键测试（双进程：一个注册热键，一个模拟按键）

- [x] Task 5: 更新模块导出和文档
  - [x] 5.1 更新 vools/reactive/monitoring/__init__.py 导出新符号
  - [x] 5.2 更新 vools/reactive/monitoring/README.md 文档
  - [x] 5.3 创建 tests/monitoring/README.md 说明测试架构

# Task Dependencies
- Task 2, Task 3, Task 4 依赖 Task 1（先建立测试框架）
- Task 5 依赖 Task 2, Task 3, Task 4
- Task 2 和 Task 3 可并行