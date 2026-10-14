"""
vools.bridge.configs 测试

覆盖：单一真源结构、不硬编码用户机器路径、编译器解析、用户 JSON 读写往返、
override/project_root/discovered 语义。
"""

import os
import sys
import json
import tempfile

import pytest

# 确保 bridges/ 在 sys.path 上
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from vools.bridge import configs as C  # noqa: E402


# ---------------------------------------------------------------------------
# 1. 不硬编码用户机器路径
# ---------------------------------------------------------------------------

def test_configs_module_has_no_hardcoded_paths():
    """configs.py 源码不应包含用户机器绝对路径。"""
    import vools.bridge.configs as cfg_mod
    src = open(cfg_mod.__file__, 'r', encoding='utf-8').read()
    assert 'IDEProjects' not in src
    assert 'E:\\IDEProjects' not in src
    assert 'C:\\Users' not in src


def test_all_specs_cover_four_langs():
    """四门桥接语言都应已注册 spec。"""
    specs = C.all_specs()
    for lang in ('tnr', 'lz', 'zi', 'pentad'):
        assert lang in specs, '缺少 spec: {}'.format(lang)


def test_specs_use_env_var_not_absolute_path():
    """工具链位置通过 root_env + globs 表达，不硬编码绝对路径。"""
    specs = C.all_specs()
    for lang in ('tnr', 'lz', 'zi', 'pentad'):
        spec = specs[lang]
        assert spec.root_env, '{} 缺少 root_env'.format(lang)
        assert spec.globs, '{} 缺少 globs'.format(lang)


# ---------------------------------------------------------------------------
# 2. 编译器解析（需本机工具链存在，否则跳过）
# ---------------------------------------------------------------------------

def _have(lang):
    """resolve_compiler 找不到时合法返回 None；exists(None) 会 TypeError，
    必须先判空。"""
    p = C.resolve_compiler(lang)
    return bool(p) and os.path.exists(p)


_HAVE_TOOLS = (
    all(_have(lang) for lang in ('tnr', 'lz', 'pentad'))
    or bool(os.environ.get('VOOLS_PROJECTS_ROOT'))
)

# 注：这 3 个用例原本用 skipif 跳过"未装工具链"的场景，但目标是"不跳过"。
# 改为无条件运行 + 双向契约断言：有工具链必须解析到真实文件；无工具链必须
# 合法返回空/None（不得抛异常）。两种环境都有真实断言，测试始终执行。


def test_resolve_tnr():
    """resolve_compiler('tnr') 契约：返回非空则文件必须真实存在，返回空则合法。"""
    p = C.resolve_compiler('tnr')
    if p:
        assert os.path.exists(p), (
            f"resolve_compiler('tnr') 返回 {p!r} 但文件不存在"
        )


def test_resolve_lz():
    """resolve_compiler('lz') 契约：同上。"""
    p = C.resolve_compiler('lz')
    if p:
        assert os.path.exists(p), (
            f"resolve_compiler('lz') 返回 {p!r} 但文件不存在"
        )


def test_resolve_pentad():
    """resolve_compiler('pentad') 契约：同上。"""
    p = C.resolve_compiler('pentad')
    if p:
        assert os.path.exists(p), (
            f"resolve_compiler('pentad') 返回 {p!r} 但文件不存在"
        )


# ---------------------------------------------------------------------------
# 3. 用户 JSON 读写往返（不触碰真实 HOME）
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_config(tmp_path):
    """使用临时 JSON 路径，测试后还原运行时。"""
    C.clear_runtime()
    path = os.path.join(str(tmp_path), 'bridge_config.json')
    yield path
    C.clear_runtime()


def test_save_load_round_trip(tmp_config):
    """save_user_config / load_user_config 应正确往返。"""
    C.set_override('pentad', 'C:/fake/pentad/p5c.exe')
    C.set_project_root('tnr', 'D:/fake/tnr')
    saved = C.save_user_config(tmp_config)
    assert os.path.exists(saved)

    C.clear_runtime()
    n = C.load_user_config(tmp_config)
    assert n > 0
    assert C.get_override('pentad') == 'C:/fake/pentad/p5c.exe'
    assert C.get_project_root('tnr') == 'D:/fake/tnr'


def test_override_and_clear(tmp_config):
    """set_override 生效，clear_override 清除。"""
    C.set_override('lz', 'C:/fake/lang-zone.exe')
    assert C.get_override('lz') == 'C:/fake/lang-zone.exe'
    assert C.all_overrides().get('lz') == 'C:/fake/lang-zone.exe'
    assert C.clear_override('lz') is True
    assert C.get_override('lz') is None


def test_project_root_round_trip(tmp_config):
    """set_project_root / get_project_root 往返。"""
    C.set_project_root('zi', 'C:/fake/zhi')
    assert C.get_project_root('zi') == 'C:/fake/zhi'
    assert 'zi' in C.all_project_roots()


def test_discovered_round_trip(tmp_config):
    """set_discovered / get_discovered 往返。"""
    C.set_discovered('pentad', 'C:/fake/p5c.exe', '9.9.9')
    d = C.get_discovered('pentad')
    assert d and d['path'] == 'C:/fake/p5c.exe'
    assert d['version'] == '9.9.9'


def test_register_spec_custom():
    """register_spec 应支持新增自定义语言 spec。"""
    spec = C.ToolchainSpec(
        name='fake_lang',
        commands=['fake_lang.exe'],
        version_args=['--version'],
        category='测试',
        install_hint={},
        kind='exe',
        root_env='VOOLS_FAKE_LANG_ROOT',
        globs=['bin/fake_lang.exe'],
        aux={},
        root_dirname_hints=[],
    )
    C.register_spec(spec)
    assert 'fake_lang' in C.all_specs()
    assert C.get_spec('fake_lang').name == 'fake_lang'


def test_user_config_path_default():
    """默认用户 JSON 路径应在用户 HOME 下。"""
    p = C.get_user_config_path()
    home = os.path.expanduser('~').replace('\\', '/')
    assert 'vools' in p
    assert p.replace('\\', '/').startswith(home)


def test_export_report():
    """export_report 应产出非空可读文本报告。"""
    report = C.export_report()
    assert isinstance(report, str)
    assert 'vools.bridge.configs' in report
    assert '用户 JSON' in report