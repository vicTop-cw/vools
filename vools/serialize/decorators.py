"""
序列化装饰器模块

提供 @serialize, @deserialize, @serializable 等装饰器。
"""

from functools import wraps
from typing import Any, Callable, Optional, Type

from .core import Serializer
from .config import get_default_backend
from .callable import get_handler, serialize_callable, deserialize_callable
__all__ = ['serialize', 'deserialize', 'serializable', 'serialize_method', 'deserialize_method']


def serialize(backend: Optional[str] = None):
    """
    装饰器：自动序列化函数返回值

    优先使用对象的 __getstate__ 方法（新格式），
    回退到 handler 系统（旧 __callable__ 格式）。

    Args:
        backend: 序列化后端，默认使用全局配置

    Example:
        @serialize(backend='pickle')
        def get_data():
            return {"key": "value"}
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            be = backend or get_default_backend() or 'pickle'
            s = Serializer(backend=be)

            # 优先用 __getstate__（新格式），回退到 handler（旧格式）
            if hasattr(type(result), '__getstate__'):
                return s.dumps(result)
            handler = get_handler(result)
            if handler is not None:
                name, state = serialize_callable(result, s)
                return s.dumps({'__callable__': True, 'handler': name, 'state': state})
            else:
                return s.dumps(result)
        return wrapper
    return decorator


def deserialize(backend: Optional[str] = None):
    """
    装饰器：自动反序列化函数参数

    Args:
        backend: 反序列化后端，默认使用全局配置

    Example:
        @deserialize(backend='pickle')
        def process_data(data):
            return data
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 选择后端
            be = backend or get_default_backend() or 'pickle'
            s = Serializer(backend=be)

            # 反序列化 args 中的参数
            new_args = []
            for arg in args:
                if isinstance(arg, bytes):
                    try:
                        data = s.loads(arg)
                        if isinstance(data, dict) and data.get('__callable__'):
                            new_args.append(deserialize_callable(
                                data['handler'],
                                data['state'],
                                s
                            ))
                        else:
                            new_args.append(data)
                    except Exception:
                        new_args.append(arg)
                else:
                    new_args.append(arg)

            # 反序列化 kwargs 中的参数
            new_kwargs = {}
            for k, v in kwargs.items():
                if isinstance(v, bytes):
                    try:
                        data = s.loads(v)
                        if isinstance(data, dict) and data.get('__callable__'):
                            new_kwargs[k] = deserialize_callable(
                                data['handler'],
                                data['state'],
                                s
                            )
                        else:
                            new_kwargs[k] = data
                    except Exception:
                        new_kwargs[k] = v
                else:
                    new_kwargs[k] = v

            return func(*new_args, **new_kwargs)
        return wrapper
    return decorator


def serializable(backend: Optional[str] = None):
    """
    类装饰器：为类添加序列化/反序列化方法

    Args:
        backend: 序列化后端，默认使用全局配置

    Example:
        @serializable(backend='pickle')
        class MyData:
            def __init__(self, name: str):
                self.name = name
            
            def do(self, f=print, pre_f=None, sub_f=None):
                '''Apply a function for side effects, return self.
                
                Args:
                    f: Function to apply (default print)
                    pre_f: Pre-processing function
                    sub_f: Post-processing function (no return value expected)
                
                Returns:
                    self, for chaining
                '''
                rs = self
                if pre_f:
                    rs = pre_f(rs)
                rs = f(rs)
                if sub_f:
                    sub_f(rs)
                return self
    """
    def decorator(cls: Type) -> Type:
        be = backend or get_default_backend() or 'pickle'

        @classmethod
        def serialize_class(cls, instance):
            """序列化类实例"""
            s = Serializer(backend=be)
            return s.dumps(instance)

        @classmethod
        def deserialize_class(cls, data: bytes):
            """反序列化类实例"""
            s = Serializer(backend=be)
            return s.loads(data)

        # 添加方法
        cls.serialize = serialize_class
        cls.deserialize = deserialize_class

        return cls
    return decorator


def serialize_method(backend: Optional[str] = None):
    """
    实例方法装饰器：自动序列化方法返回值

    Args:
        backend: 序列化后端，默认使用全局配置

    Example:
        class MyService:
            @serialize_method
            
            def do(self, f=print, pre_f=None, sub_f=None):
                '''Apply a function for side effects, return self.
                
                Args:
                    f: Function to apply (default print)
                    pre_f: Pre-processing function
                    sub_f: Post-processing function (no return value expected)
                
                Returns:
                    self, for chaining
                '''
                rs = self
                if pre_f:
                    rs = pre_f(rs)
                rs = f(rs)
                if sub_f:
                    sub_f(rs)
                return self
            def get_state(self):
                return {"status": "ok"}
    """
    def decorator(method: Callable) -> Callable:
        @wraps(method)
        def wrapper(self, *args, **kwargs):
            result = method(self, *args, **kwargs)
            be = backend or get_default_backend() or 'pickle'
            s = Serializer(backend=be)

            if hasattr(type(result), '__getstate__'):
                return s.dumps(result)
            handler = get_handler(result)
            if handler is not None:
                name, state = serialize_callable(result, s)
                return s.dumps({'__callable__': True, 'handler': name, 'state': state})
            else:
                return s.dumps(result)
        return wrapper
    return decorator


def deserialize_method(backend: Optional[str] = None):
    """
    实例方法装饰器：自动反序列化方法参数

    Args:
        backend: 反序列化后端，默认使用全局配置

    Example:
        class MyService:
            @deserialize_method
            
            def do(self, f=print, pre_f=None, sub_f=None):
                '''Apply a function for side effects, return self.
                
                Args:
                    f: Function to apply (default print)
                    pre_f: Pre-processing function
                    sub_f: Post-processing function (no return value expected)
                
                Returns:
                    self, for chaining
                '''
                rs = self
                if pre_f:
                    rs = pre_f(rs)
                rs = f(rs)
                if sub_f:
                    sub_f(rs)
                return self
            def update_state(self, state):
                self._state = state
    """
    def decorator(method: Callable) -> Callable:
        @wraps(method)
        def wrapper(self, *args, **kwargs):
            be = backend or get_default_backend() or 'pickle'
            s = Serializer(backend=be)

            new_args = []
            for arg in args:
                if isinstance(arg, bytes):
                    try:
                        data = s.loads(arg)
                        if isinstance(data, dict) and data.get('__callable__'):
                            new_args.append(deserialize_callable(
                                data['handler'],
                                data['state'],
                                s
                            ))
                        else:
                            new_args.append(data)
                    except Exception:
                        new_args.append(arg)
                else:
                    new_args.append(arg)

            new_kwargs = {}
            for k, v in kwargs.items():
                if isinstance(v, bytes):
                    try:
                        data = s.loads(v)
                        if isinstance(data, dict) and data.get('__callable__'):
                            new_kwargs[k] = deserialize_callable(
                                data['handler'],
                                data['state'],
                                s
                            )
                        else:
                            new_kwargs[k] = data
                    except Exception:
                        new_kwargs[k] = v
                else:
                    new_kwargs[k] = v

            return method(self, *new_args, **new_kwargs)
        return wrapper
    return decorator