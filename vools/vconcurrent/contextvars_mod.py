"""
vools.concurrent.contextvars_mod - 上下文变量高级封装

基于 vools.core.contextvars_compat 兼容层，提供增强版的上下文变量工具：

- VContextVar: 增强版 ContextVar，支持 get_or_default / set_if_none / with_value
- ContextScope: 上下文作用域管理器，批量设置 + with 自动恢复
- contextual: 函数装饰器，将函数的某个参数自动绑定到 VContextVar
- copy_context_dict / restore_context_dict: 上下文与字典互转
- ContextChain: 上下文链，支持父子上下文继承和覆盖

兼容 Python 3.6+，3.7+ 使用标准库 contextvars，3.6 回退到 vools.core.contextvars_compat
"""

from __future__ import annotations

import sys
import inspect
import functools
from contextlib import contextmanager
from typing import (
    Any, Callable, Dict, Iterator, List, Mapping, Optional,
    Tuple, TypeVar, Generic,
)

from ..core.contextvars_compat import ContextVar, Context, copy_context, Token

__all__ = [
    'VContextVar', 'ContextScope', 'contextual',
    'copy_context_dict', 'restore_context_dict', 'ContextChain',
]

_T = TypeVar('_T')
_MISSING: Any = object()  # sentinel: 表示"未提供默认值"

_PY37_PLUS = sys.version_info >= (3, 7)

# 全局注册表：VContextVar 名称 -> 实例
_REGISTRY: Dict[str, VContextVar] = {}


class VContextVar(Generic[_T]):
    """
    增强版 ContextVar

    在标准 ContextVar 之上提供：
    - get_or_default(default): 获取值，未设置则返回 default
    - set_if_none(value): 仅当未设置时才设置
    - with_value(value): 上下文管理器，临时设置值并在退出时恢复
    - 类型安全默认值

    Usage:
        user_id = VContextVar('user_id', default=0)
        user_id.set(123)
        user_id.get()              # -> 123
        user_id.get_or_default(0)  # -> 123
        with user_id.with_value(456):
            user_id.get()          # -> 456
        user_id.get()              # -> 123
    """

    def __init__(self, name: str, default: Any = _MISSING) -> None:
        self._name = name
        self._default = default
        # 复用已注册的底层 ContextVar，确保同名 VContextVar 共享状态
        existing = _REGISTRY.get(name)
        if existing is not None:
            self._var: ContextVar = existing._var
        else:
            # 不把 default 传给底层 ContextVar，以便统一检测"是否已设置"
            self._var = ContextVar(name)
        _REGISTRY[name] = self

    @property
    def name(self) -> str:
        return self._name

    @property
    def default(self) -> Any:
        """默认值（未设置时返回 None）"""
        return None if self._default is _MISSING else self._default

    def is_set(self) -> bool:
        """当前上下文中是否已设置值"""
        if _PY37_PLUS:
            try:
                self._var.get()
                return True
            except LookupError:
                return False
        else:
            # 3.6 兼容层：通过 _local 检测，与兼容层的 get() 逻辑一致
            val = getattr(self._var._local, 'value', self._var)
            return val is not self._var

    def get(self) -> _T:
        """
        获取当前值。
        - 已设置：返回当前值
        - 未设置但有默认值：返回默认值
        - 未设置且无默认值：抛出 LookupError
        """
        if self.is_set():
            return self._var.get()  # type: ignore[return-value]
        if self._default is not _MISSING:
            return self._default  # type: ignore[return-value]
        raise LookupError(self._name)

    def get_or_default(self, default: _T) -> _T:
        """获取当前值；未设置则返回 default"""
        if self.is_set():
            return self._var.get()  # type: ignore[return-value]
        return default

    def set(self, value: _T) -> Token:
        """设置当前值，返回 Token 用于后续 reset"""
        return self._var.set(value)

    def reset(self, token: Token) -> None:
        """使用 Token 重置到之前的值"""
        self._var.reset(token)

    def set_if_none(self, value: _T) -> bool:
        """
        仅当当前上下文中未设置时才设置。
        Returns:
            True 表示执行了设置；False 表示已有值，未设置。
        """
        if not self.is_set():
            self._var.set(value)
            return True
        return False

    @contextmanager
    def with_value(self, value: _T) -> Iterator[_T]:
        """上下文管理器：临时设置值，退出时自动恢复"""
        token = self._var.set(value)
        try:
            yield value
        finally:
            self._var.reset(token)

    def __repr__(self) -> str:
        return f'VContextVar({self._name!r})'


class ContextScope:
    """
    上下文作用域管理器

    批量设置多个 VContextVar，with 语句退出时自动恢复全部绑定。

    支持在进入作用域前（with 之前）和进入后（with 内部）调用 set：
    - with 之前调用 set：绑定延迟到 __enter__ 时统一应用
    - with 内部调用 set：立即应用并记录 Token，__exit__ 时恢复

    Usage:
        user_id = VContextVar('user_id')
        tenant = VContextVar('tenant')

        with ContextScope() as scope:
            scope.set('user_id', 123)
            scope.set('tenant', 'acme')
            # user_id=123, tenant='acme' 在此作用域内有效
        # 已恢复
    """

    def __init__(self) -> None:
        self._bindings: List[Tuple[VContextVar, Any]] = []
        self._tokens: List[Tuple[VContextVar, Token]] = []
        self._active: bool = False

    def set(self, name: str, value: Any) -> 'ContextScope':
        """
        添加一个变量绑定。

        如果在 with 块内调用，立即应用；否则延迟到 __enter__ 时应用。
        """
        var = _REGISTRY.get(name)
        if var is None:
            var = VContextVar(name)
        if self._active:
            token = var.set(value)
            self._tokens.append((var, token))
        else:
            self._bindings.append((var, value))
        return self

    def __enter__(self) -> 'ContextScope':
        self._active = True
        self._tokens = []
        for var, value in self._bindings:
            token = var.set(value)
            self._tokens.append((var, token))
        return self

    def __exit__(self, *exc_info: Any) -> None:
        for var, token in reversed(self._tokens):
            try:
                var.reset(token)
            except (ValueError, LookupError):
                pass
        self._tokens = []
        self._bindings = []
        self._active = False

    def __repr__(self) -> str:
        return f'ContextScope(active={self._active}, bindings={len(self._bindings)})'


def contextual(var: VContextVar, param: str) -> Callable:
    """
    函数装饰器：将函数的某个参数自动绑定到 VContextVar

    被装饰的函数在调用时，如果不显式传递该参数，则从 VContextVar 获取。

    Args:
        var: 要绑定的 VContextVar
        param: 参数名

    Usage:
        user_id = VContextVar('user_id', default=0)

        @contextual(user_id, 'uid')
        def fetch_user(uid):
            return f'user={uid}'

        fetch_user()        # uid 从 user_id ContextVar 获取
        fetch_user(123)     # uid=123（显式位置参数）
        fetch_user(uid=456) # uid=456（显式关键字参数）
    """

    def decorator(func: Callable) -> Callable:
        try:
            sig = inspect.signature(func)
            param_list = list(sig.parameters.keys())
            param_idx = param_list.index(param) if param in param_list else -1
        except (ValueError, TypeError):
            param_idx = -1

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # 显式传递（关键字或位置）则不覆盖
            if param in kwargs:
                return func(*args, **kwargs)
            if param_idx >= 0 and param_idx < len(args):
                return func(*args, **kwargs)
            kwargs[param] = var.get()
            return func(*args, **kwargs)

        return wrapper

    return decorator


def copy_context_dict(names: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    将当前上下文中已注册的 VContextVar 值复制为字典

    Args:
        names: 要复制的变量名列表；None 表示复制所有已注册的变量

    Returns:
        变量名到当前值的字典（仅包含已设置的变量）
    """
    result: Dict[str, Any] = {}
    keys = names if names is not None else list(_REGISTRY.keys())
    for name in keys:
        var = _REGISTRY.get(name)
        if var is not None and var.is_set():
            result[name] = var.get()
    return result


def restore_context_dict(data: Mapping[str, Any]) -> List[Tuple[VContextVar, Token]]:
    """
    从字典恢复上下文

    将字典中的每个键值对设置到对应的 VContextVar。
    如果变量名未注册，会自动创建新的 VContextVar。

    Args:
        data: 变量名到值的映射

    Returns:
        (VContextVar, Token) 列表，可用于后续重置：

        tokens = restore_context_dict({'a': 1, 'b': 2})
        # ... 使用上下文 ...
        for var, token in reversed(tokens):
            var.reset(token)
    """
    tokens: List[Tuple[VContextVar, Token]] = []
    for name, value in data.items():
        var = _REGISTRY.get(name)
        if var is None:
            var = VContextVar(name)
        token = var.set(value)
        tokens.append((var, token))
    return tokens


class ContextChain:
    """
    上下文链，支持父子上下文继承和覆盖

    子链继承父链的所有绑定，可覆盖特定值。
    进入时按继承顺序（父→子）应用所有绑定，退出时全部恢复。

    Usage:
        parent = ContextChain()
        parent.set('a', 1)
        parent.set('b', 2)

        child = parent.child()
        child.set('b', 3)   # 覆盖父链
        child.set('c', 4)

        with child:
            # a=1, b=3, c=4
            ...
        # 全部恢复
    """

    def __init__(self, parent: Optional['ContextChain'] = None) -> None:
        self._parent = parent
        self._bindings: Dict[str, Any] = {}
        self._tokens: List[Tuple[VContextVar, Token]] = []
        self._active: bool = False

    def set(self, name: str, value: Any) -> 'ContextChain':
        """
        设置当前链的变量绑定。

        如果在 with 块内调用，立即应用；否则延迟到 __enter__ 时应用。
        """
        self._bindings[name] = value
        if self._active:
            var = _REGISTRY.get(name)
            if var is None:
                var = VContextVar(name)
            token = var.set(value)
            self._tokens.append((var, token))
        return self

    def get(self, name: str, default: Any = _MISSING) -> Any:
        """
        获取变量值（不修改 ContextVar）。

        查找顺序：当前链绑定 → 父链绑定 → 已注册的 ContextVar 实际值 → default
        """
        if name in self._bindings:
            return self._bindings[name]
        if self._parent is not None:
            return self._parent.get(name, default)
        var = _REGISTRY.get(name)
        if var is not None and var.is_set():
            return var.get()
        if default is _MISSING:
            raise KeyError(name)
        return default

    def child(self) -> 'ContextChain':
        """创建子链"""
        return ContextChain(parent=self)

    def _collect_bindings(self) -> Dict[str, Any]:
        """递归收集从根到当前链的所有绑定（子覆盖父）"""
        result: Dict[str, Any] = {}
        if self._parent is not None:
            result.update(self._parent._collect_bindings())
        result.update(self._bindings)
        return result

    def __enter__(self) -> 'ContextChain':
        self._active = True
        self._tokens = []
        for name, value in self._collect_bindings().items():
            var = _REGISTRY.get(name)
            if var is None:
                var = VContextVar(name)
            token = var.set(value)
            self._tokens.append((var, token))
        return self

    def __exit__(self, *exc_info: Any) -> None:
        for var, token in reversed(self._tokens):
            try:
                var.reset(token)
            except (ValueError, LookupError):
                pass
        self._tokens = []
        self._active = False

    def __repr__(self) -> str:
        parent_repr = f', parent={self._parent!r}' if self._parent is not None else ''
        return f'ContextChain(active={self._active}, bindings={len(self._bindings)}{parent_repr})'
