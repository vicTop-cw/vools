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

from ..core.base import VoolsBase

# 不可变类型列表（这些类型的初始化在 __new__ 中完成）
_IMMUTABLE_TYPES = (str, int, float, bool, tuple, bytes, frozenset)


def _copy_class_attributes_from_parents(fused_cls: Type, classes: tuple) -> None:
    """把父类的**类属性**复制到融合类（BUG-421）。

    原实现只调用 :func:`_copy_methods_from_parents`——类属性（``x = 1``）在
    融合后**静默消失**：``fuse_classes(A, B)`` 得到的类没有 ``A.x``，也
    不抛任何错误。

    复制规则（与原方法优先级一致：先出现的类优先）：

    * 只处理**直接定义**在父类 ``__dict__`` 中的属性（不递归继承）；
    * 跳过 dunder（``__init__``/``__doc__``/``__slots__`` 等）；
    * 跳过可调用对象（方法由方法复制逻辑处理，且其优先级更高）；
    * 同名属性先出现者优先。

    注意：本函数**必须在方法复制之后调用**——方法优先于类属性，否则同名
    属性会占用名字导致方法无法复制。
    """
    skip = {"__doc__", "__module__", "__qualname__", "__dict__", "__weakref__",
            "__slots__", "__annotations__"}
    for cls in classes:
        try:
            cls_dict = vars(cls)
        except TypeError:
            continue
        for name, value in cls_dict.items():
            if name.startswith("__") or name in skip:
                continue
            if callable(value):
                continue          # 方法稍后由方法复制逻辑处理
            if name in fused_cls.__dict__:
                continue          # 先出现的类优先
            try:
                setattr(fused_cls, name, value)
            except Exception:
                continue


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
    
    if len(classes) == 1 and not (name or method_overrides or method_wrappers or auto_wrap_return):
        return _apply_rself_if_available(classes[0])
    
    # 生成类名
    if name is None:
        name = 'Fused' + ''.join(cls.__name__ for cls in classes)
    
    # 确定基类：使用 object 作为基类（避免 MRO 冲突）
    # 所有父类的方法会被复制到新类中
    # 确定基类：
    #  - 普通类用 object 作为基类（避免 MRO 冲突），所有父类方法会被复制到新类中；
    #  - 含不可变类型时必须以该不可变类型为基类，否则下方
    #    `immutable_cls.__new__(cls, ...)` 会因 cls 不是该类型的子类而抛
    #    TypeError（BUG-182，实测 int/str/bytes 全部崩）。
    has_immutable = any(issubclass(cls, _IMMUTABLE_TYPES) for cls in classes)
    if has_immutable:
        base_class = next(cls for cls in classes if issubclass(cls, _IMMUTABLE_TYPES))
    else:
        base_class = object
    
    # 检查是否包含不可变类型
    has_immutable = any(issubclass(cls, _IMMUTABLE_TYPES) for cls in classes)
    
    # 创建类字典
    class_dict = {}
    
    # 1. 添加 __new__（处理不可变类型）
    if has_immutable:
        # 找到第一个不可变类型作为主类型
        immutable_cls = base_class
        
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
    
    # 5. 复制所有父类的方法到融合类（先复制，方法优先）
    _copy_methods_from_parents(FusedClass, classes)

    # 5.1 复制父类的类属性（BUG-421）：同名属性跳过，已复制的方法优先
    _copy_class_attributes_from_parents(FusedClass, classes)
    
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
        from ..decorators.rself import rself as rself_decorator
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

        # 用默认参数捕获当前 original_method，避免闭包捕获循环变量
        def _make_wrapper(orig_method):
            @functools.wraps(orig_method)
            def wrapped_method(self, *args, **kwargs):
                result = orig_method(self, *args, **kwargs)

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
            return wrapped_method

        setattr(cls, method_name, _make_wrapper(original_method))
    
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


class ClassFusion(VoolsBase):
    """
    类融合器（面向对象接口）
    
    提供更灵活的类融合功能，支持多次融合和方法定制。
    """
    
    def __init__(self, *classes: Type):
        # BUG-423: 非类会一路走到 fuse() 才抛 ValueError（“At least one class
        # must be provided”），错误信息完全指不到构造参数。
        for cls in classes:
            if not isinstance(cls, type):
                raise TypeError(
                    f"ClassFusion() 只接受类，收到 {type(cls).__name__}: {cls!r}")
        self._classes = list(classes)
        self._method_overrides = {}
        self._method_wrappers = {}
        self._class_name = None
        self._auto_wrap_return = False
        self._fused_class = None

    def __getstate__(self):
        """返回序列化状态"""
        return {
            '_classes': self._classes,
            '_method_overrides': self._method_overrides,
            '_method_wrappers': self._method_wrappers,
            '_class_name': self._class_name,
            '_auto_wrap_return': self._auto_wrap_return,
        }

    def __setstate__(self, state):
        """从序列化状态恢复"""
        for k in ('_classes', '_method_overrides', '_method_wrappers'):
            setattr(self, k, state[k])
        # BUG-154: 旧 __getstate__ 未存这两项，反序列化后 fuse() 抛 AttributeError。
        # 用 get 容错：老状态回退默认值。
        self._class_name = state.get('_class_name', None)
        self._auto_wrap_return = state.get('_auto_wrap_return', False)
        self._fused_class = None

    def add_class(self, cls: Type) -> 'ClassFusion':
        """添加要融合的类"""
        # BUG-423: 非类会一路走到 fuse() 才抛 ValueError（“At least one class
        # must be provided”），错误信息完全指不到 add_class。
        if not isinstance(cls, type):
            raise TypeError(
                f"add_class() 需要类，收到 {type(cls).__name__}: {cls!r}")
        self._classes.append(cls)
        self._fused_class = None
        return self
    
    def override_method(self, name: str, impl: Callable) -> 'ClassFusion':
        """重写方法（BUG-423：入口即时校验，不再等到 fuse() 才报错）。"""
        if not callable(impl):
            raise TypeError(
                f"override_method({name!r}) 的 impl 必须可调用，收到 "
                f"{type(impl).__name__}: {impl!r}")
        self._method_overrides[name] = impl
        return self
    
    def wrap_method(
        self,
        name: str,
        before: Callable = None,
        after: Callable = None,
        replace: Callable = None
    ) -> 'ClassFusion':
        """包装方法（BUG-423：入口校验，避免 silent no-op 与晚到的天书错误）。

        校验内容：

        * ``before``/``after``/``replace`` 一旦提供必须**可调用**
          （原实现会等到 ``fuse()`` 阶段抛 ``'str' object is not callable``）；
        * 三个回调**至少提供一个**（原实现 `wrap_method('m')` 会静默 no-op，
          调用方以为包装生效）；
        * 若已注册类中存在 ``name`` 方法则要求存在（原实现会在融合后抛
          ``Method 'nope' not found``，且错误发生在较晚阶段）；
          尚未 ``add_class`` 时无法校验，仅做回调校验。
        """
        for label, fn in (("before", before), ("after", after), ("replace", replace)):
            if fn is not None and not callable(fn):
                raise TypeError(
                    f"wrap_method({name!r}) 的 {label} 必须可调用，收到 "
                    f"{type(fn).__name__}: {fn!r}")
        if before is None and after is None and replace is None:
            raise ValueError(
                f"wrap_method({name!r}) 至少需要提供 before/after/replace 之一，"
                f"否则是无效的 no-op")
        if self._classes:
            defined = any(name in vars(cls) for cls in self._classes)
            if not defined:
                known = sorted({k for cls in self._classes for k in vars(cls)
                                if not k.startswith('__')})
                raise ValueError(
                    f"wrap_method({name!r}) 未在已注册的类中找到该方法；可用方法："
                    f"{known}")
        self._method_wrappers[name] = {
            'before': before,
            'after': after,
            'replace': replace
        }
        return self
    
    def set_name(self, name: str) -> 'ClassFusion':
        """设置融合类的名称（BUG-424：入口校验，不再等到 type() 才报错）。"""
        # 原实现把任意值塞进 _class_name，fuse() 时抛
        # ``TypeError: type.__new__() argument 1 must be str, not int``——
        # 错误发生在融合阶段，且完全看不出是 set_name 传错。
        if not isinstance(name, str):
            raise TypeError(
                f"set_name() 需要 str，收到 {type(name).__name__}: {name!r}")
        if not name.strip():
            raise ValueError("set_name() 需要非空字符串作为类名")
        self._class_name = name
        return self
    
    def set_auto_wrap_return(self, enabled: bool) -> 'ClassFusion':
        """设置是否自动包装返回类型（BUG-424：入口校验）。

        原实现接受任意值：``set_auto_wrap_return('x')`` 会被**静默当成 True**
        （非空字符串为真），调用方无法察觉参数类型错误。
        """
        if isinstance(enabled, bool) is False:
            raise TypeError(
                f"set_auto_wrap_return() 需要 bool，收到 "
                f"{type(enabled).__name__}: {enabled!r}")
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
