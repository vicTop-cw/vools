"""
Singleton implementation of placeholder class similar to vools library's _X class.
支持无参和带参的占位模式调用，满足 X.strip == X.strip()
"""

from typing import Any, Callable, Dict, Optional
import threading

__all__ = ['X']

class _MethodWrapper:
    """
    方法包装类，实现 X.strip == X.strip()
    当访问属性时返回缓存的lambda
    当调用无参数时返回同一个缓存的lambda
    当调用带参数时返回新的带参lambda
    """
    
    def __init__(self, method_name: str, method_cache: Dict[str, Callable], bound_value: Any = None):
        self._method_name = method_name
        self._method_cache = method_cache
        self._bound_value = bound_value
    
    def _get_lambda(self) -> Callable:
        """获取或创建无参lambda"""
        method = self._method_name
        if method not in self._method_cache:
            self._method_cache[method] = lambda x, *args, **kwargs: getattr(x, method)(*args, **kwargs)
        return self._method_cache[method]
    
    def __call__(self, *args, **kwargs) -> Any:
        """
        方法调用处理：
        - 有绑定值时，直接执行方法并返回结果或继续链式调用
        - 无绑定值且无参数调用 X.strip() 返回缓存的无参lambda
        - 无绑定值且带参数调用 X.strip(',') 返回新的带参lambda
        """
        if self._bound_value is not None:
            # 有绑定值，直接执行
            result = getattr(self._bound_value, self._method_name)(*args, **kwargs)
            # 返回绑定了结果的包装器，支持继续链式调用
            return _ChainedResult(result)
        else:
            if not args and not kwargs:
                return self._get_lambda()
            else:
                method = self._method_name
                return lambda x: getattr(x, method)(*args, **kwargs)
    
    def __eq__(self, other) -> bool:
        """支持 X.strip == X.strip() 比较"""
        if callable(other):
            return other == self._get_lambda()
        return False
    
    def __hash__(self) -> int:
        return hash(self._method_name)


class _ChainedResult:
    """
    链式调用结果包装器，支持继续链式调用
    """
    
    def __init__(self, value: Any):
        self._value = value
    
    def __getattr__(self, name: str) -> '_MethodWrapper':
        """拦截方法调用，继续链式调用"""
        return _MethodWrapper(name, {}, bound_value=self._value)
    
    @property
    def val(self) -> Any:
        """获取最终值"""
        return self._value
    
    def __str__(self) -> str:
        return str(self._value)
    
    def __repr__(self) -> str:
        return repr(self._value)


class _X:
    """
    单例占位符类，支持链式方法调用
    关键特性:
        X.strip == X.strip()  -> True
        X.strip() 是无参数的 lambda: lambda x: x.strip()
        X.strip(',') 是带参数的 lambda: lambda x: x.strip(',')
    
    单例特性:
        应用程序生命周期内仅存在一个实例
        线程安全的实例创建
    """
    
    _instance: Optional['_X'] = None
    _lock: threading.Lock = threading.Lock()
    _method_cache: Dict[str, Callable] = {}
    _wrapper_cache: Dict[str, '_MethodWrapper'] = {}
    
    def __new__(cls) -> '_X':
        """线程安全的单例实例创建"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(_X, cls).__new__(cls)
                cls._method_cache = {}
                cls._wrapper_cache = {}
        return cls._instance
    
    def __init__(self):
        """初始化实例状态"""
        pass
    
    def __getattr__(self, name: str) -> '_MethodWrapper':
        """
        拦截属性访问，返回缓存的方法包装器
        X.strip 返回同一个缓存的 _MethodWrapper 对象
        """
        if name in ['_method_cache', '_wrapper_cache']:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
        
        if name not in self._wrapper_cache:
            self._wrapper_cache[name] = _MethodWrapper(name, self._method_cache)
        
        return self._wrapper_cache[name]
    
    def __call__(self, *args, **kwargs) -> Any:
        """
        执行方法调用或绑定初始值
        - X() 返回恒等函数
        - X('hello') 返回绑定值的包装器，支持后续链式调用
        """
        if args:
            return _ChainedResult(args[0])
        
        return lambda x: x
    
    def __str__(self) -> str:
        return "<X>"
    
    def __repr__(self) -> str:
        return "<X>"
    
    @classmethod
    def get_instance(cls) -> '_X':
        """获取单例实例的标准方法"""
        return cls()


# 单例全局实例
X = _X()


# ========== 单元测试 ==========
if __name__ == '__main__':
    # 测试1: 单例特性 - 多次调用返回同一实例
    instance1 = _X()
    instance2 = _X()
    print(f"Singleton test: instance1 is instance2 = {instance1 is instance2}")
    assert instance1 is instance2, "Singleton failed: instances are not the same"
    
    # 测试2: 单例特性 - X也是同一实例
    print(f"Singleton test: X is instance1 = {X is instance1}")
    assert X is instance1, "Singleton failed: X is not the same instance"
    
    # 测试3: X.strip == X.strip() 等值性
    print(f"X.strip == X.strip() = {X.strip == X.strip()}")
    assert X.strip == X.strip(), "X.strip != X.strip()"
    
    # 测试4: 多次访问 X.strip 返回同一对象
    wrapper1 = X.strip
    wrapper2 = X.strip
    print(f"X.strip is X.strip = {wrapper1 is wrapper2}")
    assert wrapper1 is wrapper2, "X.strip is not the same object on repeated access"
    
    # 测试5: X.strip() 返回的是正确的lambda
    strip_fn = X.strip()
    result = strip_fn('  hello  ')
    print(f"X.strip()('  hello  ') = '{result}'")
    assert result == 'hello', f"Expected 'hello', got '{result}'"
    
    # 测试6: X.strip(',') 带参数调用
    strip_with_arg = X.strip(',')
    result = strip_with_arg(',hello,')
    print(f"X.strip(',')(',hello,') = '{result}'")
    assert result == 'hello', f"Expected 'hello', got '{result}'"
    
    # 测试7: 带参数调用不影响缓存
    X.strip(',')
    result = X.strip()('  hello  ')
    print(f"After X.strip(','), X.strip()('  hello  ') = '{result}'")
    assert result == 'hello', "Parameterized call affected cached lambda"
    
    # 测试8: 其他方法
    print(f"X.upper == X.upper() = {X.upper == X.upper()}")
    assert X.upper == X.upper(), "X.upper != X.upper()"
    result = X.upper()('hello')
    print(f"X.upper()('hello') = '{result}'")
    assert result == 'HELLO', f"Expected 'HELLO', got '{result}'"
    
    # 测试9: split方法 - 无参版本使用空格分隔
    print(f"X.split == X.split() = {X.split == X.split()}")
    assert X.split == X.split(), "X.split != X.split()"
    result = X.split()('a b c')
    print(f"X.split()('a b c') = {result}")
    assert result == ['a', 'b', 'c'], f"Expected ['a', 'b', 'c'], got {result}"
    
    # 测试9b: split带参数
    split_with_arg = X.split(',')
    result = split_with_arg('a,b,c')
    print(f"X.split(',')('a,b,c') = {result}")
    assert result == ['a', 'b', 'c'], f"Expected ['a', 'b', 'c'], got {result}"
    
    # 测试10: replace方法 - 无参版本需要传递完整参数
    print(f"X.replace == X.replace() = {X.replace == X.replace()}")
    assert X.replace == X.replace(), "X.replace != X.replace()"
    result = X.replace()('hello', 'l', 'r')
    print(f"X.replace()('hello', 'l', 'r') = '{result}'")
    assert result == 'herro', f"Expected 'herro', got '{result}'"
    
    # 测试11: replace带参数
    replace_with_args = X.replace('l', 'r')
    result = replace_with_args('hello')
    print(f"X.replace('l', 'r')('hello') = '{result}'")
    assert result == 'herro', f"Expected 'herro', got '{result}'"
    
    # 测试12: 链式调用
    result = X('  hello  ').strip().val
    print(f"X('  hello  ').strip().val = '{result}'")
    assert result == 'hello', f"Expected 'hello', got '{result}'"
    
    # 测试13: 复杂链式调用
    result = X('  hello,world  ').strip().split(',').val
    print(f"X('  hello,world  ').strip().split(',').val = {result}")
    assert result == ['hello', 'world'], f"Expected ['hello', 'world'], got {result}"
    
    print("\nAll tests passed!")