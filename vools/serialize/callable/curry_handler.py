"""
柯里化函数序列化处理器（BUG-453）。

``@curry`` / ``curry(fn)`` 返回的 ``Curried`` 对象此前**完全不可序列化**：

* pickle 路径：``TypeError: cannot pickle 'mappingproxy' object``
  （``Curried`` 用 ``__slots__``，内部持有类/描述符相关对象）
* JSON 路径：``TypeError: Object of type Curried is not serializable``

因此把柯里化函数放进任务载荷/缓存时静默不可用。本处理器把
``func`` 存成可 pickle 的 ``{'module','qualname'}`` 引用（复用
``DecoratorHandler`` 的助手），并把部分应用参数 ``bound_args`` 一并保存，
反序列化时重建等价的 ``Curried``。
"""

from typing import Any, Dict, Optional

from . import CallableHandler
from ...core.base import VoolsBase
from .decorator_handler import _make_ref, _resolve_ref

__all__ = ['CurryHandler']


class CurryHandler(CallableHandler, VoolsBase):
    """处理 ``Curried``（柯里化函数）的序列化。"""

    @property
    def handler_name(self) -> str:
        return "CurryHandler"

    def can_handle(self, obj: Any) -> bool:
        """仅认领 ``Curried`` 实例。"""
        try:
            from ...decorators.curry_core import Curried
        except Exception:
            return False
        return isinstance(obj, Curried)

    def get_state(self, obj: Any) -> Dict[str, Any]:
        """保存底层函数引用 + 部分应用参数 + 模式标志。"""
        state: Dict[str, Any] = {'type_name': 'Curried'}
        fn = getattr(obj, 'func', None)
        ref = _make_ref(fn) if fn is not None else None
        if ref is not None:
            state['func_ref'] = ref
        elif fn is not None:
            # 无法用 module+qualname 定位（lambda/<locals>）时退回对象：
            # 序列化会响亮失败而不是产出错误的 Curried。
            state['func'] = fn
        state['bound_args'] = dict(getattr(obj, 'bound_args', {}) or {})
        state['is_strict'] = bool(getattr(obj, 'is_strict', False))
        state['delaied'] = bool(getattr(obj, 'delaied', False))
        return state

    def restore(self, state: Dict[str, Any]) -> Any:
        """按引用（或兜底对象）重建 ``Curried``。"""
        try:
            from ...decorators.curry_core import Curried, is_curried
        except Exception as exc:      # pragma: no cover - 依赖缺失时显式报错
            raise ValueError(f"无法导入 Curried：{exc}") from exc

        fn = state.get('func')
        ref = state.get('func_ref')
        if fn is None and ref is not None:
            fn = _resolve_ref(ref)
        if fn is None:
            raise ValueError("无法恢复 Curried：func 及引用均不可用")

        # 模块级 @curry 函数的名字已被 Curried 实例占用，引用会解析回它本身
        if is_curried(fn):
            return fn

        return Curried(
            fn,
            state.get('bound_args') or {},
            bool(state.get('is_strict', False)),
            bool(state.get('delaied', False)),
        )
