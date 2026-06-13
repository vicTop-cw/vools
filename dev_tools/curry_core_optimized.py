"""
标准柯里化装饰器 - 优化版本

主要优化：
1. 参数顺序预计算缓存
2. 减少对象创建开销
3. 优化 __call__ 方法逻辑
"""

from inspect import signature, Parameter, isfunction, isclass
from typing import get_type_hints, Any
from functools import lru_cache

__all__ = ['curry', 'Curried', 'CurryDescriptor', 'is_curried', 'CurryExecutionError']

is_curried = lambda x: isinstance(x, (Curried, CurryDescriptor))


# 缓存函数签名信息
_func_info_cache = {}

def _get_func_info(func):
    """获取函数签名信息，缓存结果"""
    if func not in _func_info_cache:
        try:
            sig = signature(func)
        except (ValueError, TypeError):
            if hasattr(func, '__text_signature__'):
                try:
                    sig = signature(func.__text_signature__)
                except:
                    sig = signature(lambda *args, **kwargs: None)
            elif hasattr(__builtins__, func.__name__ if hasattr(func, '__name__') else ''):
                builtin_arg_counts = {
                    'filter': 2, 'map': 2, 'sorted': 1, 'len': 1, 'abs': 1,
                    'sum': 1, 'min': 1, 'max': 1, 'zip': 2, 'enumerate': 1, 'reversed': 1,
                }
                name = func.__name__
                if name in builtin_arg_counts:
                    args = ', '.join([f'arg{i}' for i in range(builtin_arg_counts[name])])
                    sig = signature(eval(f'lambda {args}: None', {}))
                else:
                    sig = signature(lambda *args, **kwargs: None)
            else:
                sig = signature(lambda *args, **kwargs: None)
        
        params = sig.parameters
        required_args = []
        positional_params = []
        keyword_only_params = []
        var_pos_param = None
        var_kw_param = None
        
        for name, param in params.items():
            if param.kind == Parameter.VAR_POSITIONAL:
                var_pos_param = name
            elif param.kind == Parameter.VAR_KEYWORD:
                var_kw_param = name
            elif param.kind == Parameter.KEYWORD_ONLY:
                keyword_only_params.append(name)
                if param.default is Parameter.empty:
                    required_args.append(name)
            else:
                positional_params.append(name)
                if param.default is Parameter.empty:
                    required_args.append(name)
        
        try:
            type_hints = get_type_hints(func)
        except (TypeError, AttributeError, NameError):
            type_hints = {}
        
        _func_info_cache[func] = {
            'sig': sig,
            'params': params,
            'required_args': required_args,
            'positional_params': positional_params,
            'keyword_only_params': keyword_only_params,
            'var_pos_param': var_pos_param,
            'var_kw_param': var_kw_param,
            'type_hints': type_hints,
        }
    
    return _func_info_cache[func]


class CurryExecutionError(Exception):
    """柯里化执行错误"""
    pass


class CurryDescriptor:
    """柯里化描述符，用于处理类方法的柯里化"""
    
    __slots__ = ('func', 'is_strict', 'delaied', '_name', '_doc', '_info')
    
    def __init__(self, func, is_strict, delaied):
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
        self._info = None
    
    @property
    def __name__(self):
        return self._name

    @__name__.setter
    def __name__(self, v):
        self._name = v
    
    @property
    def __doc__(self):
        return self._doc
    
    def _get_info(self, func):
        if self._info is None:
            self._info = _get_func_info(func)
        return self._info
    
    def __get__(self, instance, owner):
        if instance is None:
            f = self.func.__init__ if isclass(self.func) and hasattr(self.func, '__init__') else self.func
            info = self._get_info(f)
            return Curried(self.func, is_strict=self.is_strict, delaied=self.delaied, **info)
        bound_func = self.func.__get__(instance, owner)
        f = bound_func.__func__.__init__ if isclass(self.func) and hasattr(self.func, '__init__') else bound_func
        info = self._get_info(f)
        return Curried(bound_func, is_strict=self.is_strict, delaied=self.delaied, **info)

    def __call__(self, *args, **kwargs):
        return self.__get__(None, type(self))(*args, **kwargs)


class Curried:
    """柯里化函数对象"""
    
    __slots__ = ('func', 'bound_args', 'is_strict', 'delaied', '_name', '_doc',
                 '_isclass', 'sig', 'params', 'type_hints', 'required_args',
                 'positional_params', 'keyword_only_params', 'var_pos_param', 'var_kw_param')
    
    def __init__(self, func, bound_args=None, is_strict=False, delaied=False, **info):
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
        self.bound_args = bound_args or {}
        self.delaied = delaied
        self.is_strict = is_strict
        
        # 从缓存的信息中获取参数信息
        self.sig = info.get('sig')
        self.params = info.get('params')
        self.type_hints = info.get('type_hints', {})
        self.required_args = info.get('required_args', [])
        self.positional_params = info.get('positional_params', [])
        self.keyword_only_params = info.get('keyword_only_params', [])
        self.var_pos_param = info.get('var_pos_param')
        self.var_kw_param = info.get('var_kw_param')

    @property
    def __name__(self):
        return self._name

    @__name__.setter
    def __name__(self, v):
        self._name = v
    
    @property
    def __doc__(self):
        return self._doc
    
    @property
    def isclass(self):
        return self._isclass
    
    @property    
    def is_ready(self):
        bound = self.bound_args
        for name in self.required_args:
            if name not in bound:
                return False
        return True
    
    @property
    def is_full(self):
        bound = self.bound_args
        for name, param in self.params.items():
            if param.kind in (Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD):
                return False
            if name not in bound:
                return False
        return True
    
    def _check_type(self, name, value):
        if self.is_strict and name in self.type_hints:
            expected_type = self.type_hints[name]
            if not isinstance(value, expected_type):
                raise TypeError(f"Argument '{name}' expects type {expected_type}, got {type(value)}")

    def _check_return_type(self, result):
        if self.is_strict and 'return' in self.type_hints:
            expected_type = self.type_hints['return']
            if not isinstance(result, expected_type):
                raise TypeError(f"Return value expects type {expected_type}, got {type(result)}")
    
    def __hash__(self):
        return hash((self.func, frozenset(self.bound_args.items()) if self.bound_args else None))

    def __eq__(self, other):
        return (isinstance(other, Curried) and self.func == other.func and
                self.bound_args == other.bound_args)

    def __ne__(self, other):
        return not self.__eq__(other) 

    def __call__(self, *args, **kwargs):
        try:
            bound = self.bound_args
            new_bindings = {}
            arg_index = 0
            
            # 空调用且已就绪时执行
            if not args and not kwargs:
                if self.is_ready:
                    pos_args = []
                    kw_args = {}
                    
                    for name in self.positional_params:
                        if name in bound:
                            pos_args.append(bound[name])
                    
                    for name in self.keyword_only_params:
                        if name in bound:
                            kw_args[name] = bound[name]
                    
                    if self.var_pos_param and self.var_pos_param in bound:
                        pos_args.extend(bound[self.var_pos_param])
                    
                    if self.var_kw_param and self.var_kw_param in bound:
                        kw_args.update(bound[self.var_kw_param])
                    
                    result = self.func(*pos_args, **kw_args)
                    self._check_return_type(result)
                    return result
                raise TypeError("Too few arguments")

            # 处理位置参数
            for name in self.positional_params:
                if name in bound:
                    continue
                if arg_index >= len(args):
                    break
                new_bindings[name] = args[arg_index]
                self._check_type(name, args[arg_index])
                arg_index += 1
            
            # 处理可变位置参数
            if self.var_pos_param and arg_index < len(args):
                new_bindings[self.var_pos_param] = list(args[arg_index:])
                arg_index = len(args)
            
            if arg_index < len(args):
                raise TypeError(f"Too many positional arguments")

            # 处理关键字参数
            for name, value in kwargs.items():
                if name in bound or name in new_bindings:
                    raise TypeError(f"Multiple values for argument '{name}'")
                
                if name in self.params:
                    param = self.params[name]
                    if param.kind == Parameter.POSITIONAL_ONLY:
                        raise TypeError(f"Argument '{name}' is position-only")
                    new_bindings[name] = value
                    self._check_type(name, value)
                elif self.var_kw_param:
                    if self.var_kw_param not in new_bindings:
                        new_bindings[self.var_kw_param] = {}
                    new_bindings[self.var_kw_param][name] = value
                else:
                    raise TypeError(f"Unexpected keyword argument '{name}'")

            # 更新绑定参数
            updated_bound = {**bound, **new_bindings}
            
            # 创建新的柯里化对象
            info = {
                'sig': self.sig,
                'params': self.params,
                'type_hints': self.type_hints,
                'required_args': self.required_args,
                'positional_params': self.positional_params,
                'keyword_only_params': self.keyword_only_params,
                'var_pos_param': self.var_pos_param,
                'var_kw_param': self.var_kw_param,
            }
            result = self.__class__(self.func, updated_bound, self.is_strict, self.delaied, **info)
            
            if self.delaied:
                return result
            return result() if result.is_ready else result
            
        except TypeError as e:
            raise TypeError(f"Failed to curry {self.func.__name__}: {e}") from e
        except Exception as e:
            raise CurryExecutionError(f"Failed to curry {self.func.__name__}: {e}") from e


def _curry(func=None, *, is_strict=False, delaied=False):
    """柯里化装饰器"""
    if func is None:
        return lambda f: curry(f, is_strict=is_strict, delaied=delaied)
    if isfunction(func) and '.' in func.__qualname__ and not isinstance(func, (classmethod, staticmethod)):
        return CurryDescriptor(func, is_strict, delaied)
    f = func.__init__ if isclass(func) and hasattr(func, '__init__') else func
    info = _get_func_info(f)
    return Curried(func, is_strict=is_strict, delaied=delaied, **info)


def curry(func=None, *args, **kwargs):
    """柯里化装饰器"""
    curry.__doc__ = _curry.__doc__
    is_strict = kwargs.pop('is_strict', False)
    delaied = kwargs.pop('delaied', False)
    if func is None:
        return lambda f: _curry(f, is_strict=is_strict, delaied=delaied)
    result = _curry(func, is_strict=is_strict, delaied=delaied)
    return result(*args, **kwargs) if any([args, kwargs]) else result