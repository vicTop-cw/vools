"""
通用工具模块

包含：
- stuff: 高级参数注入装饰器（基于 curry）
- identity: 恒等函数
- const: 常量函数
- compose: 函数组合
- pipe: 函数管道
"""

from typing import Any, Callable

__all__ = ['stuff', 'identity', 'const', 'compose', 'pipe']


# ============================================================================
# 基础工具函数
# ============================================================================

def identity(x: Any) -> Any:
    """恒等函数"""
    return x


def const(x: Any) -> Callable:
    """常量函数"""
    return lambda *args, **kwargs: x


def compose(*funcs: Callable) -> Callable:
    """
    函数组合（从右到左）
    
    示例:
        >>> f = compose(lambda x: x + 1, lambda x: x * 2)
        >>> f(3)
        7  # (3 * 2) + 1
    """
    def _compose(x):
        result = x
        for func in reversed(funcs):
            result = func(result)
        return result
    return _compose


def pipe(*funcs: Callable) -> Callable:
    """
    函数管道（从左到右）
    
    示例:
        >>> f = pipe(lambda x: x * 2, lambda x: x + 1)
        >>> f(3)
        7  # (3 * 2) + 1
    """
    def _pipe(x):
        result = x
        for func in funcs:
            result = func(result)
        return result
    return _pipe


# ============================================================================
# stuff - 高级参数注入装饰器
# ============================================================================

from .stuff import stuff, Stuff, IndexedDict

__all__.extend(['Stuff', 'IndexedDict'])
