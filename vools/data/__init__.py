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
from .itor import Itor,Node,ItorState, use_nim, get_itor
from .validator import (
    is_email, is_mobile, is_id_card_15, is_id_card_18,
    is_plate_number, is_url, is_username, is_password,
    is_chinese_name, is_phone_with_area, is_phone_without_area,
    is_all_chinese, contains_chinese, starts_with, ends_with,
)

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
    'Itor','Node','ItorState',
    'use_nim', 'get_itor',
    'is_email', 'is_mobile', 'is_id_card_15', 'is_id_card_18',
    'is_plate_number', 'is_url', 'is_username', 'is_password',
    'is_chinese_name', 'is_phone_with_area', 'is_phone_without_area',
    'is_all_chinese', 'contains_chinese', 'starts_with', 'ends_with',
]
