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

from inspect import signature, Parameter, isfunction, isclass
from typing import get_type_hints, Any
from functools import lru_cache

__all__ = ['curry', 'Curried', 'CurryDescriptor', 'is_curried', 'CurryExecutionError']

is_curried = lambda x: isinstance(x, (Curried, CurryDescriptor))


@lru_cache(maxsize=512)
def _get_cached_signature(func):
    """缓存函数签名获取，支持内置函数"""
    try:
        return signature(func)
    except (ValueError, TypeError):
        # 对于内置函数或C扩展函数，尝试获取__text_signature__
        if hasattr(func, '__text_signature__'):
            try:
                return signature(func.__text_signature__)
            except:
                pass
        
        # 对于内置函数，尝试获取参数数量
        if hasattr(__builtins__, func.__name__ if hasattr(func, '__name__') else ''):
            # 常见内置函数的参数数量
            builtin_arg_counts = {
                'filter': 2,
                'map': 2,
                'sorted': 1,
                'len': 1,
                'abs': 1,
                'sum': 1,
                'min': 1,
                'max': 1,
                'zip': 2,
                'enumerate': 1,
                'reversed': 1,
            }
            name = func.__name__
            if name in builtin_arg_counts:
                # 创建一个简单的签名
                import inspect
                args = ', '.join([f'arg{i}' for i in range(builtin_arg_counts[name])])
                return signature(eval(f'lambda {args}: None', {}))
        
        # 返回一个通用的签名，接受任意参数
        return signature(lambda *args, **kwargs: None)


@lru_cache(maxsize=512)
def _get_cached_type_hints(func):
    """缓存类型注解获取"""
    try:
        return get_type_hints(func)
    except (TypeError, AttributeError, NameError):
        return {}


class CurryExecutionError(Exception):
    """柯里化执行错误"""
    pass


class CurryDescriptor:
    """柯里化描述符，用于处理类方法的柯里化"""
    
    __slots__ = ('func', 'is_strict', 'delaied', '_name', '_doc', 'pre_attrs')
    
    def __init__(self, func, is_strict, delaied, **pre_attrs):
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
        self.pre_attrs = pre_attrs

    def __str__(self):
        bound_args = self.pre_attrs.get('bound_args', {})
        sig = self.pre_attrs.get('sig', '()')
        return f"""<CurryDescriptor {self.func.__name__}{bound_args}  
            is_ready= ?, is_full= ?
            is_strict= {self.is_strict} , delaied= {self.delaied}
            
            protofunc= {self.func.__name__}{sig}>
        """
    
    def __repr__(self):
        return self.__str__()
            
    @property
    def __name__(self):
        return self._name

    @__name__.setter
    def __name__(self, v):
        self._name = v
    
    @property
    def __doc__(self):
        return self._doc
    
    def __get__(self, instance, owner):
        if instance is None:
            return Curried(self.func, is_strict=self.is_strict, delaied=self.delaied, **self.pre_attrs)
        bound_func = self.func.__get__(instance, owner)
        return Curried(bound_func, is_strict=self.is_strict, delaied=self.delaied, **self.pre_attrs)

    def __call__(self, *args, **kwargs):
        return Curried(self.func, is_strict=self.is_strict, delaied=self.delaied, **self.pre_attrs)(*args, **kwargs)


class Curried:
    """柯里化函数对象"""
    
    __slots__ = ('func', 'bound_args', 'is_strict', 'delaied', '_name', '_doc',
                 '_isclass', 'f', 'sig', 'params', 'type_hints', 'required_args')
    
    def __init__(self, func, bound_args=None, is_strict=False, delaied=False, **pre_attrs):
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
        f = func.__init__ if self._isclass and hasattr(func, '__init__') else func
        self.f = f
        self.bound_args = bound_args or {}
        self.delaied = delaied  # 是否延迟调用
        self.is_strict = is_strict
        
        # 预填充属性，避免重复计算 获取参数信息
        self.sig = pre_attrs.get('sig', _get_cached_signature(f))
        self.params = pre_attrs.get('params', self.sig.parameters)
        self.type_hints = pre_attrs.get('type_hints', _get_cached_type_hints(f))
        self.required_args = pre_attrs.get('required_args', [
            name for name, param in self.params.items()
            if param.default is Parameter.empty
            and param.kind not in (Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD)
        ])

    def __str__(self):
        return f"""<Curried {self.func.__name__}{self.bound_args}  
            is_ready= {self.is_ready} , is_full={self.is_full}>
            is_strict= {self.is_strict} , delaied= {self.delaied}
            
            protofunc= {self.func.__name__}{self.sig}>
        """
    
    def __repr__(self):
        return self.__str__()
    
    @property
    def isclass(self):
        return self._isclass
    
    @property    
    def is_ready(self):
        ready = all(name in self.bound_args for name in self.required_args)
        if ready or not self.isclass:
            return ready
        required_count = len(self.required_args)
        bound_count = sum(1 for name in self.required_args if name in self.bound_args) + 1
        if bound_count == required_count:
            return True
        return False
    
    @property
    def is_full(self):
        bounds = [name for name in self.bound_args]
        for name, param in self.params.items():
            if param.kind in (Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD):
                return False
            if name not in bounds:
                return False
        return True
        

    @property
    def __name__(self):
        return self._name

    @__name__.setter
    def __name__(self, v):
        self._name = v
    
    @property
    def __doc__(self):
        return self._doc
    
    def _check_type(self, name: str, value: Any):
        if name in self.type_hints:
            expected_type = self.type_hints[name]
            if not isinstance(value, expected_type):
                raise TypeError(f"Argument '{name}' expects type {expected_type}, got {type(value)}")

    def _check_return_type(self, result: Any):
        if 'return' in self.type_hints:
            expected_type = self.type_hints['return']
            if not isinstance(result, expected_type):
                raise TypeError(f"Return value expects type {expected_type}, got {type(result)}")
            
    
    def __hash__(self):
        return hash((self.func, 
                     frozenset(self.bound_args.items()) if self.bound_args else None
                     ))

    def __eq__(self, other):
        return (isinstance(other, Curried) and self.func == other.func and
                self.bound_args == other.bound_args)

    def __ne__(self, other):
        return not self.__eq__(other) 

    def __call__(self, *args, **kwargs):
        try:
            current_bound = self.bound_args.copy()
            new_bindings = {}

            if not args and not kwargs:
                if self.is_ready:
                    pos_args = []
                    kw_args = {}

                    for name, param in self.params.items():
                        if name in current_bound:
                            if param.kind == Parameter.VAR_POSITIONAL:
                                pos_args.extend(current_bound[name])
                            elif param.kind in (Parameter.POSITIONAL_OR_KEYWORD, Parameter.POSITIONAL_ONLY):
                                pos_args.append(current_bound[name])

                    for name, param in self.params.items():
                        if name in current_bound:
                            if param.kind == Parameter.KEYWORD_ONLY:
                                kw_args[name] = current_bound[name]
                            elif param.kind == Parameter.VAR_KEYWORD:
                                kw_args.update(current_bound[name])

                    result = self.func(*pos_args, **kw_args)
                    if self.is_strict:
                        self._check_return_type(result)
                    return result
                raise TypeError("Too few arguments")

            bindable_params = []
            for name in self.params:
                if name in current_bound:
                    continue
                param = self.params[name]
                if param.kind in (Parameter.POSITIONAL_OR_KEYWORD, 
                                Parameter.POSITIONAL_ONLY,
                                Parameter.VAR_POSITIONAL):
                    bindable_params.append(name)

            arg_index = 0
            for param_name in bindable_params:
                if arg_index >= len(args):
                    break
                param = self.params[param_name]
                if param.kind == Parameter.VAR_POSITIONAL:
                    if param_name in new_bindings:
                        new_bindings[param_name].extend(args[arg_index:])
                    else:
                        new_bindings[param_name] = list(args[arg_index:])

                    if self.is_strict:
                        for val in args[arg_index:]:
                            self._check_type(param_name, val)
                    arg_index = len(args)
                    break
                else:
                    new_bindings[param_name] = args[arg_index]

                    if self.is_strict:
                        self._check_type(param_name, args[arg_index])
                    arg_index += 1

            if arg_index < len(args):
                raise TypeError(f"Too many positional arguments: expected at most {arg_index}, got {len(args)}")

            for name, value in kwargs.items():
                if name in self.params:
                    param = self.params[name]
                    if name in current_bound or name in new_bindings:
                        raise TypeError(f"Multiple values for argument '{name}'")
                    if param.kind == Parameter.POSITIONAL_ONLY:
                        raise TypeError(f"Argument '{name}' is position-only")
                    new_bindings[name] = value

                    if self.is_strict:
                        self._check_type(name, value)
                else:
                    var_kw_name = next(
                        (n for n, p in self.params.items() if p.kind == Parameter.VAR_KEYWORD), 
                        None
                    )
                    if var_kw_name:
                        if var_kw_name not in new_bindings:
                            new_bindings[var_kw_name] = {}
                        new_bindings[var_kw_name][name] = value

                        if self.is_strict and var_kw_name in self.type_hints:
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
                'required_args': self.required_args
            }
            result = self.__class__(self.func, updated_bound, self.is_strict, self.delaied, **pre_attrs)
            if self.delaied:
                return result
            return result() if result.is_ready else result
        except TypeError as e:
            raise TypeError(f"Failed to curry {self.func.__name__}: {e}") from e
        except Exception as e:
            raise CurryExecutionError(f"Failed to curry {self.func.__name__}: {e}") from e


def _curry(func=None, *, is_strict=False, delaied=False):
    """柯里化装饰器，将函数转换为可部分应用参数的柯里化函数。

    支持普通函数、实例方法、类方法和静态方法的柯里化。对于实例方法，
    会自动处理`self`参数的绑定，无需手动传递。

    参数:
        func: 要柯里化的函数，如果为None，则返回一个带参数的装饰器。
        is_strict (bool): 是否严格校验参数类型。
        delaied (bool): 是否延迟调用，即是否返回Curried对象，直到所有必参都被传入才调用。

    返回:
        Curried: 柯里化后的函数对象，或带参数的装饰器（当func为None时）。

    示例:
        装饰普通函数:
        >>> @curry
        ... def multiply(a, b, c):
        ...     return a * b * c
        ...
        >>> multiply(2)(3)(4)
        24
        >>> multiply(2, 3)(4)
        24

        装饰实例方法:
        >>> class Calculator:
        ...     @curry
        ...     def add(self, a, b):
        ...         return self.value + a + b
        ...
        ...     def __init__(self, value):
        ...         self.value = value
        ...
        >>> calc = Calculator(10)
        >>> add5 = calc.add(5)
        >>> add5(3)
        18

        装饰静态方法:
        >>> class MathUtils:
        ...     @staticmethod
        ...     @curry
        ...     def power(base, exponent):
        ...         return base ** exponent
        ...
        >>> square = MathUtils.power(exponent=2)
        >>> square(3)
        9
    """
    if func is None:
        return lambda f: curry(f, is_strict=is_strict, delaied=delaied)
    if isfunction(func) and '.' in func.__qualname__ and not isinstance(func, (classmethod, staticmethod)):
        return CurryDescriptor(func, is_strict, delaied)
    return Curried(func, is_strict=is_strict, delaied=delaied)


def curry(func=None, *args, **kwargs):
    """柯里化装饰器
    
    将函数转换为可部分应用参数的柯里化函数。
    
    参数:
        func: 要柯里化的函数
        is_strict: 是否严格校验参数类型
        delaied: 是否延迟调用
    
    返回:
        柯里化后的函数对象
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
