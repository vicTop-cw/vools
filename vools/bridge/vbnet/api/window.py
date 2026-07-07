"""
Window 模块 - 窗口操作

封装 API.Window COM 对象，提供窗口查找、信息获取、位置大小控制等功能。
"""

from typing import Optional, Tuple

from ._base import APIBridgeError, _BaseModule


class WindowModule(_BaseModule):
    """窗口操作模块

    提供窗口查找、信息获取、位置大小控制、状态管理等功能。
    """

    _prog_id = "API.Window"

    def FindWindow(self, class_name: Optional[str] = None, window_name: Optional[str] = None) -> int:
        """查找顶级窗口

        Args:
            class_name: 窗口类名，为 None 时匹配任意类名
            window_name: 窗口标题，为 None 时匹配任意标题

        Returns:
            int: 窗口句柄 (HWND)，失败返回 0
        """
        return self._call_int("FindWindow", class_name or "", window_name or "")

    def FindWindowEx(self, parent_hwnd: int, child_after: int = 0,
                    class_name: Optional[str] = None,
                    window_name: Optional[str] = None) -> int:
        """查找子窗口

        Args:
            parent_hwnd: 父窗口句柄
            child_after: 子窗口起始位置，0 表示从第一个子窗口开始
            class_name: 窗口类名，为 None 时匹配任意类名
            window_name: 窗口标题，为 None 时匹配任意标题

        Returns:
            int: 子窗口句柄，失败返回 0
        """
        return self._call_int("FindWindowEx", parent_hwnd, child_after,
                             class_name or "", window_name or "")

    def GetWindowText(self, hwnd: int) -> str:
        """获取窗口标题文本

        Args:
            hwnd: 窗口句柄

        Returns:
            str: 窗口标题文本
        """
        return self._call_str("GetWindowText", hwnd)

    def SetWindowText(self, hwnd: int, text: str) -> bool:
        """设置窗口标题文本

        Args:
            hwnd: 窗口句柄
            text: 新的窗口标题

        Returns:
            bool: 是否成功
        """
        return self._call_bool("SetWindowText", hwnd, text)

    def GetWindowRect(self, hwnd: int) -> Tuple[int, int, int, int]:
        """获取窗口矩形区域（屏幕坐标）

        Args:
            hwnd: 窗口句柄

        Returns:
            tuple: (left, top, right, bottom) 矩形坐标
        """
        return self._call_rect("GetWindowRect", hwnd)

    def GetClientRect(self, hwnd: int) -> Tuple[int, int, int, int]:
        """获取客户区矩形（客户区坐标）

        Args:
            hwnd: 窗口句柄

        Returns:
            tuple: (left, top, right, bottom) 客户区矩形，left 和 top 通常为 0
        """
        return self._call_rect("GetClientRect", hwnd)

    def MoveWindow(self, hwnd: int, x: int, y: int, w: int, h: int) -> bool:
        """移动并调整窗口大小

        Args:
            hwnd: 窗口句柄
            x: 新的左上角 X 坐标
            y: 新的左上角 Y 坐标
            w: 新的宽度
            h: 新的高度

        Returns:
            bool: 是否成功
        """
        return self._call_bool("MoveWindow", hwnd, x, y, w, h)

    def ShowWindow(self, hwnd: int, cmd_show: int) -> bool:
        """显示或隐藏窗口

        Args:
            hwnd: 窗口句柄
            cmd_show: 显示命令（SW_* 常量）

        Returns:
            bool: 是否成功
        """
        return self._call_bool("ShowWindow", hwnd, cmd_show)

    def CloseWindow(self, hwnd: int) -> bool:
        """最小化窗口（关闭窗口）

        Args:
            hwnd: 窗口句柄

        Returns:
            bool: 是否成功
        """
        return self._call_bool("CloseWindow", hwnd)

    def EnableWindow(self, hwnd: int, enable: bool) -> bool:
        """启用或禁用窗口

        Args:
            hwnd: 窗口句柄
            enable: True 启用，False 禁用

        Returns:
            bool: 是否成功
        """
        return self._call_bool("EnableWindow", hwnd, enable)

    def IsWindowExists(self, hwnd: int) -> bool:
        """检查窗口是否存在

        Args:
            hwnd: 窗口句柄

        Returns:
            bool: 窗口是否存在
        """
        return self._call_bool("IsWindowExists", hwnd)

    def GetClassName(self, hwnd: int) -> str:
        """获取窗口类名

        Args:
            hwnd: 窗口句柄

        Returns:
            str: 窗口类名
        """
        return self._call_str("GetClassName", hwnd)

    def GetParent(self, hwnd: int) -> int:
        """获取父窗口句柄

        Args:
            hwnd: 窗口句柄

        Returns:
            int: 父窗口句柄
        """
        return self._call_int("GetParent", hwnd)

    def SetParent(self, hwnd: int, parent_hwnd: int) -> int:
        """设置父窗口

        Args:
            hwnd: 子窗口句柄
            parent_hwnd: 新的父窗口句柄

        Returns:
            int: 原来的父窗口句柄
        """
        return self._call_int("SetParent", hwnd, parent_hwnd)

    def GetForegroundWindow(self) -> int:
        """获取前台窗口（当前激活的窗口）

        Returns:
            int: 前台窗口句柄
        """
        return self._call_int("GetForegroundWindow")

    def SetForegroundWindow(self, hwnd: int) -> bool:
        """设置窗口为前台窗口

        Args:
            hwnd: 窗口句柄

        Returns:
            bool: 是否成功
        """
        return self._call_bool("SetForegroundWindow", hwnd)

    def GetDesktopWindow(self) -> int:
        """获取桌面窗口句柄

        Returns:
            int: 桌面窗口句柄
        """
        return self._call_int("GetDesktopWindow")

    def GetWindowProcessId(self, hwnd: int) -> int:
        """获取创建窗口的进程 ID

        Args:
            hwnd: 窗口句柄

        Returns:
            int: 进程 ID
        """
        return self._call_int("GetWindowProcessId", hwnd)

    def BringWindowToTop(self, hwnd: int) -> bool:
        """将窗口置于 Z 序顶部

        Args:
            hwnd: 窗口句柄

        Returns:
            bool: 是否成功
        """
        return self._call_bool("BringWindowToTop", hwnd)


Window = WindowModule()
