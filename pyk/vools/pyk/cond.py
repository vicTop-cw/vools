# -*- coding: utf-8 -*-
"""ConditionBuilder —— legacy vools.py 的条件构建器 (py3.6 兼容)。

legacy 文件位置: pyk/_dec7z/vools.py  L6005-6275
功能: 用链式 when/case/otherwise 构造条件判断, 类似 pandas.Series.map 或
      numpy.select, 支持短路 / 补充运算符 / 结果类型校验 / 批量求值。
"""

import inspect as ins
from collections.abc import Iterable

__all__ = ["ConditionBuilder", "sig", "iif"]


class ConditionBuilder:
    _OPERATORS = {
        "=": lambda a, b: a == b,
        "_?": lambda _, b: bool(b),
        "?_": lambda a, _: bool(a),
        "==": lambda a, b: a == b,
        "===": lambda a, b: a is b and a == b,
        ">": lambda a, b: a > b,
        "<": lambda a, b: a < b,
        ">=": lambda a, b: a >= b,
        "<=": lambda a, b: a <= b,
        "!=": lambda a, b: a != b,
        "is": lambda a, b: a is b,
        "is not": lambda a, b: a is not b,
        "and": lambda a, b: a and b,
        "or": lambda a, b: a or b,
        "xor": lambda a, b: a ^ b,
        "^": lambda a, b: a ^ b,
        "in": lambda a, b: a in b,
        "not in": lambda a, b: a not in b,
    }

    # ---- 构造 ----
    def __init__(self, base_value, comp='==', sht=True, result_type=None, supp=False,
                 cover_default=False, is_iters=None, exec_result=True):
        self.base = base_value
        self.supp = supp
        self._comp_lable = comp
        self.comp = comp
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

    # ---- 属性 ----
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
                    comp = eval("lambda x: " + comp[2:], globals(), locals())
                elif self.supp:
                    comp = eval("lambda x: " + comp, globals(), locals())
                else:
                    nm = self._comp_lable.__name__ if callable(self._comp_lable) else self._comp_lable
                    if nm in ("_?", "bool"):
                        comp = self._OPERATORS[nm]
                    else:
                        raise ValueError("不支持的比较符")
                self._comp = self._fix_comp(comp)
        else:
            self._comp = self._OPERATORS["_?"]

    @staticmethod
    def _fix_comp(comp):
        if comp is bool:
            comp = lambda _, b: bool(b)  # noqa: E731
        else:
            ps = ins.signature(comp).parameters
            l = len(ps)
            if l >= 2:
                pass
            elif l == 1:
                comp = lambda _, b: bool(comp(b))  # noqa: E731
            elif l == 0:
                comp = lambda _, b: bool(comp())  # noqa: E731
        return comp

    @property
    def is_iters(self):
        return self._is_iters

    @property
    def cover_default(self):
        return self._cover_default

    @property
    def conds(self):
        return self._conditions

    @property
    def result(self):
        return self._result

    @property
    def results(self):
        return self._results

    # ---- 链式构建 ----
    def case(self, value, result, comp=None):
        if self._chain_locked:
            raise RuntimeError("链式调用已终止")
        if comp is None:
            self._conditions.append((lambda x: self.comp(x, value), result))
        elif isinstance(comp, str):
            comp = self._OPERATORS.get(comp, None)
            if comp is None:
                raise ValueError("不支持的比较符")
            self._conditions.append((lambda x: comp(x, value), result))
        elif callable(comp):
            self._conditions.append((lambda x: comp(x, value), result))
        else:
            raise ValueError("不支持的比较符")
        return self

    def cases(self, *args):
        """批量添加 case: (value, result) / (value, result, comp) / dict / str 列表"""
        if len(args) == 0:
            return self
        if all(isinstance(i, str) for i in args):
            for i in args:
                self.case(i, i)
            return self
        if all(isinstance(i, dict) for i in args):
            for i in args:
                for k, v in i.items():
                    self.case(k, v)
            return self
        if all(isinstance(i, Iterable) for i in args):
            for i in args:
                l = len(i)
                if l == 1:
                    self.case(i[0], i[0])
                elif l in (2, 3):
                    self.case(*i)
            return self
        for i in args:
            self.case(i, i)
        return self

    def when(self, value, result, logic=None):
        """添加条件, 支持 and/or 逻辑组合"""
        if self._chain_locked:
            raise RuntimeError("链式调用已终止")
        if callable(value):
            cond_func = value
        elif isinstance(value, str):
            if value.startswith('->'):
                cond_func = eval("lambda x: " + value[2:], globals(), locals())
            else:
                cond_func = self._OPERATORS.get(value, None)
                if cond_func is None:
                    if self.supp:
                        cond_func = eval("lambda x: " + value, globals(), locals())
                    else:
                        cond_func = lambda x: self.comp(x, value)  # noqa: E731
                else:
                    cond_func = lambda x: cond_func(x, value)  # noqa: E731
        else:
            cond_func = lambda x: self.comp(x, value)  # noqa: E731

        if logic is None:
            self._conditions.append((cond_func, result))
        elif self._conditions and logic in ('and', 'or'):
            prev_cond, prev_res = self._conditions[-1]
            new_cond = (
                lambda x: prev_cond(x) and cond_func(x) if logic == 'and'
                else prev_cond(x) or cond_func(x)
            )
            self._conditions[-1] = (new_cond, result)
        else:
            self._conditions.append((cond_func, result))
        return self

    def whens(self, *args):
        """批量添加 when"""
        for i in args:
            if isinstance(i, str):
                self.when(self.comp, i)
            elif isinstance(i, dict):
                for k, v in i.items():
                    self.when(k, v)
            elif isinstance(i, Iterable):
                l = len(i)
                if l == 1:
                    self.when(self.comp, i[0])
                elif l in (2, 3):
                    self.when(*i)
        return self

    def otherwise(self, default):
        self._default = default
        self._chain_locked = True
        return self

    # ---- 执行 ----
    def evaluate(self, data, cover_default=None):
        cover_default = self.cover_default if cover_default is None else cover_default
        result = data if cover_default else self._default
        if self.exec_result:
            if callable(result):
                pass
            elif isinstance(result, str) and result.startswith('->'):
                result = eval("lambda x: " + result[2:], globals(), locals())
        for cond, res in self._conditions:
            cond_result = cond(data)
            if cond_result:
                if self.exec_result:
                    if callable(res):
                        res = res(data)
                    elif isinstance(res, str) and res.startswith('->'):
                        res = eval("lambda x: " + res[2:], globals(), locals())(data)
                result = res
                if self.sht:
                    break
        else:
            if self.exec_result:
                if callable(result):
                    result = result(data)
        if self.result_type and not isinstance(result, self.result_type):
            raise TypeError("结果必须为 {}".format(self.result_type))
        self._result = result
        self._results.append(result)
        return result

    def evaluateEx(self, datas):
        self._results.clear()
        if not isinstance(datas, Iterable) or isinstance(datas, str):
            datas = [datas]
        for i in datas:
            self.evaluate(i)
        return self._results

    # ---- 辅助工具 ----
    def as_numpy_selector(self, default=None):
        """生成 numpy.select 选择器函数"""
        default = default or self._default

        def selector(data):
            import numpy as np
            conditions = [cond(data) for cond, _ in self._conditions]
            choices = [res for _, res in self._conditions]
            return np.select(conditions, choices, default=default)

        return selector

    def np_where(self, cond, x=None, y=None):
        import numpy as np
        x = x if x is not None else self.base
        y = y if y is not None else self._default
        return np.where(cond, x, y)

    def np_select(self, *args, default=None):
        import numpy as np
        if len(args) == 0:
            raise ValueError("参数不能为空")
        return np.select([bool(i[0]) for i in args], [i[1] for i in args], default=default)

    # ---- 调用 ----
    def __call__(self, data=None, is_iters=None):
        if isinstance(data, str) or not isinstance(data, Iterable):
            return self.evaluate(data)
        is_iters = self._is_iters if is_iters is None else is_iters
        f = self.evaluateEx if is_iters else self.evaluate
        return f(data if data is not None else self.base)


# ============================================================
# 顶层函数
# ============================================================
def sig(obj):
    """兼容 legacy sig: 函数签名 / 类方法列表 / dir"""
    if ins.isfunction(obj):
        return ins.signature(obj)
    if ins.isclass(obj):
        mbs = ins.getmembers(obj, predicate=ins.isfunction)
        return [i for i, _ in mbs]
    return dir(obj)


def iif(base=None, true_body=None, false_body=None, comp='_?', sht=True, result_type=None,
        supp=False, whens=None, cases=None, cover_default=False, is_iters=True,
        exec_result=True):
    """legacy iif: 三元/条件构建快捷函数。"""
    if cases is not None:
        cases = [cases] if not isinstance(cases, Iterable) or isinstance(cases, (str, dict)) else cases
        b = ConditionBuilder(base, comp, sht=sht, result_type=result_type, supp=supp,
                             cover_default=cover_default, is_iters=is_iters).cases(*cases)
        b = b.otherwise(false_body) if false_body is not None else b
        return (true_body if b() else false_body) if base is not None and (true_body is not None or false_body is not None) else b

    if whens is not None:
        whens = [whens] if not isinstance(whens, Iterable) or isinstance(whens, (str, dict)) else whens
        b = ConditionBuilder(base, comp, sht=sht, result_type=result_type, supp=supp,
                             cover_default=cover_default, is_iters=is_iters,
                             exec_result=exec_result).whens(*whens)
        b = b.otherwise(false_body) if false_body is not None else b
        return (true_body if b() else false_body) if base is not None and (true_body is not None or false_body is not None) else b

    # 场景1：返回构建器
    if true_body is None and false_body is None:
        return ConditionBuilder(base, comp, sht=sht, result_type=result_type, supp=supp,
                                cover_default=cover_default, is_iters=is_iters,
                                exec_result=exec_result)
    # 场景2：立即计算
    if base is not None:
        if callable(base):
            return true_body if base() else false_body
        if isinstance(base, str):
            pass
        # 简化: 直接用三元
        return true_body if base else false_body
    return true_body if true_body else false_body
