"""
函数结果缓存装饰器 (memorize)

提供带过期时间的函数结果缓存功能。
"""

import time
import hashlib
import pickle
from functools import wraps
from typing import Callable, Any, Optional, Dict
from collections import OrderedDict
import threading

__all__ = ['memorize', 'TimedCache', '_CACHE']


class TimedCache:
    """带过期时间和大小限制的缓存（线程安全）"""
    
    def __init__(self, max_size: int = 1000):
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._max_size = max_size
        self._lock = threading.Lock()
    
    def _is_obsolete(self, entry: Dict[str, Any], duration: float) -> bool:
        """检查缓存是否过期"""
        return time.time() - entry['time'] > duration
    
    def get(self, key: str, duration: float) -> Optional[Any]:
        """获取缓存值"""
        with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                if not self._is_obsolete(entry, duration):
                    self._cache.move_to_end(key)
                    return entry['result']
                del self._cache[key]
        return None
    
    def set(self, key: str, result: Any):
        """设置缓存值"""
        with self._lock:
            if len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)
            
            self._cache[key] = {
                'result': result,
                'time': time.time()
            }
    
    def clear(self) -> None:
        """清空缓存"""
        with self._lock:
            self._cache.clear()
    
    def __len__(self):
        """返回缓存条目数"""
        with self._lock:
            return len(self._cache)
    
    
# 全局缓存实例
_CACHE = TimedCache(max_size=1000)


def _compute_key(func: Callable, args: tuple, kwargs: dict) -> str:
    """计算缓存键"""
    key = pickle.dumps((func.__name__, args, kwargs))
    return hashlib.sha256(key).hexdigest()


def memorize(func: Optional[Callable] = None, *, duration: float = 3) -> Callable:
    """
    函数结果缓存装饰器，缓存函数结果一段时间
    
    参数:
        func: 要装饰的函数（可选）
        duration: 缓存持续时间（秒），默认 3 秒
    
    返回:
        装饰后的函数
    
    示例:
        >>> @memorize
        ... def expensive_function(x):
        ...     return x ** 2
        
        >>> @memorize(duration=5)
        ... def another_function(x):
        ...     return x ** 3
        
        >>> class MyClass:
        ...     @memorize(duration=5)
        ...     def method(self, x):
        ...         return x * 2
    
    文档:
        https://vools.readthedocs.io/decorators/cache.html#memorize
    """
    # 参数类型验证
    if not isinstance(duration, (int, float)):
        raise TypeError(
            f"参数 'duration' 类型错误: 期望 int 或 float, 实际收到 {type(duration).__name__}。\n"
            f"修复建议: 使用数字类型，例如 @memorize(duration=5) 或 @memorize(duration=3.0)\n"
            f"文档链接: https://vools.readthedocs.io/decorators/cache.html#memorize"
        )
    
    # 参数范围验证
    if duration <= 0:
        raise ValueError(
            f"参数 'duration' 值无效: 必须为正数，当前值: {duration}。\n"
            f"修复建议: 使用正数作为缓存时间，例如:\n"
            f"  - @memorize(duration=1)    # 缓存 1 秒\n"
            f"  - @memorize(duration=60)   # 缓存 60 秒\n"
            f"  - @memorize(duration=0.5)  # 缓存 0.5 秒\n"
            f"文档链接: https://vools.readthedocs.io/decorators/cache.html#memorize"
        )
    
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def wrapper(*args, **kwargs):
            key = _compute_key(f, args, kwargs)
            
            cached_result = _CACHE.get(key, duration)
            if cached_result is not None:
                return cached_result
            
            result = f(*args, **kwargs)
            _CACHE.set(key, result)
            
            return result
        return wrapper
    
    # 支持两种调用方式
    if func is None:
        # @memorize(duration=5) 带参数调用
        return decorator
    else:
        # @memorize 直接调用
        return decorator(func)


if __name__ == '__main__':
    print("=== 测试 memorize ===")
    
    @memorize
    def test_func1():
        return time.time()
    
    for i in range(5):
        print(f"调用 {i}: {test_func1()}")
        time.sleep(0.5)
    
    @memorize(duration=2)
    def test_func2():
        return time.time()
    
    print("\n测试 duration 参数:")
    for i in range(5):
        print(f"调用 {i}: {test_func2()}")
        time.sleep(0.5)
