"""
Image 模块 - 图像处理与截图

封装 API.Image COM 对象，提供屏幕截图、图像操作、像素颜色等功能。
"""

from typing import Any, Optional

from ._base import APIBridgeError, _BaseModule


class ImageModule(_BaseModule):
    """图像处理模块

    提供屏幕截图、图像加载/保存、像素操作、图像变换等功能。
    """

    _prog_id = "API.Image"

    def ScreenCapture(self, left: int, top: int, right: int, bottom: int) -> Any:
        """截取指定区域的屏幕

        Args:
            left: 区域左边界 X 坐标
            top: 区域上边界 Y 坐标
            right: 区域右边界 X 坐标
            bottom: 区域下边界 Y 坐标

        Returns:
            图像对象（COM 对象）
        """
        return self._call("ScreenCapture", left, top, right, bottom)

    def CaptureFullScreen(self) -> Any:
        """截取整个屏幕

        自动获取屏幕尺寸并进行全屏截图。

        Returns:
            图像对象（COM 对象）
        """
        width, height = self._get_screen_size()
        return self.ScreenCapture(0, 0, width, height)

    def OpenImage(self, file_path: str) -> Any:
        """从文件加载图像

        Args:
            file_path: 图像文件路径

        Returns:
            图像对象（COM 对象）
        """
        return self._call("OpenImage", file_path)

    def SaveImage(self, image: Any, file_path: str) -> bool:
        """保存图像到文件

        Args:
            image: 图像对象
            file_path: 保存文件路径

        Returns:
            bool: 是否保存成功
        """
        return self._call_bool("SaveImage", image, file_path)

    def GetPixelColor(self, x: int, y: int) -> int:
        """获取指定屏幕坐标的像素颜色

        Args:
            x: X 坐标
            y: Y 坐标

        Returns:
            int: COLORREF 颜色值 (0x00BBGGRR)
        """
        return self._call_int("GetPixelColor", x, y)

    def SetPixelColor(self, x: int, y: int, color: int) -> bool:
        """设置指定屏幕坐标的像素颜色

        Args:
            x: X 坐标
            y: Y 坐标
            color: COLORREF 颜色值 (0x00BBGGRR)

        Returns:
            bool: 是否设置成功
        """
        return self._call_bool("SetPixelColor", x, y, color)

    def ChangeSize(self, image: Any, width: int, height: int) -> Any:
        """调整图像大小

        Args:
            image: 图像对象
            width: 新的宽度
            height: 新的高度

        Returns:
            调整大小后的图像对象
        """
        return self._call("ChangeSize", image, width, height)

    def CropImage(self, image: Any, x: int, y: int, w: int, h: int) -> Any:
        """裁剪图像

        Args:
            image: 图像对象
            x: 裁剪区域左上角 X 坐标
            y: 裁剪区域左上角 Y 坐标
            w: 裁剪宽度
            h: 裁剪高度

        Returns:
            裁剪后的图像对象
        """
        return self._call("CropImage", image, x, y, w, h)

    def RotateFlip(self, image: Any, rotate_type: int) -> Any:
        """旋转或翻转图像

        Args:
            image: 图像对象
            rotate_type: 旋转/翻转类型（RotateFlipType 枚举值）

        Returns:
            旋转/翻转后的图像对象
        """
        return self._call("RotateFlip", image, rotate_type)

    def CreateNewBitmap(self, width: int, height: int) -> Any:
        """创建新的空白位图

        Args:
            width: 位图宽度
            height: 位图高度

        Returns:
            新的位图对象
        """
        return self._call("CreateNewBitmap", width, height)


Image = ImageModule()
