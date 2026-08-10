"""
安全表达式求值模块
提供受限的表达式求值能力，防止代码注入攻击

支持 Rust 加速：通过 safe_eval_rust 函数在 Rust 库可用时使用高性能实现，
否则回退到纯 Python 实现。
"""

__all__ = [
    'safe_eval',
    'safe_eval_rust',
    'is_rust_safe_eval_available',
    'SafeEvalError',
    'SafeExpressionEvaluator',
    'ALLOWED_OPERATORS',
    'ALLOWED_BUILTINS',
    'safe_lambda',
]

import ast
import operator
from typing import Any, Dict, Optional, Tuple


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
}


class SafeEvalError(Exception):
    """安全求值异常"""
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



class SafeExpressionEvaluator:
    """安全表达式求值器"""

    def __init__(self, allowed_vars: Optional[Dict[str, Any]] = None):
        self.allowed_vars = allowed_vars or {}

    def _eval_node(self, node: ast.AST) -> Any:
        if isinstance(node, ast.Constant):
            return node.value

        elif hasattr(ast, 'Num') and isinstance(node, ast.Num):
            return node.n

        elif hasattr(ast, 'Str') and isinstance(node, ast.Str):
            return node.s

        elif hasattr(ast, 'NameConstant') and isinstance(node, ast.NameConstant):
            return node.value

        elif isinstance(node, ast.Name):
            if node.id in self.allowed_vars:
                return self.allowed_vars[node.id]
            elif node.id in ALLOWED_BUILTINS:
                return ALLOWED_BUILTINS[node.id]
            raise SafeEvalError(f"不允许的变量: {node.id}")

        elif isinstance(node, ast.BinOp):
            left = self._eval_node(node.left)
            right = self._eval_node(node.right)
            op_type = type(node.op)
            if op_type not in ALLOWED_OPERATORS:
                raise SafeEvalError(f"不允许的运算符: {op_type.__name__}")
            return ALLOWED_OPERATORS[op_type](left, right)

        elif isinstance(node, ast.UnaryOp):
            operand = self._eval_node(node.operand)
            op_type = type(node.op)
            if op_type not in ALLOWED_OPERATORS:
                raise SafeEvalError(f"不允许的运算符: {op_type.__name__}")
            return ALLOWED_OPERATORS[op_type](operand)

        elif isinstance(node, ast.Compare):
            left = self._eval_node(node.left)
            for op, comparator in zip(node.ops, node.comparators):
                right = self._eval_node(comparator)
                op_type = type(op)
                if op_type not in ALLOWED_OPERATORS:
                    raise SafeEvalError(f"不允许的比较运算符: {op_type.__name__}")
                if not ALLOWED_OPERATORS[op_type](left, right):
                    return False
            return True

        elif isinstance(node, ast.BoolOp):
            values = [self._eval_node(v) for v in node.values]
            op_type = type(node.op)
            if op_type not in ALLOWED_OPERATORS:
                raise SafeEvalError(f"不允许的布尔运算符: {op_type.__name__}")
            return ALLOWED_OPERATORS[op_type](*values)

        elif isinstance(node, ast.Call):
            func = self._eval_node(node.func)
            args = [self._eval_node(arg) for arg in node.args]

            if func not in ALLOWED_BUILTINS.values():
                raise SafeEvalError(f"不允许的函数调用: {func}")

            return func(*args)

        else:
            raise SafeEvalError(f"不支持的表达式类型: {type(node).__name__}")


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
    
    def evaluate(self, expr: str) -> Any:
        try:
            tree = ast.parse(expr, mode='eval')
            return self._eval_node(tree.body)
        except SyntaxError as e:
            raise SafeEvalError(f"语法错误: {e}")
        except SafeEvalError:
            raise
        except Exception as e:
            raise SafeEvalError(f"求值错误: {e}")


def safe_eval(expr: str, vars: Optional[Dict[str, Any]] = None) -> Any:
    """
    安全求值表达式

    Args:
        expr: 要求值的表达式字符串
        vars: 允许的变量字典

    Returns:
        表达式求值结果

    Raises:
        SafeEvalError: 当表达式包含不安全内容时
    """
    evaluator = SafeExpressionEvaluator(vars)
    return evaluator.evaluate(expr)


# =============================================================================
# Rust 加速版本的 safe_eval
# =============================================================================

# 导入 shim（shim 不引用 vools 子包，避免循环导入）。
# 当 vools-bridges 未安装时回退到 None，保证核心 safe_eval 仍然可用。
try:
    from ..bridge.rust import safe_eval_shim as _safe_eval_shim
except Exception:
    _safe_eval_shim = None


def _safe_eval_rust_impl(expr: str, vars: Optional[Dict[str, Any]] = None, timeout_ms: int = 1000) -> Any:
    """
    Rust 版本的 safe_eval 实现

    通过栈式 VM 在 Rust 沙箱中执行表达式，提供：
    - 超时控制
    - 内存限制
    - 安全隔离（无文件/网络/系统调用访问）

    Args:
        expr: 要求值的表达式字符串
        vars: 允许的变量字典（暂未支持）
        timeout_ms: 超时时间（毫秒）

    Returns:
        表达式求值结果

    Raises:
        SafeEvalError: 当表达式包含不安全内容时
    """
    # 检查 Rust 是否可用
    if _safe_eval_shim is None or not _safe_eval_shim.is_rust_available():
        raise SafeEvalError("Rust 桥接库不可用")

    # 编译表达式为 VM 指令
    instructions, compile_err = _safe_eval_shim.compile_to_instructions(expr)
    if compile_err:
        raise SafeEvalError(compile_err)

    # 执行指令
    result = _safe_eval_shim.eval_instructions(instructions, timeout_ms)

    if not result.get("ok", False):
        error = result.get("error", {})
        error_type = error.get("type", "unknown")
        error_msg = error.get("message", "Unknown error")
        raise SafeEvalError(f"[Rust] {error_type}: {error_msg}")

    # 解析返回值
    value = result.get("value", {})
    value_type = value.get("type", "unknown")
    value_data = value.get("value")

    if value_type == "int":
        return int(value_data)
    elif value_type == "float":
        return float(value_data)
    elif value_type == "str":
        return str(value_data)
    elif value_type == "bool":
        return bool(value_data)
    else:
        raise SafeEvalError(f"[Rust] Unknown value type: {value_type}")


def safe_eval_rust(expr: str, vars: Optional[Dict[str, Any]] = None, timeout_ms: int = 1000) -> Any:
    """
    安全求值表达式（Rust 加速版）

    当 Rust 库可用时使用 Rust 沙箱执行，否则回退到纯 Python 实现。

    Args:
        expr: 要求值的表达式字符串
        vars: 允许的变量字典（暂未支持）
        timeout_ms: 超时时间（毫秒）

    Returns:
        表达式求值结果

    Raises:
        SafeEvalError: 当表达式包含不安全内容时
    """
    # 优先尝试 Rust
    try:
        return _safe_eval_rust_impl(expr, vars, timeout_ms)
    except SafeEvalError as e:
        error_msg = str(e)
        if "Rust 桥接库不可用" in error_msg:
            # Rust 不可用，回退到纯 Python
            return safe_eval(expr, vars)
        raise


def is_rust_safe_eval_available() -> bool:
    """检查 Rust 安全沙箱是否可用"""
    return _safe_eval_shim is not None and _safe_eval_shim.is_rust_available()


DANGEROUS_PATTERNS = [
    'import', 'open', 'exec', 'eval', 'compile',
    '__', 'getattr', 'setattr', 'delattr',
    'os.', 'sys.', 'subprocess', 'requests',
    'eval(', 'exec(', 'compile(', 'open(',
]


def _is_safe_expr(expr: str) -> bool:
    """
    检查表达式是否安全

    Args:
        expr: 表达式字符串

    Returns:
        True 如果安全，False 如果不安全
    """
    expr_lower = expr.lower().strip()
    for pattern in DANGEROUS_PATTERNS:
        if pattern in expr_lower:
            return False
    return True


def _validate_lambda_params(var_names: Tuple[str, ...]) -> bool:
    """
    验证 lambda 参数名称

    Args:
        var_names: 参数名称元组

    Returns:
        True 如果有效，False 如果无效
    """
    valid_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_')
    for name in var_names:
        if not name:
            return False
        if not all(c in valid_chars for c in name):
            return False
        if name[0].isdigit():
            return False
    return True


def safe_lambda(var_names: Tuple[str, ...], expr: str) -> callable:
    """
    安全地创建 lambda 函数

    Args:
        var_names: 参数名称元组，如 ('x',) 或 ('x', 'y')
        expr: lambda 表达式字符串

    Returns:
        lambda 函数

    Raises:
        SafeEvalError: 当表达式包含不安全内容时
    """
    if not _validate_lambda_params(var_names):
        raise SafeEvalError(f"无效的参数名称: {var_names}")

    if not _is_safe_expr(expr):
        raise SafeEvalError(f"表达式包含不安全内容")

    try:
        args = ', '.join(var_names)
        full_expr = f"lambda {args}: {expr}"

        tree = ast.parse(full_expr, mode='eval')

        allowed_vars = {name: f'_v_{i}' for i, name in enumerate(var_names)}
        evaluator = SafeExpressionEvaluator(allowed_vars)

        lambda_node = tree.body
        if isinstance(lambda_node, ast.Lambda):
            result = evaluator._eval_node(lambda_node.body)

        safe_globals = {'__builtins__': {}}

        return eval(full_expr, safe_globals, {})
    except SyntaxError as e:
        raise SafeEvalError(f"lambda 语法错误: {e}")
    except SafeEvalError:
        raise
    except Exception as e:
        raise SafeEvalError(f"lambda 创建错误: {e}")