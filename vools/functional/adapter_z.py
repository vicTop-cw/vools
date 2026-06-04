"""
适配器 Z：智能切换 X 和 _ 的行为
- 属性访问（Z.xxxx）：走 X 的方法包装器逻辑
- 其他操作（运算符、索引访问、调用）：走 _ 的占位符表达式逻辑
"""

from typing import Any, Callable, Dict, Optional
import threading
from .placeholder_impl import X, _MethodWrapper, _ChainedResult
from .placeholder import _IndexHolder


class _AdapterZ:
    """
    智能适配器类，根据使用方式自动切换行为
    - Z.xxxx 属性访问：返回 _MethodWrapper（X 风格）
    - Z + 1, Z[0] 等：返回 _IndexHolder 表达式（_ 风格）
    """
    
    _instance: Optional['_AdapterZ'] = None
    _lock: threading.Lock = threading.Lock()
    _method_cache: Dict[str, Callable] = {}
    _wrapper_cache: Dict[str, _MethodWrapper] = {}
    
    def __new__(cls) -> '_AdapterZ':
        """线程安全的单例实例创建"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(_AdapterZ, cls).__new__(cls)
                cls._method_cache = {}
                cls._wrapper_cache = {}
        return cls._instance
    
    def __init__(self):
        """初始化实例状态"""
        # 创建底层的 _IndexHolder 实例，用于运算符和索引操作
        self._holder = _IndexHolder(ix=0)
    
    def __getattr__(self, name: str) -> _MethodWrapper:
        """
        属性访问：走 X 的方法包装器逻辑
        Z.upper 返回 _MethodWrapper，支持 X 风格的链式调用
        """
        if name in ['_holder', '_method_cache', '_wrapper_cache']:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
        
        if name not in self._wrapper_cache:
            self._wrapper_cache[name] = _MethodWrapper(name, self._method_cache)
        
        return self._wrapper_cache[name]
    
    def __call__(self, *args, **kwargs) -> Any:
        """
        调用操作：走 X 的绑定值逻辑或 _ 的表达式调用逻辑
        - Z() 返回恒等函数（X 风格）
        - Z(value) 返回绑定值的包装器（X 风格）
        - Z(*args, **kwargs) 如果有参数，尝试调用底层 holder（_ 风格）
        """
        if args:
            return _ChainedResult(args[0])
        
        if kwargs:
            # 如果有关键字参数，尝试走 _ 的表达式调用逻辑
            return self._holder.__call__(*args, **kwargs)
        
        return lambda x: x
    
    def __getitem__(self, key):
        """
        索引访问：走 _ 的占位符表达式逻辑
        Z[0] 返回新的占位符表达式
        """
        return self._holder.__getitem__(key)
    
    def __neg__(self):
        return self._holder.__neg__()
    
    def __pos__(self):
        return self._holder.__pos__()
    
    def __abs__(self):
        return self._holder.__abs__()
    
    def __invert__(self):
        return self._holder.__invert__()
    
    def __add__(self, other):
        return self._holder.__add__(other)
    
    def __sub__(self, other):
        return self._holder.__sub__(other)
    
    def __mul__(self, other):
        return self._holder.__mul__(other)
    
    def __truediv__(self, other):
        return self._holder.__truediv__(other)
    
    def __floordiv__(self, other):
        return self._holder.__floordiv__(other)
    
    def __mod__(self, other):
        return self._holder.__mod__(other)
    
    def __pow__(self, other):
        return self._holder.__pow__(other)
    
    def __lshift__(self, other):
        return self._holder.__lshift__(other)
    
    def __rshift__(self, other):
        return self._holder.__rshift__(other)
    
    def __and__(self, other):
        return self._holder.__and__(other)
    
    def __xor__(self, other):
        return self._holder.__xor__(other)
    
    def __or__(self, other):
        return self._holder.__or__(other)
    
    def __radd__(self, other):
        return self._holder.__radd__(other)
    
    def __rsub__(self, other):
        return self._holder.__rsub__(other)
    
    def __rmul__(self, other):
        return self._holder.__rmul__(other)
    
    def __rtruediv__(self, other):
        return self._holder.__rtruediv__(other)
    
    def __rfloordiv__(self, other):
        return self._holder.__rfloordiv__(other)
    
    def __rmod__(self, other):
        return self._holder.__rmod__(other)
    
    def __rpow__(self, other):
        return self._holder.__rpow__(other)
    
    def __rlshift__(self, other):
        return self._holder.__rlshift__(other)
    
    def __rrshift__(self, other):
        return self._holder.__rrshift__(other)
    
    def __rand__(self, other):
        return self._holder.__rand__(other)
    
    def __rxor__(self, other):
        return self._holder.__rxor__(other)
    
    def __ror__(self, other):
        return self._holder.__ror__(other)
    
    def __lt__(self, other):
        return self._holder.__lt__(other)
    
    def __le__(self, other):
        return self._holder.__le__(other)
    
    def __eq__(self, other):
        return self._holder.__eq__(other)
    
    def __ne__(self, other):
        return self._holder.__ne__(other)
    
    def __gt__(self, other):
        return self._holder.__gt__(other)
    
    def __ge__(self, other):
        return self._holder.__ge__(other)
    
    def __str__(self):
        return "<Z Adapter>"
    
    def __repr__(self):
        return "<Z Adapter>"


# 单例全局实例
Z = _AdapterZ()

__all__ = ['Z']
