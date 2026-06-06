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
- cache_with_ttl: 带过期时间的缓存装饰器
- hybrid_method: 混合方法装饰器
- classproperty: 类属性装饰器
- enumize: 枚举装饰器
"""

__all__ = [
    'timeit', 'safe', 'throttle', 'debounce', 'singleton', 'deprecated',
    'conditional', 'with_context', 'with_timeout', 'validate', 'rate_limit',
    'cache_with_ttl', 'hybrid_method', 'classproperty', 'enumize'
]

import functools
import inspect
import threading
import time
import warnings
from typing import Any, Callable, Optional, Tuple, TypeVar, Union

T = TypeVar('T')
R = TypeVar('R')


def timeit(func: Callable[..., T] = None, *, logger: Optional[Any] = None) -> Callable[..., T]:
    """计时装饰器

    Args:
        func: 被装饰的函数
        logger: 可选的日志记录器

    Returns:
        装饰后的函数或装饰器
    """
    def decorator(f: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(f)
        def wrapper(*args, **kwargs) -> T:
            start_time = time.perf_counter()
            try:
                result = f(*args, **kwargs)
            finally:
                end_time = time.perf_counter()
                elapsed = end_time - start_time
                if logger:
                    logger.info(f"{f.__name__} 执行时间: {elapsed:.4f}秒")
                else:
                    print(f"{f.__name__} 执行时间: {elapsed:.4f}秒")
            return result
        return wrapper

    if func is None:
        return decorator
    else:
        return decorator(func)


def safe(func: Callable[..., T] = None, *, default: Any = None, exceptions: Tuple[type, ...] = (Exception,)) -> Callable[..., T]:
    """安全执行装饰器

    Args:
        func: 被装饰的函数
        default: 执行失败时返回的默认值
        exceptions: 要捕获的异常类型元组

    Returns:
        装饰后的函数或装饰器
    """
    def decorator(f: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(f)
        def wrapper(*args, **kwargs) -> T:
            try:
                return f(*args, **kwargs)
            except exceptions as e:
                if default is not None:
                    return default
                return None, e
        return wrapper

    if func is None:
        return decorator
    else:
        return decorator(func)


def throttle(interval: float):
    """节流装饰器

    Args:
        interval: 最小调用间隔（秒）

    Returns:
        装饰器函数
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        last_call_time = {}
        lock = threading.Lock()

        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            with lock:
                key = id(func)
                current_time = time.time()
                if key in last_call_time and current_time - last_call_time[key] < interval:
                    return None
                last_call_time[key] = current_time

            return func(*args, **kwargs)
        return wrapper
    return decorator


def debounce(wait: float):
    """防抖装饰器

    Args:
        wait: 等待时间（秒）

    Returns:
        装饰器函数
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        timer = {}
        lock = threading.Lock()

        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            with lock:
                key = id(func)
                if key in timer:
                    timer[key].cancel()

                new_timer = threading.Timer(wait, lambda: func(*args, **kwargs))
                timer[key] = new_timer
                new_timer.start()
        return wrapper
    return decorator


def singleton(cls):
    """单例模式装饰器"""
    instances = {}
    lock = threading.Lock()

    @functools.wraps(cls)
    def get_instance(*args, **kwargs):
        with lock:
            if cls not in instances:
                instances[cls] = cls(*args, **kwargs)
        return instances[cls]
    return get_instance


def deprecated(reason: str = None):
    """弃用警告装饰器

    Args:
        reason: 弃用原因

    Returns:
        装饰器函数
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            warning_msg = f"{func.__name__} 已弃用"
            if reason:
                warning_msg += f": {reason}"
            warnings.warn(warning_msg, DeprecationWarning, stacklevel=2)
            return func(*args, **kwargs)
        return wrapper
    return decorator


def conditional(condition: Callable[..., bool], action: str = 'skip'):
    """条件执行装饰器

    Args:
        condition: 返回bool的函数
        action: 条件为True时的动作，'skip'跳过执行，'warn'发出警告

    Returns:
        装饰器函数
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            if condition(*args, **kwargs):
                if action == 'skip':
                    return None
                elif action == 'warn':
                    warnings.warn(f"{func.__name__} 的条件已满足，跳过执行")
            return func(*args, **kwargs)
        return wrapper
    return decorator


def with_context(context_manager):
    """上下文管理器装饰器

    Args:
        context_manager: 上下文管理器

    Returns:
        装饰器函数
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            with context_manager:
                return func(*args, **kwargs)
        return wrapper
    return decorator


def with_timeout(timeout: float):
    """超时装饰器

    Args:
        timeout: 超时时间（秒）

    Returns:
        装饰器函数
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            result = [None]
            exception = [None]

            def target():
                try:
                    result[0] = func(*args, **kwargs)
                except Exception as e:
                    exception[0] = e

            thread = threading.Thread(target=target)
            thread.daemon = True
            thread.start()
            thread.join(timeout)

            if thread.is_alive():
                raise TimeoutError(f"{func.__name__} 执行超时（{timeout}秒）")

            if exception[0]:
                raise exception[0]

            return result[0]
        return wrapper
    return decorator


def validate(**validators):
    """参数验证装饰器

    Args:
        **validators: 参数名到验证函数的映射

    Returns:
        装饰器函数
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            sig = inspect.signature(func)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()

            for param_name, validator in validators.items():
                if param_name in bound.arguments:
                    if not validator(bound.arguments[param_name]):
                        raise ValueError(f"参数 {param_name} 验证失败")
            return func(*args, **kwargs)
        return wrapper
    return decorator


def rate_limit(max_calls: int, period: float, logic: str = 'or', logger: Optional[Any] = None) -> Callable:
    """速率限制装饰器

    Args:
        max_calls: 最大调用次数
        period: 时间段（秒）
        logic: 'or' 任意条件触发限制，'and' 所有条件同时触发限制
        logger: 可选的日志记录器

    Returns:
        装饰器函数
    """
    calls = []
    lock = threading.Lock()

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            now = time.time()

            with lock:
                nonlocal calls
                calls = [t for t in calls if now - t < period]

                if len(calls) >= max_calls:
                    if logger:
                        logger.warning(f"{func.__name__} 超过速率限制")
                    else:
                        print(f"{func.__name__} 超过速率限制")
                    return None

                calls.append(now)

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
    """带过期时间的缓存装饰器（线程安全）

    Args:
        ttl: 缓存过期时间（秒）

    Returns:
        装饰器函数
    """
    def decorator(func: Callable[..., R]) -> Callable[..., R]:
        cache = {}
        lock = threading.Lock()

        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> R:
            key = str(args) + str(kwargs)
            now = time.time()

            with lock:
                expired_keys = [k for k, (_, timestamp) in list(cache.items()) if now - timestamp > ttl]
                for k in expired_keys:
                    del cache[k]

                if key not in cache:
                    pass
                else:
                    result, _ = cache[key]
                    return result

            result = func(*args, **kwargs)

            with lock:
                cache[key] = (result, now)

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
    @functools.wraps(func)
    def wrapper(cls):
        return func(cls)
    return property(wrapper)


def enumize(*values):
    """枚举装饰器

    Args:
        *values: 枚举值列表

    Returns:
        装饰器函数
    """
    def decorator(cls):
        for i, value in enumerate(values):
            setattr(cls, value.upper(), i)
        cls._values = values
        return cls
    return decorator