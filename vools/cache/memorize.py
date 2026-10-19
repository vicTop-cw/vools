"""
函数结果缓存装饰器 (memorize)

提供带过期时间的函数结果缓存功能。
"""

import time
from functools import wraps
from typing import Callable, Any, Optional, Dict
from collections import OrderedDict
import threading

__all__ = ['memorize', 'TimedCache', '_CACHE']


# BUG-103: 哨兵对象用于区分"缓存未命中"和"缓存值为 None"。
# 旧实现 get() 返回 None 表示未命中，无法缓存返回 None 的函数结果。
_MISS = object()


class TimedCache:
    """带过期时间和大小限制的缓存（线程安全）"""
    
    def __init__(self, max_size: int = 1000):
        # BUG-210: max_size<=0 时旧实现任何 set 都对空缓存 popitem 抛
        # KeyError（0>=0 / 0>=负数 恒 True），缓存完全不可用。与本文件
        # memorize(duration<=0) 的 ValueError 口径一致，构造时显式拒绝。
        if not isinstance(max_size, int) or isinstance(max_size, bool) \
                or max_size <= 0:
            raise ValueError(
                f"参数 'max_size' 值无效: 必须为正整数，当前值: {max_size!r}。\n"
                f"修复建议: 使用正数作为容量上限，例如 TimedCache(max_size=100)"
            )
        self._cache = OrderedDict()  # type: ignore
        self._max_size = max_size
        self._lock = threading.Lock()

    def __getstate__(self):
        # BUG-146: 原读 self.max_size（无下划线），但 __init__ 只设 _max_size，pickle 抛 AttributeError
        d = {'max_size': self._max_size}
        with self._lock:
            d['_cache'] = dict(getattr(self, '_cache', {}))
        return d
    def __setstate__(self, state):
        self._max_size = state['max_size']
        # BUG-146: 恢复为 OrderedDict，否则后续 popitem(last=False) 与 move_to_end 会失败
        self._cache = OrderedDict(state.get('_cache', {}))
        self._lock = threading.Lock()
    
    def _is_obsolete(self, entry: Dict[str, Any], duration: float) -> bool:
        """检查缓存是否过期"""
        return time.time() - entry['time'] > duration
    
    def get(self, key: str, duration: float) -> Any:
        """获取缓存值

        BUG-103: 使用 _MISS 哨兵区分"缓存未命中"和"缓存值为 None"。
        旧实现返回 None 表示未命中，导致返回 None 的函数结果无法被缓存。

        Returns:
            缓存结果；未命中时返回 _MISS 哨兵
        """
        with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                if not self._is_obsolete(entry, duration):
                    self._cache.move_to_end(key)
                    return entry['result']
                del self._cache[key]
        return _MISS
    
    def set(self, key: str, result: Any):
        """设置缓存值

        BUG-210: 更新既有 key 只覆写并移到队尾，不驱逐（容量未涨却踢
        LRU 头部无辜条目会无谓击穿命中率）；仅新增且满员时驱逐最旧，
        while 兜底防御构造后 max_size 被外部调小的情形。
        """
        entry = {
            'result': result,
            'time': time.time()
        }
        with self._lock:
            if key in self._cache:
                self._cache[key] = entry
                self._cache.move_to_end(key)
                return
            while len(self._cache) >= self._max_size and self._cache:
                self._cache.popitem(last=False)
            if len(self._cache) >= self._max_size:
                # max_size 被构造后改小到 0 等退化形状：不写入也不崩
                # （__init__ 已拒绝 max_size<=0，这里纯防御）。
                return
            self._cache[key] = entry
    
    def clear(self) -> None:
        """清空缓存"""
        with self._lock:
            self._cache.clear()
    

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
    def __len__(self):
        """返回缓存条目数"""
        with self._lock:
            return len(self._cache)
    
    
# 全局缓存实例
_CACHE = TimedCache(max_size=1000)


def _compute_key(func: Callable, args: tuple, kwargs: dict) -> Any:
    """计算缓存键

    BUG-103: 旧实现用 `pickle.dumps((func.__name__, args, kwargs))`，
    当参数含 lambda/file/socket 等不可 pickle 对象时装饰后的函数直接崩溃。
    BUG-110: 旧 key 用 `func.__name__` 作一部分，同名函数跨作用域缓存冲突
    （如两个模块都定义 `get_ab`，key 相同导致命中错误结果）。
    改为：优先用 (func, args, tuple(sorted(kwargs.items()))) 作为键，
    函数对象本身可哈希且身份唯一，彻底避免同名冲突；
    不可哈希时回退到 repr 字符串（牺牲部分性能换取可用性）。
    """
    try:
        key = (func, args, tuple(sorted(kwargs.items())))
        hash(key)  # 验证可哈希（快速失败，避免后续 dict 插入时报错）
        return key
    except TypeError:
        # BUG-135: 回退分支原用 func.__name__，同名函数跨模块缓存键冲突
        # （BUG-110 只修了主分支）。改用 __module__ + __qualname__ 唯一标识。
        return (func.__module__, func.__qualname__, repr(args), repr(kwargs))


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
            if cached_result is not _MISS:
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

