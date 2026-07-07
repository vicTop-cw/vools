"""工具层"""
from .helpers import (
    rowcol_to_addr,
    addr_to_rowcol,
    rgb_to_color,
    color_to_rgb,
)

try:
    import pandas as _pd
    _pandas_available = True
except ImportError:
    _pd = None
    _pandas_available = False


__all__ = [
    'rowcol_to_addr',
    'addr_to_rowcol',
    'rgb_to_color',
    'color_to_rgb',
    'show_table',
    'sheet_to_2d_list',
    'book_to_sheets_data',
    'dataframe_to_2d_list',
]


def _is_sheet_obj(data):
    try:
        from .._objects.sheet import Sheet
        return isinstance(data, Sheet)
    except Exception:
        return False


def _is_book_obj(data):
    try:
        from .._objects.book import Book
        return isinstance(data, Book)
    except Exception:
        return False


def _is_dataframe(data):
    if not _pandas_available:
        return False
    return isinstance(data, _pd.DataFrame)


def sheet_to_2d_list(sheet, has_header=True):
    first_row = sheet.first_row
    last_row = sheet.last_row
    first_col = sheet.first_col
    last_col = sheet.last_col

    if first_row > last_row or first_col > last_col:
        return []

    rows = last_row - first_row + 1
    cols = last_col - first_col + 1

    try:
        return sheet.read_matrix(rows, cols, first_row, first_col)
    except Exception:
        result = []
        for row in range(first_row, last_row + 1):
            row_data = []
            for col in range(first_col, last_col + 1):
                row_data.append(sheet.read_str(row, col))
            result.append(row_data)
        return result


def book_to_sheets_data(book, sheet_names=None):
    sheets_data = []
    names = []

    count = book.sheet_count
    for i in range(count):
        sheet = book.get_sheet(i)
        name = sheet.name

        if sheet_names is not None and name not in sheet_names:
            continue

        data = sheet_to_2d_list(sheet, has_header=True)
        sheets_data.append(data)
        names.append(name)

    return sheets_data, names


def dataframe_to_2d_list(df, show_index=False):
    if show_index:
        df = df.reset_index()

    headers = list(df.columns)
    data = [headers]

    for _, row in df.iterrows():
        data.append([str(v) if v is not None else '' for v in row.tolist()])

    return data


def _normalize_data(data, has_header=True, show_index=False):
    if _is_book_obj(data):
        sheets_data, sheet_names = book_to_sheets_data(data)
        return {'type': 'book', 'sheets': sheets_data, 'names': sheet_names}

    if _is_sheet_obj(data):
        sheet_data = sheet_to_2d_list(data, has_header=has_header)
        return {'type': 'sheet', 'data': sheet_data, 'name': data.name}

    if _is_dataframe(data):
        df_data = dataframe_to_2d_list(data, show_index=show_index)
        return {'type': 'dataframe', 'data': df_data}

    if isinstance(data, list):
        return {'type': 'list', 'data': data}

    raise TypeError(
        f'Unsupported data type: {type(data).__name__}. '
        f'Supported types: list, Sheet, Book, pandas.DataFrame'
    )


def _format_cell(value):
    if value is None:
        return ''
    return str(value)


def _format_table(data):
    """将二维数据格式化为类似 tabulate 的文本表格。"""
    if not data:
        return ''

    rows = [_format_cell(v) for row in data for v in row]

    num_cols = max(len(row) for row in data) if data else 0
    num_rows = len(data)

    col_widths = [0] * num_cols
    for row in data:
        for i, value in enumerate(row):
            width = len(_format_cell(value))
            if width > col_widths[i]:
                col_widths[i] = width

    lines = []
    for r, row in enumerate(data):
        cells = []
        for c in range(num_cols):
            value = _format_cell(row[c]) if c < len(row) else ''
            cells.append(value.ljust(col_widths[c]))
        lines.append(' | '.join(cells))

    if len(lines) > 1:
        sep = '-+-'.join('-' * w for w in col_widths)
        lines.insert(1, sep)

    return '\n'.join(lines)


def show_table(data, title=None, has_header=True, modal=True, show_index=False):
    """在控制台打印二维表格数据。

    参数：
        data: 二维列表、Sheet、Book 或 pandas.DataFrame
        title: 表格标题
        has_header: 第一行是否作为表头
        modal: 保留参数，当前实现中忽略
        show_index: 是否显示 DataFrame 索引
    """
    normalized = _normalize_data(data, has_header=has_header, show_index=show_index)

    if title is None:
        if normalized['type'] == 'book':
            title = 'Book Viewer'
        elif normalized['type'] == 'sheet':
            title = f"Sheet: {normalized['name']}"
        elif normalized['type'] == 'dataframe':
            title = 'DataFrame Viewer'
        else:
            title = 'Table Viewer'

    output = []
    if title:
        output.append(title)

    if normalized['type'] == 'book':
        for name, sheet_data in zip(normalized['names'], normalized['sheets']):
            output.append(f"\n[{name}]")
            output.append(_format_table(sheet_data))
    else:
        output.append(_format_table(normalized['data']))

    print('\n'.join(output))
