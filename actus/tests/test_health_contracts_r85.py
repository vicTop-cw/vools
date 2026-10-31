# -*- coding: utf-8 -*-
"""health.py 契约测试（第 85 轮）——系统健康检查。

覆盖：HealthCheckResult/HealthReport（status_counts/overall/summary）、
全部 8 个检查函数的 ok/warn/error 分支、_core_module_dirs 双布局、
HealthChecker（run 异常收口/add_check/report_text）、run_health_check。

隔离：tmp repo + HOME；network 检查 patch urllib.request.urlopen（不真上网）。
"""
import _ai_local_bootstrap  # noqa: F401

import pytest

import vools.actus.health as hm
from vools.actus.health import (HealthCheckResult, HealthChecker,
                                HealthReport, check_actions_directory,
                                check_compilers, check_core_modules,
                                check_disk_space, check_meta_directory,
                                check_network, check_python_version,
                                check_vault, run_health_check)


@pytest.fixture
def world(tmp_path, monkeypatch):
    (tmp_path / 'actions').mkdir()
    (tmp_path / '_meta').mkdir()
    home = tmp_path / 'home'
    home.mkdir()
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setenv('USERPROFILE', str(home))
    monkeypatch.setenv('ACTUS_META_DIR', str(tmp_path / '_meta'))
    # 不真上网：把 urlopen 全局换成快速假响应（HealthChecker.run 含 network 检查）
    import urllib.request as _ur

    class _FastResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    monkeypatch.setattr(_ur, 'urlopen', lambda url, timeout: _FastResp())
    return tmp_path


# ═══════════════════════════════════════════════════════════════════
# 数据类
# ═══════════════════════════════════════════════════════════════════

class TestDataclasses:
    def test_result_defaults(self):
        r = HealthCheckResult('x', 'ok', 'msg')
        assert r.duration == 0.0 and r.suggestion == ''

    def test_status_counts_and_overall(self):
        rep = HealthReport(results=[
            HealthCheckResult('a', 'ok', ''), HealthCheckResult('a', 'ok', ''),
            HealthCheckResult('b', 'warn', ''), HealthCheckResult('c', 'error', '')])
        assert rep.status_counts == {'ok': 2, 'warn': 1, 'error': 1}
        assert rep.overall == 'error'

    def test_overall_warn(self):
        rep = HealthReport(results=[HealthCheckResult('a', 'warn', '')])
        assert rep.overall == 'warn'

    def test_overall_ok_and_summary(self):
        rep = HealthReport(results=[HealthCheckResult('a', 'ok', '')])
        assert rep.overall == 'ok'
        s = rep.summary()
        assert '1 通过' in s and '0 警告' in s

    def test_unknown_status_falls_in_counts(self):
        rep = HealthReport(results=[HealthCheckResult('a', '??', '')])
        assert rep.status_counts['??'] == 1
        assert rep.overall == 'ok'   # 未知状态不抬 overall


# ═══════════════════════════════════════════════════════════════════
# 检查函数
# ═══════════════════════════════════════════════════════════════════

class TestChecks:
    def test_python_version_ok(self):
        r = check_python_version()
        assert r.status == 'ok' and r.name == 'python_version'

    def test_python_version_error_branch(self, monkeypatch):
        import sys as _sys
        from collections import namedtuple
        _V = namedtuple('_V', 'major minor micro')
        monkeypatch.setattr(_sys, 'version_info', _V(3, 7, 9))
        r = check_python_version()
        assert r.status == 'error' and '3.8' in r.message

    def test_core_modules_package_layout_ok(self, world):
        r = check_core_modules(str(world))
        assert r.status == 'ok'
        assert '包 vools.actus' in r.message

    def test_core_modules_missing_in_pkg(self, world, monkeypatch):
        # 伪造包目录缺文件 → error（用 tmp 目录冒充 vools.actus.__file__）
        import vools.actus as pkg
        pkg_dir = world / 'fakepkg'
        pkg_dir.mkdir()
        monkeypatch.setattr(pkg, '__file__', str(pkg_dir / '__init__.py'))
        r = check_core_modules(str(world))
        assert r.status == 'error'
        assert '缺少核心模块' in r.message

    def test_core_modules_pkg_import_fail(self, world, monkeypatch):
        # 包布局 import 失败（95-97）→ 静默落 engine 候选 → 最终 error
        monkeypatch.setitem(__import__('sys').modules, 'vools.actus', None)
        r = check_core_modules(str(world))
        assert r.status == 'error' and '已查' in r.message

    def test_core_modules_engine_fallback(self, world, monkeypatch):
        # 包布局不可用 → engine/actuscore 兜底
        import vools.actus as pkg
        monkeypatch.setattr(pkg, '__file__', str(world / 'nope' / '__init__.py'))
        r = check_core_modules(str(world))
        assert r.status == 'error'   # engine 布局也不存在
        assert '已查' in r.message

    def test_actions_directory_missing_warns(self, tmp_path):
        (tmp_path / 'actions').unlink(missing_ok=True) if (tmp_path / 'actions').is_dir() else None
        r = check_actions_directory(str(tmp_path))
        assert r.status == 'warn' and 'scaffold' in r.suggestion

    def test_actions_directory_ok(self, world):
        r = check_actions_directory(str(world))
        assert r.status == 'ok' and '0 个动作文件' in r.message

    def test_compilers_full_matrix(self, monkeypatch):
        import shutil as sh
        monkeypatch.setattr(sh, 'which', lambda n: '/bin/' + n)
        r = check_compilers()
        assert r.status == 'ok'
        for name in ('python', 'node', 'rust', 'c', 'shell'):
            assert name in r.message

    def test_compilers_ok(self, monkeypatch):
        import shutil as sh
        monkeypatch.setattr(sh, 'which', lambda n: '/bin/' + n if n == 'python' else None)
        r = check_compilers()
        assert r.status == 'ok' and 'python' in r.message

    def test_compilers_none_warns(self, monkeypatch):
        import shutil as sh
        monkeypatch.setattr(sh, 'which', lambda n: None)
        r = check_compilers()
        assert r.status == 'warn'

    def test_disk_space_ok(self, world):
        r = check_disk_space(str(world))
        assert r.status in ('ok', 'warn')   # 取决于宿主盘余量

    def test_disk_space_tiny_threshold(self, world, monkeypatch):
        # <0.5GB → error
        fake = type('U', (), {'free': 0.4 * 1024 ** 3, 'total': 100, 'used': 1})()
        monkeypatch.setattr("vools.actus.health.shutil.disk_usage",
                            lambda p: fake)
        r = check_disk_space(str(world))
        assert r.status == 'error'

    def test_disk_space_low_warn(self, world, monkeypatch):
        fake = type('U', (), {'free': 1.2 * 1024 ** 3, 'total': 100, 'used': 1})()
        monkeypatch.setattr("vools.actus.health.shutil.disk_usage",
                            lambda p: fake)
        r = check_disk_space(str(world))
        assert r.status == 'warn'

    def test_disk_space_exception(self, world, monkeypatch):
        def boom(p):
            raise RuntimeError('disk boom')
        monkeypatch.setattr("vools.actus.health.shutil.disk_usage", boom)
        r = check_disk_space(str(world))
        assert r.status == 'warn' and 'disk boom' in r.message

    def test_network_ok(self, world, monkeypatch):
        import urllib.request as ur
        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        monkeypatch.setattr(ur, 'urlopen',
                            lambda url, timeout: FakeResp())
        r = hm.check_network()
        assert r.status == 'ok'

    def test_network_failure_warns(self, world, monkeypatch):
        import urllib.request as ur
        def boom(url, timeout):
            raise OSError('no net')
        monkeypatch.setattr(ur, 'urlopen', boom)
        r = hm.check_network()
        assert r.status == 'warn'

    def test_meta_directory_explicit_root(self, world):
        r = check_meta_directory(str(world))
        assert r.status == 'ok'

    def test_meta_directory_missing(self, world, monkeypatch):
        import shutil as sh
        sh.rmtree(world / '_meta')
        r = check_meta_directory(str(world))
        assert r.status == 'warn'
        (world / '_meta').mkdir()

    def test_meta_directory_default_root(self, world):
        # repo_root 缺省 → paths.meta_dir()（ACTUS_META_DIR）
        r = check_meta_directory()
        assert r.status == 'ok'

    def test_vault_available(self, world):
        r = check_vault(str(world))
        assert r.status == 'ok'

    def test_vault_both_import_fail(self, world, monkeypatch):
        monkeypatch.setitem(__import__('sys').modules, 'actuscore', None)
        monkeypatch.setitem(__import__('sys').modules, 'actuscore.vault', None)
        monkeypatch.setitem(__import__('sys').modules, 'vools.actus.vault', None)
        r = check_vault(str(world))
        assert r.status == 'warn'
        assert '不可用' in r.message

    def test_vault_generic_exception(self, world, monkeypatch):
        # __import__ 替身：actuscore.vault 抛非 ImportError → warn
        import builtins
        _real = builtins.__import__

        def fake_import(name, *a, **k):
            if name == 'actuscore.vault':
                raise RuntimeError('vault broken')
            return _real(name, *a, **k)
        monkeypatch.setattr(builtins, '__import__', fake_import)
        r = check_vault(str(world))
        assert r.status == 'warn' and '导入失败' in r.message


# ═══════════════════════════════════════════════════════════════════
# HealthChecker 运行器
# ═══════════════════════════════════════════════════════════════════

class TestHealthChecker:
    def test_run_all_checks(self, world):
        rep = HealthChecker(str(world)).run()
        assert len(rep.results) == 8
        assert rep.total_duration >= 0
        names = {r.name for r in rep.results}
        assert {'Python 版本', '核心模块', '动作目录', '元数据目录',
                '编译器', '磁盘空间', '网络', 'Vault'} <= names

    def test_run_captures_check_exception(self, world):
        c = HealthChecker(str(world))
        c.add_check('boom', lambda: 1 / 0)
        rep = c.run()
        last = rep.results[-1]
        assert last.name == 'boom' and last.status == 'error'
        assert '检查异常' in last.message

    def test_report_text_with_suggestion(self, world):
        rep = HealthReport(results=[
            HealthCheckResult('某检查', 'error', '坏了', 0.1, '做某事')])
        text = HealthChecker('.').report_text(rep)
        assert '❌' in text and '建议: 做某事' in text   # 覆盖 286

    def test_report_text(self, world):
        rep = HealthChecker(str(world)).run()
        text = c_report_text(rep)
        assert '健康报告' in text and '总体状态' in text
        assert '✅' in text or '⚠️' in text


def c_report_text(rep):
    return HealthChecker('.').report_text(rep)


def test_run_health_check_convenience(world):
    rep = run_health_check(str(world))
    assert isinstance(rep, HealthReport) and rep.results


def test_all_exports():
    assert 'HealthChecker' in hm.__all__ and 'run_health_check' in hm.__all__
