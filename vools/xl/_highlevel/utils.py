"""便捷函数 - 快速读写 Excel"""
import os
from typing import List, Dict, Any, Optional, Union

from .._objects import Book, Sheet, Format, Font


def read_excel(filename: str, sheet_index: int = 0,
               header: bool = True,
               start_row: Optional[int] = None,
               end_row: Optional[int] = None,
               start_col: Optional[int] = None,
               end_col: Optional[int] = None,
               skip_empty: bool = True) -> List[Dict[str, Any]]:
    """读取 Excel 文件为字典列表

    Args:
        filename: Excel 文件路径
        sheet_index: 工作表索引 (从0开始)
        header: 是否将首行作为表头
        start_row: 起始行 (从0开始，默认自动检测)
        end_row: 结束行 (从0开始，默认自动检测)
        start_col: 起始列 (从0开始，默认自动检测)
        end_col: 结束列 (从0开始，默认自动检测)
        skip_empty: 是否跳过全空行

    Returns:
        字典列表，每个字典代表一行数据
    """
    if not os.path.exists(filename):
        raise FileNotFoundError(f'File not found: {filename}')

    with Book() as book:
        if not book.load(filename):
            raise RuntimeError(f'Failed to load: {book.error_message}')

        sheet = book.get_sheet(sheet_index)

        first_row = start_row if start_row is not None else sheet.first_row
        last_row = end_row if end_row is not None else sheet.last_row
        first_col = start_col if start_col is not None else sheet.first_col
        last_col = end_col if end_col is not None else sheet.last_col

        if first_row > last_row or first_col > last_col:
            return []

        # 自动检测有效起始行（跳过前面的空行）
        if start_row is None:
            for row in range(first_row, last_row + 1):
                has_value = False
                for col in range(first_col, min(first_col + 100, last_col + 1)):
                    val = _read_cell(sheet, row, col)
                    if val is not None and val != '':
                        has_value = True
                        break
                if has_value:
                    first_row = row
                    break

        # 自动检测有效列数（从表头行扫描）
        if header and end_col is None:
            header_row = first_row
            detected_last_col = first_col
            for col in range(first_col, min(first_col + 100, last_col + 1)):
                val = _read_cell(sheet, header_row, col)
                if val is not None and val != '':
                    detected_last_col = col
            last_col = detected_last_col

        if header:
            headers = []
            for col in range(first_col, last_col + 1):
                val = _read_cell(sheet, first_row, col)
                headers.append(str(val) if val is not None else f'col_{col}')
            data_start_row = first_row + 1
        else:
            headers = [f'col_{i}' for i in range(last_col - first_col + 1)]
            data_start_row = first_row

        result = []
        for row in range(data_start_row, last_row + 1):
            row_data = {}
            has_value = False
            for i, col in enumerate(range(first_col, last_col + 1)):
                val = _read_cell(sheet, row, col)
                row_data[headers[i]] = val
                if val is not None and val != '':
                    has_value = True
            if not skip_empty or has_value:
                result.append(row_data)

        return result


def write_excel(filename: str, data: List[Dict[str, Any]],
                sheet_name: str = 'Sheet1',
                header: bool = True,
                fmt_header: bool = True) -> bool:
    """将字典列表写入 Excel 文件

    Args:
        filename: Excel 文件路径
        data: 字典列表，每个字典代表一行数据
        sheet_name: 工作表名称
        header: 是否写入表头
        fmt_header: 是否格式化表头（粗体+居中）

    Returns:
        True-成功, False-失败
    """
    if not data:
        raise ValueError('data is empty')

    headers = list(data[0].keys())

    with Book() as book:
        sheet = book.add_sheet(sheet_name)

        header_fmt = None
        if header and fmt_header:
            header_fmt = book.add_format()
            header_fmt.bold = True
            header_fmt.align_h = 2  # 居中

        row = 1  # 避开 trial 版本的 A1

        if header:
            for col, h in enumerate(headers):
                sheet.write_str(row, col, str(h), header_fmt)
            row += 1

        for item in data:
            for col, h in enumerate(headers):
                val = item.get(h)
                _write_cell(sheet, row, col, val)
            row += 1

        return book.save(filename)


def read_excel_rows(filename: str, sheet_index: int = 0,
                    start_row: Optional[int] = None,
                    end_row: Optional[int] = None,
                    start_col: Optional[int] = None,
                    end_col: Optional[int] = None,
                    skip_empty: bool = True) -> List[List[Any]]:
    """读取 Excel 文件为二维列表

    Args:
        filename: Excel 文件路径
        sheet_index: 工作表索引 (从0开始)
        start_row: 起始行 (从0开始，默认自动检测)
        end_row: 结束行 (从0开始，默认自动检测)
        start_col: 起始列 (从0开始，默认自动检测)
        end_col: 结束列 (从0开始，默认自动检测)
        skip_empty: 是否跳过全空行

    Returns:
        二维列表
    """
    if not os.path.exists(filename):
        raise FileNotFoundError(f'File not found: {filename}')

    with Book() as book:
        if not book.load(filename):
            raise RuntimeError(f'Failed to load: {book.error_message}')

        sheet = book.get_sheet(sheet_index)

        first_row = start_row if start_row is not None else sheet.first_row
        last_row = end_row if end_row is not None else sheet.last_row
        first_col = start_col if start_col is not None else sheet.first_col
        last_col = end_col if end_col is not None else sheet.last_col

        if first_row > last_row or first_col > last_col:
            return []

        result = []
        for row in range(first_row, last_row + 1):
            row_data = []
            has_value = False
            for col in range(first_col, last_col + 1):
                val = _read_cell(sheet, row, col)
                row_data.append(val)
                if val is not None and val != '':
                    has_value = True
            if not skip_empty or has_value:
                result.append(row_data)

        return result


def write_excel_rows(filename: str, data: List[List[Any]],
                     sheet_name: str = 'Sheet1') -> bool:
    """将二维列表写入 Excel 文件

    Args:
        filename: Excel 文件路径
        data: 二维列表
        sheet_name: 工作表名称

    Returns:
        True-成功, False-失败
    """
    if not data:
        raise ValueError('data is empty')

    with Book() as book:
        sheet = book.add_sheet(sheet_name)

        for row_idx, row_data in enumerate(data):
            for col_idx, val in enumerate(row_data):
                _write_cell(sheet, row_idx + 1, col_idx, val)

        return book.save(filename)


def _read_cell(sheet: Sheet, row: int, col: int) -> Any:
    """读取单元格值，自动判断类型"""
    from .._core.api import (
        CELLTYPE_EMPTY, CELLTYPE_NUMBER, CELLTYPE_STRING,
        CELLTYPE_BOOLEAN, CELLTYPE_BLANK, CELLTYPE_ERROR
    )

    cell_type = sheet.cell_type(row, col)

    if cell_type == CELLTYPE_EMPTY:
        return None
    elif cell_type == CELLTYPE_STRING:
        return sheet.read_str(row, col)
    elif cell_type == CELLTYPE_NUMBER:
        return sheet.read_num(row, col)
    elif cell_type == CELLTYPE_BOOLEAN:
        return sheet.read_bool(row, col)
    elif cell_type == CELLTYPE_BLANK:
        return ''
    elif cell_type == CELLTYPE_ERROR:
        return sheet.read_error(row, col)
    else:
        return None


def _write_cell(sheet: Sheet, row: int, col: int, value: Any,
                fmt: Format = None) -> bool:
    """写入单元格值，自动判断类型"""
    if value is None:
        return sheet.write_blank(row, col, fmt)
    elif isinstance(value, bool):
        return sheet.write_bool(row, col, value, fmt)
    elif isinstance(value, (int, float)):
        return sheet.write_num(row, col, float(value), fmt)
    elif isinstance(value, str):
        if value.startswith('='):
            return sheet.write_formula(row, col, value[1:], fmt)
        return sheet.write_str(row, col, value, fmt)
    else:
        return sheet.write_str(row, col, str(value), fmt)


__all__ = [
    'read_excel',
    'write_excel',
    'read_excel_rows',
    'write_excel_rows',
    'read_excel_matrix',
    'write_excel_matrix',
]


def read_excel_matrix(filename: str, sheet_index: int = 0,
                      rows: int = None, cols: int = None,
                      start_row: int = 1, start_col: int = 0) -> List[List]:
    """读取 Excel 为二维矩阵

    Args:
        filename: Excel 文件路径
        sheet_index: 工作表索引 (从0开始)
        rows: 要读取的行数 (默认全部)
        cols: 要读取的列数 (默认全部)
        start_row: 起始行 (默认1避开trial)
        start_col: 起始列 (默认0)

    Returns:
        二维列表

    示例::

        matrix = read_excel_matrix('data.xlsx', rows=1000, cols=10)
        for row in matrix:
            print(row[0], row[1])
    """
    if not os.path.exists(filename):
        raise FileNotFoundError(f'File not found: {filename}')

    with Book() as book:
        if not book.load(filename):
            raise RuntimeError(f'Failed to load: {book.error_message}')

        sheet = book.get_sheet(sheet_index)

        # 自动检测行列数
        if rows is None:
            rows = sheet.last_row - start_row + 1
        if cols is None:
            cols = sheet.last_col - start_col + 1

        if rows <= 0 or cols <= 0:
            return []

        return sheet.read_matrix(rows, cols, start_row, start_col)


def write_excel_matrix(filename: str, data: List[List],
                       sheet_name: str = 'Sheet1',
                       start_row: int = 1,
                       start_col: int = 0) -> bool:
    """将二维矩阵写入 Excel

    Args:
        filename: Excel 文件路径
        data: 二维列表，如 [[a, b, c], [d, e, f], ...]
        sheet_name: 工作表名称
        start_row: 起始行 (默认1避开trial)
        start_col: 起始列 (默认0)

    Returns:
        True-成功

    示例::

        data = [
            ['Name', 'Age', 'City'],
            ['Alice', 25, 'New York'],
            ['Bob', 30, 'Los Angeles'],
        ]
        write_excel_matrix('output.xlsx', data)
    """
    if not data:
        raise ValueError('data is empty')

    with Book() as book:
        sheet = book.add_sheet(sheet_name)
        sheet.write_matrix(data, start_row=start_row, start_col=start_col)
        return book.save(filename)
