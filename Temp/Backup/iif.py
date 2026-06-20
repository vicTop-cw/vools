"""
条件判断工具模块

提供 iif 函数和 ConditionBuilder 类，用于灵活的条件判断和分支处理。
优化包括：
- 使用 __slots__ 减少内存开销
- 缓存 safe_lambda 编译结果
- 减少重复的 isinstance 检查
"""

import inspect as ins
from collections.abc import Iterable
from functools import wraps, lru_cache
from typing import Any, Callable, Optional, Union, List, Dict, Tuple
from ..security.safe_eval import safe_lambda, SafeEvalError

__all__ = ["LazyProperty", "ConditionBuilder", "iif"]


class LazyProperty:
    """延迟属性装饰器"""
    __slots__ = ('func', '_name')
    
    def __init__(self, func):
        self.func = func
        self._name = f"_lazy_{func.__name__}"

    def __get__(self, instance, cls):
        if instance is None:
            return self
        if hasattr(instance, self._name):
            return getattr(instance, self._name)
        value = self.func(instance)
        setattr(instance, self._name, value)
        return value

    def __set__(self, instance, value):
        raise AttributeError("Lazy properties are read-only")


@lru_cache(maxsize=128)
def _compile_expression(expr: str) -> Callable:
    """缓存表达式编译结果"""
    try:
        return safe_lambda(('x',), expr)
    except SafeEvalError:
        return None


class ConditionBuilder:
    """
    条件构建器类

    用于构建复杂的条件表达式，支持链式调用和多种比较操作符。
    """

    _OPERATORS = {
        '==': lambda x, y: x == y,
        '!=': lambda x, y: x != y,
        '>': lambda x, y: x > y,
        '>=': lambda x, y: x >= y,
        '<': lambda x, y: x < y,
        '<=': lambda x, y: x <= y,
        'in': lambda x, y: x in y,
        'not in': lambda x, y: x not in y,
        'and': lambda x, y: x and y,
        'or': lambda x, y: x or y,
        '?': lambda x, y: bool(x) == bool(y),
        '_?': lambda x, y: bool(x) == bool(y),
        'bool': lambda x, y: bool(x) == bool(y),
    }
    
    __slots__ = (
        'base', 'supp', '_comp_lable', '_comp', '_conditions', '_default',
        '_chain_locked', 'result_type', 'sht', '_result', '_results',
        '_is_iters', '_cover_default', 'exec_result'
    )

    def __init__(self, base_value, comp='==', sht=True, result_type=None, supp=True, cover_default=False, is_iters=None, exec_result=True):
        self.base = base_value
        self.supp = supp
        self._comp_lable = comp
        self._comp = self._OPERATORS.get(comp, self._OPERATORS['=='])
        self._conditions = []
        self._default = None
        self._chain_locked = False
        self.result_type = result_type
        self.sht = sht
        self._result = None
        self._results = []
        self._is_iters = is_iters
        self._cover_default = cover_default
        self.exec_result = exec_result

    @property
    def comp(self):
        return self._comp

    @comp.setter
    def comp(self, comp):
        if callable(comp):
            self._comp = self._fix_comp(comp)
        elif isinstance(comp, str):
            self._comp = self._OPERATORS.get(comp, None)
            if self._comp is None:
                if comp.startswith('->'):
                    cond_func = _compile_expression(comp[2:])
                    if cond_func is None:
                        raise ValueError(f"不安全的表达式: {comp}")
                elif self.supp:
                    cond_func = _compile_expression(comp)
                    if cond_func is None:
                        raise ValueError(f"不安全的表达式: {comp}")
                else:
                    nm = self._comp_lable.__name__ if callable(self._comp_lable) else self._comp_lable
                    if nm in ("_?", "bool"):
                        cond_func = self._OPERATORS[nm]
                    else:
                        raise ValueError("不支持的比较符")
                self._comp = self._fix_comp(cond_func)
        else:
            self._comp = self._OPERATORS["_?"]

    def _fix_comp(self, func):
        """修复比较函数，确保它接受一个参数"""
        if func is None:
            return self._OPERATORS["_?"]

        try:
            sig = ins.signature(func)
            param_count = len(sig.parameters)
            if param_count == 1:
                return func
            elif param_count > 1:
                @wraps(func)
                def wrapper(x):
                    return func(x, self.base)
                return wrapper
            else:
                return self._OPERATORS["_?"]
        except (ValueError, TypeError):
            return self._OPERATORS["_?"]

    @property
    def base_value(self):
        """获取基础值"""
        return self.base

    def case(self, value, result):
        """添加条件分支"""
        if self._chain_locked:
            raise RuntimeError("链式调用已终止")
        cond = self._get_condition(value)
        self._conditions.append((cond, result))
        return self

    def cases(self, *cases):
        """批量添加条件分支"""
        for case_item in cases:
            if isinstance(case_item, dict):
                for k, v in case_item.items():
                    self.case(k, v)
            elif isinstance(case_item, (list, tuple)) and len(case_item) == 2:
                cond, result = case_item
                self.case(cond, result)
        return self

    def when(self, value, result, logic=None):
        """添加比较值，支持逻辑组合"""
        if self._chain_locked:
            raise RuntimeError("链式调用已终止")
        
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

    def _create_condition(self, value):
        """创建条件函数"""
        if callable(value):
            return value
        elif isinstance(value, str):
            if value.startswith('->'):
                cond_func = _compile_expression(value[2:])
                if cond_func is None:
                    raise ValueError(f"不安全的表达式: {value}")
                return cond_func
            else:
                cond_func = self._OPERATORS.get(value)
                if cond_func is None:
                    if self.supp:
                        cond_func = _compile_expression(value)
                        if cond_func is None:
                            raise ValueError(f"不安全的表达式: {value}")
                        return cond_func
                    else:
                        return lambda x, v=value: self._comp(x, v)
                else:
                    return lambda x, v=value, cf=cond_func: cf(x, v)
        else:
            return lambda x, v=value: self._comp(x, v)

    def whens(self, *whens):
        """批量添加条件"""
        for when_data in whens:
            if len(when_data) == 2:
                value, result = when_data
                self.when(value, result)
            elif len(when_data) == 3:
                value, result, logic = when_data
                self.when(value, result, logic)
        return self

    def default(self, value):
        """设置默认值"""
        if self._chain_locked:
            raise RuntimeError("链式调用已终止")
        self._default = value
        return self

    def otherwise(self, value):
        """设置默认值（default 的别名）"""
        result = self.default(value)
        self._chain_locked = True  # 设置默认值后锁定链式调用
        return result

    def evaluate(self, value=None):
        """执行条件判断（接受一个值）"""
        if value is not None:
            return self._execute_single(value)
        return self._execute_single(self.base)

    def evaluateEx(self, iterable):
        """批量执行条件判断"""
        return self._execute_iterable(iterable)

    def _get_condition(self, value):
        """获取条件判断函数"""
        if callable(value):
            return value
        return lambda x: self._comp(x, value)

    def __call__(self, value=None, data=None):
        """执行条件判断"""
        if value is not None:
            self.base = value

        target = data if data is not None else self.base

        if self.exec_result:
            return self._execute(target)
        return self._results

    def _execute(self, target):
        """执行条件判断并返回结果"""
        if isinstance(target, Iterable) and not isinstance(target, str):
            return self._execute_iterable(target)
        return self._execute_single(target)

    def _execute_single(self, target):
        """执行单个值的条件判断"""
        for cond, result in self._conditions:
            if cond(target):
                if callable(result):
                    return result(target)
                return result
        if self._default is not None:
            if callable(self._default):
                return self._default(target)
            return self._default
        return None

    def _execute_iterable(self, target):
        """执行可迭代对象的条件判断"""
        results = []
        for item in target:
            result = self._execute_single(item)
            if self.result_type is not None:
                result = self.result_type(result)
            results.append(result)
        return results

    def __repr__(self):
        return f"ConditionBuilder(base={self.base!r}, conditions={len(self._conditions)})"

    def __or__(self, other):
        """支持 | 操作符组合条件"""
        if not isinstance(other, ConditionBuilder):
            raise TypeError("只能与 ConditionBuilder 组合")
        new_cb = ConditionBuilder(self.base)
        new_cb._conditions = self._conditions + other._conditions
        new_cb._default = other._default if other._default is not None else self._default
        return new_cb

    def __and__(self, other):
        """支持 & 操作符组合条件"""
        if not isinstance(other, ConditionBuilder):
            raise TypeError("只能与 ConditionBuilder 组合")
        new_cb = ConditionBuilder(self.base)
        new_cb._conditions = [
            (lambda x, c1=c1, c2=c2: c1(x) and c2(x), r1)
            for (c1, r1), (c2, r2) in zip(self._conditions, other._conditions)
        ]
        new_cb._default = self._default
        return new_cb

    def clear(self):
        """清空所有条件"""
        self._conditions.clear()
        self._default = None
        self._chain_locked = False
        return self


def iif(condition=None, true_body=None, false_body=None, data=None, supp=True, whens=None):
    """
    条件表达式函数

    根据条件返回不同的值，支持函数式编程风格。

    Args:
        condition: 条件表达式，可以是布尔值、字符串或可调用对象
        true_body: 条件为真时返回的值或函数
        false_body: 条件为假时返回的值或函数（可选）
        data: 要评估的数据（可选）
        supp: 是否启用补充运算符（默认True）
        whens: 条件列表 [(condition, result), ...]

    Returns:
        根据条件评估结果返回相应的值
    """
    if condition is None and true_body is None:
        return ConditionBuilder(None)

    if data is None and whens is None:
        if callable(condition):
            condition_result = condition()
        else:
            condition_result = condition
        base = true_body if condition_result else false_body
        return base() if callable(base) else base

    if callable(condition):
        cond_result = condition(data) if data is not None else condition()
    elif isinstance(condition, str):
        if condition.startswith('->'):
            expr = condition[2:]
            cond_func = _compile_expression(expr)
            if cond_func is None:
                cond_result = bool(condition)
            else:
                try:
                    cond_result = cond_func(data) if data is not None else False
                except Exception:
                    cond_result = bool(condition)
        elif condition in ('and', 'or', 'not'):
            cond_func = _compile_expression(condition)
            if cond_func is None:
                cond_result = bool(condition)
            else:
                try:
                    cond_result = cond_func(data) if data is not None else False
                except Exception:
                    cond_result = bool(condition)
        else:
            cond_func = _compile_expression(condition)
            if cond_func is None:
                cond_result = bool(condition)
            else:
                try:
                    cond_result = cond_func(data) if data is not None else False
                except Exception:
                    cond_result = bool(condition)
    else:
        cond_result = bool(condition) if condition is not None else False

    if cond_result:
        result = true_body
    else:
        result = false_body if false_body is not None else None

    if whens is not None:
        cb = ConditionBuilder(condition, supp=supp)
        for w in whens:
            if len(w) == 2:
                cb.when(w[0], w[1])
            elif len(w) == 3:
                cb.when(w[0], w[1], w[2])
        return cb(condition)

    if callable(result):
        return result(data) if data is not None else result()
    return result