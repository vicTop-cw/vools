"""
缓存相关装饰器（已废弃，请使用 vools.cache）

.. deprecated::
    本模块已废弃，请使用 ``vools.cache`` 替代。
    ``vools.decorators.cache`` 仍可用作向后兼容，但建议迁移到 ``vools.cache``。

包含：
- memorize: 函数结果缓存装饰器
- once: 单次执行装饰器（支持函数和类）
- persist: 持久化缓存装饰器
"""

import warnings

from ..cache import (
    memorize,
    once,
    persist,
    FileLock,
)
from ..cache.memorize import TimedCache, _CACHE, _compute_key
from ..cache.persist import sanitize_file_key, _default_force_when_by_day


_DEPRECATION_MSG = (
    "vools.decorators.cache is deprecated, please use vools.cache instead. "
    "Importing from vools.decorators.cache will be removed in a future version."
)

warnings.warn(_DEPRECATION_MSG, DeprecationWarning, stacklevel=2)

__all__ = ['memorize', 'once', 'persist']
