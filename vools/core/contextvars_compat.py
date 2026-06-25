"""
vools.core.contextvars_compat - contextvars 兼容性模块

Python 3.7 引入了 contextvars，但 Python 3.6 没有此模块。
本模块提供兼容实现，在 3.6 中使用 threading.local 模拟基础功能。

注意：由于 3.6 没有真正的 contextvars，模拟版本不是 async-safe 的，
仅保证线程内有效。在 3.6 环境下，如果异步代码和同步代码混用，
可能需要额外注意上下文隔离。
"""

import sys
import threading
from typing import TypeVar, Generic, Optional, Any

_T = TypeVar('_T')

# Python 版本检测
_PY37_PLUS = sys.version_info >= (3, 7)

if _PY37_PLUS:
    import contextvars as _ctx
    ContextVar = _ctx.ContextVar
    Context = _ctx.Context
    copy_context = _ctx.copy_context
    Token = _ctx.Token
else:
    # Python 3.6 兼容实现
    # 使用简单的类来模拟 ContextVar 的基本行为
    
    class Token:
        """Token 用于重置 ContextVar（模拟）"""
        __slots__ = ('_value',)
        
        def __init__(self, value):
            self._value = value


    class ContextVar:
        """
        ContextVar 兼容实现（Python 3.6）
        
        使用 threading.local 存储每个线程的上下文，
        不保证 async-safe，仅作为基础替代。
        """
        __slots__ = ('_name', '_default', '_local')
        
        def __init__(self, name: str, default: _T = None):
            self._name = name
            self._default = default
            self._local = threading.local()
        
        @property
        def name(self) -> str:
            return self._name
        
        def get(self, default: _T = None) -> _T:
            """
            获取当前线程的 ContextVar 值。
            
            如果当前线程未设置值，返回默认值。
            """
            value = getattr(self._local, 'value', self)
            if value is self:
                return self._default if self._default is not None else default
            return value
        
        def set(self, value: _T):
            """
            设置当前线程的 ContextVar 值。
            
            返回 Token 用于后续 reset。
            """
            old_value = getattr(self._local, 'value', self)
            self._local.value = value
            return Token(old_value)
        
        def reset(self, token: Token):
            """
            重置 ContextVar 到设置前的值。
            
            注意：这不是真正的 reset，仅用于兼容 API。
            """
            self._local.value = token._value


__all__ = ['ContextVar', 'Context', 'copy_context', 'Token']
