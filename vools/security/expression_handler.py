"""
安全表达式处理模块
提供安全的字符串表达式到函数的转换能力
"""

import ast
import operator
from typing import Any, Callable, Dict, Optional, Tuple, Union

from ..core.ast_compat import LITERAL_TYPES


ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    # BUG-483: 一元正负号此前被当作"非法运算符"——`-1`、`2 * -3`、`abs(-1)`
    # 全部抛 "不允许的运算符: USub"，模板里根本无法出现负数；负号本身无逃逸
    # 风险（操作数仍逐个过 _validate_ast_node）。
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
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

ALLOWED_BUILTINS = {
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

DANGEROUS_PATTERNS = [
    '__import__', 'exec', 'eval', 'compile', 'open',
    '__builtins__', '__globals__', '__locals__',
    'os.', 'sys.', 'subprocess.', 'requests.',
    'socket.', 'shutil.', 'glob.', 'tempfile.',
    'pickle.', 'json.', 'yaml.', 'marshal.',
    'ctypes.', 'win32api.', 'win32con.',
    # BUG-101: Python 对象模型逃逸属性（().__class__.__base__ 等）
    '__class__', '__base__', '__bases__', '__subclasses__', '__mro__',
    '__dict__', '__init__', '__getattribute__', '__getattr__', '__setattr__',
    '__delattr__', '__get__', '__set__', '__delete__',
]

# BUG-101: 禁止访问的对象模型属性名（ast.Attribute 白名单校验）
DANGEROUS_ATTRS = frozenset({
    '__class__', '__base__', '__bases__', '__subclasses__', '__mro__',
    '__dict__', '__init__', '__getattribute__', '__getattr__', '__setattr__',
    '__delattr__', '__get__', '__set__', '__delete__',
    '__call__', '__func__', '__self__',
})

_FORMAT_ESCAPE_ATTRS = frozenset({'format', 'format_map'})
"""BUG-287: format-field 属性遍历逃逸原语——字符串字面量内的 {0.__class__} 对 AST 不可见，必须在属性层禁止这两个方法。"""


class ExpressionSecurityError(Exception):
    """表达式安全异常"""
    pass
    def do(self, f=print, pre_f=None, sub_f=None):
        """Apply a function for side effects, return self for chaining.

        Args:
            f: Function to apply (default print)
            pre_f: Pre-processing function applied before f
            sub_f: Post-processing function (no return expected)

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



def _contains_dangerous_patterns(expr: str) -> bool:
    """检查表达式是否包含危险模式"""
    expr_lower = expr.lower()
    for pattern in DANGEROUS_PATTERNS:
        if pattern in expr_lower:
            return True
    return False


def _validate_identifier(name: str) -> bool:
    """验证标识符是否安全"""
    if not name:
        return False
    if not name[0].isalpha() and name[0] != '_':
        return False
    for char in name[1:]:
        if not char.isalnum() and char != '_':
            return False
    return True


def _validate_comprehension(
    node: ast.AST, allowed_names: Optional[set] = None
) -> None:
    """校验列表/集合/字典推导式。

    推导式中的 target 变量仅在其范围内有效（scope-local），
    不污染外层 allowed_names（避免 target 名在外层被误允许）。
    """
    allowed_names = allowed_names or set()
    comp_allowed = set(allowed_names)

    for gen in node.generators:
        # 迭代器（iter）在 comp_allowed 作用域内求值
        _validate_ast_node(gen.iter, comp_allowed)
        # 推导式 target 允许作为局部变量使用
        for target_node in ast.walk(gen.target):
            if isinstance(target_node, ast.Name):
                comp_allowed.add(target_node.id)
        # ifs 条件
        for if_node in gen.ifs:
            _validate_ast_node(if_node, comp_allowed)

    _validate_ast_node(node.elt, comp_allowed)


def _validate_ast_node(node: ast.AST, allowed_names: Optional[set] = None) -> None:
    """验证 AST 节点是否安全"""
    allowed_names = allowed_names or set()
    
    # 用 ast_compat.LITERAL_TYPES：py3.8+ 仅 ast.Constant；py3.6/3.7 才含
    # legacy 类。直接硬编码 (ast.Num, ast.Str, ast.Bytes) 在 py3.14 会
    # AttributeError（这三个类已移除），且 3.12 起已触发 DeprecationWarning。
    if isinstance(node, LITERAL_TYPES):
        return
    
    elif isinstance(node, ast.Name):
        if node.id not in ALLOWED_BUILTINS and node.id not in allowed_names:
            raise ExpressionSecurityError(f"不允许使用变量或函数: {node.id}")
        return
    
    elif isinstance(node, ast.BinOp):
        if type(node.op) not in ALLOWED_OPERATORS:
            raise ExpressionSecurityError(f"不允许的运算符: {type(node.op).__name__}")
        _validate_ast_node(node.left, allowed_names)
        _validate_ast_node(node.right, allowed_names)
        return
    
    elif isinstance(node, ast.UnaryOp):
        if type(node.op) not in ALLOWED_OPERATORS:
            raise ExpressionSecurityError(f"不允许的运算符: {type(node.op).__name__}")
        _validate_ast_node(node.operand, allowed_names)
        return
    
    elif isinstance(node, ast.Compare):
        _validate_ast_node(node.left, allowed_names)
        for op, comparator in zip(node.ops, node.comparators):
            if type(op) not in ALLOWED_OPERATORS:
                raise ExpressionSecurityError(f"不允许的比较运算符: {type(op).__name__}")
            _validate_ast_node(comparator, allowed_names)
        return
    
    elif isinstance(node, ast.BoolOp):
        for value in node.values:
            _validate_ast_node(value, allowed_names)
        return
    
    elif isinstance(node, ast.Call):
        _validate_ast_node(node.func, allowed_names)
        for arg in node.args:
            _validate_ast_node(arg, allowed_names)
        for kw in node.keywords:
            _validate_ast_node(kw.value, allowed_names)
        return
    
    elif isinstance(node, ast.Lambda):
        for arg in node.args.args:
            if not _validate_identifier(arg.arg):
                raise ExpressionSecurityError(f"无效的参数名称: {arg.arg}")
        # BUG-102: lambda 参数是 scope-local，收集后加入 allowed_names
        lambda_names = set(allowed_names)
        for arg in node.args.args:
            lambda_names.add(arg.arg)
        _validate_ast_node(node.body, lambda_names)
        return
    
    elif isinstance(node, ast.List):
        for elt in node.elts:
            _validate_ast_node(elt, allowed_names)
        return
    
    elif isinstance(node, ast.Tuple):
        for elt in node.elts:
            _validate_ast_node(elt, allowed_names)
        return
    
    elif isinstance(node, ast.Set):
        for elt in node.elts:
            _validate_ast_node(elt, allowed_names)
        return
    
    elif isinstance(node, ast.Dict):
        for key, value in zip(node.keys, node.values):
            if key is not None:
                _validate_ast_node(key, allowed_names)
            _validate_ast_node(value, allowed_names)
        return
    
    elif isinstance(node, ast.Subscript):
        _validate_ast_node(node.value, allowed_names)
        _validate_ast_node(node.slice, allowed_names)
        return
    
    elif isinstance(node, ast.Attribute):
        # BUG-101: 校验属性名，禁止对象模型逃逸（__class__/__base__ 等）
        # BUG-287: 两处加固——① 下划线开头的属性一律拒绝（dunder 逃逸全兜底，
        # 不依赖 DANGEROUS_ATTRS 枚举完整）；② 拒绝 format/format_map：
        # `('{0.__cla' + 'ss__}').format(x)` 这类拼接可绕过原文子串黑名单，
        # 而 format-field 内的属性遍历(" {0.__class__}"）对 AST 不可见——
        # 实测可抵达 <class 'int'>、乃至 __subclasses__ 绑定方法（沙箱逃逸）。
        if (node.attr in DANGEROUS_ATTRS
                or node.attr.startswith('_')
                or node.attr in _FORMAT_ESCAPE_ATTRS):
            raise ExpressionSecurityError(
                f"不允许访问属性: {node.attr}"
                f"（BUG-101/BUG-287 对象模型与 format 逃逸防护）"
            )
        _validate_ast_node(node.value, allowed_names)
        return
    
    elif isinstance(node, ast.IfExp):
        _validate_ast_node(node.test, allowed_names)
        _validate_ast_node(node.body, allowed_names)
        _validate_ast_node(node.orelse, allowed_names)
        return
    
    elif isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
        _validate_comprehension(node, allowed_names)
        return

    elif isinstance(node, ast.DictComp):
        _validate_comprehension(node, allowed_names)
        # DictComp 还有 value 字段
        _validate_ast_node(node.value, allowed_names)
        return

    else:
        raise ExpressionSecurityError(f"不支持的表达式类型: {type(node).__name__}")


def safe_compile_expression(expr: str, param_names: Tuple[str, ...] = ('x',)) -> Callable:
    """
    安全编译表达式为函数
    
    Args:
        expr: 表达式字符串
        param_names: 参数名称元组
    
    Returns:
        编译后的函数
    
    Raises:
        ExpressionSecurityError: 当表达式不安全时
    """
    if not expr or not isinstance(expr, str):
        raise ExpressionSecurityError("表达式必须是非空字符串")
    
    if _contains_dangerous_patterns(expr):
        raise ExpressionSecurityError("表达式包含不安全内容")
    
    for name in param_names:
        if not _validate_identifier(name):
            raise ExpressionSecurityError(f"无效的参数名称: {name}")
    
    try:
        # BUG-443: 原实现无条件拼成 ``lambda {args}: {expr}``。当 expr 本身已是
        # lambda 形式（如 ``'lambda x: x > 1'``）时会变成
        # ``lambda x: lambda x: x > 1``——编译出的函数被调用后返回**内层 lambda
        # 对象**（恒真），过滤静默失效：
        #     VList([1, 2, 3]).filter('lambda x: x > 1')  -> [1, 2, 3]   # 应为 [2, 3]
        # 因此先判断 expr 是否已是完整 lambda，若是则直接编译（不再外层包裹）。
        try:
            parsed = ast.parse(expr, mode='eval')
        except SyntaxError as e:
            raise ExpressionSecurityError(f"语法错误: {e}")
        if isinstance(parsed.body, ast.Lambda):
            full_expr = expr
        else:
            args = ', '.join(param_names)
            full_expr = f"lambda {args}: {expr}"
        
        tree = ast.parse(full_expr, mode='eval')
        _validate_ast_node(tree.body, set(param_names))
        
        safe_globals = {
            '__builtins__': {k: v for k, v in ALLOWED_BUILTINS.items()}
        }
        
        return eval(full_expr, safe_globals, {})
    
    except SyntaxError as e:
        raise ExpressionSecurityError(f"语法错误: {e}")
    except ExpressionSecurityError:
        raise
    except Exception as e:
        raise ExpressionSecurityError(f"编译错误: {e}")


def safe_eval_expression(expr: str, vars: Optional[Dict[str, Any]] = None) -> Any:
    """
    安全求值表达式
    
    Args:
        expr: 表达式字符串
        vars: 允许的变量字典
    
    Returns:
        表达式求值结果
    
    Raises:
        ExpressionSecurityError: 当表达式不安全时
    """
    vars = vars or {}
    
    if not expr or not isinstance(expr, str):
        raise ExpressionSecurityError("表达式必须是非空字符串")
    
    if _contains_dangerous_patterns(expr):
        raise ExpressionSecurityError("表达式包含不安全内容")
    
    try:
        tree = ast.parse(expr, mode='eval')
        _validate_ast_node(tree.body, set(vars.keys()))
        
        safe_globals = {
            '__builtins__': {k: v for k, v in ALLOWED_BUILTINS.items()}
        }
        
        return eval(expr, safe_globals, vars)
    
    except SyntaxError as e:
        raise ExpressionSecurityError(f"语法错误: {e}")
    except ExpressionSecurityError:
        raise
    except Exception as e:
        raise ExpressionSecurityError(f"求值错误: {e}")


def create_filter_func(expr: str, param_name: str = 'x') -> Callable[[Any], bool]:
    """
    创建安全的过滤函数
    
    Args:
        expr: 过滤表达式
        param_name: 参数名称
    
    Returns:
        过滤函数
    """
    return safe_compile_expression(expr, (param_name,))


def create_map_func(expr: str, param_name: str = 'x') -> Callable[[Any], Any]:
    """
    创建安全的映射函数
    
    Args:
        expr: 映射表达式
        param_name: 参数名称
    
    Returns:
        映射函数
    """
    return safe_compile_expression(expr, (param_name,))


__all__ = [
    'ExpressionSecurityError',
    'safe_compile_expression',
    'safe_eval_expression',
    'create_filter_func',
    'create_map_func',
]
