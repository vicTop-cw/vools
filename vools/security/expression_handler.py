"""
安全表达式处理模块
提供安全的字符串表达式到函数的转换能力
"""

import ast
import operator
from typing import Any, Callable, Dict, Optional, Tuple, Union


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
]


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


def _validate_ast_node(node: ast.AST, allowed_names: Optional[set] = None) -> None:
    """验证 AST 节点是否安全"""
    allowed_names = allowed_names or set()
    
    if isinstance(node, (ast.Constant, ast.Num, ast.Str, ast.Bytes)):
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
        _validate_ast_node(node.body, allowed_names)
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
        _validate_ast_node(node.value, allowed_names)
        return
    
    elif isinstance(node, ast.IfExp):
        _validate_ast_node(node.test, allowed_names)
        _validate_ast_node(node.body, allowed_names)
        _validate_ast_node(node.orelse, allowed_names)
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
