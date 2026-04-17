"""
延迟柯里化装饰器

提供延迟执行的柯里化功能，支持：
- 延迟参数绑定
- 延迟函数执行
- 参数提供者模式
"""

from inspect import signature, Parameter
from functools import wraps, update_wrapper

__all__ = ['delay_curry', 'DelayCurried', 'is_lazy', 'lazy']


def lazy(value):
    """基础lazy函数，将值包装为延迟求值的函数"""
    if callable(value) and not hasattr(value, '_is_lazy'):
        def wrapper():
            return value()
        wrapper._is_lazy = True
        return wrapper
    if not callable(value) and not hasattr(value, '_is_lazy'):
        if isinstance(value, str):
            from .lazy import lazy as _lazy
            temp = _lazy(value)
            temp._is_lazy = True
            return temp
        else:
            def _constant_wrapper():
                return value
            _constant_wrapper._is_lazy = True
            return _constant_wrapper
        
    return value


def is_lazy(value):
    """检查值是否为lazy包装的延迟值"""
    return callable(value) and hasattr(value, '_is_lazy') and value._is_lazy


class DelayCurried:
    """延迟柯里化函数对象"""
    
    def __init__(self, func):
        self.func = func
        update_wrapper(self, func)
        self.sig = signature(func)
        self.bound_args = {}
        self._is_ready = False

        # 确定必选参数
        self.required_params = [
            name for name, param in self.sig.parameters.items()
            if param.default is Parameter.empty and
               param.kind not in (Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD)
        ]

        var_count = sum(1 for param in self.sig.parameters.values() 
                       if param.kind in (Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD))

        self.max_args_count = float('inf') if var_count > 0 else len(self.sig.parameters) - var_count
        
        self._bound_providers = {}
    
    @property
    def has_var_keyword(self):
        return any(p.kind == Parameter.VAR_KEYWORD for p in self.sig.parameters.values())
    
    @property
    def has_var_positional(self):
        return any(p.kind == Parameter.VAR_POSITIONAL for p in self.sig.parameters.values())
    
    
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
        
    def fill_by_mutil(self, *funcs, provider: str = None):
        """多个函数的结果合并成一个tuple提供给一个参数（延迟执行版）"""
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
        """一个函数提供多个关键字参数，依据返回结果类型自动匹配（延迟执行版）
        
        providers 必须提供参数名列表或逗号分隔的字符串
        """
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
                     frozenset(self.bound_providers.items()) if self.bound_args else None
                     ))

    def __eq__(self, other):
        return (isinstance(other, DelayCurried) and self.func == other.func and
                self.bound_args == other.bound_args and self.bound_providers == other.keywords)

    def __ne__(self, other):
        return not self.__eq__(other)

        
    def register(self, func=None, providers=None, result_is_dict=False, sep=",", return_curried=False):
        """注册参数提供者
        
        Args:
            func: 函数参数的提供者，可以是函数，也可以是其它任意实例
            providers: 为函数提供哪些参数：参数名列表
            result_is_dict: 与providers联合使用，结果是否是字典还是列表
            return_curried: 是否返回一个Stuff实例，默认为False，返回原始函数

        Returns:
            注册后的函数或DelayCurried实例
        """
        if func is None:
            return lambda f: self.register(f, providers, result_is_dict, sep, return_curried)
        _ = self.fill(func, providers, result_is_dict, sep) if providers is not None else self.__call__(func)
        return delay_curry(func) if return_curried else func


    def __call__(self, *args, **kwargs):
        # 包装参数为lazy
        if not args and not kwargs and not self.is_ready:
            return self
        wrapped_args = [lazy(arg) for arg in args]
        wrapped_kwargs = {k: lazy(v) for k, v in kwargs.items()}

        # 处理位置参数
        param_list = list(self.sig.parameters.values())
        arg_index = 0

        for i, param in enumerate(param_list):
            if arg_index >= len(wrapped_args):
                break

            if param.kind in (Parameter.POSITIONAL_OR_KEYWORD, Parameter.POSITIONAL_ONLY):
                if param.name not in self.bound_args:
                    self.bound_args[param.name] = wrapped_args[arg_index]
                    arg_index += 1
            elif param.kind == Parameter.VAR_POSITIONAL:
                if param.name not in self.bound_args:
                    self.bound_args[param.name] = []
                self.bound_args[param.name].extend(wrapped_args[arg_index:])
                arg_index = len(wrapped_args)
                break

        # 处理关键字参数
        for name, value in wrapped_kwargs.items():
            if name in self.sig.parameters:
                param = self.sig.parameters[name]
                if param.kind == Parameter.POSITIONAL_ONLY:
                    raise TypeError(f"参数 {name} 必须是位置参数")
                if name in self.bound_args:
                    raise TypeError(f"参数 {name} 重复赋值")
                self.bound_args[name] = value
            else:
                var_kw_param = next(
                    (p for p in self.sig.parameters.values() if p.kind == Parameter.VAR_KEYWORD),
                    None
                )
                if var_kw_param:
                    if var_kw_param.name not in self.bound_args:
                        self.bound_args[var_kw_param.name] = {}
                    self.bound_args[var_kw_param.name][name] = value
                else:
                    raise TypeError(f"意外的关键字参数: {name}")

        # 检查是否所有必选参数都已绑定
        self._is_ready = all(param in self.bound_args for param in self.required_params)
        
        if self._is_ready:
            self._is_ready = all(value.is_ready for value in self.bound_args.values() 
                                if isinstance(value, DelayCurried))

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
                value = self._bound_providers[name]
                value = value[1]()
            resolved_args[name] = resolve_value(value)

        # 准备执行参数
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

        # 合并参数
        pos_args.extend(var_pos)
        kw_args.update(var_kw)

        # 执行函数
        return self.func(*pos_args, **kw_args)

    @property
    def is_ready(self):
        return self._is_ready


def delay_curry(func):
    """延迟柯里化装饰器
    
    将函数转换为延迟执行的柯里化函数，支持：
    - 延迟参数绑定
    - 延迟函数执行
    - 参数提供者模式
    
    参数:
        func: 要装饰的函数
    
    返回:
        延迟柯里化后的函数
    
    示例:
        >>> @delay_curry
        ... def add(a, b):
        ...     return a + b
        ...
        >>> add(1)(2)()  # 需要显式调用空参数来执行
        3
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        return DelayCurried(func)(*args, **kwargs)
    
    return wrapper
