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
    import weakref
    from collections.abc import Mapping as _Mapping

    # "未设置"哨兵：与 ContextVar 实例自身区分，供 copy_context 判定
    _UNSET = object()

    # 活着的 ContextVar 弱引用集合，供 copy_context() 做快照
    _VAR_REGISTRY = weakref.WeakSet()

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
        __slots__ = ('_name', '_default', '_local', '__weakref__')
        
        def __init__(self, name: str, default: _T = None):
            self._name = name
            self._default = default
            self._local = threading.local()
            _VAR_REGISTRY.add(self)
        
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


    class Context(_Mapping):
        """
        Context 兼容实现（Python 3.6）

        标准库 3.7+ 的 Context 是「当前上下文变量的不可变快照」，支持：
        - 映射协议：ctx[var] / len(ctx) / iter(ctx) / var in ctx
        - ctx.run(callable, *args, **kwargs)：在该快照内执行并返回结果

        py3.6 版本用「dict 快照 + run 时临时赋值并在 finally 恢复」模拟。
        局限（与 ContextVar 模拟版一致）：基于 threading.local，非 async-safe。
        """
        __slots__ = ('_snapshot',)

        def __init__(self, snapshot=None):
            # snapshot: {ContextVar: value}，只保留「已设置」的变量
            self._snapshot = dict(snapshot or {})

        def __getitem__(self, key):
            return self._snapshot[key]

        def __iter__(self):
            return iter(self._snapshot)

        def __len__(self):
            return len(self._snapshot)

        def copy(self):
            """返回快照副本"""
            return Context(self._snapshot)

        def run(self, callable, *args, **kwargs):
            """
            在本快照上下文内执行 callable，结束后恢复原值。

            Args:
                callable: 要执行的可调用对象
                *args, **kwargs: 传给 callable 的参数

            Returns:
                callable 的返回值
            """
            tokens = []
            try:
                for var, value in list(self._snapshot.items()):
                    tokens.append((var, var.set(value)))
                return callable(*args, **kwargs)
            finally:
                # 逆序恢复，尽量贴近标准库语义
                for var, token in reversed(tokens):
                    var.reset(token)


    def copy_context():
        """
        快照当前线程的上下文（Python 3.6 模拟）。

        标准库 3.7+ 返回当前 Context 的浅拷贝；这里遍历所有已注册的
        ContextVar，收集「当前线程已设置」的值组成快照。

        Returns:
            Context: 变量快照（只含已设置过值的变量）
        """
        snapshot = {}
        for var in list(_VAR_REGISTRY):
            # 与 ContextVar.get/set 同一套哨兵约定：未设置时 _local.value
            # 不存在，或等于 var 自身
            value = getattr(var._local, 'value', _UNSET)
            if value is not _UNSET and value is not var:
                snapshot[var] = value
        return Context(snapshot)


__all__ = ['ContextVar', 'Context', 'copy_context', 'Token']
