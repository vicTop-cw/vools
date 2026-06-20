"""
函数扩展装饰器

包含：
- extend: 将外部函数扩展为类的实例方法
"""

from functools import wraps, partial
from typing import Callable, Any

__all__ = ['extend']


def extend(func: Callable, *fixed_args, _method_type: str = 'instant', **fixed_kwargs) -> Callable:
    """
    将外部函数扩展为类的实例方法，支持固定部分参数
    
    参数:
        func: 要扩展的外部函数
        *fixed_args: 要固定的位置参数，可以是值或属性名（字符串）
        **fixed_kwargs: 要固定的关键字参数，可以是值或属性名（字符串）
        _method_type: 方法类型，可选值为：
            - 'instant': 实例方法
            - 'static': 静态方法
            - 'class': 类方法
            - 'property': 属性
    
    返回:
        装饰后的函数
    
    示例:
        >>> def add(x, y, z=3):
        ...     return x + y + z
        
        >>> class Test:
        ...     def __init__(self, y):
        ...         self._y = y
        ...     
        ...     @property
        ...     def y(self):
        ...         return self._y
        ...     
        ...     # 固定第一个参数为 self.y 的值
        ...     add_method = extend(add, 'y', z=4)
        ...     
        ...     # 属性示例
        ...     add_property = extend(add, 1, 2, z=3, _method_type='property')
        
        >>> t = Test(10)
        >>> t.add_method(3)  # add(t.y, 3, z=4) = add(10, 3, z=4) = 17
        17
        >>> t.add_property  # add(1, 2, z=3) = 6
        6
    """
    def get_arg(obj, arg):
        """获取参数的实际值，如果是字符串且是对象的属性名，则返回属性值"""
        if isinstance(arg, str) and obj is not None:
            try:
                return getattr(obj, arg)
            except AttributeError:
                if '.' in arg:
                    parts = arg.split('.')
                    current_obj = obj
                    for part in parts:
                        try:
                            current_obj = getattr(current_obj, part)
                        except AttributeError:
                            return arg
                    return current_obj
                else:
                    return arg
        else:
            return arg
    
    if _method_type == 'instant':
        @wraps(func)
        def instant_wrapper(self, *args, **kwargs):
            resolved_args = [get_arg(self, arg) for arg in fixed_args]
            resolved_kwargs = {k: get_arg(self, v) for k, v in fixed_kwargs.items()}
            return func(*resolved_args, *args, **resolved_kwargs, **kwargs)
        return instant_wrapper
    
    elif _method_type == 'class':
        @wraps(func)
        def class_wrapper(cls, *args, **kwargs):
            resolved_args = [get_arg(cls, arg) for arg in fixed_args]
            resolved_kwargs = {k: get_arg(cls, v) for k, v in fixed_kwargs.items()}
            return func(*resolved_args, *args, **resolved_kwargs, **kwargs)
        return classmethod(class_wrapper)
    
    elif _method_type == 'static':
        @wraps(func)
        def static_wrapper(*args, **kwargs):
            resolved_args = [get_arg(None, arg) for arg in fixed_args]
            resolved_kwargs = {k: get_arg(None, v) for k, v in fixed_kwargs.items()}
            return func(*resolved_args, *args, **resolved_kwargs, **kwargs)
        return staticmethod(static_wrapper)
    
    elif _method_type == 'property':
        @wraps(func)
        def property_wrapper(self):
            resolved_args = [get_arg(self, arg) for arg in fixed_args]
            resolved_kwargs = {k: get_arg(self, v) for k, v in fixed_kwargs.items()}
            return func(*resolved_args, **resolved_kwargs)
        return property(property_wrapper)
    
    else:
        raise ValueError(f"_method_type must be 'instant', 'static', 'class', or 'property', got {_method_type}")


# ============================================================================
# 测试代码
# ============================================================================

if __name__ == "__main__":
    def add(x, y, z=3):
        """测试函数"""
        return x + y + z
    
    class Test:
        def __init__(self, y):
            self._y = y
        
        @property
        def y(self):
            """property示例"""
            return self._y
        
        @y.setter
        def y(self, value):
            self._y = value
        
        # 实例方法
        add_method = extend(add, 'y', z=4)
        
        # 属性
        add_property = extend(add, 1, 2, z=3, _method_type='property')
    
    print("=== 测试 extend ===")
    
    t = Test(10)
    
    # 测试实例方法
    result = t.add_method(3)
    print(f"实例方法结果: {result}")  # 10 + 3 + 4 = 17
    assert result == 17
    
    # 测试属性
    result = t.add_property
    print(f"属性结果: {result}")  # 1 + 2 + 3 = 6
    assert result == 6
    
    # 修改 property 的值并再次测试
    t.y = 20
    result = t.add_method(4)
    print(f"修改后实例方法结果: {result}")  # 20 + 4 + 4 = 28
    assert result == 28
    
    print("\n所有测试通过!")
