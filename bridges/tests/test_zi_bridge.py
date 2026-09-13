"""
vools.bridge.zi 桥接测试

覆盖：工具链探测、类型映射、直通运行、参数注入、装饰器模式、fallback。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from vools.bridge.zi import (
    zi,
    ZiBridge,
    compile_and_run,
    zi_compiler_available,
    get_zi_version,
    get_zi_type,
)

pytestmark = pytest.mark.skipif(
    not zi_compiler_available(),
    reason='zhi 编译器或 Elixir 运行时不可用'
)


HELLO_ZI = '''
坊 示例

策 主
    言 "你好兹"
'''

PLAIN_ZI = '''
坊 示例

策 主
    言 "hello-zi"
'''


# ---------------------------------------------------------------------------
# 工具链探测
# ---------------------------------------------------------------------------

def test_zi_compiler_available():
    """zhi 编译器 + Elixir 应可用。"""
    assert zi_compiler_available() is True


def test_get_zi_version():
    """版本信息非空。"""
    version = get_zi_version()
    assert isinstance(version, str)


# ---------------------------------------------------------------------------
# 类型映射
# ---------------------------------------------------------------------------

def test_zi_type_mapping():
    """Python 类型 → 兹类型名称映射。"""
    assert get_zi_type(int) == '数'
    assert get_zi_type(float) == '数'
    assert get_zi_type(str) == '字'
    assert get_zi_type(bool) == '真'
    assert get_zi_type(list) == '列'
    assert get_zi_type('number') == '数'
    assert get_zi_type('string') == '字'


# ---------------------------------------------------------------------------
# 直通运行
# ---------------------------------------------------------------------------

def test_compile_and_run_string():
    """言 字符串输出。"""
    result = compile_and_run(HELLO_ZI)
    assert '你好兹' in result


def test_compile_and_run_multi_lines():
    """多行输出返回全文。"""
    code = '''
坊 示例

策 主
    言 "line1"
    言 "line2"
'''
    result = compile_and_run(code)
    assert 'line1' in result
    assert 'line2' in result


def test_compile_and_run_args():
    """参数文本替换注入。"""
    code = '''
坊 示例

策 主
    言 "arg0"
'''
    # arg0 被替换为 "3"
    result = compile_and_run(code, args=(3,))
    assert '3' in result


# ---------------------------------------------------------------------------
# 装饰器模式
# ---------------------------------------------------------------------------

def test_decorator_hello():
    """@zi 装饰器：函数体即兹代码。"""

    @zi
    def hello() -> str:
        return HELLO_ZI

    result = hello()
    assert '你好兹' in result


def test_decorator_fallback():
    """编译失败时回退 Python 实现。"""

    def py_hello():
        return 'fallback-ok'

    @zi(fallback=py_hello)
    def hello() -> str:
        return '策 主\n    言 "oops'  # 语法错误，触发 fallback

    result = hello()
    assert result == 'fallback-ok'


# ---------------------------------------------------------------------------
# 代码生成与缓存
# ---------------------------------------------------------------------------

def test_generate_code_with_module():
    """module_code 拼进生成代码。"""
    bridge = ZiBridge()
    from vools.bridge._base import FunctionParser
    spec = FunctionParser.from_body('mod_fn', PLAIN_ZI, {'return': str})
    spec.module_code = '// header'
    code = bridge.generate_code(spec)
    assert '// header' in code
    assert '策 主' in code


def test_compile_code_writes_source():
    """compile_code 落盘 .玆 源文件。"""
    bridge = ZiBridge()
    src_path = bridge.compile_code(PLAIN_ZI, 'test_cache', None)
    assert os.path.exists(src_path)
    assert src_path.endswith('.玆')
    with open(src_path, 'r', encoding='utf-8') as f:
        assert '策 主' in f.read()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
