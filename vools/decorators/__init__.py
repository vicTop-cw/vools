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

from ..cache import memorize, once, persist
from .lazy import lazy
from .control import repeat, retry, rerun, excepts, suppress, ignore
from .trd import trd, proc
# extend 延迟导入（原 decorators.extend 已移至 oop.method_extend）
from .shotcut import (
    timeit,
    safe,
    throttle,
    debounce,
    singleton,
    deprecated,
    conditional,
    with_context,
    with_timeout,
    validate,
    rate_limit,
    cache_with_ttl,
    hybrid_method,
    classproperty,
    enumize,
)

# 柯里化装饰器
from .curry_core import curry, Curried, CurryDescriptor, is_curried, CurryExecutionError
from .curry_delay import delay_curry, DelayCurried, is_lazy
from .curry_decorator import curry_class
# 重载装饰器（新模式：基于 OverloadMode 标志）
from .overload import overload, OverloadManager, OverloadMode, strict
from .overload import Priority, AllowSyncName, Strict, Ambiguous
from .overload import ParentMode, ExportAsFunction, ExportAsManager
from .overload import reset_registry

# overcurry 装饰器
from .overcurry import overcurry, OvercurryManager

# 选择器
from .selector import Selector, Overloads
# 重载装饰器（从 overloads.py 导入，不是 selector.py）
from .overloads import overloads

# rself 装饰器
from .rself import rself

# bridge 装饰器
from .bridge_decorator import bridge, BridgeRegistry

# 柯里化函数（延迟导入避免与 vools.curried 循环 import：
# vools.curried -> vools.decorators.curry_core -> vools.decorators.curried -> vools.curried）
# 直接 `import vools.curried.collection` 会触发 ImportError: cannot import name 'map'
_CURRIED_EXPORTS = {
    'curried_map', 'curried_filter', 'curried_reduce',
    'compose', 'pipe', 'curried_pipe',
    'add', 'mul', 'sub', 'div',
    'and_', 'or_', 'not_',
    'identity', 'const', 'flip', 'apply', 'curried_apply',
}

_curried_cache = None  # type: Optional[Dict[str, Any]]

def _load_curried():
    global _curried_cache
    if _curried_cache is None:
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
        _curried_cache = locals()
    return _curried_cache

#灵活的占位符
from .flex_pos import flex_pos

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
    'excepts',
    'suppress',
    'ignore',

    # 多线程
    'trd',
    'proc',

    # 函数扩展
    'extend',

    # 快捷工具
    'timeit',
    'safe',
    'throttle',
    'debounce',
    'singleton',
    'deprecated',
    'conditional',
    'with_context',
    'with_timeout',
    'validate',
    'rate_limit',
    'cache_with_ttl',
    'hybrid_method',
    'classproperty',
    'enumize',

    # 柯里化
    'curry',
    'curry_class',
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
    'OverloadMode',
    'strict',
    'Priority',
    'AllowSyncName',
    'Strict',
    'Ambiguous',
    'reset_registry',

    # overcurry
    'overcurry',
    'OvercurryManager',

    # 选择器
    'Selector',
    'Overloads',
    'overloads',

    # rself 装饰器
    'rself',

    # bridge 装饰器
    'bridge',
    'BridgeRegistry',

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
    'flex_pos'
]

# 向后兼容：extend 装饰器（原 decorators.extend，现移至 oop.method_extend）
# 使用延迟导入避免循环导入
def __getattr__(name):
    if name == 'extend':
        from ..oop.method_extend import extend
        return extend
    if name in _CURRIED_EXPORTS:
        return _load_curried().get(name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


import sys as _sys
if _sys.version_info < (3, 7):
    try:
        from ..oop.method_extend import extend
    except Exception:
        pass