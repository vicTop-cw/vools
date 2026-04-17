"""
条件判断工具模块

提供 iif 函数和 ConditionBuilder 类，用于灵活的条件判断和分支处理。
"""

import inspect as ins
from collections.abc import Iterable
from typing import Any, Callable, Optional, Union, List, Dict

__all__ = ["LazyProperty", "ConditionBuilder", "iif"]


class LazyProperty:
    """延迟属性装饰器"""
    def __init__(self, func):
        self.func = func
        self._name = f"_lazy_{func.__name__}"  # 强制添加前缀

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
    """条件构建器类"""
    
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
        "not in": lambda a, b: a not in b
    }
    
    @property
    def comp(self):
        return self._comp

    @staticmethod
    def _fix_comp(comp):
        if comp is bool:
            comp = lambda _, b: bool(b)
        else:
            ps = ins.signature(comp).parameters
            l = len(ps)
            if l >= 2:
                pass
            elif l == 1:
                comp = lambda _, b: bool(comp(b))
            elif l == 0:
                comp = lambda _, b: bool(comp())
        return comp

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

    def __init__(self, base_value, comp='==', sht=True, result_type=None, supp=True, cover_default=False, is_iters=None, exec_result=True):
        self.base = base_value
        self.supp = supp  # 补充运算符开关
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
        self.exec_result = exec_result  # 执行结果开关,默认True,如果返回结果是个函数 则执行结果，函数必须是单参函数

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

    def case(self, value, result, comp=None):
        """添加条件案例"""
        if self._chain_locked:
            raise RuntimeError("链式调用已终止")
        
        if comp is None:
            self._conditions.append((lambda x: self.comp(x, value), result))
        elif isinstance(comp, str):
            comp = self._OPERATORS.get(comp, None)
            if comp is None:
                raise ValueError("不支持的比较符")
            self._conditions.append((lambda x: (x, value), result))
        elif callable(comp):
            self._conditions.append((lambda x: comp(x, value), result))
        else:
            raise ValueError("不支持的比较符")
        return self

    def cases(self, *args):
        """
        批量添加条件案例
        
        args:
            (value, result)
            (value, result, comp)
        """
        len_args = len(args)
        if len_args == 0:
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
        """添加比较值，支持逻辑组合"""
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
                        cond_func = lambda x: self.comp(x, value)
                else:
                    cond_func = lambda x: cond_func(x, value)

        else:
            cond_func = lambda x: self.comp(x, value)
        
        # 复合条件处理
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
        """批量添加条件"""
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
        """设置默认值"""
        self._default = default
        self._chain_locked = True
        return self

    def evaluate(self, data, cover_default=None):
        """执行计算并验证结果类型"""
        cover_default = self.cover_default if cover_default is None else cover_default
        result = data if cover_default else self._default
        x = data
        if self.exec_result:
            if callable(result):
                pass
            elif isinstance(result, str) and result.startswith('->'):
                result = eval(f"lambda x: {result[2:]}", globals(), locals())
        for cond, res in self._conditions:
            cond_result = cond(data)
            if cond_result:
                if self.exec_result:
                    if callable(res):
                        res = res(data)
                    elif isinstance(res, str) and res.startswith('->'):
                        res = eval(f"lambda x: {res[2:]}", globals(), locals())(data)
                result = res
                if self.sht: break
        else:
            if self.exec_result:
                if callable(result):
                    result = result(data)
        if self.result_type and not isinstance(result, self.result_type):
            raise TypeError(f"结果必须为 {self.result_type}")
        self._result = result
        self._results.append(result)
        return result

    def evaluateEx(self, datas):
        """批量执行计算"""
        self._results.clear()
        if not isinstance(datas, Iterable) or isinstance(datas, str):
            datas = [datas]
        for i in datas:
            self.evaluate(i)
        return self._results

    def __call__(self, data=None, is_iters=None):
        """调用方式兼容"""
        if isinstance(data, str) or not isinstance(data, Iterable):
            return self.evaluate(data)
        is_iters = self._is_iters if is_iters is None else is_iters
        f = self.evaluateEx if is_iters else self.evaluate
        return f(data if data is not None else self.base)


def iif(base=None, true_body=None, false_body=None, comp='_?', sht=True, result_type=None, supp=False, whens=None, cases=None, cover_default=False, is_iters=True):
    """
    条件判断函数
    
    参数:
        base: 基础值
        true_body: 条件为真时的结果
        false_body: 条件为假时的结果
        comp: 比较运算符
        sht: 是否短路（找到第一个匹配条件后停止）
        result_type: 结果类型
        supp: 是否支持补充运算符
        whens: 条件列表
        cases: 案例列表
        cover_default: 是否覆盖默认值
        is_iters: 是否批量处理
    
    返回:
        条件构建器或计算结果
    """
    if cases is not None:
        cases = [cases] if not isinstance(cases, Iterable) or isinstance(cases, (str, dict)) else cases
        b = ConditionBuilder(base, comp, sht=sht, result_type=result_type, supp=supp, cover_default=cover_default, is_iters=is_iters).cases(*cases)
        b = b.otherwise(false_body) if false_body is not None else b
        return (true_body if b() else false_body) if base is not None and (true_body is not None or false_body is not None) else b
    
    if whens is not None:
        whens = [whens] if not isinstance(whens, Iterable) or isinstance(whens, (str, dict)) else whens
        b = ConditionBuilder(base, comp, sht=sht, result_type=result_type, supp=supp, cover_default=cover_default, is_iters=is_iters).whens(*whens)
        b = b.otherwise(false_body) if false_body is not None else b
        return (true_body if b() else false_body) if base is not None and (true_body is not None or false_body is not None) else b
    
    # 场景1：返回Condition构建器
    if true_body is None and false_body is None:
        return ConditionBuilder(base, comp, sht=sht, result_type=result_type, supp=supp, cover_default=cover_default, is_iters=is_iters)
    
    # 场景2：立即计算结果
    if base is not None:
        if callable(base):
            return true_body if base() else false_body
        if isinstance(base, str):
            if base.startswith('->'):
                return true_body if eval(base[2:], globals(), locals())() else false_body
            elif supp:
                return true_body if eval(base, globals(), locals())() else false_body
    
    return true_body if true_body else false_body