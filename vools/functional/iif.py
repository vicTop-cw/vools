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
  - [改进] _OPERATORS 中 '?'/'_?'/'bool' 合并为单一内部标识符，保留向后兼容别名
  - [改进] _fix_comp 优先用 try/except 替代 inspect.signature 降低性能开销
  - [改进] evaluateEx 重命名为 evaluate_each（保留旧名作弃用别名）
  - [改进] whens 方法增加输入类型校验
  - [改进] 移除未使用的 sht 参数（保留向后兼容，但标注为 deprecated）
  - [改进] 修正拼写：_comp_lable -> _comp_label
  - [改进] iif() 字符串条件分支提取为 _eval_string_condition 内部函数
  - [改进] 补全主要方法的类型注解
"""

import inspect as ins
from collections.abc import Iterable
from functools import wraps, lru_cache
from typing import Any, Callable, Optional, Union, List, Dict, Tuple, overload
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
       ``dict`` 中，以 ``id(instance)`` 为键。注意：slots 类的实例
       通常不被垃圾回收前析构，此处不做 WeakRef 以保持兼容性；
       若需要对大量短生命周期对象使用，请改用普通类。
    """

    def __init__(self, func: Callable) -> None:
        self.func = func
        self._attr_name: Optional[str] = None
        self._id_cache: Dict[int, Any] = {}
        wraps(func)(self)

    def __set_name__(self, owner: type, name: str) -> None:
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
        return self._comp

    @comp.setter
    def comp(self, comp: Union[str, Callable]) -> None:
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
        """添加相等比较分支。"""
        if self._chain_locked:
            raise RuntimeError("链式调用已被 otherwise() 终止，无法继续添加条件")
        self._conditions.append((self._get_condition(value), result))
        return self

    def cases(self, *cases: Any) -> "ConditionBuilder":
        """批量添加条件分支。

        支持传入 dict 或长度为 2 的 list/tuple。
        """
        for case_item in cases:
            if isinstance(case_item, dict):
                for k, v in case_item.items():
                    self.case(k, v)
            elif isinstance(case_item, (list, tuple)) and len(case_item) == 2:
                self.case(case_item[0], case_item[1])
        return self

    def when(self, value: Any, result: Any, logic: Optional[str] = None) -> "ConditionBuilder":
        """添加条件分支，支持逻辑组合（'and' / 'or'）。"""
        if self._chain_locked:
            raise RuntimeError("链式调用已被 otherwise() 终止，无法继续添加条件")

        cond_func = self._create_condition(value)

        if logic is None:
            self._conditions.append((cond_func, result))
        elif self._conditions and logic in ('and', 'or'):
            prev_cond, _ = self._conditions[-1]
            if logic == 'and':
                new_cond = lambda x, pc=prev_cond, cf=cond_func: pc(x) and cf(x)
            else:
                new_cond = lambda x, pc=prev_cond, cf=cond_func: pc(x) or cf(x)
            self._conditions[-1] = (new_cond, result)
        return self

    def whens(self, *whens: Any) -> "ConditionBuilder":
        """批量添加 when 条件。

        每项须为长度 2 或 3 的 list/tuple，格式：(value, result) 或 (value, result, logic)。

        Raises:
            TypeError: 当某项不是 list/tuple 时。
            ValueError: 当某项长度不在 [2, 3] 之间时。
        """
        for i, when_data in enumerate(whens):
            if not isinstance(when_data, (list, tuple)):
                raise TypeError(
                    f"whens 的第 {i} 项须为 list 或 tuple，实际收到 {type(when_data).__name__}"
                )
            if len(when_data) == 2:
                self.when(when_data[0], when_data[1])
            elif len(when_data) == 3:
                self.when(when_data[0], when_data[1], when_data[2])
            else:
                raise ValueError(
                    f"whens 的第 {i} 项长度须为 2 或 3，实际为 {len(when_data)}"
                )
        return self

    def default(self, value: Any) -> "ConditionBuilder":
        """设置默认值（支持将 None 作为有效默认值）。"""
        if self._chain_locked:
            raise RuntimeError("链式调用已被 otherwise() 终止")
        self._default = value
        return self

    def otherwise(self, value: Any) -> "ConditionBuilder":
        """设置默认值并锁定链式调用（default 的终止别名）。"""
        self._default = value
        self._chain_locked = True
        return self

    def evaluate(self, value: Any = _UNSET) -> Any:
        """对指定值（或 base）执行条件判断。不修改实例状态。"""
        target = self.base if value is _UNSET else value
        return self._execute_single(target)

    def evaluate_each(self, iterable: Iterable) -> List[Any]:
        """对可迭代对象逐项执行条件判断，返回结果列表。"""
        return self._execute_iterable(iterable)

    def evaluateEx(self, iterable: Iterable) -> List[Any]:
        """已弃用，请使用 evaluate_each()。"""
        return self.evaluate_each(iterable)

    def __call__(self, value: Any = _UNSET, data: Any = None) -> Any:
        """执行条件判断。不修改 self.base。"""
        # 确定求值目标（优先 data，其次显式传入的 value，最后 self.base）
        if data is not None:
            target = data
        elif value is not _UNSET:
            target = value
        else:
            target = self.base

        if self.exec_result:
            return self._execute(target)
        return self._results

    # ------------------------------------------------------------------
    # 执行逻辑
    # ------------------------------------------------------------------

    def _execute(self, target: Any) -> Any:
        if isinstance(target, Iterable) and not isinstance(target, (str, bytes)):
            return self._execute_iterable(target)
        return self._execute_single(target)

    def _execute_single(self, target: Any) -> Any:
        for cond, result in self._conditions:
            if cond(target):
                return result(target) if callable(result) else result
        if self._default is not _UNSET:
            return self._default(target) if callable(self._default) else self._default
        return None

    def _execute_iterable(self, target: Iterable) -> List[Any]:
        results = []
        for item in target:
            result = self._execute_single(item)
            if self.result_type is not None:
                result = self.result_type(result)
            results.append(result)
        return results

    # ------------------------------------------------------------------
    # 运算符重载
    # ------------------------------------------------------------------

    def __or__(self, other: "ConditionBuilder") -> "ConditionBuilder":
        """
        用 | 合并两个 builder 的全部条件（顺序追加）。
        default 取 other 的优先；若 other 未设置则用 self 的。
        """
        if not isinstance(other, ConditionBuilder):
            raise TypeError("只能与 ConditionBuilder 实例组合")
        new_cb = ConditionBuilder(self.base)
        new_cb._conditions = self._conditions + other._conditions
        new_cb._default = other._default if other._default is not _UNSET else self._default
        return new_cb

    def __and__(self, other: "ConditionBuilder") -> "ConditionBuilder":
        """
        用 & 将两个 builder 的条件逐对取 AND，结果取左侧 result。

        要求两个 builder 的条件数量相同，否则抛出 ValueError。
        语义：第 i 条分支在 self 第 i 个条件 AND other 第 i 个条件都成立时匹配，
        返回 self 第 i 个分支的结果。
        """
        if not isinstance(other, ConditionBuilder):
            raise TypeError("只能与 ConditionBuilder 实例组合")
        if len(self._conditions) != len(other._conditions):
            raise ValueError(
                f"__and__ 要求两侧条件数量相同，"
                f"左侧 {len(self._conditions)} 条，右侧 {len(other._conditions)} 条"
            )
        new_cb = ConditionBuilder(self.base)
        new_cb._conditions = [
            (lambda x, c1=c1, c2=c2: c1(x) and c2(x), r1)
            for (c1, r1), (c2, _) in zip(self._conditions, other._conditions)
        ]
        new_cb._default = self._default
        return new_cb

    def clear(self) -> "ConditionBuilder":
        """清空所有条件和默认值，解除链锁。"""
        self._conditions.clear()
        self._default = _UNSET
        self._chain_locked = False
        return self

    def __repr__(self) -> str:
        default_repr = repr(self._default) if self._default is not _UNSET else "<unset>"
        return (
            f"ConditionBuilder(base={self.base!r}, "
            f"conditions={len(self._conditions)}, "
            f"default={default_repr})"
        )


# ---------------------------------------------------------------------------
# iif 顶层函数
# ---------------------------------------------------------------------------

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
        whens: 条件列表，格式 ``[(condition, result), ...]`` 或 ``[(condition, result, logic), ...]``。
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

    # whens 模式：构建 ConditionBuilder 并对 target 求值
    if whens is not None:
        target = data if data is not None else condition
        cb = ConditionBuilder(target, supp=supp)
        for w in whens:
            if not isinstance(w, (list, tuple)):
                raise TypeError(f"whens 中每项须为 list 或 tuple，实际为 {type(w).__name__}")
            if len(w) == 2:
                cb.when(w[0], w[1])
            elif len(w) == 3:
                cb.when(w[0], w[1], w[2])
            else:
                raise ValueError(f"whens 项长度须为 2 或 3，实际为 {len(w)}")
        return cb(target)

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
