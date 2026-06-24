"""
vools.bridge.core - 桥接核心基础设施

包含共享库加载器、类型映射、装饰器、序列化层和签名缓存。
"""

from .loader import (
    LibraryLoader,
    SharedLibrary,
    load_library,
    load_from_path,
    is_available,
)
from .types import (
    CTypeMapper,
    PY_TO_CTYPES,
    infer_arg_types,
    infer_ret_type,
    convert_args,
)
from .decorators import bridge_function, bridge_module, bridge_func_name
from .serialization import Serializer
from .sigcache import (
    BridgeSigCache,
    get_language_cache,
    clear_language_cache,
    clear_all_caches,
    all_cache_info,
    get_cached_signature,
    get_cached_annotations,
    get_cached_body,
    get_cached_spec,
    clear_cache,
    cache_info,
)

__all__ = [
    'LibraryLoader',
    'SharedLibrary',
    'load_library',
    'load_from_path',
    'is_available',
    'CTypeMapper',
    'PY_TO_CTYPES',
    'infer_arg_types',
    'infer_ret_type',
    'convert_args',
    'bridge_function',
    'bridge_module',
    'bridge_func_name',
    'Serializer',
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
