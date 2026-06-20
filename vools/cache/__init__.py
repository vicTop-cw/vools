"""
vools.cache - 函数签名缓存与装饰器包

包含：
- sigcache: 函数签名缓存核心功能
- once: 单次执行装饰器
- persist: 持久化缓存装饰器
"""

from .sigcache import (
    get_signature,
    cached_getsignature,
    add_custom_sig,
    remove_signature,
    clear_cache,
    cache_info,
)

from .once import once
from .persist import persist, FileLock
from .memorize import memorize

__all__ = [
    # sigcache 模块
    "get_signature",
    "cached_getsignature",
    "add_custom_sig",
    "remove_signature",
    "clear_cache",
    "cache_info",
    # memorize 模块
    "memorize",
    # once 模块
    "once",
    # persist 模块
    "persist",
    "FileLock",
]
