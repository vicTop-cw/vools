"""
Stuff 延迟调用执行框架

基于柯里化 (curry) 实现的延迟调用执行框架，支持参数依赖注入、函数组合和延迟执行。

核心特性
    1. 延迟执行
       - 函数不会立即执行，而是等到所有必需参数都提供后才执行
       - 支持嵌套依赖，可以构建复杂的函数调用链

    2. 参数依赖注入
       - 参数注入必须是实例、无参函数、或 Stuff 实例
       - 支持一个函数提供多个参数，或多个函数提供同一个参数
       - 自动处理参数绑定和类型检查

    3. 函数组合
       - 支持将多个函数组合成调用链
       - 提供装饰器语法糖，简化使用
       - 支持类方法的柯里化和延迟调用

    4. 灵活的装饰器
       - @stuff：基本装饰器，将函数转换为 Stuff 实例
       - @func.provide：注册参数提供函数（单个参数）
       - @func.provide_with：注册返回多个参数的提供者
       - @func.provide_multi_params：注册返回多个位置参数的提供者
       - @func.aggregate_providers：聚合多个提供者为同一参数

基本用法
    简单示例:

        @stuff
        def add(a, b, c):
            return a + b + c

        result = add(1)(2)(3)()      # 返回 6
        result = add(1, 2, 3)()       # 返回 6

    参数依赖注入:

        @stuff
        def calculate_total(price, quantity, tax_rate):
            return price * quantity * (1 + tax_rate)

        @calculate_total.provide(name='price')
        def get_price():
            return 100

        @calculate_total.provide_with(names=['quantity', 'tax_rate'])
        def get_quantity_and_tax():
            return 2, 0.1

        result = calculate_total()     # 自动调用依赖函数

高级功能
    1. 类支持

        @stuff
        class Calculator:
            def __init__(self, base_value, multiplier):
                self.base = base_value
                self.multiplier = multiplier

            def compute(self, x):
                return self.base + x * self.multiplier

    2. 多函数提供同一参数

        aggregate_data.aggregate_providers(get_db_data, get_api_data, get_file_data, name='sources')

    3. 配置项
        StuffConfig(cache_duration=3.0, max_workers=4, debug=False, strict=False)

注意事项
    - 函数必须为所有参数提供默认值，或者通过依赖注入完整提供
    - 参数名不能重复绑定
    - 必须使用无参调用 () 触发最终执行
    - 不支持内置函数和 C 扩展函数（无法获取签名）
"""

import inspect
from inspect import isclass, signature, Parameter, ismethod
from functools import wraps, lru_cache
try:
    from functools import cached_property
except ImportError:
    class cached_property(object):
        def __init__(self, func):
            self.func = func
            self.__doc__ = getattr(func, '__doc__')
        def __get__(self, instance, cls):
            if instance is None:
                return self
            value = instance.__dict__[self.func.__name__] = self.func(instance)
            return value
from collections.abc import Iterable
from collections import OrderedDict
from typing import Callable, Any, Optional, Union, List, Tuple, Dict

from ..decorators import curry, memorize
from ..decorators.trd import vic_execute

__all__ = ['Stuff', 'IndexedDict', 'stuff', 'StuffConfig']


class StuffExecutionError(Exception):
    """Stuff 执行过程中抛出的异常。"""
    pass


class IndexedDict:
    """
    可通过整数索引或关键字访问的有序字典。

    参数:
        data: 数据内容（字典/可迭代对象/单个值）
        providers_pos: 位置参数的起始位置
        providers: 位置参数后关键字参数的名称列表
    """

    def __init__(self, data, providers_pos=0, providers=None):
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

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._data[tuple(self._data.keys())[key]]
        if isinstance(key, slice):
            return self.__class__({
                k: v for k, v in zip(
                    tuple(self._data.keys())[key], tuple(self._data.values())[key]
                )
            })
        return self._data[key]

    def keys(self):
        return self._data.keys()

    def values(self):
        return self._data.values()

    def items(self):
        return self._data.items()

    def __len__(self):
        return len(self._data)

    def __iter__(self):
        return iter(self._data.values())

    def __next__(self):
        return next(iter(self._data.values()))

    def __repr__(self):
        return f"IndexedDict({self._data})"


class StuffConfig:
    """
    Stuff 全局/局部配置。

    属性:
        cache_duration (float): 提供者结果缓存时长（秒），默认 3.0
        max_workers (int): 并发执行提供者时的最大线程数，默认 4
        debug (bool): 是否打印调试信息，默认 False
        strict (bool): 是否启用严格参数校验，默认 False
    """

    def __init__(self, cache_duration=3.0, max_workers=4, debug=False, strict=False):
        self.cache_duration = cache_duration
        self.max_workers = max_workers
        self.debug = debug
        self.strict = strict


_DEFAULT_CONFIG = StuffConfig()


def _create_faked_func(func):
    """
    创建一个带正确签名的"空壳"函数，供 curry 进行参数绑定。

    参数:
        func: 原始函数或类

    返回:
        一个具有与 func 相同签名但不做任何事的函数/类
    """
    if isinstance(func, Stuff):
        raise TypeError("不能 Stuff 另一个 Stuff 实例")
    if not callable(func):
        raise TypeError("func 必须是可调用对象")

    if isclass(func):
        target = func.__init__
    else:
        target = func

    try:
        sig = signature(target)
    except (ValueError, TypeError):
        sig = inspect.Signature()

    params = []
    for name, param in sig.parameters.items():
        new_param = Parameter(
            name=name, kind=param.kind,
            default=param.default, annotation=param.annotation
        )
        params.append(new_param)
    new_sig = sig.replace(parameters=params)

    if isclass(func):
        class fake:
            __init__ = _create_faked_func(target)
            __signature__ = new_sig
            __name__ = func.__name__
            __doc__ = func.__doc__
        return fake

    @wraps(target)
    def wrapper(*_, **__):
        return None
    wrapper.__signature__ = new_sig
    return wrapper


class Stuff:
    """
    Stuff 延迟调用执行类。

    提供参数依赖注入能力：通过 provide/provide_with/aggregate_providers 等方法
    逐步提供参数，最终通过 () 无参调用触发目标函数执行。
    """

    def __init__(
        self,
        func: Callable[..., Any],
        cur: Optional[Any] = None,
        bound_stuffs: Optional[Dict[int, 'Stuff']] = None,
        config: Optional[StuffConfig] = None
    ) -> None:
        """初始化 Stuff 实例。

        Args:
            func: 要包装的函数或类
            cur: 可选的 curried 函数
            bound_stuffs: 已绑定的 Stuff 实例字典
            config: Stuff 配置
        """
        self.main_func = func
        self.config = config or _DEFAULT_CONFIG
        if cur is None:
            self.func = _create_faked_func(func)
            self.curried = curry(self.func, is_strict=False, delaied=True)
            self.bound_stuffs = {}
        else:
            self.func = cur.func
            self.curried = cur
            self.bound_stuffs = bound_stuffs or {}

    # ------------------------------------------------------------------
    # 工具类静态方法
    # ------------------------------------------------------------------
    @staticmethod
    @lru_cache(maxsize=128)
    def _get_cached_signature(func):
        """缓存函数签名，避免重复构建。"""
        return signature(func)

    @classmethod
    def _trans(cls, func_or_instance):
        """
        将参数转换为 Stuff 可接受的形式。

        - Stuff 实例：标记延迟并直接返回
        - 已 __stuff_transed__：直接返回
        - 不可调用对象：包装为 lambda 无参函数
        - 有参函数：必须所有参数都有默认值，否则抛出 ValueError
        """
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
            raise ValueError('func must have default value for all parameters')
        return False, func_or_instance

    # ------------------------------------------------------------------
    # cached_property：惰性计算的属性
    # ------------------------------------------------------------------
    @cached_property
    def sig(self):
        """获取主函数的签名（若 curry 已绑定则从其获取）。"""
        try:
            return self.curried.sig
        except AttributeError:
            try:
                pre = getattr(self.curried, 'pre_attrs', {})
                if 'sig' in pre:
                    return pre['sig']
            except Exception:
                pass
            return signature(self.main_func)

    @cached_property
    def params(self):
        """所有参数名称列表。"""
        return list(self.sig.parameters.keys())

    @cached_property
    def has_var_keyword(self):
        """是否存在 **kwargs 形式的可变关键字参数。"""
        return any(
            p.kind == Parameter.VAR_KEYWORD for p in self.sig.parameters.values()
        )

    @cached_property
    def has_var_positional(self):
        """是否存在 *args 形式的可变位置参数。"""
        return any(
            p.kind == Parameter.VAR_POSITIONAL for p in self.sig.parameters.values()
        )

    @cached_property
    def is_ready(self):
        """所有参数（包括嵌套 Stuff）是否都已就绪。"""
        if self.bound_stuffs:
            return self.curried.is_ready and all(
                f.is_ready for f in self.bound_stuffs.values()
            )
        return self.curried.is_ready

    @cached_property
    def isclass(self):
        """主函数是否为一个类。"""
        return isclass(self.main_func)

    @cached_property
    def max_supported_args(self):
        """最多可接受的位置+关键字参数数量（无限参数时为 inf）。"""
        if self.has_var_positional or self.has_var_keyword:
            return float('inf')
        return len(self.params)

    # ------------------------------------------------------------------
    # 属性回退
    # ------------------------------------------------------------------
    def __getattr__(self, name):
        if name in self.__dict__:
            return self.__dict__[name]
        return getattr(self.curried, name)

    # ------------------------------------------------------------------
    # 参数验证
    # ------------------------------------------------------------------
    def _validate_providers_keys(self, providers, sep=','):
        """验证关键字参数名称列表是否合法。

        参数:
            providers: 参数名称列表/字符串
            sep: 字符串分隔符

        返回:
            清理后的参数名称列表

        异常:
            TypeError: providers 类型不合法
            ValueError: providers 为空或包含已绑定参数名
        """
        if providers is None:
            return []
        if not isinstance(providers, (list, tuple, str)):
            raise TypeError("providers参数必须是列表或元组或字符串")
        if isinstance(providers, str):
            providers = providers.strip().split(sep)
        providers = [str(p).strip() for p in providers]
        if not providers:
            raise ValueError("providers不能为空")
        if any(k in providers for k in self.bound_args):
            raise ValueError(
                "providers参数不能包含函数签名中已存在的参数名"
            )
        if not self.has_var_keyword:
            for p in providers:
                if p not in self.sig.parameters:
                    raise ValueError(f"{p} 不存在于函数签名中")
        return providers

    def _validate_providers(self, providers_pos, providers, sep=','):
        """验证位置参数和关键字参数的组合是否合法。

        参数:
            providers_pos: 位置参数个数
            providers: 关键字参数名称列表/字符串
            sep: 字符串分隔符

        返回:
            {'pos': OrderedDict, 'keys': OrderedDict} 结构

        异常:
            TypeError: providers_pos 类型不合法
            ValueError: providers_pos 超出剩余参数槽位
        """
        if not isinstance(providers_pos, int):
            raise TypeError("providers_pos 参数必须是整数")
        if providers_pos < 0:
            raise ValueError("providers_pos 参数必须大于等于 0")
        leisure_cnt = self.max_supported_args - len(self.bound_args)
        if providers_pos > leisure_cnt:
            raise ValueError(f"providers_pos  不能大于 {leisure_cnt}")
        providers = self._validate_providers_keys(providers, sep)
        if len(providers) + providers_pos > leisure_cnt:
            raise ValueError(
                f"providers  参数个数不能大于 {leisure_cnt - providers_pos}"
            )
        pos = OrderedDict({f"__stuff_pos_{i}": None for i in range(providers_pos)})
        ks = OrderedDict({k: None for k in providers})
        return {'pos': pos, 'keys': ks}

    # ------------------------------------------------------------------
    # 核心填充方法（内部使用）
    # ------------------------------------------------------------------
    def _fill(
        self,
        func: Union['Stuff', Callable[..., Any], Any],
        providers_pos: int = 0,
        providers: Optional[Union[List[str], Tuple[str, ...], str]] = None,
        sep: str = ','
    ) -> 'Stuff':
        """注册一个提供者函数，并将其结果按位置或关键字填充到目标函数。

        参数:
            func: 提供者函数（Stuff 实例 / 无参函数 / 任意值）
            providers_pos: 位置参数个数
            providers: 关键字参数名称列表/字符串
            sep: 字符串 providers 的分隔符

        返回:
            self（支持链式调用）
        """
        func = self._trans(func)[1]
        providers = self._validate_providers(providers_pos, providers, sep)
        if isinstance(func, self.__class__):
            self.bound_stuffs[id(func)] = func

        duration = self.config.cache_duration

        @memorize(duration=duration)
        @wraps(func)
        def wrapper():
            result = func()
            return IndexedDict(result, providers_pos=providers_pos, providers=list(providers['keys'].keys()))

        args = []
        if providers['pos']:
            for i in range(providers_pos):
                args.append(lambda i=i: wrapper()[i])
        kws = {}
        if providers['keys']:
            for k in providers['keys'].keys():
                kws[k] = lambda k=k: wrapper()[k]

        self.curried = self.curried(*args, **kws)
        return self

    def _fill_multi(
        self,
        *funcs: Union['Stuff', Callable[..., Any], Any],
        name: Optional[str] = None
    ) -> 'Stuff':
        """注册多个提供者，把它们的返回值聚合为同一参数或一组位置参数。

        参数:
            *funcs: 多个提供者（Stuff / 无参函数 / 任意值）
            name: 关键字参数名（None 表示作为位置参数列表）

        返回:
            self（支持链式调用）
        """
        if not funcs:
            return self
        cls = self.__class__
        funcs = [cls._trans(f)[1] for f in funcs]
        for func in funcs:
            if isinstance(func, cls):
                self.bound_stuffs[id(func)] = func
        f = lambda: [f() for f in funcs]
        if name is None:
            self.curried = self.curried(f)
        else:
            self.curried = self.curried(**{name: f})
        return self

    # ------------------------------------------------------------------
    # 新 API（推荐使用）
    # ------------------------------------------------------------------
    def provide(self, func=None, *, name=None):
        """
        注册提供者函数。

        参数:
            func: 提供者函数（若为 None 则返回装饰器）
            name: 关键字参数名（None 表示作为下一个位置参数）

        返回:
            self（支持链式调用）

        示例:
            >>> @stuff
            ... def add(a, b, c):
            ...     return a + b + c
            >>> @add.provide
            ... def getA():
            ...     return 1
            >>> @add.provide(name='b')
            ... def getB():
            ...     return 2
            >>> add.provide(lambda: 3, name='c')
            >>> add()
            6
        """
        if func is None:
            return lambda f: self.provide(f, name=name)
        func = self._trans(func)[1]
        if isinstance(func, self.__class__):
            self.bound_stuffs[id(func)] = func
        if name is None:
            self.curried = self.curried(func)
        else:
            self.curried = self.curried(**{name: func})
        return self

    def provide_with(self, func=None, *, names=None):
        """
        注册提供者，其返回值的每个元素将依次填入 names 指定的参数。

        参数:
            func: 提供者函数
            names: 参数名称列表（None 表示作为下一个位置参数）

        返回:
            self

        示例:
            >>> @stuff
            ... def calc(a, b, c):
            ...     return a * b * c
            >>> @calc.provide_with(names=['a', 'b'])
            ... def get_ab():
            ...     return 2, 3
            >>> calc.provide(lambda: 4, name='c')
            >>> calc()
            24
        """
        if func is None:
            return lambda f: self.provide_with(f, names=names)
        if names is None:
            return self.provide(func, name=None)
        if isinstance(names, str):
            names = [names]
        return self._fill(func, 0, list(names))

    def provide_multi_params(self, func=None, *, count=1):
        """
        注册提供者，其返回值为可迭代对象，前 count 个元素作为位置参数。

        参数:
            func: 提供者函数
            count: 位置参数个数

        返回:
            self

        示例:
            >>> @stuff
            ... def add(a, b, c):
            ...     return a + b + c
            >>> @add.provide_multi_params(count=2)
            ... def get_ab():
            ...     return 1, 2
            >>> add.provide(lambda: 3, name='c')
            >>> add()
            6
        """
        if func is None:
            return lambda f: self.provide_multi_params(f, count=count)
        return self._fill(func, providers_pos=count)

    def aggregate_providers(self, *providers, name=None):
        """
        聚合多个提供者为同一参数。

        参数:
            *providers: 多个提供者（Stuff / 无参函数 / 任意值）
            name: 关键字参数名（None 表示作为下一个位置参数）

        返回:
            self

        示例:
            >>> @stuff
            ... def process(data):
            ...     return sum(data)
            >>> process.aggregate_providers(lambda: 1, lambda: 2, lambda: 3)
            >>> process()
            6
        """
        return self._fill_multi(*providers, name=name)

    # ------------------------------------------------------------------
    # 参数执行
    # ------------------------------------------------------------------
    @staticmethod
    def _get_only_pos_args_name(func):
        """获取仅位置参数 (POSITIONAL_ONLY) 的参数名列表。"""
        return [
            name for i, (name, param) in enumerate(signature(func).parameters.items())
            if param.kind == Parameter.POSITIONAL_ONLY
        ]

    def _evalate_old(self):
        """回退执行路径：串行解析参数。"""
        only_pos_args_name = self._get_only_pos_args_name(self.main_func)
        actual_kwargs = {}
        actual_args = []
        for name, arg in self.bound_args.items():
            if name in only_pos_args_name:
                actual_args.append(arg())
            else:
                actual_kwargs[name] = arg()
        return self.main_func(*actual_args, **actual_kwargs)

    def _evalate(self):
        """
        真正执行：

        - 并发调用所有绑定的 provider（若配置允许）
        - 根据主函数类型（类/实例方法/普通函数）分发到正确路径
        - 处理 POSITIONAL_ONLY 参数
        """
        only_pos_args_name = self._get_only_pos_args_name(self.main_func)
        actual_kwargs = {}
        actual_args = []
        bounds = self.curried.bound_args.copy()
        l = len(bounds)

        @vic_execute(max_workers=self.config.max_workers, use_process=0)
        def compute(v):
            return v()

        actuals = compute(bounds.values())

        p = self.isclass and hasattr(self.main_func, '__init__')
        q = p or (
            hasattr(self.main_func, '__self__') and not isclass(self.main_func.__self__)
        )
        it = list(self.params)
        if len(it) == 0:
            first_name = None
            first_bound = None
        else:
            first_name = it[0]
            first_bound = list(bounds.keys())[0]
            z = first_name in ('cls', 'self') and first_bound == first_name

        if (p or z) and first_bound in ('cls', 'self'):
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
                    actual_kwargs[it[len(bounds)]] = pre
            if z and not p:
                actual_kwargs[first_name] = 'NONE'
        else:
            for i, name in enumerate(bounds.keys()):
                if name in only_pos_args_name:
                    actual_args.append(actuals[i])
                else:
                    actual_kwargs[name] = actuals[i]
            if (first_name in ('self', 'cls')
                    and first_name not in bounds.keys()
                    and not p):
                actual_args.insert(0, 'NONE')

        return self.main_func(*actual_args, **actual_kwargs)

    @property
    def bound_args(self):
        """当前已绑定的参数（来自 curried）。"""
        try:
            return self.curried.bound_args
        except AttributeError:
            return {}

    # ------------------------------------------------------------------
    # 主调用入口
    # ------------------------------------------------------------------
    def __call__(self, *args, **kwargs):
        """调用 Stuff 实例：填充参数或触发执行。

        - 无参数调用 ()：触发目标函数执行
        - 有参数调用：返回新的 Stuff 实例（绑定新参数）

        参数:
            *args: 位置参数（可包含 Stuff 实例）
            **kwargs: 关键字参数（可包含 Stuff 实例）

        返回:
            无参数调用：目标函数执行结果
            有参数调用：新的 Stuff 实例

        异常:
            StuffExecutionError: 执行过程中发生错误
        """
        try:
            if not args and not kwargs:
                return self._evalate()
            cls = self.__class__
            bound_stuffs = self.bound_stuffs.copy()
            gs = []
            for a in args:
                gs.append(cls._trans(a)[1])
                if isinstance(a, cls):
                    bound_stuffs[id(a)] = a
            ks = {}
            for k, v in kwargs.items():
                ks[k] = cls._trans(v)[1]
                if isinstance(v, cls):
                    bound_stuffs[id(v)] = v
            new_curried = self.curried(*gs, **ks)
            return cls(self.main_func, new_curried, bound_stuffs, config=self.config)
        except Exception as e:
            raise StuffExecutionError(f"Stuff 执行失败: {e}") from e

    # ------------------------------------------------------------------
    # 其它工具
    # ------------------------------------------------------------------
    def reset(self):
        """
        重置所有已绑定的参数。

        重新初始化 curried 为一个全新的 curry 实例。
        """
        self.func = _create_faked_func(self.main_func)
        self.curried = curry(self.func, is_strict=False, delaied=True)
        self.bound_stuffs = {}
        # 清除所有 cached_property 缓存
        for key in ('sig', 'params', 'has_var_keyword',
                    'has_var_positional', 'is_ready',
                    'isclass', 'max_supported_args'):
            try:
                self.__dict__.pop(key, None)
            except Exception:
                pass
        return self


def stuff(func=None, *args, **kwargs):
    """
    将函数或类包装为 Stuff 实例（装饰器入口）。

    使用方式:
        @stuff
        def add(a, b, c): ...

        @stuff
        class Calculator: ...

        calc = stuff(some_function, 1, 2)  # 预填充部分参数

    参数:
        func: 要包装的函数/类（若为 None 返回装饰器）
        *args, **kwargs: 预填充的位置/关键字参数

    返回:
        Stuff 实例
    """
    if func is None:
        return lambda f: stuff(f, *args, **kwargs)
    result = Stuff(func)
    if any([args, kwargs]):
        result = result(*args, **kwargs)
    return result


if __name__ == "__main__":
    @stuff
    def sub(a, b, c):
        return a - b - c

    @sub.provide
    def getA():
        return 3

    @sub.provide_multi_params(count=2)
    def getB():
        return 2, 1

    assert sub() == 0

    @stuff
    def add(a, b, c):
        return f"a={a},b={b},c={c}"

    @add.provide
    def getA():
        return 10

    c = add.provide(lambda: 30, name='b').provide(lambda: 20, name='c')()
    print(c)