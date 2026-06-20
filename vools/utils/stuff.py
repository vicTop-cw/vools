"""
vools.utils.stuff — 延迟调用执行框架

基于柯里化(curry)实现，支持参数依赖注入、函数组合和延迟执行。
允许逐步构建函数的参数依赖关系，在所有参数就绪时自动执行目标函数。
"""

import inspect
from collections import OrderedDict
from collections.abc import Callable, Iterable, Iterator
from functools import cached_property, lru_cache, wraps
from inspect import Parameter, isclass, ismethod, signature
from typing import Any, List, Optional, Tuple, Union

from ..decorators import curry, memorize
from ..decorators.curry_core import Curried
from ..decorators.trd import vic_execute

__all__ = ['Stuff', 'IndexedDict', 'StuffConfig', 'stuff']


# ============================================================================
# StuffConfig — 配置类
# ============================================================================

class StuffConfig:
    """Stuff 实例的配置对象。

    Attributes:
        cache_duration: memorize 缓存过期秒数（默认 3）
        max_workers: vic_execute 并行线程数，None 表示自动计算（默认 None）
        debug: 是否打印调试信息（默认 False）
        strict: 严格模式，对参数验证更严格（默认 True）
    """
    __slots__ = ('cache_duration', 'max_workers', 'debug', 'strict')

    def __init__(
        self,
        cache_duration: int = 3,
        max_workers: Optional[int] = None,
        debug: bool = False,
        strict: bool = True,
    ) -> None:
        self.cache_duration = cache_duration
        self.max_workers = max_workers
        self.debug = debug
        self.strict = strict

    def __repr__(self) -> str:
        return (
            f"StuffConfig(cache_duration={self.cache_duration}, "
            f"max_workers={self.max_workers}, debug={self.debug}, "
            f"strict={self.strict})"
        )


# ============================================================================
# 自定义异常
# ============================================================================

class StuffExecutionError(Exception):
    """Stuff 执行期间发生的异常。"""
    pass


# ============================================================================
# IndexedDict — 支持整数/字符串双索引的有序字典
# ============================================================================

class IndexedDict:
    """既支持整数索引又支持字符串键的有序字典。

    Args:
        data: 初始化数据（可迭代对象、字典或标量）
        providers_pos: 前 N 个元素作为位置参数
        providers: 后续元素对应的键名列表
    """

    def __init__(
        self,
        data: Any,
        providers_pos: int = 0,
        providers: Optional[List[str]] = None,
    ) -> None:
        if isinstance(data, (str, bytes)) or not isinstance(data, Iterable):
            data = [data]
        if isinstance(data, dict):
            self._data: OrderedDict = OrderedDict(data)
        else:
            if providers is None:
                self._data = OrderedDict(enumerate(data))
            else:
                od: OrderedDict = OrderedDict()
                for i, d in enumerate(data[:providers_pos]):
                    od[i] = d
                for k, v in zip(providers, data[providers_pos:]):
                    od[k] = v
                self._data = od
        self._iter_index: int = 0

    def __getitem__(self, key: Union[int, slice, str]) -> Any:
        if isinstance(key, int):
            return self._data[tuple(self._data.keys())[key]]
        if isinstance(key, slice):
            keys = tuple(self._data.keys())[key]
            vals = tuple(self._data.values())[key]
            return self.__class__(dict(zip(keys, vals)))
        return self._data[key]

    def keys(self) -> Any:
        return self._data.keys()

    def values(self) -> Any:
        return self._data.values()

    def items(self) -> Any:
        return self._data.items()

    def __len__(self) -> int:
        return len(self._data)

    def __iter__(self) -> Iterator:
        self._iter_index = 0
        return self

    def __next__(self) -> Any:
        keys = tuple(self._data.keys())
        if self._iter_index >= len(keys):
            raise StopIteration
        val = self._data[keys[self._iter_index]]
        self._iter_index += 1
        return val


        def do(self, f=print, pre_f=None, sub_f=None):
            """Apply a function for side effects, return self.

            Args:
                f: Function to apply (default print)
                pre_f: Pre-processing function
                sub_f: Post-processing function (no return value expected)

            Returns:
                self, for chaining
            """
            rs = self
            if pre_f:
                rs = pre_f(rs)
            rs = f(rs)
            if sub_f:
                sub_f(rs)
            return self

    def __repr__(self) -> str:
        return f"IndexedDict({self._data})"


# ============================================================================
# _create_faked_func — 创建与目标签名相同的伪函数
# ============================================================================

def _create_faked_func(func: Callable) -> Callable:
    """创建一个与目标函数签名相同的伪函数（供 curry 驱动参数绑定）。

    Args:
        func: 目标函数或类

    Returns:
        与目标签名相同的伪函数（或伪类）

    Raises:
        TypeError: func 是 Stuff 实例或不可调用
    """
    if isinstance(func, Stuff):
        raise TypeError("func should not be an instance of Stuff")
    if not callable(func):
        raise TypeError("func should be a callable object")

    target = func.__init__ if isclass(func) else func

    try:
        sig = signature(target)
    except (ValueError, TypeError):
        sig = inspect.Signature()

    params = [
        Parameter(
            name=name,
            kind=param.kind,
            default=param.default,
            annotation=param.annotation,
        )
        for name, param in sig.parameters.items()
    ]
    new_sig = sig.replace(parameters=params)

    if isclass(func):
        class fake:
            __init__ = _create_faked_func(target)  # type: ignore
            __signature__ = new_sig
            __name__ = func.__name__
            __doc__ = func.__doc__

        return fake

    @wraps(target)
    def wrapper(*_: Any, **__: Any) -> None:
        return None

    wrapper.__signature__ = new_sig  # type: ignore
    return wrapper


# ============================================================================
# Stuff — 延迟调用执行框架核心类
# ============================================================================

class Stuff:
    """延迟调用执行框架，基于柯里化(Curry)实现。

    支持参数依赖注入、函数组合和延迟执行。
    使用方法:
        1. 使用 @stuff 装饰函数或类
        2. 逐步调用提供参数，或用 .provide() 系列方法注册提供者
        3. 无参调用 () 触发最终执行

    Example:
        >>> @stuff
        ... def add(a, b, c):
        ...     return a + b + c
        >>> add(1)(2)(3)()
        6
    """

    def __init__(
        self,
        func: Callable,
        cur: Any = None,
        bound_stuffs: Optional[dict] = None,
        config: Optional[StuffConfig] = None,
    ) -> None:
        self.main_func: Callable = func
        self.config: StuffConfig = config or StuffConfig()
        if cur is None:
            self.func: Callable = _create_faked_func(func)
            self.curried: Any = curry(self.func, is_strict=False, delaied=True)
            # Ensure curried is always a Curried instance (not CurryDescriptor)
            if not isinstance(self.curried, Curried):
                cd = self.curried
                self.curried = Curried(
                    cd.func,
                    is_strict=cd.is_strict,
                    delaied=cd.delaied,
                    **cd.pre_attrs,
                )
            self.bound_stuffs: dict = {}
        else:
            self.func = cur.func
            self.curried = cur
            self.bound_stuffs = bound_stuffs or {}

    # ------------------------------------------------------------------
    # 签名与属性
    # ------------------------------------------------------------------

    @staticmethod
    @lru_cache(maxsize=128)
    def _get_cached_signature(func: Callable) -> Any:
        return signature(func)

    @classmethod
    def _trans(cls, func_or_instance: Any) -> Tuple[bool, Callable]:
        """将输入规范化为可调用的提供者。"""
        if isinstance(func_or_instance, cls):
            func_or_instance.delaied = True
            return True, func_or_instance
        if not callable(func_or_instance):
            f = lambda: func_or_instance
            return False, f
        require_cnt = sum(
            1
            for _, param in signature(func_or_instance).parameters.items()
            if param.default is Parameter.empty
        )
        if require_cnt > 0:
            raise ValueError('func must have default value for all parameters')
        return False, func_or_instance

    @cached_property
    def sig(self) -> Any:
        return self.curried.sig

    @cached_property
    def has_var_keyword(self) -> bool:
        return any(p.kind == Parameter.VAR_KEYWORD for p in self.sig.parameters.values())

    @cached_property
    def has_var_positional(self) -> bool:
        return any(p.kind == Parameter.VAR_POSITIONAL for p in self.sig.parameters.values())

    @cached_property
    def is_ready(self) -> bool:
        if self.bound_stuffs:
            return self.curried.is_ready and all(f.is_ready for f in self.bound_stuffs.values())
        return self.curried.is_ready

    @property
    def max_supported_args(self) -> Union[int, float]:
        if self.has_var_positional or self.has_var_keyword:
            return float('inf')
        return len(self.params)

    @property
    def bound_args(self) -> dict:
        try:
            return self.curried.bound_args
        except AttributeError:
            return {}

    def __getattr__(self, name: str) -> Any:
        if name in self.__dict__:
            return self.__dict__[name]
        curried = self.curried
        # CurryDescriptor stores attrs in pre_attrs dict
        if hasattr(curried, 'pre_attrs') and name in curried.pre_attrs:
            return curried.pre_attrs[name]
        return getattr(curried, name)

    # ------------------------------------------------------------------
    # reset — 重置所有绑定
    # ------------------------------------------------------------------

    def reset(self, keep_config: bool = True) -> 'Stuff':
        """清空所有已绑定的参数和提供者，重置到初始状态。

        Args:
            keep_config: 是否保留当前配置（默认 True，保留配置）

        Returns:
            self（支持链式调用）
        """
        self.func = _create_faked_func(self.main_func)
        self.curried = curry(self.func, is_strict=False, delaied=True)
        self.bound_stuffs = {}
        if not keep_config:
            self.config = StuffConfig()
        return self

    # ------------------------------------------------------------------
    # 参数验证
    # ------------------------------------------------------------------

    def _validate_providers_keys(
        self,
        providers: Optional[Union[List[str], Tuple[str, ...], str]],
        sep: str = ",",
    ) -> List[str]:
        """验证参数提供者的参数名是否合法。"""
        if providers is None:
            return []
        if not isinstance(providers, (list, tuple, str)):
            raise TypeError("providers must be a list, tuple, or string")
        if isinstance(providers, str):
            providers = [p.strip() for p in providers.split(sep) if p.strip()]
        providers_list = [str(p).strip() for p in providers]
        if not providers_list:
            raise ValueError("providers cannot be empty")

        if any(k in providers_list for k in self.bound_args):
            raise ValueError(
                "providers parameter names conflict with already bound parameters"
            )

        if self.config.strict and not self.has_var_keyword:
            for p in providers_list:
                if p not in self.sig.parameters:
                    raise ValueError(f"Parameter '{p}' not found in function signature")
        return providers_list

    def _validate_providers(
        self,
        pos_count: int,
        providers: Optional[Union[List[str], str]],
        sep: str = ",",
    ) -> dict:
        """验证位置参数提供者的合法性。"""
        if not isinstance(pos_count, int):
            raise TypeError("pos_count must be an integer")
        if pos_count < 0:
            raise ValueError("pos_count must be >= 0")

        leisure_cnt: Union[int, float] = self.max_supported_args - len(self.bound_args)
        if pos_count > leisure_cnt:
            raise ValueError(f"pos_count cannot exceed {leisure_cnt}")
        providers_list = self._validate_providers_keys(providers, sep)
        if len(providers_list) + pos_count > leisure_cnt:
            raise ValueError(
                f"providers count cannot exceed {leisure_cnt - pos_count}"
            )
        pos = OrderedDict({f'__stuff_pos_{i}': None for i in range(pos_count)})
        ks = OrderedDict({k: None for k in providers_list})
        return {'pos': pos, 'keys': ks}

    # ------------------------------------------------------------------
    # 新 API 系列
    # ------------------------------------------------------------------

    def provide(
        self,
        func: Optional[Callable] = None,
        for_param: Optional[Union[str, int, List[str], Tuple[str, ...]]] = None,
        *,
        sep: str = ",",
    ) -> Callable:
        """注册一个参数提供函数。

        语义：func 为当前 Stuff 实例提供参数值。

        Args:
            func: 提供者函数（无参，或所有参数有默认值）
            for_param: 为哪个参数提供值：
                - None: 提供一个位置参数
                - str: 提供关键字参数（逗号分隔可表示多个）
                - int: 提供 N 个位置参数
                - list/tuple: 提供多个关键字参数
            sep: for_param 为字符串时的分隔符

        Returns:
            传入的 func（可用作装饰器）
        """
        if func is None:
            return lambda f: self.provide(f, for_param=for_param, sep=sep)

        # Wrap callable funcs in Stuff to enable chained decoration
        if callable(func) and not isinstance(func, self.__class__):
            func = stuff(func)

        func = self._trans(func)[1]

        if for_param is None:
            self.curried = self.curried(func)
        elif isinstance(for_param, str):
            if "," in for_param:
                names = [n.strip() for n in for_param.split(sep) if n.strip()]
                self.provide_multi_params(func, pos_count=0, for_params=names)
            else:
                self.curried = self.curried(**{for_param: func})
        elif isinstance(for_param, int):
            self.provide_multi_params(func, pos_count=for_param)
        elif isinstance(for_param, (tuple, list)):
            self.provide_multi_params(func, pos_count=0, for_params=list(for_param))
        else:
            raise TypeError("for_param type not supported")
        return func

    def provide_with(
        self,
        func: Optional[Callable] = None,
        *args: Any,
        **kwargs: Any,
    ) -> Callable:
        """注册提供者，同时为 Stuff 目标函数提供额外的内联参数。

        Args:
            func: 提供者函数
            *args: 额外的位置参数（传递给目标函数）
            **kwargs: 额外的关键字参数，支持 for_param 指定参数名

        Returns:
            传入的 func（可用作装饰器）
        """
        if func is None:
            return lambda f: self.provide_with(f, *args, **kwargs)
        for_param = kwargs.pop('for_param', None)
        func = self._trans(func)[1]
        self.provide(func, for_param=for_param)
        if args or kwargs:
            self.curried = self.curried(*args, **kwargs)
        return func

    def provide_multi_params(
        self,
        func: Callable,
        pos_count: int = 0,
        for_params: Optional[Union[List[str], Tuple[str, ...], str]] = None,
        *,
        sep: str = ",",
    ) -> 'Stuff':
        """一个函数提供多个参数。

        函数返回值会被按位置/关键字拆分绑定到目标函数的多个参数上。

        Args:
            func: 提供者函数
            pos_count: 返回值中前 N 个作为位置参数
            for_params: 返回值中后续元素对应的关键字参数名列表
            sep: for_params 为字符串时的分隔符

        Returns:
            self（支持链式调用）
        """
        func = self._trans(func)[1]
        validated = self._validate_providers(pos_count, for_params, sep)
        if isinstance(func, self.__class__):
            self.bound_stuffs[id(func)] = func

        def wrapper() -> Any:
            result = func()
            return IndexedDict(
                result,
                providers_pos=pos_count,
                providers=list(validated['keys'].keys()),
            )

        args_list: List[Callable] = []
        if validated['pos']:
            for i in range(pos_count):
                args_list.append(lambda i=i: wrapper()[i])

        kws: dict = {}
        if validated['keys']:
            for k in validated['keys']:
                kws[k] = lambda k=k: wrapper()[k]

        self.curried = self.curried(*args_list, **kws)
        return self

    def aggregate_providers(
        self,
        *funcs: Callable,
        for_param: Optional[str] = None,
    ) -> 'Stuff':
        """多个函数聚合提供同一个参数。

        每个函数的返回值被收集为一个列表，绑定到目标函数的同一个参数上。

        Args:
            *funcs: 多个提供者函数
            for_param: 目标参数名。为 None 时提供位置参数

        Returns:
            self（支持链式调用）
        """
        if not funcs:
            return self
        cls = self.__class__
        funcs_list = [cls._trans(f)[1] for f in funcs]
        for func in funcs_list:
            if isinstance(func, cls):
                self.bound_stuffs[id(func)] = func

        def combined() -> list:
            return [f() for f in funcs_list]

        if for_param is None:
            self.curried = self.curried(combined)
        else:
            self.curried = self.curried(**{for_param: combined})
        return self

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _get_only_pos_args_name(func: Callable) -> List[str]:
        """获取函数中仅位置参数的名称列表。"""
        return [
            name
            for name, param in signature(func).parameters.items()
            if param.kind == Parameter.POSITIONAL_ONLY
        ]

    def _evaluate(self) -> Any:
        """执行最终求值：收集所有参数值并调用目标函数。"""
        only_pos_args_name = self._get_only_pos_args_name(self.main_func)
        actual_kwargs: dict = {}
        actual_args: list = []
        bounds = self.curried.bound_args.copy()
        l = len(bounds)

        @vic_execute(
            max_workers=self.config.max_workers or (l // 3 + 1),
            use_process=0,
        )
        def compute(v: Callable) -> Any:
            return v()

        actuals = compute(bounds.values())

        if self.config.debug:
            print(f"[Stuff._evaluate] bounds={list(bounds.keys())}, actuals={actuals}")

        p = self.isclass and hasattr(self.main_func, '__init__')
        q = p or (
            hasattr(self.main_func, '__self__')
            and not isclass(self.main_func.__self__)
        )
        it = list(self.params)
        if len(it) == 0:
            z = False
            first_name: Optional[str] = None
            first_bound: Optional[str] = None
        else:
            first_name = it[0]
            first_bound = list(bounds.keys())[0]
            z = first_name in ('cls', 'self') and first_bound == first_name

        if (p or z) and first_bound in ('cls', 'self'):
            pre: Any = None
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
                    actual_kwargs[it[len(bounds)]] = pre
            if z and not p:
                actual_kwargs[first_name] = 'NONE'
        else:
            for i, name in enumerate(bounds.keys()):
                if name in only_pos_args_name:
                    actual_args.append(actuals[i])
                else:
                    actual_kwargs[name] = actuals[i]
            if (
                first_name in ('self', 'cls')
                and first_name not in bounds.keys()
                and not p
            ):
                actual_args.insert(0, 'NONE')

        return self.main_func(*actual_args, **actual_kwargs)

    # ------------------------------------------------------------------
    # __call__
    # ------------------------------------------------------------------


        def do(self, f=print, pre_f=None, sub_f=None):
            """Apply a function for side effects, return self.

            Args:
                f: Function to apply (default print)
                pre_f: Pre-processing function
                sub_f: Post-processing function (no return value expected)

            Returns:
                self, for chaining
            """
            rs = self
            if pre_f:
                rs = pre_f(rs)
            rs = f(rs)
            if sub_f:
                sub_f(rs)
            return self

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        try:
            if not args and not kwargs:
                return self._evaluate()
            cls = self.__class__
            trans = cls._trans
            bound_stuffs = self.bound_stuffs.copy()
            gs: list = []
            for a in args:
                gs.append(trans(a)[1])
                if isinstance(a, cls):
                    bound_stuffs[id(a)] = a
            ks: dict = {}
            for k, v in kwargs.items():
                ks[k] = trans(v)[1]
                if isinstance(v, cls):
                    bound_stuffs[id(v)] = v
            new_curried = self.curried(*gs, **ks)
            return cls(self.main_func, new_curried, bound_stuffs, self.config)
        except Exception as e:
            raise StuffExecutionError(
                f"Error executing {self.main_func.__name__}: {e}"
            ) from e


# ============================================================================
# stuff — 顶层装饰器/工厂函数
# ============================================================================

def stuff(
    func: Optional[Callable] = None,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """将函数或类转换为 Stuff 实例。

    支持延迟调用和参数依赖注入。

    Args:
        func: 要装饰的函数或类
        *args: 初始位置参数（直接传递给目标函数）
        **kwargs: 支持 config=StuffConfig(...) 传递配置

    Returns:
        Stuff 实例，或装饰器（当 func 为 None 时）

    Example:
        >>> @stuff
        ... def add(a, b, c):
        ...     return a + b + c
        >>> add(1)(2)(3)()
        6
    """
    if func is None:
        return lambda f: stuff(f, *args, **kwargs)
    config = kwargs.pop('config', None)
    instance = Stuff(func, config=config)
    return instance(*args, **kwargs) if (args or kwargs) else instance
