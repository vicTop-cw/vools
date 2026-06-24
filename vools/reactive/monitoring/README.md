# vools.reactive.monitoring — 系统监控

键盘、鼠标、剪贴板、文件/文件夹监控的 Observable 封装，将系统事件转换为响应式流。

## 监控源

| 名称 | 说明 |
|------|------|
| `from_keyboard` | 键盘事件监控 |
| `from_mouse` | 鼠标事件监控 |
| `from_clipboard` | 剪贴板变化监控 |
| `from_filesystem` | 文件变化监控 |
| `from_foldersystem` | 文件夹变化监控 |

> 需要平台特定依赖（如 `pywin32`）。

## 使用示例

### 键盘监控

```python
from vools.reactive.monitoring import from_keyboard

# 监听键盘事件
keyboard_obs = from_keyboard()
subscription = keyboard_obs.subscribe(
    on_next=lambda key_data: print(f"Key: {key_data.key}, Type: {key_data.event_type}")
)

# 停止监听
# subscription.dispose()
```

### 鼠标监控

```python
from vools.reactive.monitoring import from_mouse

# 监听鼠标事件
mouse_obs = from_mouse()
mouse_obs.subscribe(
    on_next=lambda mouse_data: print(
        f"Mouse: ({mouse_data.x}, {mouse_data.y}), "
        f"Type: {mouse_data.event_type}"
    )
)
```

### 剪贴板监控

```python
from vools.reactive.monitoring import from_clipboard

# 监听剪贴板变化
clipboard_obs = from_clipboard()
clipboard_obs.subscribe(
    on_next=lambda clip_data: print(
        f"Clipboard changed: {clip_data.change_type}, "
        f"Content: {clip_data.content}"
    )
)
```

### 文件监控

```python
from vools.reactive.monitoring import from_filesystem

# 监控单个文件变化
file_obs = from_filesystem("path/to/file.txt")
file_obs.subscribe(
    on_next=lambda file_data: print(
        f"File changed: {file_data.path}, "
        f"Type: {file_data.change_type}"
    )
)
```

### 文件夹监控

```python
from vools.reactive.monitoring import from_foldersystem

# 监控文件夹变化
folder_obs = from_foldersystem("path/to/folder")
folder_obs.subscribe(
    on_next=lambda folder_data: print(
        f"Folder changed: {folder_data.path}, "
        f"Type: {folder_data.change_type}"
    )
)
```

### 结合操作符使用

```python
from vools.reactive.monitoring import from_keyboard
from vools.reactive.operators import filter, map

# 只监听特定按键
keyboard_obs = from_keyboard()
keyboard_obs.pipe(
    filter(lambda k: k.event_type == "down"),
    map(lambda k: k.key)
).subscribe(lambda key: print(f"Key pressed: {key}"))
```
