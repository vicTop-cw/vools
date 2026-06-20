"""
vools vic 工具模块

提供 vicTools, vicDate, vicText, vicList 等工具类
保持向后兼容，从新位置导入
"""

from .utils import tools as vicTools
from .datetime import vDate as vicDate
from .data.vtext import VText as vicText
from .data.vlist import VList as vicList

__all__ = ['vicTools', 'vicDate', 'vicText', 'vicList']