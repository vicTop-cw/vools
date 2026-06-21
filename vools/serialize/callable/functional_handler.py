"""
函数式对象序列化处理器

处理 Pipe, Ops, P, Box 等函数式对象的序列化
"""

from typing import Any, Dict

from . import CallableHandler
__all__ = ['FunctionalHandler']


class FunctionalHandler(CallableHandler):
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
            state['raw_func'] = getattr(obj, 'raw_func', None)
            state['func'] = getattr(obj, 'func', None)
        elif obj_type == 'Ops':
            # Ops 是静态方法集合，不需要特殊状态
            pass
        elif obj_type == 'P':
            state['func'] = getattr(obj, 'func', None)
            state['args'] = getattr(obj, 'args', tuple())
            state['kwargs'] = getattr(obj, 'kwargs', {})
            state['ix'] = getattr(obj, 'ix', 1)
        elif obj_type == 'Box':
            state['value'] = getattr(obj, '_value', getattr(obj, 'value', None))

        return state


    def do(self, f=print, pre_f=None, sub_f=None):
        """Apply a function for side effects, return self.

        Args:
            f: Function to apply (default print)
            pre_f: Pre-processing function
            sub_f: Post-processing function (no return value expected)

        Returns:
            self, for chaining
        """
        rs = self
        if pre_f:
            rs = pre_f(rs)
        rs = f(rs)
        if sub_f:
            sub_f(rs)
        return self
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
            func = state.get('func')
            if func:
                return Pipe(func)
            return state.get('raw_func')

        elif obj_type == 'Ops':
            from ...functional import Ops
            return Ops

        elif obj_type == 'P':
            from ...functional import P
            return P(
                state.get('func'),
                *state.get('args', tuple()),
                **state.get('kwargs', {})
            )

        elif obj_type == 'Box':
            from ...functional import Box
            return Box(state.get('value'))

        raise ValueError(f"Unknown functional type: {obj_type}")