"""
OOP 工具模块

包含面向对象编程的实用工具：
- extend: 类扩展装饰器
- selector: 方法选择器
- calltype: 调用类型检查
"""

from .extend import *
from .selector import *
from .calltype import *

__all__ = [
    # 从 extend 导出
    'extend',
    'cls_extend',
    
    # 从 selector 导出
    'selector',
    'Selector',
    
    # 从 calltype 导出
    'calltype',
]
