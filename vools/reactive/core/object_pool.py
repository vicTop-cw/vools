"""
对象池化模块 - 减少频繁创建与销毁开销
"""

from __future__ import annotations
import threading
import time
from typing import Type, Optional, Callable, Any
__all__ = ['ObjectPool', 'PooledObject', 'get_pool', 'clear_all_pools', 'pooled_acquire', 'pooled_release']


class ObjectPool:
    """通用对象池"""
    
    __slots__ = ('_pool', '_max_size', '_min_size', '_lock', '_type', '_create_fn', '_reset_fn', '_expire_time')
    
    def __init__(self, obj_type: Type, create_fn: Callable = None, reset_fn: Callable = None,
                 max_size: int = 100, min_size: int = 10, expire_time: float = 300.0):
        self._pool = []
        self._max_size = max_size
        self._min_size = min_size
        self._lock = threading.Lock()
        self._type = obj_type
        self._create_fn = create_fn or (lambda: obj_type())
        self._reset_fn = reset_fn or (lambda obj: None)
        self._expire_time = expire_time
        
        self._preallocate()

    def __getstate__(self):
        return {'_pool': [], '_max_size': self._max_size, '_min_size': self._min_size,
                '_type': self._type, '_create_fn': self._create_fn, '_reset_fn': self._reset_fn,
                '_expire_time': self._expire_time}
    def __setstate__(self, state):
        self._pool = []
        self._max_size = state['_max_size']
        self._min_size = state['_min_size']
        self._lock = threading.Lock()
        self._type = state['_type']
        self._create_fn = state['_create_fn']
        self._reset_fn = state['_reset_fn']
        self._expire_time = state['_expire_time']
    
    def _preallocate(self):
        """预分配最小数量的对象"""
        with self._lock:
            while len(self._pool) < self._min_size:
                self._pool.append((self._create_fn(), time.time()))
    
    def acquire(self) -> Any:
        """从池中获取对象"""
        with self._lock:
            while self._pool:
                obj, create_time = self._pool.pop()
                
                if self._expire_time > 0 and (time.time() - create_time) > self._expire_time:
                    continue
                
                return obj
            
            return self._create_fn()
    
    def release(self, obj: Any) -> None:
        """将对象放回池中"""
        if not isinstance(obj, self._type):
            return
        
        with self._lock:
            if len(self._pool) < self._max_size:
                self._reset_fn(obj)
                self._pool.append((obj, time.time()))
    
    def clear(self) -> None:
        """清空对象池"""
        with self._lock:
            self._pool.clear()
    
    @property
    def size(self) -> int:
        """获取池大小"""
        with self._lock:
            return len(self._pool)
    
    @property
    def max_size(self) -> int:
        return self._max_size
    
    @max_size.setter
    def max_size(self, value: int):
        self._max_size = value
        with self._lock:
            while len(self._pool) > self._max_size:
                self._pool.pop()


class PooledObject:
    """池化对象基类"""
    
    __slots__ = ('_pool',)
    
    def __init__(self):
        self._pool = None
    
    def set_pool(self, pool: ObjectPool):
        """设置所属对象池"""
        self._pool = pool
    
    def release(self):
        """释放回对象池"""
        if self._pool is not None:
            self._pool.release(self)
    
    def reset(self):
        """重置对象状态（子类实现）"""
        pass


_default_pools = {}
_pools_lock = threading.Lock()


def get_pool(obj_type: Type, **kwargs) -> ObjectPool:
    """获取或创建对象池"""
    key = obj_type.__name__
    
    with _pools_lock:
        if key not in _default_pools:
            _default_pools[key] = ObjectPool(obj_type, **kwargs)
        return _default_pools[key]


def clear_all_pools():
    """清空所有对象池"""
    with _pools_lock:
        for pool in _default_pools.values():
            pool.clear()
        _default_pools.clear()


def pooled_acquire(obj_type: Type, **kwargs) -> Any:
    """从默认池中获取对象"""
    pool = get_pool(obj_type, **kwargs)
    return pool.acquire()


def pooled_release(obj: Any):
    """将对象释放回默认池"""
    if hasattr(obj, 'release') and callable(obj.release):
        obj.release()
    else:
        obj_type = type(obj)
        pool = get_pool(obj_type)
        pool.release(obj)