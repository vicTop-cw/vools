"""
Keyboard 模块 - 键盘操作

封装 API.Keyboard COM 对象，提供键盘按键模拟、状态查询等功能。
"""

from ._base import APIBridgeError, _BaseModule


class KeyboardModule(_BaseModule):
    """键盘操作模块

    提供键盘按键模拟、按键状态查询、锁键状态查询等功能。
    """

    _prog_id = "API.Keyboard"

    def SendKeys(self, text: str) -> None:
        """发送键盘输入文本

        Args:
            text: 要发送的文本内容
        """
        self._call("SendKeys", text)

    def KeyDown(self, vk_code: int) -> None:
        """按下指定虚拟键

        Args:
            vk_code: 虚拟键码（VK_* 常量）
        """
        self._call("KeyDown", vk_code)

    def KeyUp(self, vk_code: int) -> None:
        """释放指定虚拟键

        Args:
            vk_code: 虚拟键码（VK_* 常量）
        """
        self._call("KeyUp", vk_code)

    def KeyDownUp(self, vk_code: int) -> None:
        """按下并释放指定虚拟键（单次按键）

        Args:
            vk_code: 虚拟键码（VK_* 常量）
        """
        self._call("KeyDownUp", vk_code)

    def GetKeyPressed(self, vk_code: int) -> bool:
        """查询指定按键是否被按下

        Args:
            vk_code: 虚拟键码（VK_* 常量）

        Returns:
            bool: 按键是否被按下
        """
        return self._call_bool("GetKeyPressed", vk_code)

    def GetKeyOpened(self, vk_code: int) -> bool:
        """查询指定锁键是否开启

        Args:
            vk_code: 虚拟键码（VK_CAPITAL, VK_NUMLOCK, VK_SCROLL 等）

        Returns:
            bool: 锁键是否开启
        """
        return self._call_bool("GetKeyOpened", vk_code)

    def AltKeyPressed(self) -> bool:
        """Alt 键是否被按下

        Returns:
            bool: Alt 键是否被按下
        """
        return self._call_bool("AltKeyPressed")

    def CtrlKeyPressed(self) -> bool:
        """Ctrl 键是否被按下

        Returns:
            bool: Ctrl 键是否被按下
        """
        return self._call_bool("CtrlKeyPressed")

    def ShiftKeyPressed(self) -> bool:
        """Shift 键是否被按下

        Returns:
            bool: Shift 键是否被按下
        """
        return self._call_bool("ShiftKeyPressed")

    def CapsLockOpened(self) -> bool:
        """CapsLock 是否开启

        Returns:
            bool: CapsLock 是否开启
        """
        return self._call_bool("CapsLockOpened")

    def NumLockOpened(self) -> bool:
        """NumLock 是否开启

        Returns:
            bool: NumLock 是否开启
        """
        return self._call_bool("NumLockOpened")

    def ScrollLockOpened(self) -> bool:
        """ScrollLock 是否开启

        Returns:
            bool: ScrollLock 是否开启
        """
        return self._call_bool("ScrollLockOpened")


Keyboard = KeyboardModule()
