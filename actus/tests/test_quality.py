"""tests/actus/test_quality.py —— 质量分级计算测试。

覆盖：
  - quality_scale 分级判定（platinum/gold/silver/bronze）
  - 判据明细 evidence
  - is_maintained 维护活跃度
  - best-effort：数据源不可用降级 bronze
"""

import os
import time
import pytest

from vools.actus import quality
from vools.actus.quality import quality_scale, is_maintained, QUALITY_LEVELS


class _FakeAction:
    """最小 Action 替身（quality_scale 只读 id/path/meta）。"""

    def __init__(self, aid='a.b', path='/nonexistent/x.actus.md'):
        self.meta = {'id': aid}
        self.path = path


class TestQualityLevels:
    """等级集合测试"""

    def test_levels_closed(self):
        assert QUALITY_LEVELS == ('platinum', 'gold', 'silver', 'bronze', 'internal')


class TestIsMaintained:
    """维护活跃度测试"""

    def test_recent_file(self, tmp_path):
        f = tmp_path / 'recent.md'
        f.write_text('x')
        assert is_maintained(str(f), within_days=30) is True

    def test_old_file(self, tmp_path):
        f = tmp_path / 'old.md'
        f.write_text('x')
        old = time.time() - 40 * 86400
        os.utime(str(f), (old, old))
        assert is_maintained(str(f), within_days=30) is False

    def test_missing_file(self):
        assert is_maintained('/nonexistent/x.md') is False


class TestQualityScale:
    """分级判定测试"""

    def test_zero_execution_bronze(self, tmp_path):
        """零执行 → bronze（不虚报更高等级）"""
        action = _FakeAction(path=str(tmp_path / 'x.actus.md'))
        (tmp_path / 'x.actus.md').write_text('x')
        q = quality_scale(action, meta_dir=str(tmp_path / '_meta'))
        assert q['quality'] == 'bronze'
        assert q['evidence']['exec_count'] == 0

    def test_evidence_shape(self, tmp_path):
        action = _FakeAction(path=str(tmp_path / 'x.actus.md'))
        (tmp_path / 'x.actus.md').write_text('x')
        q = quality_scale(action, meta_dir=str(tmp_path / '_meta'))
        ev = q['evidence']
        for key in ('action_id', 'signed', 'has_omega_spec',
                    'exec_count', 'success_rate', 'maintained_30d'):
            assert key in ev

    def test_unsigned_low_execution_bronze(self, tmp_path):
        """未签名 + 少量执行 → bronze（silver 需签名）"""
        from vools.actus import calllog
        meta_dir = str(tmp_path / '_meta')
        for _ in range(5):
            calllog.write_action_metric('a.b', ok=True, runtime_ms=10,
                                        caller='t', meta_dir=meta_dir)
        action = _FakeAction(path=str(tmp_path / 'x.actus.md'))
        (tmp_path / 'x.actus.md').write_text('x')
        q = quality_scale(action, meta_dir=meta_dir)
        assert q['quality'] == 'bronze'  # 未签名无法到 silver

    def test_best_effort_no_crash(self, tmp_path):
        """所有数据源不可用也不抛（降级 bronze）"""
        action = _FakeAction(path='/nonexistent/x.actus.md')
        q = quality_scale(action, meta_dir=str(tmp_path / '_meta'))
        assert q['quality'] in QUALITY_LEVELS
