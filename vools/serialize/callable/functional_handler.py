"""
函数式对象序列化处理器

处理 Pipe, Ops, P, Box 等函数式对象的序列化
"""

from typing import Any, Dict

from . import CallableHandler
from .decorator_handler import _make_ref, _resolve_ref
from ...core.base import VoolsBase
__all__ = ['FunctionalHandler']


class FunctionalHandler(CallableHandler, VoolsBase):
    """处理函数式对象的序列化"""

    # 要处理的类型
    _handles_types = ('Pipe', 'Ops', 'P', 'Box')

    def can_handle(self, obj: Any) -> bool:
        """检查对象是否是函数式对象"""
        return type(obj).__name__ in self._handles_types

    def get_state(self, obj: Any) -> Dict[str, Any]:
        """
        获取函数式对象的序列化状态

        Args:
            obj: 函数式对象

        Returns:
            包含序列化状态的字典
        """
        state = {
            'type_name': type(obj).__name__,
        }

        obj_type = type(obj).__name__

        if obj_type == 'Pipe':
            raw = getattr(obj, 'raw_func', None)
            state['raw_func_ref'] = _make_ref(raw)
            if state['raw_func_ref'] is None and raw is not None:
                state['raw_func'] = raw
            state['args'] = tuple(getattr(obj, 'args', ()))
            state['kwargs'] = dict(getattr(obj, 'kwargs', {}))
        elif obj_type == 'Ops':
            # Ops 是静态方法集合，不需要特殊状态
            pass
        elif obj_type == 'P':
            fn = getattr(obj, 'func', None)
            state['func_ref'] = _make_ref(fn)
            if state['func_ref'] is None and fn is not None:
                state['func'] = fn
            state['args'] = getattr(obj, 'args', tuple())
            state['kwargs'] = getattr(obj, 'kwargs', {})
            state['ix'] = getattr(obj, 'ix', 1)
        elif obj_type == 'Box':
            state['value'] = getattr(obj, '__wrapped__',
                                     getattr(obj, '_value',
                                             getattr(obj, 'value', None)))

        return state


    def restore(self, state: Dict[str, Any]) -> Any:
        """
        从状态恢复函数式对象

        Args:
            state: 序列化状态字典

        Returns:
            恢复的函数式对象
        """
        obj_type = state['type_name']

        if obj_type == 'Pipe':
            from ...functional import Pipe
            raw = state.get('raw_func')
            ref = state.get('raw_func_ref')
            if raw is None and ref is not None:
                raw = _resolve_ref(ref)
            if raw is None:
                # 向后兼容：旧格式把闭包函数存在 'func' 里
                raw = state.get('func')
            if raw is None:
                raise ValueError(
                    "无法恢复 Pipe：raw_func 及引用均不可用")
            return Pipe(raw, *state.get('args', tuple()),
                        **state.get('kwargs', {}))

        elif obj_type == 'Ops':
            from ...functional import Ops
            return Ops

        elif obj_type == 'P':
            from ...functional import P
            fn = state.get('func')
            ref = state.get('func_ref')
            if fn is None and ref is not None:
                fn = _resolve_ref(ref)
            if fn is None:
                raise ValueError("无法恢复 P：func 及引用均不可用")
            # BUG-451: 原实现忽略 state['ix'] —— P(..., ix=2) 恢复后变回 ix=1，
            # 管道插入位置改变（静默错位）。
            return P(
                fn,
                *state.get('args', tuple()),
                ix=state.get('ix', 1),
                **state.get('kwargs', {})
            )

        elif obj_type == 'Box':
            from ...functional import Box
            return Box(state.get('value'))

        raise ValueError(f"Unknown functional type: {obj_type}")