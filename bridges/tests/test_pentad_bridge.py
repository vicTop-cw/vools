"""
vools.bridge.pentad 桥接测试

覆盖：工具链探测、代码执行、参数字面量注入、装饰器模式、UTF-8 输出。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from vools.bridge.pentad import (
    pentad,
    PentadBridge,
    compile_and_run,
    pentad_compiler_available,
    get_pentad_version,
    get_pentad_type,
)

pytestmark = pytest.mark.skipif(
    not pentad_compiler_available(),
    reason='p5c 工具链不可用（设置 VOOLS_PENTAD_ROOT/VOOLS_PROJECTS_ROOT 或把 p5c 加入 PATH）'
)


# ---------------------------------------------------------------------------
# 工具链探测
# ---------------------------------------------------------------------------

def test_pentad_compiler_available():
    """工具链应可用。"""
    assert pentad_compiler_available() is True


def test_get_pentad_version():
    """版本号应为非空字符串。"""
    v = get_pentad_version()
    assert isinstance(v, str)
    assert v.strip() != ''


def test_get_pentad_type():
    """类型标识应为 'pentad'。"""
    assert get_pentad_type() == 'pentad'


# ---------------------------------------------------------------------------
# 执行
# ---------------------------------------------------------------------------

def test_compile_and_run_add():
    """直接执行 print(1 + 2) 应输出 '3'。"""
    result = compile_and_run('print(1 + 2)')
    assert '3' in result


def test_compile_and_run_with_args():
    """带参数执行 print(x + y) 应输出 x+y 结果。"""
    result = compile_and_run('print(x + y)', args=(3, 5), names=('x', 'y'))
    assert '8' in result


def test_compile_and_run_string():
    """输出中文字符串应按 UTF-8 正确解码（不出现乱码）。"""
    result = compile_and_run('print("你好")')
    assert '你好' in result


def test_decorator_add():
    """@pentad 装饰器应把函数体作为 Pentad 代码执行（参数绑定为 arg0/arg1）。"""
    @pentad
    def add(arg0: int, arg1: int) -> int:
        return 'print(arg0 + arg1)'

    out = add(3, 5)
    assert '8' in out


# ---------------------------------------------------------------------------
# 桥接实现
# ---------------------------------------------------------------------------

def test_bridge_type():
    """桥接类型应为 INTERPRETED，扩展名 .p5。"""
    b = PentadBridge()
    assert b.file_ext == '.p5'
    assert b.name == 'pentad'


def test_compile_code_returns_path():
    """compile_code 应返回 .p5 文件路径且文件存在。"""
    import tempfile
    b = PentadBridge()
    cache_dir = tempfile.mkdtemp()
    p = b.compile_code('print(1)', 'main', cache_dir)
    assert os.path.exists(p)
    assert p.endswith('.p5')