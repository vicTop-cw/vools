"""
类融合器模块 (Class Fusion Module) - 重构版

提供类级别的融合功能，将多个类融合生成新类，并自动处理返回类型转换。

核心功能：
1. 融合任意多个类生成新类
2. 将所有父类的方法复制到融合类（避免 __getattr__ 委托）
3. 方法返回父类实例时自动转换为融合类实例
4. 支持自定义方法修改或增加
5. 结合 @rself 装饰器的思想
"""

import functools
import types
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, Union

# 不可变类型列表（这些类型的初始化在 __new__ 中完成）
_IMMUTABLE_TYPES = (str, int, float, bool, tuple, bytes, frozenset)


def fuse_classes(
    *classes: Type,
    name: str = None,
    method_overrides: Dict[str, Callable] = None,
    method_wrappers: Dict[str, Dict[str, Any]] = None,
    auto_wrap_return: bool = False
) -> Type:
    """
    融合多个类生成新类
    
    参数：
        *classes: 要融合的类
        name: 新类的名称（可选）
        method_overrides: 方法重写字典 {方法名: 新方法}
        method_wrappers: 方法包装器字典 {方法名: {'before': fn, 'after': fn, 'replace': fn}}
        auto_wrap_return: 是否自动包装返回类型
    
    返回：
        融合后的新类
    """
    if not classes:
        raise ValueError("At least one class must be provided")
    
    if len(classes) == 1:
        return _apply_rself_if_available(classes[0])
    
    # 生成类名
    if name is None:
        name = 'Fused' + ''.join(cls.__name__ for cls in classes)
    
    # 确定基类：使用 object 作为基类（避免 MRO 冲突）
    # 所有父类的方法会被复制到新类中
    base_class = object
    
    # 检查是否包含不可变类型
    has_immutable = any(issubclass(cls, _IMMUTABLE_TYPES) for cls in classes)
    
    # 创建类字典
    class_dict = {}
    
    # 1. 添加 __new__（处理不可变类型）
    if has_immutable:
        # 找到第一个不可变类型作为主类型
        immutable_cls = next(cls for cls in classes if issubclass(cls, _IMMUTABLE_TYPES))
        
        def __new__(cls, *args, **kwargs):
            # 对于不可变类型，调用其 __new__
            instance = immutable_cls.__new__(cls, *args, **kwargs)
            return instance
        
        class_dict['__new__'] = __new__
    
    # 2. 添加 __init__
    def __init__(self, *args, **kwargs):
        # 调用所有父类的 __init__（如果它们存在且不是 object.__init__）
        for cls in classes:
            if '__init__' in cls.__dict__ and cls.__init__ is not object.__init__:
                try:
                    cls.__init__(self, *args, **kwargs)
                except TypeError:
                    # 如果参数不匹配，尝试无参调用
                    try:
                        cls.__init__(self)
                    except Exception:
                        pass
        
        # 对于不可变类型，__init__ 可能不会正确处理实例属性
        # 所以我们需要在 __init__ 之后，显式地设置实例属性
        # 这是通过遍历所有父类的 __dict__，找到实例属性并设置
        # 但更简单的方法是：在 __new__ 中存储额外的属性
        # 这里我们先不处理，因为比较复杂
    
    class_dict['__init__'] = __init__
    
    # 3. 添加 __repr__
    def __repr__(self) -> str:
        # 尝试使用第一个有 __repr__ 的父类
        for cls in classes:
            if '__repr__' in cls.__dict__:
                try:
                    return f"{type(self).__name__}({cls.__repr__(self)})"
                except Exception:
                    pass
        return f"{type(self).__name__}()"
    
    class_dict['__repr__'] = __repr__
    
    # 4. 使用 type() 动态创建类
    FusedClass = type(name, (base_class,), class_dict)
    
    # 5. 复制所有父类的方法到融合类
    _copy_methods_from_parents(FusedClass, classes)
    
    # 6. 应用方法重写
    if method_overrides:
        for method_name, method_impl in method_overrides.items():
            if callable(method_impl):
                setattr(FusedClass, method_name, method_impl)
            else:
                raise TypeError(f"method_overrides['{method_name}'] must be callable")
    
    # 7. 应用方法包装器
    if method_wrappers:
        for method_name, wrapper_config in method_wrappers.items():
            _apply_method_wrapper(FusedClass, method_name, wrapper_config)
    
    # 8. 自动包装返回类型（可选）
    if auto_wrap_return:
        FusedClass = _wrap_methods_for_return_type(FusedClass, classes)
    
    # 9. 尝试应用 @rself 装饰器
    # 注意：@rself 装饰器可能有 bug，暂时禁用
    # FusedClass = _apply_rself_if_available(FusedClass)
    
    return FusedClass


def _copy_methods_from_parents(FusedClass: Type, parent_classes: Tuple[Type, ...]) -> None:
    """
    将所有父类的方法复制到融合类
    
    这样，所有方法都在融合类中，可以正确应用方法包装器和返回类型转换。
    """
    for parent_cls in parent_classes:
        for attr_name in dir(parent_cls):
            # 跳过魔法方法（除了 __init__ 和 __repr__，它们已经在 class_dict 中定义了）
            if attr_name.startswith('__') and attr_name.endswith('__'):
                continue
            
            # 跳过已在融合类中定义的方法
            if attr_name in FusedClass.__dict__:
                continue
            
            # 获取属性
            try:
                attr = getattr(parent_cls, attr_name)
            except AttributeError:
                continue
            
            # 只复制可调用对象（方法、类方法、静态方法）
            if callable(attr):
                # 复制方法
                if isinstance(attr, types.MethodType):
                    # 实例方法（通过类访问时，是函数）
                    func = attr.__func__ if hasattr(attr, '__func__') else attr
                else:
                    func = attr
                
                # 使用默认参数捕获当前 func 的值（避免闭包捕获循环变量）
                def create_wrapper(f):
                    @functools.wraps(f)
                    def wrapped_method(self, *args, **kwargs):
                        return f(self, *args, **kwargs)
                    return wrapped_method
                
                wrapped_method = create_wrapper(func)
                setattr(FusedClass, attr_name, wrapped_method)


def _apply_rself_if_available(cls: Type) -> Type:
    """尝试为类应用 @rself 装饰器"""
    try:
        from vools.decorators.rself import rself as rself_decorator
        return rself_decorator(cls)
    except (ImportError, TypeError):
        pass
    
    return cls


def _wrap_methods_for_return_type(cls: Type, fused_classes: Tuple[Type, ...]) -> Type:
    """
    包装类的方法，自动转换返回类型
    
    遍历类的所有方法，如果方法返回值是任何融合类的父类实例，
    则转换为融合类实例。
    """
    # 获取所有需要包装的方法
    methods_to_wrap = []
    
    for attr_name in dir(cls):
        # 跳过魔法方法
        if attr_name.startswith('__') and attr_name.endswith('__'):
            continue
        
        # 只包装在类中定义的方法
        if attr_name not in cls.__dict__:
            continue
        
        try:
            attr = getattr(cls, attr_name)
            if callable(attr) and not isinstance(attr, type):
                methods_to_wrap.append(attr_name)
        except AttributeError:
            continue
    
    # 包装每个方法
    for method_name in methods_to_wrap:
        original_method = getattr(cls, method_name)
        
        @functools.wraps(original_method)
        def wrapped_method(self, *args, **kwargs):
            result = original_method(self, *args, **kwargs)
            
            # 检查返回值是否需要转换
            for parent_cls in fused_classes:
                if isinstance(result, parent_cls) and type(result) is not type(self):
                    # 需要转换：创建新的融合类实例
                    try:
                        return type(self)(result)
                    except Exception:
                        # 如果转换失败，返回原结果
                        return result
            
            return result
        
        # 替换原方法
        setattr(cls, method_name, wrapped_method)
    
    return cls


def _apply_method_wrapper(cls: Type, method_name: str, wrapper_config: Dict[str, Any]) -> None:
    """
    为指定方法应用包装器
    
    wrapper_config 可以包含：
    - 'before': 在方法调用前执行的函数
    - 'after': 在方法调用后执行的函数，接收结果作为参数
    - 'replace': 完全替换原方法
    """
    if wrapper_config.get('replace') is not None:
        # 完全替换方法
        setattr(cls, method_name, wrapper_config['replace'])
        return
    
    original_method = getattr(cls, method_name, None)
    if original_method is None:
        raise AttributeError(f"Method '{method_name}' not found in class {cls.__name__}")
    
    before_fn = wrapper_config.get('before')
    after_fn = wrapper_config.get('after')
    
    @functools.wraps(original_method)
    def wrapped_method(self, *args, **kwargs):
        # 执行 before 函数
        if before_fn:
            before_fn(self, *args, **kwargs)
        
        # 调用原方法
        result = original_method(self, *args, **kwargs)
        
        # 执行 after 函数
        if after_fn:
            result = after_fn(self, result)
        
        return result
    
    setattr(cls, method_name, wrapped_method)


class ClassFusion:
    """
    类融合器（面向对象接口）
    
    提供更灵活的类融合功能，支持多次融合和方法定制。
    """
    
    def __init__(self, *classes: Type):
        self._classes = list(classes)
        self._method_overrides = {}
        self._method_wrappers = {}
        self._class_name = None
        self._auto_wrap_return = False
        self._fused_class = None
    
    def add_class(self, cls: Type) -> 'ClassFusion':
        """添加要融合的类"""
        self._classes.append(cls)
        self._fused_class = None
        return self
    
    def override_method(self, name: str, impl: Callable) -> 'ClassFusion':
        """重写方法"""
        self._method_overrides[name] = impl
        return self
    
    def wrap_method(
        self,
        name: str,
        before: Callable = None,
        after: Callable = None,
        replace: Callable = None
    ) -> 'ClassFusion':
        """包装方法"""
        self._method_wrappers[name] = {
            'before': before,
            'after': after,
            'replace': replace
        }
        return self
    
    def set_name(self, name: str) -> 'ClassFusion':
        """设置融合类的名称"""
        self._class_name = name
        return self
    
    def set_auto_wrap_return(self, enabled: bool) -> 'ClassFusion':
        """设置是否自动包装返回类型"""
        self._auto_wrap_return = enabled
        return self
    
    def fuse(self) -> Type:
        """执行融合，返回融合后的类"""
        if self._fused_class is None:
            self._fused_class = fuse_classes(
                *self._classes,
                name=self._class_name,
                method_overrides=self._method_overrides,
                method_wrappers=self._method_wrappers,
                auto_wrap_return=self._auto_wrap_return
            )
        return self._fused_class
    
    def __call__(self, *args, **kwargs) -> Any:
        """创建融合类的实例"""
        fused_class = self.fuse()
        return fused_class(*args, **kwargs)


# 导出
__all__ = ['fuse_classes', 'ClassFusion']
