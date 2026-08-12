"""Font 类 - 字体封装"""
from .._core.api import get_libxl_dll, _encode_str, _decode_str, FontHandle


class Font:
    """字体对象

    封装 LibXL 字体操作。
    由 Book.add_font() 创建，不要直接实例化。
    """

    def __init__(self, handle: FontHandle, book):
        self._handle = handle
        self._book = book
        self._dll = get_libxl_dll()

    @property
    def handle(self) -> FontHandle:
        """获取字体句柄"""
        return self._handle

    @property
    def size(self) -> int:
        """字号"""
        return self._dll.xlFontSizeA(self._handle)

    @size.setter
    def size(self, value: int):
        self._dll.xlFontSetSizeA(self._handle, value)

    @property
    def bold(self) -> bool:
        """粗体"""
        return bool(self._dll.xlFontBoldA(self._handle))

    @bold.setter
    def bold(self, value: bool):
        self._dll.xlFontSetBoldA(self._handle, 1 if value else 0)

    @property
    def italic(self) -> bool:
        """斜体"""
        return bool(self._dll.xlFontItalicA(self._handle))

    @italic.setter
    def italic(self, value: bool):
        self._dll.xlFontSetItalicA(self._handle, 1 if value else 0)

    @property
    def strike_out(self) -> bool:
        """删除线"""
        return bool(self._dll.xlFontStrikeOutA(self._handle))

    @strike_out.setter
    def strike_out(self, value: bool):
        self._dll.xlFontSetStrikeOutA(self._handle, 1 if value else 0)

    @property
    def color(self) -> int:
        """字体颜色"""
        return self._dll.xlFontColorA(self._handle)

    @color.setter
    def color(self, value: int):
        self._dll.xlFontSetColorA(self._handle, value)

    @property
    def name(self) -> str:
        """字体名称"""
        result = self._dll.xlFontNameA(self._handle)
        return _decode_str(result) if result else ''

    @name.setter
    def name(self, value: str):
        self._dll.xlFontSetNameA(self._handle, _encode_str(value))

    @property
    def script(self) -> int:
        """上下标 (0=正常, 1=上标, 2=下标)"""
        return self._dll.xlFontScriptA(self._handle)

    @script.setter
    def script(self, value: int):
        self._dll.xlFontSetScriptA(self._handle, value)

    @property
    def underline(self) -> int:
        """下划线类型"""
        return self._dll.xlFontUnderlineA(self._handle)

    @underline.setter
    def underline(self, value: int):
        self._dll.xlFontSetUnderlineA(self._handle, value)

    def __repr__(self):
        return f'Font(name={self.name!r}, size={self.size}, bold={self.bold})'


__all__ = ['Font']
