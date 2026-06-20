"""
overcurry 装饰器模块

提供基于 curry 的函数重载功能，结合了 curry 和 overload 的特性。
基于 selector.py 中的 Overloads 实现。
"""

from inspect import signature, Parameter, isfunction, isclass
from typing import get_type_hints, Any, Callable, Optional, List, Tuple, Union, Dict

from .curry_core import curry, Curried, CurryDescriptor, is_curried
from .selector import Overloads

__all__ = ['overcurry', 'OvercurryManager']


class OvercurryManager:
    """overcurry 管理器类，基于 Overloads 实现"""
    def __init__(self, *funcs, delaied=False, is_strict=False):
        """
        初始化 overcurry 管理器
        
        参数:
            *funcs: 要注册的函数
            delaied: 是否延迟调用
            is_strict: 是否使用严格模式（类型检查）
        """
        # 对每个函数进行 curry 处理
        curried_funcs = []
        for func in funcs:
            if not is_curried(func):
                curried_func = curry(func, is_strict=is_strict, delaied=delaied)
                curried_funcs.append(curried_func)
            else:
                curried_funcs.append(func)
        
        # 创建 Overloads 对象
        self.overloads = Overloads(*curried_funcs, delaied=delaied)
        self.delaied = delaied
        self.is_strict = is_strict
    
    def __call__(self, *args, **kwargs) -> Any:
        """执行重载函数调用"""
        try:
            # 调用 Overloads 对象的 __call__ 方法
            result = self.overloads(*args, **kwargs)
            
            # 检查结果是否已经是一个非可调用的普通值（如整数、字符串等）
            if not callable(result):
                return result
            
            # 如果返回的是 Overloads 对象，将其转换为 OvercurryManager 对象
            if isinstance(result, Overloads):
                # 检查 result.funcs 是否只有一个元素
                if len(result.funcs) == 1:
                    # 检查这个元素是否是一个已经准备好执行的 Curried 对象
                    if is_curried(result.funcs[0]):
                        is_ready = getattr(result.funcs[0], 'is_ready', False)
                        if is_ready:
                            # 如果已经有足够的参数，执行函数并返回结果
                            return result.funcs[0]()
                    # 检查这个元素是否是一个非可调用的普通值（如整数、字符串等）
                    elif not callable(result.funcs[0]):
                        return result.funcs[0]
                # 检查 result.funcs 中是否有非可调用的普通值（如整数、字符串等）
                non_callable_funcs = [f for f in result.funcs if not callable(f)]
                if non_callable_funcs:
                    # 如果有非可调用的普通值，返回第一个
                    return non_callable_funcs[0]
                # 检查 result.funcs 中的元素是否都是可调用的
                callable_funcs = [f for f in result.funcs if callable(f)]
                if callable_funcs:
                    return OvercurryManager(*callable_funcs, delaied=self.delaied, is_strict=self.is_strict)
                else:
                    # 如果没有可调用的函数，返回第一个结果
                    return result.funcs[0] if result.funcs else None
            
            # 如果返回的是 Curried 或 CurryDescriptor 对象
            if is_curried(result):
                # 检查是否已经有足够的参数（is_ready 为 True）
                # 注意：我们需要检查 result 对象是否有 is_ready 属性
                is_ready = getattr(result, 'is_ready', False)
                
                if is_ready:
                    # 如果已经有足够的参数，执行函数并返回结果
                    return result()
                else:
                    # 如果没有足够的参数，将其包装在一个新的 OvercurryManager 对象中返回
                    return OvercurryManager(result, delaied=self.delaied, is_strict=self.is_strict)
            
            # 否则，直接返回结果
            return result
        except TypeError as e:
            # 处理类型错误，例如当尝试对非可调用对象进行 curry 处理时
            if "func must be a callable object" in str(e):
                # 如果是因为非可调用对象导致的错误，尝试直接返回结果
                # 这里我们假设 args 和 kwargs 已经足够调用一个重载函数
                # 并且该函数已经返回了一个结果
                # 我们可以尝试直接调用第一个注册的函数
                if hasattr(self.overloads, 'funcs') and self.overloads.funcs:
                    first_func = self.overloads.funcs[0]
                    try:
                        return first_func(*args, **kwargs)
                    except:
                        pass
            raise
    
    def register(self, func: Optional[Callable] = None, 
                returnOverload: bool = False) -> Union[Callable, 'OvercurryManager']:
        """
        注册重载函数（支持作为装饰器使用）
        
        参数:
            func: 要注册的函数
            returnOverload: 是否返回 Overload 对象
        """
        if func is None:
            def decorator(f: Callable) -> 'OvercurryManager':
                # 对函数进行 curry 处理
                if not is_curried(f):
                    curried_func = curry(f, is_strict=self.is_strict, delaied=self.delaied)
                else:
                    curried_func = f
                # 调用 Overloads 对象的 register 方法
                self.overloads.register(curried_func, returnOverload=returnOverload)
                # 返回 self，而不是返回 Overloads.register 方法的结果
                return self
            return decorator
        
        # 对函数进行 curry 处理
        if not is_curried(func):
            curried_func = curry(func, is_strict=self.is_strict, delaied=self.delaied)
        else:
            curried_func = func
        # 调用 Overloads 对象的 register 方法
        self.overloads.register(curried_func, returnOverload=returnOverload)
        # 返回 self，而不是返回 Overloads.register 方法的结果
        return self


def overcurry(func: Optional[Callable] = None, 
             *funcs: Callable, 
             is_strict: bool = False, 
             delaied: bool = False) -> Any:
    """
    overcurry 装饰器，结合了 curry 和 overload 的特性
    基于 selector.py 中的 Overloads 实现
    
    参数:
        func: 主函数
        *funcs: 额外的重载函数
        is_strict: 是否使用严格类型检查
        delaied: 是否延迟调用
    
    返回:
        OvercurryManager 实例
    
    示例:
        >>> @overcurry
        ... def add(a, b):
        ...     return a + b
        ...
        >>> @add.register
        ... def add(a, b, c):
        ...     return a + b + c
        ...
        >>> add(1)(2)  # 3
        >>> add(1)(2)(3)  # 6
    """
    # 处理装饰器参数
    if func is None:
        # 带参数的情况：@overcurry(is_strict=True)
        def decorator(f: Callable) -> OvercurryManager:
            return OvercurryManager(f, delaied=delaied, is_strict=is_strict)
        return decorator
    
    if isinstance(func, Callable) and not funcs:
        # 无参数情况：@overcurry
        return OvercurryManager(func, delaied=delaied, is_strict=is_strict)
    
    # 多函数注册：@overcurry(func1, func2)
    return OvercurryManager(func, *funcs, delaied=delaied, is_strict=is_strict)
