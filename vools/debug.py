"""
vools-debug - 调试工具模块

提供用于调试和性能分析的工具函数
"""

import functools
import time
import inspect
from typing import Any, Callable


def trace(func: Callable = None, *, enabled: bool = True, prefix: str = ""):
    """
    跟踪函数调用的装饰器
    
    打印函数调用的详细信息，包括参数、返回值和执行时间
    
    Args:
        func: 要装饰的函数
        enabled: 是否启用跟踪
        prefix: 输出前缀
    
    Example:
        @trace
        def my_operator(x):
            return x * 2
        
        @trace(enabled=False)
        def production_code(x):
            return x + 1
    """
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not enabled:
                return func(*args, **kwargs)
            
            func_name = func.__name__
            full_prefix = f"[{prefix}] " if prefix else ""
            
            # 格式化参数
            arg_strs = []
            for i, arg in enumerate(args):
                if i < len(inspect.signature(func).parameters):
                    param_name = list(inspect.signature(func).parameters.keys())[i]
                    arg_strs.append(f"{param_name}={arg!r}")
                else:
                    arg_strs.append(repr(arg))
            
            arg_strs.extend(f"{k}={v!r}" for k, v in kwargs.items())
            args_str = ", ".join(arg_strs)
            
            start_time = time.time()
            
            print(f"{full_prefix}Calling {func_name}({args_str})")
            
            try:
                result = func(*args, **kwargs)
                elapsed = (time.time() - start_time) * 1000
                print(f"{full_prefix}{func_name}({args_str}) -> {result!r} [{elapsed:.2f}ms]")
                return result
            except Exception as e:
                elapsed = (time.time() - start_time) * 1000
                print(f"{full_prefix}{func_name}({args_str}) -> Exception: {type(e).__name__}: {e} [{elapsed:.2f}ms]")
                raise
        
        return wrapper
    
    if func is not None:
        return decorator(func)
    return decorator


def trace_async(func: Callable = None, *, enabled: bool = True, prefix: str = ""):
    """
    跟踪异步函数调用的装饰器
    
    Args:
        func: 要装饰的异步函数
        enabled: 是否启用跟踪
        prefix: 输出前缀
    """
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            if not enabled:
                return await func(*args, **kwargs)
            
            func_name = func.__name__
            full_prefix = f"[{prefix}] " if prefix else ""
            
            arg_strs = []
            for i, arg in enumerate(args):
                if i < len(inspect.signature(func).parameters):
                    param_name = list(inspect.signature(func).parameters.keys())[i]
                    arg_strs.append(f"{param_name}={arg!r}")
                else:
                    arg_strs.append(repr(arg))
            
            arg_strs.extend(f"{k}={v!r}" for k, v in kwargs.items())
            args_str = ", ".join(arg_strs)
            
            start_time = time.time()
            
            print(f"{full_prefix}Calling async {func_name}({args_str})")
            
            try:
                result = await func(*args, **kwargs)
                elapsed = (time.time() - start_time) * 1000
                print(f"{full_prefix}{func_name}({args_str}) -> {result!r} [{elapsed:.2f}ms]")
                return result
            except Exception as e:
                elapsed = (time.time() - start_time) * 1000
                print(f"{full_prefix}{func_name}({args_str}) -> Exception: {type(e).__name__}: {e} [{elapsed:.2f}ms]")
                raise
        
        return wrapper
    
    if func is not None:
        return decorator(func)
    return decorator


def profile(func: Callable) -> Callable:
    """
    性能分析装饰器 - 统计函数调用次数和平均执行时间
    
    Example:
        @profile
        def process_data(data):
            # ...
        
        # 查看统计信息
        print(process_data.stats)
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start_time
        
        # 更新统计
        wrapper.call_count += 1
        wrapper.total_time += elapsed
        wrapper.max_time = max(wrapper.max_time, elapsed)
        wrapper.min_time = min(wrapper.min_time, elapsed) if wrapper.min_time else elapsed
        
        return result
    
    wrapper.call_count = 0
    wrapper.total_time = 0.0
    wrapper.max_time = 0.0
    wrapper.min_time = None
    
    @property
    def stats(self):
        if self.call_count == 0:
            return {"call_count": 0, "avg_time_ms": 0.0}
        return {
            "call_count": self.call_count,
            "total_time_ms": self.total_time * 1000,
            "avg_time_ms": (self.total_time / self.call_count) * 1000,
            "max_time_ms": self.max_time * 1000,
            "min_time_ms": self.min_time * 1000
        }
    
    wrapper.stats = property(lambda self: stats(self))
    
    return wrapper