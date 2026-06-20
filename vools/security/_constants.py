"""
安全表达式求值的共享常量

safe_eval.py 和 expression_handler.py 共用这些定义，
避免两处维护不一致导致安全漏洞。
"""

import ast
import operator
__all__ = ['ALLOWED_OPERATORS', 'ALLOWED_BUILTINS_BASIC', 'ALLOWED_BUILTINS_EXTENDED']

# 允许的二元/一元/比较运算符
ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.And: operator.and_,
    ast.Or: operator.or_,
    ast.Not: operator.not_,
    ast.In: lambda x, y: x in y,
    ast.NotIn: lambda x, y: x not in y,
    ast.Is: lambda x, y: x is y,
    ast.IsNot: lambda x, y: x is not y,
}

# 基础允许的内置函数（safe_eval 使用）
ALLOWED_BUILTINS_BASIC = {
    'abs': abs,
    'min': min,
    'max': max,
    'len': len,
    'sum': sum,
    'round': round,
    'int': int,
    'float': float,
    'str': str,
    'bool': bool,
}

# 扩展允许的内置函数（expression_handler 使用）
ALLOWED_BUILTINS_EXTENDED = {
    **ALLOWED_BUILTINS_BASIC,
    'list': list,
    'tuple': tuple,
    'set': set,
    'dict': dict,
    'range': range,
    'enumerate': enumerate,
    'zip': zip,
    'sorted': sorted,
    'reversed': reversed,
    'any': any,
    'all': all,
    'chr': chr,
    'ord': ord,
    'hex': hex,
    'oct': oct,
    'bin': bin,
    'hash': hash,
    'id': id,
}