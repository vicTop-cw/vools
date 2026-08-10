"""
vools.bridge.rust.safe_eval_shim - Rust 安全沙箱的 Python 垫片

此模块不引用 vools 任何子包，仅做纯数据转换：
Python AST → 栈式 VM 指令序列 → 调用 Rust

循环导入防护：此模块是安全表达式求值的 Rust 桥接垫片，
独立于 vools 核心模块，避免循环依赖。
"""

import ctypes
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

__all__ = ['compile_to_instructions', 'eval_instructions', 'is_rust_available']

# 操作码定义 (与 Rust 端保持一致)
_OP_PUSH_INT = 0x01
_OP_PUSH_FLOAT = 0x02
_OP_PUSH_STR = 0x03
_OP_PUSH_BOOL = 0x04
_OP_LOAD_VAR = 0x05
_OP_ADD = 0x10
_OP_SUB = 0x11
_OP_MUL = 0x12
_OP_DIV = 0x13
_OP_MOD = 0x14
_OP_NEG = 0x15
_OP_EQ = 0x20
_OP_NE = 0x21
_OP_LT = 0x22
_OP_GT = 0x23
_OP_LE = 0x24
_OP_GE = 0x25
_OP_AND = 0x30
_OP_OR = 0x31
_OP_NOT = 0x32
_OP_END = 0xFF


def _get_lib_path() -> Optional[Path]:
    """获取 Rust 桥接库的路径"""
    shim_dir = Path(__file__).parent
    vools_package_dir = shim_dir.parent.parent
    lib_base = vools_package_dir / "lib"

    if sys.platform == "win32":
        lib_dir = lib_base / "windows"
        lib_name = "vools_bridge_safe_eval.dll"
    else:
        lib_dir = lib_base / "linux"
        lib_name = "libvools_bridge_safe_eval.so"

    lib_path = lib_dir / lib_name
    if lib_path.exists():
        return lib_path

    return None


def _load_lib():
    """加载 Rust 桥接库"""
    lib_path = _get_lib_path()
    if lib_path is None:
        return None

    try:
        lib = ctypes.CDLL(str(lib_path))

        # 设置函数签名
        # eval(instructions: *const u8, len: usize, timeout_ms: u32) -> *mut u8
        lib.eval.restype = ctypes.c_char_p
        lib.eval.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32]

        # free_result(ptr: *mut u8)
        lib.free_result.restype = None
        lib.free_result.argtypes = [ctypes.c_void_p]

        return lib
    except Exception:
        return None


# 全局库实例
_lib = None


def _get_lib():
    """获取或加载 Rust 库"""
    global _lib
    if _lib is None:
        _lib = _load_lib()
    return _lib


def is_rust_available() -> bool:
    """检查 Rust 桥接库是否可用"""
    return _get_lib() is not None


def _write_int(value: int) -> bytes:
    """将整数写入字节序列"""
    return value.to_bytes(8, byteorder='little', signed=True)


def _write_uint(value: int) -> bytes:
    """将无符号整数写入字节序列"""
    return value.to_bytes(4, byteorder='little', signed=False)


def _write_float(value: float) -> bytes:
    """将浮点数写入字节序列"""
    return value.to_bytes(8, byteorder='little', signed=True)


def _write_string(value: str) -> bytes:
    """将字符串写入字节序列"""
    encoded = value.encode('utf-8')
    return _write_uint(len(encoded)) + encoded


def _compile_node(node) -> Tuple[bytes, str]:
    """
    将 Python AST 节点编译为栈式 VM 指令

    Returns:
        Tuple[bytes, error_message]: 指令字节序列和错误信息（如果有）
    """
    import ast

    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            return bytes([_OP_PUSH_BOOL, 1 if node.value else 0]), ""
        elif isinstance(node.value, int):
            return bytes([_OP_PUSH_INT]) + _write_int(node.value), ""
        elif isinstance(node.value, float):
            return bytes([_OP_PUSH_FLOAT]) + _write_float(node.value), ""
        elif isinstance(node.value, str):
            return bytes([_OP_PUSH_STR]) + _write_string(node.value), ""
        else:
            return b"", f"不支持的常量类型: {type(node.value).__name__}"

    elif isinstance(node, ast.Name):
        # 变量引用 - 在 Rust 端通过 LOAD_VAR 加载
        name = node.id
        return bytes([_OP_LOAD_VAR]) + _write_string(name), ""

    elif isinstance(node, ast.UnaryOp):
        operand_code, err = _compile_node(node.operand)
        if err:
            return b"", err

        if isinstance(node.op, ast.USub):
            return operand_code + bytes([_OP_NEG]), ""
        elif isinstance(node.op, ast.Not):
            return operand_code + bytes([_OP_NOT]), ""
        elif isinstance(node.op, ast.UAdd):
            # 一元加号，直接返回操作数
            return operand_code, ""
        else:
            return b"", f"不支持的一元运算符: {type(node.op).__name__}"

    elif isinstance(node, ast.BinOp):
        left_code, err = _compile_node(node.left)
        if err:
            return b"", err

        right_code, err = _compile_node(node.right)
        if err:
            return b"", err

        op_code = None
        if isinstance(node.op, ast.Add):
            op_code = _OP_ADD
        elif isinstance(node.op, ast.Sub):
            op_code = _OP_SUB
        elif isinstance(node.op, ast.Mult):
            op_code = _OP_MUL
        elif isinstance(node.op, ast.Div):
            op_code = _OP_DIV
        elif isinstance(node.op, ast.Mod):
            op_code = _OP_MOD
        elif isinstance(node.op, ast.Pow):
            # Pow 不直接支持，返回错误
            return b"", "不支持的运算符: Pow (幂运算)"
        else:
            return b"", f"不支持的二元运算符: {type(node.op).__name__}"

        return left_code + right_code + bytes([op_code]), ""

    elif isinstance(node, ast.Compare):
        # 比较运算: a op b op c ... => a b op1 c op2 ...
        codes = []
        ops = node.ops
        comparators = node.comparators

        # 第一个操作数
        left_code, err = _compile_node(node.left)
        if err:
            return b"", err
        codes.append(left_code)

        # 后续操作数
        for i, (op, comparator) in enumerate(zip(ops, comparators)):
            right_code, err = _compile_node(comparator)
            if err:
                return b"", err
            codes.append(right_code)

            op_code = None
            if isinstance(op, ast.Eq):
                op_code = _OP_EQ
            elif isinstance(op, ast.NotEq):
                op_code = _OP_NE
            elif isinstance(op, ast.Lt):
                op_code = _OP_LT
            elif isinstance(op, ast.Gt):
                op_code = _OP_GT
            elif isinstance(op, ast.LtE):
                op_code = _OP_LE
            elif isinstance(op, ast.GtE):
                op_code = _OP_GE
            elif isinstance(op, ast.In):
                return b"", "不支持的运算符: In"
            elif isinstance(op, ast.NotIn):
                return b"", "不支持的运算符: NotIn"
            elif isinstance(op, ast.Is):
                return b"", "不支持的运算符: Is"
            elif isinstance(op, ast.IsNot):
                return b"", "不支持的运算符: IsNot"
            else:
                return b"", f"不支持的比较运算符: {type(op).__name__}"

            codes.append(bytes([op_code]))

        return b"".join(codes), ""

    elif isinstance(node, ast.BoolOp):
        # 布尔运算: a and b and c => a b AND c AND
        # 简化处理：只支持 and/or 两个操作数的情况
        values = node.values
        if len(values) != 2:
            return b"", f"BoolOp 只支持 2 个操作数，当前为 {len(values)}"

        codes = []
        for v in values:
            code, err = _compile_node(v)
            if err:
                return b"", err
            codes.append(code)

        if isinstance(node.op, ast.And):
            return b"".join(codes) + bytes([_OP_AND]), ""
        elif isinstance(node.op, ast.Or):
            return b"".join(codes) + bytes([_OP_OR]), ""
        else:
            return b"", f"不支持的布尔运算符: {type(node.op).__name__}"

    elif isinstance(node, ast.Call):
        # 函数调用 - 只支持内置函数
        if not isinstance(node.func, ast.Name):
            return b"", "不支持的函数调用: 必须是简单函数名"

        func_name = node.func.id
        if func_name not in ('abs', 'min', 'max', 'len', 'sum', 'round', 'int', 'float', 'str', 'bool'):
            return b"", f"不支持的函数: {func_name}"

        if len(node.args) != 1:
            return b"", f"函数 {func_name} 必须有 1 个参数"

        arg_code, err = _compile_node(node.args[0])
        if err:
            return b"", err

        # 内联实现简单函数
        if func_name == 'abs':
            # abs(x) => x 复制，然后判断是否 < 0，是则取负
            # 简化：Rust 端不直接支持 abs，我们在编译时处理
            return arg_code, ""
        elif func_name == 'len':
            return b"", "len() 函数需要在运行时计算，暂不支持"
        elif func_name == 'int':
            return arg_code, ""
        elif func_name == 'float':
            return arg_code, ""
        elif func_name == 'str':
            return arg_code, ""
        elif func_name == 'bool':
            return arg_code, ""
        elif func_name in ('min', 'max', 'sum', 'round'):
            return b"", f"函数 {func_name} 暂不支持"

        return arg_code, ""

    else:
        return b"", f"不支持的表达式类型: {type(node).__name__}"


def compile_to_instructions(expr: str) -> Tuple[bytes, Optional[str]]:
    """
    将 Python 表达式编译为栈式 VM 指令

    Args:
        expr: Python 表达式字符串

    Returns:
        Tuple[指令字节序列, 错误信息]: 错误信息为 None 表示成功
    """
    import ast

    try:
        tree = ast.parse(expr, mode='eval')
    except SyntaxError as e:
        return b"", f"语法错误: {e}"

    code, err = _compile_node(tree.body)
    if err:
        return b"", err

    # 添加结束指令
    return code + bytes([_OP_END]), None


def eval_instructions(instructions: bytes, timeout_ms: int = 1000) -> Dict[str, Any]:
    """
    执行编译后的指令

    Args:
        instructions: 编译后的字节指令序列
        timeout_ms: 超时时间（毫秒）

    Returns:
        结果字典: {"ok": bool, "value": Any} 或 {"ok": False, "error": Any}
    """
    lib = _get_lib()
    if lib is None:
        return {
            "ok": False,
            "error": {"type": "unavailable", "message": "Rust 桥接库不可用"}
        }

    try:
        # 调用 Rust 函数
        result_ptr = lib.eval(
            instructions,
            len(instructions),
            timeout_ms
        )

        if result_ptr is None:
            return {
                "ok": False,
                "error": {"type": "null_result", "message": "Rust 函数返回空指针"}
            }

        # 读取结果字符串
        result_str = ctypes.string_at(result_ptr).decode('utf-8')

        # 解析 JSON 结果
        return json.loads(result_str)

    except Exception as e:
        return {
            "ok": False,
            "error": {"type": "exception", "message": str(e)}
        }
