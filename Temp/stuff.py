"""
Stuff - 延迟调用执行框架（改进版）

核心特性：
1. 延迟执行：函数不会立即执行，等到所有必需参数都提供后才执行
2. 参数依赖注入：支持多种参数提供方式
3. 函数组合：支持将多个函数组合成调用链
4. 灵活的装饰器：简化使用语法

使用示例：
    # 简单柯里化
    @stuff
    def add(a, b, c):
        return a + b + c
    result = add(1)(2)(3)()

    # 依赖注入
    @stuff
    def process(data, config):
        return transform(data, config)

    @process.provide(param='data')
    def fetch_data():
        return load_from_db()
"""

from inspect import isclass, signature, Parameter, ismethod
import inspect
from functools import wraps, lru_cache, cached_property
from typing import (
    Any, Callable, Optional, Union, List, Tuple, Dict,
    TypeVar, Generic, overload as typing_overload
)
from collections.abc import Iterable
from collections import OrderedDict

# 尝试导入依赖
try:
    from ..decorators import curry, memorize
except ImportError:
    from vools.decorators import curry, memorize

try:
    from ..decorators.trd import vic_execute
except ImportError:
    # 如果导入失败，提供简单的替代实现
    def vic_execute(max_workers=4, use_process=0):
        def decorator(func):
            def wrapper(iterable):
                return [func(item) for item in iterable]
            return wrapper
        return decorator


__all__ = ['Stuff', 'IndexedDict', 'stuff', 'StuffConfig']

T = TypeVar('T')
F = TypeVar('F', bound=Callable)


class StuffConfig:
    """Stuff 配置类"""
    
    def __init__(
        self,
        cache_duration: float = 3.0,
        max_workers: int = 4,
        debug: bool = False,
        strict: bool = False
    ):
        self.cache_duration = cache_duration
        self.max_workers = max_workers
        self.debug = debug
        self.strict = strict
    
    def copy(self) -> 'StuffConfig':
        return StuffConfig(
            cache_duration=self.cache_duration,
            max_workers=self.max_workers,
            debug=self.debug,
            strict=self.strict
        )


# 默认配置
DEFAULT_CONFIG = StuffConfig()


class IndexedDict:
    """支持索引访问的字典"""
    
    def __init__(
        self,
        data: Any,
        providers_pos: int = 0,
        providers: Optional[List[str]] = None
    ):
        if isinstance(data, (str, bytes)) or not isinstance(data, Iterable):
            data = [data]
        
        if isinstance(data, dict):
            self._data = OrderedDict(data)
        else:
            if providers is None:
                self._data = OrderedDict({i: v for i, v in enumerate(data)})
            else:
                od = OrderedDict()
                for i, d in enumerate(data[:providers_pos]):
                    od[i] = d
                for k, v in zip(providers, data[providers_pos:]):
                    od[k] = v
                self._data = od
    
    def __getitem__(self, key: Union[int, str, slice]) -> Any:
        if isinstance(key, int):
            return self._data[tuple(self._data.keys())[key]]
        if isinstance(key, slice):
            keys = tuple(self._data.keys())[key]
            values = tuple(self._data.values())[key]
            return self.__class__({k: v for k, v in zip(keys, values)})
        return self._data[key]
    
    def keys(self) -> List[str]:
        return list(self._data.keys())
    
    def values(self) -> List[Any]:
        return list(self._data.values())
    
    def items(self) -> List[Tuple[str, Any]]:
        return list(self._data.items())
    
    def __len__(self) -> int:
        return len(self._data)
    
    def __iter__(self):
        return iter(self._data.values())
    
    def __repr__(self) -> str:
        return f"IndexedDict({dict(self._data)})"


class StuffExecutionError(Exception):
    """Stuff 执行错误"""
    pass


class StuffValidationError(Exception):
    """Stuff 参数验证错误"""
    pass


def _create_faked_func(func: Callable) -> Callable:
    """创建带有原始签名的假函数"""
    if isinstance(func, Stuff):
        raise TypeError("func should not be an instance of Stuff")
    
    if not callable(func):
        raise TypeError("func should be a callable object")
    
    # 处理类
    target = func.__init__ if isclass(func) else func
    
    # 获取签名
    try:
        sig = signature(target)
    except (ValueError, TypeError):
        sig = inspect.Signature()
    
    # 构建参数列表
    params = []
    for name, param in sig.parameters.items():
        new_param = Parameter(
            name=name,
            kind=param.kind,
            default=param.default,
            annotation=param.annotation
        )
        params.append(new_param)
    
    new_sig = sig.replace(parameters=params)
    
    if isclass(func):
        class Fake:
            __init__ = _create_faked_func(target)
            __signature__ = new_sig
            __name__ = func.__name__
            __doc__ = func.__doc__
        return Fake
    else:
        @wraps(target)
        def wrapper(*_, **__):
            return None
        wrapper.__signature__ = new_sig
        return wrapper


class Stuff:
    """
    延迟调用执行框架
    
    支持参数依赖注入、函数组合和延迟执行。
    """
    
    def __init__(
        self,
        func: Callable,
        cur: Optional[Any] = None,
        bound_stuffs: Optional[Dict[int, 'Stuff']] = None,
        config: Optional[StuffConfig] = None
    ):
        self.main_func = func
        self._config = config or DEFAULT_CONFIG.copy()
        
        if cur is None:
            self.func = _create_faked_func(func)
            self.curried = curry(self.func, is_strict=self._config.strict, delaied=True)
            self._bound_stuffs: Dict[int, Stuff] = {}
        else:
            self.func = cur.func
            self.curried = cur
            self._bound_stuffs = bound_stuffs or {}
    
    @property
    def config(self) -> StuffConfig:
        return self._config
    
    @property
    def bound_stuffs(self) -> Dict[int, 'Stuff']:
        return self._bound_stuffs
    
    @staticmethod
    @lru_cache(maxsize=128)
    def _get_cached_signature(func: Callable) -> inspect.Signature:
        return signature(func)
    
    @cached_property
    def sig(self) -> inspect.Signature:
        # 处理 CurryDescriptor 和 Curried
        if hasattr(self.curried, 'pre_attrs'):
            # CurryDescriptor
            sig = self.curried.pre_attrs.get('sig')
            if sig is not None:
                return sig
            # 从原始函数获取签名
            return signature(self.curried.func)
        elif hasattr(self.curried, 'sig'):
            # Curried
            return self.curried.sig
        else:
            # 从原始函数获取签名
            return signature(self.func)
    
    @cached_property
    def params(self) -> List[str]:
        return list(self.sig.parameters.keys())
    
    @cached_property
    def has_var_keyword(self) -> bool:
        return any(p.kind == Parameter.VAR_KEYWORD for p in self.sig.parameters.values())
    
    @cached_property
    def has_var_positional(self) -> bool:
        return any(p.kind == Parameter.VAR_POSITIONAL for p in self.sig.parameters.values())
    
    @cached_property
    def is_ready(self) -> bool:
        if self._bound_stuffs:
            # 检查 curried 的 is_ready
            curried_ready = getattr(self.curried, 'is_ready', False)
            return curried_ready and all(f.is_ready for f in self._bound_stuffs.values())
        return getattr(self.curried, 'is_ready', False)
    
    @cached_property
    def isclass(self) -> bool:
        return isclass(self.main_func)
    
    def __getattr__(self, name: str) -> Any:
        # 优先检查 cached_property
        if name in ('sig', 'params', 'has_var_keyword', 'has_var_positional', 'is_ready', 'isclass', 'max_supported_args'):
            # 这些是 cached_property，需要特殊处理
            try:
                return self.__dict__[name]
            except KeyError:
                # 触发 cached_property 计算
                attr = getattr(type(self), name, None)
                if attr is not None and isinstance(attr, cached_property):
                    return attr.__get__(self, type(self))
        
        if name in self.__dict__:
            return self.__dict__[name]
        return getattr(self.curried, name)
    
    @property
    def bound_args(self) -> Dict[str, Callable]:
        try:
            # 处理 CurryDescriptor 和 Curried
            if hasattr(self.curried, 'pre_attrs'):
                # CurryDescriptor
                return self.curried.pre_attrs.get('bound_args', {})
            elif hasattr(self.curried, 'bound_args'):
                # Curried
                return self.curried.bound_args
            return {}
        except AttributeError:
            return {}
    
    # =========================================================================
    # 参数提供方法（改进命名）
    # =========================================================================
    
    def provide(
        self,
        func: Optional[F] = None,
        *,
        param: Optional[Union[str, int, List[str], Tuple[str, ...]]] = None,
        return_stuff: bool = False
    ) -> Union[F, 'Stuff', Callable[[F], Union[F, 'Stuff']]]:
        """
        为目标函数提供参数
        
        参数:
            func: 参数提供函数
            param: 参数名，支持以下格式：
                   - None: 提供一个位置参数
                   - str: 提供一个关键字参数（支持逗号分隔多个参数）
                   - int: 提供指定数量的位置参数
                   - list/tuple: 提供多个关键字参数
            return_stuff: 是否返回 Stuff 实例
        
        返回:
            原函数或 Stuff 实例
        """
        if func is None:
            return lambda f: self.provide(f, param=param, return_stuff=return_stuff)
        
        if return_stuff and not isinstance(func, Stuff):
            func = stuff(func)
        
        func = self._trans(func)[1]
        
        if param is None:
            self.curried = self.curried(func)
        elif isinstance(param, str):
            if ',' in param:
                param_list = [p.strip() for p in param.split(',') if p.strip()]
                self._provide_multi_params(func, param_list)
            else:
                self.curried = self.curried(**{param: func})
        elif isinstance(param, int):
            self._provide_multi_params(func, providers_pos=param)
        elif isinstance(param, (list, tuple)):
            self._provide_multi_params(func, list(param))
        else:
            raise StuffValidationError(
                f"param 参数类型错误，应为 None/str/int/list/tuple，实际为 {type(param)}"
            )
        
        return func
    
    def provide_with(
        self,
        func: Optional[F] = None,
        *args: Any,
        **kwargs: Any
    ) -> Union[F, Callable[[F], F]]:
        """
        注册参数提供函数，同时提供额外参数
        
        参数:
            func: 参数提供函数
            args: 额外的位置参数
            kwargs: 额外的关键字参数（param_name 用于指定参数名）
        """
        if func is None:
            return lambda f: self.provide_with(f, *args, **kwargs)
        
        param = kwargs.pop('param', None)
        func = self._trans(func)[1]
        self.provide(func, param=param, return_stuff=False)
        
        if args or kwargs:
            self.curried = self.curried(*args, **kwargs)
        
        return func
    
    def provide_chain(
        self,
        func: Optional[F] = None,
        *args: Any,
        **kwargs: Any
    ) -> Union['Stuff', Callable[[F], 'Stuff']]:
        """
        注册参数提供函数并返回 Stuff 实例（支持链式调用）
        
        参数:
            func: 参数提供函数
            args: 额外的位置参数
            kwargs: 额外的关键字参数（param 用于指定参数名）
        """
        if func is None:
            return lambda f: self.provide_chain(f, *args, **kwargs)
        
        param = kwargs.pop('param', None)
        
        if not isinstance(func, Stuff):
            func = stuff(func)
        
        func = self._trans(func)[1]
        result = self.provide(func, param=param, return_stuff=True)
        
        return result(*args, **kwargs) if (args or kwargs) else result
    
    def provide_multi_params(
        self,
        func: Callable,
        providers_pos: int = 0,
        providers: Optional[List[str]] = None,
        sep: str = ','
    ) -> 'Stuff':
        """
        一个函数提供多个参数
        
        参数:
            func: 参数提供函数
            providers_pos: 位置参数数量
            providers: 关键字参数名列表
            sep: 字符串分隔符
        """
        return self._provide_multi_params(func, providers_pos, providers, sep)
    
    def _provide_multi_params(
        self,
        func: Callable,
        providers: Optional[List[str]] = None,
        providers_pos: int = 0,
        sep: str = ','
    ) -> 'Stuff':
        """内部实现：一个函数提供多个参数"""
        func = self._trans(func)[1]
        providers_info = self._validate_providers(providers_pos, providers, sep)
        
        if isinstance(func, Stuff):
            self._bound_stuffs[id(func)] = func
        
        # 使用配置的缓存时间
        @memorize(duration=self._config.cache_duration)
        @wraps(func)
        def wrapper():
            result = func()
            return IndexedDict(
                result,
                providers_pos=providers_pos,
                providers=list(providers_info['keys'].keys())
            )
        
        args = []
        if providers_info['pos']:
            for i in range(providers_pos):
                args.append(lambda i=i: wrapper()[i])
        
        kws = {}
        if providers_info['keys']:
            for k in providers_info['keys'].keys():
                kws[k] = lambda k=k: wrapper()[k]
        
        self.curried = self.curried(*args, **kws)
        return self
    
    def aggregate_providers(
        self,
        *funcs: Callable,
        param: Optional[str] = None
    ) -> 'Stuff':
        """
        多个函数聚合到同一参数
        
        参数:
            funcs: 参数提供函数列表
            param: 参数名（None 时作为位置参数）
        """
        if not funcs:
            return self
        
        funcs = [self._trans(f)[1] for f in funcs]
        
        for func in funcs:
            if isinstance(func, Stuff):
                self._bound_stuffs[id(func)] = func
        
        aggregator = lambda: [f() for f in funcs]
        
        if param is None:
            self.curried = self.curried(aggregator)
        else:
            self.curried = self.curried(**{param: aggregator})
        
        return self
    
    # =========================================================================
    # 兼容旧 API（别名）
    # =========================================================================
    
    register = provide  # 别名
    register_by = provide_with  # 别名
    register_stuff = provide_chain  # 别名
    fill = provide_multi_params  # 别名
    fill_multi = aggregate_providers  # 别名
    
    # =========================================================================
    # 参数验证
    # =========================================================================
    
    def _validate_providers_keys(
        self,
        providers: Optional[Union[str, List[str]]],
        sep: str = ","
    ) -> List[str]:
        """验证参数提供者名称"""
        if providers is None:
            return []
        
        if not isinstance(providers, (list, tuple, str)):
            raise StuffValidationError(
                f"providers 参数必须是 list/tuple/str，实际为 {type(providers)}"
            )
        
        if isinstance(providers, str):
            providers = providers.strip().split(sep)
        
        providers = [str(p).strip() for p in providers]
        
        if not providers:
            raise StuffValidationError("providers 不能为空")
        
        if any(k in providers for k in self.bound_args):
            raise StuffValidationError(
                f"providers 参数不能包含已绑定的参数名: {set(providers) & set(self.bound_args.keys())}"
            )
        
        if not self.has_var_keyword:
            for p in providers:
                if p not in self.sig.parameters:
                    raise StuffValidationError(
                        f"参数 '{p}' 不存在于函数签名中，可用参数: {list(self.sig.parameters.keys())}"
                    )
        
        return providers
    
    @cached_property
    def max_supported_args(self) -> int:
        """最大支持参数个数"""
        if self.has_var_positional or self.has_var_keyword:
            return float('inf')
        return len(self.params)
    
    def _validate_providers(
        self,
        providers_pos: int,
        providers: Optional[List[str]],
        sep: str = ','
    ) -> Dict[str, OrderedDict]:
        """验证位置参数提供者"""
        if not isinstance(providers_pos, int):
            raise StuffValidationError(
                f"providers_pos 参数必须是 int，实际为 {type(providers_pos)}"
            )
        
        if providers_pos < 0:
            raise StuffValidationError("providers_pos 参数必须大于等于 0")
        
        leisure_cnt = self.max_supported_args - len(self.bound_args)
        
        if providers_pos > leisure_cnt:
            raise StuffValidationError(
                f"providers_pos 参数不能大于 {leisure_cnt}"
            )
        
        providers = self._validate_providers_keys(providers, sep)
        
        if len(providers) + providers_pos > leisure_cnt:
            raise StuffValidationError(
                f"providers 参数个数不能大于 {leisure_cnt - providers_pos}"
            )
        
        pos = OrderedDict({f'__stuff_pos_{i}': None for i in range(providers_pos)})
        ks = OrderedDict({k: None for k in providers})
        
        return {'pos': pos, 'keys': ks}
    
    # =========================================================================
    # 参数转换
    # =========================================================================
    
    @classmethod
    def _trans(cls, func_or_instance: Any) -> Tuple[bool, Callable]:
        """转换参数提供者"""
        if isinstance(func_or_instance, cls):
            func_or_instance.delaied = True
            return True, func_or_instance
        
        if hasattr(func_or_instance, '__stuff_transed__'):
            return False, func_or_instance
        
        if not callable(func_or_instance):
            f = lambda: func_or_instance
            return False, f
        
        require_cnt = sum(
            1 for name, param in signature(func_or_instance).parameters.items()
            if param.default is Parameter.empty
        )
        
        if require_cnt > 0:
            raise StuffValidationError(
                f"参数提供函数 '{func_or_instance.__name__}' 必须为所有参数提供默认值，"
                f"缺少默认值的参数数量: {require_cnt}"
            )
        
        return False, func_or_instance
    
    # =========================================================================
    # 执行
    # =========================================================================
    
    def _get_only_pos_args_name(self) -> List[str]:
        """获取仅位置参数名"""
        return [
            name for name, param in self.sig.parameters.items()
            if param.kind == Parameter.POSITIONAL_ONLY
        ]
    
    def _evaluate(self) -> Any:
        """执行函数"""
        only_pos_args_name = self._get_only_pos_args_name()
        actual_kwargs: Dict[str, Any] = {}
        actual_args: List[Any] = []
        bounds = self.bound_args.copy()  # 使用 self.bound_args 属性
        l = len(bounds)
        
        # 使用配置的并发数
        @vic_execute(max_workers=self._config.max_workers, use_process=0)
        def compute(v):
            return v()
        
        actuals = compute(bounds.values())
        
        # 处理类方法绑定
        is_class_init = self.isclass and hasattr(self.main_func, '__init__')
        is_bound_method = hasattr(self.main_func, '__self__') and not isclass(self.main_func.__self__)
        
        params_list = list(self.params)
        
        if len(params_list) == 0:
            first_name = None
            first_bound = None
            has_self_cls = False
        else:
            first_name = params_list[0]
            first_bound = list(bounds.keys())[0] if bounds else None
            has_self_cls = first_name in ('cls', 'self') and first_bound == first_name
        
        # 调试输出
        if self._config.debug:
            print(f"[Stuff Debug] is_class_init={is_class_init}, is_bound_method={is_bound_method}")
            print(f"[Stuff Debug] bounds={list(bounds.keys())}, actuals={actuals}")
        
        if (is_class_init or has_self_cls) and first_bound in ('cls', 'self'):
            pre = None
            for i, name in enumerate(bounds.keys()):
                if name == first_name:
                    pre = actuals[i]
                    continue
                if name in only_pos_args_name:
                    actual_args.append(pre)
                else:
                    actual_kwargs[name] = pre
                pre = actuals[i]
            
            if pre is not None:
                if first_name in only_pos_args_name:
                    actual_args.append(pre)
                else:
                    actual_kwargs[params_list[len(bounds)]] = pre
            
            if has_self_cls and not is_class_init:
                actual_kwargs[first_name] = 'NONE'
        else:
            # 正确处理位置参数（整数键）和关键字参数（字符串键）
            pos_args_with_index = []
            
            for i, name in enumerate(bounds.keys()):
                if isinstance(name, int):
                    # 位置参数，记录索引和值
                    pos_args_with_index.append((name, actuals[i]))
                elif name in only_pos_args_name:
                    actual_args.append(actuals[i])
                else:
                    actual_kwargs[name] = actuals[i]
            
            # 按索引排序位置参数
            pos_args_with_index.sort(key=lambda x: x[0])
            actual_args.extend([v for _, v in pos_args_with_index])
            
            if first_name in ('self', 'cls') and first_name not in bounds.keys() and not is_class_init:
                actual_args.insert(0, 'NONE')
        
        return self.main_func(*actual_args, **actual_kwargs)
    
    def __call__(self, *args, **kwargs) -> Any:
        """调用函数"""
        try:
            if not args and not kwargs:
                return self._evaluate()
            
            bound_stuffs = self._bound_stuffs.copy()
            trans = self._trans
            
            gs = []
            for a in args:
                gs.append(trans(a)[1])
                if isinstance(a, Stuff):
                    bound_stuffs[id(a)] = a
            
            ks = {}
            for k, v in kwargs.items():
                ks[k] = trans(v)[1]
                if isinstance(v, Stuff):
                    bound_stuffs[id(v)] = v
            
            new_curried = self.curried(*gs, **ks)
            
            return Stuff(
                self.main_func,
                new_curried,
                bound_stuffs,
                config=self._config
            )
        except Exception as e:
            raise StuffExecutionError(
                f"执行 '{self.main_func.__name__}' 时出错：{e}"
            ) from e
    
    def reset(self) -> 'Stuff':
        """重置所有绑定"""
        self.curried = curry(self.func, is_strict=self._config.strict, delaied=True)
        self._bound_stuffs.clear()
        return self
    
    def __repr__(self) -> str:
        ready = "ready" if self.is_ready else "pending"
        return f"Stuff({self.main_func.__name__}, {ready})"


def stuff(
    func: Optional[F] = None,
    *args: Any,
    config: Optional[StuffConfig] = None,
    **kwargs: Any
) -> Union[Stuff, Callable[[F], Stuff]]:
    """
    Stuff 装饰器
    
    参数:
        func: 目标函数
        args: 初始位置参数
        config: 配置对象
        kwargs: 初始关键字参数
    
    返回:
        Stuff 实例或装饰器
    
    使用示例:
        @stuff
        def add(a, b, c):
            return a + b + c
        
        result = add(1)(2)(3)()
        
        # 带配置
        @stuff(config=StuffConfig(debug=True))
        def process(data):
            return transform(data)
    """
    if func is None:
        return lambda f: stuff(f, *args, config=config, **kwargs)
    
    instance = Stuff(func, config=config)
    return instance(*args, **kwargs) if (args or kwargs) else instance


# =========================================================================
# 测试
# =========================================================================

def test_stuff():
    """测试 Stuff 功能"""
    print("=" * 60)
    print("测试 1: 基本柯里化")
    print("=" * 60)
    
    @stuff
    def add(a, b, c):
        return a + b + c
    
    result = add(1)(2)(3)()
    print(f"add(1)(2)(3)() = {result}")
    assert result == 6
    
    result = add(1, 2, 3)()
    print(f"add(1, 2, 3)() = {result}")
    assert result == 6
    
    print()
    print("=" * 60)
    print("测试 2: 参数依赖注入")
    print("=" * 60)
    
    @stuff
    def sub(a, b, c):
        return a - b - c
    
    @sub.provide
    def get_a():
        return 3
    
    @sub.provide(param=2)
    def get_bc():
        return 2, 1
    
    print(f"sub() = {sub()}")
    assert sub() == 0
    
    print()
    print("=" * 60)
    print("测试 3: 链式依赖")
    print("=" * 60)
    
    # 简化测试：先测试基本的 provide_chain
    @stuff
    def simple_chain(a):
        return f"a={a}"
    
    @simple_chain.provide_chain(param='a')
    def get_a():
        return 3
    
    print(f"simple_chain() = {simple_chain()}")
    assert simple_chain() == 'a=3'
    
    # 测试多参数链式依赖（使用默认值）
    @stuff
    def format_result(a, b=2, c=3):
        return f"a={a},b={b},c={c}"
    
    @format_result.provide_chain(param='a')
    def get_a2():
        return 3
    
    print(f"format_result() = {format_result()}")
    assert format_result() == 'a=3,b=2,c=3'
    
    print()
    print("=" * 60)
    print("测试 4: 多函数聚合")
    print("=" * 60)
    
    @stuff
    def aggregate(a, b, c):
        return f"a={a},b={b},c={c}"
    
    # 先聚合，再提供其他参数
    def get_a():
        return 3
    
    def get_b():
        return 2
    
    def get_c():
        return 1
    
    aggregate.aggregate_providers(get_a, get_b, get_c, param='a')
    
    # 使用 provide_with 同时提供 b 和 c
    @aggregate.provide_with(c=lambda: 3, param='b')
    def get_b2():
        return 2
    
    print(f"aggregate() = {aggregate()}")
    assert aggregate() == 'a=[3, 2, 1],b=2,c=3'
    
    print()
    print("=" * 60)
    print("测试 5: 类方法")
    print("=" * 60)
    
    class Calculator:
        @stuff
        def compute(self, a, b, c):
            return f"a={a},b={b},c={c}"
        
        def get_a(self):
            return 3
        
        def get_b(self):
            return 2
        
        def get_c(self):
            return 1
    
    calc = Calculator()
    print(f"calc.compute.bound_args = {calc.compute.bound_args}")
    print(f"calc.compute(1, 2, 3)() = {calc.compute(1, 2, 3)()}")
    
    calc.compute.aggregate_providers(calc.get_a, calc.get_b, calc.get_c, param='a')
    print(f"calc.compute(c=2, b=3)() = {calc.compute(c=2, b=3)()}")
    
    print()
    print("=" * 60)
    print("测试 6: 类柯里化")
    print("=" * 60)
    
    @stuff
    class DataContainer:
        def __init__(self, a, b, c):
            self.args = (a, b, c)
        
        def __str__(self):
            return f"DataContainer<{self.args}>"
    
    print(f"DataContainer(1, 2, 3)() = {DataContainer(1, 2, 3)()}")
    print(f"DataContainer(1)(2)(3)() = {DataContainer(1)(2)(3)()}")
    
    DataContainer.aggregate_providers(1, 3, 5, param='a')
    DataContainer.provide_with(55, c=lambda: 3, param='b')
    print(f"DataContainer() = {DataContainer()}")
    
    print()
    print("=" * 60)
    print("测试 7: 配置和调试")
    print("=" * 60)
    
    @stuff(config=StuffConfig(debug=True, cache_duration=5))
    def debug_func(a, b):
        return a + b
    
    @debug_func.provide
    def get_a():
        return 1
    
    @debug_func.provide(param='b')
    def get_b():
        return 2
    
    print(f"debug_func() = {debug_func()}")
    
    print()
    print("=" * 60)
    print("测试 8: 重置")
    print("=" * 60)
    
    @stuff
    def reset_test(a, b):
        return a + b
    
    reset_test(1)(2)
    print(f"reset_test.is_ready = {reset_test.is_ready}")
    
    reset_test.reset()
    print(f"reset_test.reset() 后 is_ready = {reset_test.is_ready}")
    
    print()
    print("所有测试通过！")


if __name__ == '__main__':
    test_stuff()