"""
控制流装饰器

包含：
- repeat: 重复执行装饰器
- retry: 重试装饰器
- rerun: 重新运行装饰器
"""

import time
import threading
import logging
from typing import Any, Callable, Iterator, Union, Optional, Type, Tuple, TypeVar
from functools import wraps
import inspect

# ============================================================================
# excepts - 异常处理装饰器
# ============================================================================

def excepts(exc_type: Type[Exception], handler: Callable) -> Callable:
    """
    捕获指定类型的异常并使用处理函数处理

    Args:
        exc_type: 要捕获的异常类型
        handler: 异常处理函数，接收异常并返回替代值

    Returns:
        装饰器

    Example:
        >>> @excepts(ValueError, lambda e: f"错误: {e}")
        ... def risky_operation():
        ...     raise ValueError("测试错误")
        >>> risky_operation()
        '错误: 测试错误'
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except exc_type as e:
                return handler(e)
        return wrapper
    return decorator


# ============================================================================
# silent - 静默异常装饰器
# ============================================================================

def silent(fn: Optional[Callable] = None, *, default: Any = None) -> Callable:
    """
    静默异常，返回默认值

    Args:
        fn: 要装饰的函数
        default: 发生异常时返回的默认值

    Returns:
        装饰器或装饰后的函数

    Example:
        >>> @silent(default="默认值")
        ... def risky():
        ...     raise ValueError("错误")
        >>> risky()
        '默认值'
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception:
                return default
        return wrapper
    
    if fn is None:
        return decorator
    return decorator(fn)


# ============================================================================
# suppress - 抑制异常装饰器
# ============================================================================

def suppress(*args):
    """
    抑制指定类型的异常，不返回任何值。

    支持两种调用方式：
        @suppress              → 抑制所有 Exception
        @suppress(ValueError)  → 抑制指定异常类型

    Args:
        *args: 要抑制的异常类型（为空时默认抑制 Exception）

    Returns:
        装饰器或已装饰函数

    Example:
        >>> @suppress
        ... def risky1():
        ...     raise ValueError("错误")
        >>> risky1() is None
        True
        >>> @suppress(ValueError, TypeError)
        ... def risky2():
        ...     raise ValueError("错误")
        >>> risky2() is None
        True
    """
    # 判断调用方式：@suppress（无括号）→ args[0] 是可调用对象
    if len(args) == 1 and callable(args[0]) and not isinstance(args[0], type):
        # 无括号调用：@suppress
        func = args[0]
        @wraps(func)
        def wrapper(*wargs, **wkwargs):
            try:
                return func(*wargs, **wkwargs)
            except Exception:
                pass
        return wrapper

    # 带参数调用：@suppress(...) 或 @suppress
    exc_types = args if args else (Exception,)

    def decorator(func):
        @wraps(func)
        def wrapper(*wargs, **wkwargs):
            try:
                return func(*wargs, **wkwargs)
            except exc_types:
                pass
        return wrapper
    return decorator


# ============================================================================
# ignore - 忽略返回值装饰器
# ============================================================================

def ignore(*args):
    """
    忽略函数的返回值（始终返回 None）。

    支持两种调用方式：
        @ignore              → 直接装饰
        @ignore(some_arg)   → 带参数装饰（参数暂未使用，保留扩展性）

    Args:
        *args: 可选参数（保留扩展性，当前未使用）

    Returns:
        装饰器或已装饰函数

    Example:
        >>> @ignore
        ... def returns_value():
        ...     return 42
        >>> returns_value() is None
        True
    """
    # 判断调用方式：@ignore（无括号）→ args[0] 是可调用对象
    if len(args) == 1 and callable(args[0]) and not isinstance(args[0], type):
        func = args[0]
        @wraps(func)
        def wrapper(*wargs, **wkwargs):
            func(*wargs, **wkwargs)
            return None
        return wrapper

    # 带参数调用（当前参数未使用）
    def decorator(func):
        @wraps(func)
        def wrapper(*wargs, **wkwargs):
            func(*wargs, **wkwargs)
            return None
        return wrapper
    return decorator


__all__ = ['repeat', 'retry', 'rerun', 'excepts', 'suppress', 'ignore']

# 定义可调用类型变量
F = TypeVar('F', bound=Callable[..., Any])




# ============================================================================
# repeat - 重复执行装饰器
# ============================================================================

def _repeat(
    cnt: Union[int, Callable[[], bool], Any] = 1, 
    delay: float = 0
) -> Callable[[F], F]:
    """
    重复执行被装饰函数的装饰器工厂
    
    参数:
        cnt: 重复次数或停止条件
            - int > 0: 执行指定次数
            - int < 0: 无限循环
            - int = 0: 不执行
            - 可调用对象: 返回False时停止
        delay: 每次调用后的延迟时间（秒）
    
    返回:
        装饰器函数：返回生成器迭代器
    
    示例:
        >>> @repeat(cnt=3, delay=0.5)
        ... def greet(name):
        ...     return f"Hello, {name}!"
        >>> for result in greet("Alice"):
        ...     print(result)
    """
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Iterator[Any]:
            # 情况1: cnt是可调用对象
            if callable(cnt):
                while True:
                    if not cnt():
                        break
                    result = func(*args, **kwargs)
                    yield result
                    if delay > 0:
                        time.sleep(delay)
            
            # 情况2: cnt是整数
            elif isinstance(cnt, int):
                if cnt < 0:  # 无限循环
                    while True:
                        result = func(*args, **kwargs)
                        yield result
                        if delay > 0:
                            time.sleep(delay)
                elif cnt == 0:  # 不执行
                    return
                else:  # 执行指定次数
                    for i in range(cnt):
                        result = func(*args, **kwargs)
                        yield result
                        if i < cnt - 1 and delay > 0:
                            time.sleep(delay)
            
            # 情况3: 其他类型
            else:
                if bool(cnt):
                    yield func(*args, **kwargs)
        
        return wrapper  # type: ignore
    return decorator


def repeat(
    func: Optional[F] = None, 
    cnt: Union[int, Callable[[], bool], Any] = 1, 
    delay: float = 0
) -> Callable[[F], F]:
    """重复执行装饰器"""
    if func is None:
        return _repeat(cnt, delay)
    else:
        return _repeat(cnt, delay)(func)


# ============================================================================
# retry - 重试装饰器
# ============================================================================

def retry(*args, **kwargs):
    """
    重试装饰器，支持多种重试条件和灵活的重试逻辑
    
    支持两种调用方式：
        @retry              # 使用默认参数
        @retry(tries=3, delay=1)  # 指定参数
    
    参数（仅限关键字参数）：
        tries: 最大重试次数（包括首次执行）
        delay: 初始延迟时间（秒）
        backoff: 延迟时间倍增因子
        exceptions: 需要捕获并重试的异常类型
        check_func: 返回值检查函数
        logic: 重试条件逻辑组合方式 ('or', 'and', 'xor')
        logger: 日志记录器实例
    
    示例:
        >>> @retry
        ... def unreliable_request():
        ...     import random
        ...     if random.random() < 0.8:
        ...         raise ConnectionError("网络连接失败")
        ...     return "请求成功"
        
        >>> @retry(tries=3, delay=0.5)
        ... def unreliable_request():
        ...     import random
        ...     if random.random() < 0.8:
        ...         raise ConnectionError("网络连接失败")
        ...     return "请求成功"
    """
    # 检测是否直接调用（@retry）
    if len(args) == 1 and callable(args[0]):
        # @retry 直接调用
        return _retry_decorator()(args[0])
    
    # @retry(...) 带参数调用
    tries = kwargs.get('tries', 3)
    delay = kwargs.get('delay', 1)
    backoff = kwargs.get('backoff', 2)
    exceptions = kwargs.get('exceptions', Exception)
    check_func = kwargs.get('check_func', None)
    logic = kwargs.get('logic', 'or')
    logger = kwargs.get('logger', None)
    
    return _retry_decorator(
        tries=tries,
        delay=delay,
        backoff=backoff,
        exceptions=exceptions,
        check_func=check_func,
        logic=logic,
        logger=logger
    )


def _retry_decorator(
    tries: int = 3,
    delay: float = 1,
    backoff: float = 2,
    exceptions: Union[Type[Exception], Tuple[Type[Exception], ...]] = Exception,
    check_func: Optional[Callable[[Any], bool]] = None,
    logic: str = 'or',
    logger: Optional[logging.Logger] = None
) -> Callable:
    """内部函数：创建 retry 装饰器"""
    # 验证逻辑参数
    valid_logics = {'or', '|', '||', 'and', '&', '&&', 'xor', '^'}
    if logic not in valid_logics:
        raise ValueError(f"无效的逻辑类型: {logic}. 有效值: {valid_logics}")
    
    # 规范化逻辑关键词
    logic = 'or' if logic in {'|', '||'} else \
           'and' if logic in {'&', '&&'} else \
           'xor' if logic in {'^'} else logic
    
    # 设置日志记录器
    log = logger.info if logger else print
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            nonlocal delay
            current_delay = delay
            last_exception = None
            last_result = None
            attempt = 1
            
            while attempt <= tries:
                retry_by_exception = False
                retry_by_result = False
                result = None
                
                try:
                    result = func(*args, **kwargs)
                    last_result = result
                    
                    if check_func is not None:
                        retry_by_result = not check_func(result)
                    
                except Exception as e:
                    if not isinstance(e, exceptions):
                        raise
                    
                    last_exception = e
                    retry_by_exception = True
                    
                    if check_func is not None:
                        retry_by_result = False
                
                # 判断是否重试
                if logic == 'or':
                    should_retry = retry_by_exception or retry_by_result
                elif logic == 'and':
                    should_retry = retry_by_exception and retry_by_result
                else:  # 'xor'
                    should_retry = retry_by_exception != retry_by_result
                
                if not should_retry:
                    return result
                
                if attempt == tries:
                    break
                
                # 记录重试信息
                retry_reason = []
                if retry_by_exception:
                    retry_reason.append(f"异常: {type(last_exception).__name__}")
                if retry_by_result:
                    retry_reason.append("返回值检查失败")
                
                log(f"尝试 {attempt}/{tries} 失败，{current_delay:.2f}秒后重试...")
                
                time.sleep(current_delay)
                current_delay *= backoff
                attempt += 1
            
            if last_exception is not None:
                raise last_exception
            return last_result
        
        return wrapper
    
    return decorator


# ============================================================================
# rerun - 重新运行装饰器
# ============================================================================

def rerun(*args, **kwargs):
    """
    周期性执行函数直到满足终止条件或超时
    
    支持两种调用方式：
        @rerun              # 使用默认参数
        @rerun(until=..., interval=5, time_out=300)  # 指定参数
    
    参数（仅限关键字参数）：
        until: 检查函数返回值的谓词函数，返回True时停止
        interval: 重试间隔时间（秒）
        time_out: 总超时时间（秒）
    
    返回:
        函数的最终返回值
    
    异常:
        TimeoutError: 当超过time_out时间仍未满足条件时抛出
    
    示例:
        >>> @rerun
        ... def check_status():
        ...     return {'status': 'success'}
        
        >>> @rerun(until=lambda x: x.get('status') == 'success', interval=1, time_out=10)
        ... def check_status():
        ...     import random
        ...     if random.random() < 0.7:
        ...         return {'status': 'pending'}
        ...     return {'status': 'success'}
    """
    # 检测是否直接调用（@rerun）
    if len(args) == 1 and callable(args[0]):
        # @rerun 直接调用
        return _rerun_decorator()(args[0])
    
    # @rerun(...) 带参数调用
    until = kwargs.get('until', lambda x: x is not None)
    interval = kwargs.get('interval', 5)
    time_out = kwargs.get('time_out', 300)
    
    return _rerun_decorator(until=until, interval=interval, time_out=time_out)


def _rerun_decorator(
    until: Callable[[Any], bool] = lambda x: x is not None,
    interval: int = 5,
    time_out: int = 300
):
    """内部函数：创建 rerun 装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.monotonic()
            attempt_count = 0
            
            while True:
                attempt_count += 1
                attempt_start = time.monotonic()
                
                try:
                    result = func(*args, **kwargs)
                    
                    if until(result):
                        return result
                        
                    elapsed = time.monotonic() - start_time
                    if elapsed > time_out:
                        raise TimeoutError(
                            f"Function {func.__name__} timed out after {time_out}s"
                        )
                    
                    execution_time = time.monotonic() - attempt_start
                    wait_time = max(0, interval - execution_time)
                    
                    if wait_time > 0:
                        time.sleep(wait_time)
                        
                except Exception as e:
                    elapsed = time.monotonic() - start_time
                    if elapsed > time_out:
                        raise TimeoutError(
                            f"Function {func.__name__} timed out after {time_out}s"
                        ) from e
                    
                    time.sleep(interval)
        
        return wrapper
    
    return decorator

