"""
vools.bridge.vbnet.api - API.tlb COM 组件桥接模块

封装 API.tlb 中的 COM 组件，为 Python 提供 Windows 自动化能力，
包括窗口操作、键鼠模拟、图像处理、文件系统、进程管理、网络等功能。

前置条件：
- Windows 操作系统
- API.dll / API.tlb 已正确注册为 COM 组件
- pywin32 (win32com) 已安装

用法：
    from vools.bridge.vbnet import api

    if api.is_api_available():
        # 使用 Window 模块
        hwnd = api.Window.FindWindow("Notepad", None)
        print(f"记事本句柄: {hwnd}")

        # 使用 Mouse 模块
        api.Mouse.MouseMove(100, 200)
        api.Mouse.LeftClick()
"""

from ._base import APIBridgeError, _COMObjectCache, _BaseModule, is_api_available
from .window import Window, WindowModule
from .mouse import Mouse, MouseModule
from .keyboard import Keyboard, KeyboardModule
from .image import Image, ImageModule
from .filesystem import FileSystem, FileSystemModule
from .process import Process, ProcessModule
from .network import Network, NetworkModule

__all__ = [
    'APIBridgeError',
    'is_api_available',
    'Window',
    'WindowModule',
    'Mouse',
    'MouseModule',
    'Keyboard',
    'KeyboardModule',
    'Image',
    'ImageModule',
    'FileSystem',
    'FileSystemModule',
    'Process',
    'ProcessModule',
    'Network',
    'NetworkModule',
]
