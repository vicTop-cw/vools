# vools.bridge.vbnet.api — API.tlb COM 组件桥接

> 通过 COM 互操作封装 API.tlb 中的 COM 组件，为 Python 提供 Windows 自动化能力

## 模块简介

`vools.bridge.vbnet.api` 模块封装了 API.tlb 类型库中的 COM 组件，通过 pywin32 的 win32com 接口，为 Python 提供了一套完整的 Windows 自动化功能，包括窗口操作、鼠标键盘模拟、屏幕截图、图像处理、文件系统操作、进程管理和网络功能等。

该模块是 vools 项目中 VB.NET 桥接的重要组成部分，与 `vools.bridge.vbnet` 编译器桥接不同，`api` 子包直接调用已注册的 COM 组件，无需编译代码，开箱即用（需提前注册 API.dll）。

## 主要功能

| 功能模块 | 说明 |
|---------|------|
| Window | 窗口查找、信息获取、位置大小控制、状态管理 |
| Mouse | 鼠标移动、各种按键操作和滚轮控制 |
| Keyboard | 键盘按键模拟、按键状态查询、锁键状态 |
| Image | 屏幕截图、图像加载/保存、像素操作、图像变换 |
| FileSystem | 文件和目录的创建、删除、读写、路径操作 |
| Process | 进程启动、查询、终止、等待 |
| Network | 网络可用性检测、文件下载、URL 编解码、网页源码获取 |

## 安装前置条件

### 1. Windows 操作系统

本模块仅支持 Windows 平台，依赖 Windows 7 及以上版本。

### 2. API.dll / API.tlb 注册

确保 API.dll 已正确注册为 COM 组件：

```cmd
:: 使用管理员权限运行命令提示符
regsvr32 API.dll
```

如果 API.tlb 是 .NET 程序集暴露的 COM 接口，可能需要使用：

```cmd
regasm /tlb:API.tlb /codebase API.dll
```

### 3. pywin32

安装 pywin32 库（提供 win32com 支持：

```bash
pip install pywin32
```

安装完成后，建议执行以下命令确保 COM 支持：

```bash
python -m pywin32_postinstall
```

## 快速开始

### 检测可用性

```python
from vools.bridge.vbnet import api

if api.is_api_available():
    print("API.tlb 组件可用")
else:
    print("API.tlb 组件不可用")
```

### 基本使用示例

```python
from vools.bridge.vbnet import api

if api.is_api_available():
    # ========== Window 模块示例 ==========
    # 查找记事本窗口
    hwnd = api.Window.FindWindow("Notepad", None)
    if hwnd:
        print(f"记事本句柄: {hwnd}")
        # 获取窗口标题
        title = api.Window.GetWindowText(hwnd)
        print(f"窗口标题: {title}")
        # 获取窗口位置大小
        rect = api.Window.GetWindowRect(hwnd)
        print(f"窗口矩形: {rect}")

    # ========== Mouse 模块示例 ==========
    # 移动鼠标到 (100, 200)
    api.Mouse.MouseMove(100, 200)
    # 左键单击
    api.Mouse.LeftClick()

    # ========== Keyboard 模块示例 ==========
    # 发送文本
    api.Keyboard.SendKeys("Hello, World!")
    # 按下并释放回车键
    api.Keyboard.KeyDownUp(0x0D)  # VK_RETURN

    # ========== Image 模块示例 ==========
    # 获取指定像素颜色
    color = api.Image.GetPixelColor(100, 100)
    print(f"像素颜色: 0x{color:06X}")

    # ========== FileSystem 模块示例 ==========
    # 判断文件是否存在
    exists = api.FileSystem.FileExists("C:\\test.txt")
    print(f"文件存在: {exists}")

    # ========== Process 模块示例 ==========
    # 启动进程
    pid = api.Process.Start("notepad.exe")
    print(f"启动的进程ID: {pid}")

    # ========== Network 模块示例 ==========
    # 检测网络是否可用
    net_available = api.Network.NetworkIsAvailable()
    print(f"网络可用: {net_available}")
```

## 支持的模块列表

### Window 模块（窗口操作）

**ProgID**: `API.Window`

**主要方法**:

| 方法 | 说明 | 参数 | 返回值 |
|------|------|------|--------|
| `FindWindow(class_name, window_name)` | 查找顶级窗口 | class_name: 窗口类名<br>window_name: 窗口标题 | int: 窗口句柄 |
| `FindWindowEx(parent, child_after, class_name, window_name)` | 查找子窗口 | parent: 父窗口句柄<br>child_after: 起始位置 | int: 子窗口句柄 |
| `GetWindowText(hwnd)` | 获取窗口标题 | hwnd: 窗口句柄 | str: 窗口标题 |
| `SetWindowText(hwnd, text)` | 设置窗口标题 | hwnd: 窗口句柄<br>text: 新标题 | bool: 是否成功 |
| `GetWindowRect(hwnd)` | 获取窗口矩形 | hwnd: 窗口句柄 | tuple: (left, top, right, bottom) |
| `GetClientRect(hwnd)` | 获取客户区矩形 | hwnd: 窗口句柄 | tuple: (left, top, right, bottom) |
| `MoveWindow(hwnd, x, y, w, h)` | 移动并调整窗口 | hwnd: 窗口句柄<br>x,y,w,h: 位置大小 | bool: 是否成功 |
| `ShowWindow(hwnd, cmd_show)` | 显示/隐藏窗口 | hwnd: 窗口句柄<br>cmd_show: 显示命令 | bool: 是否成功 |
| `CloseWindow(hwnd)` | 最小化窗口 | hwnd: 窗口句柄 | bool: 是否成功 |
| `EnableWindow(hwnd, enable)` | 启用/禁用窗口 | hwnd: 窗口句柄<br>enable: bool | bool: 是否成功 |
| `IsWindowExists(hwnd)` | 检查窗口是否存在 | hwnd: 窗口句柄 | bool: 是否存在 |
| `GetClassName(hwnd)` | 获取窗口类名 | hwnd: 窗口句柄 | str: 类名 |
| `GetParent(hwnd)` | 获取父窗口句柄 | hwnd: 窗口句柄 | int: 父窗口句柄 |
| `SetParent(hwnd, parent_hwnd)` | 设置父窗口 | hwnd: 子窗口句柄<br>parent_hwnd: 新父窗口 | int: 原父窗口句柄 |
| `GetForegroundWindow()` | 获取前台窗口 | - | int: 前台窗口句柄 |
| `SetForegroundWindow(hwnd)` | 设置前台窗口 | hwnd: 窗口句柄 | bool: 是否成功 |
| `GetDesktopWindow()` | 获取桌面窗口 | - | int: 桌面窗口句柄 |
| `GetWindowProcessId(hwnd)` | 获取窗口进程ID | hwnd: 窗口句柄 | int: 进程ID |
| `BringWindowToTop(hwnd)` | 窗口置顶 | hwnd: 窗口句柄 | bool: 是否成功 |

### Mouse 模块（鼠标操作）

**ProgID**: `API.Mouse`

**主要方法**:

| 方法 | 说明 | 参数 |
|------|------|------|
| `MouseMove(x, y)` | 移动鼠标到指定位置 | x: X坐标<br>y: Y坐标 |
| `LeftDown()` | 按下鼠标左键 | - |
| `LeftUp()` | 释放鼠标左键 | - |
| `LeftClick()` | 鼠标左键单击 | - |
| `RightDown()` | 按下鼠标右键 | - |
| `RightUp()` | 释放鼠标右键 | - |
| `RightClick()` | 鼠标右键单击 | - |
| `MiddleDown()` | 按下鼠标中键 | - |
| `MiddleUp()` | 释放鼠标中键 | - |
| `MiddleClick()` | 鼠标中键单击 | - |
| `DoubleClick()` | 鼠标左键双击 | - |
| `MouseWheel(delta)` | 滚动鼠标滚轮 | delta: 滚动量（正上负下） |

### Keyboard 模块（键盘操作）

**ProgID**: `API.Keyboard`

**主要方法**:

| 方法 | 说明 | 参数 | 返回值 |
|------|------|------|--------|
| `SendKeys(text)` | 发送键盘输入文本 | text: 要发送的文本 | - |
| `KeyDown(vk_code)` | 按下指定虚拟键 | vk_code: 虚拟键码 | - |
| `KeyUp(vk_code)` | 释放指定虚拟键 | vk_code: 虚拟键码 | - |
| `KeyDownUp(vk_code)` | 按下并释放虚拟键 | vk_code: 虚拟键码 | - |
| `GetKeyPressed(vk_code)` | 查询按键是否按下 | vk_code: 虚拟键码 | bool: 是否按下 |
| `GetKeyOpened(vk_code)` | 查询锁键是否开启 | vk_code: 虚拟键码 | bool: 是否开启 |
| `AltKeyPressed()` | Alt 键是否按下 | - | bool: 是否按下 |
| `CtrlKeyPressed()` | Ctrl 键是否按下 | - | bool: 是否按下 |
| `ShiftKeyPressed()` | Shift 键是否按下 | - | bool: 是否按下 |
| `CapsLockOpened()` | CapsLock 是否开启 | - | bool: 是否开启 |
| `NumLockOpened()` | NumLock 是否开启 | - | bool: 是否开启 |
| `ScrollLockOpened()` | ScrollLock 是否开启 | - | bool: 是否开启 |

### Image 模块（图像处理与截图）

**ProgID**: `API.Image`

**主要方法**:

| 方法 | 说明 | 参数 | 返回值 |
|------|------|------|--------|
| `ScreenCapture(left, top, right, bottom)` | 截取指定区域屏幕 | left, top, right, bottom: 区域坐标 | 图像对象 |
| `CaptureFullScreen()` | 截取整个屏幕 | - | 图像对象 |
| `OpenImage(file_path)` | 从文件加载图像 | file_path: 图像文件路径 | 图像对象 |
| `SaveImage(image, file_path)` | 保存图像到文件 | image: 图像对象<br>file_path: 保存路径 | bool: 是否成功 |
| `GetPixelColor(x, y)` | 获取屏幕像素颜色 | x: X坐标<br>y: Y坐标 | int: COLORREF 颜色值 |
| `SetPixelColor(x, y, color)` | 设置屏幕像素颜色 | x,y: 坐标<br>color: 颜色值 | bool: 是否成功 |
| `ChangeSize(image, width, height)` | 调整图像大小 | image: 图像对象<br>width, height: 新尺寸 | 图像对象 |
| `CropImage(image, x, y, w, h)` | 裁剪图像 | image: 图像对象<br>x,y,w,h: 裁剪区域 | 图像对象 |
| `RotateFlip(image, rotate_type)` | 旋转或翻转图像 | image: 图像对象<br>rotate_type: 旋转类型 | 图像对象 |
| `CreateNewBitmap(width, height)` | 创建空白位图 | width, height: 尺寸 | 图像对象 |

### FileSystem 模块（文件系统操作）

**ProgID**: `API.FileSystem`

**主要方法**:

| 方法 | 说明 | 参数 | 返回值 |
|------|------|------|--------|
| `CreateDirectory(path)` | 创建目录 | path: 目录路径 | bool: 是否成功 |
| `DeleteDirectory(path)` | 删除目录 | path: 目录路径 | bool: 是否成功 |
| `DeleteFile(path)` | 删除文件 | path: 文件路径 | bool: 是否成功 |
| `ReadAllText(path, encoding)` | 读取文本文件全部内容 | path: 文件路径<br>encoding: 编码（可选） | str: 文件内容 |
| `WriteAllText(path, text, encoding)` | 写入文本到文件 | path: 文件路径<br>text: 文本<br>encoding: 编码（可选） | bool: 是否成功 |
| `CombinePath(path1, path2)` | 合并两个路径 | path1, path2: 路径 | str: 合并后的路径 |
| `DirectoryExists(path)` | 判断目录是否存在 | path: 目录路径 | bool: 是否存在 |
| `FileExists(path)` | 判断文件是否存在 | path: 文件路径 | bool: 是否存在 |
| `GetParentPath(path)` | 获取父目录路径 | path: 路径 | str: 父目录路径 |
| `CopyFile(src, dst)` | 复制文件 | src: 源路径<br>dst: 目标路径 | bool: 是否成功 |
| `MoveFile(src, dst)` | 移动文件 | src: 源路径<br>dst: 目标路径 | bool: 是否成功 |
| `RenameFile(path, new_name)` | 重命名文件 | path: 原路径<br>new_name: 新文件名 | bool: 是否成功 |

### Process 模块（进程管理）

**ProgID**: `API.Process`

**主要方法**:

| 方法 | 说明 | 参数 | 返回值 |
|------|------|------|--------|
| `Start(file_name, arguments, working_dir)` | 启动进程 | file_name: 可执行文件<br>arguments: 参数（可选）<br>working_dir: 工作目录（可选） | int: 进程ID |
| `Shell(file_name, arguments, working_dir)` | 通过 Shell 启动进程 | file_name: 文件路径<br>arguments: 参数（可选）<br>working_dir: 工作目录（可选） | int: 实例ID |
| `GetProcesses()` | 获取所有运行进程 | - | list: 进程列表 |
| `GetProcessesByName(name)` | 按名称获取进程 | name: 进程名称 | list: 进程列表 |
| `Kill(process_id)` | 终止进程 | process_id: 进程ID | bool: 是否成功 |
| `WaitForExit(process_id, timeout)` | 等待进程退出 | process_id: 进程ID<br>timeout: 超时毫秒（默认-1无限） | bool: 是否已退出 |
| `HasExited(process_id)` | 检查进程是否退出 | process_id: 进程ID | bool: 是否已退出 |
| `GetProcessId(hwnd)` | 根据窗口句柄获取进程ID | hwnd: 窗口句柄 | int: 进程ID |

### Network 模块（网络功能）

**ProgID**: `API.Network`

**主要方法**:

| 方法 | 说明 | 参数 | 返回值 |
|------|------|------|--------|
| `NetworkIsAvailable()` | 检测网络是否可用 | - | bool: 是否可用 |
| `DownloadFile(url, save_path)` | 下载文件到本地 | url: 文件URL<br>save_path: 本地保存路径 | bool: 是否成功 |
| `UrlEncode(text)` | URL 编码 | text: 要编码的文本 | str: 编码后字符串 |
| `UrlDecode(text)` | URL 解码 | text: 要解码的字符串 | str: 解码后文本 |
| `GetWebSourceCode(url)` | 获取网页源代码 | url: 网页URL | str: HTML源码 |
| `GetIPAddresses()` | 获取本机IP地址列表 | - | list: IP地址列表 |

## 核心架构

### 异常类

**`APIBridgeError` — API 桥接异常基类，所有 API.tlb 桥接相关异常都从此类派生。

```python
try:
    api.Window.FindWindow("Notepad", None)
except api.APIBridgeError as e:
    print(f"错误: {e}")
    if e.cause:
        print(f"原因: {e.cause}")
```

### COM 对象缓存

内部使用 `_COMObjectCache` 管理 COM 对象单例缓存，确保每个 ProgID 只创建一次实例，提供延迟创建和缓存复用机制。

### 模块基类

`_BaseModule` 提供通用的 COM 对象调用逻辑：
- 延迟获取 COM 对象
- 异常转换（COM 异常 → APIBridgeError）
- 返回值类型转换（int, str, bool, rect, list 等）

## 常见问题与故障排除

### Q1: 调用 `is_api_available()` 返回 False

**可能原因及解决方案**:

1. **非 Windows 平台**: 本模块仅支持 Windows

2. **pywin32 未安装**:
   ```bash
   pip install pywin32
   python -m pywin32_postinstall
   ```

3. **API.dll 未注册**:
   ```cmd
   regsvr32 API.dll
   ```
   或对于 .NET 程序集：
   ```cmd
   regasm /tlb:API.tlb /codebase API.dll
   ```

### Q2: 导入模块时提示 ImportError

确保安装了 pywin32：

```bash
pip install pywin32
```

### Q3: 调用方法时出现 "无法创建 COM 对象"

- 确认 API.dll 已正确注册
- 检查 ProgID 是否正确（API.Window, API.Mouse 等
- 尝试使用 查看注册表中是否存在对应的 COM 注册项

### Q4: 在 64 位 Python 上使用 32 位 API.dll

**问题**: 无法创建 COM 对象

**解决方案**:
- 确保 Python 位数与 DLL 位数一致
- 32 位 DLL 需要 32 位 Python
- 64 位 DLL 需要 64 位 Python

### Q5: 如何查看支持哪些 ProgID？

```python
from vools.bridge.vbnet.api._base import _COMObjectCache

cache = _COMObjectCache()
print(cache.supported_progids)
```

支持的 ProgID 列表：
- `API.Window`
- `API.Mouse`
- `API.Keyboard`
- `API.Image`
- `API.FileSystem`
- `API.Process`
- `API.Network`

## 注意事项

- 本模块仅支持 Windows 平台
- 需要提前安装并注册 API.dll/API.tlb
- 需要安装 pywin32 库
- COM 对象采用延迟初始化，首次访问时才创建
- 所有 COM 异常都会被包装为 APIBridgeError
- 建议在使用前通过 is_api_available()` 检测可用性
- 请注意 Python 位数与 API.dll 位数必须一致（32位/64位）

## 相关资源

- [pywin32 文档](https://github.com/mhammond/pywin32)
- [Windows API 文档](https://learn.microsoft.com/en-us/windows/win32/)
- [vools.bridge.vbnet 模块](../README.md)
