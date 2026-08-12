"""
标准柯里化装饰器

提供柯里化功能的装饰器，支持普通函数、实例方法、类方法和静态方法的柯里化。

柯里化是将接受多个参数的函数转换为一系列接受单个参数的函数的过程，
使得函数可以部分应用参数并返回新的函数。

示例:
    >>> @curry
    ... def add(a, b, c):
    ...     return a + b + c
    ...
    >>> add(1)(2)(3)
    6
    >>> add(1, 2)(3)
    6
    >>> add(1)(2, 3)
    6
"""

from inspect import signature, Parameter, isfunction, isclass, Signature
from typing import get_type_hints, Any, Callable, Dict, Optional, TypeVar, Union, Tuple

from functools import lru_cache

__all__ = ['curry', 'Curried', 'CurryDescriptor', 'is_curried', 'CurryExecutionError']

F = TypeVar('F', bound=Callable[..., Any])

is_curried = lambda x: isinstance(x, (Curried, CurryDescriptor))


@lru_cache(maxsize=512)
def _get_cached_signature(func: Callable[..., Any]) -> Signature:
    """获取函数的签名并缓存结果。
    
    Args:
        func: 要获取签名的函数
        
    Returns:
        函数的签名对象
    """
    try:
        return signature(func)
    except (ValueError, TypeError):
        if hasattr(func, '__text_signature__'):
            try:
                return signature(func.__text_signature__)
            except:
                pass
        if hasattr(__builtins__, func.__name__ if hasattr(func, '__name__') else ''):
            builtin_arg_counts = {
                'filter': 2, 'map': 2, 'sorted': 1, 'len': 1, 'abs': 1,
                'sum': 1, 'min': 1, 'max': 1, 'zip': 2, 'enumerate': 1, 'reversed': 1,
            }
            name = func.__name__
            if name in builtin_arg_counts:
                import inspect
                args = ', '.join([f'arg{i}' for i in range(builtin_arg_counts[name])])
                return signature(eval(f'lambda {args}: None', {}))
        return signature(lambda *args, **kwargs: None)


@lru_cache(maxsize=512)
def _get_cached_type_hints(func: Callable[..., Any]) -> Dict[str, Any]:
    """获取函数的类型注解并缓存结果。
    
    Args:
        func: 要获取类型注解的函数
        
    Returns:
        类型注解字典
    """
    try:
        return get_type_hints(func)
    except (TypeError, AttributeError, NameError):
        return {}


@lru_cache(maxsize=512)
def _get_func_info(func: Callable[..., Any]) -> Dict[str, Any]:
    """获取函数的完整信息并缓存。
    
    Args:
        func: 要获取信息的函数
        
    Returns:
        包含函数签名、参数、类型注解等信息的字典
    """
    f = func.__init__ if isclass(func) and hasattr(func, '__init__') else func
    sig = _get_cached_signature(f)
    params = sig.parameters
    type_hints = _get_cached_type_hints(f)
    required_args = [
        name for name, param in params.items()
        if param.default is Parameter.empty
        and param.kind not in (Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD)
    ]
    return {
        'sig': sig,
        'params': params,
        'type_hints': type_hints,
        'required_args': required_args,
        'f': f
    }


class CurryExecutionError(Exception):
    """柯里化执行异常，当函数执行失败时抛出。"""
    def do(self, f: Callable[..., Any] = print, pre_f: Optional[Callable[..., Any]] = None, 
            sub_f: Optional[Callable[..., Any]] = None) -> "CurryExecutionError":
        """应用函数进行副作用处理，返回 self 以支持链式调用。
        
        Args:
            f: 要应用的函数（默认 print）
            pre_f: 在 f 之前应用的预处理函数
            sub_f: 在 f 之后应用的后处理函数
            
        Returns:
            self，用于链式调用
        """
        rs = self
        if pre_f:
            rs = pre_f(rs)
        rs = f(rs)
        if sub_f:
            sub_f(rs)
        return self



class CurryDescriptor:
    """柯里化描述符，用于描述可柯里化函数的元数据。
    
    CurryDescriptor 是函数的包装器，记录函数是否被柯里化以及相关属性。
    
    Attributes:
        func: 原始函数
        is_strict: 是否严格模式
        delaied: 是否延迟执行
        pre_attrs: 预绑定属性
    """
    __slots__ = ('func', 'is_strict', 'delaied', '_name', '_doc', 'pre_attrs')
    
    def __init__(self, func: Callable[..., Any], is_strict: bool, delaied: bool, **pre_attrs: Any) -> None:
        """初始化 CurryDescriptor。
        
        Args:
            func: 要包装的函数
            is_strict: 是否严格模式（进行类型检查）
            delaied: 是否延迟执行
            **pre_attrs: 预绑定的属性
            
        Raises:
            TypeError: 当 func 已被柯里化或不可调用时
        """
        if is_curried(func):
            raise TypeError("Cannot curry a curried function")
        if not callable(func):
            raise TypeError("func must be a callable object")
        self.func = func
        self.is_strict = is_strict
        self.delaied = delaied
        try:
            self._name = func.__name__
        except AttributeError:
            self._name = f"<lambda>id({id(func)})"
        self._doc = func.__doc__
        
        func_info = _get_func_info(func)
        self.pre_attrs = {
            'sig': func_info['sig'],
            'params': func_info['params'],
            'type_hints': func_info['type_hints'],
            'required_args': func_info['required_args'],
            **pre_attrs
        }

    def __str__(self) -> str:
        bound_args = self.pre_attrs.get('bound_args', {})
        sig = self.pre_attrs.get('sig', '()')
        return f"""<CurryDescriptor {self.func.__name__}{bound_args}  
            is_ready= ?, is_full= ?
            is_strict= {self.is_strict} , delaied= {self.delaied}
            
            protofunc= {self.func.__name__}{sig}>
        """
    
    def __repr__(self) -> str:
        return self.__str__()
            
    @property
    def __name__(self) -> str:
        """返回函数的名称。"""
        return self._name

    @__name__.setter
    def __name__(self, v: str) -> None:
        """设置函数的名称。"""
        self._name = v
    
    @property
    def __doc__(self) -> Optional[str]:
        """返回函数的文档字符串。"""
        return self._doc
    
    def __get__(self, instance: Any, owner: type) -> Union["Curried", "CurryDescriptor"]:
        """获取描述符值。
        
        Args:
            instance: 实例对象（如果通过类访问则为 None）
            owner: 所属类
            
        Returns:
            如果 instance 为 None 返回 Curried，否则返回绑定后的 Curried
        """
        # classmethod 委托场景：Python 的 classmethod.__get__ 会把类本身作为
        # instance 传给 descriptor（instance is owner），此时需将第一个参数 (cls)
        # 绑定为 owner 并从 required_args 中剔除。
        is_classmethod_delegation = (
            owner is not None
            and isinstance(instance, type)
            and instance is owner
            and isinstance(getattr(owner, '__dict__', {}).get(self._name), classmethod)
        )
        if is_classmethod_delegation:
            bound_func = self.func.__get__(owner, owner)
            pre_attrs = self.pre_attrs.copy()
            required_args = pre_attrs.get('required_args', [])
            params = pre_attrs.get('params', {})
            if required_args:
                first = required_args[0]
                pre_attrs['required_args'] = required_args[1:]
                pre_attrs['params'] = {k: v for k, v in params.items() if k != first}
            return Curried(bound_func, is_strict=self.is_strict, delaied=self.delaied, **pre_attrs)
        if instance is None:
            return Curried(self.func, is_strict=self.is_strict, delaied=self.delaied, **self.pre_attrs)
        bound_func = self.func.__get__(instance, owner)
        pre_attrs = self.pre_attrs.copy()
        required_args = pre_attrs.get('required_args', [])
        params = pre_attrs.get('params', {})
        if required_args and required_args[0] == 'self':
            pre_attrs['required_args'] = required_args[1:]
            pre_attrs['params'] = {k: v for k, v in params.items() if k != 'self'}
        return Curried(bound_func, is_strict=self.is_strict, delaied=self.delaied, **pre_attrs)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """调用柯里化函数。"""
        return Curried(self.func, is_strict=self.is_strict, delaied=self.delaied, **self.pre_attrs)(*args, **kwargs)


class Curried:
    """柯里化函数包装器，支持部分参数绑定和延迟执行。
    
    Curried 将函数包装为可分步调用的形式，允许部分绑定参数。
    
    Attributes:
        func: 原始函数
        bound_args: 已绑定的参数字典
        is_strict: 是否严格模式
        delaied: 是否延迟执行
    """
    __slots__ = ('func', 'bound_args', 'is_strict', 'delaied', '_name', '_doc',
                 '_isclass', 'f', 'sig', 'params', 'type_hints', 'required_args')

    def __init__(self, func: Callable[..., Any], bound_args: Optional[Dict[str, Any]] = None, 
                 is_strict: bool = False, delaied: bool = False, **pre_attrs: Any) -> None:
        """初始化 Curried 包装器。
        
        Args:
            func: 要包装的函数
            bound_args: 初始绑定的参数字典
            is_strict: 是否严格模式（进行类型检查）
            delaied: 是否延迟执行
            **pre_attrs: 预绑定的属性
            
        Raises:
            TypeError: 当 func 已被柯里化或不可调用时
        """
        if is_curried(func):
            raise TypeError("Cannot curry a curried function")
        if not callable(func):
            raise TypeError("func must be a callable object")
        self.func = func
        try:
            self._name = func.__name__
        except AttributeError:
            self._name = f"<lambda>id({id(func)})"
        self._doc = func.__doc__
        self._isclass = isclass(func)
        self.bound_args = bound_args if bound_args is not None else {}
        self.delaied = delaied
        self.is_strict = is_strict

        if 'sig' in pre_attrs:
            self.sig = pre_attrs['sig']
            self.params = pre_attrs['params']
            self.type_hints = pre_attrs['type_hints']
            self.required_args = pre_attrs['required_args']
            self.f = pre_attrs.get('f', func.__init__ if self._isclass and hasattr(func, '__init__') else func)
        else:
            func_info = _get_func_info(func)
            self.sig = func_info['sig']
            self.params = func_info['params']
            self.type_hints = func_info['type_hints']
            self.required_args = func_info['required_args']
            self.f = func_info['f']

    def __str__(self) -> str:
        return f"""<Curried {self.func.__name__}{self.bound_args}  
            is_ready= {self.is_ready} , is_full={self.is_full}>
            is_strict= {self.is_strict} , delaied= {self.delaied}
            
            protofunc= {self.func.__name__}{self.sig}>
        """
    
    def __repr__(self) -> str:
        return self.__str__()
    
    @property
    def isclass(self) -> bool:
        """返回 func 是否为类。"""
        return self._isclass
    
    @property    
    def is_ready(self) -> bool:
        """检查是否所有必需参数都已绑定。"""
        required = self.required_args
        bound = self.bound_args
        for name in required:
            if name not in bound:
                return False
        return True
    
    @property
    def is_full(self) -> bool:
        """检查是否所有参数都已绑定（包括可选参数）。"""
        bounds = self.bound_args
        for name, param in self.params.items():
            if param.kind in (Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD):
                return False
            if name not in bounds:
                return False
        return True

    @property
    def __name__(self) -> str:
        """返回函数的名称。"""
        return self._name

    @__name__.setter
    def __name__(self, v: str) -> None:
        """设置函数的名称。"""
        self._name = v
    
    @property
    def __doc__(self) -> Optional[str]:
        """返回函数的文档字符串。"""
        return self._doc
    
    def _check_type(self, name: str, value: Any) -> None:
        """检查参数类型是否符合类型注解。
        
        Args:
            name: 参数名
            value: 参数值
            
        Raises:
            TypeError: 当类型不匹配时
        """
        type_hints = self.type_hints
        if name in type_hints:
            expected_type = type_hints[name]
            if not isinstance(value, expected_type):
                raise TypeError(f"Argument '{name}' expects type {expected_type}, got {type(value)}")

    def _check_return_type(self, result: Any) -> None:
        """检查返回值类型是否符合类型注解。
        
        Args:
            result: 返回值
            
        Raises:
            TypeError: 当返回值类型不匹配时
        """
        type_hints = self.type_hints
        if 'return' in type_hints:
            expected_type = type_hints['return']
            if not isinstance(result, expected_type):
                raise TypeError(f"Return value expects type {expected_type}, got {type(result)}")
        
    def __hash__(self) -> int:
        """返回对象的哈希值。"""
        return hash((self.func, frozenset(self.bound_args.items()) if self.bound_args else None))

    def __eq__(self, other: object) -> bool:
        """检查与另一个 Curried 对象是否相等。"""
        return isinstance(other, Curried) and self.func == other.func and self.bound_args == other.bound_args

    def __ne__(self, other: object) -> bool:
        """检查与另一个 Curried 对象是否不相等。"""
        return not self.__eq__(other)

    def __call__(self, *args: Any, **kwargs: Any) -> Union["Curried", Any]:
        """调用柯里化函数，绑定参数并返回结果或新的 Curried。
        
        Args:
            *args: 位置参数
            **kwargs: 关键字参数
            
        Returns:
            如果参数已满且可执行则返回执行结果，否则返回新的 Curried
            
        Raises:
            TypeError: 参数绑定或执行失败时
        """
        try:
            current_bound = self.bound_args
            new_bindings = {}
            args_len = len(args)

            if not args_len and not kwargs:
                if self.is_ready:
                    pos_args = []
                    kw_args = {}
                    params = self.params
                    bound_args = self.bound_args

                    for name, param in params.items():
                        if name in bound_args:
                            if param.kind == Parameter.VAR_POSITIONAL:
                                pos_args.extend(bound_args[name])
                            elif param.kind in (Parameter.POSITIONAL_OR_KEYWORD, Parameter.POSITIONAL_ONLY):
                                pos_args.append(bound_args[name])

                    for name, param in params.items():
                        if name in bound_args:
                            if param.kind == Parameter.KEYWORD_ONLY:
                                kw_args[name] = bound_args[name]
                            elif param.kind == Parameter.VAR_KEYWORD:
                                kw_args.update(bound_args[name])

                    result = self.func(*pos_args, **kw_args)
                    if self.is_strict:
                        self._check_return_type(result)
                    return result
                raise TypeError("Too few arguments")

            bindable_params = []
            params = self.params
            for name in params:
                if name in current_bound:
                    continue
                param = params[name]
                if param.kind in (Parameter.POSITIONAL_OR_KEYWORD, Parameter.POSITIONAL_ONLY, Parameter.VAR_POSITIONAL):
                    bindable_params.append(name)

            arg_index = 0
            bindable_len = len(bindable_params)
            is_strict = self.is_strict
            for i in range(bindable_len):
                if arg_index >= args_len:
                    break
                param_name = bindable_params[i]
                param = params[param_name]
                if param.kind == Parameter.VAR_POSITIONAL:
                    if param_name in new_bindings:
                        new_bindings[param_name].extend(args[arg_index:])
                    else:
                        new_bindings[param_name] = list(args[arg_index:])
                    if is_strict:
                        for val in args[arg_index:]:
                            self._check_type(param_name, val)
                    arg_index = args_len
                    break
                else:
                    new_bindings[param_name] = args[arg_index]
                    if is_strict:
                        self._check_type(param_name, args[arg_index])
                    arg_index += 1

            if arg_index < args_len:
                raise TypeError(f"Too many positional arguments: expected at most {arg_index}, got {args_len}")

            for name, value in kwargs.items():
                if name in params:
                    param = params[name]
                    if name in current_bound or name in new_bindings:
                        raise TypeError(f"Multiple values for argument '{name}'")
                    if param.kind == Parameter.POSITIONAL_ONLY:
                        raise TypeError(f"Argument '{name}' is position-only")
                    new_bindings[name] = value
                    if is_strict:
                        self._check_type(name, value)
                else:
                    var_kw_name = next(
                        (n for n, p in params.items() if p.kind == Parameter.VAR_KEYWORD),
                        None
                    )
                    if var_kw_name:
                        if var_kw_name not in new_bindings:
                            new_bindings[var_kw_name] = {}
                        new_bindings[var_kw_name][name] = value
                        if is_strict and var_kw_name in self.type_hints:
                            expected_type = self.type_hints[var_kw_name]
                            if not isinstance(value, expected_type):
                                raise TypeError(
                                    f"Keyword argument '{name}' expects type {expected_type}, "
                                    f"got {type(value)}"
                                )
                    else:
                        raise TypeError(f"Unexpected keyword argument '{name}'")

            updated_bound = {**current_bound, **new_bindings}
            pre_attrs = {
                'sig': self.sig,
                'params': self.params,
                'type_hints': self.type_hints,
                'required_args': self.required_args,
                'f': self.f
            }
            result = self.__class__(self.func, updated_bound, self.is_strict, self.delaied, **pre_attrs)
            if self.delaied:
                return result
            return result() if result.is_ready else result
        except TypeError as e:
            raise TypeError(f"Failed to curry {self.func.__name__}: {e}") from e
        except Exception as e:
            raise CurryExecutionError(f"Failed to curry {self.func.__name__}: {e}") from e


def _curry(func: Optional[Callable[..., Any]] = None, *, is_strict: bool = False, 
           delaied: bool = False) -> Union[Callable[[F], Union["Curried", "CurryDescriptor"]], "Curried", "CurryDescriptor"]:
    """内部柯里化函数。
    
    Args:
        func: 要柯里化的函数，如果为 None 返回装饰器
        is_strict: 是否严格模式
        delaied: 是否延迟执行
        
    Returns:
        如果 func 为 None 返回装饰器，否则返回柯里化后的函数或描述符
    """
    if func is None:
        return lambda f: curry(f, is_strict=is_strict, delaied=delaied)
    if isfunction(func) and '.' in func.__qualname__ and not isinstance(func, (classmethod, staticmethod)):
        return CurryDescriptor(func, is_strict, delaied)
    return Curried(func, is_strict=is_strict, delaied=delaied)


def curry(func: Optional[F] = None, *args: Any, **kwargs: Any) -> Union[F, Callable[[F], F], "Curried", "CurryDescriptor"]:
    """柯里化装饰器，将函数转换为可分步调用的形式。
    
    Args:
        func: 要柯里化的函数，如果为 None 返回装饰器
        *args: 初始位置参数
        **kwargs: 初始关键字参数，可包含 is_strict 和 delaied
        
    Returns:
        如果 func 为 None 返回装饰器，否则返回柯里化后的函数
        
    示例:
        @curry
        def add(a, b, c):
            return a + b + c
        
        add(1)(2)(3)  # 返回 6
        add(1, 2)(3)  # 返回 6
    """
    curry.__doc__ = _curry.__doc__
    is_strict = kwargs.pop('is_strict', False)
    delaied = kwargs.pop('delaied', False)
    if func is None:
        if any([args, kwargs]):
            lambda f: _curry(f, is_strict=is_strict, delaied=delaied)(*args, **kwargs)
        return lambda f: _curry(f, is_strict=is_strict, delaied=delaied)
    result = _curry(func, is_strict=is_strict, delaied=delaied)
    return result(*args, **kwargs) if any([args, kwargs]) else result