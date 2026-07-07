"""Format 类 - 单元格格式封装"""
from ctypes import c_void_p

from .._core.api import get_libxl_dll, _encode_str, _decode_str, FormatHandle
from .font import Font


class Format:
    """单元格格式对象

    封装 LibXL 格式操作。
    由 Book.add_format() 创建，不要直接实例化。
    """

    def __init__(self, handle: FormatHandle, book):
        self._handle = handle
        self._book = book
        self._dll = get_libxl_dll()

    @property
    def handle(self) -> FormatHandle:
        """获取格式句柄"""
        return self._handle

    @property
    def font(self) -> Font:
        """获取字体"""
        font_handle = self._dll.xlFormatFontA(self._handle)
        return Font(font_handle, self._book)

    @font.setter
    def font(self, value: Font):
        self._dll.xlFormatSetFontA(self._handle, value.handle)

    @property
    def num_format(self) -> int:
        """数字格式"""
        return self._dll.xlFormatNumFormatA(self._handle)

    @num_format.setter
    def num_format(self, value: int):
        self._dll.xlFormatSetNumFormatA(self._handle, value)

    @property
    def align_h(self) -> int:
        """水平对齐方式"""
        return self._dll.xlFormatAlignHA(self._handle)

    @align_h.setter
    def align_h(self, value: int):
        self._dll.xlFormatSetAlignHA(self._handle, value)

    @property
    def align_v(self) -> int:
        """垂直对齐方式"""
        return self._dll.xlFormatAlignVA(self._handle)

    @align_v.setter
    def align_v(self, value: int):
        self._dll.xlFormatSetAlignVA(self._handle, value)

    @property
    def wrap(self) -> bool:
        """自动换行"""
        return bool(self._dll.xlFormatWrapA(self._handle))

    @wrap.setter
    def wrap(self, value: bool):
        self._dll.xlFormatSetWrapA(self._handle, 1 if value else 0)

    @property
    def rotation(self) -> int:
        """文字旋转角度"""
        return self._dll.xlFormatRotationA(self._handle)

    @rotation.setter
    def rotation(self, value: int):
        self._dll.xlFormatSetRotationA(self._handle, value)

    @property
    def indent(self) -> int:
        """缩进"""
        return self._dll.xlFormatIndentA(self._handle)

    @indent.setter
    def indent(self, value: int):
        self._dll.xlFormatSetIndentA(self._handle, value)

    @property
    def shrink_to_fit(self) -> bool:
        """缩小字体填充"""
        return bool(self._dll.xlFormatShrinkToFitA(self._handle))

    @shrink_to_fit.setter
    def shrink_to_fit(self, value: bool):
        self._dll.xlFormatSetShrinkToFitA(self._handle, 1 if value else 0)

    def set_border(self, style: int):
        """设置所有边框样式

        Args:
            style: 边框样式
        """
        self._dll.xlFormatSetBorderA(self._handle, style)

    def set_border_color(self, color: int):
        """设置所有边框颜色

        Args:
            color: 颜色值
        """
        self._dll.xlFormatSetBorderColorA(self._handle, color)

    @property
    def border_left(self) -> int:
        """左边框样式"""
        return self._dll.xlFormatBorderLeftA(self._handle)

    @border_left.setter
    def border_left(self, value: int):
        self._dll.xlFormatSetBorderLeftA(self._handle, value)

    @property
    def border_right(self) -> int:
        """右边框样式"""
        return self._dll.xlFormatBorderRightA(self._handle)

    @border_right.setter
    def border_right(self, value: int):
        self._dll.xlFormatSetBorderRightA(self._handle, value)

    @property
    def border_top(self) -> int:
        """上边框样式"""
        return self._dll.xlFormatBorderTopA(self._handle)

    @border_top.setter
    def border_top(self, value: int):
        self._dll.xlFormatSetBorderTopA(self._handle, value)

    @property
    def border_bottom(self) -> int:
        """下边框样式"""
        return self._dll.xlFormatBorderBottomA(self._handle)

    @border_bottom.setter
    def border_bottom(self, value: int):
        self._dll.xlFormatSetBorderBottomA(self._handle, value)

    @property
    def border_left_color(self) -> int:
        """左边框颜色"""
        return self._dll.xlFormatBorderLeftColorA(self._handle)

    @border_left_color.setter
    def border_left_color(self, value: int):
        self._dll.xlFormatSetBorderLeftColorA(self._handle, value)

    @property
    def border_right_color(self) -> int:
        """右边框颜色"""
        return self._dll.xlFormatBorderRightColorA(self._handle)

    @border_right_color.setter
    def border_right_color(self, value: int):
        self._dll.xlFormatSetBorderRightColorA(self._handle, value)

    @property
    def border_top_color(self) -> int:
        """上边框颜色"""
        return self._dll.xlFormatBorderTopColorA(self._handle)

    @border_top_color.setter
    def border_top_color(self, value: int):
        self._dll.xlFormatSetBorderTopColorA(self._handle, value)

    @property
    def border_bottom_color(self) -> int:
        """下边框颜色"""
        return self._dll.xlFormatBorderBottomColorA(self._handle)

    @border_bottom_color.setter
    def border_bottom_color(self, value: int):
        self._dll.xlFormatSetBorderBottomColorA(self._handle, value)

    @property
    def border_diagonal(self) -> int:
        """对角线类型"""
        return self._dll.xlFormatBorderDiagonalA(self._handle)

    @border_diagonal.setter
    def border_diagonal(self, value: int):
        self._dll.xlFormatSetBorderDiagonalA(self._handle, value)

    @property
    def border_diagonal_style(self) -> int:
        """对角线样式"""
        return self._dll.xlFormatBorderDiagonalStyleA(self._handle)

    @border_diagonal_style.setter
    def border_diagonal_style(self, value: int):
        self._dll.xlFormatSetBorderDiagonalStyleA(self._handle, value)

    @property
    def border_diagonal_color(self) -> int:
        """对角线颜色"""
        return self._dll.xlFormatBorderDiagonalColorA(self._handle)

    @border_diagonal_color.setter
    def border_diagonal_color(self, value: int):
        self._dll.xlFormatSetBorderDiagonalColorA(self._handle, value)

    @property
    def fill_pattern(self) -> int:
        """填充模式"""
        return self._dll.xlFormatFillPatternA(self._handle)

    @fill_pattern.setter
    def fill_pattern(self, value: int):
        self._dll.xlFormatSetFillPatternA(self._handle, value)

    @property
    def pattern_foreground_color(self) -> int:
        """图案前景色"""
        return self._dll.xlFormatPatternForegroundColorA(self._handle)

    @pattern_foreground_color.setter
    def pattern_foreground_color(self, value: int):
        self._dll.xlFormatSetPatternForegroundColorA(self._handle, value)

    @property
    def pattern_background_color(self) -> int:
        """图案背景色"""
        return self._dll.xlFormatPatternBackgroundColorA(self._handle)

    @pattern_background_color.setter
    def pattern_background_color(self, value: int):
        self._dll.xlFormatSetPatternBackgroundColorA(self._handle, value)

    @property
    def locked(self) -> bool:
        """锁定单元格"""
        return bool(self._dll.xlFormatLockedA(self._handle))

    @locked.setter
    def locked(self, value: bool):
        self._dll.xlFormatSetLockedA(self._handle, 1 if value else 0)

    @property
    def hidden(self) -> bool:
        """隐藏公式"""
        return bool(self._dll.xlFormatHiddenA(self._handle))

    @hidden.setter
    def hidden(self, value: bool):
        self._dll.xlFormatSetHiddenA(self._handle, 1 if value else 0)

    def __repr__(self):
        return f'Format(align_h={self.align_h}, align_v={self.align_v})'


__all__ = ['Format']
