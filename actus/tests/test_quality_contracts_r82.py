"""quality.py 契约测试（第 82 轮）——质量分级计算。

覆盖：is_maintained（OSError/TypeError 降级）、internal 短路（V-07）、
四级阶梯（platinum/gold/silver/bronze）、自指排除接线（V-08）、
_probe_signed/_probe_omega/_probe_metrics 降级路径、batch_quality。

隔离：ACTUS_META_DIR 指 tmp；指标行用真 calllog 写入；
_probe_signed/_probe_omega 用 monkeypatch 打桩（签名/spec 基建不在此测）。
"""
import os
import sys
import time

import pytest

import _ai_local_bootstrap  # noqa: F401

import vools.actus.quality as qm
from vools.actus.calllog import write_action_metric
from vools.actus.quality import QUALITY_LEVELS, batch_quality, is_maintained, quality_scale

import types


def _action(aid='demo.x', vis='', path=None):
    return types.SimpleNamespace(
        id=aid, path=path or '', meta={'id': aid, 'visibility': vis})


@pytest.fixture
def iso(tmp_path, monkeypatch):
    meta = tmp_path / 'meta'
    meta.mkdir()
    monkeypatch.setenv('ACTUS_META_DIR', str(meta))
    fresh = tmp_path / 'a.actus.md'
    fresh.write_text('x', encoding='utf-8')
    return {'meta_dir': str(meta), 'fresh': str(fresh), 'tmp': tmp_path}


def _fill_metrics(aid, meta_dir, total, ok):
    """写 total 行指标，其中 ok 行成功。"""
    for i in range(total):
        write_action_metric(aid, ok=(i < ok), runtime_ms=10, caller='user',
                            meta_dir=meta_dir)


# ═══════════════════════════════════════════════════════════════════
# is_maintained
# ═══════════════════════════════════════════════════════════════════

class TestIsMaintained:
    def test_fresh_file_true(self, iso):
        assert is_maintained(iso['fresh']) is True

    def test_none_falls_back_false(self):
        # V-09：TypeError 也要兜住（公开 API 容错承诺）
        assert is_maintained(None) is False

    def test_missing_file_false(self):
        assert is_maintained('Z:/no/such/file.actus.md') is False

    def test_old_file_false(self, iso):
        p = iso['tmp'] / 'old.actus.md'
        p.write_text('x', encoding='utf-8')
        old = time.time() - 60 * 86400
        os.utime(p, (old, old))
        assert is_maintained(str(p)) is False

    def test_within_days_zero(self, iso):
        # 0 天窗口：任何真实文件的 age>0 → False（边界不虚报）
        assert is_maintained(iso['fresh'], within_days=0) is False


# ═══════════════════════════════════════════════════════════════════
# quality_scale：internal 短路 + 四级阶梯
# ═══════════════════════════════════════════════════════════════════

class TestQualityLevels:
    def test_internal_short_circuit(self, iso):
        # V-07：visibility=internal 的引擎/系统动作直接短路
        r = quality_scale(_action(vis='internal'), meta_dir=iso['meta_dir'])
        assert r['quality'] == 'internal'
        assert r['evidence']['signed'] is None
        assert 'internal' in r['evidence']['reason']
        assert r['evidence']['exec_count'] is None

    def test_platinum(self, iso, monkeypatch):
        monkeypatch.setattr(qm, '_probe_signed', lambda a: True)
        monkeypatch.setattr(qm, '_probe_omega', lambda a: True)
        _fill_metrics('demo.x', iso['meta_dir'], 100, 99)
        r = quality_scale(_action(path=iso['fresh']), meta_dir=iso['meta_dir'],
                          signed=True)
        assert r['quality'] == 'platinum'
        assert r['evidence']['exec_count'] == 100
        assert r['evidence']['success_rate'] >= 0.99
        assert r['evidence']['maintained_30d'] is True

    def test_platinum_needs_maintained(self, iso, monkeypatch):
        # 100+/99% 但文件陈旧 → gold
        monkeypatch.setattr(qm, '_probe_signed', lambda a: True)
        monkeypatch.setattr(qm, '_probe_omega', lambda a: True)
        _fill_metrics('demo.x', iso['meta_dir'], 100, 100)
        old = iso['tmp'] / 'old.actus.md'
        old.write_text('x', encoding='utf-8')
        old_t = time.time() - 90 * 86400
        os.utime(old, (old_t, old_t))
        r = quality_scale(_action(path=str(old)), meta_dir=iso['meta_dir'],
                          signed=True)
        assert r['quality'] == 'gold'

    def test_gold(self, iso, monkeypatch):
        monkeypatch.setattr(qm, '_probe_signed', lambda a: True)
        monkeypatch.setattr(qm, '_probe_omega', lambda a: True)
        _fill_metrics('demo.x', iso['meta_dir'], 50, 48)   # 96%
        r = quality_scale(_action(path=iso['fresh']), meta_dir=iso['meta_dir'],
                          signed=True)
        assert r['quality'] == 'gold'

    def test_silver_without_omega(self, iso, monkeypatch):
        monkeypatch.setattr(qm, '_probe_signed', lambda a: True)
        monkeypatch.setattr(qm, '_probe_omega', lambda a: False)
        _fill_metrics('demo.x', iso['meta_dir'], 10, 9)    # 90%
        r = quality_scale(_action(path=iso['fresh']), meta_dir=iso['meta_dir'],
                          signed=True)
        assert r['quality'] == 'silver'

    def test_bronze_single_exec(self, iso):
        _fill_metrics('demo.x', iso['meta_dir'], 1, 1)
        r = quality_scale(_action(path=iso['fresh']), meta_dir=iso['meta_dir'],
                          signed=False)
        assert r['quality'] == 'bronze'

    def test_zero_exec_bronze_no_inflation(self, iso):
        r = quality_scale(_action(path=iso['fresh']), meta_dir=iso['meta_dir'],
                          signed=True)
        assert r['quality'] == 'bronze'   # 零执行不虚报

    def test_self_call_excluded(self, iso):
        # V-08：质量计算自身刷的指标（caller 命中 _SELF_TOOLS）不计入
        write_action_metric('demo.x', ok=True, runtime_ms=1,
                            caller='actus_quality', meta_dir=iso['meta_dir'])
        r = quality_scale(_action(path=iso['fresh']), meta_dir=iso['meta_dir'],
                          signed=True)
        assert r['evidence']['exec_count'] == 0

    def test_levels_closed_set(self):
        assert QUALITY_LEVELS == ('platinum', 'gold', 'silver', 'bronze',
                                  'internal')


# ═══════════════════════════════════════════════════════════════════
# 探针降级路径
# ═══════════════════════════════════════════════════════════════════

class TestProbes:
    def test_probe_signed_import_error(self, monkeypatch):
        monkeypatch.setitem(sys.modules, 'vools.actus.trust_model', None)
        assert qm._probe_signed(_action(path='x')) is False

    def test_probe_signed_empty_path(self):
        assert qm._probe_signed(_action(path='')) is False

    def test_probe_signed_missing_file(self):
        assert qm._probe_signed(_action(path='Z:/no/file.actus.md')) is False

    def test_probe_signed_verify_raises(self, iso, monkeypatch):
        from vools.actus import trust_model as tm
        def boom(p, *a, **k):
            raise RuntimeError('verify boom')
        monkeypatch.setattr(tm, 'verify_action', boom)
        assert qm._probe_signed(_action(path=iso['fresh'])) is False

    def test_probe_signed_error_status(self, iso, monkeypatch):
        from vools.actus import trust_model as tm
        monkeypatch.setattr(
            tm, 'verify_action', lambda p, *a, **k: {'status': 'error'})
        assert qm._probe_signed(_action(path=iso['fresh'])) is False

    def test_probe_signed_ok(self, iso, monkeypatch):
        from vools.actus import trust_model as tm
        monkeypatch.setattr(
            tm, 'verify_action', lambda p, *a, **k: {'status': 'ok'})
        assert qm._probe_signed(_action(path=iso['fresh'])) is True

    def test_probe_omega_empty_aid(self):
        assert qm._probe_omega(_action(aid='')) is False

    def test_probe_omega_exception_false(self, monkeypatch):
        from vools.actus import omega as om
        def boom(aid, root):
            raise RuntimeError('omega boom')
        monkeypatch.setattr(om, '_find_omega_spec', boom)
        assert qm._probe_omega(_action(aid='a.b')) is False

    def test_probe_metrics_empty_aid(self):
        assert qm._probe_metrics('') == {'total': 0, 'success_rate': 0.0}

    def test_probe_metrics_exception_zeros(self, monkeypatch):
        from vools.actus import calllog as C
        def boom(aid, **k):
            raise RuntimeError('agg boom')
        monkeypatch.setattr(C, 'aggregate_metrics', boom)
        assert qm._probe_metrics('a.b') == {'total': 0, 'success_rate': 0.0}

    def test_probe_metrics_real(self, iso):
        _fill_metrics('demo.x', iso['meta_dir'], 4, 3)
        m = qm._probe_metrics('demo.x', iso['meta_dir'])
        assert m['total'] == 4 and abs(m['success_rate'] - 0.75) < 0.001

    def test_lazy_signed_probe_in_quality_scale(self, iso, monkeypatch):
        # signed=None 时走 _probe_signed 惰性验证
        monkeypatch.setattr(qm, '_probe_signed', lambda a: True)
        monkeypatch.setattr(qm, '_probe_omega', lambda a: False)
        r = quality_scale(_action(path=iso['fresh']),
                          meta_dir=iso['meta_dir'], signed=None)
        assert r['evidence']['signed'] is True


# ═══════════════════════════════════════════════════════════════════
# batch_quality
# ═══════════════════════════════════════════════════════════════════

class TestBatchQuality:
    def test_batch(self, iso):
        acts = {'a': _action('a', path=iso['fresh']),
                'b': _action('b', vis='internal')}
        out = batch_quality(acts, meta_dir=iso['meta_dir'])
        assert set(out) == {'a', 'b'}
        assert out['b']['quality'] == 'internal'
        assert out['a']['quality'] == 'bronze'
