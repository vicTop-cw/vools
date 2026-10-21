# 系统监控（vools.reactive.monitoring）{#A25}

> **模块路径**：`vools.reactive.monitoring`
> **文档编号**：#A25
> **最后更新**：2026-10-18

---

## 概述

键盘、鼠标、剪贴板、文件/文件夹/窗口/进程监控的 Observable 封装，
将系统事件转换为响应式流。

> 需要平台特定依赖（Windows 下如 `pywin32`），不可用时优雅降级。

## 监控源

| 名称 | 说明 |
|------|------|
| `from_keyboard` | 键盘事件监控 |
| `from_mouse` | 鼠标事件监控 |
| `from_clipboard` | 剪贴板变化监控 |
| `from_filesystem` | 文件变化监控 |
| `from_foldersystem` | 文件夹变化监控 |
| `from_window` | 窗口焦点变化监控 |
| `from_process` | 进程启动/退出监控 |

## 使用示例

### 键盘监控

```python
from vools.reactive.monitoring import from_keyboard

keyboard_obs = from_keyboard()
subscription = keyboard_obs.subscribe(
    on_next=lambda key_data: print(f"Key: {key_data.key}, Type: {key_data.event_type}")
)
# 停止监听: subscription.dispose()
```

### 鼠标监控

```python
from vools.reactive.monitoring import from_mouse

mouse_obs = from_mouse()
mouse_obs.subscribe(
    on_next=lambda mouse_data: print(
        f"Mouse: ({mouse_data.x}, {mouse_data.y}), Type: {mouse_data.event_type}"
    )
)
```

### 剪贴板监控

```python
from vools.reactive.monitoring import from_clipboard

clipboard_obs = from_clipboard()
clipboard_obs.subscribe(
    on_next=lambda clip_data: print(
        f"Clipboard changed: {clip_data.change_type}, Content: {clip_data.content}"
    )
)
```

### 文件监控

```python
from vools.reactive.monitoring import from_filesystem

file_obs = from_filesystem("path/to/file.txt")
file_obs.subscribe(
    on_next=lambda file_data: print(
        f"File changed: {file_data.path}, Type: {file_data.change_type}"
    )
)
```

### 文件夹监控

```python
from vools.reactive.monitoring import from_foldersystem

folder_obs = from_foldersystem("path/to/folder")
folder_obs.subscribe(
    on_next=lambda folder_data: print(
        f"Folder changed: {folder_data.path}, Type: {folder_data.change_type}"
    )
)
```

### 窗口监控

```python
from vools.reactive.monitoring import from_window

window_obs, dispatcher = from_window()
window_obs.subscribe(
    on_next=lambda wd: print(
        f"Window: {wd.title}, Class: {wd.class_name}, PID: {wd.pid}"
    )
)
windows = dispatcher.snapshot()
```

### 进程监控

```python
from vools.reactive.monitoring import from_process

process_obs, dispatcher = from_process()
process_obs.subscribe(
    on_next=lambda pd: print(
        f"Process: {pd.name} (PID: {pd.pid}), Event: {pd.event_type}"
    )
)
processes = dispatcher.snapshot()
```

### 热键注册

```python
from vools.reactive.monitoring import KeyboardDispatcher, MOD_CONTROL, MOD_ALT

kbd = KeyboardDispatcher()
hotkey_id = kbd.register_hotkey(
    modifiers=MOD_CONTROL | MOD_ALT,
    vk=0x70,  # VK_F1
    callback=lambda: print("Hotkey triggered!"),
)
kbd.unregister_hotkey(hotkey_id)
```

### 结合操作符使用

```python
from vools.reactive.monitoring import from_keyboard
from vools.reactive.operators import filter, map

keyboard_obs = from_keyboard()
keyboard_obs.pipe(
    filter(lambda k: k.event_type == "down"),
    map(lambda k: k.key),
).subscribe(lambda key: print(f"Key pressed: {key}"))
```

## 相关文档

- [vools.reactive（rx 子项目）](index.md)
