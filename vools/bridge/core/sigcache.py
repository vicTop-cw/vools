"""
vools.bridge.core.sigcache - Bridge 子包签名缓存机制

为 vools.bridge 子包提供独立的函数签名缓存体系，
与 vools.cache.sigcache 不冲突，每种语言桥接可以有自己的缓存实例。

缓存内容包括:
    - 函数签名 (inspect.Signature)
    - 函数类型注解 (annotations / get_type_hints)
    - 函数体提取结果 (body string)
    - FunctionSpec 对象 (解析后的完整规格)

特性:
    - 按语言命名空间隔离缓存
    - LRU 淘汰策略，防止内存泄漏
    - 线程安全（CPython GIL 保护）
    - 提供 clear_cache() 等管理函数
"""

import inspect
import logging
import weakref
from collections import OrderedDict
from typing import Any, Callable, Dict, Optional, List

log = logging.getLogger("vools.bridge.sigcache")

_MAX_CACHE_SIZE = 2048
"""每种语言缓存的最大条目数，超过时淘汰最久未使用的条目 (LRU)。"""


class BridgeSigCache:
    """Bridge 签名缓存类，每种语言桥接可以有自己的缓存实例。

    使用 OrderedDict 实现 LRU 淘汰策略，按语言命名空间隔离缓存。
    使用 weakref 跟踪函数对象生命周期，避免 id 复用导致的缓存错误命中。

    Attributes:
        lang: 语言名称，用于标识缓存命名空间。
        max_size: 缓存最大条目数。
    """

    def __init__(self, lang: str = "default", max_size: int = _MAX_CACHE_SIZE) -> None:
        """初始化 BridgeSigCache 实例。

        Args:
            lang: 语言名称，用于标识缓存命名空间。
            max_size: 缓存最大条目数。
        """
        self.lang = lang
        self.max_size = max_size
        self._sig_cache: OrderedDict = OrderedDict()
        self._annotations_cache: OrderedDict = OrderedDict()
        self._body_cache: OrderedDict = OrderedDict()
        self._spec_cache: OrderedDict = OrderedDict()
        self._weak_refs: Dict[int, weakref.ref] = {}
        self._hits = 0
        self._misses = 0

    def _on_object_dead(self, ref: weakref.ref) -> None:
        """弱引用回调：当被引用的函数对象被回收时，清理对应缓存。

        Args:
            ref: 已失效的弱引用对象。
        """
        dead_id = None
        for obj_id, r in list(self._weak_refs.items()):
            if r is ref:
                dead_id = obj_id
                break
        if dead_id is not None:
            self._weak_refs.pop(dead_id, None)
            self._sig_cache.pop(dead_id, None)
            self._annotations_cache.pop(dead_id, None)
            for key in list(self._body_cache.keys()):
                if isinstance(key, tuple) and key[0] == dead_id:
                    self._body_cache.pop(key, None)
            for key in list(self._spec_cache.keys()):
                if isinstance(key, tuple) and key[0] == dead_id:
                    self._spec_cache.pop(key, None)

    def _register_weakref(self, func: Callable) -> None:
        """注册函数对象的弱引用，用于检测对象回收。

        Args:
            func: 要跟踪的函数对象。
        """
        obj_id = id(func)
        if obj_id not in self._weak_refs:
            try:
                ref = weakref.ref(func, self._on_object_dead)
                self._weak_refs[obj_id] = ref
            except TypeError:
                pass

    def _is_valid(self, func: Callable, obj_id: int) -> bool:
        """检查缓存键对应的对象是否仍然有效。

        Args:
            func: 当前函数对象（用于验证）。
            obj_id: 缓存键（id）。

        Returns:
            True 如果缓存有效，False 如果已失效。
        """
        if obj_id not in self._weak_refs:
            return False
        ref = self._weak_refs[obj_id]
        return ref() is func

    def _cache_get(self, cache: OrderedDict, key: int) -> Any:
        """从 OrderedDict 缓存中获取值并更新 LRU 顺序。

        Args:
            cache: 目标缓存字典。
            key: 缓存键。

        Returns:
            缓存的值。

        Raises:
            KeyError: 如果键不存在。
        """
        value = cache[key]
        cache.move_to_end(key)
        self._hits += 1
        return value

    def _cache_set(self, cache: OrderedDict, key: int, value: Any) -> None:
        """设置缓存值，超过上限时淘汰最久未使用的条目。

        Args:
            cache: 目标缓存字典。
            key: 缓存键。
            value: 要缓存的值。
        """
        cache[key] = value
        cache.move_to_end(key)
        while len(cache) > self.max_size:
            evicted_key, _ = cache.popitem(last=False)
            log.debug("LRU 淘汰 [%s]: key=%s", self.lang, evicted_key)

    # ------------------------------------------------------------------
    # 签名缓存
    # ------------------------------------------------------------------

    def get_signature(self, func: Callable[..., Any]) -> inspect.Signature:
        """获取函数签名（带 LRU 缓存）。

        Args:
            func: 目标函数或可调用对象。

        Returns:
            inspect.Signature 对象。
        """
        key = id(func)
        if key in self._sig_cache and self._is_valid(func, key):
            return self._cache_get(self._sig_cache, key)
        self._misses += 1
        self._register_weakref(func)
        sig = inspect.signature(func)
        self._cache_set(self._sig_cache, key, sig)
        return sig

    def has_signature(self, func: Callable[..., Any]) -> bool:
        """检查函数签名是否已缓存。

        Args:
            func: 目标函数或可调用对象。

        Returns:
            True 如果已缓存，否则 False。
        """
        key = id(func)
        return key in self._sig_cache and self._is_valid(func, key)

    # ------------------------------------------------------------------
    # 类型注解缓存
    # ------------------------------------------------------------------

    def get_annotations(self, func: Callable[..., Any]) -> Dict[str, Any]:
        """获取函数类型注解（带 LRU 缓存）。

        优先使用 typing.get_type_hints，失败时回退到 __annotations__。

        Args:
            func: 目标函数或可调用对象。

        Returns:
            类型注解字典。
        """
        from typing import get_type_hints

        key = id(func)
        if key in self._annotations_cache and self._is_valid(func, key):
            return self._cache_get(self._annotations_cache, key)
        self._misses += 1
        self._register_weakref(func)
        try:
            annotations = get_type_hints(func)
        except Exception:
            annotations = getattr(func, '__annotations__', {}) or {}
        self._cache_set(self._annotations_cache, key, annotations)
        return annotations

    def has_annotations(self, func: Callable[..., Any]) -> bool:
        """检查函数类型注解是否已缓存。

        Args:
            func: 目标函数或可调用对象。

        Returns:
            True 如果已缓存，否则 False。
        """
        key = id(func)
        return key in self._annotations_cache and self._is_valid(func, key)

    # ------------------------------------------------------------------
    # 函数体缓存
    # ------------------------------------------------------------------

    def get_body(self, func: Callable[..., Any], args: tuple = (), kwargs: Optional[Dict[str, Any]] = None) -> str:
        """获取函数体代码字符串（带 LRU 缓存）。

        注意：body 缓存的 key 包含 args/kwargs 的哈希，因为不同参数
        可能导致函数返回不同的 body 字符串。

        Args:
            func: 目标函数或可调用对象。
            args: 位置参数元组。
            kwargs: 关键字参数字典。

        Returns:
            函数体代码字符串。
        """
        if kwargs is None:
            kwargs = {}

        cache_key = (id(func), _hash_args(args, kwargs))

        if cache_key in self._body_cache and self._is_valid(func, id(func)):
            return self._cache_get(self._body_cache, cache_key)
        self._misses += 1
        self._register_weakref(func)
        body = _extract_body(func, args, kwargs)
        self._cache_set(self._body_cache, cache_key, body)
        return body

    def has_body(self, func: Callable[..., Any], args: tuple = (), kwargs: Optional[Dict[str, Any]] = None) -> bool:
        """检查函数体是否已缓存。

        Args:
            func: 目标函数或可调用对象。
            args: 位置参数元组。
            kwargs: 关键字参数字典。

        Returns:
            True 如果已缓存，否则 False。
        """
        if kwargs is None:
            kwargs = {}
        cache_key = (id(func), _hash_args(args, kwargs))
        return cache_key in self._body_cache and self._is_valid(func, id(func))

    # ------------------------------------------------------------------
    # FunctionSpec 缓存
    # ------------------------------------------------------------------

    def get_spec(self, func: Callable[..., Any], args: tuple = (), kwargs: Optional[Dict[str, Any]] = None) -> Any:
        """获取 FunctionSpec 对象（带 LRU 缓存）。

        注意：spec 缓存的 key 包含 args/kwargs 的哈希。

        Args:
            func: 目标函数或可调用对象。
            args: 位置参数元组。
            kwargs: 关键字参数字典。

        Returns:
            FunctionSpec 对象。
        """
        if kwargs is None:
            kwargs = {}

        cache_key = (id(func), _hash_args(args, kwargs))

        if cache_key in self._spec_cache and self._is_valid(func, id(func)):
            return self._cache_get(self._spec_cache, cache_key)
        self._misses += 1
        self._register_weakref(func)
        from .._base import FunctionSpec

        name = func.__name__
        annotations = self.get_annotations(func)
        sig = self.get_signature(func)

        defaults = {}
        for param_name, param in sig.parameters.items():
            if param.default is not inspect.Parameter.empty:
                defaults[param_name] = param.default

        body = self.get_body(func, args, kwargs)

        spec = FunctionSpec(
            name=name,
            annotations=annotations,
            args=args,
            defaults=defaults,
            body=body,
        )
        self._cache_set(self._spec_cache, cache_key, spec)
        return spec

    def has_spec(self, func: Callable[..., Any], args: tuple = (), kwargs: Optional[Dict[str, Any]] = None) -> bool:
        """检查 FunctionSpec 是否已缓存。

        Args:
            func: 目标函数或可调用对象。
            args: 位置参数元组。
            kwargs: 关键字参数字典。

        Returns:
            True 如果已缓存，否则 False。
        """
        if kwargs is None:
            kwargs = {}
        cache_key = (id(func), _hash_args(args, kwargs))
        return cache_key in self._spec_cache and self._is_valid(func, id(func))

    # ------------------------------------------------------------------
    # 缓存管理
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """清空该语言实例的所有缓存。"""
        self._sig_cache.clear()
        self._annotations_cache.clear()
        self._body_cache.clear()
        self._spec_cache.clear()
        self._hits = 0
        self._misses = 0

    def cache_info(self) -> Dict[str, Any]:
        """返回缓存统计信息。

        Returns:
            包含缓存统计信息的字典。
        """
        total = self._hits + self._misses
        return {
            "lang": self.lang,
            "max_size": self.max_size,
            "sig_size": len(self._sig_cache),
            "annotations_size": len(self._annotations_cache),
            "body_size": len(self._body_cache),
            "spec_size": len(self._spec_cache),
            "hits": self._hits,
            "misses": self._misses,
            "hit_ratio": self._hits / total if total > 0 else 0.0,
        }


# ====================================================================
# 全局缓存注册表
# ====================================================================

_language_caches: Dict[str, BridgeSigCache] = {}
"""按语言名称注册的缓存实例字典。"""


def get_language_cache(lang: str, max_size: int = _MAX_CACHE_SIZE) -> BridgeSigCache:
    """获取指定语言的缓存实例，不存在则创建。

    Args:
        lang: 语言名称。
        max_size: 缓存最大条目数（仅新建时生效）。

    Returns:
        BridgeSigCache 实例。
    """
    if lang not in _language_caches:
        _language_caches[lang] = BridgeSigCache(lang=lang, max_size=max_size)
    return _language_caches[lang]


def clear_language_cache(lang: str) -> bool:
    """清空指定语言的缓存。

    Args:
        lang: 语言名称。

    Returns:
        True 如果缓存存在并被清空，False 如果不存在。
    """
    if lang in _language_caches:
        _language_caches[lang].clear()
        return True
    return False


def clear_all_caches() -> None:
    """清空所有语言的缓存。"""
    for cache in _language_caches.values():
        cache.clear()


def all_cache_info() -> Dict[str, Dict[str, Any]]:
    """获取所有语言缓存的统计信息。

    Returns:
        语言名 -> 统计信息 的字典。
    """
    return {lang: cache.cache_info() for lang, cache in _language_caches.items()}


# ====================================================================
# 便捷函数（使用默认命名空间）
# ====================================================================

_default_cache: Optional[BridgeSigCache] = None


def _get_default_cache() -> BridgeSigCache:
    """获取默认缓存实例。"""
    global _default_cache
    if _default_cache is None:
        _default_cache = BridgeSigCache(lang="default")
    return _default_cache


def get_cached_signature(func: Callable[..., Any]) -> inspect.Signature:
    """便捷函数：获取函数签名（使用默认缓存）。

    Args:
        func: 目标函数或可调用对象。

    Returns:
        inspect.Signature 对象。
    """
    return _get_default_cache().get_signature(func)


def get_cached_annotations(func: Callable[..., Any]) -> Dict[str, Any]:
    """便捷函数：获取函数类型注解（使用默认缓存）。

    Args:
        func: 目标函数或可调用对象。

    Returns:
        类型注解字典。
    """
    return _get_default_cache().get_annotations(func)


def get_cached_body(func: Callable[..., Any], args: tuple = (), kwargs: Optional[Dict[str, Any]] = None) -> str:
    """便捷函数：获取函数体代码字符串（使用默认缓存）。

    Args:
        func: 目标函数或可调用对象。
        args: 位置参数元组。
        kwargs: 关键字参数字典。

    Returns:
        函数体代码字符串。
    """
    return _get_default_cache().get_body(func, args, kwargs)


def get_cached_spec(func: Callable[..., Any], args: tuple = (), kwargs: Optional[Dict[str, Any]] = None) -> Any:
    """便捷函数：获取 FunctionSpec 对象（使用默认缓存）。

    Args:
        func: 目标函数或可调用对象。
        args: 位置参数元组。
        kwargs: 关键字参数字典。

    Returns:
        FunctionSpec 对象。
    """
    return _get_default_cache().get_spec(func, args, kwargs)


def clear_cache() -> None:
    """便捷函数：清空默认缓存。"""
    _get_default_cache().clear()


def cache_info() -> Dict[str, Any]:
    """便捷函数：获取默认缓存统计信息。

    Returns:
        缓存统计信息字典。
    """
    return _get_default_cache().cache_info()


# ====================================================================
# 内部工具函数
# ====================================================================

def _hash_args(args: tuple, kwargs: Dict[str, Any]) -> int:
    """计算参数的哈希值，用于缓存键。

    注意：对于不可哈希的参数，会降级为使用 repr() 的哈希。

    Args:
        args: 位置参数元组。
        kwargs: 关键字参数字典。

    Returns:
        哈希值。
    """
    try:
        return hash((args, tuple(sorted(kwargs.items()))))
    except TypeError:
        return hash((repr(args), repr(sorted(kwargs.items()))))


def _extract_body(func: Callable[..., Any], args: tuple, kwargs: Dict[str, Any]) -> str:
    """提取函数体代码字符串。

    按以下优先级尝试获取函数体：
    1. 使用 args/kwargs 调用函数获取返回值
    2. 无参调用函数获取返回值
    3. 使用 AST 解析源代码，提取 return 语句后的字符串
    4. 读取函数的 __body__ 属性
    5. 读取函数的 docstring

    Args:
        func: 目标函数对象。
        args: 位置参数元组。
        kwargs: 关键字参数字典。

    Returns:
        提取到的函数体代码字符串，提取失败返回空字符串。
    """
    try:
        result = func(*args, **kwargs)
        if result is not None:
            return str(result)
    except TypeError:
        pass
    except Exception:
        pass

    try:
        result = func()
        if result is not None:
            return str(result)
    except TypeError:
        pass
    except Exception:
        pass

    try:
        import ast
        import textwrap
        source = inspect.getsource(func)
        source = textwrap.dedent(source)
        tree = ast.parse(source)
        func_def = None
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_def = node
                break
        if func_def:
            for node in ast.walk(func_def):
                if isinstance(node, ast.Return):
                    if isinstance(node.value, ast.Constant):
                        return str(node.value.value)
                    elif isinstance(node.value, ast.JoinedStr):
                        parts = []
                        for v in node.value.values:
                            if isinstance(v, ast.Constant):
                                parts.append(str(v.value))
                        return ''.join(parts)
    except Exception:
        pass

    body = getattr(func, '__body__', '')
    if body:
        return body

    if func.__doc__:
        return func.__doc__

    return ''


__all__ = [
    'BridgeSigCache',
    'get_language_cache',
    'clear_language_cache',
    'clear_all_caches',
    'all_cache_info',
    'get_cached_signature',
    'get_cached_annotations',
    'get_cached_body',
    'get_cached_spec',
    'clear_cache',
    'cache_info',
]
