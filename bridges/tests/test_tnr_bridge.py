"""
vools.bridge.tnr 桥接测试

覆盖：工具链探测、代码生成、参数注入、Tensor 输出解析、装饰器模式、文件直跑。
"""

import os
import sys
import shutil
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from vools.bridge.tnr import (
    tnr,
    TnrBridge,
    compile_and_run,
    run_tnr_file,
    tnr_compiler_available,
    get_tnr_version,
    get_tnr_type,
    _parse_tnr_output,
)

pytestmark = pytest.mark.skipif(
    not tnr_compiler_available(),
    reason='Tnr 工具链不可用（需要 E:/IDEProjects/AI/Tnr 产物或 PATH/WSL 中的 tnr）'
)


# ---------------------------------------------------------------------------
# 工具链探测
# ---------------------------------------------------------------------------

def test_tnr_compiler_available():
    """工具链应可用。"""
    assert tnr_compiler_available() is True


def test_get_tnr_version():
    """版本号非空且含 tnr 标识。"""
    version = get_tnr_version()
    assert isinstance(version, str)
    assert 'tnr' in version.lower() or version.strip() != ''


# ---------------------------------------------------------------------------
# 类型映射
# ---------------------------------------------------------------------------

def test_tnr_type_mapping():
    """Python 类型 → Tnr 类型映射。"""
    assert get_tnr_type(int) == 'int64'
    assert get_tnr_type(float) == 'float64'
    assert get_tnr_type(str) == 'string'
    assert get_tnr_type(bool) == 'bool'
    assert get_tnr_type(list) == 'tensor'
    assert get_tnr_type('int') == 'int64'
    assert get_tnr_type('float64') == 'float64'
    assert get_tnr_type('none') == 'unit'


# ---------------------------------------------------------------------------
# 输出解析
# ---------------------------------------------------------------------------

def test_parse_tnr_output_scalar():
    """标量 Tensor 输出解析为数字。"""
    assert _parse_tnr_output('Tensor<int64, []>(3)') == 3
    assert _parse_tnr_output('Tensor<float64, []>(7)') == 7
    assert _parse_tnr_output('Tensor<int64, []>(-5)') == -5


def test_parse_tnr_output_string():
    """非 Tensor 行原样返回。"""
    assert _parse_tnr_output('你好，Tnr') == '你好，Tnr'
    assert _parse_tnr_output('') is None


def test_parse_tnr_output_tensor():
    """张量 Tensor 输出解析为嵌套列表。"""
    assert _parse_tnr_output('Tensor<int64, [2,2]>(1,2,3,4)') == [1, 2, 3, 4]
    assert _parse_tnr_output('Tensor<int64, [2,2]>([[1, 2], [3, 4]])') == [[1, 2], [3, 4]]


def test_parse_tnr_output_ret_type():
    """按期望返回类型二次转换。"""
    assert _parse_tnr_output('Tensor<int64, []>(7)', ret_type=float) == 7.0
    assert _parse_tnr_output('Tensor<int64, []>(7)', ret_type=str) == '7'


# ---------------------------------------------------------------------------
# 直接执行（compile_and_run）
# ---------------------------------------------------------------------------

def test_compile_and_run_int():
    """整数表达式。"""
    assert compile_and_run('print(1 + 2);') == 3


def test_compile_and_run_float():
    """浮点表达式。"""
    result = compile_and_run('print(3.5 * 2);', ret_type=float)
    assert result == 7.0


def test_compile_and_run_string():
    """字符串输出。"""
    assert compile_and_run('print("你好");') == '你好'


def test_compile_and_run_multi_lines():
    """多行代码：最后一行作为返回值。"""
    code = 'let x = 10;\nprint(x + 5);'
    assert compile_and_run(code) == 15


def test_compile_and_run_args():
    """参数以字面量注入（自定义参数名）。"""
    result = compile_and_run(
        'print(x + y);',
        args=(3, 5),
        names=('x', 'y'),
    )
    assert result == 8


def test_compile_and_run_args_default_names():
    """默认参数名 arg0/arg1。"""
    result = compile_and_run(
        'print(arg0 + arg1);',
        args=(3, 5),
    )
    assert result == 8


def test_compile_and_run_tensor_value():
    """张量参数注入 + 矩阵乘法。"""
    code = 'print(matmul(A, B));'
    result = compile_and_run(
        code,
        args=([[1, 2], [3, 4]], [[5, 6], [7, 8]]),
        names=('A', 'B'),
    )
    # matmul([[1,2],[3,4]], [[5,6],[7,8]]) = [[19,22],[43,50]]
    assert result == [[19, 22], [43, 50]]


# ---------------------------------------------------------------------------
# 装饰器模式
# ---------------------------------------------------------------------------

def test_decorator_add():
    """@tnr 装饰器：函数体即 Tnr 代码（参数引用 arg0/arg1...）。"""

    @tnr
    def add(x: int, y: int) -> int:
        return 'print(arg0 + arg1);'

    assert add(3, 5) == 8


def test_decorator_fallback():
    """工具链不可用或执行失败时回退 Python 实现。"""

    def py_add(x, y):
        return x + y + 100

    @tnr(fallback=py_add)
    def add(x: int, y: int) -> int:
        return 'print(arg0 + arg1);'

    # 正常情况下走 Tnr
    assert add(1, 2) == 3


# ---------------------------------------------------------------------------
# 文件直跑
# ---------------------------------------------------------------------------

def test_run_tnr_file():
    """直接运行 .tnr 文件。"""
    tmpdir = tempfile.mkdtemp()
    tnr_file = os.path.join(tmpdir, 'hello.tnr')
    with open(tnr_file, 'w', encoding='utf-8') as f:
        f.write('print(1 + 2);\nprint("ok");')
    try:
        code, stdout, stderr = run_tnr_file(tnr_file)
        assert code == 0
        assert 'ok' in stdout
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 缓存与模块级代码
# ---------------------------------------------------------------------------

def test_bridge_cache_dir():
    """缓存目录生成与源文件落盘。"""
    bridge = TnrBridge()
    code = 'print(42);'
    src_path = bridge.compile_code(code, 'test_cache', None)
    assert os.path.exists(src_path)
    with open(src_path, 'r', encoding='utf-8') as f:
        assert f.read() == code


def test_generate_code_with_module():
    """module_code 拼进生成代码。"""
    bridge = TnrBridge()
    from vools.bridge._base import FunctionParser
    spec = FunctionParser.from_body(
        'mod_fn', 'print(1);', {'return': int}
    )
    spec.module_code = '// header'
    code = bridge.generate_code(spec)
    assert '// header' in code
    assert 'print(1);' in code


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
