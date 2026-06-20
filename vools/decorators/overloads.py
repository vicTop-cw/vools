"""
已弃用: overloads 装饰器

此模块已合并到 ``vools.decorators.overload``。
请改用 ``from vools.decorators import overload`` 和新 API。

原来的 ``@overloads`` 用法请替换为:
    >>> from vools.decorators import overload
    >>> @overload(mode=Strict | Ambiguous)
    ... def fn(...): ...
"""

import warnings
from .overload import (
    overload, OverloadManager, OverloadMode,
    Priority, AllowSyncName, Strict, Ambiguous,
    ParentMode, ExportAsFunction, ExportAsManager,
    reset_registry,
)

# 注册表：(module, scope) -> {func_name: [impl1, impl2, ...]}
_registry = {}
_wrappers_cache = {}


def overloads(func):
    """已弃用: 请改用 ``@overload``"""
    warnings.warn(
        "``@overloads`` 已弃用, 请改用 ``@overload``",
        DeprecationWarning,
        stacklevel=2,
    )
    return overload(func)


def reset_overloads():
    """重置全局注册表"""
    reset_registry()


__all__ = ['overloads']
