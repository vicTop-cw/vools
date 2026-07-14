# 监控类测试设计方案

## 双进程架构

监控类测试采用**控制进程 + 模拟进程**双进程架构：

```
┌─────────────────────────────────────────────────────────────────────┐
│                         测试主进程（控制进程）                          │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │ 1. 启动监控器 Subject                                            │ │
│  │ 2. 创建控制文件（写入 "start"）                                    │ │
│  │ 3. 启动模拟子进程                                                 │ │
│  │ 4. 等待事件到达（带超时）                                          │ │
│  │ 5. 验证事件内容                                                   │ │
│  │ 6. 写入控制文件 "stop" → 终止模拟进程                              │ │
│  │ 7. 清理资源                                                       │ │
│  └─────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ 子进程
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        模拟子进程（Simulator）                        │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │ 1. 读取控制文件，等待 "start"                                     │ │
│  │ 2. 执行模拟操作（按键/鼠标/剪贴板/文件操作）                        │ │
│  │ 3. 记录操作结果到日志文件                                          │ │
│  │ 4. 循环检测控制文件，收到 "stop" 时退出                            │ │
│  └─────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

## 进程间通信

使用**控制文件 + 日志文件**进行进程间通信：

| 文件类型 | 用途 | 格式 |
|----------|------|------|
| `{test}_control.json` | 主进程→子进程控制指令 | `{"action": "start"|"stop"|"simulate", "params": {...}}` |
| `{test}_log.jsonl` | 子进程→主进程操作日志 | 每行一个 JSON 记录 |

## 各监控类型测试设计

### 1. 键盘监控测试

**控制进程**：
```python
def test_keyboard_events():
    control_file = Path("keyboard_control.json")
    log_file = Path("keyboard_log.jsonl")
    
    # 启动监控
    with KeySubject() as ks:
        events = []
        ks.subscribe(on_next=lambda kd: events.append(kd))
        
        # 启动模拟子进程
        write_control(control_file, {"action": "start", "keys": ["A", "ENTER", "F1"]})
        proc = subprocess.Popen([sys.executable, "simulators/keyboard_sim.py", control_file, log_file])
        
        # 等待事件
        time.sleep(2)
        
        # 验证
        assert len(events) >= 3
        assert any(e.key_name == "A" for e in events)
        
        # 停止
        write_control(control_file, {"action": "stop"})
        proc.wait(timeout=5)
```

**模拟子进程** (`simulators/keyboard_sim.py`)：
```python
import ctypes
import json
import time
from pathlib import Path

def simulate_keys(keys):
    user32 = ctypes.windll.user32
    INPUT_KEYBOARD = 1
    KEYEVENTF_KEYUP = 0x0002
    
    for key in keys:
        vk = vk_code(key)
        # key down
        user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.05)
        # key up
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.1)
        log_event(log_file, "key_press", key=key)

def main(control_file, log_file):
    while True:
        ctrl = read_control(control_file)
        if ctrl and ctrl.get("action") == "start":
            simulate_keys(ctrl["keys"])
        if ctrl and ctrl.get("action") == "stop":
            break
        time.sleep(0.1)
```

### 2. 鼠标监控测试

**模拟操作**：`SetCursorPos` + `mouse_event` / `SendInput`
- 移动到指定坐标
- 左键点击
- 右键点击
- 滚轮滚动

### 3. 剪贴板监控测试

**模拟操作**：`OpenClipboard` + `EmptyClipboard` + `SetClipboardData`
- 写入文本
- 写入文件列表（CF_HDROP）
- 清空剪贴板

### 4. 文件监控测试

**模拟操作**：标准 `open/write/close` + `os.remove`
- 创建文件
- 修改文件内容
- 删除文件

### 5. 文件夹监控测试

**模拟操作**：`os.mkdir` / `os.rmdir` + `shutil.rmtree`
- 创建文件夹
- 创建子文件
- 删除文件夹

### 6. 窗口监控测试（新增）

**模拟操作**：创建隐藏窗口 / 切换焦点
- 使用 `CreateWindowEx` 创建临时窗口
- 使用 `SetForegroundWindow` 切换焦点

### 7. 进程监控测试（新增）

**模拟操作**：启动子进程 / 终止子进程
- `subprocess.Popen` 启动测试进程
- `proc.kill()` / `proc.terminate()` 终止进程

## 测试目录结构

```
tests/
├── monitoring/
│   ├── simulators/                    # 模拟子进程脚本
│   │   ├── __init__.py
│   │   ├── keyboard_sim.py            # 键盘模拟
│   │   ├── mouse_sim.py               # 鼠标模拟
│   │   ├── clipboard_sim.py           # 剪贴板模拟
│   │   ├── file_sim.py                # 文件模拟
│   │   ├── folder_sim.py              # 文件夹模拟
│   │   ├── window_sim.py              # 窗口模拟（新增）
│   │   ├── process_sim.py             # 进程模拟（新增）
│   │   └── utils.py                   # 公共函数（控制文件读写、日志）
│   │
│   ├── test_keyboard.py               # 键盘监控单元测试（单进程）
│   ├── test_keyboard_integration.py   # 键盘监控集成测试（双进程）
│   ├── test_mouse.py
│   ├── test_mouse_integration.py
│   ├── test_clipboard.py
│   ├── test_clipboard_integration.py
│   ├── test_file_watcher.py
│   ├── test_file_watcher_integration.py
│   ├── test_folder_watcher.py
│   ├── test_folder_watcher_integration.py
│   ├── test_window.py                 # 新增
│   ├── test_window_integration.py     # 新增
│   ├── test_process.py                # 新增
│   └── test_process_integration.py    # 新增
│   │
│   └── conftest.py                    # pytest fixtures
```

## 测试标记

```python
import pytest

# 集成测试标记（需要真实系统事件）
pytestmark = pytest.mark.integration

# Windows 平台标记
pytestmark = pytest.mark.windows_only

# 跳过 CI 环境的标记（CI 无法模拟用户交互）
pytestmark = pytest.mark.skip_ci
```

## 运行测试

```powershell
# 运行所有单元测试（单进程，快速）
pytest tests/monitoring/ -v -m "not integration"

# 运行集成测试（双进程，需要交互）
pytest tests/monitoring/ -v -m "integration"

# 运行特定监控类型
pytest tests/monitoring/test_keyboard_integration.py -v

# 排除监控集成测试
pytest tests/ -v --ignore=tests/monitoring
```