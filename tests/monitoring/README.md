# 测试架构说明

## 双进程测试架构

本目录采用**双进程测试架构**，用于测试系统级监控功能（窗口、进程、剪贴板、键盘、鼠标等）。

### 架构组成

- **控制进程（主测试进程）**：运行 pytest 测试用例，通过 RPC 控制 Dispatcher
- **模拟子进程（simulators/）**：独立进程运行 Dispatcher，模拟用户交互

### 架构优势

1. **隔离性**：测试进程不会干扰被监控的系统资源
2. **可控性**：控制进程可以精确控制测试时序
3. **真实性**：子进程运行真实的 Dispatcher 代码
4. **可观测性**：通过 RPC 接口观察和验证系统行为

## simulators/ 目录

模拟器模块，用于启动独立进程运行 Dispatcher：

```
simulators/
├── __init__.py          # 导出所有模拟器
├── clipboard_sim.py     # 剪贴板模拟器
├── keyboard_sim.py      # 键盘模拟器
├── mouse_sim.py         # 鼠标模拟器
├── file_sim.py          # 文件监控模拟器
├── folder_sim.py        # 文件夹监控模拟器
└── utils.py             # 共享工具函数
```

### 模拟器接口

每个模拟器提供标准的 RPC 接口：

```python
# 启动模拟器
python -m tests.monitoring.simulators.clipboard_sim

# RPC 接口示例（以剪贴板为例）
sim = ClipboardSimulator()
sim.start()                    # 启动 Dispatcher
sim.set_clipboard_text("test") # 设置剪贴板内容
events = sim.get_events()      # 获取事件列表
sim.stop()                     # 停止 Dispatcher
```

## 运行测试

### 单元测试

运行所有单元测试（不涉及系统交互）：

```bash
pytest tests/monitoring/ -v
```

### 集成测试

仅运行集成测试（标记为 `@pytest.mark.integration`）：

```bash
pytest tests/monitoring/ -v -m integration
```

### Windows 专用测试

某些测试仅在 Windows 平台运行（标记为 `@pytest.mark.windows_only`）：

```bash
pytest tests/monitoring/ -v -m windows_only
```

## 测试标记说明

| 标记 | 说明 | 使用场景 |
|------|------|---------|
| `integration` | 集成测试 | 需要真实系统交互的测试 |
| `windows_only` | Windows 专用 | 依赖 Windows API 的测试 |
| `slow` | 慢速测试 | 执行时间 > 1 秒的测试 |

## 测试文件命名规范

- `test_*_integration.py`：集成测试（涉及真实系统交互）
- `test_*_observer.py`：Observer 行为测试
- `test_*_monitor.py`：Dispatcher 功能测试
- `*_sim.py`：模拟器模块（不包含测试用例）

## 添加新测试

### 添加新的模拟器

1. 在 `simulators/` 下创建新文件（如 `window_sim.py`）
2. 实现 `WindowSimulator` 类，提供标准 RPC 接口
3. 在 `simulators/__init__.py` 中导出

### 添加新的集成测试

1. 创建 `test_<feature>_integration.py`
2. 添加标记：`@pytest.mark.integration`
3. 使用模拟器控制子进程：

```python
import pytest
from .simulators import ClipboardSimulator

@pytest.mark.integration
def test_clipboard_integration():
    sim = ClipboardSimulator()
    sim.start()

    try:
        sim.set_clipboard_text("test")
        events = sim.get_events()
        assert len(events) > 0
    finally:
        sim.stop()
```

## 注意事项

⚠️ **Windows 平台限制**：所有监控模块仅支持 Windows 平台，测试在 Linux/macOS 上会被跳过。

⚠️ **系统权限**：部分监控（如全局热键）需要管理员权限，测试时应注意权限要求。

⚠️ **测试隔离**：集成测试可能影响真实系统状态，建议在虚拟机或隔离环境中运行。