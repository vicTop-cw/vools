"""工具函数"""
from ctypes import c_int, byref


def _check_result(result, book):
    """检查函数返回值，失败则抛出异常

    Args:
        result: 函数返回值 (0=失败, 非0=成功)
        book: Book 对象，用于获取错误信息

    Returns:
        result 值

    Raises:
        RuntimeError: 操作失败时抛出
    """
    if result == 0:
        error_msg = book.error_message if book else 'Unknown error'
        raise RuntimeError(f'LibXL error: {error_msg}')
    return result


def rowcol_to_addr(row, col, absolute=False):
    """行列索引转换为 Excel 地址格式

    Args:
        row: 行号 (从0开始)
        col: 列号 (从0开始)
        absolute: 是否使用绝对引用 ($A$1 格式)

    Returns:
        Excel 地址字符串，如 "A1" 或 "$A$1"
    """
    col_str = ''
    col += 1
    while col > 0:
        col -= 1
        col_str = chr(65 + (col % 26)) + col_str
        col //= 26
    row_str = str(row + 1)
    if absolute:
        return f'${col_str}${row_str}'
    return f'{col_str}{row_str}'


def addr_to_rowcol(addr):
    """Excel 地址转换为行列索引

    Args:
        addr: Excel 地址字符串，如 "A1" 或 "$A$1"

    Returns:
        (row, col) 元组 (从0开始)
    """
    addr = addr.replace('$', '').upper()
    col_str = ''
    row_str = ''
    for c in addr:
        if c.isalpha():
            col_str += c
        else:
            row_str += c
    col = 0
    for c in col_str:
        col = col * 26 + (ord(c) - 64)
    col -= 1
    row = int(row_str) - 1
    return row, col


def rgb_to_color(red, green, blue):
    """RGB 颜色值转换为 LibXL 颜色值

    Args:
        red: 红色分量 (0-255)
        green: 绿色分量 (0-255)
        blue: 蓝色分量 (0-255)

    Returns:
        LibXL 颜色值
    """
    return (red & 0xFF) | ((green & 0xFF) << 8) | ((blue & 0xFF) << 16)


def color_to_rgb(color):
    """LibXL 颜色值转换为 RGB

    Args:
        color: LibXL 颜色值

    Returns:
        (red, green, blue) 元组
    """
    red = color & 0xFF
    green = (color >> 8) & 0xFF
    blue = (color >> 16) & 0xFF
    return red, green, blue


__all__ = [
    '_check_result',
    'rowcol_to_addr',
    'addr_to_rowcol',
    'rgb_to_color',
    'color_to_rgb',
]
