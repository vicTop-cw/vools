"""
快捷工具装饰器

提供各种实用的快捷装饰器和工具函数：
- timeit: 计时装饰器
- safe: 安全执行装饰器
- throttle: 节流装饰器
- debounce: 防抖装饰器
- singleton: 单例装饰器
- deprecated: 弃用警告装饰器
- conditional: 条件执行装饰器
- with_context: 上下文管理器装饰器
- with_timeout: 超时装饰器
- validate: 参数验证装饰器
- rate_limit: 速率限制装饰器
- log_calls: 调用日志装饰器
- cache_with_ttl: 带过期时间的缓存装饰器
- hybrid_method: 混合方法装饰器
- classproperty: 类属性装饰器
- enumize: 枚举装饰器
"""

import functools
import inspect
import threading
import time
import warnings
from typing import Any, Callable, Optional, Tuple, TypeVar, Union

T = TypeVar('T')
R = TypeVar('R')

__all__ = [
    'timeit',
    'safe',
    'throttle',
    'debounce',
    'singleton',
    'deprecated',
    'conditional',
    'with_context',
    'with_timeout',
    'validate',
    'rate_limit',
    'log_calls',
    'cache_with_ttl',
    'hybrid_method',
    'classproperty',
    'enumize',
]


def timeit(func: Callable[..., R]) -> Callable[..., Tuple[R, float]]:
    """计时装饰器"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Tuple[R, float]:
        start = time.time()
        result = func(*args, **kwargs)
        end = time.time()
        return result, end - start
    return wrapper


def safe(func: Callable[..., R]) -> Callable[..., Tuple[Optional[R], Optional[Exception]]]:
    """安全执行函数，返回结果和异常"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Tuple[Optional[R], Optional[Exception]]:
        try:
            result = func(*args, **kwargs)
            return result, None
        except Exception as e:
            return None, e
    return wrapper


def throttle(interval: float) -> Callable[[Callable[..., R]], Callable[..., Optional[R]]]:
    """节流装饰器"""
    def decorator(func: Callable[..., R]) -> Callable[..., Optional[R]]:
        last_called = 0
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Optional[R]:
            nonlocal last_called
            now = time.time()
            if now - last_called >= interval:
                last_called = now
                return func(*args, **kwargs)
            return None
        
        return wrapper
    return decorator


def debounce(interval: float) -> Callable[[Callable[..., R]], Callable[..., R]]:
    """防抖装饰器"""
    def decorator(func: Callable[..., R]) -> Callable[..., R]:
        timer = None
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> R:
            nonlocal timer
            if timer:
                timer.cancel()
            
            def delayed():
                func(*args, **kwargs)
            
            timer = threading.Timer(interval, delayed)
            timer.start()
        
        return wrapper
    return decorator


def singleton(cls):
    """单例装饰器"""
    instances = {}
    
    @functools.wraps(cls)
    def get_instance(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]
    
    return get_instance


def deprecated(message: str = "该函数已被弃用"):
    """弃用警告装饰器"""
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            warnings.warn(message, DeprecationWarning, stacklevel=2)
            return func(*args, **kwargs)
        return wrapper
    return decorator


def conditional(condition: Callable[[], bool]) -> Callable[[Callable[..., R]], Callable[..., Optional[R]]]:
    """条件执行装饰器"""
    def decorator(func: Callable[..., R]) -> Callable[..., Optional[R]]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Optional[R]:
            if condition():
                return func(*args, **kwargs)
            return None
        return wrapper
    return decorator


def with_context(context_manager):
    """上下文管理器装饰器"""
    def decorator(func: Callable[..., R]) -> Callable[..., R]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> R:
            with context_manager:
                return func(*args, **kwargs)
        return wrapper
    return decorator


def with_timeout(seconds: float):
    """超时装饰器"""
    def decorator(func: Callable[..., R]) -> Callable[..., R]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> R:
            result = None
            exception = None
            
            def target():
                nonlocal result, exception
                try:
                    result = func(*args, **kwargs)
                except Exception as e:
                    exception = e
            
            thread = threading.Thread(target=target)
            thread.daemon = True
            thread.start()
            thread.join(seconds)
            
            if thread.is_alive():
                raise TimeoutError(f"函数执行超时（{seconds}秒）")
            if exception:
                raise exception
            return result
        return wrapper
    return decorator


def validate(*validators: Callable[[Any], bool]):
    """参数验证装饰器"""
    def decorator(func: Callable[..., R]) -> Callable[..., R]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for i, (arg, validator) in enumerate(zip(args, validators)):
                if not validator(arg):
                    raise ValueError(f"参数 {i} 验证失败")
            return func(*args, **kwargs)
        return wrapper
    return decorator


def rate_limit(max_calls: int, period: float):
    """速率限制装饰器"""
    def decorator(func: Callable[..., R]) -> Callable[..., R]:
        calls = []
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> R:
            nonlocal calls
            now = time.time()
            calls = [t for t in calls if now - t < period]
            if len(calls) >= max_calls:
                raise ValueError(f"速率限制：{max_calls}次/({period}秒)")
            calls.append(now)
            return func(*args, **kwargs)
        
        return wrapper
    return decorator


def log_calls(logger=None):
    """调用日志装饰器"""
    def decorator(func: Callable[..., R]) -> Callable[..., R]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> R:
            if logger:
                logger.info(f"调用 {func.__name__}，参数: {args}, {kwargs}")
            else:
                print(f"调用 {func.__name__}，参数: {args}, {kwargs}")
            result = func(*args, **kwargs)
            if logger:
                logger.info(f"{func.__name__} 返回: {result}")
            else:
                print(f"{func.__name__} 返回: {result}")
            return result
        return wrapper
    return decorator


def cache_with_ttl(ttl: float):
    """带过期时间的缓存装饰器"""
    def decorator(func: Callable[..., R]) -> Callable[..., R]:
        cache = {}
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> R:
            nonlocal cache
            key = str(args) + str(kwargs)
            now = time.time()
            
            expired_keys = [k for k, (_, timestamp) in cache.items() if now - timestamp > ttl]
            for k in expired_keys:
                del cache[k]
            
            if key not in cache:
                result = func(*args, **kwargs)
                cache[key] = (result, now)
            else:
                result, _ = cache[key]
            
            return result
        
        return wrapper
    return decorator


def hybrid_method(func):
    """混合方法装饰器，可同时作为类方法和实例方法使用"""
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        if isinstance(self, type):
            return func(self, *args, **kwargs)
        else:
            return func(self.__class__, self, *args, **kwargs)
    return wrapper


def classproperty(func):
    """类属性装饰器"""
    return property(classmethod(func))


def enumize(enum_class):
    """枚举装饰器，将类转换为枚举"""
    import enum
    return enum.Enum(enum_class.__name__, [(attr, getattr(enum_class, attr)) for attr in dir(enum_class) if not attr.startswith('_')])