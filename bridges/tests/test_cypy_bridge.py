"""
vools.bridge.cypy 桥接测试

覆盖：工具链探测、类型映射、Cypy→Cython 转译、参数注入、装饰器模式、执行降级。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from vools.bridge.cypy import (
    cypy,
    CypyBridge,
    compile_and_run,
    cypy_compiler_available,
    cypy_run_available,
    get_cypy_type,
)

pytestmark = pytest.mark.skipif(
    not cypy_compiler_available(),
    reason='cypyc 工具链不可用'
)


HELLO_CYPY = """
print(1 + 2)
"""

PLAIN_CYPY = """
print("hello-cypy")
"""


# ---------------------------------------------------------------------------
# 工具链探测
# ---------------------------------------------------------------------------

def test_cypy_compiler_available():
    """cypyc 工具链应可用。"""
    assert cypy_compiler_available() is True


def test_cypy_run_available_type():
    """执行链路探测返回 bool。"""
    assert isinstance(cypy_run_available(), bool)


# ---------------------------------------------------------------------------
# 类型映射
# ---------------------------------------------------------------------------

def test_cypy_type_mapping():
    """Python 类型 → Cypy 类型映射。"""
    assert get_cypy_type(int) == 'int'
    assert get_cypy_type(float) == 'float'
    assert get_cypy_type(str) == 'str'
    assert get_cypy_type(bool) == 'bool'
    assert get_cypy_type(list) == 'list'
    assert get_cypy_type(dict) == 'dict'
    assert get_cypy_type('float64') == 'float'
    assert get_cypy_type('string') == 'str'
    assert get_cypy_type('none') == 'None'


# ---------------------------------------------------------------------------
# Cypy → Cython 转译（核心能力）
# ---------------------------------------------------------------------------

def test_compile_code_transpiles_pyx():
    """compile_code 应把 .cypy 转译为 .pyx 文件。"""
    bridge = CypyBridge()
    pyx_path = bridge.compile_code(PLAIN_CYPY, 'test_hello', None)
    assert os.path.exists(pyx_path)
    assert pyx_path.endswith('.pyx')


def test_generate_code_with_module():
    """module_code 拼进生成代码。"""
    bridge = CypyBridge()
    from vools.bridge._base import FunctionParser
    spec = FunctionParser.from_body('mod_fn', PLAIN_CYPY, {'return': str})
    spec.module_code = '# comment'
    code = bridge.generate_code(spec)
    assert '# comment' in code
    assert 'print' in code


def test_compile_and_run_result():
    """compile_and_run：环境支持时返回执行输出，否则返回 .pyx 路径。"""
    result = compile_and_run(HELLO_CYPY)
    if cypy_run_available():
        assert '3' in str(result)
    else:
        assert isinstance(result, str)
        assert result.endswith('.pyx')


# ---------------------------------------------------------------------------
# 装饰器模式
# ---------------------------------------------------------------------------

def test_decorator_hello():
    """@cypy 装饰器：函数体即 Cypy 代码。"""

    @cypy
    def hello() -> str:
        return HELLO_CYPY

    result = hello()
    assert isinstance(result, str)
    if cypy_run_available():
        assert '3' in result


def test_decorator_fallback():
    """转译/执行失败时回退 Python 实现。"""

    def py_hello():
        return 'fallback-ok'

    @cypy(fallback=py_hello)
    def hello() -> str:
        return "print('this is cypy syntax error '''"  # 语法错误触发 fallback

    result = hello()
    assert result == 'fallback-ok'


# ---------------------------------------------------------------------------
# 参数注入与缓存
# ---------------------------------------------------------------------------

def test_arg_injection():
    """参数文本替换注入。"""
    from vools.bridge.cypy.compiler import _inject_args
    code = 'print(arg0 + arg1)'
    assert _inject_args(code, (3, 5)) == 'print(3 + 5)'
    code2 = 'print(arg0)'
    assert _inject_args(code2, ("hi",)) == 'print(\'hi\')'


def test_compile_code_writes_source():
    """compile_code 落盘 .cypy 源文件并转译。"""
    bridge = CypyBridge()
    pyx_path = bridge.compile_code('print(42)', 'cache_check', None)
    assert os.path.exists(pyx_path)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
