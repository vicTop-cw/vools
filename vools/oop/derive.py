"""
类装饰器工厂：create_derive

通过复用 extend，为目标类批量扩展实例方法 / 静态方法 / 类方法 / 属性 / 描述符。

用法:
    create_derive(kind='instance')   # kind in ['static', 'property', 'class', 'instance', 'descriptor']

    derive = create_derive()                    # 默认 instance
    property_derive = create_derive('property')
    descriptor_derive = create_derive('descriptor')

    @derive(lambda self, x: self.x + x, ...)            # 位置参数：自动取函数名
    @derive(greet=lambda self, name: f"Hi {name}")      # 关键字参数：key 为方法别名

    # 可写属性：传入 (getter, setter) 或 (getter, setter, deleter) 元组
    @property_derive(x=(get_x, set_x))

    # 描述符：传入描述符实例或描述符类（自动用属性名实例化）
    @descriptor_derive(Typed('age', int))
    @descriptor_derive(age=Typed)    # 等价于 Typed(name='age')
    class Foo: ...
"""

import inspect
from functools import wraps
from typing import Any, Callable, Dict, Tuple, Union

from .method_extend import extend


def create_derive(kind: str = 'instance') -> Callable[..., Callable[[type], type]]:
    """
    创建一个类装饰器工厂。

    参数:
        kind: 扩展成员的类型
            - 'instance'   : 实例方法（默认）
            - 'static'     : 静态方法
            - 'class'      : 类方法
            - 'property'   : 属性（支持只读和可写）
            - 'descriptor' : 描述符（传入描述符实例或描述符类）

    返回:
        一个装饰器工厂 decorator_factory(*args, **kwargs) -> class_decorator，
        其中每个 arg / kwarg 都是可调用对象；关键字参数的 key 作为扩展成员的别名。

    可写属性:
        当 kind='property' 时，成员可以是 (getter, setter) 或 (getter, setter, deleter) 元组，
        用于创建可读写的 property。

    描述符:
        当 kind='descriptor' 时，成员可以是：
        - 描述符实例：直接挂载（__get__/__set__/__delete__）
        - 描述符类：自动用属性名实例化（调用 DescriptorClass(name=attr_name)）
    """
    if kind not in ('instance', 'static', 'property', 'class', 'descriptor'):
        raise ValueError(
            f"kind must be one of 'instance', 'static', 'property', 'class', 'descriptor', got {kind!r}"
        )

    method_type = 'instant' if kind == 'instance' else kind

    def decorator_factory(*args: Callable, **kwargs: Callable) -> Callable[[type], type]:
        # 收集 (name, func) 对：位置参数自动推断名称
        members: Dict[str, Callable] = {}

        for i, func in enumerate(args):
            if not callable(func) and not _is_descriptor(func):
                raise TypeError(f"create_derive positional arg {i} is not callable or descriptor")
            name = _infer_name(func, fallback=f"derived_{i}")
            if name in members:
                raise ValueError(f"duplicate derived member name {name!r}")
            members[name] = func

        for name, func in kwargs.items():
            if not callable(func) and not _is_property_tuple(func) and not _is_descriptor(func):
                raise TypeError(f"create_derive kwarg {name!r} is not callable, property tuple, or descriptor")
            if name in members:
                raise ValueError(f"duplicate derived member name {name!r}")
            members[name] = func

        def class_decorator(cls: type) -> type:
            if not inspect.isclass(cls):
                raise TypeError(f"create_derive decorator applies to classes, got {cls!r}")

            for name, func in members.items():
                if method_type == 'instant':
                    # 实例方法：直接挂载，由 Python 描述符协议自动绑定 self
                    setattr(cls, name, func)
                elif method_type == 'property':
                    # property：支持只读和可写
                    if _is_property_tuple(func):
                        # (getter, setter) 或 (getter, setter, deleter)
                        setattr(cls, name, property(*func))
                    else:
                        # 只读：func(self) -> value
                        setattr(cls, name, property(func))
                elif method_type == 'class':
                    # classmethod：func(cls, ...) -> value
                    setattr(cls, name, classmethod(func))
                elif method_type == 'static':
                    # staticmethod：func(...) -> value，复用 extend 的 static 类型转换
                    setattr(cls, name, extend(func, _method_type='static'))
                elif method_type == 'descriptor':
                    # 描述符：支持实例或类（自动实例化）
                    descriptor = _resolve_descriptor(func, name)
                    setattr(cls, name, descriptor)
            return cls

        return class_decorator

    return decorator_factory


def _is_property_tuple(func) -> bool:
    """检查是否为 property 元组 (getter, setter) 或 (getter, setter, deleter)"""
    if not isinstance(func, tuple):
        return False
    if len(func) not in (2, 3):
        return False
    # 所有元素都应该是 callable 或 None
    return all(c is None or callable(c) for c in func)


def _is_descriptor(func) -> bool:
    """检查是否为描述符（实现了 __get__/__set__/__delete__ 的对象或类）"""
    # 描述符实例：有 __get__ 方法
    if hasattr(func, '__get__'):
        return True
    # 描述符类：是 type 且有 __get__
    if isinstance(func, type) and hasattr(func, '__get__'):
        return True
    return False


def _resolve_descriptor(func, name: str):
    """解析描述符：如果是类则自动实例化，否则直接返回实例"""
    # 如果是类（type），尝试用 name= 实例化
    if isinstance(func, type):
        try:
            return func(name=name)
        except TypeError:
            # 如果构造函数不接受 name 参数，尝试无参实例化
            try:
                return func()
            except TypeError:
                raise TypeError(
                    f"Descriptor class {func.__name__} cannot be instantiated automatically. "
                    f"Please provide an instance instead."
                )
    # 否则直接返回描述符实例
    return func


def _infer_name(func: Callable, fallback: str) -> str:
    """从可调用对象推断一个合理的成员名。"""
    name = getattr(func, '__name__', '') or ''
    if name == '<lambda>':
        # 尝试从源码反推（仅用于命名，失败则回退）
        try:
            src = inspect.getsource(func)
            body = src.split('lambda', 1)[1]
            # 取参数部分直到 ':'
            params_part = body.split(':', 1)[0].strip()
            # 无参 lambda -> 回退
            if params_part:
                last = params_part.rsplit(',', 1)[-1].strip()
                candidate = last.split('=')[0].strip().strip('() ')
                # 排除纯 self/cls 这类无意义参数名
                if candidate and candidate.isidentifier() and candidate not in ('self', 'cls'):
                    return candidate
        except Exception:
            pass
        return fallback
    if not name or not name.isidentifier():
        return fallback
    return name


# ---- 预置常用装饰器 ----
derive: Callable[..., Callable[[type], type]] = create_derive('instance')
property_derive: Callable[..., Callable[[type], type]] = create_derive('property')
static_derive: Callable[..., Callable[[type], type]] = create_derive('static')
class_derive: Callable[..., Callable[[type], type]] = create_derive('class')
descriptor_derive: Callable[..., Callable[[type], type]] = create_derive('descriptor')


__all__ = [
    'create_derive',
    'derive',
    'property_derive',
    'static_derive',
    'class_derive',
    'descriptor_derive',
]
