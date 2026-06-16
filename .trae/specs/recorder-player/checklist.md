# Checklist - 键鼠操作录制与回放模块

## 类型定义和基础结构
- [x] vools/recorder/__init__.py 导出主要类
- [x] ActionType 枚举包含所有命令类型
- [x] Action 数据类可序列化
- [x] Recording 数据类可序列化

## 录制器 (Recorder)
- [x] Recorder 类实现 start()/stop()/is_recording()
- [x] 支持监听键盘事件
- [x] 支持监听鼠标事件
- [x] 支持监听剪贴板事件
- [x] 事件去重功能正常

## 回放器 (Player)
- [x] Player 类实现 play()/pause()/resume()/stop()/is_playing
- [x] 键盘动作执行正确 (keydown, keyup, keypress, type, hotkey)
- [x] 鼠标动作执行正确 (moveto, move, click, dbclick, down, up, wheel, hwheel)
- [x] 剪贴板动作执行正确 (setclip, paste)
- [x] 延迟动作正确执行
- [x] 速度调节功能正常
- [x] 暂停/恢复功能正常

## 脚本解析器 (Parser)
- [x] 解析 Quicker InputScript 格式
- [x] 支持 moveto:50%,50% 百分比坐标
- [x] generate_quicker_script() 生成正确格式
- [x] 导出/导入 YAML 格式正常
- [x] 导出/导入 JSON 格式正常

## 测试
- [x] Action 单元测试通过 (6 个测试)
- [x] Recording 单元测试通过 (5 个测试)
- [x] Parser 解析测试通过 (14 个测试)
- [x] 常量测试通过 (2 个测试)

## 文档
- [x] 模块 docstring 完整
- [x] 类和方法文档完整
- [x] 使用示例可用
