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
import threading
import weakref
from functools import wraps
from inspect import signature, isclass
from typing import Any, Callable, Optional

__all__ = ['once']


class _OnceWrapper:
    """单次执行函数包装器"""
    
    __slots__ = ("func", "called", "result", "force", "called_args", 
                 "called_kwargs", "last_called_time", "__signature__", "force_default",
                 "_lock", "_instance_cache")
    
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
        # BUG-104: 并发安全锁（RLock 允许 func 内部递归调用自身装饰的函数）
        self._lock = threading.RLock()
        # BUG-382: 方法装饰时按**实例**缓存（WeakKeyDictionary，避免强引用泄漏）
        self._instance_cache = weakref.WeakKeyDictionary()
    
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
        # BUG-104: 反序列化后重建锁（Lock 不可 pickle）
        self._lock = threading.RLock()
        self._instance_cache = weakref.WeakKeyDictionary()

    def __get__(self, instance, owner=None):
        """BUG-382: 支持 `@once` 装饰**实例方法**。

        原实现包装成普通可调用对象（无 `__get__`），实例访问不会绑定 self，
        一调用就抛 `TypeError: ... missing 1 required positional argument: 'self'`。
        语义按"每个实例各自只执行一次"实现（缓存用弱引用表，实例回收后自动释放）；
        类访问（``Cls.method``）仍返回包装器本身。
        """
        if instance is None:
            return self

        def bound(*args, **kwargs):
            _force = kwargs.pop("force", self.force_default)
            with self._lock:
                try:
                    if not _force and instance in self._instance_cache:
                        return self._instance_cache[instance]
                except TypeError:
                    # 实例不可弱引用/不可哈希（如某些 __slots__ 对象）→ 不缓存
                    return self.func(instance, *args, **kwargs)
                _result = self.func(instance, *args, **kwargs)
                self._instance_cache[instance] = _result
                return _result

        bound.__name__ = getattr(self.func, "__name__", "bound")
        bound.__doc__ = getattr(self.func, "__doc__", None)
        return bound

    def __call__(self, *args, **kwargs) -> Any:
        # 使用 force_default 作为默认值，如果调用时提供了 force 参数则覆盖
        force = kwargs.pop("force", self.force_default)
        # BUG-104: 用锁保护 "检查已调用" 和 "写入 result" 两个动作的原子性。
        # 旧实现在 self.called = True 之后到 self.result = func(...) 完成之间，
        # 其他线程看到 called==True 直接返回 self.result（此时还是初始 None）。
        with self._lock:
            if force:
                self.force = True
            if self.called and not self.force:
                return self.result
            self.called_args = args
            self.called_kwargs = kwargs
            self.force = False
            # BUG-209: called/result 只能在 func 成功后盖章——原实现在调用前
            # 就置 called=True，func 抛异常时 result 停留在初始 None，后续调用
            # 全部静默返回 None 且永不重试（失败被永久缓存、错误被吞）。
            # 现在失败异常原样传播，called 保持 False，下次调用自然重试。
            result = self.func(*args, **kwargs)
            self.result = result
            self.called = True
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
        
        >>> initialize()  # 首次调用会打印
        Initializing...
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
