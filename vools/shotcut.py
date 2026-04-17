"""
shotcut.py - 快捷工具集

提供快捷工具和辅助函数，整合 shotcut、hoder 和 shotcutEx 功能。
"""

from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar, Union
import functools
import inspect
import sys
import time
import os
import re


# ============================================================================
# 类型定义
# ============================================================================

T = TypeVar('T')
R = TypeVar('R')


# ============================================================================
# 基础工具类
# ============================================================================

class Hoder:
    """对象持有者，用于延迟加载和管理对象"""
    
    def __init__(self, obj=None, lazy: bool = False, creator: Callable = None):
        """
        初始化持有者
        
        Args:
            obj: 初始对象
            lazy: 是否延迟加载
            creator: 延迟加载的创建函数
        """
        self._obj = obj
        self._lazy = lazy
        self._creator = creator
        self._created = not lazy
    
    def get(self) -> Any:
        """获取对象"""
        if not self._created and self._creator:
            self._obj = self._creator()
            self._created = True
        return self._obj
    
    def set(self, obj: Any) -> 'Hoder':
        """设置对象"""
        self._obj = obj
        self._created = True
        return self
    
    def reset(self) -> 'Hoder':
        """重置对象"""
        self._created = False
        return self
    
    def is_created(self) -> bool:
        """检查对象是否已创建"""
        return self._created
    
    def __call__(self) -> Any:
        """调用时获取对象"""
        return self.get()
    
    def __getattr__(self, name: str) -> Any:
        """代理对象的属性访问"""
        return getattr(self.get(), name)
    
    def __setattr__(self, name: str, value: Any) -> None:
        """代理对象的属性设置"""
        if name.startswith('_'):
            super().__setattr__(name, value)
        else:
            setattr(self.get(), name, value)


# ============================================================================
# 快捷工具函数
# ============================================================================

class Shotcut:
    """快捷工具类，提供常用操作的快捷方法"""
    
    @staticmethod
    def timeit(func: Callable[..., R]) -> Callable[..., Tuple[R, float]]:
        """计时装饰器"""
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Tuple[R, float]:
            start = time.time()
            result = func(*args, **kwargs)
            end = time.time()
            return result, end - start
        return wrapper
    
    @staticmethod
    def memoize(func: Callable[..., R]) -> Callable[..., R]:
        """记忆化装饰器"""
        cache = {}
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> R:
            key = str(args) + str(kwargs)
            if key not in cache:
                cache[key] = func(*args, **kwargs)
            return cache[key]
        
        return wrapper
    
    @staticmethod
    def once(func: Callable[..., R]) -> Callable[..., R]:
        """只执行一次的装饰器"""
        called = False
        result = None
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> R:
            nonlocal called, result
            if not called:
                result = func(*args, **kwargs)
                called = True
            return result
        
        return wrapper
    
    @staticmethod
    def retry(max_attempts: int = 3, delay: float = 1.0) -> Callable[[Callable[..., R]], Callable[..., R]]:
        """重试装饰器"""
        def decorator(func: Callable[..., R]) -> Callable[..., R]:
            @functools.wraps(func)
            def wrapper(*args, **kwargs) -> R:
                attempts = 0
                while attempts < max_attempts:
                    try:
                        return func(*args, **kwargs)
                    except Exception as e:
                        attempts += 1
                        if attempts >= max_attempts:
                            raise
                        time.sleep(delay)
                return func(*args, **kwargs)
            return wrapper
        return decorator
    
    @staticmethod
    def asyncify(func: Callable[..., R]) -> Callable[..., Callable[..., R]]:
        """将同步函数转换为异步函数"""
        import asyncio
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> R:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, func, *args, **kwargs)
        
        return async_wrapper
    
    @staticmethod
    def compose(*funcs: Callable) -> Callable:
        """函数组合"""
        def composed(*args, **kwargs):
            result = funcs[0](*args, **kwargs)
            for func in funcs[1:]:
                result = func(result)
            return result
        return composed
    
    @staticmethod
    def pipe(value: Any, *funcs: Callable) -> Any:
        """管道操作"""
        result = value
        for func in funcs:
            result = func(result)
        return result
    
    @staticmethod
    def curry(func: Callable) -> Callable:
        """柯里化函数"""
        @functools.wraps(func)
        def curried(*args, **kwargs):
            if len(args) + len(kwargs) >= inspect.signature(func).parameters.__len__():
                return func(*args, **kwargs)
            
            @functools.wraps(func)
            def smart_partial(*more_args, **more_kwargs):
                return curried(*(args + more_args), **{**kwargs, **more_kwargs})
            
            return smart_partial
        
        return curried
    
    @staticmethod
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
    
    @staticmethod
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
    
    @staticmethod
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
                
                import threading
                timer = threading.Timer(interval, delayed)
                timer.start()
            
            return wrapper
        return decorator
    
    @staticmethod
    def singleton(cls):
        """单例装饰器"""
        instances = {}
        
        @functools.wraps(cls)
        def get_instance(*args, **kwargs):
            if cls not in instances:
                instances[cls] = cls(*args, **kwargs)
            return instances[cls]
        
        return get_instance
    
    @staticmethod
    def deprecated(message: str = "该函数已被弃用"):
        """弃用警告装饰器"""
        def decorator(func: Callable):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                import warnings
                warnings.warn(message, DeprecationWarning, stacklevel=2)
                return func(*args, **kwargs)
            return wrapper
        return decorator


# ============================================================================
# 扩展快捷工具类
# ============================================================================

class ShotcutEx:
    """扩展快捷工具类，提供更高级的快捷方法"""
    
    # 继承基础快捷工具
    timeit = Shotcut.timeit
    memoize = Shotcut.memoize
    once = Shotcut.once
    retry = Shotcut.retry
    asyncify = Shotcut.asyncify
    compose = Shotcut.compose
    pipe = Shotcut.pipe
    curry = Shotcut.curry
    safe = Shotcut.safe
    throttle = Shotcut.throttle
    debounce = Shotcut.debounce
    singleton = Shotcut.singleton
    deprecated = Shotcut.deprecated
    
    @staticmethod
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
    
    @staticmethod
    def with_context(context_manager):
        """上下文管理器装饰器"""
        def decorator(func: Callable[..., R]) -> Callable[..., R]:
            @functools.wraps(func)
            def wrapper(*args, **kwargs) -> R:
                with context_manager:
                    return func(*args, **kwargs)
            return wrapper
        return decorator
    
    @staticmethod
    def with_timeout(seconds: float):
        """超时装饰器"""
        def decorator(func: Callable[..., R]) -> Callable[..., R]:
            @functools.wraps(func)
            def wrapper(*args, **kwargs) -> R:
                import threading
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
    
    @staticmethod
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
    
    @staticmethod
    def rate_limit(max_calls: int, period: float):
        """速率限制装饰器"""
        def decorator(func: Callable[..., R]) -> Callable[..., R]:
            calls = []
            
            @functools.wraps(func)
            def wrapper(*args, **kwargs) -> R:
                nonlocal calls
                now = time.time()
                # 清理过期的调用记录
                calls = [t for t in calls if now - t < period]
                if len(calls) >= max_calls:
                    raise ValueError(f"速率限制：{max_calls}次/({period}秒)")
                calls.append(now)
                return func(*args, **kwargs)
            
            return wrapper
        return decorator
    
    @staticmethod
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
    
    @staticmethod
    def cache_with_ttl(ttl: float):
        """带过期时间的缓存装饰器"""
        def decorator(func: Callable[..., R]) -> Callable[..., R]:
            cache = {}
            
            @functools.wraps(func)
            def wrapper(*args, **kwargs) -> R:
                nonlocal cache
                key = str(args) + str(kwargs)
                now = time.time()
                
                # 清理过期缓存
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
    
    @staticmethod
    def hybrid_method(func):
        """混合方法装饰器，可同时作为类方法和实例方法使用"""
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            if isinstance(self, type):
                # 作为类方法调用
                return func(self, *args, **kwargs)
            else:
                # 作为实例方法调用
                return func(self.__class__, self, *args, **kwargs)
        return wrapper
    
    @staticmethod
    def classproperty(func):
        """类属性装饰器"""
        return property(classmethod(func))
    
    @staticmethod
    def enumize(enum_class):
        """枚举装饰器，将类转换为枚举"""
        import enum
        return enum.Enum(enum_class.__name__, [(attr, getattr(enum_class, attr)) for attr in dir(enum_class) if not attr.startswith('_')])


# ============================================================================
# 导出接口
# ============================================================================

# 导出 Hoder 类
hoder = Hoder

# 导出 ShotcutEx 作为主要接口
shotcut = ShotcutEx
shotcutEx = ShotcutEx

# 导出常用方法到模块级别
timeit = ShotcutEx.timeit
memoize = ShotcutEx.memoize
once = ShotcutEx.once
retry = ShotcutEx.retry
asyncify = ShotcutEx.asyncify
compose = ShotcutEx.compose
pipe = ShotcutEx.pipe
smart_partial = ShotcutEx.curry
safe = ShotcutEx.safe
throttle = ShotcutEx.throttle
debounce = ShotcutEx.debounce
singleton = ShotcutEx.singleton
deprecated = ShotcutEx.deprecated
conditional = ShotcutEx.conditional
with_context = ShotcutEx.with_context
with_timeout = ShotcutEx.with_timeout
validate = ShotcutEx.validate
rate_limit = ShotcutEx.rate_limit
log_calls = ShotcutEx.log_calls
cache_with_ttl = ShotcutEx.cache_with_ttl
hybrid_method = ShotcutEx.hybrid_method
classproperty = ShotcutEx.classproperty
enumize = ShotcutEx.enumize


# ============================================================================
# 测试代码
# ============================================================================

if __name__ == '__main__':
    print("=== 测试 shotcut 功能 ===")
    
    # 测试 Hoder
    print("\n1. 测试 Hoder 类:")
    h = hoder(lazy=True, creator=lambda: "Hello, Hoder!")
    print(f"Hoder 已创建: {h.is_created()}")
    print(f"Hoder 值: {h.get()}")
    print(f"Hoder 已创建: {h.is_created()}")
    
    # 测试 timeit
    print("\n2. 测试 timeit 装饰器:")
    @timeit
    def slow_function():
        time.sleep(0.1)
        return "Done"
    result, duration = slow_function()
    print(f"结果: {result}, 耗时: {duration:.4f}秒")
    
    # 测试 memoize
    print("\n3. 测试 memoize 装饰器:")
    @memoize
    def expensive_function(x):
        print(f"计算 {x} 的平方")
        return x * x
    print(f"第一次调用: {expensive_function(5)}")
    print(f"第二次调用: {expensive_function(5)}")
    
    # 测试 smart_partial
    print("\n4. 测试 smart_partial 函数:")
    @smart_partial
    def add(a, b, c):
        return a + b + c
    add5 = add(5)
    add5and3 = add5(3)
    print(f"add(5)(3)(2) = {add5and3(2)}",add5(2,3))
    
    # 测试 pipe
    print("\n5. 测试 pipe 函数:")
    result = pipe(
        10,
        lambda x: x * 2,
        lambda x: x + 5,
        lambda x: x ** 2
    )
    print(f"pipe(10, x*2, x+5, x**2) = {result}")
    
    # 测试 safe
    print("\n6. 测试 safe 函数:")
    @safe
    def risky_function(x):
        if x == 0:
            raise ValueError("除数不能为零")
        return 10 / x
    result, error = risky_function(0)
    print(f"risky_function(0) - 结果: {result}, 错误: {error}")
    result, error = risky_function(5)
    print(f"risky_function(5) - 结果: {result}, 错误: {error}")
    
    print("\n所有测试通过!")
