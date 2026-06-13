"""
延迟柯里化装饰器

提供延迟执行的柯里化功能，支持：
- 延迟参数绑定
- 延迟函数执行
- 参数提供者模式
"""

from inspect import signature, Parameter
from functools import wraps, lru_cache

from .lazy import lazy, is_lazy

__all__ = ['delay_curry', 'DelayCurried', 'is_lazy', 'lazy']


@lru_cache(maxsize=512)
def _get_delay_func_info(func):
    sig = signature(func)
    params = sig.parameters
    required_params = [
        name for name, param in params.items()
        if param.default is Parameter.empty and
           param.kind not in (Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD)
    ]
    has_var_keyword = any(p.kind == Parameter.VAR_KEYWORD for p in params.values())
    has_var_positional = any(p.kind == Parameter.VAR_POSITIONAL for p in params.values())
    var_count = sum(1 for param in params.values() 
                   if param.kind in (Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD))
    max_args_count = float('inf') if var_count > 0 else len(params) - var_count
    
    return {
        'sig': sig,
        'params': params,
        'required_params': required_params,
        'has_var_keyword': has_var_keyword,
        'has_var_positional': has_var_positional,
        'max_args_count': max_args_count
    }


class DelayCurried:
    __slots__ = ('func', 'sig', 'bound_args', '_is_ready', 'required_params', 
                 'max_args_count', '_bound_providers', '_has_var_keyword', '_has_var_positional',
                 '_module', '_name', '_doc', '_annotations')
    
    def __init__(self, func):
        self.func = func
        object.__setattr__(self, '_module', func.__module__)
        object.__setattr__(self, '_name', func.__name__)
        object.__setattr__(self, '_doc', func.__doc__)
        object.__setattr__(self, '_annotations', getattr(func, '__annotations__', {}))
        
        func_info = _get_delay_func_info(func)
        self.sig = func_info['sig']
        self.required_params = func_info['required_params']
        self.max_args_count = func_info['max_args_count']
        self._has_var_keyword = func_info['has_var_keyword']
        self._has_var_positional = func_info['has_var_positional']
        
        self.bound_args = {}
        self._is_ready = False
        self._bound_providers = {}
    
    @property
    def has_var_keyword(self):
        return self._has_var_keyword
    
    @property
    def has_var_positional(self):
        return self._has_var_positional
    
    @property
    def __module__(self):
        return self._module
    
    @property
    def __name__(self):
        return self._name
    
    @property
    def __doc__(self):
        return self._doc
    
    @property
    def __annotations__(self):
        return self._annotations
    
    @staticmethod
    def resolve_value(value):
        if isinstance(value, DelayCurried) and value.is_ready:
            return DelayCurried.resolve_value(value())
        if is_lazy(value):
            return DelayCurried.resolve_value(value())
        if isinstance(value, list):
            return [DelayCurried.resolve_value(v) for v in value]
        if isinstance(value, dict):
            return {k: DelayCurried.resolve_value(v) for k, v in value.items()}
        if isinstance(value, tuple):
            return tuple(DelayCurried.resolve_value(v) for v in value)
        return value
    
    @property
    def if_full(self):
        return len(self.bound_args) == self.max_args_count
        
    def fill_by_mutil(self, *funcs, provider: str = None):
        def merge_func():
            return tuple(DelayCurried.resolve_value(func) for func in funcs)
        lazy_merge = lazy(merge_func)
        if provider is None:
            return self.__call__(lazy_merge)
        else:
            return self.__call__(**{provider: lazy_merge})

    def _validate_providers(self, providers, sep=","):
        if not isinstance(providers, (list, tuple, str)):
            raise TypeError("providers参数必须是列表或元组或字符串")
        if isinstance(providers, str):
            providers = providers.strip().split(sep)
        providers = [str(p).strip() for p in providers]
        if not providers:
            raise ValueError("providers不能为空")
        
        if any(k in providers for k in self.bound_args):
            raise ValueError(f"providers参数不能包含函数签名中已存在的参数名")
    
        if not self.has_var_keyword:
            params = self.sig.parameters
            for p in providers:
                if p not in params:
                    raise ValueError(f"参数 {p} 不存在于函数签名中")
        return providers

    def bound_providers(self):
        return self._bound_providers
    
    def _bind_provider(self, provider, value):
        self._bound_providers[provider] = value

    def fill(self, func, providers=None, result_is_dict=False, sep=","):
        if not callable(func):
            if isinstance(func, dict):
                return self.__call__(**func)
            elif isinstance(func, (list, tuple)):
                return self.__call__(*func)
            else:
                return self.__call__(**{providers[0]: lazy(func)})
            
        providers = self._validate_providers(providers, sep)
        
        from .cache import memorize
        func = memorize(func)
        
        def _wrap_func(func, key):
            def _gene_func():
                temp = func()
                if isinstance(temp, (dict, tuple, list)):
                    return temp[key]
                return temp
            _gene_func.__name__ = f"{func.__name__}_{key}"
            return _gene_func
        
        dct = {}
        for i, provider in enumerate(providers):
            value = lazy(_wrap_func(func, provider if result_is_dict else i))
            self._bind_provider(provider, (func, value))
            dct[provider] = value
        
        return self.__call__(**dct)
        
    def __hash__(self):
        return hash((self.func, 
                     frozenset(self.bound_args.items()) if self.bound_args else None,
                     frozenset(self._bound_providers.items()) if self._bound_providers else None
                     ))

    def __eq__(self, other):
        return isinstance(other, DelayCurried) and self.func == other.func and \
               self.bound_args == other.bound_args and self._bound_providers == other._bound_providers

    def __ne__(self, other):
        return not self.__eq__(other)

    def register(self, func=None, providers=None, result_is_dict=False, sep=",", return_curried=False):
        if func is None:
            return lambda f: self.register(f, providers, result_is_dict, sep, return_curried)
        _ = self.fill(func, providers, result_is_dict, sep) if providers is not None else self.__call__(func)
        return delay_curry(func) if return_curried else func

    def __call__(self, *args, **kwargs):
        args_len = len(args)
        kwargs_len = len(kwargs)
        
        if not args_len and not kwargs_len and not self.is_ready:
            return self
        
        wrapped_args = [lazy(arg) for arg in args]
        wrapped_kwargs = {k: lazy(v) for k, v in kwargs.items()}

        param_list = list(self.sig.parameters.values())
        arg_index = 0
        bound_args = self.bound_args

        for i, param in enumerate(param_list):
            if arg_index >= args_len:
                break

            if param.kind in (Parameter.POSITIONAL_OR_KEYWORD, Parameter.POSITIONAL_ONLY):
                if param.name not in bound_args:
                    bound_args[param.name] = wrapped_args[arg_index]
                    arg_index += 1
            elif param.kind == Parameter.VAR_POSITIONAL:
                if param.name not in bound_args:
                    bound_args[param.name] = []
                bound_args[param.name].extend(wrapped_args[arg_index:])
                arg_index = args_len
                break

        params = self.sig.parameters
        for name, value in wrapped_kwargs.items():
            if name in params:
                param = params[name]
                if param.kind == Parameter.POSITIONAL_ONLY:
                    raise TypeError(f"参数 {name} 必须是位置参数")
                if name in bound_args:
                    raise TypeError(f"参数 {name} 重复赋值")
                bound_args[name] = value
            else:
                var_kw_param = next(
                    (p for p in params.values() if p.kind == Parameter.VAR_KEYWORD),
                    None
                )
                if var_kw_param:
                    if var_kw_param.name not in bound_args:
                        bound_args[var_kw_param.name] = {}
                    bound_args[var_kw_param.name][name] = value
                else:
                    raise TypeError(f"意外的关键字参数: {name}")

        required_params = self.required_params
        self._is_ready = all(param in bound_args for param in required_params)
        
        if self._is_ready:
            for value in bound_args.values():
                if isinstance(value, DelayCurried) and not value.is_ready:
                    self._is_ready = False
                    break

        if not args_len and not kwargs_len and self._is_ready:
            return self._execute()

        return self
    
    def _execute(self):
        def resolve_value(value):
            if isinstance(value, DelayCurried) and value.is_ready:
                return resolve_value(value())
            if is_lazy(value):
                return resolve_value(value())
            if isinstance(value, list):
                return [resolve_value(v) for v in value]
            if isinstance(value, dict):
                return {k: resolve_value(v) for k, v in value.items()}
            return value

        resolved_args = {}
        bound_args = self.bound_args
        bound_providers = self._bound_providers
        
        for name, value in bound_args.items():
            if name in bound_providers:
                value = bound_providers[name][1]()
            resolved_args[name] = resolve_value(value)

        pos_args = []
        kw_args = {}
        var_pos = []
        var_kw = {}

        for name, param in self.sig.parameters.items():
            if name not in resolved_args:
                continue

            value = resolved_args[name]
            if param.kind in (Parameter.POSITIONAL_OR_KEYWORD, Parameter.POSITIONAL_ONLY):
                pos_args.append(value)
            elif param.kind == Parameter.VAR_POSITIONAL:
                var_pos.extend(value)
            elif param.kind == Parameter.KEYWORD_ONLY:
                kw_args[name] = value
            elif param.kind == Parameter.VAR_KEYWORD:
                var_kw.update(value)

        pos_args.extend(var_pos)
        kw_args.update(var_kw)

        return self.func(*pos_args, **kw_args)

    @property
    def is_ready(self):
        return self._is_ready


def delay_curry(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        return DelayCurried(func)(*args, **kwargs)
    
    return wrapper