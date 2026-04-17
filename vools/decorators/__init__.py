"""
装饰器模块

包含各种实用的装饰器：
- cache: 缓存装饰器（memorize, once）
- lazy: 延迟求值装饰器
- curry: 柯里化装饰器（curry, delay_curry）
- control: 控制流装饰器（repeat, retry, rerun）
- overload: 重载装饰器
- threading: 多线程装饰器（trd, proc）
- extend: 函数扩展装饰器
"""

from .cache import memorize, once, persist
from .lazy import lazy
from .control import repeat, retry, rerun
from .trd import trd, proc
from .extend import extend

# 柯里化装饰器
from .curry_core import curry, Curried, CurryDescriptor, is_curried, CurryExecutionError
from .curry_delay import delay_curry, DelayCurried, is_lazy

# 重载装饰器
from .overload import overload, OverloadManager, strict

# overcurry 装饰器
from .overcurry import overcurry, OvercurryManager

# 选择器
from .selector import Selector, Overloads, overloads

# 柯里化函数
from .curried import (
    curried_map,
    curried_filter,
    curried_reduce,
    compose,
    pipe,
    curried_pipe,
    add,
    mul,
    sub,
    div,
    and_,
    or_,
    not_,
    identity,
    const,
    flip,
    apply,
    curried_apply,
)

__all__ = [
    # 缓存
    'memorize',
    'once',
    'persist',
    
    # 延迟求值
    'lazy',
    
    # 控制流
    'repeat',
    'retry',
    'rerun',
    
    # 多线程
    'trd',
    'proc',
    
    # 函数扩展
    'extend',
    
    # 柯里化
    'curry',
    'delay_curry',
    'Curried',
    'CurryDescriptor',
    'DelayCurried',
    'is_curried',
    'is_lazy',
    'CurryExecutionError',
    
    # 重载
    'overload',
    'OverloadManager',
    'strict',
    
    # overcurry
    'overcurry',
    'OvercurryManager',
    
    # 选择器
    'Selector',
    'Overloads',
    'overloads',
    
    # 柯里化函数
    'curried_map',
    'curried_filter',
    'curried_reduce',
    'compose',
    'pipe',
    'curried_pipe',
    'add',
    'mul',
    'sub',
    'div',
    'and_',
    'or_',
    'not_',
    'identity',
    'const',
    'flip',
    'apply',
    'curried_apply',
]
