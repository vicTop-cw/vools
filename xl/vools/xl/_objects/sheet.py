"""Sheet 类 - 工作表封装"""
from ctypes import c_int, c_double, c_void_p, byref, POINTER

from .._core.api import get_libxl_dll, _encode_str, _decode_str, SheetHandle, FormatHandle
from .format import Format


class Sheet:
    """工作表对象

    封装 LibXL 工作表操作。
    由 Book.add_sheet() 或 Book.get_sheet() 创建，不要直接实例化。
    """

    def __init__(self, handle: SheetHandle, book):
        self._handle = handle
        self._book = book
        self._dll = get_libxl_dll()

    @property
    def handle(self) -> SheetHandle:
        """获取工作表句柄"""
        return self._handle

    @property
    def book(self):
        """所属工作簿"""
        return self._book

    @property
    def name(self) -> str:
        """工作表名称"""
        result = self._dll.xlSheetNameA(self._handle)
        return _decode_str(result) if result else ''

    @name.setter
    def name(self, value: str):
        self._dll.xlSheetSetNameA(self._handle, _encode_str(value))

    def cell_type(self, row: int, col: int) -> int:
        """获取单元格类型

        Args:
            row: 行号 (从0开始)
            col: 列号 (从0开始)

        Returns:
            单元格类型 (0=空, 1=数字, 2=字符串, 3=布尔, 4=空白, 5=错误)
        """
        return self._dll.xlSheetCellTypeA(self._handle, row, col)

    def is_formula(self, row: int, col: int) -> bool:
        """检查单元格是否为公式

        Args:
            row: 行号 (从0开始)
            col: 列号 (从0开始)

        Returns:
            True-是公式, False-不是公式
        """
        return bool(self._dll.xlSheetIsFormulaA(self._handle, row, col))

    def cell_format(self, row: int, col: int) -> Format:
        """获取单元格格式

        Args:
            row: 行号 (从0开始)
            col: 列号 (从0开始)

        Returns:
            Format 对象
        """
        fmt_handle = self._dll.xlSheetCellFormatA(self._handle, row, col)
        return Format(fmt_handle, self._book)

    def set_cell_format(self, row: int, col: int, fmt: Format):
        """设置单元格格式

        Args:
            row: 行号 (从0开始)
            col: 列号 (从0开始)
            fmt: Format 对象
        """
        self._dll.xlSheetSetCellFormatA(self._handle, row, col, fmt.handle)

    def read_str(self, row: int, col: int) -> str:
        """读取字符串

        Args:
            row: 行号 (从0开始)
            col: 列号 (从0开始)

        Returns:
            字符串值
        """
        fmt_handle = c_void_p()
        result = self._dll.xlSheetReadStrA(self._handle, row, col, byref(fmt_handle))
        return _decode_str(result) if result else ''

    def write_str(self, row: int, col: int, value: str, fmt: Format = None) -> bool:
        """写入字符串

        Args:
            row: 行号 (从0开始)
            col: 列号 (从0开始)
            value: 字符串值
            fmt: 格式对象 (可选)

        Returns:
            True-成功, False-失败
        """
        fmt_handle = fmt.handle if fmt else None
        result = self._dll.xlSheetWriteStrA(
            self._handle, row, col, _encode_str(value), fmt_handle
        )
        return bool(result)

    def read_num(self, row: int, col: int) -> float:
        """读取数字

        Args:
            row: 行号 (从0开始)
            col: 列号 (从0开始)

        Returns:
            数字值
        """
        fmt_handle = c_void_p()
        return self._dll.xlSheetReadNumA(self._handle, row, col, byref(fmt_handle))

    def write_num(self, row: int, col: int, value: float, fmt: Format = None) -> bool:
        """写入数字

        Args:
            row: 行号 (从0开始)
            col: 列号 (从0开始)
            value: 数字值
            fmt: 格式对象 (可选)

        Returns:
            True-成功, False-失败
        """
        fmt_handle = fmt.handle if fmt else None
        result = self._dll.xlSheetWriteNumA(
            self._handle, row, col, value, fmt_handle
        )
        return bool(result)

    def read_bool(self, row: int, col: int) -> bool:
        """读取布尔值

        Args:
            row: 行号 (从0开始)
            col: 列号 (从0开始)

        Returns:
            布尔值
        """
        fmt_handle = c_void_p()
        return bool(self._dll.xlSheetReadBoolA(self._handle, row, col, byref(fmt_handle)))

    def write_bool(self, row: int, col: int, value: bool, fmt: Format = None) -> bool:
        """写入布尔值

        Args:
            row: 行号 (从0开始)
            col: 列号 (从0开始)
            value: 布尔值
            fmt: 格式对象 (可选)

        Returns:
            True-成功, False-失败
        """
        fmt_handle = fmt.handle if fmt else None
        result = self._dll.xlSheetWriteBoolA(
            self._handle, row, col, 1 if value else 0, fmt_handle
        )
        return bool(result)

    def read_blank(self, row: int, col: int) -> bool:
        """读取空白单元格

        Args:
            row: 行号 (从0开始)
            col: 列号 (从0开始)

        Returns:
            True-是空白, False-不是空白
        """
        fmt_handle = c_void_p()
        return bool(self._dll.xlSheetReadBlankA(self._handle, row, col, byref(fmt_handle)))

    def write_blank(self, row: int, col: int, fmt: Format = None) -> bool:
        """写入空白单元格

        Args:
            row: 行号 (从0开始)
            col: 列号 (从0开始)
            fmt: 格式对象 (可选)

        Returns:
            True-成功, False-失败
        """
        fmt_handle = fmt.handle if fmt else None
        result = self._dll.xlSheetWriteBlankA(
            self._handle, row, col, fmt_handle
        )
        return bool(result)

    def read_formula(self, row: int, col: int) -> str:
        """读取公式

        Args:
            row: 行号 (从0开始)
            col: 列号 (从0开始)

        Returns:
            公式字符串
        """
        fmt_handle = c_void_p()
        result = self._dll.xlSheetReadFormulaA(self._handle, row, col, byref(fmt_handle))
        return _decode_str(result) if result else ''

    def write_formula(self, row: int, col: int, expr: str, fmt: Format = None) -> bool:
        """写入公式

        Args:
            row: 行号 (从0开始)
            col: 列号 (从0开始)
            expr: 公式表达式
            fmt: 格式对象 (可选)

        Returns:
            True-成功, False-失败
        """
        fmt_handle = fmt.handle if fmt else None
        result = self._dll.xlSheetWriteFormulaA(
            self._handle, row, col, _encode_str(expr), fmt_handle
        )
        return bool(result)

    def is_date(self, row: int, col: int) -> bool:
        """检查单元格是否为日期

        Args:
            row: 行号 (从0开始)
            col: 列号 (从0开始)

        Returns:
            True-是日期, False-不是日期
        """
        return bool(self._dll.xlSheetIsDateA(self._handle, row, col))

    def read_error(self, row: int, col: int) -> int:
        """读取错误类型

        Args:
            row: 行号 (从0开始)
            col: 列号 (从0开始)

        Returns:
            错误类型
        """
        return self._dll.xlSheetReadErrorA(self._handle, row, col)

    def write_error(self, row: int, col: int, error: int, fmt: Format = None) -> bool:
        """写入错误

        Args:
            row: 行号 (从0开始)
            col: 列号 (从0开始)
            error: 错误类型
            fmt: 格式对象 (可选)

        Returns:
            True-成功, False-失败
        """
        fmt_handle = fmt.handle if fmt else None
        result = self._dll.xlSheetWriteErrorA(
            self._handle, row, col, error, fmt_handle
        )
        return bool(result)

    def read_comment(self, row: int, col: int) -> str:
        """读取批注

        Args:
            row: 行号 (从0开始)
            col: 列号 (从0开始)

        Returns:
            批注文本
        """
        result = self._dll.xlSheetReadCommentA(self._handle, row, col)
        return _decode_str(result) if result else ''

    def write_comment(self, row: int, col: int, value: str, author: str = '',
                      width: int = 200, height: int = 150):
        """写入批注

        Args:
            row: 行号 (从0开始)
            col: 列号 (从0开始)
            value: 批注文本
            author: 作者
            width: 宽度
            height: 高度
        """
        self._dll.xlSheetWriteCommentA(
            self._handle, row, col,
            _encode_str(value), _encode_str(author), width, height
        )

    def remove_comment(self, row: int, col: int):
        """删除批注

        Args:
            row: 行号 (从0开始)
            col: 列号 (从0开始)
        """
        self._dll.xlSheetRemoveCommentA(self._handle, row, col)

    def col_width(self, col: int) -> float:
        """获取列宽

        Args:
            col: 列号 (从0开始)

        Returns:
            列宽
        """
        return self._dll.xlSheetColWidthA(self._handle, col)

    def row_height(self, row: int) -> float:
        """获取行高

        Args:
            row: 行号 (从0开始)

        Returns:
            行高
        """
        return self._dll.xlSheetRowHeightA(self._handle, row)

    def set_col(self, first: int, last: int, width: float,
                fmt: Format = None, hidden: bool = False) -> bool:
        """设置列属性

        Args:
            first: 起始列号 (从0开始)
            last: 结束列号 (从0开始)
            width: 列宽
            fmt: 格式对象 (可选)
            hidden: 是否隐藏

        Returns:
            True-成功, False-失败
        """
        fmt_handle = fmt.handle if fmt else None
        result = self._dll.xlSheetSetColA(
            self._handle, first, last, width, fmt_handle, 1 if hidden else 0
        )
        return bool(result)

    def set_row(self, row: int, height: float,
                fmt: Format = None, hidden: bool = False) -> bool:
        """设置行属性

        Args:
            row: 行号 (从0开始)
            height: 行高
            fmt: 格式对象 (可选)
            hidden: 是否隐藏

        Returns:
            True-成功, False-失败
        """
        fmt_handle = fmt.handle if fmt else None
        result = self._dll.xlSheetSetRowA(
            self._handle, row, height, fmt_handle, 1 if hidden else 0
        )
        return bool(result)

    def row_hidden(self, row: int) -> bool:
        """检查行是否隐藏

        Args:
            row: 行号 (从0开始)

        Returns:
            True-隐藏, False-显示
        """
        return bool(self._dll.xlSheetRowHiddenA(self._handle, row))

    def set_row_hidden(self, row: int, hidden: bool) -> bool:
        """设置行隐藏

        Args:
            row: 行号 (从0开始)
            hidden: 是否隐藏

        Returns:
            True-成功, False-失败
        """
        result = self._dll.xlSheetSetRowHiddenA(
            self._handle, row, 1 if hidden else 0
        )
        return bool(result)

    def col_hidden(self, col: int) -> bool:
        """检查列是否隐藏

        Args:
            col: 列号 (从0开始)

        Returns:
            True-隐藏, False-显示
        """
        return bool(self._dll.xlSheetColHiddenA(self._handle, col))

    def set_col_hidden(self, col: int, hidden: bool) -> bool:
        """设置列隐藏

        Args:
            col: 列号 (从0开始)
            hidden: 是否隐藏

        Returns:
            True-成功, False-失败
        """
        result = self._dll.xlSheetSetColHiddenA(
            self._handle, col, 1 if hidden else 0
        )
        return bool(result)

    def set_merge(self, row_first: int, row_last: int,
                  col_first: int, col_last: int) -> bool:
        """合并单元格

        Args:
            row_first: 起始行号 (从0开始)
            row_last: 结束行号 (从0开始)
            col_first: 起始列号 (从0开始)
            col_last: 结束列号 (从0开始)

        Returns:
            True-成功, False-失败
        """
        result = self._dll.xlSheetSetMergeA(
            self._handle, row_first, row_last, col_first, col_last
        )
        return bool(result)

    def get_merge(self, row: int, col: int):
        """获取合并单元格区域

        Args:
            row: 行号 (从0开始)
            col: 列号 (从0开始)

        Returns:
            (row_first, row_last, col_first, col_last) 元组，或 None
        """
        row_first = c_int()
        row_last = c_int()
        col_first = c_int()
        col_last = c_int()
        result = self._dll.xlSheetGetMergeA(
            self._handle, row, col,
            byref(row_first), byref(row_last),
            byref(col_first), byref(col_last)
        )
        if result:
            return (row_first.value, row_last.value,
                    col_first.value, col_last.value)
        return None

    def merge_size(self) -> int:
        """获取合并单元格数量

        Returns:
            合并单元格数量
        """
        return self._dll.xlSheetMergeSizeA(self._handle)

    def merge_by_index(self, index: int):
        """按索引获取合并单元格

        Args:
            index: 索引

        Returns:
            (row_first, row_last, col_first, col_last) 元组，或 None
        """
        row_first = c_int()
        row_last = c_int()
        col_first = c_int()
        col_last = c_int()
        result = self._dll.xlSheetMergeA(
            self._handle, index,
            byref(row_first), byref(row_last),
            byref(col_first), byref(col_last)
        )
        if result:
            return (row_first.value, row_last.value,
                    col_first.value, col_last.value)
        return None

    def del_merge(self, row: int, col: int) -> bool:
        """删除合并单元格

        Args:
            row: 行号 (从0开始)
            col: 列号 (从0开始)

        Returns:
            True-成功, False-失败
        """
        return bool(self._dll.xlSheetDelMergeA(self._handle, row, col))

    def del_merge_by_index(self, index: int) -> bool:
        """按索引删除合并单元格

        Args:
            index: 索引

        Returns:
            True-成功, False-失败
        """
        return bool(self._dll.xlSheetDelMergeByIndexA(self._handle, index))

    @property
    def first_row(self) -> int:
        """首行索引 (从0开始)"""
        return self._dll.xlSheetFirstRowA(self._handle)

    @property
    def last_row(self) -> int:
        """末行索引 (从0开始)"""
        return self._dll.xlSheetLastRowA(self._handle)

    @property
    def first_col(self) -> int:
        """首列索引 (从0开始)"""
        return self._dll.xlSheetFirstColA(self._handle)

    @property
    def last_col(self) -> int:
        """末列索引 (从0开始)"""
        return self._dll.xlSheetLastColA(self._handle)

    @property
    def hidden(self) -> int:
        """工作表隐藏状态"""
        return self._dll.xlSheetHiddenA(self._handle)

    @hidden.setter
    def hidden(self, value: int):
        self._dll.xlSheetSetHiddenA(self._handle, value)

    def clear(self, row_first: int, row_last: int, col_first: int, col_last: int):
        """清除单元格区域

        Args:
            row_first: 起始行号 (从0开始)
            row_last: 结束行号 (从0开始)
            col_first: 起始列号 (从0开始)
            col_last: 结束列号 (从0开始)
        """
        self._dll.xlSheetClearA(
            self._handle, row_first, row_last, col_first, col_last
        )

    def insert_row(self, first: int, last: int) -> bool:
        """插入行

        Args:
            first: 起始行号 (从0开始)
            last: 结束行号 (从0开始)

        Returns:
            True-成功, False-失败
        """
        return bool(self._dll.xlSheetInsertRowA(self._handle, first, last))

    def insert_col(self, first: int, last: int) -> bool:
        """插入列

        Args:
            first: 起始列号 (从0开始)
            last: 结束列号 (从0开始)

        Returns:
            True-成功, False-失败
        """
        return bool(self._dll.xlSheetInsertColA(self._handle, first, last))

    def remove_row(self, first: int, last: int) -> bool:
        """删除行

        Args:
            first: 起始行号 (从0开始)
            last: 结束行号 (从0开始)

        Returns:
            True-成功, False-失败
        """
        return bool(self._dll.xlSheetRemoveRowA(self._handle, first, last))

    def remove_col(self, first: int, last: int) -> bool:
        """删除列

        Args:
            first: 起始列号 (从0开始)
            last: 结束列号 (从0开始)

        Returns:
            True-成功, False-失败
        """
        return bool(self._dll.xlSheetRemoveColA(self._handle, first, last))

    def copy_cell(self, row_src: int, col_src: int,
                  row_dst: int, col_dst: int) -> bool:
        """复制单元格

        Args:
            row_src: 源行号
            col_src: 源列号
            row_dst: 目标行号
            col_dst: 目标列号

        Returns:
            True-成功, False-失败
        """
        return bool(self._dll.xlSheetCopyCellA(
            self._handle, row_src, col_src, row_dst, col_dst
        ))

    @property
    def display_gridlines(self) -> bool:
        """显示网格线"""
        return bool(self._dll.xlSheetDisplayGridlinesA(self._handle))

    @display_gridlines.setter
    def display_gridlines(self, value: bool):
        self._dll.xlSheetSetDisplayGridlinesA(
            self._handle, 1 if value else 0
        )

    @property
    def print_gridlines(self) -> bool:
        """打印网格线"""
        return bool(self._dll.xlSheetPrintGridlinesA(self._handle))

    @print_gridlines.setter
    def print_gridlines(self, value: bool):
        self._dll.xlSheetSetPrintGridlinesA(
            self._handle, 1 if value else 0
        )

    @property
    def zoom(self) -> int:
        """缩放比例"""
        return self._dll.xlSheetZoomA(self._handle)

    @zoom.setter
    def zoom(self, value: int):
        self._dll.xlSheetSetZoomA(self._handle, value)

    @property
    def landscape(self) -> bool:
        """横向打印"""
        return bool(self._dll.xlSheetLandscapeA(self._handle))

    @landscape.setter
    def landscape(self, value: bool):
        self._dll.xlSheetSetLandscapeA(self._handle, 1 if value else 0)

    @property
    def paper(self) -> int:
        """纸张大小"""
        return self._dll.xlSheetPaperA(self._handle)

    @paper.setter
    def paper(self, value: int):
        self._dll.xlSheetSetPaperA(self._handle, value)

    @property
    def header(self) -> str:
        """页眉"""
        result = self._dll.xlSheetHeaderA(self._handle)
        return _decode_str(result) if result else ''

    @header.setter
    def header(self, value: str):
        self._dll.xlSheetSetHeaderA(self._handle, _encode_str(value))

    @property
    def footer(self) -> str:
        """页脚"""
        result = self._dll.xlSheetFooterA(self._handle)
        return _decode_str(result) if result else ''

    @footer.setter
    def footer(self, value: str):
        self._dll.xlSheetSetFooterA(self._handle, _encode_str(value))

    def picture_size(self) -> int:
        """图片数量"""
        return self._dll.xlSheetPictureSizeA(self._handle)

    # ==================== 批量操作方法 ====================

    def write_matrix(self, data, start_row: int = 1, start_col: int = 0,
                     fmt=None):
        """批量写入二维数据矩阵

        Args:
            data: 二维列表，如 [[a, b, c], [d, e, f], ...]
            start_row: 起始行 (默认1避开trial)
            start_col: 起始列 (默认0)
            fmt: 默认格式对象 (可选)

        Returns:
            True-全部成功

        示例::

            sheet.write_matrix([
                ['Name', 'Age', 'City'],
                ['Alice', 25, 'New York'],
                ['Bob', 30, 'Los Angeles'],
            ])
        """
        fmt_handle = fmt.handle if fmt else None
        dll = self._dll
        handle = self._handle

        for row_idx, row_data in enumerate(data):
            row = start_row + row_idx
            for col_idx, value in enumerate(row_data):
                col = start_col + col_idx
                if value is None:
                    dll.xlSheetWriteBlankA(handle, row, col, fmt_handle)
                elif isinstance(value, bool):
                    dll.xlSheetWriteBoolA(handle, row, col, 1 if value else 0, fmt_handle)
                elif isinstance(value, (int, float)):
                    dll.xlSheetWriteNumA(handle, row, col, float(value), fmt_handle)
                elif isinstance(value, str):
                    if value.startswith('='):
                        dll.xlSheetWriteFormulaA(handle, row, col, _encode_str(value[1:]), fmt_handle)
                    else:
                        dll.xlSheetWriteStrA(handle, row, col, _encode_str(value), fmt_handle)
                else:
                    dll.xlSheetWriteStrA(handle, row, col, _encode_str(str(value)), fmt_handle)
        return True

    def read_matrix(self, rows: int, cols: int,
                   start_row: int = 1, start_col: int = 0):
        """批量读取矩阵数据

        Args:
            rows: 行数
            cols: 列数
            start_row: 起始行 (默认1)
            start_col: 起始列 (默认0)

        Returns:
            二维列表

        示例::

            data = sheet.read_matrix(100, 10)  # 读取100行10列
        """
        dll = self._dll
        handle = self._handle
        result = []

        for row_idx in range(rows):
            row = start_row + row_idx
            row_data = []
            for col_idx in range(cols):
                col = start_col + col_idx
                cell_type = dll.xlSheetCellTypeA(handle, row, col)

                if cell_type == 0:  # EMPTY
                    row_data.append(None)
                elif cell_type == 1:  # NUMBER
                    row_data.append(dll.xlSheetReadNumA(handle, row, col, None))
                elif cell_type == 2:  # STRING
                    val = dll.xlSheetReadStrA(handle, row, col, None)
                    row_data.append(_decode_str(val) if val else '')
                elif cell_type == 3:  # BOOLEAN
                    row_data.append(bool(dll.xlSheetReadBoolA(handle, row, col, None)))
                elif cell_type == 4:  # BLANK
                    row_data.append(None)
                else:
                    row_data.append(None)
            result.append(row_data)

        return result

    def read_range(self, row_first: int, row_last: int,
                   col_first: int, col_last: int):
        """按范围批量读取

        Args:
            row_first: 起始行 (从0开始)
            row_last: 结束行 (从0开始)
            col_first: 起始列 (从0开始)
            col_last: 结束列 (从0开始)

        Returns:
            二维列表

        示例::

            data = sheet.read_range(1, 100, 0, 9)  # 1-100行, 0-9列
        """
        rows = row_last - row_first + 1
        cols = col_last - col_first + 1
        return self.read_matrix(rows, cols, row_first, col_first)

    def show(self, title=None, has_header=True, modal=True):
        """在控制台显示当前工作表

        Args:
            title: 表格标题 (默认使用工作表名称)
            has_header: 是否将首行作为表头
            modal: 保留参数，当前实现中忽略
        """
        from .._utils import show_table
        show_table(self, title=title, has_header=has_header, modal=modal)

    def __repr__(self):
        return f'Sheet(name={self.name!r})'


__all__ = ['Sheet']
