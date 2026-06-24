"""MoonBit 类型映射"""

from typing import Optional, Type

# Python 类型到 MoonBit 类型的映射
PY_TO_MOONBIT_TYPE = {
    int: 'Int',
    float: 'Double',
    str: 'String',
    bool: 'Bool',
}

# MoonBit 类型到 Python 类型的映射
MOONBIT_TO_PY_TYPE = {
    'Int': int,
    'Double': float,
    'Float': float,
    'String': str,
    'Bool': bool,
    'Int64': int,
}


def get_moonbit_type(py_type: Optional[Type]) -> str:
    """将 Python 类型转换为 MoonBit 类型"""
    if py_type is None:
        return 'String'
    if py_type is type(None):
        return 'Unit'
    if py_type is int:
        return 'Int'
    if py_type is float:
        return 'Double'
    if py_type is str:
        return 'String'
    if py_type is bool:
        return 'Bool'
    if py_type is bytes:
        return 'Bytes'
    return 'String'


def get_python_type(moonbit_type: str) -> Optional[Type]:
    """将 MoonBit 类型转换为 Python 类型"""
    return MOONBIT_TO_PY_TYPE.get(moonbit_type, str)
