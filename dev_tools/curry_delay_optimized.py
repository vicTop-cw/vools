"""
延迟柯里化装饰器 - 优化版本

主要优化：
1. 减少 lazy 包装开销
2. 优化参数绑定逻辑
3. 使用 __slots__ 优化内存
"""

from inspect import signature, Parameter
from functools import wraps, update_wrapper

from .lazy import lazy, is_lazy

__all__ = ['delay_curry', 'DelayCurried', 'is_lazy', 'lazy']


# 缓存函数签名信息
_delay_func_info_cache = {}


def _get_delay_func_info(func):
    """获取函数签名信息，缓存结果"""
    if func not in _delay_func_info_cache:
        sig = signature(func)
        params = sig.parameters
        
        required_params = []
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
                    required_params.append(name)
            else:
                positional_params.append(name)
                if param.default is Parameter.empty:
                    required_params.append(name)
        
        var_count = sum(1 for param in params.values() 
                       if param.kind in (Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD))
        max_args_count = float('inf') if var_count > 0 else len(params) - var_count
        
        _delay_func_info_cache[func] = {
            'sig': sig,
            'params': params,
            'required_params': required_params,
            'positional_params': positional_params,
            'keyword_only_params': keyword_only_params,
            'var_pos_param': var_pos_param,
            'var_kw_param': var_kw_param,
            'max_args_count': max_args_count,
        }
    
    return _delay_func_info_cache[func]


class DelayCurried:
    """延迟柯里化函数对象 - 优化版本"""
    
    __slots__ = ('func', 'bound_args', '_is_ready', '_name', '_doc',
                 'sig', 'params', 'required_params', 'positional_params', 
                 'keyword_only_params', 'var_pos_param', 'var_kw_param',
                 'max_args_count', '_bound_providers')
    
    def __init__(self, func):
        self.func = func
        update_wrapper(self, func)
        self._name = func.__name__ if hasattr(func, '__name__') else f"<lambda>id({id(func)})"
        self._doc = func.__doc__
        self.bound_args = {}
        self._is_ready = False
        self._bound_providers = {}
        
        # 预计算参数信息
        info = _get_delay_func_info(func)
        self.sig = info['sig']
        self.params = info['params']
        self.required_params = info['required_params']
        self.positional_params = info['positional_params']
        self.keyword_only_params = info['keyword_only_params']
        self.var_pos_param = info['var_pos_param']
        self.var_kw_param = info['var_kw_param']
        self.max_args_count = info['max_args_count']
    
    @property
    def has_var_keyword(self):
        return self.var_kw_param is not None
    
    @property
    def has_var_positional(self):
        return self.var_pos_param is not None
    
    @staticmethod
    def resolve_value(value):
        """递归解析所有嵌套的延迟函数和lazy值"""
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
        
    def fill_by_mutil(self, *funcs, provider=None):
        """多个函数的结果合并成一个tuple提供给一个参数"""
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
            for p in providers:
                if p not in self.sig.parameters:
                    raise ValueError(f"参数 {p} 不存在于函数签名中")
        return providers

    def bound_providers(self):
        return self._bound_providers
    
    def _bind_provider(self, provider, value):
        self._bound_providers[provider] = value

    def fill(self, func, providers=None, result_is_dict=False, sep=","):
        """一个函数提供多个关键字参数"""
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
        return (isinstance(other, DelayCurried) and self.func == other.func and
                self.bound_args == other.bound_args and self._bound_providers == other._bound_providers)

    def __ne__(self, other):
        return not self.__eq__(other)

    def register(self, func=None, providers=None, result_is_dict=False, sep=",", return_curried=False):
        """注册参数提供者"""
        if func is None:
            return lambda f: self.register(f, providers, result_is_dict, sep, return_curried)
        _ = self.fill(func, providers, result_is_dict, sep) if providers is not None else self.__call__(func)
        return delay_curry(func) if return_curried else func

    def __call__(self, *args, **kwargs):
        # 包装参数为lazy
        if not args and not kwargs and not self._is_ready:
            return self
        
        # 延迟包装：只在需要时才包装
        wrapped_args = []
        for arg in args:
            if isinstance(arg, (DelayCurried,)) or is_lazy(arg):
                wrapped_args.append(arg)
            else:
                wrapped_args.append(lazy(arg))
        
        wrapped_kwargs = {}
        for k, v in kwargs.items():
            if isinstance(v, (DelayCurried,)) or is_lazy(v):
                wrapped_kwargs[k] = v
            else:
                wrapped_kwargs[k] = lazy(v)

        # 处理位置参数
        arg_index = 0
        for param_name in self.positional_params:
            if param_name in self.bound_args:
                continue
            if arg_index >= len(wrapped_args):
                break
            
            self.bound_args[param_name] = wrapped_args[arg_index]
            arg_index += 1

        # 处理可变位置参数
        if self.var_pos_param and arg_index < len(wrapped_args):
            if self.var_pos_param not in self.bound_args:
                self.bound_args[self.var_pos_param] = []
            self.bound_args[self.var_pos_param].extend(wrapped_args[arg_index:])
            arg_index = len(wrapped_args)

        # 处理关键字参数
        for name, value in wrapped_kwargs.items():
            if name in self.params:
                if name in self.bound_args:
                    raise TypeError(f"参数 {name} 重复赋值")
                self.bound_args[name] = value
            elif self.var_kw_param:
                if self.var_kw_param not in self.bound_args:
                    self.bound_args[self.var_kw_param] = {}
                self.bound_args[self.var_kw_param][name] = value
            else:
                raise TypeError(f"意外的关键字参数: {name}")

        # 检查是否所有必选参数都已绑定
        self._is_ready = all(param in self.bound_args for param in self.required_params)
        
        if self._is_ready:
            self._is_ready = all(not isinstance(value, DelayCurried) or value.is_ready 
                                for value in self.bound_args.values())

        # 如果没有参数且已准备好，执行函数
        if not args and not kwargs and self._is_ready:
            return self._execute()

        # 否则返回自身以继续绑定
        return self
    
    def _execute(self):
        """执行函数，解析所有延迟参数"""
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

        # 解析所有参数
        resolved_args = {}
        for name, value in self.bound_args.items():
            if name in self._bound_providers:
                value = self._bound_providers[name][1]()
            resolved_args[name] = resolve_value(value)

        # 准备执行参数
        pos_args = []
        kw_args = {}

        for name in self.positional_params:
            if name in resolved_args:
                pos_args.append(resolved_args[name])
        
        for name in self.keyword_only_params:
            if name in resolved_args:
                kw_args[name] = resolved_args[name]

        if self.var_pos_param in resolved_args:
            pos_args.extend(resolved_args[self.var_pos_param])
        
        if self.var_kw_param in resolved_args:
            kw_args.update(resolved_args[self.var_kw_param])

        # 执行函数
        return self.func(*pos_args, **kw_args)

    @property
    def is_ready(self):
        return self._is_ready

    @property
    def __name__(self):
        return self._name

    @__name__.setter
    def __name__(self, v):
        self._name = v
    
    @property
    def __doc__(self):
        return self._doc


def delay_curry(func):
    """延迟柯里化装饰器"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        return DelayCurried(func)(*args, **kwargs)
    
    return wrapper