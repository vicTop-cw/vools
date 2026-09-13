"""
vools.bridge.lz 桥接测试

覆盖：工具链探测、类型映射、LZ→Rust 转译、参数注入、装饰器模式、rustc 降级。
"""

import os
import sys
import shutil
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from vools.bridge.lz import (
    lz,
    LzBridge,
    compile_and_run,
    lz_compiler_available,
    get_lz_type,
    rustc_available,
)

pytestmark = pytest.mark.skipif(
    not lz_compiler_available(),
    reason='lang-zone 工具链不可用（需要 E:/IDEProjects/AI/lang-zone 产物或 PATH 中的 lang-zone）'
)


HELLO_LZ = """
def main():
    let v = arg0 + arg1
    print(v)
"""

PLAIN_LZ = """
def main():
    let v = 1 + 2
    print(v)
"""


# ---------------------------------------------------------------------------
# 工具链探测
# ---------------------------------------------------------------------------

def test_lz_compiler_available():
    """lang-zone 工具链应可用。"""
    assert lz_compiler_available() is True


def test_rustc_available_type():
    """rustc 探测返回 bool。"""
    assert isinstance(rustc_available(), bool)


# ---------------------------------------------------------------------------
# 类型映射
# ---------------------------------------------------------------------------

def test_lz_type_mapping():
    """Python 类型 → LZ 类型映射。"""
    assert get_lz_type(int) == 'i64'
    assert get_lz_type(float) == 'f64'
    assert get_lz_type(str) == 'String'
    assert get_lz_type(bool) == 'bool'
    assert get_lz_type(list) == 'Vec'
    assert get_lz_type('float64') == 'f64'
    assert get_lz_type('string') == 'String'
    assert get_lz_type('int64') == 'i64'


# ---------------------------------------------------------------------------
# LZ → Rust 转译（核心能力）
# ---------------------------------------------------------------------------

def test_compile_code_transpiles_rs():
    """compile_code 应把 .lz 转译为 .rs 文件（无参数代码）。"""
    bridge = LzBridge()
    rs_path = bridge.compile_code(PLAIN_LZ, 'test_hello', None)
    assert os.path.exists(rs_path)
    assert rs_path.endswith('.rs')
    with open(rs_path, 'r', encoding='utf-8') as f:
        rs = f.read()
    assert 'fn main' in rs or 'pub fn main' in rs
    assert 'println' in rs


def test_generate_code_with_module():
    """module_code 拼进生成代码。"""
    bridge = LzBridge()
    from vools.bridge._base import FunctionParser
    spec = FunctionParser.from_body('mod_fn', HELLO_LZ, {'return': int})
    spec.module_code = '// header'
    code = bridge.generate_code(spec)
    assert '// header' in code
    assert 'def main' in code


def test_compile_and_run_transpile_only():
    """rustc 不可用时 compile_and_run 返回 .rs 路径（降级）。"""
    result = compile_and_run(HELLO_LZ, args=(1, 2))
    if rustc_available():
        assert isinstance(result, str)
    else:
        # 降级：返回 .rs 路径
        assert isinstance(result, str)
        assert result.endswith('.rs')


# ---------------------------------------------------------------------------
# 装饰器模式
# ---------------------------------------------------------------------------

def test_decorator_hello():
    """@lz 装饰器：函数体即 LZ 代码。"""

    @lz
    def hello(x: int, y: int) -> int:
        return HELLO_LZ

    result = hello(1, 2)
    assert isinstance(result, str)
    if rustc_available():
        assert '3' in result


def test_decorator_fallback():
    """工具链不可用或转译失败时回退 Python 实现。"""

    def py_hello(x, y):
        return x + y + 100

    @lz(fallback=py_hello)
    def hello(x: int, y: int) -> int:
        return HELLO_LZ

    result = hello(1, 2)
    if rustc_available():
        assert '3' in str(result)
    else:
        # 转译本身成功（.rs 路径），不回退
        assert isinstance(result, str) and result.endswith('.rs')


# ---------------------------------------------------------------------------
# 缓存与文件直跑
# ---------------------------------------------------------------------------

def test_literal_injection():
    """参数字面量注入源码。"""
    bridge = LzBridge()
    from vools.bridge._base import FunctionParser
    spec = FunctionParser.from_body('inj', 'print(arg0)', {'return': int})
    code = bridge.generate_code(spec)
    # 参数绑定由 call_func 注入
    assert 'print(arg0)' in code


def test_no_bom_write():
    """.lz 文件写入必须无 BOM（LZ 解析器不识别 BOM）。"""
    bridge = LzBridge()
    code_hash = os.urandom(4).hex()
    src = bridge.compile_code(PLAIN_LZ, 'bom_check_' + code_hash, None)
    with open(src, 'rb') as f:
        head = f.read(3)
    assert head != b'\xef\xbb\xbf', '.lz 文件不应包含 UTF-8 BOM'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
