# Tasks - 键鼠操作录制与回放模块

## 阶段 1: 类型定义和基础结构

- [x] Task 1.1: 创建 `vools/recorder/` 目录结构
  - [x] 创建 `vools/recorder/__init__.py`
  - [x] 创建 `vools/recorder/typedefs.py`
  - [x] 创建 `vools/recorder/actions.py`

- [x] Task 1.2: 实现 `ActionType` 枚举
  - [x] 定义所有键盘命令类型
  - [x] 定义所有鼠标命令类型
  - [x] 定义剪贴板和延迟命令类型

- [x] Task 1.3: 实现 `Action` 数据类
  - [x] 字段: action_type, timestamp, params
  - [x] 方法: to_dict(), from_dict(), to_yaml(), from_yaml()

- [x] Task 1.4: 实现 `Recording` 数据类
  - [x] 字段: start_time, end_time, actions, tags
  - [x] 方法: to_dict(), from_dict(), to_yaml(), from_yaml(), to_json(), from_json()
  - [x] 方法: to_quicker_script() - 生成 Quicker InputScript 格式

## 阶段 2: 录制器实现

- [x] Task 2.1: 实现 `Recorder` 类
  - [x] 构造函数: record_keyboard, record_mouse, record_clipboard 参数
  - [x] start() 方法 - 开始录制
  - [x] stop() 方法 - 停止录制并返回 Recording
  - [x] is_recording() 属性

- [x] Task 2.2: 集成键鼠监控
  - [x] 使用 KeyboardSubject 监听键盘事件
  - [x] 使用 MouseSubject 监听鼠标事件
  - [x] 使用 ClipboardSubject 监听剪贴板变化

- [x] Task 2.3: 事件去重和优化
  - [x] 实现 deduplicate_interval 去重逻辑
  - [x] 优化鼠标移动事件的采样

## 阶段 3: 回放器实现

- [x] Task 3.1: 实现 `Player` 类
  - [x] 构造函数: 注入 KeyboardDispatcher, MouseDispatcher, ClipboardSubject
  - [x] play(recording, speed) 方法
  - [x] pause() / resume() / stop() 方法
  - [x] is_playing 属性

- [x] Task 3.2: 动作执行器
  - [x] 执行键盘动作 (keydown, keyup, keypress, type, hotkey)
  - [x] 执行鼠标动作 (moveto, move, click, dbclick, down, up, wheel, hwheel)
  - [x] 执行剪贴板动作 (setclip, paste)
  - [x] 执行延迟动作 (delay)

- [x] Task 3.3: 时间控制
  - [x] 按 timestamp 执行动作
  - [x] 支持 speed 参数 (0.5x, 1x, 2x)
  - [x] 支持暂停/恢复

## 阶段 4: 脚本解析器

- [x] Task 4.1: 实现 `Parser` 类
  - [x] 解析 Quicker InputScript 格式
  - [x] parse(text) -> List[Action]
  - [x] parse_file(path) -> List[Action]

- [x] Task 4.2: 实现脚本生成器
  - [x] generate_quicker_script(actions) -> str
  - [x] generate_yaml(actions) -> str

## 阶段 5: 集成和测试

- [x] Task 5.1: 更新 `vools/__init__.py` 导出

- [x] Task 5.2: 编写单元测试
  - [x] 测试 Action 序列化
  - [x] 测试 Recording 序列化
  - [x] 测试 Parser 解析
  - [x] 测试 Recorder 录制
  - [x] 测试 Player 回放

- [x] Task 5.3: 编写集成测试
  - [x] 录制-回放完整流程测试
  - [x] 速度调节测试
  - [x] 暂停恢复测试

## Task Dependencies

- Task 1.1 → Task 1.2 → Task 1.3 → Task 1.4
- Task 1.4 → Task 2.1 → Task 2.2 → Task 2.3
- Task 1.4 → Task 3.1 → Task 3.2 → Task 3.3
- Task 1.4 → Task 4.1 → Task 4.2
- Task 2.3, Task 3.3, Task 4.2 → Task 5.1 → Task 5.2 → Task 5.3
