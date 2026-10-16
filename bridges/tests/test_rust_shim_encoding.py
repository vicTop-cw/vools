# -*- coding: utf-8 -*-
"""bridges/tests/test_rust_shim_encoding.py — Rust safe_eval shim 的字节编码必须匹配 VM 契约

钉两个同文件缺陷（2026-10-17 寻虫）：

BUG-75（同族）：_compile_node 曾只认 ast.Constant，py3.6/3.7 的 Num/Str/... 全落
  兜底分支返回错误 —— 表达式编译在 3.6 上不可用。修法复用 vools.core.ast_compat。

BUG-76：_write_float 是 _write_int 的复制粘贴（value.to_bytes(...)），但 float
  没有 to_bytes —— 任何浮点字面量编译即 AttributeError（双版本都炸，与 AST 版本
  无关）。Rust 侧 PUSH_FLOAT 用 f64::from_le_bytes 读 8 字节小端 double
  （safe_eval/src/lib.rs:134），Python 等价即 struct.pack('<d', ...)。

这里只测 _compile_node 的字节产出（纯 Python，不需要 .dll），并用 struct 反解
自证编码符合契约。
"""

import ast
import os
import struct
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _p in (_ROOT, os.path.join(_ROOT, 'bridges')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from vools.bridge.rust import safe_eval_shim as S  # noqa: E402

_OP_PUSH_FLOAT = 0x02
_OP_PUSH_INT = 0x01


def _compile(expr):
    return S._compile_node(ast.parse(expr, mode='eval').body)


def test_float_literal_encodes_as_f64_le():
    code, err = _compile('1.5')
    assert err == '', '浮点编译报错: %r' % err
    assert code[0] == _OP_PUSH_FLOAT
    # 8 字节小端 double，与 Rust f64::from_le_bytes 对齐
    assert code[1:] == struct.pack('<d', 1.5)
    assert struct.unpack('<d', code[1:])[0] == 1.5


def test_int_literal_encodes_as_i64_le():
    code, err = _compile('7')
    assert err == ''
    assert code[0] == _OP_PUSH_INT
    assert struct.unpack('<q', code[1:])[0] == 7


def test_string_literal_compiles():
    code, err = _compile("'abc'")
    assert err == ''
    # 1 字节 opcode + 4 字节 u32 长度 + 内容
    assert code[1:] == struct.pack('<I', 3) + b'abc'


def test_arith_with_literals_compiles():
    code, err = _compile('1 + 2')
    assert err == '', '含字面量的算式在 py3.6 曾因只认 ast.Constant 编译失败'
    assert len(code) > 0
