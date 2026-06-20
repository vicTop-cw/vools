"""
条件判断工具模块

提供 iif 函数和 ConditionBuilder 类，用于灵活的条件判断和分支处理。

改进说明（相对原始版本）：
  - [修复] LazyProperty 双路缓存策略，兼容 __slots__ 宿主类
  - [修复] __and__ 操作符：条件数不一致时抛出明确异常；文档化语义
  - [修复] comp.setter 各分支独立 return，消除 UnboundLocalError 隐患
  - [修复] iif() whens 分支传参错误：正确使用 data 而非 condition 作为求值目标
  - [修复] default/otherwise 用哨兵值 _UNSET，支持将 None 设为有效默认值
  - [修复] __call__ 移除对 self.base 的副作用修改，builder 可安全复用
  - [改进] _OPERATORS 中 '?'/'_?'/'bool' 合并语义，保留向后兼容别名
  - [改进] _fix_comp 优先用 try/except 替代 inspect.signature 降低性能开销
  - [改进] evaluateEx 重命名为 evaluate_each（保留旧名作别名）
  - [改进] whens 方法增加输入类型校验
  - [改进] 移除未使用的 sht 参数（保留向后兼容，但标注为 deprecated）
  - [改进] 修正拼写：_comp_lable -> _comp_label
  - [改进] iif() 字符串条件分支提取为 _eval_string_condition 内部函数
  - [改进] 补全主要方法的类型注解
"""

import inspect as ins
from collections.abc import Iterable
from functools import wraps, lru_cache
from typing import Any, Callable, Optional, Union, List, Dict, Tuple
from ..security.safe_eval import safe_lambda, SafeEvalError

__all__ = ["LazyProperty", "ConditionBuilder", "iif"]

# 哨兵对象，用于区分"未设置"与 None
_UNSET = object()


class LazyProperty:
    """
    延迟属性描述符，属性为只读。

    缓存策略（双路，按宿主类是否允许动态属性自动选择）：

    1. **普通类**（有 ``__dict__``）：首次计算后直接写入实例字典，
       后续访问由 Python 属性查找机制直接返回，描述符不再介入。
    2. **__slots__ 类**（无 ``__dict__``）：结果缓存在描述符内部的
       ``dict`` 中，以 ``id(instance)`` 为键。
    """

    def __init__(self, func: Callable) -> None:
        self.func = func
        self._attr_name: Optional[str] = None
        self._id_cache: Dict[int, Any] = {}
        wraps(func)(self)

    def __set_name__(self, owner: type, name: str) -> None:
        """Python 3.6+ 自动获取属性名"""
        self._attr_name = f"_lazy_{name}"

    def __get__(self, instance: Any, cls: Any) -> Any:
        if instance is None:
            return self
        # 路径 1：普通类，尝试写入实例 __dict__
        if hasattr(instance, '__dict__'):
            attr = self._attr_name or f"_lazy_{self.func.__name__}"
            cached = instance.__dict__.get(attr, _UNSET)
            if cached is not _UNSET:
                return cached
            value = self.func(instance)
            try:
                instance.__dict__[attr] = value
            except (AttributeError, TypeError):
                pass
            return value
        # 路径 2：__slots__ 类，使用内部 id 缓存
        key = id(instance)
        if key not in self._id_cache:
            self._id_cache[key] = self.func(instance)
        return self._id_cache[key]


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

    def __set__(self, instance: Any, value: Any) -> None:
        raise AttributeError("Lazy properties are read-only")


@lru_cache(maxsize=128)
def _compile_expression(expr: str) -> Optional[Callable]:
    """缓存表达式编译结果；编译失败返回 None。"""
    try:
        return safe_lambda(('x',), expr)
    except SafeEvalError:
        return None


def _eval_string_condition(condition: str, data: Any, supp: bool) -> bool:
    """
    将字符串条件对 data 求值，返回 bool。

    优先处理 '->' 前缀；否则尝试编译为 lambda（需要 supp=True）；
    兜底直接做 bool(condition)。
    """
    expr = condition[2:] if condition.startswith('->') else condition
    cond_func = _compile_expression(expr)
    if cond_func is None:
        return bool(condition)
    try:
        return bool(cond_func(data)) if data is not None else False
    except Exception:
        return bool(condition)


class ConditionBuilder:
    """
    条件构建器类。

    用于构建复杂的条件表达式，支持链式调用和多种比较操作符。

    基本用法::

        result = (
            ConditionBuilder(x)
            .case(1, "one")
            .case(2, "two")
            .otherwise("other")
        )()

    注意：
        - :meth:`otherwise` 会锁定链式调用，之后不可继续 :meth:`case`/:meth:`when`。
        - :meth:`__call__` / :meth:`evaluate` 不会修改实例状态，可安全复用。
    """

    # 内部语义标识符
    _BOOL_EQ = staticmethod(lambda x, y: bool(x) == bool(y))

    _OPERATORS: Dict[str, Callable] = {
        '==':     lambda x, y: x == y,
        '!=':     lambda x, y: x != y,
        '>':      lambda x, y: x > y,
        '>=':     lambda x, y: x >= y,
        '<':      lambda x, y: x < y,
        '<=':     lambda x, y: x <= y,
        'in':     lambda x, y: x in y,
        'not in': lambda x, y: x not in y,
        'and':    lambda x, y: x and y,
        'or':     lambda x, y: x or y,
        # 向后兼容别名，均映射到 bool 相等语义
        '?':      lambda x, y: bool(x) == bool(y),
        '_?':     lambda x, y: bool(x) == bool(y),
        'bool':   lambda x, y: bool(x) == bool(y),
    }

    __slots__ = (
        'base', 'supp', '_comp_label', '_comp', '_conditions', '_default',
        '_chain_locked', 'result_type', '_result', '_results',
        '_is_iters', '_cover_default', 'exec_result',
    )

    def __init__(
        self,
        base_value: Any,
        comp: Union[str, Callable] = '==',
        result_type: Optional[type] = None,
        supp: bool = True,
        cover_default: bool = False,
        is_iters: Optional[bool] = None,
        exec_result: bool = True,
        # sht 保留签名兼容性，但已弃用且无效果
        sht: bool = True,
    ) -> None:
        self.base = base_value
        self.supp = supp
        self._comp_label = comp
        self._comp = self._OPERATORS.get(comp if isinstance(comp, str) else '==',
                                         self._OPERATORS['=='])
        if callable(comp):
            self._comp = self._fix_comp(comp)
        self._conditions: List[Tuple[Callable, Any]] = []
        self._default: Any = _UNSET
        self._chain_locked = False
        self.result_type = result_type
        self._result: Any = None
        self._results: List[Any] = []
        self._is_iters = is_iters
        self._cover_default = cover_default
        self.exec_result = exec_result

    # ------------------------------------------------------------------
    # comp 属性
    # ------------------------------------------------------------------

    @property
    def comp(self) -> Callable:
        """当前比较函数（只读）。"""
        return self._comp

    @comp.setter
    def comp(self, comp: Union[str, Callable]) -> None:
        """设置比较函数，支持字符串别名或可调用对象。"""
        if callable(comp):
            self._comp = self._fix_comp(comp)
            return

        if not isinstance(comp, str):
            self._comp = self._OPERATORS['_?']
            return

        # 从内置映射查找
        built_in = self._OPERATORS.get(comp)
        if built_in is not None:
            self._comp = built_in
            return

        # '->' 前缀：强制走 safe_lambda
        if comp.startswith('->'):
            cond_func = _compile_expression(comp[2:])
            if cond_func is None:
                raise ValueError(f"不安全的表达式: {comp}")
            self._comp = self._fix_comp(cond_func)
            return

        # supp 模式：尝试编译任意表达式
        if self.supp:
            cond_func = _compile_expression(comp)
            if cond_func is None:
                raise ValueError(f"不安全的表达式: {comp}")
            self._comp = self._fix_comp(cond_func)
            return

        # 非 supp 模式：只允许内置别名
        label = self._comp_label.__name__ if callable(self._comp_label) else self._comp_label
        if label in ('_?', 'bool'):
            self._comp = self._OPERATORS[label]
            return

        raise ValueError(f"不支持的比较符: {comp!r}（supp=False 时仅接受内置运算符）")

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _fix_comp(self, func: Optional[Callable]) -> Callable:
        """
        规范化比较函数，使其接受单个参数（自动绑定 self.base 作为第二参数）。
        优先使用 try/except 试调用，避免 inspect.signature 在 built-in 上的额外开销。
        """
        if func is None:
            return self._OPERATORS['_?']

        # 先尝试直接以单参数调用
        try:
            func(None)
            return func
        except TypeError as e:
            err_msg = str(e)
            # 若错误提示缺少必要参数，则包装为双参绑定
            if 'argument' in err_msg or 'positional' in err_msg:
                @wraps(func)
                def wrapper(x: Any, _base: Any = self.base) -> Any:
                    return func(x, _base)
                return wrapper
            # 其他 TypeError（如 NoneType 运算）说明函数本身接受单参
            return func
        except Exception:
            # 函数接受单参但执行时抛出其他异常，说明参数数量 OK
            return func

    def _get_condition(self, value: Any) -> Callable:
        """根据 value 创建简单相等比较函数（供 case 使用）。"""
        if callable(value):
            return value
        return lambda x, v=value: self._comp(x, v)

    def _create_condition(self, value: Any) -> Callable:
        """根据 value 创建条件函数（供 when 使用，支持字符串表达式）。"""
        if callable(value):
            return value

        if isinstance(value, str):
            if value.startswith('->'):
                cond_func = _compile_expression(value[2:])
                if cond_func is None:
                    raise ValueError(f"不安全的表达式: {value}")
                return cond_func

            built_in = self._OPERATORS.get(value)
            if built_in is not None:
                return lambda x, v=value, cf=built_in: cf(x, v)

            if self.supp:
                cond_func = _compile_expression(value)
                if cond_func is None:
                    raise ValueError(f"不安全的表达式: {value}")
                return cond_func

            return lambda x, v=value: self._comp(x, v)

        return lambda x, v=value: self._comp(x, v)

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    @property
    def base_value(self) -> Any:
        """获取基础值（只读）。"""
        return self.base

    def case(self, value: Any, result: Any) -> "ConditionBuilder":
        """
        添加相等比较分支。

        Args:
            value: 要比较的值（或可调用条件函数）。
            result: 匹配时返回的结果（或可调用结果函数）。

        Returns:
            self，支持链式调用。
        """
        if self._chain_locked:
            raise RuntimeError("链式调用已被 otherwise() 终止，无法继续添加条件")
        self._conditions.append((self._get_condition(value), result))
        return self

    def cases(self, *cases: Any) -> "ConditionBuilder":
        """
        批量添加相等比较分支。

        支持格式：
        - ``cases([1, "one"], [2, "two"])`` —— 列表对
        - ``cases({"apple": "fruit", "carrot": "vegetable"})`` —— 字典

        Args:
            *cases: 条件-结果对，或一个字典。

        Returns:
            self，支持链式调用。
        """
        if self._chain_locked:
            raise RuntimeError("链式调用已被 otherwise() 终止，无法继续添加条件")

        for item in cases:
            if isinstance(item, dict):
                for k, v in item.items():
                    self._conditions.append((self._get_condition(k), v))
            elif isinstance(item, (list, tuple)):
                if len(item) != 2:
                    raise ValueError(f"case 对需要 2 个元素，但给出了 {len(item)}")
                self._conditions.append((self._get_condition(item[0]), item[1]))
            else:
                raise TypeError(f"不支持的 cases 项类型: {type(item).__name__}")
        return self

    def when(self, value: Any, result: Any, logic: Optional[str] = None) -> "ConditionBuilder":
        """
        添加自定义条件分支（支持短路逻辑）。

        Args:
            value: 条件，可以是 callable、字符串表达式或比较值。
            result: 条件满足时返回的结果。
            logic: 短路逻辑 ``'and'`` 或 ``'or'``（可选）。

        Returns:
            self，支持链式调用。
        """
        if self._chain_locked:
            raise RuntimeError("链式调用已被 otherwise() 终止，无法继续添加条件")
        self._conditions.append((self._create_condition(value), result))
        return self

    def whens(self, *whens: Any) -> "ConditionBuilder":
        """
        批量添加自定义条件分支。

        Args:
            *whens: 每个元素可以是 (condition, result) 二元组，
                    或 (condition, result, logic) 三元组。

        Returns:
            self，支持链式调用。
        """
        if self._chain_locked:
            raise RuntimeError("链式调用已被 otherwise() 终止，无法继续添加条件")

        for item in whens:
            if not isinstance(item, (list, tuple)):
                raise TypeError(f"whens 每项须为 list 或 tuple，实际为 {type(item).__name__}")
            if len(item) == 2:
                cond, res = item
                self._conditions.append((self._create_condition(cond), res))
            elif len(item) == 3:
                cond, res, logic = item
                self._conditions.append((self._create_condition(cond), res))
            else:
                raise ValueError(f"whens 项长度须为 2 或 3，实际为 {len(item)}")
        return self

    def default(self, value: Any) -> "ConditionBuilder":
        """
        设置默认值（未锁链式，别名 :meth:`otherwise`）。

        Args:
            value: 无匹配条件时的默认结果。

        Returns:
            self，支持链式调用。
        """
        self._default = value
        return self

    def otherwise(self, value: Any) -> "ConditionBuilder":
        """
        设置默认值并锁定链式调用。

        调用后不可再添加新的 case/when 条件。

        Args:
            value: 无匹配条件时的默认结果。

        Returns:
            self（链式已锁定）。
        """
        self._default = value
        self._chain_locked = True
        return self

    def evaluate(self, value: Any = _UNSET) -> Any:
        """
        对指定值求值并返回匹配结果。

        Args:
            value: 要评估的值。不传时使用 self.base。

        Returns:
            匹配的结果，若无匹配则返回默认值（若未设置默认值则返回 None）。
        """
        target = self.base if value is _UNSET else value
        return self._execute(target)

    def evaluate_each(self, iterable: Iterable) -> List[Any]:
        """
        对可迭代对象中的每个元素求值，返回结果列表。

        Args:
            iterable: 可迭代对象。

        Returns:
            每个元素的匹配结果组成的列表。
        """
        return [self._execute(item) for item in iterable]

    def evaluateEx(self, iterable: Iterable) -> List[Any]:
        """
        ``evaluate_each`` 的别名。已弃用，请使用 :meth:`evaluate_each`。
        """
        return self.evaluate_each(iterable)

    def __call__(self, value: Any = _UNSET, data: Any = None) -> Any:
        """
        调用实例进行条件求值。

        Args:
            value: 主要求值目标（不传时使用 self.base）。
            data: 传递给可调用结果的额外数据。

        Returns:
            匹配结果。
        """
        target = self.base if value is _UNSET else value
        return self._execute(target)

    def _execute(self, target: Any) -> Any:
        """执行条件匹配求值。"""
        if self._is_iters:
            return self._execute_iterable(target)

        result = self._execute_single(target)
        return result

    def _execute_single(self, target: Any) -> Any:
        """单个值求值。"""
        for cond, result in self._conditions:
            try:
                if cond(target):
                    if callable(result):
                        return result(target)
                    if self.exec_result and callable(result):
                        return result(target)
                    return result
            except (TypeError, ValueError):
                continue

        if self._default is not _UNSET:
            if callable(self._default):
                return self._default(target)
            return self._default

        if self._cover_default and self._conditions:
            last_result = self._conditions[-1][1]
            if callable(last_result):
                return last_result(target)
            return last_result

        return None

    def _execute_iterable(self, target: Iterable) -> List[Any]:
        """可迭代对象求值（为每个元素独立匹配）。"""
        results = []
        for item in target:
            results.append(self._execute_single(item))
        return results

    def __or__(self, other: "ConditionBuilder") -> "ConditionBuilder":
        """
        合并两个 ConditionBuilder 的条件（逻辑或语义）。

        新 builder 的 base 采用 self.base。
        条件顺序：self 的条件在前，other 的条件在后。
        若两个 builder 的 base 不一致，以 self.base 为准。

        Args:
            other: 另一个 ConditionBuilder 实例。

        Returns:
            新的 ConditionBuilder 实例。
        """
        new_cb = ConditionBuilder(self.base, comp=self._comp, supp=self.supp)
        new_cb._conditions = self._conditions + other._conditions
        new_cb._default = self._default if self._default is not _UNSET else other._default
        return new_cb

    def __and__(self, other: "ConditionBuilder") -> "ConditionBuilder":
        """
        合并两个 ConditionBuilder 的条件（逻辑与语义）。

        要求两个 builder 的条件数一致，对应位置的条件需**同时满足**。
        新 builder 的 base 采用 self.base。

        Args:
            other: 另一个 ConditionBuilder 实例。

        Returns:
            新的 ConditionBuilder 实例。

        Raises:
            ValueError: 两个 builder 的条件数不一致时抛出。
        """
        if len(self._conditions) != len(other._conditions):
            raise ValueError(
                f"__and__ 要求两个 ConditionBuilder 条件数一致："
                f"self={len(self._conditions)}, other={len(other._conditions)}"
            )
        new_cb = ConditionBuilder(self.base, comp=self._comp, supp=self.supp)
        new_conditions = []
        for (c1, r1), (c2, r2) in zip(self._conditions, other._conditions):
            def combined_cond(x, _c1=c1, _c2=c2):
                return _c1(x) and _c2(x)
            combined_cond.__name__ = f"({c1.__name__} & {c2.__name__})" if hasattr(c1, '__name__') else "combined"
            new_conditions.append((combined_cond, r1))
        new_cb._conditions = new_conditions
        new_cb._default = self._default if self._default is not _UNSET else other._default
        return new_cb

    def clear(self) -> "ConditionBuilder":
        """
        清空所有条件、默认值和锁定状态，保留 base 和 comp。

        Returns:
            self。
        """
        self._conditions.clear()
        self._default = _UNSET
        self._chain_locked = False
        self._result = None
        self._results.clear()
        return self

    def __repr__(self) -> str:
        return (
            f"ConditionBuilder(base={self.base!r}, "
            f"conditions={len(self._conditions)}, "
            f"has_default={self._default is not _UNSET})"
        )


# =============================================================================
# iif 函数
# =============================================================================

def iif(
    condition: Any = None,
    true_body: Any = None,
    false_body: Any = None,
    data: Any = None,
    supp: bool = True,
    whens: Optional[List[Tuple]] = None,
) -> Any:
    """
    条件表达式函数。

    根据条件返回不同的值，支持函数式编程风格。

    Args:
        condition: 条件表达式，可以是布尔值、字符串或可调用对象。
            - 布尔/数值：直接做真值判断。
            - 字符串：
                - ``'->'`` 前缀：强制用 safe_lambda 编译，例如 ``'-> x > 3'``。
                - 普通字符串（supp=True）：尝试编译为 lambda，失败则 fallback 到 bool(condition)。
            - callable：以 ``data`` 为参数调用（data 为 None 时无参调用）。
        true_body: 条件为真时返回的值或函数（以 data 为参数调用）。
        false_body: 条件为假时返回的值或函数（可选）。
        data: 传递给 condition/true_body/false_body 的数据。
        supp: 是否启用字符串表达式编译（默认 True）。
        whens: 条件列表，格式 ``[(condition, result), ...]``
               或 ``[(condition, result, logic), ...]``。
               当提供 whens 时，condition 仅用于初始化 ConditionBuilder 的比较器，
               真正的求值目标为 data。

    Returns:
        根据条件评估结果返回相应的值；
        若 condition 和 true_body 均为 None，则返回空 ConditionBuilder 实例。

    Examples::

        # 基本用法
        iif(True, "yes", "no")                  # -> "yes"
        iif(x > 5, lambda: do_a(), lambda: do_b())

        # 字符串表达式（supp 模式）
        iif("-> x > 3", "big", "small", data=x)

        # 链式构建器
        iif().case(1, "one").case(2, "two").otherwise("other")

        # whens 批量条件
        iif(data=x, whens=[(lambda v: v > 10, "big"), (lambda v: v <= 10, "small")])
    """
    # 无参数：返回空 ConditionBuilder，供链式调用
    if condition is None and true_body is None and whens is None:
        return ConditionBuilder(None)

    # whens 模式：构建 ConditionBuilder 并对 data 求值
    if whens is not None:
        cb = ConditionBuilder(data, supp=supp)
        for w in whens:
            if not isinstance(w, (list, tuple)):
                raise TypeError(f"whens 中每项须为 list 或 tuple，实际为 {type(w).__name__}")
            if len(w) == 2:
                cb.when(w[0], w[1])
            elif len(w) == 3:
                cb.when(w[0], w[1], w[2])
            else:
                raise ValueError(f"whens 项长度须为 2 或 3，实际为 {len(w)}")
        return cb(data)

    # 简单模式（无 data）：直接对 condition 做真值判断
    if data is None:
        if callable(condition):
            condition_result = condition()
        else:
            condition_result = bool(condition) if condition is not None else False
        base = true_body if condition_result else false_body
        return base() if callable(base) else base

    # data 模式：对 data 求值 condition，再选择 true_body/false_body
    if callable(condition):
        cond_result = condition(data)
    elif isinstance(condition, str):
        cond_result = _eval_string_condition(condition, data, supp)
    else:
        cond_result = bool(condition) if condition is not None else False

    result = true_body if cond_result else (false_body if false_body is not None else None)

    if callable(result):
        return result(data)
    return result
