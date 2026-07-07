"""
vools.decorators.bridge_decorator - @bridge 装饰器实现

提供跨语言桥接装饰器，支持在桥接库可用时调用高性能实现，
不可用时自动回退到纯 Python 实现。

支持的符号格式：
  - "lang.module.func"（dot格式）：从桥接库加载 module.func
  - "lang:func"（colon格式）：从桥接库加载 func
"""

import functools
import logging
import threading
from typing import Callable, Optional, Any

__all__ = ['bridge', 'BridgeRegistry']

# 日志记录器
_logger = logging.getLogger(__name__)


class BridgeRegistry:
    """
    桥接库注册表，管理所有语言的桥接库加载
    
    使用单例模式，确保每个语言只加载一次共享库。
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._loaders = {}  # language -> loader instance
        self._libs = {}  # (language, lib_name) -> loaded library
        self._lib_lock = threading.Lock()
    
    def _get_loader(self, language: str):
        """获取指定语言的加载器"""
        if language not in self._loaders:
            from ..bridge.core.loader import get_loader
            self._loaders[language] = get_loader(language)
        return self._loaders[language]
    
    def is_available(self, language: str) -> bool:
        """
        检查指定语言的桥接库是否可用
        
        Args:
            language: 语言名称（如 "nim", "rust", "go" 等）
            
        Returns:
            bool: 桥接库是否可用
        """
        from ..bridge.core.loader import is_available as core_is_available
        return core_is_available(language)
    
    def get_lib(self, language: str, lib_name: str = None):
        """
        获取指定语言的共享库
        
        Args:
            language: 语言名称
            lib_name: 库名称（可选，部分语言不需要）
            
        Returns:
            ctypes.CDLL 或 None: 加载的共享库
        """
        from ..bridge.core.loader import load_library
        
        cache_key = (language, lib_name)
        
        with self._lib_lock:
            if cache_key in self._libs:
                return self._libs[cache_key]
            
            lib = load_library(language, lib_name)
            self._libs[cache_key] = lib
            return lib
    
    def load_symbol(self, language: str, symbol_path: str) -> Optional[Any]:
        """
        从桥接库加载符号
        
        Args:
            language: 语言名称
            symbol_path: 符号路径，支持两种格式：
                - "module.func"（dot格式）
                - "func"（直接函数名，与 colon 格式配合使用）
                
        Returns:
            加载的函数对象，或 None
        """
        # 先检查语言是否可用
        if not self.is_available(language):
            return None
        
        # 确定库名和函数路径
        # 对于大多数语言，lib_name 为 None 表示使用默认库
        lib = self.get_lib(language, None)
        if lib is None:
            return None
        
        # 解析符号路径
        # symbol_path 可以是 "module.func" 或直接是 "func"
        func = None
        try:
            if '.' in symbol_path:
                # dot 格式：module.func，需要逐级访问
                parts = symbol_path.split('.')
                current = lib
                for part in parts:
                    current = getattr(current, part)
                func = current
            else:
                # 直接函数名
                func = getattr(lib, symbol_path)
        except AttributeError:
            return None
        
        return func


# 全局注册表实例
_registry = None


def _get_registry() -> BridgeRegistry:
    """获取桥接库注册表单例"""
    global _registry
    if _registry is None:
        _registry = BridgeRegistry()
    return _registry


def _parse_symbol(lang: str, symbol: str) -> tuple:
    """
    解析符号字符串
    
    支持的格式：
      - "module.func" -> (lang, "module.func")
      - "lang.module.func" -> (lang, "module.func")  # lang 被忽略，使用参数中的 lang
    
    Args:
        lang: 语言名称（来自装饰器参数）
        symbol: 符号字符串
        
    Returns:
        tuple: (language, symbol_path)
    """
    # symbol 格式：
    # 1. "lang.module.func" - lang 前缀，可以有也可以没有
    # 2. "module.func" - 只有模块路径
    # 3. "lang:func" - 使用 colon 分隔，lang 来自参数
    # 4. "func" - 直接函数名
    
    if ':' in symbol:
        # colon 格式：可能是 "lang:func" 或 ":func" 或 "func:with:colons"
        parts = symbol.split(':', 1)
        if parts[0]:
            # "lang:func" 格式，lang 来自 symbol
            return parts[0], parts[1]
        else:
            # ":func" 格式，lang 来自参数
            return lang, parts[1]
    else:
        # dot 格式或直接函数名
        return lang, symbol


def bridge(lang: str, symbol: str, fallback: Optional[Callable] = None):
    """
    桥接装饰器
    
    当桥接库可用时，调用桥接函数；否则调用 fallback。
    如果桥接函数抛出异常，也会回退到 fallback。
    
    Args:
        lang: 桥接库语言，如 "nim", "rust", "go", "scala", "powershell", "shell"
        symbol: 桥接库中的符号名，支持两种格式：
            - "module.func"（dot格式）：从桥接库加载 module.func
            - "lang:func"（colon格式）：lang 被忽略，使用参数中的 lang，加载 func
        fallback: 回退函数，桥接库不可用或出错时调用
        
    Returns:
        装饰后的函数
        
    用法示例：
        @bridge("nim", "serialize.pickle_encode", fallback=pickle_encode_py)
        def pickle_encode(obj, protocol=pickle.HIGHEST_PROTOCOL):
            '''序列化对象为字节串。如果桥接库可用则使用高性能实现。'''
            return pickle.dumps(obj, protocol=protocol)
        
        # colon 格式
        @bridge("nim", ":pickle_encode", fallback=pickle_encode_py)
        def pickle_encode(obj):
            pass
    """
    def decorator(func: Callable) -> Callable:
        # 解析符号，确定语言和路径
        actual_lang, symbol_path = _parse_symbol(lang, symbol)
        
        # 用于缓存已解析的函数
        _cached_bridge_func = None
        _bridge_func_lock = threading.Lock()
        
        def _get_bridge_func():
            """获取桥接函数（延迟加载，线程安全）"""
            nonlocal _cached_bridge_func
            
            if _cached_bridge_func is not None:
                return _cached_bridge_func
            
            with _bridge_func_lock:
                if _cached_bridge_func is not None:
                    return _cached_bridge_func
                
                registry = _get_registry()
                _cached_bridge_func = registry.load_symbol(actual_lang, symbol_path)
                return _cached_bridge_func
        
        def _log_warning(msg: str):
            """记录警告日志"""
            _logger.warning(msg)
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 尝试获取桥接函数
            bridge_func = _get_bridge_func()
            
            # 路径1：桥接库可用，调用桥接函数
            if bridge_func is not None:
                try:
                    return bridge_func(*args, **kwargs)
                except Exception as e:
                    # 路径3：桥接函数抛出异常，记录 warning，回退 fallback
                    _log_warning(
                        "Bridge function '%s.%s' raised %s: %s, falling back to Python implementation" % (
                            actual_lang, symbol_path, type(e).__name__, str(e)
                        )
                    )
                    if fallback is not None:
                        return fallback(*args, **kwargs)
                    raise
            
            # 路径2：桥接库不可用，调用 fallback
            if fallback is not None:
                return fallback(*args, **kwargs)
            
            # 没有 fallback，抛出 RuntimeError
            raise RuntimeError(
                "No bridge implementation available for '%s' (language: %s, symbol: %s)" % (
                    func.__name__, actual_lang, symbol_path
                )
            )
        
        # 添加一些有用的属性
        wrapper._bridge_lang = actual_lang
        wrapper._bridge_symbol = symbol_path
        wrapper._bridge_fallback = fallback
        wrapper._is_bridge_func = True
        
        return wrapper
    
    return decorator
