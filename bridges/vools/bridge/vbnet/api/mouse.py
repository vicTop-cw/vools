"""
Mouse 模块 - 鼠标操作

封装 API.Mouse COM 对象，提供鼠标移动、点击、滚轮等功能。
"""

from ._base import APIBridgeError, _BaseModule


class MouseModule(_BaseModule):
    """鼠标操作模块

    提供鼠标移动、各种按键操作和滚轮控制。
    """

    _prog_id = "API.Mouse"

    def MouseMove(self, x: int, y: int) -> None:
        """移动鼠标到指定位置

        Args:
            x: 目标 X 坐标（屏幕坐标）
            y: 目标 Y 坐标（屏幕坐标）
        """
        self._call("MouseMove", x, y)

    def LeftDown(self) -> None:
        """按下鼠标左键"""
        self._call("LeftDown")

    def LeftUp(self) -> None:
        """释放鼠标左键"""
        self._call("LeftUp")

    def LeftClick(self) -> None:
        """鼠标左键单击"""
        self._call("LeftClick")

    def RightDown(self) -> None:
        """按下鼠标右键"""
        self._call("RightDown")

    def RightUp(self) -> None:
        """释放鼠标右键"""
        self._call("RightUp")

    def RightClick(self) -> None:
        """鼠标右键单击"""
        self._call("RightClick")

    def MiddleDown(self) -> None:
        """按下鼠标中键"""
        self._call("MiddleDown")

    def MiddleUp(self) -> None:
        """释放鼠标中键"""
        self._call("MiddleUp")

    def MiddleClick(self) -> None:
        """鼠标中键单击"""
        self._call("MiddleClick")

    def DoubleClick(self) -> None:
        """鼠标左键双击"""
        self._call("DoubleClick")

    def MouseWheel(self, delta: int) -> None:
        """滚动鼠标滚轮

        Args:
            delta: 滚动量，正数向上滚动，负数向下滚动
        """
        self._call("MouseWheel", delta)


Mouse = MouseModule()
