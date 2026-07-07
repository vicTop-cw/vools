"""vools.data - 数据结构模块

提供轻量级数据结构，与外部库互补。

数据结构:
- Seq/VList: 链式序列
- VText: 文本处理
- Table: 二维表格 (QAX 风格)
"""

from .seq import Seq, NONE, collect
from .vlist import VList
from .vtext import VText
from .table import Table, Row, Column
from .qax import Qax

# 便捷函数
from .table import read_excel, write_excel

__all__ = [
    'Seq', 'NONE', 'collect',
    'VList',
    'VText',
    'Table', 'Row', 'Column',
    'Qax',
    'read_excel',
    'write_excel',
]
