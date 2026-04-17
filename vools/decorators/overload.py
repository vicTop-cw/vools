"""
函数重载装饰器模块

提供函数重载功能，支持：
- 基于参数数量的重载
- 基于参数类型的重载（严格模式）
- 优先级控制
- 类方法支持

示例:
    >>> @overload
    ... def process():
    ...     return "无参数"
    ...
    >>> @process.register
    ... def process(x: int):
    ...     return f"一个参数: {x}"
    ...
    >>> process()          # "无参数"
    >>> process(10)        # "一个参数: 10"
"""

import inspect
import types
from functools import wraps
from typing import Any, Callable, Optional, List, Tuple, Union, Dict
import typing

from .curry_core import is_curried, Curried

__all__ = ['overload', 'OverloadManager', 'strict']


def strict(func):
    """严格类型检查装饰器
    
    在函数执行前检查参数类型是否符合类型注解。
    
    参数:
        func: 要检查的函数
    
    返回:
        包装后的函数
    
    示例:
        >>> @strict
        ... def add(a: int, b: int) -> int:
        ...     return a + b
        ...
        >>> add(1, 2)      # 3
        >>> add(1, "2")    # TypeError
    """
    sig = inspect.signature(func)
    annotations = func.__annotations__
    
    @wraps(func)
    def wrapper(*args, **kwargs):
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()
        
        for name, value in bound.arguments.items():
            if name in annotations:
                expected_type = annotations[name]
                if not isinstance(value, expected_type):
                    raise TypeError(
                        f"参数 '{name}' 应为 {expected_type.__name__} 类型，"
                        f"实际传入 {type(value).__name__} 类型"
                    )
        
        return func(*args, **kwargs)
    return wrapper


class OverloadManager:
    """重载管理器类
    
    支持多种匹配模式和优先级控制。
    
    属性:
        overloads: 已注册的重载函数列表
        main_func: 主函数
        is_strict: 是否使用严格模式（类型检查）
        global_priority: 全局优先级 ('first' 或 'last')
    """
    
    def __init__(self, main_func: Optional[Callable] = None, is_strict: bool = False, global_priority: str = 'last'):
        """
        初始化重载管理器
        
        参数:
            main_func: 主函数
            is_strict: 是否使用严格模式（类型检查）
            global_priority: 全局优先级 ('first' 或 'last')
        """
        self.overloads: List[Tuple[Callable, Optional[Callable], int, int]] = []
        self.main_func = main_func
        self.is_strict = is_strict
        self.global_priority = global_priority
        self.counter = 0  # 注册计数器，保证注册顺序
        
        if main_func:
            # 为主函数自动创建检查函数并注册
            priority_value = -10**9 if global_priority == 'first' else 10**9
            self.register(main_func, priority=priority_value)
    
    def __get__(self, instance, owner):
        """描述符协议，支持类方法绑定"""
        if instance is None:
            return self
        return types.MethodType(self, instance)
    
    def register(self, func: Optional[Callable] = None, 
                check: Optional[Callable] = None, 
                priority: Optional[int] = None) -> Union[Callable, 'OverloadManager']:
        """
        注册重载函数（支持作为装饰器使用）
        
        参数:
            func: 要注册的函数
            check: 自定义检查函数
            priority: 优先级（数值越大优先级越高）
        
        返回:
            装饰器或管理器本身
        
        示例:
            >>> @manager.register
            ... def func1(x: int):
            ...     return x
            ...
            >>> @manager.register(priority=10)
            ... def func2(x: str):
            ...     return x
        """
        # 装饰器用法：@manager.register 或 @manager.register(priority=1)
        if func is None:
            def decorator(f: Callable) -> Callable:
                self._register_function(f, check, priority)
                return f
            return decorator
        
        # 直接调用注册
        self._register_function(func, check, priority)
        return self
    
    def _register_function(self, func: Callable, 
                          check: Optional[Callable] = None, 
                          priority: Optional[int] = None) -> None:
        """内部注册函数实现"""
        # 设置默认优先级
        if priority is None:
            priority = 0
        
        # 自动创建检查函数（如果未提供）
        if check is None:
            if self.is_strict:
                check = self._create_strict_check(func)
            else:
                # 普通模式使用参数数量检查
                check = self._create_count_check(func)
        
        # 记录注册顺序并保存
        reg_index = self.counter
        self.counter += 1
        self.overloads.append((check, func, priority, reg_index))
        
        # 设置第一个注册的函数为主函数
        if self.main_func is None:
            self.main_func = func
    
    def _create_count_check(self, func: Callable) -> Callable:
        """创建基于参数数量的检查函数"""
        # 检查函数是否已经被柯里化
        if is_curried(func):
            # 从柯里化对象中获取原始函数
            if hasattr(func, 'func'):
                func = func.func
        
        sig = inspect.signature(func)
        params = sig.parameters
        
        # 计算必需参数数量
        min_args = sum(1 for p in params.values()
                      if p.default == p.empty
                      and p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD))
        
        # 处理可变参数
        has_var_args = any(p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
                      for p in params.values())
        max_args = float('inf') if has_var_args else len(params)
        
        def count_check(args, kwargs):
            arg_count = len(args) + len(kwargs)
            return min_args <= arg_count <= max_args
        
        return count_check
    
    def _create_strict_check(self, func: Callable) -> Callable:
        """创建严格的类型检查函数，包含详细的错误信息"""
        # 检查函数是否已经被柯里化
        if is_curried(func):
            # 从柯里化对象中获取原始函数
            if hasattr(func, 'func'):
                func = func.func
        
        sig = inspect.signature(func)
        type_hints = func.__annotations__
        params = sig.parameters
        
        def strict_check(args, kwargs):
            # 第一步：验证参数存在性（位置和名称匹配）
            try:
                bound = sig.bind(*args, **kwargs)
                bound.apply_defaults()
            except TypeError as e:
                # 捕获并重新包装错误信息
                return False, f"参数不匹配: {str(e)}"
            
            # 第二步：检查类型是否符合注解
            errors = []
            for name, value in bound.arguments.items():
                if name in type_hints:
                    expected_type = type_hints[name]
                    param = params[name]
                    
                    # 处理可变位置参数 (*args)
                    if param.kind == inspect.Parameter.VAR_POSITIONAL:
                        for i, item in enumerate(value):
                            if not isinstance(item, expected_type):
                                errors.append(
                                    f"位置参数 #{i} (属于*{name}) 类型错误: "
                                    f"期望 {expected_type.__name__}, 实际 {type(item).__name__}"
                                )
                    
                    # 处理可变关键字参数 (**kwargs)
                    elif param.kind == inspect.Parameter.VAR_KEYWORD:
                        for key, item in value.items():
                            if not isinstance(item, expected_type):
                                errors.append(
                                    f"关键字参数 '{key}' (属于**{name}) 类型错误: "
                                    f"期望 {expected_type.__name__}, 实际 {type(item).__name__}"
                                )
                    
                    # 处理普通参数
                    else:
                        # 检查字典类型的键值对
                        if isinstance(value, dict) and hasattr(expected_type, '__args__'):
                            origin_type = getattr(typing, 'get_origin', None)
                            if origin_type and origin_type(expected_type) is dict:
                                key_type, val_type = typing.get_args(expected_type)
                                for k, v in value.items():
                                    if not isinstance(k, key_type):
                                        errors.append(
                                            f"参数 '{name}' 的键 '{k}' 类型错误: "
                                            f"期望 {key_type.__name__}, 实际 {type(k).__name__}"
                                        )
                                    if not isinstance(v, val_type):
                                        errors.append(
                                            f"参数 '{name}' 的值 '{v}' 类型错误: "
                                            f"期望 {val_type.__name__}, 实际 {type(v).__name__}"
                                        )
                                continue
                        
                        # 普通类型检查
                        if not isinstance(value, expected_type):
                            errors.append(
                                f"参数 '{name}' 类型错误: "
                                f"期望 {expected_type.__name__}, 实际 {type(value).__name__}"
                            )
            
            if errors:
                return False, " | ".join(errors)
            return True, None
        
        return strict_check
    
    def __call__(self, *args, **kwargs) -> Any:
        """执行重载函数调用
        
        按优先级排序后尝试匹配函数执行。
        """
        # 按优先级排序：先按priority值降序（数值大的优先级高），再按注册顺序升序
        sorted_overloads = sorted(self.overloads, key=lambda x: (-x[2], x[3]))
        
        # 尝试匹配函数
        for check, func, _, _ in sorted_overloads:
            try:
                if not self.is_strict:
                    # 普通模式：尝试执行函数
                    return func(*args, **kwargs)
                else:
                    # 严格模式：使用检查函数
                    is_valid, error_msg = check(args, kwargs)
                    if is_valid:
                        return func(*args, **kwargs)
                    else:
                        # 记录错误信息但继续尝试其他重载
                        last_error = error_msg
            except (TypeError, ValueError) as e:
                # 忽略参数不匹配的错误
                last_error = str(e)
                continue
        
        # 没有匹配的函数
        if self.main_func:
            try:
                return self.main_func(*args, **kwargs)
            except Exception as e:
                # 添加详细的错误信息
                if 'last_error' in locals():
                    raise TypeError(f"没有找到匹配的重载函数: {last_error}") from e
                else:
                    raise TypeError("没有找到匹配的重载函数") from e
        
        # 添加详细的错误信息
        if 'last_error' in locals():
            raise TypeError(f"没有找到匹配的重载函数: {last_error}")
        else:
            raise TypeError("没有找到匹配的重载函数")
    
    @classmethod
    def create(cls) -> 'OverloadManager':
        """创建新的重载管理器实例"""
        return cls()


def overload(func: Optional[Callable] = None, 
            *funcs: Callable, 
            is_strict: bool = False, 
            priority: str = 'last', 
            check: Optional[Callable] = None) -> Any:
    """
    高效的重载装饰器，支持多种模式和优先级
    
    参数:
        func: 主函数
        *funcs: 额外的重载函数
        is_strict: 是否使用严格类型检查
        priority: 全局优先级 ('first' 或 'last')
        check: 自定义参数匹配规则
    
    返回:
        OverloadManager 实例
    
    使用方式1:
        >>> @overload
        ... def main_func():
        ...     return "无参数"
        ...
        >>> @main_func.register
        ... def func1(x):
        ...     return f"一个参数: {x}"
    
    使用方式2:
        >>> @overload(is_strict=True, priority='first')
        ... def main_func():
        ...     return "无参数"
    
    使用方式3:
        >>> @overload(func1, func2)
        ... def main_func():
        ...     return "无参数"
    """
    # 处理装饰器参数
    if func is None:
        # 带参数的情况：@overload(is_strict=True)
        def decorator(f: Callable) -> OverloadManager:
            manager = OverloadManager(is_strict=is_strict, global_priority=priority)
            main_priority = -10**9 if priority == 'first' else 10**9
            manager.register(f, check=check, priority=main_priority)
            return manager
        return decorator
    
    if isinstance(func, Callable) and not funcs:
        # 无参数情况：@overload
        manager = OverloadManager(is_strict=is_strict, global_priority=priority)
        main_priority = -10**9 if priority == 'first' else 10**9
        manager.register(func, check=check, priority=main_priority)
        return manager
    
    # 多函数注册：@overload(func1, func2)
    manager = OverloadManager(is_strict=is_strict, global_priority=priority)
    main_priority = -10**9 if priority == 'first' else 10**9
    manager.register(func, check=check, priority=main_priority)
    for f in funcs:
        manager.register(f, check=check)
    return manager
