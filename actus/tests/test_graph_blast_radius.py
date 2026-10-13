"""actus/tests/test_graph_blast_radius.py — 依赖图问题不得连坐整个动作市场。

回归背景：
    旧 build_index 调 validate_graph（首条坏边即抛 ActionError），随后把
    **所有** entries 一律标 invalid。真实事故：一条
    ``actus.private.jump_all 依赖 actus.private.jump_push 不存在``
    让 111 个动作（含毫无关系的 vault.* / textstats / system.*）全部下架，
    AI 工具目录瞬间变空。

修复后 analyze_graph 只标记坏边属主（+环成员+其真实下游锥）。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 本地源码优先命名空间（必须先于 vools.actus）
_ai_local_bootstrap.install()

from vools.actus.model import Action
from vools.actus.validate import analyze_graph, validate_graph
from vools.actus.errors import ActionError


def _action(aid, deps=None):
    meta = {'id': aid, 'name': aid.split('.')[-1], 'version': '1.0.0',
            'trust': 'audit', 'entry': 'main', 'deps': list(deps or [])}
    return Action(meta=meta, path='actions/%s.actus.md' % aid,
                  sha256='x', raw='', body='')


def test_missing_dep_only_marks_owner_and_downstream_cone():
    a = _action('a')                 # 健康独立动作
    bad = _action('bad', deps=['ghost'])   # 依赖不存在
    child = _action('child', deps=['bad'])  # 依赖坏点
    grand = _action('grand', deps=['child'])
    unrelated = _action('unrelated', deps=['a'])

    issues = analyze_graph({'a': a, 'bad': bad, 'child': child,
                            'grand': grand, 'unrelated': unrelated})

    # 坏点 + 其下游锥被标记
    assert 'bad' in issues and issues['bad']['code'] == 'dependency_missing'
    assert 'child' in issues
    assert 'grand' in issues
    # 关键回归：无关动作绝不连坐
    assert 'a' not in issues
    assert 'unrelated' not in issues


def test_clean_graph_has_no_issues():
    a = _action('a')
    b = _action('b', deps=['a'])
    assert analyze_graph({'a': a, 'b': b}) == {}


def test_cycle_marks_only_cycle_members_and_cone():
    a = _action('a', deps=['b'])
    b = _action('b', deps=['a'])
    c = _action('c', deps=['a'])
    z = _action('z')
    issues = analyze_graph({'a': a, 'b': b, 'c': c, 'z': z})
    assert issues['a']['code'] == 'dependency_cycle'
    assert issues['b']['code'] == 'dependency_cycle'
    assert 'c' in issues   # 依赖了环，传播锥
    assert 'z' not in issues


def test_validate_graph_still_raises_for_backward_compat():
    # 旧的抛异常接口保持不变（executor/scattered 仍在用）
    with pytest.raises(ActionError) as ei:
        validate_graph({'bad': _action('bad', deps=['ghost'])})
    assert ei.value.code == 'dependency_missing'
