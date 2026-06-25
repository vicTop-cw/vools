"""
日期时间工具模块

包含日期时间处理的实用工具：
- utils: 日期时间工具函数（整合了原range、mydate、mydates的功能）
- dates_format: 日期格式化工具
"""

from .utils import *
from .vdate_class import VDate
from .dates_format import *

__all__ = [
    # 从 utils 导出
    'vDate',
    'get_week',
    'get_month',
    'days_gap',
    'weeks_gap',
    'months_gap',
    'get_recently_months',
    'get_recently_weeks',
    'get_recently_days',
    'get_dates',
    'parse_date_string',
    'get_date_range',
    'simplify_date_ranges',

    # 从 vdate_class 导出
    'VDate',

    # 从 dates_format 导出
    'DateProcessor',
    'EnhancedDateFormatter',
]


def __getattr__(name):
    """延迟加载 vicDate"""
    if name == 'vicDate':
        from ..datetime.vdate_class import VDate as vicDate
        return vicDate
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


import sys as _sys
if _sys.version_info < (3, 7):
    try:
        from .vdate_class import VDate as vicDate
    except Exception:
        pass