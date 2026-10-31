"""sigma.py 求值器核心契约测试（r93）。

覆盖：值语法 / 顶层切分 / 元算与矩阵 / 比较与成员 / 索引 /
33 个参考操作全矩阵 / eval_test 负向语义。全部通过公开入口 eval_expr
驱动，仅少量边界直接调纯函数。隔离零副作用。
"""
import _ai_local_bootstrap  # noqa: F401  必须先于 vools.actus 导入

import pytest

from vools.actus import sigma as sg

E = sg.eval_expr


# ── 值语法 ────────────────────────────────────────────────────────────────

def test_parse_val_scalars():
    assert sg.parse_val('5') == ('num', 5)
    assert sg.parse_val('-3') == ('num', -3)
    assert sg.parse_val('0.5') == ('fnum', 0.5)
    assert sg.parse_val('−2') == ('num', -2)          # unicode minus
    assert sg.parse_val('1e3') is None                 # 非法字面量
    assert sg.parse_val('+5') is None


def test_parse_val_lists_and_tuples():
    assert sg.parse_val('[1,2,3]') == ('list', [('num', 1), ('num', 2), ('num', 3)])
    v = sg.parse_val('[[1],[2]]')
    assert v[1][1][1][0] == ('num', 2)                # 二层嵌套
    assert sg.parse_val('(1,0)') == sg.parse_val('[1,0]')   # 元组同构
    assert sg.parse_val('[1,]') == ('list', [('num', 1)])   # 尾随逗号吞掉


def test_split_top_level():
    assert sg.split_top_level('a,b', ',') == ('a', 'b')
    assert sg.split_top_level('f(1,2),3', ',') == ('f(1,2)', '3')
    assert sg.split_top_level('no-sep', ',') is None
    # split_top_level 校验括号配对（split_all_top_level 不校验）
    assert sg.split_top_level('unbalanced(1,2', ',') is None


def test_split_all_top_level():
    assert sg.split_all_top_level('1,2,3', ',') == ['1', '2', '3']
    assert sg.split_all_top_level('f(1,2),g(3)', ',') == ['f(1,2)', 'g(3)']
    assert sg.split_all_top_level('unbalanced(1', ',') == ['unbalanced(1']


def test_fmt_val_roundtrip():
    for s in ('5', '0.5', '[1,2]', '[[1,2],[3,4]]'):
        v = sg.parse_val(s)
        assert sg.parse_val(sg.fmt_val(v)) == v


def test_fmt_val_kinds():
    assert sg.fmt_val(('num', 7)) == '7'
    assert sg.fmt_val(('fnum', 0.5)) == repr(0.5)
    assert sg.fmt_val(('list', [('num', 1), ('num', 2)])) == '[1,2]'


# ── 元算 / 矩阵 / 比较 ────────────────────────────────────────────────────

def test_elemwise_arith_scalars():
    assert sg.elemwise_add(('num', 2), ('num', 3)) == ('num', 5)
    assert sg.elemwise_add(('num', 2), ('fnum', 0.5)) == ('fnum', 2.5)
    assert sg.elemwise_sub(('num', 2), ('num', 5)) == ('num', -3)
    assert sg.elemwise_mul(('num', 3), ('num', 4)) == ('num', 12)


def test_elemwise_lists_and_errors():
    va = sg.parse_val('[1,2]')
    vb = sg.parse_val('[3,4]')
    assert sg.elemwise_add(va, vb) == sg.parse_val('[4,6]')
    assert sg.elemwise_sub(va, vb) == sg.parse_val('[-2,-2]')
    assert sg.elemwise_mul(va, vb) == sg.parse_val('[3,8]')
    assert sg.elemwise_div(va, vb) == \
        ('list', [('fnum', 1 / 3), ('fnum', 0.5)])     # 列表除法逐元素
    vc = sg.parse_val('[1]')
    assert sg.elemwise_add(va, vc) == 'ShapeError'
    assert sg.elemwise_add(('num', 1), va) == 'ShapeError'
    assert sg.elemwise_div(va, sg.parse_val('[0,2]')) == 'DivByZero'
    assert sg.elemwise_div(('num', 1), ('num', 0)) == 'DivByZero'
    assert sg.elemwise_div(('num', 7), ('num', 2)) == ('fnum', 3.5)
    assert sg.elemwise_div(('num', 6), ('num', 3)) == ('num', 2)


def test_mat_mul_shapes():
    a = sg.parse_val('[[1,2],[3,4]]')
    b = sg.parse_val('[5,6]')
    r = sg.mat_mul(a, b)
    assert r == sg.parse_val('[17,39]')
    assert sg.mat_mul(('num', 1), b) == 'ShapeError'
    bad_row = sg.parse_val('[[1,2],[3]]')
    assert sg.mat_mul(bad_row, b) == 'ShapeError'
    # 非数值单元 → TypeError（行长度必须先匹配列数，字面量语法无字符串）
    str_cell = ('list', [('list', [('str', 'x'), ('num', 1)])])
    assert sg.mat_mul(str_cell, b) == 'TypeError'
    # fnum 参与 → 整行 fnum
    f = sg.mat_mul(sg.parse_val('[[1.0,2]]'), b)
    assert f[1][0] == ('fnum', 17.0)


def test_value_eq_cmp_in():
    assert sg.value_eq(('num', 1), ('num', 1)) == ('num', 1)
    assert sg.value_eq(('num', 1), ('num', 2)) == ('num', 0)
    assert sg.value_eq(('num', 1), ('fnum', 1.0)) == 'TypeError'
    assert sg.value_eq(sg.parse_val('[1,[2]]'), sg.parse_val('[1,[2]]')) == ('num', 1)
    assert sg.value_eq(sg.parse_val('[1]'), sg.parse_val('[1,2]')) == ('num', 0)
    assert sg.value_cmp(('num', 3), ('num', 2), 'ge') == ('num', 1)
    assert sg.value_cmp(('num', 3), ('num', 2), 'le') == ('num', 0)
    assert sg.value_cmp(sg.parse_val('[1]'), ('num', 2), 'ge') == 'TypeError'
    assert sg.value_in(('num', 2), sg.parse_val('[1,2]')) == ('num', 1)
    assert sg.value_in(('num', 9), sg.parse_val('[1,2]')) == ('num', 0)
    assert sg.value_in(('num', 2), ('num', 2)) == 'TypeError'


def test_index_into_and_errors():
    assert sg.index_into(sg.parse_val('[7,8]'), ('num', 1)) == ('num', 8)
    nested = sg.parse_val('[[1,2],[3,4]]')
    assert sg.index_into(nested, sg.parse_val('[1,0]')) == ('num', 3)
    assert sg.index_into(nested, ('num', 5)) == 'OutOfBounds'
    assert sg.index_into(('num', 1), ('num', 0)) == 'TypeError'
    assert sg.collect_path(('num', 2)) == [2]
    assert sg.collect_path(sg.parse_val('[0,2]')) == [0, 2]
    assert sg.collect_path(('fnum', 1.0)) == []


def test_raise_error_unknown_name():
    with pytest.raises(ValueError):
        sg._raise_error('NoSuchErrorName')
    with pytest.raises(sg.IronLawViolation) as ei:
        sg._raise_error('BountyErr', 'neg')
    assert ei.value.name == 'BountyErr'
    assert ei.value.message == 'neg'


# ── eval_expr 基础 ────────────────────────────────────────────────────────

def test_eval_expr_constants_and_i2():
    assert E('0xK001') == ('fnum', 3.141592653589793)
    assert E('0xQ001') == ('num', 299792458)
    assert E('I₂') == sg.parse_val('[[1,0],[0,1]]')
    assert E('points_new()') == sg.parse_val('[0,0]')


def test_eval_expr_operators():
    assert E('2 ⊕ 3') == ('num', 5)
    assert E('[1,2] ⊕ [3,4]') == sg.parse_val('[4,6]')
    assert E('[[1,2]] ⊗ [5,6]') == sg.parse_val('[17]')
    assert E('7 ⊘ 2') == ('fnum', 3.5)
    assert E('6 ⊘ 0') == 'DivByZero'
    assert E('2 ⊙ 3') == ('num', 6)
    assert E('2 ⊖ 5') == ('num', -3)
    assert E('5 ≡ 5') == ('num', 1)
    assert E('5 ≥ 5') == ('num', 1)
    assert E('4 ≤ 5') == ('num', 1)
    assert E('2 ∈ [1,2]') == ('num', 1)
    assert E('2 ⊕ 3 ⊕ 4') == ('num', 9)          # 右结合链


def test_eval_expr_unparseable_and_shape_hint():
    assert E('1e3').startswith('unparseable')
    assert E('1 ⊕ [1] where shape mismatch') == 'ShapeError'


def test_eval_expr_index_and_bad_index():
    assert E('index([7,8],1)') == ('num', 8)
    assert E('index([7,8],x)').startswith('bad index')


# ── 参考操作全矩阵 ────────────────────────────────────────────────────────

def _row(a, b, c, d):
    return sg.fmt_val(sg.parse_val(f'[{a},{b},{c},{d}]'))


def test_op_task_create():
    assert E('task_create(3,4)') == sg.parse_val('[3,4,0,0]')
    assert E('task_create(3,-1)') == 'BountyErr'
    # sigma 字面量无字符串语法 → "x" 解析失败透传 unparseable
    assert E('task_create(3,"x")') == 'unparseable: "x"'
    assert E('task_create(1)').startswith('bad task_create args')
    assert E('task_create(zz,1)') == 'unparseable: zz'


def _open():
    return 'task_create(3,4)'


def test_op_accept_task_flow():
    t = E(_open())
    assert E(f'accept_task({sg.fmt_val(t)},5)') == sg.parse_val('[3,4,1,5]')
    inprog = sg.fmt_val(sg.parse_val('[3,4,1,5]'))
    assert E(f'accept_task({inprog},5)') == 'StateError'
    assert E('accept_task(7,5)') == 'TypeError'
    assert E('accept_task(1)').startswith('bad accept_task args')


def test_op_task_submit_and_accept():
    inprog = sg.fmt_val(sg.parse_val('[3,4,1,5]'))
    pend = E(f'task_submit({inprog})')
    assert pend == sg.parse_val('[3,4,2,5]')
    assert E(f'task_submit({sg.fmt_val(sg.parse_val("[3,4,0,0]"))})') == 'StateError'
    assert E('task_submit(7)') == 'TypeError'
    assert E('task_submit()') == 'unparseable: '   # 空实参整体求值失败
    # INV-4：仅作者（task[0]==3）可验收
    assert E(f'task_accept({sg.fmt_val(pend)},3)') == sg.parse_val('[3,4,3,5]')
    assert E(f'task_accept({sg.fmt_val(pend)},9)') == 'AuthError'
    assert E('task_accept(7,3)') == 'TypeError'
    assert E('task_accept(1)').startswith('bad task_accept args')


def test_op_review_merge():
    # 条目形状 = [id, vote, weight]（vote/weight 裸数值）
    votes = '[[[9],1,3],[[8],0,2]]'
    assert E(f'review_merge({votes})') == ('num', 1)
    votes_lo = '[[[9],1,1],[[8],0,3]]'
    assert E(f'review_merge({votes_lo})') == ('num', 0)
    assert E('review_merge([[[9],7,1]])') == 'TypeError'
    assert E('review_merge([[[9],1]])') == 'ShapeError'
    assert E('review_merge(7)') == 'TypeError'
    assert E('review_merge()') == 'unparseable: '    # 空实参整体求值


def test_op_contribution_score():
    assert E('contribution_score([[1,0,5],[2,0,7]])') == ('num', 12)
    assert E('contribution_score([[1,0,5]])') == ('num', 5)
    assert E('contribution_score([1])') == 'ShapeError'
    assert E('contribution_score(7)') == 'TypeError'


def test_op_credit_score():
    assert E('credit_score([[0,2]])') == ('num', 110)     # 100 + 5*2
    assert E('credit_score([[1,1]])') == ('num', 70)      # 100*7//10
    assert E('credit_score([[1,2]])') == ('num', 49)
    assert E('credit_score([[2,1]])') == 'TypeError'
    assert E('credit_score([[0]])') == 'ShapeError'
    assert E('credit_score(1)') == 'TypeError'


def test_op_portfolio_and_trades():
    assert E('portfolio_new(100)') == sg.parse_val('[100,0,0]')
    assert E('portfolio_new(-1)') == 'TypeError'
    assert E('portfolio_new("x")') == 'unparseable: "x"'
    assert E('buy(portfolio_new(100),0,30)') == sg.parse_val('[70,30,0]')
    assert E('buy(portfolio_new(10),0,30)') == 'InsufficientFunds'
    assert E('buy(portfolio_new(100),5,1)') == 'UnknownAsset'
    p = 'buy(portfolio_new(100),0,30)'
    assert E(f'sell({p},0,10)') == sg.parse_val('[80,20,0]')
    assert E(f'sell({p},1,1)') == 'InsufficientShares'
    assert E(f'portfolio_value({p})') == ('num', 100)
    assert E(f'risk_score({p})') == ('num', 30)
    assert E('portfolio_value(7)') == 'TypeError'
    assert E('buy(portfolio_new(100),0)').startswith('bad buy args')
    assert E('sell(portfolio_new(100),0)').startswith('bad sell args')


def test_op_quota_family():
    assert E('quota_new(10)') == sg.parse_val('[10,10]')
    assert E('quota_new(-1)') == 'TypeError'
    q = 'quota_use(quota_new(10),3)'
    assert E(q) == sg.parse_val('[10,7]')
    assert E('quota_use(quota_new(10),11)') == 'QuotaExhausted'
    assert E('quota_use(7,1)') == 'TypeError'
    assert E('quota_use(1)').startswith('bad quota_use args')
    assert E('quota_reset(quota_use(quota_new(10),9))') == sg.parse_val('[10,10]')
    assert E('quota_reset(7)') == 'TypeError'
    assert E('quota_advance(quota_new(10))') == sg.parse_val('[10,20]')
    assert E('quota_advance(7)') == 'TypeError'


def test_op_points_family():
    p = 'points_hold(points_new(),5)'
    assert E(p) == sg.parse_val('[5,0]')
    assert E('points_hold(points_new(),-1)') == sg.parse_val('[-1,0]')
    assert E('points_hold(7,1)') == 'TypeError'
    assert E('points_hold(1)').startswith('bad points_hold args')
    assert E(f'points_release({p},3)') == sg.parse_val('[2,3]')
    assert E(f'points_release({p},9)') == 'InsufficientEscrow'
    assert E('points_release(7,1)') == 'TypeError'
    assert E('points_release(1)').startswith('bad points_release args')
    ap = 'points_release(points_hold(points_new(),5),5)'
    assert E(f'points_withdraw({ap},5)') == sg.parse_val('[0,0]')
    assert E(f'points_withdraw({ap},9)') == 'InsufficientPoints'
    assert E('points_withdraw(1)').startswith('bad points_withdraw args')


def test_op_badge_family():
    assert E('badge_level(50)') == ('num', 0)
    assert E('badge_level(100)') == ('num', 1)
    assert E('badge_level(300)') == ('num', 2)
    assert E('badge_level(600)') == ('num', 3)
    assert E('badge_level("x")') == 'unparseable: "x"'
    assert E('badge_issue(1000,7,50)') == sg.parse_val('[1000,7,0]')
    assert E('badge_issue(999,7,50)') == 'AuthError'
    assert E('badge_issue(1000,7)').startswith('bad badge_issue args')


def test_op_dispute_and_team():
    assert E('dispute_review([[1,1,2],[2,0,1]])') == ('num', 1)
    assert E('dispute_review([[1,1,1],[2,0,3]])') == ('num', 0)
    assert E('dispute_review([[1,7,1]])') == 'TypeError'
    assert E('dispute_review([[1,1]])') == 'ShapeError'
    assert E('team_create(1,2,3)') == sg.parse_val('[1,2,1,3]')
    assert E('team_create(1,2,0)') == 'TypeError'
    assert E('team_create(1,2)').startswith('bad team_create args')
    t = 'team_create(1,2,3)'
    assert E(f'team_join({t},9)') == sg.parse_val('[1,2,2,3]')
    full = sg.fmt_val(sg.parse_val('[1,2,3,3]'))
    assert E(f'team_join({full},9)') == 'TeamFull'
    assert E('team_join(7,9)') == 'TypeError'
    assert E('team_join(1)').startswith('bad team_join args')
    assert E('team_share([[1,2],[3,6]],9)') == \
        sg.parse_val('[[1,2],[3,6]]')                  # (9*2)//8=2, (9*6)//8=6
    assert E('team_share([[1,0]],9)') == 'DivByZero'
    assert E('team_share([[1]],9)') == 'ShapeError'
    assert E('team_share(7,9)') == 'TypeError'
    assert E('team_share(1)').startswith('bad team_share args')


def test_op_ledger_and_inventory():
    assert E('points_ledger([[0,5,1],[1,3,2]])') == \
        sg.parse_val('[[1,1,5],[2,2,3]]')
    assert E('points_ledger([[0,5,0]])') == 'NotTraceable'
    assert E('points_ledger([[0,-1,1]])') == 'TypeError'
    assert E('points_ledger([[0,5]])') == 'ShapeError'
    assert E('points_ledger([["x",5,1]])') == 'unparseable: [["x",5,1]]'
    assert E('inventory_new(2,3)') == sg.parse_val('[2,3]')
    assert E('inventory_new(-1,3)') == 'TypeError'
    assert E('inventory_new(1)').startswith('bad inventory_new args')
    inv = 'inventory_new(2,3)'
    assert E(f'receive_stock({inv},0,5)') == sg.parse_val('[7,3]')
    assert E(f'ship_stock({inv},1,3)') == sg.parse_val('[2,0]')
    assert E(f'ship_stock({inv},1,9)') == 'InsufficientStock'
    assert E(f'receive_stock({inv},7,1)') == 'UnknownItem'
    assert E(f'receive_stock({inv},0,-1)') == 'TypeError'
    assert E('receive_stock(1,0,1)') == 'TypeError'    # 3 实参齐 → 库非列表
    assert E('ship_stock(1,0,1)') == 'TypeError'
    assert E(f'stock_level({inv},0)') == ('num', 2)
    assert E(f'stock_level({inv},9)') == 'TypeError'
    assert E('stock_level(1)').startswith('bad stock_level args')


def test_op_fill_rate():
    assert E('fill_rate(3,4)') == ('fnum', 0.75)
    assert E('fill_rate(3,0)') == 'DivByZero'
    assert E('fill_rate(1)').startswith('bad fill_rate args')
    assert E('fill_rate(3,"x")') == 'unparseable: "x"'


# ── eval_test / eval_compat_test ─────────────────────────────────────────

def test_eval_test_pass_and_fail():
    assert sg.eval_test('2 ⊕ 3', '5') is None
    assert sg.eval_test('[1] ⊕ [2]', '[1,2]') is not None
    assert sg.eval_test('6 ⊘ 0', '⊥DivByZero') is None
    assert sg.eval_test('2 ⊕ 3', '⊥X') is not None        # 期望错误但无错
    assert sg.eval_test('6 ⊘ 0', '⊥Other') is not None    # 错误名不匹配
    assert sg.eval_test('6 ⊘ 0', '5') is not None          # 求值错误但期望值
    assert sg.eval_test('2 ⊕ 3', 'bogus!!').startswith('unparseable expectation')


def test_eval_compat_test_true_or_detail():
    assert sg.eval_compat_test('2 ⊕ 3', '5') is True
    assert isinstance(sg.eval_compat_test('2 ⊕ 3', '6'), str)


# ── 规约结构与指纹 ────────────────────────────────────────────────────────

_SIGMA_MINI = '''# Module: mini
# Version: 1.0.0

## Operation: task_create (§T)

### Signature
task_create : num × num → task

### Laws
- ∀ w b . task_create(w, b) ≡ [w, b, 0, 0]

### Tests
| Input | Output |
|---|---|
| task_create(3,4) | [3,4,0,0] |

### Definition

```
task_create(w, b) = [w, b, 0, 0]
```
'''


def test_parse_module_text_mini():
    m = sg.parse_module_text(_SIGMA_MINI)
    assert m['name'] == 'mini'
    assert len(m['ops']) == 1
    op = m['ops'][0]
    assert op['name'] == 'task_create'
    assert op['fp'] is None                     # 无 Fingerprint 行 → 缺失指纹
    assert op['sig'].startswith('task_create')
    assert len(op['laws']) == 1 and len(op['tests']) == 1
    assert op['definition']                     # 定义体被收集


def test_fingerprint_of_stable():
    m1 = sg.parse_module_text(_SIGMA_MINI)
    m2 = sg.parse_module_text(_SIGMA_MINI)
    fp = sg.fingerprint_of(m1)
    assert fp == sg.fingerprint_of(m2) and fp       # 稳定且非空
    # 指纹跟随操作 Fingerprint 行（非模块名）
    mini_fp = _SIGMA_MINI.replace('### Signature',
                                  'Fingerprint: 0xA001\n\n### Signature')
    m3 = sg.parse_module_text(mini_fp)
    assert sg.fingerprint_of(m3) != fp


def test_fingerprint_of_spec():
    # 指纹跟随操作 fingerprint 字段（_module_from_spec:3040 取 op.get('fingerprint')；
    # 注意 spec 键名是 operations 不是 ops）
    base = {'name': 'a', 'kind': 'pure', 'params': [], 'returns': 'num'}
    spec = {'operations': [dict(base, fingerprint='0xA001')]}
    assert sg.fingerprint_of_spec(spec) == sg.fingerprint_of_spec(spec)
    spec2 = {'operations': [dict(base, fingerprint='0xA002')]}
    assert sg.fingerprint_of_spec(spec) != sg.fingerprint_of_spec(spec2)


def test_return_type_and_param_types():
    # 语义类语法用 Unicode 箭头（→），ASCII '->' 不参与切分
    assert sg.return_type('f : num → task') == 'task'
    assert sg.return_type('f : num') == 'f : num'      # 无箭头原样返回
    assert sg.return_type('') == 'Any'
    assert sg.param_types('f : num × task → num') == ['num', 'task']
    assert sg.param_types('f : num') == ['num']
    assert sg.param_types('no-colon') == []


def test_to_spec_json_and_law_helpers():
    m = sg.parse_module_text(_SIGMA_MINI)
    spec = sg.to_spec_json(m, spec_id='mini.spec')
    assert spec['version'] and spec['operations'][0]['name'] == 'task_create'
    assert sg._law_forall('∀ w b . P | guard') == ['w', 'b']
    assert sg._law_forall('∃ x . P') == []
    assert sg._law_predicate('∀ w b . P | guard') == 'P | guard'


def test_validate_spec_json_rejects_bad():
    good = sg.to_spec_json(sg.parse_module_text(_SIGMA_MINI))
    assert sg.validate_spec_json(good, strict=False) == []
    bad = {'spec_id': 'x', 'ops': 'not-a-list'}
    problems = sg.validate_spec_json(bad, strict=False)
    assert problems  # 结构问题被报出
