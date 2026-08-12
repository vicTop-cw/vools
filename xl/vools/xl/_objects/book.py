"""Book 类 - 工作簿封装"""
from ctypes import c_int, c_uint, c_double, c_char_p, c_void_p, byref, POINTER

from .._core.api import get_libxl_dll, _encode_str, _decode_str, BookHandle
from .sheet import Sheet
from .format import Format
from .font import Font


class Book:
    """工作簿对象

    封装 LibXL 工作簿操作。

    示例::

        from vools.xl import Book

        with Book() as book:
            sheet = book.add_sheet("Sheet1")
            sheet.write_str(0, 0, "Hello")
            book.save("output.xls")
    """

    def __init__(self, xml_format: bool = True):
        """创建工作簿

        Args:
            xml_format: True=创建 xlsx 格式, False=创建 xls 格式（默认 xlsx）
        """
        self._dll = get_libxl_dll()
        if xml_format:
            self._handle = self._dll.xlCreateXMLBookCA()
        else:
            self._handle = self._dll.xlCreateBookCA()

        # 自动注册 LibXL，解除 trial 版本限制
        self._dll.xlBookSetKeyA(
            self._handle,
            _encode_str('vic'),
            _encode_str('windows-26252f000ac1ef056ab26e64aexdg1zb')
        )

        self._sheets = []
        self._formats = []
        self._fonts = []
        self._released = False

    @property
    def handle(self) -> BookHandle:
        """获取工作簿句柄"""
        return self._handle

    @property
    def error_message(self) -> str:
        """获取错误信息"""
        result = self._dll.xlBookErrorMessageA(self._handle)
        return _decode_str(result) if result else ''

    def load(self, filename: str) -> bool:
        """加载 Excel 文件

        Args:
            filename: 文件路径

        Returns:
            True-成功, False-失败
        """
        result = self._dll.xlBookLoadA(self._handle, _encode_str(filename))
        return bool(result)

    def save(self, filename: str) -> bool:
        """保存 Excel 文件

        Args:
            filename: 文件路径

        Returns:
            True-成功, False-失败
        """
        result = self._dll.xlBookSaveA(self._handle, _encode_str(filename))
        return bool(result)

    def release(self):
        """释放工作簿资源"""
        if not self._released and self._handle:
            self._dll.xlBookReleaseA(self._handle)
            self._handle = None
            self._released = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False

    def add_sheet(self, name: str, init_sheet: Sheet = None) -> Sheet:
        """添加工作表

        Args:
            name: 工作表名称
            init_sheet: 初始化用的工作表 (可选)

        Returns:
            Sheet 对象
        """
        init_handle = init_sheet.handle if init_sheet else None
        sheet_handle = self._dll.xlBookAddSheetA(
            self._handle, _encode_str(name), init_handle
        )
        sheet = Sheet(sheet_handle, self)
        self._sheets.append(sheet)
        return sheet

    def insert_sheet(self, index: int, name: str,
                     init_sheet: Sheet = None) -> Sheet:
        """插入工作表

        Args:
            index: 插入位置 (从0开始)
            name: 工作表名称
            init_sheet: 初始化用的工作表 (可选)

        Returns:
            Sheet 对象
        """
        init_handle = init_sheet.handle if init_sheet else None
        sheet_handle = self._dll.xlBookInsertSheetA(
            self._handle, index, _encode_str(name), init_handle
        )
        sheet = Sheet(sheet_handle, self)
        self._sheets.insert(index, sheet)
        return sheet

    def get_sheet(self, index: int) -> Sheet:
        """获取工作表

        Args:
            index: 工作表索引 (从0开始)

        Returns:
            Sheet 对象
        """
        sheet_handle = self._dll.xlBookGetSheetA(self._handle, index)
        return Sheet(sheet_handle, self)

    def sheet_type(self, index: int) -> int:
        """获取工作表类型

        Args:
            index: 工作表索引 (从0开始)

        Returns:
            工作表类型 (0=工作表, 1=图表, 2=未知)
        """
        return self._dll.xlBookSheetTypeA(self._handle, index)

    @property
    def sheet_count(self) -> int:
        """工作表数量"""
        return self._dll.xlBookSheetCountA(self._handle)

    def del_sheet(self, index: int) -> bool:
        """删除工作表

        Args:
            index: 工作表索引 (从0开始)

        Returns:
            True-成功, False-失败
        """
        return bool(self._dll.xlBookDelSheetA(self._handle, index))

    def move_sheet(self, src_index: int, dst_index: int) -> bool:
        """移动工作表

        Args:
            src_index: 源索引
            dst_index: 目标索引

        Returns:
            True-成功, False-失败
        """
        return bool(self._dll.xlBookMoveSheetA(self._handle, src_index, dst_index))

    @property
    def active_sheet(self) -> int:
        """活动工作表索引"""
        return self._dll.xlBookActiveSheetA(self._handle)

    @active_sheet.setter
    def active_sheet(self, value: int):
        self._dll.xlBookSetActiveSheetA(self._handle, value)

    def add_format(self, init_format: Format = None) -> Format:
        """添加格式

        Args:
            init_format: 初始化用的格式 (可选)

        Returns:
            Format 对象
        """
        init_handle = init_format.handle if init_format else None
        fmt_handle = self._dll.xlBookAddFormatA(self._handle, init_handle)
        fmt = Format(fmt_handle, self)
        self._formats.append(fmt)
        return fmt

    def add_font(self, init_font: Font = None) -> Font:
        """添加字体

        Args:
            init_font: 初始化用的字体 (可选)

        Returns:
            Font 对象
        """
        init_handle = init_font.handle if init_font else None
        font_handle = self._dll.xlBookAddFontA(self._handle, init_handle)
        font = Font(font_handle, self)
        self._fonts.append(font)
        return font

    def add_custom_num_format(self, custom_num_format: str) -> int:
        """添加自定义数字格式

        Args:
            custom_num_format: 自定义格式字符串

        Returns:
            格式索引
        """
        return self._dll.xlBookAddCustomNumFormatA(
            self._handle, _encode_str(custom_num_format)
        )

    def custom_num_format(self, fmt: int) -> str:
        """获取自定义数字格式

        Args:
            fmt: 格式索引

        Returns:
            格式字符串
        """
        result = self._dll.xlBookCustomNumFormatA(self._handle, fmt)
        return _decode_str(result) if result else ''

    def format(self, index: int) -> Format:
        """获取格式

        Args:
            index: 格式索引

        Returns:
            Format 对象
        """
        fmt_handle = self._dll.xlBookFormatA(self._handle, index)
        return Format(fmt_handle, self)

    @property
    def format_size(self) -> int:
        """格式数量"""
        return self._dll.xlBookFormatSizeA(self._handle)

    def font(self, index: int) -> Font:
        """获取字体

        Args:
            index: 字体索引

        Returns:
            Font 对象
        """
        font_handle = self._dll.xlBookFontA(self._handle, index)
        return Font(font_handle, self)

    @property
    def font_size(self) -> int:
        """字体数量"""
        return self._dll.xlBookFontSizeA(self._handle)

    def default_font(self):
        """获取默认字体

        Returns:
            (font_name, font_size) 元组
        """
        font_size = c_int()
        result = self._dll.xlBookDefaultFontA(self._handle, byref(font_size))
        return (_decode_str(result) if result else '', font_size.value)

    def set_default_font(self, font_name: str, font_size: int):
        """设置默认字体

        Args:
            font_name: 字体名称
            font_size: 字号
        """
        self._dll.xlBookSetDefaultFontA(
            self._handle, _encode_str(font_name), font_size
        )

    def set_key(self, name: str, key: str):
        """设置注册码

        Args:
            name: 注册名
            key: 注册码
        """
        self._dll.xlBookSetKeyA(self._handle, _encode_str(name), _encode_str(key))

    @property
    def version(self) -> int:
        """版本号"""
        return self._dll.xlBookVersionA(self._handle)

    @property
    def biff_version(self) -> int:
        """BIFF 版本"""
        return self._dll.xlBookBiffVersionA(self._handle)

    @property
    def is_date_1904(self) -> bool:
        """是否使用 1904 日期系统"""
        return bool(self._dll.xlBookIsDate1904A(self._handle))

    @is_date_1904.setter
    def is_date_1904(self, value: bool):
        self._dll.xlBookSetDate1904A(self._handle, 1 if value else 0)

    @property
    def is_template(self) -> bool:
        """是否为模板"""
        return bool(self._dll.xlBookIsTemplateA(self._handle))

    @is_template.setter
    def is_template(self, value: bool):
        self._dll.xlBookSetTemplateA(self._handle, 1 if value else 0)

    @property
    def ref_r1c1(self) -> bool:
        """是否使用 R1C1 引用样式"""
        return bool(self._dll.xlBookRefR1C1A(self._handle))

    @ref_r1c1.setter
    def ref_r1c1(self, value: bool):
        self._dll.xlBookSetRefR1C1A(self._handle, 1 if value else 0)

    @property
    def rgb_mode(self) -> bool:
        """是否使用 RGB 颜色模式"""
        return bool(self._dll.xlBookRgbModeA(self._handle))

    @rgb_mode.setter
    def rgb_mode(self, value: bool):
        self._dll.xlBookSetRgbModeA(self._handle, 1 if value else 0)

    def set_locale(self, locale: str) -> bool:
        """设置区域设置

        Args:
            locale: 区域设置字符串

        Returns:
            True-成功, False-失败
        """
        return bool(self._dll.xlBookSetLocaleA(self._handle, _encode_str(locale)))

    def date_pack(self, year: int, month: int, day: int,
                  hour: int = 0, minute: int = 0,
                  second: int = 0, msec: int = 0) -> float:
        """日期打包为 Excel 日期值

        Args:
            year: 年
            month: 月
            day: 日
            hour: 时
            minute: 分
            second: 秒
            msec: 毫秒

        Returns:
            Excel 日期值
        """
        return self._dll.xlBookDatePackA(
            self._handle, year, month, day, hour, minute, second, msec
        )

    def date_unpack(self, value: float):
        """Excel 日期值解包

        Args:
            value: Excel 日期值

        Returns:
            (year, month, day, hour, minute, second, msec) 元组
        """
        year = c_int()
        month = c_int()
        day = c_int()
        hour = c_int()
        minute = c_int()
        second = c_int()
        msec = c_int()
        self._dll.xlBookDateUnpackA(
            self._handle, value,
            byref(year), byref(month), byref(day),
            byref(hour), byref(minute), byref(second), byref(msec)
        )
        return (year.value, month.value, day.value,
                hour.value, minute.value, second.value, msec.value)

    def color_pack(self, red: int, green: int, blue: int) -> int:
        """RGB 颜色打包

        Args:
            red: 红色分量 (0-255)
            green: 绿色分量 (0-255)
            blue: 蓝色分量 (0-255)

        Returns:
            LibXL 颜色值
        """
        return self._dll.xlBookColorPackA(self._handle, red, green, blue)

    def color_unpack(self, color: int):
        """LibXL 颜色值解包

        Args:
            color: LibXL 颜色值

        Returns:
            (red, green, blue) 元组
        """
        red = c_int()
        green = c_int()
        blue = c_int()
        self._dll.xlBookColorUnpackA(
            self._handle, color, byref(red), byref(green), byref(blue)
        )
        return (red.value, green.value, blue.value)

    def picture_size(self) -> int:
        """图片数量"""
        return self._dll.xlBookPictureSizeA(self._handle)

    def add_picture(self, filename: str) -> int:
        """添加图片

        Args:
            filename: 图片文件路径

        Returns:
            图片索引
        """
        return self._dll.xlBookAddPictureA(self._handle, _encode_str(filename))

    def show(self, title=None, has_header=True, modal=True, sheet_names=None):
        """在控制台显示所有工作表

        Args:
            title: 表格标题 (默认 "Book Viewer")
            has_header: 是否将首行作为表头
            modal: 保留参数，当前实现中忽略
            sheet_names: 要显示的工作表名称列表，None 表示显示全部
        """
        from .._utils import show_table
        show_table(self, title=title, has_header=has_header, modal=modal)

    def __del__(self):
        self.release()

    def __repr__(self):
        if self._released:
            return 'Book(released)'
        return f'Book(sheets={self.sheet_count})'


__all__ = ['Book']
