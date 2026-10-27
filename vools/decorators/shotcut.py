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
from ..cache.sigcache import get_signature
import time
import warnings
from typing import Any, Callable, Optional, Tuple, TypeVar, Union

T = TypeVar('T')
R = TypeVar('R')

_MISSING = object()
"""sentinel：区分"未传 default"与"显式传 default=None"（BUG-116）"""


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


def safe(func: Callable[..., T] = None, *, default: Any = _MISSING, exceptions: Tuple[type, ...] = (Exception,)) -> Callable[..., T]:
    """安全执行装饰器

    Args:
        func: 被装饰的函数
        default: 执行失败时返回的默认值。显式传 ``default=None`` 时异常返回 None；
            未传时返回 ``(None, exception)`` 元组（BUG-116）。
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
                if default is _MISSING:
                    return None, e
                return default
        return wrapper

    # BUG-524: safe(123) 会把非可调用对象当函数包起来，调用期才炸
    # "'int' object is not callable"（装饰期毫无提示）。
    if func is not None and not callable(func):
        raise TypeError(
            f"safe() 的 func 必须可调用或 None，收到 {type(func).__name__}: {func!r}")
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
    if callable(interval) and not isinstance(interval, (int, float, str)):
        # BUG-373: 裸用 @throttle 时被装饰函数会落到 interval 参数上，返回的
        # 装饰器替换掉原函数，直到调用才报 "decorator() missing 1 required
        # positional argument"。这里在装饰期就给出可执行提示。
        raise TypeError(
            f"裸用 @throttle 无效：interval 需要显式传参，请写 @throttle(interval=秒数)"
            f"（收到 {type(interval).__name__}: {getattr(interval, '__name__', interval)!r}）")

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


def _require_duration(value, what: str, *, allow_zero: bool) -> None:
    """校验时间参数是合法数值（BUG-473）。

    原实现只拦住"裸用装饰器"（BUG-373），``debounce(wait=-1)`` /
    ``cache_with_ttl(ttl='x')`` 仍静默通过：前者让 Timer 立即触发放大调用，
    后者的 ``now - ts > ttl`` 直到**调用时**才抛
    ``'>' not supported between instances of 'float' and 'str'``。
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(
            f"{what} 必须是数值，收到 {type(value).__name__}: {value!r}")
    if allow_zero:
        if value < 0:
            raise ValueError(f"{what} 不能为负，收到 {value!r}")
    elif value <= 0:
        raise ValueError(f"{what} 必须为正数，收到 {value!r}")


def debounce(wait: float):
    """防抖装饰器

    Args:
        wait: 等待时间（秒）

    Returns:
        装饰器函数
    """
    if callable(wait) and not isinstance(wait, (int, float, str)):
        # BUG-373: 裸用 @debounce 时被装饰函数会落到 wait 参数上，返回的
        # 装饰器替换掉原函数，直到调用才报 "decorator() missing 1 required
        # positional argument"。这里在装饰期就给出可执行提示。
        raise TypeError(
            f"裸用 @debounce 无效：wait 需要显式传参，请写 @debounce(wait=秒数)"
            f"（收到 {type(wait).__name__}: {getattr(wait, '__name__', wait)!r}）")
    # BUG-473: 数值校验（wait 允许 0 = 立即触发，但负值/字符串必须拒绝）
    _require_duration(wait, "debounce() 的 wait", allow_zero=True)

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
    """单例模式装饰器

    BUG-148: 早期实现把 ``cls`` 替换为 ``get_instance`` 函数，导致 ``Foo``
    不再是类型——``isinstance(x, Foo)`` 抛 TypeError，``issubclass`` /
    ``__bases__`` / 类型注解全部失效。改为改写 ``__new__`` / ``__init__``，
    保留原类型；按类缓存实例（子类各自独立单例），只在首次创建时执行
    ``__init__``，后续调用返回同一实例并跳过重复初始化。
    """
    instances = {}
    lock = threading.Lock()
    original_new = cls.__new__
    original_init = cls.__init__

    def _new_singleton(cls_, *args, **kwargs):
        with lock:
            if cls_ not in instances:
                if original_new is object.__new__:
                    instance = object.__new__(cls_)
                else:
                    instance = original_new(cls_, *args, **kwargs)
                original_init(instance, *args, **kwargs)
                instances[cls_] = instance
            return instances[cls_]

    cls.__new__ = staticmethod(_new_singleton)
    cls.__init__ = lambda self, *args, **kwargs: None
    return cls


def deprecated(reason: str = None):
    """弃用警告装饰器

    Args:
        reason: 弃用原因

    Returns:
        装饰器函数
    """
    if callable(reason) and not isinstance(reason, (int, float, str)):
        # BUG-373: 裸用 @deprecated 时被装饰函数会落到 reason 参数上，返回的
        # 装饰器替换掉原函数，直到调用才报 "decorator() missing 1 required
        # positional argument"。这里在装饰期就给出可执行提示。
        raise TypeError(
            f"裸用 @deprecated 无效：reason 需要显式传参，请写 @deprecated() 或 @deprecated(reason=...)"
            f"（收到 {type(reason).__name__}: {getattr(reason, '__name__', reason)!r}）")

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
    # BUG-524: condition 必须可调用、action 只接受 'skip' / 'warn'。原实现
    # 零校验——action='bogus' 时既不跳过也不告警，**静默退化为无条件执行**
    # （装饰器形同不存在）；condition=None/'x' 直到调用期才抛
    # "TypeError: 'NoneType' object is not callable"。
    if not callable(condition):
        raise TypeError(
            f"conditional() 的 condition 必须可调用，收到 "
            f"{type(condition).__name__}: {condition!r}")
    if action not in ('skip', 'warn'):
        raise ValueError(
            f"conditional() 的 action 只支持 'skip' / 'warn'，收到 {action!r}")
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
    if callable(timeout) and not isinstance(timeout, (int, float, str)):
        # BUG-373: 裸用 @with_timeout 时被装饰函数会落到 timeout 参数上，返回的
        # 装饰器替换掉原函数，直到调用才报 "decorator() missing 1 required
        # positional argument"。这里在装饰期就给出可执行提示。
        raise TypeError(
            f"裸用 @with_timeout 无效：timeout 需要显式传参，请写 @with_timeout(timeout=秒数)"
            f"（收到 {type(timeout).__name__}: {getattr(timeout, '__name__', timeout)!r}）")

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
            sig = get_signature(func)
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
        logic: 保留的兼容参数（仅存在单条件判断，本实现无多条件可组合）
        logger: 可选的日志记录器（仅在提供时记录每次调用与返回值）

    Returns:
        装饰器函数

    Note:
        BUG-523: max_calls 必须为正整数、period 必须为正数；未提供 logger 时
        不再打印每次调用的参数/返回值（原实现无条件 print，可能泄露敏感数据）。
        BUG-162: 原实现把 ``calls`` 列表放在 decorator 闭包外层，同一
        ``rate_limit(...)`` 装饰多个函数时配额共享——第一个函数耗尽配额后
        第二个也被拒。现按 ``id(func)`` 分函数独立计数。
    """
    # BUG-523: 参数零校验——
    #   ① period <= 0 时窗口过滤 `now - t < period` 恒为假，调用记录永远为空，
    #     **限流被静默绕过**（配了限流却完全不生效）；
    #   ② max_calls <= 0 会让每次调用都被拒（装饰器把函数变成永久返回 None）；
    #   ③ max_calls='x' 直到调用期才在 `len(calls) >= 'x'` 抛 TypeError。
    if isinstance(max_calls, bool) or not isinstance(max_calls, int):
        raise TypeError(
            f"rate_limit() 的 max_calls 必须是正整数，收到 "
            f"{type(max_calls).__name__}: {max_calls!r}")
    if max_calls <= 0:
        raise ValueError(
            f"rate_limit() 的 max_calls 必须 >= 1（0 会让每次调用都被拒），"
            f"收到 {max_calls!r}")
    _require_duration(period, "rate_limit() 的 period", allow_zero=False)

    calls_by_func = {}
    lock = threading.Lock()

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            now = time.time()
            key = id(func)

            with lock:
                calls = calls_by_func.setdefault(key, [])
                calls = [t for t in calls if now - t < period]
                calls_by_func[key] = calls

                if len(calls) >= max_calls:
                    if logger:
                        logger.warning(f"{func.__name__} 超过速率限制")
                    else:
                        print(f"{func.__name__} 超过速率限制")
                    return None

                calls.append(now)

            # BUG-523: 原实现在**没有 logger 时无条件 print** 每次调用的参数与
            # 返回值——不仅噪音大，还会把敏感实参/结果直接打到 stdout（信息
            # 泄露）。现仅当显式传入 logger 时记录。
            if logger:
                logger.info(f"调用 {func.__name__}，参数: {args}, {kwargs}")
            result = func(*args, **kwargs)
            if logger:
                logger.info(f"{func.__name__} 返回: {result}")
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
    if callable(ttl) and not isinstance(ttl, (int, float, str)):
        # BUG-373: 裸用 @cache_with_ttl 时被装饰函数会落到 ttl 参数上，返回的
        # 装饰器替换掉原函数，直到调用才报 "decorator() missing 1 required
        # positional argument"。这里在装饰期就给出可执行提示。
        raise TypeError(
            f"裸用 @cache_with_ttl 无效：ttl 需要显式传参，请写 @cache_with_ttl(ttl=秒数)"
            f"（收到 {type(ttl).__name__}: {getattr(ttl, '__name__', ttl)!r}）")
    # BUG-473: ttl 必须为正数（ttl<=0 等于永不缓存/立即全失效，属静默错配置）
    _require_duration(ttl, "cache_with_ttl() 的 ttl", allow_zero=False)

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


class _ClassProperty:
    """classproperty 的 descriptor 实现。

    BUG-117: Python 内置 ``property`` 在类访问时返回 property 对象本身（instance is None），
    且实例访问时把实例传给 fget——两者都不符合 classproperty 语义。
    自定义 descriptor 统一在类访问和实例访问时都传 owner（所属类）给 func。
    """
    def __init__(self, func: Callable[..., T]) -> None:
        self.func = func
        functools.update_wrapper(self, func)

    @property
    def fget(self) -> Callable[..., T]:
        """暴露底层函数（对齐 builtins.property.fget，BUG-163）"""
        return self.func

    def __get__(self, instance: Any, owner: Optional[type] = None) -> T:
        if instance is None:
            # 类访问返回 descriptor 本身，可读 .fget/.func（对齐 builtins.property 类访问）
            return self
        return self.func(type(instance))


def classproperty(func):
    """类属性装饰器

    BUG-117: 类访问与实例访问都传 owner（所属类）给 func，而不是 property 对象或实例。
    """
    return _ClassProperty(func)


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