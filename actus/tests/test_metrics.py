"""tests/actus/test_metrics.py —— 使用量指标测试。

覆盖：
  - write_action_metric 落库
  - aggregate_metrics 聚合（total/last_7d/last_30d/success_rate/unique_callers）
  - popular_actions 排序
  - trending_actions 增长率
  - best-effort：坏输入不抛
"""

import os
import time
from datetime import datetime, timezone, timedelta

import pytest

from vools.actus import calllog


@pytest.fixture
def metrics_db(tmp_path):
    """隔离的指标库目录（每个测试独立）。"""
    return str(tmp_path / '_meta')


class TestWriteActionMetric:
    """write_action_metric 测试"""

    def test_write_and_aggregate(self, metrics_db):
        assert calllog.write_action_metric('a.b', ok=True, runtime_ms=100,
                                           caller='t1', meta_dir=metrics_db) is True
        agg = calllog.aggregate_metrics('a.b', meta_dir=metrics_db)
        assert agg['total'] == 1
        assert agg['success_rate'] == 1.0
        assert agg['avg_runtime_ms'] == 100
        assert agg['unique_callers'] == 1

    def test_empty_action_id_noop(self, metrics_db):
        assert calllog.write_action_metric('', meta_dir=metrics_db) is False

    def test_aggregate_unknown_action_zero(self, metrics_db):
        agg = calllog.aggregate_metrics('nope.nope', meta_dir=metrics_db)
        assert agg['total'] == 0
        assert agg['success_rate'] == 0.0

    def test_multiple_writes(self, metrics_db):
        for i in range(5):
            calllog.write_action_metric('a.b', ok=(i < 4), runtime_ms=10 * i,
                                        caller=f't{i}', meta_dir=metrics_db)
        agg = calllog.aggregate_metrics('a.b', meta_dir=metrics_db)
        assert agg['total'] == 5
        assert agg['success_rate'] == 0.8
        assert agg['unique_callers'] == 5
        assert agg['avg_runtime_ms'] == 20  # mean(0,10,20,30,40)


class TestPopularActions:
    """popular_actions 测试"""

    def test_ranking(self, metrics_db):
        for _ in range(10):
            calllog.write_action_metric('a.hot', meta_dir=metrics_db)
        for _ in range(3):
            calllog.write_action_metric('a.cold', meta_dir=metrics_db)
        pop = calllog.popular_actions(limit=10, meta_dir=metrics_db)
        assert pop[0]['action_id'] == 'a.hot'
        assert pop[0]['count'] == 10
        assert pop[-1]['action_id'] == 'a.cold'

    def test_empty(self, metrics_db):
        assert calllog.popular_actions(meta_dir=metrics_db) == []


class TestTrendingActions:
    """trending_actions 测试"""

    def test_growth(self, metrics_db):
        # a.hot 全部发生在最近 7 天；a.old 全部发生在 30 天前
        now = datetime.now(timezone(timedelta(hours=8)))
        db = calllog._metrics_connect(metrics_db)
        try:
            for _ in range(5):
                db.execute(
                    "INSERT INTO action_metrics (action_id, ts, caller, ok, runtime_ms) "
                    "VALUES (?, ?, ?, ?, ?)",
                    ('a.hot', (now - timedelta(days=3)).isoformat(), 't', 1, 10))
            for _ in range(30):
                db.execute(
                    "INSERT INTO action_metrics (action_id, ts, caller, ok, runtime_ms) "
                    "VALUES (?, ?, ?, ?, ?)",
                    ('a.old', (now - timedelta(days=25)).isoformat(), 't', 1, 10))
            db.commit()
        finally:
            db.close()
        trending = calllog.trending_actions(limit=10, meta_dir=metrics_db)
        assert trending
        assert trending[0]['action_id'] == 'a.hot'

    def test_empty(self, metrics_db):
        assert calllog.trending_actions(meta_dir=metrics_db) == []
