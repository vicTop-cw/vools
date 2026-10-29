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

    def test_levels_semantic(self):
        """第 20 轮（#15）：不抄常量元组，断言**等级语义**：
        非空、无重复、所有等级都有排序、且 `QUALITY_LEVELS` 的顺序 == 高→低。
        （原 `== ('platinum', ...)` 在合法重排/新增等级时红；行为坏了却未必红。）
        """
        from vools.actus import quality as q
        levels = q.QUALITY_LEVELS
        assert isinstance(levels, tuple) and levels, levels
        assert len(set(levels)) == len(levels), "等级不得重复: %r" % (levels,)
        ranks = [q._LEVEL_RANK[level] for level in levels]
        assert ranks == sorted(ranks, reverse=True), \
            "QUALITY_LEVELS 必须按质量高→低排列: %r" % (levels,)
        assert set(levels) == set(q._LEVEL_RANK), \
            "每个等级都必须有 rank（新增等级忘了登记会红）"
        assert q._LEVEL_RANK['platinum'] > q._LEVEL_RANK['bronze'] > q._LEVEL_RANK['internal'], \
            "platinum > bronze > internal 的等级序被破坏: %r" % (q._LEVEL_RANK,)


class TestIsMaintained:
    """维护活跃度测试"""

    def test_recent_file(self, tmp_path):
        f = tmp_path / 'recent.md'
        f.write_text('x')
        assert is_maintained(str(f), within_days=30) is True

    def test_within_days_boundary_both_sides(self, tmp_path, monkeypatch):
        """第 20 轮（#14）：30 天边界两侧 —— `<=` 写成 `<` 或方向写反必须红。

        原测试只有 now / 40 天（40 天足够远，`<=` vs `<`、甚至符号写反都可能绿）。
        这里 29 天（应 True）/ 31 天（应 False）夹住边界，并用**固定时钟**
        精确测正好 30 天（实现语义 `age_days <= within_days` ⇒ True）——
        不用真实时钟，避免"执行延迟让 30 天变成 30 天 + 1ms"的 flaky。
        """
        import types

        fixed_now = 1_000_000_000.0
        monkeypatch.setattr(quality, 'time', types.SimpleNamespace(time=lambda: fixed_now))

        def _touch(name, days_ago):
            path = tmp_path / name
            path.write_text('x')
            ts = fixed_now - days_ago * 86400.0
            os.utime(str(path), (ts, ts))
            return str(path)

        assert quality.is_maintained(_touch('d29.md', 29), within_days=30) is True
        assert quality.is_maintained(_touch('d31.md', 31), within_days=30) is False
        assert quality.is_maintained(_touch('d30.md', 30), within_days=30) is True

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
