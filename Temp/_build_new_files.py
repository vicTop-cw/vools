
# -*- coding: utf-8 -*-
# 构建脚本：生成新的 overload.py 和 stuff.py
import os

OVERLOAD_PY = r'''
"""
函数重载装饰器模块

提供灵活的函数重载功能，支持：
- 基于参数数量的重载
- 基于参数类型的重载（严格模式）
- 优先级控制（Priority）
- 非同名函数注册（AllowSyncName，需配合 Priority）
- 模糊匹配（Ambiguous，需配合 Priority）
- 类方法支持
- 多种导出模式（export_mode）

导出模式 (export_mode)：
    None              : 不改变原函数（默认）
    ParentMode        : 继承父级管理器的模式设置
    Priority|Strict|..: 成为新的 OverloadManager 实例，使用指定模式组合

示例:
    >>> @overload
    ... def add(a, b):
    ...     return a + b
    >>> @add.register
    ... def add(a, b, c):
    ...     return a + b + c
    >>> add(1, 2)
    3
    >>> add(1, 2, 3)
    6

    >>> @overload(mode=Priority | Strict | AllowSyncName | Ambiguous)
    ... def calc(a, b):
    ...     return a + b
    >>> @calc.register(export_mode=ParentMode)
    ... def calc_int(a: int, b: int):
    ...     return a * b
    >>> calc('Hello', 'World')
    'HelloWorld'
    >>> calc(2, 3)
    6
"""

import inspect
import types
import warnings
from enum import IntFlag
from functools import wraps
from typing import Any, Callable, Optional, List, Tuple, Union

from vools.sig_cache import get_signature
from .curry_core import is_curried

__all__ = ['overload', 'OverloadManager', 'strict',
           'Priority', 'Strict', 'AllowSyncName', 'Ambiguous',
           'ParentMode', 'ExportAsManager', 'ExportAsFunction']


class OverloadMode(IntFlag):
    """
    重载模式枚举

    位掩码，可通过 | 组合使用。

    模式说明:
        Priority       : 优先级模式，按注册时提供的 priority 属性尝试匹配
        Strict         : 严格模式，检查参数类型是否与类型注解匹配
        AllowSyncName  : 允许注册非同名函数（仅在 Priority 模式下有效）
        Ambiguous      : 允许有多个候选函数匹配时也能成功执行（仅在 Priority 下有效）

    导出模式（仅用于 register 的 export_mode 参数）:
        ParentMode     : 继承父级管理器的模式设置
        ExportAsManager: 成为新的 OverloadManager 实例（等价于设置具体模式）
        ExportAsFunction: 不改变原函数（等价于 None，默认行为）
    """
    Priority = 1 << 0
    Strict = 1 << 1
    AllowSyncName = 1 << 2
    Ambiguous = 1 << 3
    ParentMode = 1 << 4
    ExportAsManager = 1 << 5
    ExportAsFunction = 1 << 6


Priority = OverloadMode.Priority
Strict = OverloadMode.Strict
AllowSyncName = OverloadMode.AllowSyncName
Ambiguous = OverloadMode.Ambiguous
ParentMode = OverloadMode.ParentMode
ExportAsManager = OverloadMode.ExportAsManager
ExportAsFunction = OverloadMode.ExportAsFunction


def strict(func: Optional[Callable] = None, *, enabled: bool = True) -> Callable:
    """
    严格类型检查装饰器

    在函数执行前检查参数类型是否符合类型注解。

    参数:
        func: 要检查的函数（可选，用于 @strict 无括号用法）
        enabled: 是否启用类型检查，默认 True

    返回:
        Callable: 包装后的函数

    示例:
        >>> @strict
        ... def add(a: int, b: int) -> int:
        ...     return a + b
        >>> add(1, 2)
        3
        >>> add('a', 'b')  # doctest: +IGNORE_EXCEPTION_DETAIL
        Traceback (most recent call last):
            ...
        TypeError: ...
    """
    def decorator(f: Callable) -> Callable:
        if not enabled:
            return f
        sig = get_signature(f)
        annotations = f.__annotations__

        @wraps(f)
        def wrapper(*args, **kwargs):
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            for name, value in bound.arguments.items():
                if name in annotations:
                    expected_type = annotations[name]
                    if not isinstance(value, expected_type):
                        raise TypeError(
                            f"参数 '{name}' 应为 {expected_type.__name__} 类型，"
                            f"期望 {expected_type.__name__}, 实际 {type(value).__name__}"
                        )
            return f(*args, **kwargs)
        return wrapper

    if func is not None:
        return decorator(func)
    return decorator


def _validate_mode(mode: 'OverloadMode') -> None:
    """
    验证模式组合是否合法。

    - Priority 模式下：可以组合 Strict / AllowSyncName / Ambiguous
    - 非 Priority 模式下：
        * 不可同时使用 AllowSyncName（非优先级模式必须同名）
        * 不可同时使用 Ambiguous（非优先级模式必须唯一匹配）
        * Strict 可以单独使用（严格模式 + 参数数量匹配）

    参数:
        mode: 待验证的模式组合

    异常:
        ValueError: 模式组合不合法
    """
    if not isinstance(mode, OverloadMode):
        # 兼容旧 API：可能传入的不是 OverloadMode
        return
    has_priority = bool(mode & OverloadMode.Priority)
    has_allow_sync = bool(mode & OverloadMode.AllowSyncName)
    has_ambiguous = bool(mode & OverloadMode.Ambiguous)

    if not has_priority:
        if has_allow_sync:
            raise ValueError("非优先级模式下不允许 AllowSyncName（非优先级模式必须同名）")
        if has_ambiguous:
            raise ValueError("非优先级模式下不允许 Ambiguous（非优先级模式必须唯一匹配）")


class OverloadManager:
    """
    重载管理器类。

    支持多种匹配模式和优先级控制。

    属性:
        overloads (List[Tuple[Callable, Callable, int, int]]): 已注册的重载函数列表
            每项格式: (check_func, impl_func, priority, reg_index)
        main_func (Callable): 主函数
        mode (OverloadMode): 当前模式组合
        global_priority (str): 旧 API 兼容：'first' 或 'last'
        name (str): 主函数名称（用于非同名函数注册校验）

    参数:
        main_func: 主函数（可选）
        is_strict: 是否使用严格模式（旧 API 兼容，等同于 mode & Strict）
        global_priority: 旧 API 兼容，'first' 或 'last'
        mode: 模式组合（新 API，OverloadMode）
    """

    def __init__(self,
                 main_func: Optional[Callable] = None,
                 is_strict: bool = False,
                 global_priority: str = 'last',
                 mode: Optional['OverloadMode'] = None):
        self.overloads: List[Tuple[Callable, Callable, int, int]] = []
        self.main_func = main_func
        self.is_strict = is_strict
        self.global_priority = global_priority
        self.counter = 0
        self.name = main_func.__name__ if main_func else None

        if mode is None:
            # 根据旧 API 推导模式
            m = OverloadMode.Priority if True else OverloadMode(0)
            if is_strict:
                m |= OverloadMode.Strict
            # 旧 API 始终允许不同名注册（只是 register 会强制同名）
            # 为向后兼容，这里按默认行为：非优先级模式下保持严格同名
            self.mode = m
        else:
            _validate_mode(mode)
            self.mode = mode
            # 同步 is_strict 以便旧 API 感知
            self.is_strict = bool(self.mode & OverloadMode.Strict)

        if main_func:
            if self.global_priority == 'first':
                pv = -10**9
            else:
                pv = 10**9
            self._register_function(main_func, None, pv)

    # ------------------------------------------------------------------
    # descriptor 支持：类方法/实例方法
    # ------------------------------------------------------------------
    def __get__(self, instance, owner):
        if instance is None:
            return self
        return types.MethodType(self, instance)

    # ------------------------------------------------------------------
    # register / 内部注册
    # ------------------------------------------------------------------
    def register(self,
                 func: Optional[Callable] = None,
                 check: Optional[Callable] = None,
                 priority: Optional[int] = None,
                 export_mode: Union[None, 'OverloadMode', str] = None) -> Union[Callable, 'OverloadManager']:
        """
        注册重载函数（支持作为装饰器使用）。

        参数:
            func: 要注册的函数（若为 None 则返回装饰器）
            check: 自定义检查函数，签名 (args, kwargs) -> bool | (bool, str)
                严格模式下可返回 (bool, error_msg) 元组
            priority: 优先级（数值越大优先级越高，None 表示自动分配）
            export_mode: 导出模式
                None              : 不改变原函数（默认）
                ParentMode        : 继承父级管理器的模式
                Priority|Strict|..: 使被注册函数成为新的 OverloadManager 实例
                ExportAsManager   : 同上（标记用途）
                ExportAsFunction  : 不改变原函数（同 None）

        返回:
            若 export_mode 为 None 或 ExportAsFunction：返回原函数
            若 export_mode 指定为模式或 ParentMode/ExportAsManager：返回新的 OverloadManager

        异常:
            ValueError: 模式组合不合法（如非 Priority 下使用 AllowSyncName 或 Ambiguous）
            ValueError: 非 AllowSyncName 模式下注册了与主函数不同名的函数

        示例:
            >>> @overload(mode=Priority | Strict)
            ... def op(a, b):
            ...     return a + b
            >>> @op.register
            ... def op(a: int, b: int):
            ...     return a * b
            >>> op(2, 3)
            6
        """
        if func is None:
            def decorator(f: Callable) -> Union[Callable, 'OverloadManager']:
                return self._do_register(f, check, priority, export_mode)
            return decorator
        return self._do_register(func, check, priority, export_mode)

    def _do_register(self,
                     func: Callable,
                     check: Optional[Callable],
                     priority: Optional[int],
                     export_mode: Union[None, 'OverloadMode', str]) -> Union[Callable, 'OverloadManager']:
        """
        实际执行注册逻辑的内部方法。
        """
        # 名称检查（非 AllowSyncName 模式下必须同名）
        has_priority = bool(self.mode & OverloadMode.Priority)
        has_allow_sync = bool(self.mode & OverloadMode.AllowSyncName)
        if self.name is not None and func.__name__ != self.name:
            if not (has_priority and has_allow_sync):
                raise ValueError(
                    f"函数名 '{func.__name__}' 与主函数名 '{self.name}' 不一致，"
                    "需在 Priority 模式下同时启用 AllowSyncName"
                )

        # 执行注册
        self._register_function(func, check, priority)

        # 处理 export_mode
        if export_mode is None or export_mode == OverloadMode.ExportAsFunction:
            return func

        if export_mode == OverloadMode.ParentMode:
            new_mode = self.mode
        elif isinstance(export_mode, OverloadMode):
            _validate_mode(export_mode)
            # 若 export_mode 为纯导出标记（无实际行为位），继承父模式
            if not (export_mode & (OverloadMode.Priority | OverloadMode.Strict |
                                   OverloadMode.AllowSyncName | OverloadMode.Ambiguous)):
                new_mode = self.mode
            else:
                new_mode = export_mode
        else:
            # 兼容 str 标记（例如 'parent'）
            if str(export_mode).lower() == 'parent':
                new_mode = self.mode
            else:
                new_mode = self.mode

        manager = OverloadManager(main_func=func, mode=new_mode)
        return manager

    def _register_function(self,
                           func: Callable,
                           check: Optional[Callable] = None,
                           priority: Optional[int] = None) -> None:
        """
        将函数添加到 overloads 列表。
        """
        if priority is None:
            priority = 0
        if check is None:
            if self.is_strict or bool(self.mode & OverloadMode.Strict):
                check = self._create_strict_check(func)
            else:
                check = self._create_count_check(func)
        reg_index = self.counter
        self.counter += 1
        self.overloads.append((check, func, priority, reg_index))
        if self.main_func is None:
            self.main_func = func

    # ------------------------------------------------------------------
    # 参数/类型检查构造器
    # ------------------------------------------------------------------
    def _create_count_check(self, func: Callable) -> Callable:
        """
        基于参数数量的检查函数。

        支持可变位置参数 (*args) 和可变关键字参数 (**kwargs)。
        """
        if is_curried(func):
            if hasattr(func, 'func'):
                func = func.func
        sig = get_signature(func)
        params = sig.parameters
        min_args = sum(
            1 for p in params.values()
            if p.default == p.empty
            and p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        )
        has_var = any(
            p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
            for p in params.values()
        )
        max_args = float('inf') if has_var else len(params)

        def count_check(args, kwargs):
            arg_count = len(args) + len(kwargs)
            return min_args <= arg_count <= max_args
        return count_check

    def _create_strict_check(self, func: Callable) -> Callable:
        """
        基于类型注解的严格检查函数。

        返回 (is_valid: bool, error_msg: Optional[str])。
        """
        if is_curried(func):
            if hasattr(func, 'func'):
                func = func.func
        sig = get_signature(func)
        type_hints = func.__annotations__
        params = sig.parameters

        def strict_check(args, kwargs):
            try:
                bound = sig.bind(*args, **kwargs)
                bound.apply_defaults()
            except TypeError as e:
                return False, f"参数不匹配: {e}"
            errors = []
            for name, value in bound.arguments.items():
                if name in type_hints:
                    expected_type = type_hints[name]
                    param = params[name]
                    if param.kind == inspect.Parameter.VAR_POSITIONAL:
                        for i, item in enumerate(value):
                            if not isinstance(item, expected_type):
                                errors.append(
                                    f"位置参数 {name}[{i}] 类型错误: "
                                    f"期望 {expected_type.__name__}, 实际 {type(item).__name__}"
                                )
                    elif param.kind == inspect.Parameter.VAR_KEYWORD:
                        for key, item in value.items():
                            if not isinstance(item, expected_type):
                                errors.append(
                                    f"**{name} 的键 '{key}' 类型错误: "
                                    f"期望 {expected_type.__name__}, 实际 {type(item).__name__}"
                                )
                    else:
                        if not isinstance(value, expected_type):
                            errors.append(
                                f"参数 '{name}' 类型错误: "
                                f"期望 {expected_type.__name__}, 实际 {type(value).__name__}"
                            )
            if errors:
                return False, "; ".join(errors)
            return True, None
        return strict_check

    # ------------------------------------------------------------------
    # 调用执行
    # ------------------------------------------------------------------
    def __call__(self, *args, **kwargs) -> Any:
        has_priority = bool(self.mode & OverloadMode.Priority)
        has_ambiguous = bool(self.mode & OverloadMode.Ambiguous)
        is_strict = self.is_strict or bool(self.mode & OverloadMode.Strict)

        last_error = None
        matches = []

        if has_priority:
            sorted_impls = sorted(self.overloads, key=lambda x: (-x[2], x[3]))
        else:
            sorted_impls = self.overloads

        for check, func, _, _ in sorted_impls:
            if not is_strict:
                # 非严格模式：参数数量匹配即可（按 call 失败回退）
                try:
                    return func(*args, **kwargs)
                except (TypeError, ValueError) as e:
                    last_error = str(e)
                    matches.append((func, str(e)))
                    continue
            else:
                result = check(args, kwargs)
                if isinstance(result, tuple):
                    is_valid, err = result
                else:
                    is_valid, err = result, None
                if is_valid:
                    if has_priority and not has_ambiguous:
                        # 优先级 + 非模糊：第一个匹配即执行
                        return func(*args, **kwargs)
                    matches.append((func, None))
                else:
                    last_error = err
                    continue

        if has_priority and has_ambiguous and matches:
            # 优先级 + 模糊：第一个匹配执行
            return matches[0][0](*args, **kwargs)

        if not has_priority and matches:
            # 非优先级模式：必须唯一匹配
            if len(matches) == 1:
                return matches[0][0](*args, **kwargs)
            raise TypeError(
                f"非优先级模式下有 {len(matches)} 个重载匹配 '{self.name}' 的调用，"
                "请启用 Priority 模式或修正函数签名"
            )

        if self.main_func:
            try:
                return self.main_func(*args, **kwargs)
            except Exception:
                if last_error:
                    raise TypeError(f"没有找到匹配的重载函数: {last_error}")
                raise

        raise TypeError(
            f"没有找到匹配的重载函数 '{self.name}': "
            + (last_error if last_error else "无可用重载")
        )

    @classmethod
    def create(cls) -> 'OverloadManager':
        """创建一个空的 OverloadManager 实例。"""
        return cls()


def overload(func: Optional[Callable] = None,
             *funcs: Callable,
             is_strict: bool = False,
             priority: str = 'last',
             check: Optional[Callable] = None,
             mode: Optional['OverloadMode'] = None) -> Any:
    """
    函数重载装饰器，支持多种模式和优先级。

    使用方式:
        # 方式一：不带括号（默认 mode = Priority | Strict | AllowSyncName）
        @overload
        def add(a, b): ...

        # 方式二：带括号，使用旧 API
        @overload(is_strict=True, priority='first')
        def add(a, b): ...

        # 方式三：带括号，使用新模式 API（推荐）
        @overload(mode=Priority | Strict | AllowSyncName)
        def calc(a, b): ...

        # 方式四：直接传入多个函数
        add = overload(add_int, add_str, is_strict=True)

    参数:
        func: 主函数（若为 None 则返回装饰器）
        *funcs: 额外的重载函数（旧 API）
        is_strict: 是否使用严格类型检查（旧 API，等同于 mode & Strict）
        priority: 旧 API 全局优先级，'first' 或 'last'
        check: 自定义参数匹配规则（旧 API）
        mode: 新模式组合，OverloadMode 位掩码，如 Priority | Strict

    返回:
        OverloadManager: 重载管理器实例

    示例:
        >>> @overload(mode=Priority | Strict)
        ... def add(a, b):
        ...     return a + b
        >>> @add.register
        ... def add(a: int, b: int):
        ...     return a * b
        >>> add(2, 3)
        6
        >>> add('a', 'b')
        'ab'
    """
    # 推断是否使用"新 API 无括号调用"：第一个参数仅是一个函数且无其他参数
    using_new_no_paren = (
        func is not None
        and not funcs
        and not is_strict
        and priority == 'last'
        and check is None
        and mode is None
        and callable(func)
    )

    if using_new_no_paren:
        # @overload 无括号：默认 mode = Priority | Strict | AllowSyncName
        manager = OverloadManager(
            main_func=func,
            mode=OverloadMode.Priority | OverloadMode.Strict | OverloadMode.AllowSyncName,
        )
        return manager

    if mode is not None:
        # 新 API：使用 mode
        _validate_mode(mode)
        if func is None:
            def decorator(f: Callable) -> OverloadManager:
                mgr = OverloadManager(main_func=f, mode=mode)
                if check is not None:
                    # 若用户提供了全局 check，则替换主函数的 check 函数
                    last_check, last_func, last_prio, last_idx = mgr.overloads[-1]
                    mgr.overloads[-1] = (check, last_func, last_prio, last_idx)
                return mgr
            return decorator
        if callable(func) and not funcs:
            mgr = OverloadManager(main_func=func, mode=mode)
            if check is not None:
                last_check, last_func, last_prio, last_idx = mgr.overloads[-1]
                mgr.overloads[-1] = (check, last_func, last_prio, last_idx)
            return mgr
        mgr = OverloadManager(main_func=func, mode=mode)
        if check is not None:
            last_check, last_func, last_prio, last_idx = mgr.overloads[-1]
            mgr.overloads[-1] = (check, last_func, last_prio, last_idx)
        for f in funcs:
            mgr._register_function(f, check)
        return mgr

    # 旧 API 分支
    if func is None:
        def decorator(f: Callable) -> OverloadManager:
            mgr = OverloadManager(is_strict=is_strict, global_priority=priority)
            main_priority = -10**9 if priority == 'first' else 10**9
            mgr._register_function(f, check, main_priority)
            return mgr
        return decorator

    if callable(func) and not funcs:
        mgr = OverloadManager(is_strict=is_strict, global_priority=priority)
        main_priority = -10**9 if priority == 'first' else 10**9
        mgr._register_function(func, check, main_priority)
        return mgr

    mgr = OverloadManager(is_strict=is_strict, global_priority=priority)
    main_priority = -10**9 if priority == 'first' else 10**9
    mgr._register_function(func, check, main_priority)
    for f in funcs:
        mgr._register_function(f, check)
    return mgr
'''.strip()


STUFF_PY = r'''
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
       - @func.register：注册参数提供函数
       - @func.register_by：带参数注册
       - @func.register_stuff：注册并返回 Stuff 实例
       - @func.provide：register 的别名（推荐新代码使用）
       - @func.provide_with：带参数注册（新 API 推荐）
       - @func.provide_multi_params：多参数提供注册（新 API 推荐）
       - @func.aggregate_providers：聚合多个提供者为同一参数（新 API 推荐）

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

        @calculate_total.register
        def get_price():
            return 100

        @calculate_total.register(param_name=['quantity', 'tax_rate'])
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

        aggregate_data.fill_multi(get_db_data, get_api_data, get_file_data, param_name='sources')

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
from functools import wraps, lru_cache, cached_property
from collections.abc import Iterable
from collections import OrderedDict

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

    提供参数依赖注入能力：通过 register/fill/fill_multi 等方法
    逐步提供参数，最终通过 () 无参调用触发目标函数执行。
    """

    def __init__(self, func, cur=None, bound_stuffs=None, config=None):
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
    # 核心填充方法
    # ------------------------------------------------------------------
    def fill(self, func, providers_pos=0, providers=None, sep=','):
        """
        注册一个提供者函数，并将其结果按位置或关键字填充到目标函数。

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
            return func()

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

    def fill_multi(self, *funcs, param_name=None):
        """
        注册多个提供者，把它们的返回值聚合为同一参数或一组位置参数。

        参数:
            *funcs: 多个提供者（Stuff / 无参函数 / 任意值）
            param_name: 关键字参数名（None 表示作为位置参数列表）

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
        if param_name is None:
            self.curried = self.curried(f)
        else:
            self.curried = self.curried(**{param_name: f})
        return self

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
    # register 系列
    # ------------------------------------------------------------------
    def register(self, func=None, param_name=None, sep=',', returnStuff=False):
        """
        注册参数提供函数。

        兼容旧 API：param_name 可以是 str、int、list、tuple 或逗号分隔字符串。

        参数:
            func: 提供者函数（若为 None 则返回装饰器）
            param_name:
                None                  : 作为下一个位置参数
                str (无逗号)          : 作为指定的关键字参数
                str (含逗号 sep)      : 拆分为多个关键字参数名
                int                   : N 个位置参数（func 的返回值应可迭代）
                list/tuple            : N 个关键字参数名（func 返回值应可迭代）
            sep: param_name 为字符串时的分隔符
            returnStuff: 是否将 func 也包装为 Stuff 实例并返回它

        返回:
            若 returnStuff=True：返回 Stuff 实例
            否则：返回 func（保持原函数可用）

        示例:
            >>> @stuff
            ... def add(a, b, c):
            ...     return a + b + c
            >>> @add.register
            ... def getA():
            ...     return 1
            >>> @add.register(param_name='b')
            ... def getB():
            ...     return 2
            >>> add(c=3)()
            6
        """
        if func is None:
            return lambda f: self.register(f, param_name, sep, returnStuff)

        if returnStuff:
            if not isinstance(func, self.__class__):
                func = stuff(func)

        func = self._trans(func)[1]

        if param_name is None:
            self.curried = self.curried(func)
        elif isinstance(param_name, str):
            if sep in param_name:
                parts = [i.strip() for i in param_name.split(sep) if i.strip()]
                self.fill(func, 0, parts)
            else:
                self.curried = self.curried(**{param_name: func})
        elif isinstance(param_name, int):
            self.fill(func, providers_pos=param_name)
        elif isinstance(param_name, (tuple, list)):
            self.fill(func, 0, param_name)
        else:
            raise TypeError("param_name 参数类型错误")
        return func

    def register_by(self, func=None, *args, **kwargs):
        """
        注册提供者，并立即提供额外的参数。

        参数:
            func: 提供者函数（若为 None 则返回装饰器）
            *args, **kwargs: 额外的位置/关键字参数，将同时绑定到主函数

        返回:
            func（原函数）
        """
        if func is None:
            return lambda f: self.register_by(f, *args, **kwargs)
        param_name = kwargs.pop('param_name', None)
        func = self._trans(func)[1]
        self.register(func, param_name, returnStuff=False)
        if any([args, kwargs]):
            self.curried = self.curried(*args, **kwargs)
        return func

    def register_stuff(self, func=None, *args, **kwargs):
        """
        注册提供者，并将其包装为 Stuff 实例返回。

        若提供了 *args / **kwargs，则进一步将它们绑定到返回的 Stuff 实例。

        参数:
            func: 提供者函数（若为 None 则返回装饰器）
            *args, **kwargs: 额外的参数将绑定到返回的 Stuff 实例

        返回:
            Stuff 实例
        """
        if func is None:
            return lambda f: self.register_stuff(f, *args, **kwargs)
        param_name = kwargs.pop('param_name', None)
        if not isinstance(func, self.__class__):
            func = stuff(func)
        func = self._trans(func)[1]
        result = self.register(func, param_name, returnStuff=True)
        return result(*args, **kwargs) if any([args, kwargs]) else result

    # ------------------------------------------------------------------
    # 新 API 别名（更具表达力的名称）
    # ------------------------------------------------------------------
    def provide(self, func=None, *, name=None):
        """
        注册提供者函数（新 API 推荐别名）。

        参数:
            func: 提供者函数（若为 None 则返回装饰器）
            name: 关键字参数名（None 表示作为下一个位置参数）

        返回:
            func（原函数）
        """
        if func is None:
            return lambda f: self.provide(f, name=name)
        return self.register(func, param_name=name)

    def provide_with(self, func=None, *, names=None):
        """
        注册提供者，其返回值的每个元素将依次填入 names 指定的参数（新 API）。

        参数:
            func: 提供者函数
            names: 参数名称列表

        返回:
            func
        """
        if func is None:
            return lambda f: self.provide_with(f, names=names)
        if names is None:
            return self.register(func, param_name=None)
        if isinstance(names, str):
            return self.register(func, param_name=names)
        return self.register(func, param_name=list(names))

    def provide_multi_params(self, func=None, *, count=1):
        """
        注册提供者，其返回值为可迭代对象，前 count 个元素作为位置参数（新 API）。

        参数:
            func: 提供者函数
            count: 位置参数个数

        返回:
            func
        """
        if func is None:
            return lambda f: self.provide_multi_params(f, count=count)
        return self.register(func, param_name=count)

    def aggregate_providers(self, *providers, name=None):
        """
        聚合多个提供者为同一参数（新 API）。

        参数:
            *providers: 多个提供者（Stuff / 无参函数 / 任意值）
            name: 关键字参数名（None 表示作为下一个位置参数）

        返回:
            self
        """
        return self.fill_multi(*providers, param_name=name)

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

    @sub.register
    def getA():
        return 3

    @sub.register(param_name=2)
    def getB():
        return 2, 1

    assert sub() == 0

    @stuff
    def add(a, b, c):
        return f"a={a},b={b},c={c}"

    @add.register
    def getA():
        return 10

    c = add(b=30, c=20)()
    print(c)
'''

# 写入文件
overload_path = r'E:\IDEProjects\AI\vools\vools\decorators\overload.py'
stuff_path = r'E:\IDEProjects\AI\vools\vools\utils\stuff.py'

with open(overload_path, 'w', encoding='utf-8') as f:
    f.write(OVERLOAD_PY)

with open(stuff_path, 'w', encoding='utf-8') as f:
    f.write(STUFF_PY)

print(f"✅ 已写入: {overload_path}")
print(f"✅ 已写入: {stuff_path}")
