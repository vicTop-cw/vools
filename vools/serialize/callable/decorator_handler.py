"""
装饰器包装函数序列化处理器
"""

from typing import Any, Dict, Callable
import functools

from . import CallableHandler
__all__ = ['DecoratorHandler']


class DecoratorHandler(CallableHandler):
    """处理被装饰器包装的函数的序列化"""

    def can_handle(self, obj: Any) -> bool:
        """检查对象是否是被装饰器包装的函数"""
        if not callable(obj):
            return False
        # 检查是否有 wraps 保留的属性
        return (
            hasattr(obj, '__wrapped__') or
            hasattr(obj, '_vools_decorator') or
            hasattr(obj, '__name__') and not hasattr(obj, '__code__')
        )

    def get_state(self, obj: Any) -> Dict[str, Any]:
        """
        获取被装饰函数的序列化状态

        Args:
            obj: 被装饰的函数对象

        Returns:
            包含序列化状态的字典
        """
        state = {
            'name': getattr(obj, '__name__', str(type(obj))),
            'module': getattr(obj, '__module__', None),
        }

        # 保存装饰器相关属性
        if hasattr(obj, '__wrapped__'):
            state['__wrapped__'] = obj.__wrapped__
        if hasattr(obj, '_vools_decorator'):
            state['_vools_decorator'] = obj._vools_decorator

        # 尝试获取原始函数
        if hasattr(obj, '__wrapped__'):
            state['original_func'] = obj.__wrapped__

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
        从状态恢复被装饰的函数

        Args:
            state: 序列化状态字典

        Returns:
            恢复的函数
        """
        # 如果有原始函数引用，尝试重建
        if 'original_func' in state:
            original = state['original_func']
            if 'name' in state:
                # 创建一个简单的 wrapper
                @functools.wraps(original)
                def wrapper(*args, **kwargs):
                    return original(*args, **kwargs)
                wrapper._vools_decorator = state.get('_vools_decorator', 'decorator')
                return wrapper

        raise ValueError(f"Cannot restore decorated function: {state.get('name', 'unknown')}")