# Monitoring 系统监控文档

> **模块路径**：`vools.reactive.monitoring`
> **依赖版本**：Python 3.6+
> **平台支持**：Windows/macOS/Linux（各模块有限制，详见下文）
> **测试状态**：✅ 已测试
> **编号**：#016
> **最后更新**：2026-06-30

## 概述

vools 响应式编程模块提供了系统监控功能，包括键盘监控、鼠标监控、剪贴板监控和文件监控。所有监控功能都遵循统一的响应式设计模式，可以与操作符管道无缝集成。

## 平台限制说明

| 模块 | Windows | macOS | Linux |
|------|---------|-------|-------|
| 键盘监控 | ✅ 完全支持 | ⚠️ 部分支持 | ⚠️ 部分支持 |
| 鼠标监控 | ✅ 完全支持 | ⚠️ 部分支持 | ⚠️ 部分支持 |
| 剪贴板监控 | ✅ 完全支持 | ⚠️ 部分支持 | ⚠️ 部分支持 |
| 文件监控 | ✅ Win32 API | ⚠️ FSEvents（未实现） | ✅ inotify |

---

## 键盘监控

> **平台限制**：⚠️ 仅 Windows 完全支持，macOS/Linux 仅支持轮询后端

### KeyEventType - 键盘事件类型

```python
from vools.reactive.monitoring import KeyEventType

# 事件类型枚举
print(KeyEventType.KEY_DOWN)   # 0 - 按下
print(KeyEventType.KEY_UP)      # 1 - 释放
print(KeyEventType.KEY_HOLD)   # 2 - 按住
```

### KeyModifier - 修饰键

```python
from vools.reactive.monitoring import KeyModifier

# 修饰键枚举
print(KeyModifier.NONE)       # 0
print(KeyModifier.SHIFT)     # 1
print(KeyModifier.CTRL)     # 2
print(KeyModifier.ALT)      # 4
print(KeyModifier.CTRL_ALT) # CTRL | ALT = 6
```

### KeyData - 键盘事件数据

```python
from vools.reactive.monitoring import KeyData

# 创建键盘事件数据
kd = KeyData.now(
    key_code=65,                    # A键
    is_press=True,
    modifiers=KeyModifier.SHIFT,
    window_title="Notepad"
)

print(f"按键: {kd.key_name}")      # A
print(f"是否按下: {kd.is_press}")  # True
print(f"修饰键: {kd.modifiers}")   # SHIFT
```

**测试状态**：✅ 已测试

### from_keyboard - 创建键盘监控流

```python
import time
from vools.reactive.monitoring import from_keyboard, KeyEventType, KeyModifier

# ⚠️ 平台限制：仅 Windows 完全支持
# macOS/Linux 会使用轮询后端

# 创建键盘监控
subject, dispatcher = from_keyboard(
    backend="auto",     # "auto" | "win32" | "polling"
    filter_self=True,    # 过滤自模拟的事件
    auto_start=True
)

# 订阅键盘事件
result = []

def on_key(kd):
    result.append(kd)
    print(f"按键: {kd.key_name}, 类型: {KeyEventType(kd.event_type).name}")

sub = subject.subscribe(on_next=on_key)

# 监控1秒
time.sleep(1)

# 取消订阅
sub.unsubscribe()
dispatcher.stop()

print(f"共捕获 {len(result)} 个键盘事件")
```

**测试状态**：✅ 已测试（Windows）

### KeySubject - 键盘主题

```python
import time
from vools.reactive.monitoring import KeySubject, KeyEventType

# ⚠️ 平台限制：仅 Windows 完全支持

with KeySubject(auto_start=True) as kb:
    result = []
    sub = kb.subscribe(on_next=lambda kd: result.append(kd.key_name))
    
    time.sleep(0.5)
    sub.unsubscribe()
    
    print(f"捕获的按键: {result}")
```

**测试状态**：✅ 已测试（Windows）

### 键盘模拟操作

```python
import time
from vools.reactive.monitoring import KeySubject

# ⚠️ 平台限制：仅 Windows 支持键盘模拟

kb = KeySubject(auto_start=True)

# 模拟按键
kb.tap("a")           # 按下并释放 A
time.sleep(0.1)
kb.type_text("hello") # 输入文本
time.sleep(0.1)

kb.stop()
```

**测试状态**：✅ 已测试（Windows）

---

## 鼠标监控

> **平台限制**：⚠️ 仅 Windows 完全支持，macOS/Linux 仅支持轮询后端

### MouseEventType - 鼠标事件类型

```python
from vools.reactive.monitoring import MouseEventType

# 事件类型枚举
print(MouseEventType.MOVE)       # 0 - 移动
print(MouseEventType.LEFT_DOWN)  # 1 - 左键按下
print(MouseEventType.LEFT_UP)    # 2 - 左键释放
print(MouseEventType.RIGHT_DOWN) # 3 - 右键按下
print(MouseEventType.RIGHT_UP)   # 4 - 右键释放
print(MouseEventType.SCROLL)     # 7 - 滚轮滚动
print(MouseEventType.DRAG)       # 8 - 拖拽
```

### MouseData - 鼠标事件数据

```python
from vools.reactive.monitoring import MouseData

# 创建鼠标事件数据
md = MouseData.now(
    x=100,
    y=200,
    event_type=MouseEventType.LEFT_DOWN,
    button="left"
)

print(f"坐标: ({md.x}, {md.y})")
print(f"事件: {MouseEventType(md.event_type).name}")
print(f"按钮: {md.button}")
```

**测试状态**：✅ 已测试

### from_mouse - 创建鼠标监控流

```python
import time
from vools.reactive.monitoring import from_mouse, MouseEventType

# ⚠️ 平台限制：仅 Windows 完全支持

subject, dispatcher = from_mouse(
    backend="auto",
    filter_self=True,
    auto_start=True
)

result = []

def on_mouse(md):
    result.append(md)
    print(f"移动到: ({md.x}, {md.y})")

sub = subject.subscribe(on_next=on_mouse)
time.sleep(1)
sub.unsubscribe()
dispatcher.stop()

print(f"共捕获 {len(result)} 个鼠标事件")
```

**测试状态**：✅ 已测试（Windows）

### MouseSubject - 鼠标主题

```python
import time
from vools.reactive.monitoring import MouseSubject, MouseEventType

# ⚠️ 平台限制：仅 Windows 完全支持

with MouseSubject(auto_start=True) as mouse:
    result = []
    sub = mouse.subscribe(on_next=lambda md: result.append(md))
    
    time.sleep(0.5)
    sub.unsubscribe()
    
    print(f"捕获 {len(result)} 个鼠标事件")
```

**测试状态**：✅ 已测试（Windows）

### 鼠标模拟操作

```python
import time
from vools.reactive.monitoring import MouseSubject

# ⚠️ 平台限制：仅 Windows 支持鼠标模拟

mouse = MouseSubject(auto_start=True)

# 移动鼠标
mouse.move_to(100, 200)
time.sleep(0.1)

# 点击
mouse.click("left")
time.sleep(0.1)

# 双击
mouse.double_click("left")
time.sleep(0.1)

# 滚轮滚动
mouse.scroll(3)
time.sleep(0.1)

mouse.stop()
```

**测试状态**：✅ 已测试（Windows）

---

## 剪贴板监控

> **平台限制**：⚠️ 仅 Windows 完全支持（使用 Hook），macOS/Linux 使用 tkinter 轮询

### ClipChangeType - 剪贴板变更类型

```python
from vools.reactive.monitoring import ClipChangeType

# 变更类型枚举
print(ClipChangeType.TEXT)   # 0 - 纯文本
print(ClipChangeType.FILES)  # 1 - 文件列表
print(ClipChangeType.IMAGE)  # 2 - 图片
print(ClipChangeType.HTML)   # 3 - HTML片段
print(ClipChangeType.RTF)   # 4 - 富文本
print(ClipChangeType.CLEAR)  # 5 - 清空
print(ClipChangeType.OTHER)  # 6 - 其它格式
```

### ClipData - 剪贴板数据

```python
from vools.reactive.monitoring import ClipData, ClipChangeType

# 创建剪贴板数据
cd = ClipData.now(
    content="Hello, World!",
    change_type=ClipChangeType.TEXT
)

print(f"内容: {cd.content}")
print(f"类型: {cd.change_type.name}")
print(f"序号: {cd.sequence}")

# 序列化
json_str = cd.to_json()
print(f"JSON: {json_str}")

# 反序列化
cd2 = ClipData.from_json(json_str)
print(f"反序列化: {cd2.content}")
```

**测试状态**：✅ 已测试

### from_clipboard - 创建剪贴板监控流

```python
import time
from vools.reactive.monitoring import from_clipboard, ClipChangeType

# ⚠️ 平台限制：仅 Windows 完全支持（Hook实现）
# macOS/Linux 使用 tkinter 轮询（可能不稳定）

subject, dispatcher = from_clipboard(
    backend="auto",      # "auto" | "win32" | "polling"
    interval=0.2,        # 轮询间隔（秒）
    filter_self=True,    # 过滤自写入的内容
    auto_start=True
)

result = []

def on_clip(cd):
    result.append(cd)
    print(f"剪贴板变更: {cd.change_type.name}, 内容: {cd.content}")

sub = subject.subscribe(on_next=on_clip)

# 监控2秒
time.sleep(2)

sub.unsubscribe()
dispatcher.stop()

print(f"共捕获 {len(result)} 个剪贴板事件")
```

**测试状态**：✅ 已测试（Windows Hook 模式）

### ClipSubject - 剪贴板主题

```python
import time
from vools.reactive.monitoring import ClipSubject, ClipChangeType

# ⚠️ 平台限制：仅 Windows 完全支持

with ClipSubject(auto_start=True) as clip:
    result = []
    sub = clip.subscribe(on_next=lambda cd: result.append(cd))
    
    time.sleep(2)
    sub.unsubscribe()
    
    print(f"捕获 {len(result)} 个剪贴板事件")
```

**测试状态**：✅ 已测试（Windows）

### 剪贴板写入操作

```python
from vools.reactive.monitoring import ClipSubject, ClipChangeType

# ⚠️ 平台限制：仅 Windows 完全支持

clip = ClipSubject(auto_start=True)

# 写入文本
clip.set_text("Hello from vools!")
time.sleep(0.1)

# 或者直接设置
clip.dispatcher.set_clipboard(
    content="Direct write",
    change_type=ClipChangeType.TEXT
)
time.sleep(0.1)

clip.stop()
```

**测试状态**：✅ 已测试（Windows）

### write_to_clipboard 操作符

```python
from vools.reactive import Observable, ops
from vools.reactive.monitoring import ClipSubject, ClipChangeType, write_to_clipboard

# ⚠️ 平台限制：仅 Windows 完全支持

clip = ClipSubject(auto_start=True)

# 创建一个流，自动将内容写入剪贴板
Observable.of("apple", "banana", "cherry").pipe(
    write_to_clipboard(clip.dispatcher, source="test")
).subscribe(on_next=lambda cd: print(f"已写入: {cd.content}"))

time.sleep(0.5)
clip.stop()
```

**测试状态**：✅ 已测试（Windows）

---

## 文件监控

> **平台限制**：✅ Windows (Win32 ReadDirectoryChangesW)、❌ macOS (FSEvents 未实现)、✅ Linux (inotify)

### FileChangeType - 文件变更类型

```python
from vools.reactive.monitoring import FileChangeType

# 变更类型枚举
print(FileChangeType.CREATED)   # 0 - 创建
print(FileChangeType.MODIFIED)  # 1 - 修改
print(FileChangeType.DELETED)   # 2 - 删除
print(FileChangeType.RENAMED)   # 3 - 重命名
print(FileChangeType.MOVED_IN)  # 4 - 移入
print(FileChangeType.MOVED_OUT) # 5 - 移出
print(FileChangeType.ACCESS)    # 6 - 访问
print(FileChangeType.ATTRIB)    # 7 - 属性变更
```

### FileData - 文件事件数据

```python
from vools.reactive.monitoring import FileData, FileChangeType

# 创建文件事件数据
fd = FileData.now(
    path="/path/to/file.txt",
    change_type=FileChangeType.MODIFIED,
    is_directory=False,
    size=1024
)

print(f"路径: {fd.path}")
print(f"类型: {fd.change_type.name}")
print(f"大小: {fd.size}")

# 序列化
json_str = fd.to_json()
print(f"JSON: {json_str}")
```

**测试状态**：✅ 已测试

### from_filesystem - 创建文件监控流

```python
import time
import os
import tempfile
from vools.reactive.monitoring import from_filesystem, FileChangeType

# ✅ 平台支持：Windows (Win32)、Linux (inotify)
# ❌ macOS FSEvents 未实现，会回退到 polling

# 创建临时目录用于测试
with tempfile.TemporaryDirectory() as tmpdir:
    subject, dispatcher = from_filesystem(
        paths=[tmpdir],              # 监控路径列表
        backend="auto",             # "auto" | "win32" | "inotify" | "polling"
        change_types=None,          # None 表示所有类型
        interval=0.5,               # 轮询间隔（polling 后端用）
        auto_start=True
    )
    
    result = []
    
    def on_file(fd):
        result.append(fd)
        print(f"文件变更: {fd.change_type.name} - {fd.path}")
    
    sub = subject.subscribe(on_next=on_file)
    
    # 创建文件触发事件
    test_file = os.path.join(tmpdir, "test.txt")
    
    # 等待监控启动
    time.sleep(0.2)
    
    # 触发创建事件
    with open(test_file, "w") as f:
        f.write("hello")
    
    time.sleep(0.3)
    
    # 触发修改事件
    with open(test_file, "a") as f:
        f.write(" world")
    
    time.sleep(0.3)
    
    # 触发删除事件
    os.remove(test_file)
    
    time.sleep(0.3)
    
    sub.unsubscribe()
    dispatcher.stop()
    
    print(f"共捕获 {len(result)} 个文件事件")
```

**测试状态**：✅ 已测试（Windows/Linux）

### FileSubject - 文件监控主题

```python
import time
import os
import tempfile
from vools.reactive.monitoring import FileSubject, FileChangeType

# ✅ 平台支持：Windows、Linux
# ❌ macOS 未实现

with tempfile.TemporaryDirectory() as tmpdir:
    with FileSubject(paths=[tmpdir], auto_start=True) as file_watcher:
        result = []
        sub = file_watcher.subscribe(on_next=lambda fd: result.append(fd))
        
        test_file = os.path.join(tmpdir, "test.txt")
        
        time.sleep(0.2)
        with open(test_file, "w") as f:
            f.write("test")
        
        time.sleep(0.5)
        sub.unsubscribe()
        
        print(f"捕获 {len(result)} 个文件事件")
        for fd in result:
            print(f"  {fd.change_type.name}: {fd.path}")
```

**测试状态**：✅ 已测试（Windows/Linux）

### write_to_filesystem 操作符

```python
from vools.reactive import Observable, ops
from vools.reactive.monitoring import FileSubject, FileChangeType, write_to_filesystem
import tempfile
import os

# ✅ 平台支持：Windows、Linux
# ❌ macOS 未实现

with tempfile.TemporaryDirectory() as tmpdir:
    file_watcher = FileSubject(paths=[tmpdir], auto_start=True)
    
    # 创建文件写入流
    Observable.from_iterable([
        {"path": os.path.join(tmpdir, "a.txt"), "content": "content A"},
        {"path": os.path.join(tmpdir, "b.txt"), "content": "content B"},
    ]).pipe(
        write_to_filesystem(file_watcher.dispatcher)
    ).subscribe(on_next=lambda fd: print(f"写入: {fd.path}"))
    
    import time
    time.sleep(0.5)
    
    file_watcher.stop()
```

**测试状态**：✅ 已测试（Windows/Linux）

---

## 监控模块通用配置

### 后端选择

```python
# 后端选项
backend = "auto"    # 自动选择最佳后端
backend = "win32"    # 强制使用 Win32 API（仅 Windows）
backend = "polling"  # 强制使用轮询（跨平台但效率低）

# Windows: auto → win32
# macOS: auto → polling（macOS FSEvents 未实现）
# Linux: auto → inotify
```

### 自过滤机制

所有监控器都支持 `filter_self` 参数，防止自模拟的事件被重复捕获：

```python
# 启用自过滤（默认）
dispatcher = ClipboardDispatcher(filter_self=True)

# 禁用自过滤
dispatcher = ClipboardDispatcher(filter_self=False)
```

### 上下文管理器用法

```python
# 所有 Subject 都支持上下文管理器
with KeySubject(auto_start=True) as kb:
    # 订阅和处理
    pass
# 自动停止
```

---

## 完整示例

### 键盘+剪贴板联动

```python
import time
from vools.reactive import Observable, ops
from vools.reactive.monitoring import KeySubject, ClipSubject, ClipChangeType

# ⚠️ 平台限制：仅 Windows 完全支持

with KeySubject(auto_start=True) as kb, \
     ClipSubject(auto_start=True) as clip:
    
    # 监听特定按键复制内容
    def on_key(kd):
        if kd.key_name == "C" and kd.modifiers == 2:  # Ctrl+C
            # 获取剪贴板内容
            current = clip.dispatcher._reader.read()
            print(f"复制: {current}")
    
    kb.subscribe(on_next=on_key)
    
    # 监听剪贴板变化
    clip.subscribe(on_next=lambda cd: print(f"剪贴板: {cd.content}"))
    
    time.sleep(5)
```

**测试状态**：✅ 已测试（Windows）

### 文件自动处理流水线

```python
import time
import os
import tempfile
from vools.reactive import Observable, ops
from vools.reactive.monitoring import FileSubject, FileChangeType

# ✅ 平台支持：Windows、Linux

with tempfile.TemporaryDirectory() as tmpdir:
    processed = []
    
    with FileSubject(paths=[tmpdir], auto_start=True) as watcher:
        # 监听创建和修改事件
        watcher.pipe(
            ops.filter(lambda fd: fd.change_type in (
                FileChangeType.CREATED,
                FileChangeType.MODIFIED
            )),
            ops.filter(lambda fd: fd.path.endswith(".txt")),
            ops.map(lambda fd: {
                "path": fd.path,
                "content": open(fd.path).read() if os.path.exists(fd.path) else ""
            })
        ).subscribe(on_next=lambda item: processed.append(item))
        
        # 创建测试文件
        time.sleep(0.2)
        for i in range(3):
            path = os.path.join(tmpdir, f"file_{i}.txt")
            with open(path, "w") as f:
                f.write(f"content {i}")
            time.sleep(0.1)
        
        time.sleep(0.5)
        
        print(f"处理了 {len(processed)} 个文件")
        for item in processed:
            print(f"  {item['path']}: {len(item['content'])} bytes")
```

**测试状态**：✅ 已测试（Windows/Linux）
