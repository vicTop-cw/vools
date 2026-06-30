# 平台支持说明 (Platform)

> **模块路径**：-
> **依赖版本**：Python 3.6+
> **平台支持**：Windows/macOS/Linux
> **测试状态**：✅ 已测试
> **编号**：#A04
> **最后更新**：2026-06-30

---

## 概述

vools 是一个跨平台的 Python 库，支持 Windows、macOS 和 Linux。本文档说明各平台的特性和限制。

## Python 版本兼容性

| Python 版本 | 支持状态 | 备注 |
|------------|---------|------|
| 3.6.x | ✅ 支持 | 基础兼容 |
| 3.7.x | ✅ 支持 | 完全支持 |
| 3.8.x | ✅ 支持 | 完全支持 |
| 3.9.x | ✅ 支持 | 完全支持 |
| 3.10.x | ✅ 支持 | 完全支持 |
| 3.11.x | ✅ 支持 | 完全支持 |
| 3.12.x | ✅ 支持 | 完全支持 |
| 3.13.x | ✅ 支持 | 完全支持 |

## Windows 平台

### 支持版本

- Windows 7/8/10/11
- Windows Server 2016/2019/2022

### 特有功能

| 模块 | 功能 | 说明 |
|------|------|------|
| dll32 | DirectCOM 支持 | VB6 COM 组件调用 |
| dll32 | RC6 加密库 | RC6 对称加密 |
| dll32 | MQTT 客户端 | 基于 VB6Plus.dll |
| sys | Win32 注册表 | Windows 注册表操作 |
| reactive | Win32 钩子 | 低延迟键盘鼠标监控 |

### Windows 特有模块导入

```python
# dll32 模块（仅 Windows）
from vools.dll32 import vb6plus, mqtt, openssl

# 使用示例
result = vb6plus.base64_encode_utf8('Hello')
```

### WSL 支持

vools 支持在 Windows Subsystem for Linux (WSL) 中运行：

- 自动检测 WSL 环境
- 支持 WSL 发行版：Ubuntu, Debian, Kali, Alpine 等
- 编译器自动发现支持 WSL 路径

```python
from vools.bridge import discover_all

# 自动发现本机和 WSL 编译器
report = discover_all()
print(report)
```

## macOS 平台

### 支持版本

- macOS 10.14 (Mojave) 及以上
- Apple Silicon (M1/M2/M3) 和 Intel

### 特有功能

| 模块 | 功能 | 说明 |
|------|------|------|
| sys | 通知中心 | macOS 通知 |
| reactive | FSEvents | 文件系统事件监控 |

### 限制说明

- `dll32` 模块不可用（Windows 专用）
- 键盘鼠标监控使用 polling 模式（不如 Windows win32 钩子低延迟）

## Linux 平台

### 支持版本

- Ubuntu 18.04/20.04/22.04/24.04
- Debian 10/11/12
- CentOS 7/8
- 其他主流 Linux 发行版

### 特有功能

| 模块 | 功能 | 说明 |
|------|------|------|
| sys | inotify | 文件系统事件监控 |
| reactive | epoll | 高性能网络事件 |
| bridge | GCC/Clang | C/C++ 编译器桥接 |

### 限制说明

- `dll32` 模块不可用（Windows 专用）
- 键盘鼠标监控使用 polling 模式

## 跨平台兼容模块

以下模块在所有平台均可使用：

| 模块 | 功能 |
|------|------|
| decorators | 所有装饰器（@curry, @overload 等） |
| functional | 函数式工具（_, _1, g, pipe 等） |
| data | Seq 数据结构 |
| curried | 柯里化函数库 |
| cache | 缓存装饰器 |
| datetime | 日期时间工具 |
| encoding | 编码解码 |
| crypto | 加密解密 |
| serialize | 序列化 |
| reactive | 响应式编程（核心部分） |

## 响应式监控后端对比

| 功能 | Windows | macOS | Linux |
|------|---------|-------|-------|
| 键盘监控 | win32 钩子 | polling | polling |
| 鼠标监控 | win32 钩子 | polling | polling |
| 剪贴板 | Hook | polling | polling |
| 文件监控 | ReadDirectoryChangesW | FSEvents | inotify |

**推荐**：Windows 平台使用 `win32` 后端获得最低延迟。

## 安装注意事项

### Windows

```bash
# 使用 pip 安装
pip install vools

# 或从源码安装（需要编译工具）
git clone https://github.com/vicTop-cw/vools.git
cd vools
pip install -e .
```

### macOS / Linux

```bash
# 使用 pip 安装
pip install vools

# 或从源码安装
git clone https://github.com/vicTop-cw/vools.git
cd vools
pip install -e .
```

## 已知限制

1. **dll32 模块仅 Windows**：该模块依赖 Windows DLL，无法在其他平台使用
2. **win32 钩子仅 Windows**：响应式键盘鼠标监控在其他平台使用 polling
3. **某些 Nim 桥接库**：部分 Nim 编译库可能需要额外配置
