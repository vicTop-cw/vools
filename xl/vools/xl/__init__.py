"""
vools.xl - Excel 读写库

基于 LibXL 的 Excel 文件读写库，支持 .xls 和 .xlsx 格式。

用法::

    from vools.xl import Book, Sheet, Format, Font
    from vools.xl import read_excel, write_excel
    from vools.xl import read_excel_df, write_excel_df, get_engine, register_engine

    # 方式1: 对象方式
    with Book() as book:
        sheet = book.add_sheet("Sheet1")
        sheet.write_str(0, 0, "Hello")
        book.save("output.xlsx")

    # 方式2: 便捷函数
    data = read_excel("input.xlsx")
    write_excel("output.xlsx", data)

    # 方式3: pandas DataFrame (默认 vools 引擎)
    df = read_excel_df("input.xlsx")
    write_excel_df("output.xlsx", df, engine="openpyxl")
"""

from ._objects import Book, Sheet, Format, Font
from ._highlevel import (
    read_excel,
    write_excel,
    read_excel_rows,
    write_excel_rows,
    read_excel_matrix,
    write_excel_matrix,
)

# 表格查看器（控制台文本版）
from ._utils import (
    show_table,
    sheet_to_2d_list,
    book_to_sheets_data,
    dataframe_to_2d_list,
)

# 引擎适配层
from ._highlevel.engines import (
    BaseEngine,
    VoolsEngine,
    PandasEngine,
    register_engine,
    get_engine,
    list_engines,
)

# pandas 接口（可选）
try:
    from ._highlevel import (
        read_excel_df,
        write_excel_df,
    )
    _pandas_available = True
except ImportError:
    _pandas_available = False

from ._utils import rowcol_to_addr, addr_to_rowcol, rgb_to_color, color_to_rgb

__all__ = [
    # 核心类
    'Book',
    'Sheet',
    'Format',
    'Font',
    # 便捷函数
    'read_excel',
    'write_excel',
    'read_excel_rows',
    'write_excel_rows',
    'read_excel_matrix',
    'write_excel_matrix',
    # 表格查看器
    'show_table',
    'sheet_to_2d_list',
    'book_to_sheets_data',
    'dataframe_to_2d_list',
    # 工具函数
    'rowcol_to_addr',
    'addr_to_rowcol',
    'rgb_to_color',
    'color_to_rgb',
    # 引擎适配层
    'BaseEngine',
    'VoolsEngine',
    'PandasEngine',
    'register_engine',
    'get_engine',
    'list_engines',
]

# pandas 接口
if _pandas_available:
    __all__.extend(['read_excel_df', 'write_excel_df'])
