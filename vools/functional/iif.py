"""
条件判断工具模块

提供 iif 函数和 ConditionBuilder 类，用于灵活的条件判断和分支处理。
"""

import inspect as ins
from collections.abc import Iterable
from functools import wraps
from typing import Any, Callable, Optional, Union, List, Dict
from ..security.safe_eval import safe_lambda, SafeEvalError

__all__ = ["LazyProperty", "ConditionBuilder", "iif"]


class LazyProperty:
    """延迟属性装饰器"""
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
                    try:
                        comp = safe_lambda(('x',), comp[2:])
                    except SafeEvalError:
                        raise ValueError(f"不安全的表达式: {comp}")
                elif self.supp:
                    try:
                        comp = safe_lambda(('x',), comp)
                    except SafeEvalError:
                        raise ValueError(f"不安全的表达式: {comp}")
                else:
                    nm = self._comp_lable.__name__ if callable(self._comp_lable) else self._comp_lable
                    if nm in ("_?", "bool"):
                        comp = self._OPERATORS[nm]
                    else:
                        raise ValueError("不支持的比较符")

                self._comp = self._fix_comp(comp)
        else:
            self._comp = self._OPERATORS["_?"]

    def _fix_comp(self, func):
        """修复比较函数，确保它接受一个参数"""
        if func is None:
            return self._OPERATORS["_?"]

        try:
            sig = ins.signature(func)
            if len(sig.parameters) == 1:
                return func
            elif len(sig.parameters) > 1:
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
        if callable(value):
            cond_func = value
        elif isinstance(value, str):
            if value.startswith('->'):
                try:
                    cond_func = safe_lambda(('x',), value[2:])
                except SafeEvalError:
                    raise ValueError(f"不安全的表达式: {value}")
            else:
                cond_func = self._OPERATORS.get(value, None)
                if cond_func is None:
                    if self.supp:
                        try:
                            cond_func = safe_lambda(('x',), value)
                        except SafeEvalError:
                            raise ValueError(f"不安全的表达式: {value}")
                    else:
                        cond_func = lambda x: self.comp(x, value)
                else:
                    cond_func = lambda x: cond_func(x, value)
        else:
            cond_func = lambda x: self.comp(x, value)

        if logic is None:
            self._conditions.append((cond_func, result))
        elif self._conditions and logic in ('and', 'or'):
            prev_cond, prev_res = self._conditions[-1]
            new_cond = (
                lambda x: prev_cond(x) and cond_func(x) if logic == 'and'
                else lambda x: prev_cond(x) or cond_func(x)
            )
            self._conditions[-1] = (new_cond, result)
        return self

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
        self._default = value
        return self

    def otherwise(self, value):
        """设置默认值（default的别名），并锁定链式调用"""
        self._default = value
        self._chain_locked = True
        return self

    def _get_condition(self, value):
        """获取条件函数"""
        if callable(value):
            return value
        elif isinstance(value, str):
            if value.startswith('->'):
                try:
                    return safe_lambda(('x',), value[2:])
                except SafeEvalError:
                    raise ValueError(f"不安全的表达式: {value}")
            elif self.supp and value in self._OPERATORS:
                return self._OPERATORS[value]
            else:
                try:
                    return safe_lambda(('x',), value)
                except SafeEvalError:
                    return lambda x: self.comp(x, value)
        else:
            return lambda x: self.comp(x, value)

    def _execute_result(self, result):
        """执行结果"""
        if self.exec_result and callable(result):
            return result(self.base)
        return result

    def _transform_result(self, result):
        """根据 result_type 转换结果"""
        if self.result_type is None:
            return self._execute_result(result)
        try:
            if self.result_type == 'int':
                return int(self._execute_result(result))
            elif self.result_type == 'float':
                return float(self._execute_result(result))
            elif self.result_type == 'str':
                return str(self._execute_result(result))
            elif self.result_type == 'bool':
                return bool(self._execute_result(result))
            else:
                return self.result_type(self._execute_result(result))
        except (ValueError, TypeError):
            return self._execute_result(result)

    def evaluate(self, data, cover_default=None):
        """评估条件并返回结果"""
        for cond, result in self._conditions:
            try:
                if callable(cond):
                    cond_result = cond(data)
                else:
                    cond_result = bool(cond)

                if cond_result:
                    return self._transform_result(result)
            except Exception:
                continue

        if cover_default is not None:
            return cover_default
        if self._default is not None:
            return self._execute_result(self._default)
        return None

    def evaluateEx(self, datas):
        """批量评估条件"""
        return [self.evaluate(i) for i in datas]

    def __call__(self, data=None, cover_default=None):
        """使 ConditionBuilder 可调用"""
        if data is None:
            data = self.base
        return self.evaluate(data, cover_default)

    def __iter__(self):
        """使对象可迭代"""
        return iter(self._conditions)

    def __len__(self):
        """返回条件数量"""
        return len(self._conditions)

    def lock(self):
        """锁定链式调用"""
        self._chain_locked = True
        return self

    def unlock(self):
        """解锁链式调用"""
        self._chain_locked = False
        return self

    def clear(self):
        """清空所有条件"""
        self._conditions = []
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

    Examples:
        >>> iif(True, 1, 0)
        1
        >>> iif(False, 1, 0)
        0
        >>> iif("x > 5", lambda: 1, lambda: 0, data={'x': 10})
        1
    """
    if condition is None and true_body is None:
        return ConditionBuilder(None)

    if data is None and whens is None:
        if callable(condition):
            condition_result = condition()
        else:
            condition_result = condition
        base = true_body if condition_result else false_body
        if callable(base):
            base = base()
        return base

    if callable(condition):
        cond_result = condition(data) if data is not None else condition()
    elif isinstance(condition, str):
        if condition.startswith('->'):
            try:
                cond_func = safe_lambda(('x',), condition[2:])
                cond_result = cond_func(data) if data is not None else False
            except SafeEvalError:
                cond_result = bool(condition)
        elif condition in ('and', 'or', 'not'):
            try:
                cond_result = safe_lambda(('x',), condition)(data) if data is not None else False
            except (SafeEvalError, Exception):
                cond_result = bool(condition)
        else:
            try:
                cond_func = safe_lambda(('x',), condition)
                cond_result = cond_func(data) if data is not None else False
            except (SafeEvalError, Exception):
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
                w_cond, w_result = w
                cb.when(w_cond, w_result)
            elif len(w) == 3:
                w_cond, w_result, _ = w
                cb.when(w_cond, w_result)
        return cb(condition)

    if callable(result):
        return result(data) if data is not None else result()
    return result