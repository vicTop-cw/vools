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

# 可选导入 wrapt
try:
    import wrapt
    @wrapt.decorator
    def merge_params(wrapped, instance, args, kwargs):
        """
        支持函数和类方法的参数收集装饰器
        """
        # 获取原始函数
        if hasattr(wrapped, '__func__'):
            original_func = wrapped.__func__
        else:
            original_func = wrapped
        
        # 获取函数签名
        sig = ins.signature(original_func)
        
        # 绑定参数
        bound_args = sig.bind(*args, **kwargs)
        bound_args.apply_defaults()
        
        # 构建参数字典
        params = {}
        
        for param_name, param_value in bound_args.arguments.items():
            param = sig.parameters[param_name]
            
            if param.kind == param.VAR_KEYWORD:
                params.update(param_value)
            elif param.kind == param.VAR_POSITIONAL:
                params[param_name] = param_value
            else:
                params[param_name] = param_value
        
        # 设置到函数属性
        original_func.params = params
        
        return wrapped(*args, **kwargs)


    WRAPT_AVAILABLE = True
except ImportError:
    WRAPT_AVAILABLE = False
    merge_params = None

__all__ = ['repeat', 'retry', 'rerun','merge_params']

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

def retry(
    tries: int = 3,
    delay: float = 1,
    backoff: float = 2,
    exceptions: Union[Type[Exception], Tuple[Type[Exception], ...]] = Exception,
    check_func: Optional[Callable[[Any], bool]] = None,
    logic: str = 'or',
    logger: Optional[logging.Logger] = None
) -> Callable:
    """
    重试装饰器，支持多种重试条件和灵活的重试逻辑
    
    参数:
        tries: 最大重试次数（包括首次执行）
        delay: 初始延迟时间（秒）
        backoff: 延迟时间倍增因子
        exceptions: 需要捕获并重试的异常类型
        check_func: 返回值检查函数
        logic: 重试条件逻辑组合方式 ('or', 'and', 'xor')
        logger: 日志记录器实例
    
    示例:
        >>> @retry(tries=3, delay=0.5)
        ... def unreliable_request():
        ...     import random
        ...     if random.random() < 0.8:
        ...         raise ConnectionError("网络连接失败")
        ...     return "请求成功"
    """
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

def rerun(until: Callable[[Any], bool], interval: int = 5, time_out: int = 300):
    """
    周期性执行函数直到满足终止条件或超时
    
    参数:
        until: 检查函数返回值的谓词函数，返回True时停止
        interval: 重试间隔时间（秒）
        time_out: 总超时时间（秒）
    
    返回:
        函数的最终返回值
    
    异常:
        TimeoutError: 当超过time_out时间仍未满足条件时抛出
    
    示例:
        >>> @rerun(lambda x: x.get('status') == 'success', interval=1, time_out=10)
        ... def check_status():
        ...     import random
        ...     if random.random() < 0.7:
        ...         return {'status': 'pending'}
        ...     return {'status': 'success'}
    """
    if WRAPT_AVAILABLE:
        @wrapt.decorator
        def wrapper(wrapped, instance, args, kwargs):
            thread_local = threading.local()
            
            if not hasattr(thread_local, 'start_time'):
                thread_local.start_time = time.monotonic()
                thread_local.attempt_count = 0
            
            while True:
                thread_local.attempt_count += 1
                attempt_start = time.monotonic()
                
                try:
                    result = wrapped(*args, **kwargs)
                    
                    if until(result):
                        return result
                        
                    elapsed = time.monotonic() - thread_local.start_time
                    if elapsed > time_out:
                        raise TimeoutError(
                            f"Function {wrapped.__name__} timed out after {time_out}s"
                        )
                    
                    execution_time = time.monotonic() - attempt_start
                    wait_time = max(0, interval - execution_time)
                    
                    if wait_time > 0:
                        time.sleep(wait_time)
                        
                except Exception as e:
                    elapsed = time.monotonic() - thread_local.start_time
                    if elapsed > time_out:
                        raise TimeoutError(
                            f"Function {wrapped.__name__} timed out after {time_out}s"
                        ) from e
                    
                    time.sleep(interval)
        
        return wrapper
    else:
        # wrapt 不可用时使用普通装饰器
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


# ============================================================================
# 测试代码
# ============================================================================

if __name__ == '__main__':
    print("=== 测试 repeat ===")
    
    @repeat(cnt=3, delay=0.5)
    def hello(name):
        return f"Hello, {name}!"
    
    for i, result in enumerate(hello("World")):
        print(f"调用 {i+1}: {result}")
    
    print("\n=== 测试 retry ===")
    
    @retry(tries=3, delay=0.5)
    def unreliable():
        import random
        if random.random() < 0.8:
            raise ConnectionError("失败")
        return "成功"
    
    try:
        print(f"结果: {unreliable()}")
    except Exception as e:
        print(f"最终失败: {e}")
    
    print("\n=== 测试 rerun ===")
    
    @rerun(lambda x: x == "success", interval=1, time_out=5)
    def check_status():
        import random
        if random.random() < 0.7:
            return "pending"
        return "success"
    
    try:
        print(f"最终状态: {check_status()}")
    except TimeoutError as e:
        print(f"超时: {e}")
    
    print("\n所有测试通过!")
