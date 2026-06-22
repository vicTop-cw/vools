"""
OOP 工具模块

包含面向对象编程的实用工具：
- extend: 类扩展装饰器
- selector: 方法选择器
- calltype: 调用类型检查
"""

from .extend import clone, g, arrow_func
from .selector import overloads, Overloads, Selector
from .calltype import CallableType, get_callable_type, create_fake
from .mixer import Mixer, Mixer_, attr_Enum

__all__ = [
    # 从 extend 导出
    'clone',
    'g',
    'arrow_func',
    
    # 从 selector 导出
    'overloads',
    'Overloads',
    'Selector',
    
    # 从 calltype 导出
    'CallableType',
    'get_callable_type',
    'create_fake',
    
    # 从 mixer 导出
    'Mixer',
    'Mixer_',
    'attr_Enum',
]
