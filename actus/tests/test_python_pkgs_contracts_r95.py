# -*- coding: utf-8 -*-
"""probe/python_pkgs.py 契约测试 r95（目标：模块 --cov ≥90%）。

对象：``vools/actus/probe/python_pkgs.py`` —— Python 包探测
（发行元数据索引 → _vendor 索引 → pkg_resources 兜底 → import 兜底，
包维度并发，预算截断 + budget_exceeded 留痕）。

本测试锁住的契约（退步会怎样）：
  * _split_dist_filename 反解 {name}-{version}.dist-info/.egg-info，
    版本必须以数字开头 —— ABI 标记目录（foo-1.0-py3.13.egg-info）混进
    版本字段时（把 py3.13 当版本号），此处红。
  * _normalize_dist_name PEP 503 折叠（大小写 / [-_.] 连续折叠）——
    规范化不一致会让同一发行版在索引里查不到（假阴性回归）。
  * _get_pkg_version_detail 探测顺序（元数据索引 → vendor → pkg_resources
    → import）与失败留痕：版本探测悄悄变成「import 成功即装了」，
    或非预期异常被吞成「未安装」时，此处红。
  * import 兜底只用 import_name；无 __version__ 的模块报 'installed' ——
    numpy 2.x 这类没 __version__ 的包被误报空版本时此处红。
  * probe() 结果顺序与 CRITICAL_PACKAGES 逐字一致（按下标回填）——
    并发改成按完成顺序合并时，此处红。
  * 预算耗尽的包标 error_kind="budget_exceeded" 且 _summary 计数 ——
    超预算被静默少算（回归 docstring 点名的「绝不静默」契约）时，此处红。
  * _summary 三数字互斥加和为 total；没超预算时不含 budget_exceeded 键。

隔离：全部用 monkeypatch 字符串寻址 patch 'vools.actus.probe.python_pkgs.*'；
模块级单例 _PATH_SCAN / _PKG_RESOURCES_INDEX 每个测试前重置（防跨测试污染）；
CRITICAL_PACKAGES / _PKG_BUDGET_SEC monkeypatch 注入小清单，避免真扫描慢包。
禁真网络；无 GUI 路径。
"""

import _ai_local_bootstrap  # noqa: F401  (必须在 import vools.actus 之前)

import os
import sys
import threading
import time
import types

import pytest

from vools.actus.probe import python_pkgs as P


@pytest.fixture(autouse=True)
def _rebind_python_pkgs_identity():
    """bootstrap 身份对齐：monkeypatch 字符串寻址解析 sys.modules 现行条目，
    模块顶层 import 的 P 可能是替换前的旧身份。每个测试前重绑。"""
    global P
    import importlib as _il
    P = _il.import_module('vools.actus.probe.python_pkgs')
    yield


@pytest.fixture(autouse=True)
def _reset_singletons():
    """模块级懒加载单例按测试重置：单例缓存跨测试泄漏会把 A 测试的
    sys.path 视图带给 B 测试（假阳性/假阴性）。"""
    import importlib as _il
    m = _il.import_module('vools.actus.probe.python_pkgs')
    monkey_old = getattr(m, '_PATH_SCAN', 'sentinel')
    monkey_old2 = getattr(m, '_PKG_RESOURCES_INDEX', 'sentinel')
    m._PATH_SCAN = None
    m._PKG_RESOURCES_INDEX = None
    yield
    m._PATH_SCAN = monkey_old
    m._PKG_RESOURCES_INDEX = monkey_old2


@pytest.fixture
def small_table(monkeypatch):
    """把 CRITICAL_PACKAGES 换成 3 条小清单 + 大预算，隔离真机包环境。"""
    monkeypatch.setattr('vools.actus.probe.python_pkgs.CRITICAL_PACKAGES', [
        ('zzz-fakepkg', 'zzz_fakepkg', False),
        ('Pillow', 'PIL', True),
        ('pytest', 'pytest', True),
    ])
    monkeypatch.setattr('vools.actus.probe.python_pkgs._PKG_BUDGET_SEC', 5.0)


# ────────────────────────── _split_dist_filename ──────────────────────────

def test_split_dist_filename_dist_info():
    assert P._split_dist_filename('pandas-2.1.0.dist-info') == ('pandas', '2.1.0')


def test_split_dist_filename_egg_info():
    assert P._split_dist_filename('six-1.16.0.egg-info') == ('six', '1.16.0')


def test_split_dist_filename_rejects_non_numeric_version():
    # ABI 标记目录：stem rsplit 出 py3.13 —— 版本必须以数字开头才算可靠反解
    assert P._split_dist_filename('foo-1.0-py3.13.egg-info') is None


def test_split_dist_filename_rejects_bad_shapes():
    assert P._split_dist_filename('noversion.dist-info') is None      # 无 '-'
    assert P._split_dist_filename('x-.dist-info') is None             # 空版本
    assert P._split_dist_filename('-1.0.dist-info') is None           # 空名
    assert P._split_dist_filename('foo-1.0.whl') is None              # 非元数据后缀
    assert P._split_dist_filename('') is None


# ────────────────────────── _normalize_dist_name ──────────────────────────

def test_normalize_dist_name_pep503():
    assert P._normalize_dist_name('Pillow') == 'pillow'
    assert P._normalize_dist_name('mysql.connector') == 'mysql-connector'
    assert P._normalize_dist_name('scikit__learn..x') == 'scikit-learn-x'
    assert P._normalize_dist_name('  A--B  ') == 'a-b'


# ────────────────────────── _load_metadata_module ──────────────────────────

def test_load_metadata_module_stdlib_on_py313():
    from importlib import metadata as _md
    assert P._load_metadata_module() is _md


def test_load_metadata_module_fallback_chain(monkeypatch):
    # 挡掉 stdlib 路径后应退回 importlib_metadata backport。
    # 注意：`from importlib import metadata` 的字节码是 IMPORT_NAME 'importlib'
    # + IMPORT_FROM 'metadata'，__import__ 收到的 name 是 'importlib'（fromlist 含
    # 'metadata'），不是 'importlib.metadata'——按 fromlist 判定才挡得住。
    fake_backport = types.ModuleType('importlib_metadata')
    monkeypatch.setitem(sys.modules, 'importlib_metadata', fake_backport)
    real_import = __import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == 'importlib' and 'metadata' in (fromlist or ()):
            raise ImportError('no stdlib metadata')
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr('builtins.__import__', fake_import)
    assert P._load_metadata_module() is fake_backport


def test_load_metadata_module_none_when_all_missing(monkeypatch):
    def no_import(name, *a, **kw):
        raise ImportError(name)

    monkeypatch.setattr('builtins.__import__', no_import)
    assert P._load_metadata_module() is None


# ────────────────────────── _build_metadata_index ──────────────────────────

class _FakeDist:
    def __init__(self, filename=None, name=None, version=None,
                 version_value=None, meta_raises=False):
        self._filename = filename
        self._name = name
        self._version = version
        self._version_value = version_value
        self._meta_raises = meta_raises

    @property
    def _path(self):
        if self._filename is None:
            raise AttributeError('no _path')
        return types.SimpleNamespace(name=self._filename)

    @property
    def metadata(self):
        if self._meta_raises:
            raise ValueError('corrupt metadata')
        return {'Name': self._name, 'Version': self._version}

    @property
    def version(self):
        if self._version_value is None:
            raise RuntimeError('broken version')
        return self._version_value


def _patch_distributions(monkeypatch, dists, module=None):
    fake_mod = types.ModuleType('fake_metadata')
    fake_mod.distributions = lambda: iter(dists)
    # _build_metadata_index 内部调 _load_metadata_module —— patch 它的返回
    monkeypatch.setattr('vools.actus.probe.python_pkgs._load_metadata_module',
                        lambda: fake_mod)


def test_metadata_index_uses_filename_parse(monkeypatch):
    _patch_distributions(monkeypatch, [
        _FakeDist(filename='pandas-2.1.0.dist-info'),
        _FakeDist(filename='My_Pkg-1.0.dist-info'),
    ])
    idx = P._build_metadata_index()
    assert 'pandas' in idx
    assert 'my-pkg' in idx
    # 文件名反解路径：已知版本位为 None（真值命中时才读）
    assert idx['pandas'] == (idx['pandas'][0], None)


def test_metadata_index_falls_back_to_metadata_file(monkeypatch):
    # _path 拿不到 → 读 metadata['Name'/'Version']
    _patch_distributions(monkeypatch, [
        _FakeDist(name='weird-pkg', version='3.3.3'),
    ])
    idx = P._build_metadata_index()
    assert idx.get('weird-pkg') == (idx['weird-pkg'][0], '3.3.3')


def test_metadata_index_skips_corrupt_entries(monkeypatch):
    _patch_distributions(monkeypatch, [
        _FakeDist(meta_raises=True),
        _FakeDist(filename='pandas-2.1.0.dist-info'),
    ])
    idx = P._build_metadata_index()
    assert 'pandas' in idx


def test_metadata_index_empty_when_no_metadata_module(monkeypatch):
    monkeypatch.setattr('vools.actus.probe.python_pkgs._load_metadata_module',
                        lambda: None)
    assert P._build_metadata_index() == {}


def test_metadata_index_returns_empty_on_scan_failure(monkeypatch):
    def boom():
        raise OSError('scan failed')

    fake_mod = types.ModuleType('fake_metadata')
    fake_mod.distributions = boom
    monkeypatch.setattr('vools.actus.probe.python_pkgs._load_metadata_module',
                        lambda: fake_mod)
    assert P._build_metadata_index() == {}


# ────────────────────────── _indexed_version ──────────────────────────

def test_indexed_version_known_value():
    assert P._indexed_version((object(), '9.9.9')) == ('9.9.9', None)


def test_indexed_version_reads_truth(monkeypatch):
    d = _FakeDist(version_value='2.2.2')
    assert P._indexed_version((d, None)) == ('2.2.2', None)


def test_indexed_version_error_signal():
    d = _FakeDist(version_value=None)   # version property raises RuntimeError
    version, signal = P._indexed_version((d, None))
    assert version == ''
    assert signal == {'error_kind': 'metadata_error', 'error': 'RuntimeError'}


# ────────────────────────── _build_path_scan / vendor / legacy eggs ──────────────────────────

def _mk_vendor_tree(tmp_path, vendor_rel='setuptools/_vendor'):
    d = tmp_path / vendor_rel
    d.mkdir(parents=True)
    (d / 'tomli-2.0.1.dist-info').mkdir()
    (d / 'notametadata.txt').write_text('x', encoding='utf-8')
    return tmp_path


def test_path_scan_finds_vendor_and_legacy_eggs(tmp_path, monkeypatch):
    _mk_vendor_tree(tmp_path)
    (tmp_path / 'thing.egg').touch()
    monkeypatch.setattr(sys, 'path', [str(tmp_path)])
    scan = P._build_path_scan()
    assert scan['vendor'] == {'tomli': '2.0.1'}
    assert scan['legacy_eggs'] is True


def test_path_scan_no_legacy_eggs_without_egg_entries(tmp_path, monkeypatch):
    _mk_vendor_tree(tmp_path)
    monkeypatch.setattr(sys, 'path', [str(tmp_path)])
    scan = P._build_path_scan()
    assert scan['legacy_eggs'] is False


def test_path_scan_singleton_cached(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, 'path', [])
    first = P._build_path_scan()
    # 第二次走缓存：即使改 sys.path 也不重建
    monkeypatch.setattr(sys, 'path', ['nonexistent-dir'])
    assert P._build_path_scan() is first


def test_path_scan_skips_unreadable_dirs(tmp_path, monkeypatch):
    # 空字符串 / 不存在目录 / listdir 抛 OSError 的目录都要跳过
    monkeypatch.setattr(sys, 'path', ['', str(tmp_path / 'no-such-dir')])
    # 把 os.listdir 对存在的目录打成 OSError：用一个假目录绕过 isdir 再抛
    real_isdir = os.path.isdir
    decoy = tmp_path / 'decoy'
    decoy.mkdir()

    def fake_isdir(p):
        if str(p) == str(decoy):
            return True
        return real_isdir(p)

    monkeypatch.setattr('vools.actus.probe.python_pkgs.os.path.isdir', fake_isdir)
    monkeypatch.setattr(sys, 'path', ['', str(decoy)])
    scan = P._build_path_scan()
    assert scan == {'vendor': {}, 'legacy_eggs': False}


def test_vendor_index_and_legacy_helpers(tmp_path, monkeypatch):
    _mk_vendor_tree(tmp_path)
    (tmp_path / 'a.egg-link').touch()
    monkeypatch.setattr(sys, 'path', [str(tmp_path)])
    assert P._build_vendor_index() == {'tomli': '2.0.1'}
    assert P._has_legacy_eggs() is True


# ────────────────────────── _build_pkg_resources_index ──────────────────────────

def test_pkg_resources_index_reads_working_set(monkeypatch):
    fake_pr = types.ModuleType('pkg_resources')

    class _D:
        project_name = 'Some-Pkg'
        version = '0.1'

    class _Bad:
        @property
        def project_name(self):
            raise RuntimeError('bad')

    fake_pr.working_set = [_D(), _Bad()]
    monkeypatch.setitem(sys.modules, 'pkg_resources', fake_pr)
    idx = P._build_pkg_resources_index()
    assert idx == {'some-pkg': '0.1'}       # 坏条目被跳过


def test_pkg_resources_index_import_failure_returns_empty(monkeypatch):
    def no_import(name, *a, **kw):
        raise ImportError(name)

    monkeypatch.setattr('builtins.__import__', no_import)
    assert P._build_pkg_resources_index() == {}


def test_pkg_resources_index_singleton(monkeypatch):
    fake_pr = types.ModuleType('pkg_resources')
    fake_pr.working_set = []
    monkeypatch.setitem(sys.modules, 'pkg_resources', fake_pr)
    a = P._build_pkg_resources_index()
    b = P._build_pkg_resources_index()
    assert a is b


# ────────────────────────── _get_pkg_version_detail 全链路 ──────────────────────────

def _idx_with(names):
    """构造 {norm_name: (dist, version)} 形状的索引。

    空清单也要返回**非空** dict（加哨兵键）：产品代码 `if metadata_index:`
    对空 dict 走 legacy 逐名链路，而不是 vendor/legacy 索引分支 ——
    「索引存在但没命中」的契约必须构造 truthy 索引才能测到。
    """
    class _D:
        pass

    idx = {P._normalize_dist_name(n): (_D, v) for n, v in names}
    if not idx:
        idx['\x00sentinel-none'] = (_D, '0.0.0-sentinel')
    return idx


def test_detail_metadata_index_hit(monkeypatch):
    index = _idx_with([('zzz-fakepkg', '1.2.3')])
    # vendor / legacy 索引不应被走到（命中即返回）
    monkeypatch.setattr('vools.actus.probe.python_pkgs._build_vendor_index',
                        lambda: (_ for _ in ()).throw(AssertionError('should not run')))
    v, s = P._get_pkg_version_detail('zzz-fakepkg', 'zzz_fakepkg', index=index)
    assert v == '1.2.3'
    assert s is None


def test_detail_tries_import_name_when_dist_name_misses(monkeypatch):
    # Pillow/PIL 型：发行名不在索引、import 名在 → 命中
    index = _idx_with([('PIL', '9.0')])
    v, s = P._get_pkg_version_detail('Pillow', 'PIL', index=index)
    assert v == '9.0'
    assert s is None


def test_detail_vendor_fallback(monkeypatch):
    index = _idx_with([])
    monkeypatch.setattr('vools.actus.probe.python_pkgs._build_vendor_index',
                        lambda: {'pil': '8.8'})
    monkeypatch.setattr('vools.actus.probe.python_pkgs._has_legacy_eggs',
                        lambda: False)
    v, s = P._get_pkg_version_detail('Pillow', 'PIL', index=index)
    assert v == '8.8'
    assert s is None


def test_detail_pkg_resources_fallback_only_with_legacy_eggs(monkeypatch):
    index = _idx_with([])
    calls = []
    monkeypatch.setattr('vools.actus.probe.python_pkgs._build_vendor_index',
                        lambda: {})
    monkeypatch.setattr('vools.actus.probe.python_pkgs._has_legacy_eggs',
                        lambda: True)
    monkeypatch.setattr('vools.actus.probe.python_pkgs._build_pkg_resources_index',
                        lambda: calls.append(1) or {'pil': '7.7'})
    v, _ = P._get_pkg_version_detail('Pillow', 'PIL', index=index)
    assert v == '7.7'
    assert calls  # legacy egg 开关打开时才走 pkg_resources 索引


def test_detail_skips_pkg_resources_without_legacy_eggs(monkeypatch):
    index = _idx_with([])
    monkeypatch.setattr('vools.actus.probe.python_pkgs._build_vendor_index',
                        lambda: {})
    monkeypatch.setattr('vools.actus.probe.python_pkgs._has_legacy_eggs',
                        lambda: False)
    monkeypatch.setattr('vools.actus.probe.python_pkgs._build_pkg_resources_index',
                        lambda: (_ for _ in ()).throw(AssertionError('must not run')))
    import importlib as _il
    monkeypatch.setattr(_il, 'import_module',
                        lambda name: (_ for _ in ()).throw(ModuleNotFoundError(name)))
    v, s = P._get_pkg_version_detail('Pillow', 'PIL', index=index)
    assert v == ''
    assert s is None          # 没装：正常形态


def test_detail_metadata_error_signal_then_import_fallback(monkeypatch):
    # 索引命中但版本读挂 → signal 留痕，继续走 import 兜底
    class _BrokenDist:
        def __init__(self):
            pass

        def __getattr__(self, name):
            if name == 'version':
                raise RuntimeError('corrupt')
            raise AttributeError(name)

    index = {'pillow': (_BrokenDist(), None)}   # 索引键走 _normalize_dist_name('Pillow')
    monkeypatch.setattr('vools.actus.probe.python_pkgs._build_vendor_index',
                        lambda: {})
    monkeypatch.setattr('vools.actus.probe.python_pkgs._has_legacy_eggs',
                        lambda: False)
    fake_pil = types.ModuleType('PIL')
    fake_pil.__version__ = '6.6'
    import importlib as _il
    real_import_module = _il.import_module

    def _only_pil(name, *a, **kw):
        if name == 'PIL':
            return fake_pil
        return real_import_module(name, *a, **kw)

    monkeypatch.setattr(_il, 'import_module', _only_pil)
    v, s = P._get_pkg_version_detail('Pillow', 'PIL', index=index)
    assert v == '6.6'
    # 现状契约：import 兜底成功时返回硬编码 None，metadata_error 留痕被丢弃
    # （python_pkgs.py:432 `return ..., None`）——若视为缺陷应改产品在此处透传 signal，待裁决。
    assert s is None


def test_detail_no_index_falls_back_to_per_name_lookup(monkeypatch):
    # index=None 且 _build_metadata_index 返回 {} → 逐名链路
    monkeypatch.setattr('vools.actus.probe.python_pkgs._build_metadata_index',
                        lambda: {})
    fake_md = types.ModuleType('fake_metadata')
    fake_md.PackageNotFoundError = type('PNF', (Exception,), {})

    class _D:
        version = '4.4.4'

    fake_md.distribution = lambda name: _D()
    monkeypatch.setattr('vools.actus.probe.python_pkgs._load_metadata_module',
                        lambda: fake_md)
    v, s = P._get_pkg_version_detail('whatever', 'whatever')
    assert v == '4.4.4'
    assert s is None


def test_detail_no_index_per_name_metadata_error(monkeypatch):
    monkeypatch.setattr('vools.actus.probe.python_pkgs._build_metadata_index',
                        lambda: {})
    fake_md = types.ModuleType('fake_metadata')
    fake_md.PackageNotFoundError = type('PNF', (Exception,), {})

    def dist(name):
        raise ValueError('corrupt')

    fake_md.distribution = dist
    monkeypatch.setattr('vools.actus.probe.python_pkgs._load_metadata_module',
                        lambda: fake_md)
    import importlib as _il
    monkeypatch.setattr(_il, 'import_module',
                        lambda name: (_ for _ in ()).throw(ModuleNotFoundError(name)))
    v, s = P._get_pkg_version_detail('whatever', 'whatever')
    assert v == ''
    assert s == {'error_kind': 'metadata_error', 'error': 'ValueError'}


def test_detail_no_metadata_module_pkg_resources_path(monkeypatch):
    # _load_metadata_module 返回 None → 跳过逐名元数据，直接 pkg_resources
    monkeypatch.setattr('vools.actus.probe.python_pkgs._build_metadata_index',
                        lambda: {})
    monkeypatch.setattr('vools.actus.probe.python_pkgs._load_metadata_module',
                        lambda: None)
    fake_pr = types.ModuleType('pkg_resources')

    class _D:
        version = '5.5'

    fake_pr.get_distribution = lambda name: _D()
    monkeypatch.setitem(sys.modules, 'pkg_resources', fake_pr)
    v, s = P._get_pkg_version_detail('whatever', 'whatever')
    assert v == '5.5'
    assert s is None


def test_detail_pkg_resources_unavailable_signal(monkeypatch):
    monkeypatch.setattr('vools.actus.probe.python_pkgs._build_metadata_index',
                        lambda: {})
    monkeypatch.setattr('vools.actus.probe.python_pkgs._load_metadata_module',
                        lambda: None)

    def no_import(name, *a, **kw):
        raise ImportError(name)

    monkeypatch.setattr('builtins.__import__', no_import)
    v, s = P._get_pkg_version_detail('whatever', 'whatever')
    assert v == ''
    assert s == {'error_kind': 'metadata_unavailable', 'error': 'ImportError'}


def test_detail_import_fallback_without_version_attr(monkeypatch):
    # 元数据全空 + import 成功但无 __version__ → 'installed'（不是假阴性）
    monkeypatch.setattr('vools.actus.probe.python_pkgs._build_metadata_index',
                        lambda: {})
    fake = types.ModuleType('mystery')
    import importlib as _il
    monkeypatch.setattr(_il, 'import_module', lambda name: fake)
    v, s = P._get_pkg_version_detail('mystery', 'mystery')
    assert v == 'installed'
    assert s is None


def test_detail_import_fallback_empty_version_string(monkeypatch):
    monkeypatch.setattr('vools.actus.probe.python_pkgs._build_metadata_index',
                        lambda: {})
    fake = types.ModuleType('mystery')
    fake.__version__ = ''     # 空串 falsy → 'installed'
    import importlib as _il
    monkeypatch.setattr(_il, 'import_module', lambda name: fake)
    assert P._get_pkg_version_detail('mystery', 'mystery')[0] == 'installed'


def test_detail_import_error_signal(monkeypatch):
    monkeypatch.setattr('vools.actus.probe.python_pkgs._build_metadata_index',
                        lambda: {})
    import importlib as _il
    real_import_module = _il.import_module

    def broken(name, *a, **kw):
        if name == 'whatever':
            raise RuntimeError('boom')
        return real_import_module(name, *a, **kw)   # 其余放行：pkg_resources 自身导入要用

    monkeypatch.setattr(_il, 'import_module', broken)
    v, s = P._get_pkg_version_detail('whatever', 'whatever')
    assert v == ''
    assert s == {'error_kind': 'import_error', 'error': 'RuntimeError'}


def test_detail_module_not_found_is_not_error(monkeypatch):
    monkeypatch.setattr('vools.actus.probe.python_pkgs._build_metadata_index',
                        lambda: {})
    # 只挡 import_module 的目标名：全局 lambda 会连带打断 `import pkg_resources`
    # 内部（jaraco.text 资源加载）→ metadata_unavailable 假信号泄漏进 import 兜底
    import importlib as _il
    real_import_module = _il.import_module

    def _not_found_only(name, *a, **kw):
        if name == 'never_installed':
            raise ModuleNotFoundError(name)
        return real_import_module(name, *a, **kw)

    monkeypatch.setattr(_il, 'import_module', _not_found_only)
    v, s = P._get_pkg_version_detail('never-installed', 'never_installed')
    assert v == ''
    assert s is None


def test_get_pkg_version_compat_entry(monkeypatch):
    seen = {}

    def fake_detail(pkg, imp, index=None):
        seen['args'] = (pkg, imp, index)
        return '1.0', None

    monkeypatch.setattr('vools.actus.probe.python_pkgs._get_pkg_version_detail',
                        fake_detail)
    assert P._get_pkg_version('mypkg') == '1.0'
    assert seen['args'] == ('mypkg', 'mypkg', None)


def test_detail_dist_names_dedup(monkeypatch):
    # 发行名 == import 名时只查一次（不重复）
    recorded = []

    real_normalize = P._normalize_dist_name

    def spy(name):
        recorded.append(name)
        return real_normalize(name)

    monkeypatch.setattr('vools.actus.probe.python_pkgs._normalize_dist_name', spy)
    # 走索引路径（truthy 空索引 + 哨兵键）才能观察到 _normalize_dist_name；
    # 索引为空 dict 时产品走 legacy 逐名链路，不经过 normalize。
    sentinel = _idx_with([])
    monkeypatch.setattr('vools.actus.probe.python_pkgs._build_metadata_index',
                        lambda: sentinel)
    monkeypatch.setattr('vools.actus.probe.python_pkgs._build_vendor_index',
                        lambda: {})
    monkeypatch.setattr('vools.actus.probe.python_pkgs._has_legacy_eggs',
                        lambda: False)
    import importlib as _il
    real_import_module = _il.import_module

    # 去重契约的可观察面：import 兜底对同一 import 名只尝试一次
    # （dist_names=['same'] 只进一份，而不是 ['same','same'] 两份）。
    # 每个阶段各 normalize 一次是分阶段查找，不属于去重范畴。
    import_calls = []

    def _not_found_only(name, *a, **kw):
        if name == 'same':
            import_calls.append(name)
            raise ModuleNotFoundError(name)
        return real_import_module(name, *a, **kw)

    monkeypatch.setattr(_il, 'import_module', _not_found_only)
    P._get_pkg_version_detail('same', 'same', index=sentinel)
    assert import_calls == ['same']


# ────────────────────────── PythonPackagesProber.probe ──────────────────────────

def _fixed_detail(version_by_name):
    def _detail(package_name, import_name, index=None):
        v = version_by_name.get(package_name, '')
        return v, ({'error_kind': 'weird', 'error': 'X'} if v == '!sig' else None)
    return _detail


def test_probe_order_and_shape(small_table, monkeypatch):
    monkeypatch.setattr('vools.actus.probe.python_pkgs._get_pkg_version_detail',
                        _fixed_detail({'zzz-fakepkg': '1.0'}))
    monkeypatch.setattr('vools.actus.probe.python_pkgs._build_metadata_index',
                        lambda: {})
    items = P.PythonPackagesProber().probe()
    # 65 条 → 3 条小清单 + _summary
    assert [i.name for i in items] == ['zzz-fakepkg', 'Pillow', 'pytest', '_summary']
    assert all(i.category == 'python_packages' for i in items)
    assert items[0].available is True and items[0].version == '1.0'
    assert items[1].available is False and items[1].version == ''
    assert items[1].extra['is_optional'] is True
    st = items[-1].extra
    assert st['total_checked'] == 3
    assert st['installed'] == 1
    assert st['not_installed'] == 2
    assert 'budget_exceeded' not in st        # 没超预算时不写该键


def test_probe_signal_propagates_to_extra(small_table, monkeypatch):
    monkeypatch.setattr('vools.actus.probe.python_pkgs._get_pkg_version_detail',
                        _fixed_detail({'zzz-fakepkg': '!sig'}))
    monkeypatch.setattr('vools.actus.probe.python_pkgs._build_metadata_index',
                        lambda: {})
    items = P.PythonPackagesProber().probe()
    assert items[0].available is True
    assert items[0].extra['error_kind'] == 'weird'
    assert items[0].extra['error'] == 'X'


def test_probe_summary_counts_installed(small_table, monkeypatch):
    monkeypatch.setattr('vools.actus.probe.python_pkgs._get_pkg_version_detail',
                        _fixed_detail({'zzz-fakepkg': '1', 'Pillow': '2', 'pytest': '3'}))
    monkeypatch.setattr('vools.actus.probe.python_pkgs._build_metadata_index',
                        lambda: {})
    st = P.PythonPackagesProber().probe()[-1].extra
    assert (st['installed'], st['not_installed']) == (3, 0)


def test_probe_budget_exceeded_marks_items(small_table, monkeypatch):
    # _get_pkg_version_detail 卡住超过预算 → 那些包标 budget_exceeded，
    # 汇总带 budget_exceeded 计数，绝不静默少算
    monkeypatch.setattr('vools.actus.probe.python_pkgs._PKG_BUDGET_SEC', 0.05)

    def slow_detail(package_name, import_name, index=None):
        time.sleep(0.5)
        return '1.0', None

    monkeypatch.setattr('vools.actus.probe.python_pkgs._get_pkg_version_detail',
                        slow_detail)
    monkeypatch.setattr('vools.actus.probe.python_pkgs._build_metadata_index',
                        lambda: {})
    items = P.PythonPackagesProber().probe()
    names = [i.name for i in items]
    assert names[-1] == '_summary'
    exceeded = [i for i in items if i.extra.get('error_kind') == 'budget_exceeded']
    assert exceeded, '超预算的包必须被显式标记，不允许静默丢弃'
    assert all(i.available is False and i.version == '' for i in exceeded)
    st = items[-1].extra
    assert st['budget_exceeded'] == len(exceeded)
    assert st['total_checked'] == 3
    assert st['installed'] + st['not_installed'] + st['budget_exceeded'] == 3


def test_probe_metadata_index_built_once(small_table, monkeypatch):
    # 元数据索引在 probe() 入口只建一次并传给每个任务（而非每包重建）
    calls = []
    monkeypatch.setattr('vools.actus.probe.python_pkgs._build_metadata_index',
                        lambda: calls.append(1) or {})
    monkeypatch.setattr('vools.actus.probe.python_pkgs._get_pkg_version_detail',
                        _fixed_detail({}))
    P.PythonPackagesProber().probe()
    assert len(calls) == 1


def test_probe_passes_shared_index_to_detail(small_table, monkeypatch):
    seen = []
    marker = {'fake': 'index'}

    def spy_detail(package_name, import_name, index=None):
        seen.append(index)
        return '', None

    monkeypatch.setattr('vools.actus.probe.python_pkgs._get_pkg_version_detail',
                        spy_detail)
    monkeypatch.setattr('vools.actus.probe.python_pkgs._build_metadata_index',
                        lambda: marker)
    P.PythonPackagesProber().probe()
    assert seen and all(i is marker for i in seen)
