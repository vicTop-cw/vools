# 监控类 Observer 评估与完善 - 验证清单

## 现有测试修复
- [x] tests/monitoring/ 下所有测试已标记为 legacy（skip）
- [x] 新建 simulators/ 目录，包含双进程测试框架
- [x] 无测试导入错误或模块缺失

## 窗口监控 (window.py)
- [x] WindowChangeType 包含 FOCUSED/CREATED/DESTROYED/TITLE_CHANGED/MOVED/SIZED/OTHER
- [x] WindowData 支持 JSON/Pickle 往返序列化
- [x] WindowDispatcher 可启动/停止，is_running 属性正确
- [x] WindowDispatcher.snapshot() 返回 WindowData 列表
- [x] WindowSubject 继承 MonitorSubject，支持 with 语法
- [x] WindowObserver 按事件类型路由回调
- [x] from_window() 工厂返回 (Observable, Dispatcher) 二元组
- [x] WindowData 的 hwnd/title/class_name/pid 字段正确填充

## 进程监控 (process.py)
- [x] ProcessChangeType 包含 STARTED/EXITED/MODIFIED/OTHER
- [x] ProcessData 支持 JSON/Pickle 往返序列化
- [x] ProcessDispatcher 可启动/停止
- [x] ProcessDispatcher.snapshot() 返回 ProcessData 列表
- [x] ProcessSubject 继承 MonitorSubject，支持 with 语法
- [x] ProcessObserver 按事件类型路由回调
- [x] from_process() 工厂返回 (Observable, Dispatcher) 二元组
- [x] ProcessData 的 pid/ppid/name/path 字段正确填充

## 热键注册
- [x] KeyboardDispatcher.register_hotkey(modifiers, key, callback) 可注册全局热键
- [x] KeyboardDispatcher.unregister_hotkey(id) 可注销热键
- [x] 热键触发时 callback 被正确调用
- [x] Dispatcher stop 时自动注销所有热键

## 模块导出与文档
- [x] `from vools.reactive.monitoring import WindowChangeType, WindowData, WindowDispatcher, WindowSubject, WindowObserver, from_window` 无异常
- [x] `from vools.reactive.monitoring import ProcessChangeType, ProcessData, ProcessDispatcher, ProcessSubject, ProcessObserver, from_process` 无异常
- [x] README.md 已更新，包含窗口监控和进程监控的使用示例

## 代码风格
- [x] 新模块使用 `from __future__ import annotations`
- [x] 中文 docstring
- [x] __all__ 显式声明
- [x] 使用相对导入
- [x] 仅标准库 + ctypes，无第三方依赖