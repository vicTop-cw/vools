"""
单次执行装饰器 (once decorator)

确保函数或类只执行/初始化一次。

对于函数：
    - 第一次调用时执行并缓存结果
    - 后续调用直接返回缓存结果
    - 可以通过 force=True 强制重新执行

对于类：
    - 转换为单例模式
    - 所有实例共享同一个实例
"""

import time
from functools import wraps
from inspect import signature, isclass
from typing import Any, Callable, Optional

__all__ = ['once']


class _OnceWrapper:
    """单次执行函数包装器"""
    
    __slots__ = ("func", "called", "result", "force", "called_args", 
                 "called_kwargs", "last_called_time", "__signature__", "force_default")
    
    def __init__(self, func: Callable):
        self.func = func
        self.called = False
        self.result = None
        self.force = False
        self.called_args = None
        self.called_kwargs = None
        self.last_called_time = None
        self.__signature__ = signature(func)
        self.force_default = False  # 默认值
    
    def __getstate__(self):
        """Return serialization state"""
        return {k: getattr(self, k) for k in ('func','called','result','force','called_args','called_kwargs','last_called_time')}
    def __setstate__(self, state):
        """Restore from serialization state"""
        for k, v in state.items():
            setattr(self, k, v)
        from inspect import signature
        self.__signature__ = signature(self.func)
        self.force_default = getattr(self.func, '_force_default', False)

    def __call__(self, *args, **kwargs) -> Any:
        # 使用 force_default 作为默认值，如果调用时提供了 force 参数则覆盖
        force = kwargs.pop("force", self.force_default)
        if force:
            self.force = True
        if self.called and not self.force:
            return self.result
        self.called_args = args
        self.called_kwargs = kwargs
        self.called = True
        self.force = False
        self.result = self.func(*args, **kwargs)
        self.last_called_time = time.time()
        return self.result


def once(obj: Optional[Any] = None, *, force_default: bool = False) -> Any:
    """
    单次执行装饰器，确保函数或类只执行/初始化一次
    
    对于函数：
        - 第一次调用时执行并缓存结果
        - 后续调用直接返回缓存结果
        - 可以通过 force=True 强制重新执行
    
    对于类：
        - 转换为单例模式
        - 所有实例共享同一个实例
    
    参数:
        obj: 要装饰的函数或类（可选）
        force_default: 默认的 force 参数值（可选）
    
    返回:
        装饰后的函数或类
    
    示例:
        >>> @once
        ... def initialize():
        ...     print("Initializing...")
        ...     return 42
        
        >>> initialize()  # 输出: Initializing...
        42
        >>> initialize()  # 不输出
        42
        >>> initialize(force=True)  # 强制重新执行
        Initializing...
        42
        
        >>> @once(force_default=True)
        ... def always_execute():
        ...     return time.time()
        
        >>> @once
        ... class Singleton:
        ...     def __init__(self, value):
        ...         self.value = value
        
        >>> s1 = Singleton(1)
        >>> s2 = Singleton(2)
        >>> assert s1 is s2  # 同一个实例
    """
    # 参数类型验证
    if not isinstance(force_default, bool):
        raise TypeError(
            f"参数 'force_default' 类型错误: 期望 bool, 实际收到 {type(force_default).__name__}。\n"
            f"修复建议: 使用布尔值，例如:\n"
            f"  - @once(force_default=True)   # 每次都重新执行\n"
            f"  - @once(force_default=False)  # 只执行一次（默认行为）\n"
        )
    
    def decorator(o: Any) -> Any:
        if isclass(o):
            class Singleton(o):
                _instance = None
                
                def __new__(cls, *args, **kwargs):
                    if cls._instance is None:
                        cls._instance = super().__new__(cls)
                        cls._instance._initialized = False
                    return cls._instance
                

                def do(self, f=print, pre_f=None, sub_f=None):
                    """Apply a function for side effects, return self.

                    Args:
                        f: Function to apply (default print)
                        pre_f: Pre-processing function
                        sub_f: Post-processing function (no return value expected)

                    Returns:
                        self, for chaining
                    """
                    rs = self
                    if pre_f:
                        rs = pre_f(rs)
                    rs = f(rs)
                    if sub_f:
                        sub_f(rs)
                    return self
                def __init__(self, *args, **kwargs):
                    if not self._initialized:
                        super().__init__(*args, **kwargs)
                        self._initialized = True
            
            Singleton.__name__ = o.__name__
            Singleton.__qualname__ = o.__qualname__
            Singleton.__doc__ = o.__doc__
            Singleton.__module__ = o.__module__
            return Singleton
        
        # 创建函数包装器，并设置 force_default
        wrapper = _OnceWrapper(o)
        wrapper.force_default = force_default
        return wrapper
    
    # 支持两种调用方式
    if obj is None:
        # @once(force_default=True) 带参数调用
        return decorator
    else:
        # @once 直接调用
        return decorator(obj)
