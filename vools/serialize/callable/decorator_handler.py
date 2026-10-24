"""
装饰器包装函数序列化处理器
"""

from typing import Any, Dict, Callable, Optional
import functools
import importlib
import inspect

from . import CallableHandler
from ...core.base import VoolsBase
__all__ = ['DecoratorHandler', '_make_ref', '_resolve_ref']


def _make_ref(func: Any) -> Optional[Dict[str, str]]:
    """为可调用对象生成可 pickle 的 ``{'module', 'qualname'}`` 引用（BUG-449）。

    仅当对象是 Python 函数/方法且限定名不包含 ``<locals>`` 时返回引用；
    否则返回 None（调用方退回直接存对象）。
    """
    # BUG-454: 绑定方法（types.MethodType / 含 __self__）不能只用 module+qualname
    # 表示——解析回来只是函数/描述符，实例绑定信息丢失。Curried 包着绑定方法时
    # 会静默错位：c.add 的 self 被当成第一个 curry 参数（实测 r(1)(2) 得到
    # add{'self': 1, 'a': 2}）。这类对象必须退回"存对象"路径（pickle 可，JSON 响亮失败）。
    if inspect.ismethod(func) or getattr(func, "__self__", None) is not None:
        return None
    module = getattr(func, "__module__", None)
    qualname = getattr(func, "__qualname__", None)
    if not isinstance(module, str) or not isinstance(qualname, str):
        return None
    if "<locals>" in qualname or qualname == "<lambda>":
        return None
    return {"module": module, "qualname": qualname}


def _resolve_ref(ref: Dict[str, str]) -> Optional[Any]:
    """按 ``{'module', 'qualname'}`` 解析回对象（BUG-449）。"""
    try:
        obj: Any = importlib.import_module(ref["module"])
    except Exception:
        return None
    for part in ref["qualname"].split("."):
        try:
            obj = getattr(obj, part)
        except AttributeError:
            return None
    return obj if callable(obj) else None


class DecoratorHandler(CallableHandler, VoolsBase):
    """处理被装饰器包装的函数的序列化"""

    def can_handle(self, obj: Any) -> bool:
        """检查对象是否是被装饰器包装的函数"""
        if not callable(obj):
            return False
        # BUG-447: 原实现第三个条件是 ``hasattr(__name__) and not
        # hasattr(__code__)``——它把所有 **C 实现的 callable**（builtins：print/
        # len 等）都误认领为"被装饰器包装的函数"：get_state 只能拿到 name/module，
        # restore 必然抛 ``ValueError: Cannot restore decorated function: len``。
        # 真正被装饰的函数一定有 ``__wrapped__``（functools.wraps）或本库的
        # ``_vools_decorator`` 标记；其余（普通函数/builtins/lambda）应回退到
        # 'raw' 序列化路径。
        return (
            hasattr(obj, '__wrapped__') or
            hasattr(obj, '_vools_decorator')
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
        # BUG-449: 只有无法生成 module+qualname 引用时才把原始函数**对象**放进
        # 状态——否则 functools.wraps 之后模块级同名属性已被 wrapper 占用，
        # pickle 会抛 "it's not the same object as <module>.<name>"。
        if hasattr(obj, '__wrapped__') and _make_ref(obj.__wrapped__) is None:
            state['__wrapped__'] = obj.__wrapped__
        if hasattr(obj, '_vools_decorator'):
            state['_vools_decorator'] = obj._vools_decorator

        # 尝试获取原始函数
        if hasattr(obj, '__wrapped__'):
            state['original_ref'] = _make_ref(obj.__wrapped__)
            if state['original_ref'] is None:
                # 无法用 module+qualname 定位（lambda/<locals>/内建等）时退回对象
                state['original_func'] = obj.__wrapped__
        elif hasattr(obj, '_vools_decorator'):
            # BUG-448: can_handle 会认领只带 ``_vools_decorator`` 标记、没有
            # ``__wrapped__`` 的对象，但 restore 只认 ``original_func``——必然抛
            # ``ValueError: Cannot restore decorated function``（认领与恢复不对称）。
            # BUG-449: 优先记录 module+qualname 引用（可 pickle），对象仅作兜底。
            state['original_ref'] = _make_ref(obj)
            if state['original_ref'] is None:
                state['original_func'] = obj

        return state


    def restore(self, state: Dict[str, Any]) -> Any:
        """
        从状态恢复被装饰的函数

        Args:
            state: 序列化状态字典

        Returns:
            恢复的函数
        """
        # BUG-449: 优先按 module+qualname 重新导入原始可调用对象。
        # 原实现只存函数**对象**，而 functools.wraps 之后模块级同名属性已被
        # wrapper 占用，pickle 按引用序列化会抛
        # ``PicklingError: it's not the same object as <module>.<name>``
        # ——即"最典型的被装饰函数"根本无法往返。
        ref = state.get('original_ref')
        if ref is not None:
            original = _resolve_ref(ref)
            if original is not None:
                @functools.wraps(original)
                def wrapper_from_ref(*args, **kwargs):
                    return original(*args, **kwargs)
                wrapper_from_ref._vools_decorator = state.get(
                    '_vools_decorator', 'decorator')
                return wrapper_from_ref

        # 兜底：旧格式（直接存对象）
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