"""tests/actus/test_metrics_instrumentation.py —— executor 指标埋点集成测试。

覆盖 docs/03 §4.1 的最后一公里：executor.execute 执行后**必须**写
action_metrics（否则 popular/trending/quality 全是空转）。

反证：若埋点被删/改坏，本文件的用例立刻红——它直接查库，不 mock。
"""

import json
import os
import shutil
import sys
import textwrap

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402
_ai_local_bootstrap.install()

from vools.actus.calllog import aggregate_metrics, popular_actions
from vools.actus.executor import execute

_DIAG_ACTION = textwrap.dedent("""
    ```json #!cfg
    {
      "id": "diag.metrics", "name": "DiagMetrics", "version": "1.0.0",
      "trust": "sandbox", "platform": "desktop", "entry": "main",
      "description": "指标埋点诊断动作",
      "usage": "actus run diag.metrics",
      "args": {"type": "object", "properties": {"x": {"type": "string"}}}
    }
    ```

    ```python #!run tag=main
    import json, os
    def main(params):
        return {"status": "ok", "result": "diag-ok", "data": {"x": params.get("x")}}
    _p = json.loads(os.environ.get("ACTUS_PARAMS") or "{}")
    print(json.dumps(main(_p), ensure_ascii=False))
    ```
""")


@pytest.fixture
def diag_repo(tmp_path, monkeypatch):
    """隔离仓：一个合法 sandbox 动作 + 独立 _meta。"""
    actions_dir = tmp_path / 'actions'
    actions_dir.mkdir()
    (actions_dir / 'diag_metrics.actus.md').write_text(_DIAG_ACTION, encoding='utf-8')
    monkeypatch.setenv('ACTUS_REPO_ROOT', str(tmp_path))
    return tmp_path


def test_execute_writes_metric(diag_repo):
    """执行 1 次 → aggregate_metrics 立即可见（不 mock、直接查库）。"""
    meta_dir = str(diag_repo / '_meta')
    r = execute('diag.metrics', {'x': 'v'}, meta_dir=meta_dir)
    assert r['status'] == 'ok', r.get('error')

    agg = aggregate_metrics('diag.metrics', meta_dir=meta_dir)
    assert agg['total'] == 1
    assert agg['success_rate'] == 1.0
    assert agg['unique_callers'] == 1
    assert agg['avg_runtime_ms'] >= 0


def test_execute_failure_also_writes_metric(diag_repo):
    """失败执行也落指标（success_rate < 1）——否则质量分级只统计成功。"""
    meta_dir = str(diag_repo / '_meta')
    # 缺必填入参触发校验失败（args 未声明 required，用缺 platform 的动作不行——
    # 这里用一个必填缺失的方式：构造一个要求 x 的动作变体不可行，直接跑两次
    # 其中一次给非法类型触发 param_invalid）
    ok = execute('diag.metrics', {'x': 'v'}, meta_dir=meta_dir)
    bad = execute('diag.metrics', {'x': {'nested': 'obj'}}, meta_dir=meta_dir)
    assert ok['status'] == 'ok'
    assert bad['status'] == 'failed', bad.get('error')

    agg = aggregate_metrics('diag.metrics', meta_dir=meta_dir)
    assert agg['total'] == 2
    assert 0.0 < agg['success_rate'] < 1.0


def test_popular_actions_reflects_executions(diag_repo):
    """popular_actions 按执行计数排序（3 次 > 1 次）。"""
    meta_dir = str(diag_repo / '_meta')
    for _ in range(3):
        execute('diag.metrics', {'x': 'v'}, meta_dir=meta_dir)

    pop = popular_actions(limit=10, meta_dir=meta_dir)
    assert pop, 'popular_actions 空——埋点未生效'
    assert pop[0]['action_id'] == 'diag.metrics'
    assert pop[0]['count'] == 3


def test_quality_scale_reads_exec_count(diag_repo):
    """quality_scale 的 exec_count 来自真实执行（非 0）。"""
    from vools.actus.indexer import get_action
    from vools.actus.quality import quality_scale

    meta_dir = str(diag_repo / '_meta')
    for _ in range(2):
        execute('diag.metrics', {'x': 'v'}, meta_dir=meta_dir)

    action = get_action('diag.metrics')
    q = quality_scale(action, meta_dir=meta_dir)
    assert q['evidence']['exec_count'] == 2
    assert q['evidence']['success_rate'] == 1.0
    # 未签名 → 最高 bronze（silver 需签名）
    assert q['quality'] == 'bronze'


def test_metric_failure_does_not_break_execution(diag_repo, monkeypatch):
    """best-effort：写指标炸掉也不影响执行回执（calllog 设计原则）。"""
    meta_dir = str(diag_repo / '_meta')

    import vools.actus.calllog as calllog_mod
    monkeypatch.setattr(
        calllog_mod, 'write_action_metric',
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError('disk full')))

    r = execute('diag.metrics', {'x': 'v'}, meta_dir=meta_dir)
    assert r['status'] == 'ok'  # 回执不受指标写入失败影响
