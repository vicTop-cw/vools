"""sigma.py r94 求值器与门禁契约测试（补覆盖率 77% → ≥85%）。

退步会怎样：本文件的每条断言都钉住一个**可观察契约**——
  * 求值错误名（'ShapeError'/'TypeError'/'StateError'/…）漂移 → 同一规约在
    actus / sigma-lang 两端共识判定不一致，跨端验收假阴/假阳；
  * 参考操作的实参元数守卫、类型守卫或字符串传播丢失 → 非法输入被静默算成
    垃圾值而非命名错误，规约测试里的 ⊥ 分支失效；
  * spec JSON 往返丢字段（# Pre:/# Post:/meta）→ judge 恒 WA、bootstrap
    假阴性，spec_readable 与 spec_json_valid 两道门互相矛盾；
  * 引擎表驱动转移（kind=table）行序/守卫/set 语义漂移 → 状态机规约可被
    任意改写而不被察觉；
  * Iron Laws 补充细则（Proof/Determinism/Signature/Guarantee…）漏检 →
    残缺规约（无 Model/无负例/版本非语义化）真空通过门禁。
全部通过公开入口（eval_expr / SigmaEngine / judge_spec / bootstrap /
run_sigma_block）或纯函数直接驱动；零产品代码改动、零全局副作用，
每条断言在契约被破坏时都会变红。
"""

import json

import _ai_local_bootstrap  # noqa: F401
import pytest

from vools.actus import sigma as sg

E = sg.eval_expr


# ---------------------------------------------------------------------------
# 1. 值算术：elemwise / mat_mul / value_eq / value_cmp / value_in 错误传播分支
# ---------------------------------------------------------------------------

def test_elemwise_deep_error_propagation():
    v13 = sg.parse_val('[[1,2]]')
    v1 = sg.parse_val('[[1]]')
    assert sg.elemwise_add(v13, v1) == 'ShapeError'                          # 296
    assert sg.elemwise_sub(('num', 2), ('fnum', 0.5)) == ('fnum', 1.5)       # 306
    assert sg.elemwise_sub(sg.parse_val('[1]'), sg.parse_val('[1,2]')) == 'ShapeError'   # 309
    assert sg.elemwise_sub(v13, v1) == 'ShapeError'                          # 314
    assert sg.elemwise_sub(('num', 1), sg.parse_val('[1]')) == 'ShapeError'  # 317
    assert sg.elemwise_mul(('fnum', 1.5), ('num', 2)) == ('fnum', 3.0)       # 325
    assert sg.elemwise_mul(sg.parse_val('[1]'), sg.parse_val('[1,2]')) == 'ShapeError'   # 328
    assert sg.elemwise_mul(v13, v1) == 'ShapeError'                          # 333
    assert sg.elemwise_mul(('num', 1), sg.parse_val('[1]')) == 'ShapeError'  # 336
    assert sg.elemwise_div(('fnum', 1.0), ('fnum', 0.0)) == 'DivByZero'      # 349
    assert sg.elemwise_div(sg.parse_val('[1]'), sg.parse_val('[1,2]')) == 'ShapeError'   # 353
    assert sg.elemwise_div(('num', 1), sg.parse_val('[1]')) == 'ShapeError'  # 361


def test_mat_mul_row_shape_contract():
    assert sg.mat_mul(sg.parse_val('[1,2]'), sg.parse_val('[5,6]')) == 'ShapeError'  # 370


def test_value_predicate_type_contracts():
    assert sg.value_eq(('list', [('num', 1)]), ('list', [('str', 'x')])) == 'TypeError'  # 397
    assert sg.value_eq(sg.parse_val('[1,2]'), sg.parse_val('[1,3]')) == ('num', 0)       # 399
    assert sg.value_eq(('str', 'a'), ('str', 'b')) == 'TypeError'                        # 403
    assert sg.value_cmp(('str', 'a'), ('num', 1), 'ge') == 'TypeError'                   # 411
    assert sg.value_in(('str', 'a'), ('list', [('num', 1)])) == 'TypeError'              # 425


# ---------------------------------------------------------------------------
# 2. 参数元数辅助与标量判定（eval_expr 走 _REF_MIN_ARGS，这些直接驱动）
# ---------------------------------------------------------------------------

def test_args_n_helpers():
    assert sg._args2('f(1)', 'f') is None                        # 469-471
    assert sg._args2('f(1,2)', 'f') == ['1', '2']                # 472
    assert sg._args2('g(1,2)', 'f') is None
    assert sg._args3('f(1,2)', 'f') is None                      # 476-478
    assert sg._args3('f(1,2,3)', 'f') == ['1', '2', '3']         # 479
    assert sg._scalar(('num', 1)) and sg._scalar(('fnum', 1.0))  # 491
    assert not sg._scalar(('list', []))
    assert not sg._scalar('x')


# ---------------------------------------------------------------------------
# 3. 参考操作：元数守卫 / 类型守卫 / 字符串传播 / 状态机命名错误
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('handler,args,name', [
    (sg._op_task_create, ['1'], 'task_create'),
    (sg._op_accept_task, ['1'], 'accept_task'),
    (sg._op_task_submit, [], 'task_submit'),
    (sg._op_task_accept, ['1'], 'task_accept'),
    (sg._op_quota_use, ['1'], 'quota_use'),
    (sg._op_points_hold, ['1'], 'points_hold'),
    (sg._op_points_release, ['1'], 'points_release'),
    (sg._op_points_withdraw, ['1'], 'points_withdraw'),
    (sg._op_badge_issue, ['1', '2'], 'badge_issue'),
    (sg._op_team_create, ['1', '2'], 'team_create'),
    (sg._op_team_join, ['1'], 'team_join'),
    (sg._op_team_share, ['1'], 'team_share'),
    (sg._op_inventory_new, ['1'], 'inventory_new'),
    (sg._op_stock_level, ['1'], 'stock_level'),
    (sg._op_fill_rate, ['1'], 'fill_rate'),
])
def test_ref_op_argc_guards(handler, args, name):
    assert str(handler(sg.eval_expr, args)).startswith(f'bad {name} args')


def test_ref_op_argc_guards_dual_mode():
    # 买/卖与收/发共用同一个处理器，靠第三个布尔参分流
    assert str(sg._portfolio_trade(sg.eval_expr, ['1', '2'], True)).startswith('bad buy args')
    assert str(sg._portfolio_trade(sg.eval_expr, ['1', '2'], False)).startswith('bad sell args')
    assert str(sg._stock_change(sg.eval_expr, ['1', '2'], True)).startswith('bad receive_stock args')
    assert str(sg._stock_change(sg.eval_expr, ['1', '2'], False)).startswith('bad ship_stock args')


@pytest.mark.parametrize('expr', [
    'accept_task(zz,5)', 'accept_task([3,4,0,0],zz)',
    'task_accept(zz,3)', 'task_accept([3,4,2,5],zz)',
    'contribution_score(zz)', 'credit_score(zz)',
    'buy(zz,1,2)', 'portfolio_value(zz)', 'risk_score(zz)',
    'quota_new(zz)', 'quota_use(zz,1)', 'quota_use([5,5],zz)',
    'quota_reset(zz)', 'quota_advance(zz)',
    'points_hold(zz,1)', 'points_hold([0,5],zz)',
    'points_release(zz,1)', 'points_release([0,5],zz)',
    'points_withdraw(zz,1)', 'points_withdraw([0,5],zz)',
    'badge_issue(zz,5,100)',
    'dispute_review(zz)', 'team_create(zz,1,2)',
    'team_join(zz,1)', 'team_join([9,1,1,2],zz)',
    'team_share(zz,10)', 'team_share([[1,5]],zz)',
    'inventory_new(zz,1)', 'inventory_new(1,zz)',
    'receive_stock(zz,0,1)', 'ship_stock([1,2],zz,1)',
    'stock_level(zz,0)', 'stock_level([1,2],zz)',
    'fill_rate(zz,1)',
])
def test_ref_op_str_propagation(expr):
    assert E(expr) == 'unparseable: zz'


@pytest.mark.parametrize('expr', [
    'task_create(0.5,1)',
    'portfolio_new([1])',
    'buy([10,0,0],[1],2)',
    'quota_new([1])',
    'quota_advance([0.5,3])',
    'points_withdraw([0,5],[1])',
    'badge_level([1])',
    'badge_issue([1],5,100)',
    'dispute_review(7)',
    'team_create([1],1,2)',
    'points_ledger(7)',
    'points_ledger([[1.5,1,1]])',
    'inventory_new([1],1)',
    'stock_level([1,2],[0])',
    'fill_rate([1],1)',
])
def test_ref_op_type_guards(expr):
    assert E(expr) == 'TypeError'


def test_ref_op_named_contracts():
    assert E('buy([10,0,0],1,5)') == sg.parse_val('[5,0,5]')    # 现金买资产 1
    assert E('sell([10,0,5],1,3)') == sg.parse_val('[13,0,2]')  # 卖资产 1
    assert E('task_accept([3,4,1,5],3)') == 'StateError'        # 状态机守卫


def test_eval_expr_operator_str_propagation():
    assert E('zz ⊕ 3') == 'unparseable: zz'   # 1053
    assert E('3 ⊕ zz') == 'unparseable: zz'   # 1055


# ---------------------------------------------------------------------------
# 4. parse_module_text 章节标志 / 围栏内小节 / Pre-Post / 解析边界
# ---------------------------------------------------------------------------

_FLAGS_MD = '''# Module: flagsmod
# Version: 1.0.0
# Style: minimal
# Maintainer: r94

## Timing
max_latency: 5s

## Capabilities
Net, IO

## Shadowing
shadow ghostfn

## Signature
signer: alice
pubkey_fp: sha256:deadbeef
algorithm: ed25519
signature: c2ln

## Determinism
precision: 6
rounding: round
sort_stability: true

## Guarantee
metric: accuracy
threshold: 0.9
dataset: ds1

## Proof
prose here
### Trusted
### Model
m: formal
### Invariant
inv: true

## Compat Tests
prose line
| 2 ⊕ 2 | 4 |

## Operation: idty
Fingerprint: 0xE001
idty : ℕ → ℕ
# Pre: a ≥ 0
# Post: a ≥ 0

### Laws
∀a . idty(a) ≡ a

### Tests
| 5 | 5 |
| 0 ⊘ 0 | ⊥ DivByZero |
| 1, 2 | 3 |

### Definition
arg0
'''


_GOOD_MD = '''# Module: goodmod
# Version: 1.0.0

## Imports
import core

## Exports
idty

## Operation: idty
Fingerprint: 0xD001
idty : ℕ → ℕ

### Laws
∀a . idty(a) ≡ a

### Tests
| 5 | 5 |
| 0 ⊘ 0 | ⊥ DivByZero |

### Definition
arg0
'''


def test_parse_module_text_section_flags():
    m = sg.parse_module_text(_FLAGS_MD)
    assert m['timing_contract'] == {'max_latency': '5s'}
    assert m['capabilities'] == ['Net', 'IO']
    assert m['shadow_targets'] == ['ghostfn']
    assert m['signature_signer'] == 'alice'
    assert m['signature_pubkey_fp'] == 'sha256:deadbeef'
    assert m['signature_algorithm'] == 'ed25519'
    assert m['signature_value'] == 'c2ln'
    assert m['determinism_precision'] == '6'
    assert m['determinism_rounding'] == 'round'
    assert m['determinism_sort_stability'] == 'true'
    assert m['guarantee_metric'] == 'accuracy'
    assert m['guarantee_threshold'] == '0.9'
    assert m['guarantee_dataset'] == 'ds1'
    assert m['proof_has_model'] and m['proof_has_invariant']
    assert m['compat_tests'] == [('2 ⊕ 2', '4')]
    op = m['ops'][0]
    assert op['has_pre'] and op['has_post']
    assert op['pre'] == 'a ≥ 0' and op['post'] == 'a ≥ 0'


def test_to_spec_json_pre_post_and_meta():
    m = sg.parse_module_text(_FLAGS_MD)
    spec = sg.to_spec_json(m)
    op = spec['operations'][0]
    assert op['preconditions'][0]['error'] == 'DivByZero'   # _pre_error 取 ⊥ 测试名
    assert op['postcondition'] == 'a ≥ 0'
    assert spec['meta']['timing_contract'] == {'max_latency': '5s'}
    assert spec['meta']['capabilities'] == ['Net', 'IO']
    assert spec['guarantee'] == {'metric': 'accuracy', 'threshold': '0.9', 'dataset': 'ds1'}
    # 逗号输入拆分：'1, 2' → ['1', '2']
    inputs = [t['input'] for t in op['tests']]
    assert [1, 2] in inputs
    assert sg._pre_error({'pre': 'x', 'tests': [('1', '1')]}) == 'TypeError'


def test_parse_module_text_fenced_subsections():
    text = '''# Module: fenced
# Version: 1.0.0

## Operation: idty
Fingerprint: 0xE002
idty : ℕ → ℕ

```
## Laws
∀a . idty(a) ≡ a
## Tests
| 5 | 5 |
| 0 ⊘ 0 | ⊥ DivByZero |
## Definition
arg0
```
'''
    m = sg.parse_module_text(text)
    op = m['ops'][0]
    assert op['laws'] == ['∀a . idty(a) ≡ a']
    assert op['tests'] == [('5', '5'), ('0 ⊘ 0', '⊥ DivByZero')]
    assert op['definition'] == ['arg0']


def test_parse_module_oserror(tmp_path):
    with pytest.raises(sg.SpecError, match='无法读取'):
        sg.parse_module(str(tmp_path / 'missing.md'))


def test_scan_fenced_unclosed_and_empty():
    assert sg._scan_fenced('```sigma\nhello\n', False) == 'hello'
    assert sg._scan_fenced('no fence at all', False) == ''


def test_extract_sigma_block_wide_fallback():
    text = '```sigma\n## Operation: a\n```\nskip\n## Operation: b\nFingerprint: 0xA002\nb : ℕ → ℕ\n```\n'
    body = sg.extract_sigma_block(text)
    assert 'Fingerprint: 0xA002' in body
    assert sg.extract_sigma_block('no fences here') == ''


def test_parse_package(tmp_path):
    p = tmp_path / 'pkg.md'
    p.write_text('# Package: std-core\n# Version: 0.2.0\n# Depends: core\n'
                 '# Fingerprint Prefix: 0xA\n# Domain: math\n# Maintainer: someone\n'
                 '# License: MIT\nplain stop line\n# Module: whatever\n', encoding='utf-8')
    meta = sg.parse_package(str(p))
    assert meta['package'] == 'std-core'
    assert meta['version'] == '0.2.0'
    assert meta['depends'] == 'core'
    assert meta['fingerprint_prefix'] == '0xA'
    assert meta['domain'] == 'math'
    assert meta['maintainer'] == 'someone'
    assert meta['license'] == 'MIT'
    assert sg.parse_package(str(tmp_path / 'nope.md')) is None


# ---------------------------------------------------------------------------
# 5. Iron Laws 补充细则
# ---------------------------------------------------------------------------

def _op(name, fp='0xA001', sig='f : ℕ → ℕ', laws=None, tests=None,
        definition=None, has_pre=False, has_post=False):
    return {'name': name, 'fp': fp, 'sig': sig,
            'laws': laws if laws is not None else ['∀a . a ≡ a'],
            'tests': tests if tests is not None else [('1', '1')],
            'mode': 'sig', 'has_pre': has_pre, 'has_post': has_post,
            'pre': None, 'post': None, 'definition': definition or []}


def test_check_fingerprint_uniqueness():
    out = sg.check_fingerprint_uniqueness({'ops': [_op('a'), _op('b')]})
    assert out == ['FingerprintConflict(b, 0xA001)']


def test_check_encoding_requires_real_encoder():
    m = {'fns': [{'name': 'encode_x', 'sig': '', 'fp': '0xA001', 'definition': []}],
         'ops': [_op('f', sig='f : ℕ → Str')]}
    assert sg.check_encoding(m) == ['MissingEncoding(f)']
    m2 = {'fns': [{'name': 'encode_x', 'sig': 'encode : Str → ℕ', 'fp': '0xA001',
                   'definition': []}],
          'ops': [_op('f', sig='f : ℕ → Str')]}
    assert sg.check_encoding(m2) == []
    assert sg._signature_encodes('', 'Str') is False
    assert sg._signature_encodes('f : Str → Str', 'Str') is False
    assert sg._signature_encodes('encode : Str → ℕ', 'Str') is True


def test_check_dependencies_self_and_duplicate():
    out = sg.check_dependencies({'name': 'm', 'imports': ['core', 'm', 'dep', 'dep']})
    assert 'SelfDependency(m)' in out
    assert 'DuplicateImport(dep)' in out


def test_check_resource_linearity_branches():
    leak = sg.check_resource_linearity({'ops': [_op('a', definition=['open(fd)'])]})
    assert leak == ['ResourceLeak(a:fd)']
    double = sg.check_resource_linearity(
        {'ops': [_op('a', definition=['x = close(fd) use(fd) close(fd)'])]})
    assert 'DoubleClose(a:fd)' in double
    assert 'UseAfterClose(a:fd)' in double
    ok = sg.check_resource_linearity({'ops': [_op('a', definition=['open(fd) close(fd)'])]})
    assert ok == []


def test_check_guarantee_malformed():
    m = {'guarantee_declared': True, 'guarantee_metric': 'accuracy',
         'guarantee_threshold': '2.0', 'guarantee_dataset': ''}
    out = sg.check_guarantee(m)
    assert 'MalformedGuarantee(threshold out of range 0..=1)' in out
    assert 'MalformedGuarantee(missing dataset)' in out
    out2 = sg.check_guarantee(dict(m, guarantee_threshold='abc', guarantee_dataset='ds'))
    assert 'MalformedGuarantee(threshold not a number)' in out2
    assert 'MalformedGuarantee(missing dataset)' not in out2
    assert sg.check_guarantee({'guarantee_declared': False}) == []


def test_check_shadowing_discipline_branches():
    m = {'ops': [_op('dup'), _op('dup')],
         'shadow_targets': ['⊕', 'ghost', 'pkg.alias']}
    out = sg.check_shadowing_discipline(m)
    assert 'DuplicateSymbol(dup)' in out
    assert 'OpaqueShadowAttempt(⊕)' in out
    assert 'ShadowTargetMissing(ghost)' in out
    assert not any('pkg.alias' in v for v in out)   # 带点的模块别名豁免


def test_check_proof_structure_missing_parts():
    m = {'name': 'm', 'proof_declared': True, 'proof_has_model': False,
         'proof_has_invariant': False,
         'ops': [_op('a', has_pre=True, has_post=False)]}
    out = sg.check_proof_structure(m)
    assert 'MissingModel(m)' in out
    assert 'MissingInvariant(m)' in out
    assert 'IncompleteContract(a)' in out
    assert sg.check_proof_structure({'proof_declared': False, 'ops': []}) == []


def test_check_portability_and_consistency():
    bad = _op('a', sig='a : ℕ → ℕ', tests=[('1', 'bogus!!'), ('1', '[1]')])
    assert sg.check_test_portability({'ops': [bad]}) == ['UnportableAssertion(a, bogus!!)']
    out = sg.check_internal_consistency({'ops': [bad]})
    assert out == ['SignatureMismatch(a, [1])']   # ℕ 返回类型配列表期望


def test_check_eval_determinism_malformed():
    base = {'determinism_declared': True, 'determinism_rounding': 'bankers',
            'determinism_sort_stability': 'maybe'}
    out = sg.check_eval_determinism(dict(base, determinism_precision='abc'))
    assert sum(v.startswith('MalformedDeterminism') for v in out) == 3
    out2 = sg.check_eval_determinism(dict(base, determinism_precision='0',
                                          determinism_rounding='round',
                                          determinism_sort_stability='true'))
    assert len(out2) == 1 and 'invalid precision' in out2[0]
    assert sg.check_eval_determinism({'determinism_declared': False}) == []


def test_check_package_signature_malformed():
    out = sg.check_package_signature({'signature_declared': True})
    assert len(out) == 4
    assert any('missing signer' in v for v in out)
    assert any('pubkey_fp' in v for v in out)
    assert any('algorithm' in v for v in out)
    assert any('missing signature' in v for v in out)
    ok = sg.check_package_signature({'signature_declared': True,
                                     'signature_signer': 'alice',
                                     'signature_pubkey_fp': 'sha256:dead',
                                     'signature_algorithm': 'ed25519',
                                     'signature_value': 'c2ln'})
    assert ok == []


def test_check_python_runs_all_rules():
    good = sg.parse_module_text(_GOOD_MD)
    ok, vs = sg.check_python(good)
    assert ok and vs == []
    bad = sg.parse_module_text(_GOOD_MD.replace('# Version: 1.0.0', '# Version: x'))
    ok2, vs2 = sg.check_python(bad)
    assert not ok2 and any('MalformedVersion' in v for v in vs2)


def test_skipped_helpers_tolerate_non_dict():
    assert sg._skipped_law_ids(object()) == {}
    assert sg._skipped_supplemental(object()) == {}
    good = sg.parse_module_text(_GOOD_MD)
    assert set(sg._skipped_law_ids(good)) == {'XVII'}
    assert set(sg._skipped_supplemental(good)) == {
        'check_proof_structure', 'check_eval_determinism', 'check_package_signature'}


# ---------------------------------------------------------------------------
# 6. spec JSON：往返、归一化、校验、加载
# ---------------------------------------------------------------------------

def test_plain_normalization_contract():
    assert sg._to_plain(None) is None
    assert sg._plain_cmp(('num', 5)) == 5
    weird = ('list', 5)
    assert sg._plain_cmp(weird) == weird          # 归一失败 → 原样返回
    assert sg._plain_cmp('5') == 5
    assert sg._plain_cmp('zz') == 'zz'
    assert sg._plain_cmp([('num', 1), '2', 3]) == [1, 2, 3]


def test_validate_spec_json_per_op_errors():
    spec = {'spec': 's', 'version': '1.0.0', 'fingerprint_prefix': '0x0', 'types': [],
            'operations': [
                {},
                {'name': 'a'},
                {'name': 'b', 'fingerprint': '0x01',
                 'signature': {'params': ['ℕ'], 'returns': 'ℕ'},
                 'laws': [{'forall': [], 'predicate': 'p'}],
                 'tests': [{'input': [1], 'output': 1, 'error': 'WeirdErr'}],
                 'preconditions': [{'expr': 'arg0 ≥ 0', 'error': 'QuotaExhausted'}]},
                {'name': 'c', 'fingerprint': '0x01',
                 'signature': {'params': ['ℕ'], 'returns': 'ℕ'},
                 'laws': [{'forall': [], 'predicate': 'p'}],
                 'tests': [{'input': [1], 'output': 2, 'error': 'DivByZero'}]},
            ]}
    joined = '\n'.join(sg.validate_spec_json(spec))
    assert '每个 operation 需要 name' in joined
    assert 'a 缺 fingerprint' in joined
    assert '指纹冲突' in joined
    assert 'a 的 signature' in joined
    assert 'Law III: a' in joined
    assert 'Law IV: a' in joined
    assert "未注册错误名 'WeirdErr'" in joined
    assert 'Law XVI: b' in joined


def test_load_spec_json_errors(tmp_path):
    with pytest.raises(sg.SpecError, match='无法读取'):
        sg.load_spec_json(str(tmp_path / 'missing.json'))
    bad = tmp_path / 'bad.json'
    bad.write_text('{nope', encoding='utf-8')
    with pytest.raises(sg.SpecError, match='解析失败'):
        sg.load_spec_json(str(bad))


# ---------------------------------------------------------------------------
# 7. BUILTIN_FNS 纯函数矩阵
# ---------------------------------------------------------------------------

def test_fn_min_max_variants():
    assert sg._fn_min(3, 1, 2) == 1
    with pytest.raises(sg.IronLawViolation):
        sg._fn_max()
    assert sg._fn_max([1, 5, 3]) == 5
    with pytest.raises(sg.IronLawViolation):
        sg._fn_min([])


def test_fold_ints_builtin():
    add = sg.BUILTIN_FNS['add']
    assert add(2, 3, 4) == 9
    with pytest.raises(sg.IronLawViolation):
        add('x', 1)


def test_fn_weighted_family():
    rows = [[9, 1, 3], [8, 0, 2]]
    assert sg._fn_weighted_accept(rows) == 3
    assert sg._fn_weighted_reject(rows) == 2
    assert sg._fn_weighted_support(rows) == 3
    assert sg._fn_weighted(rows, want=1) == 3
    with pytest.raises(sg.IronLawViolation):
        sg._fn_weighted([[1, 2]], want=1)   # 行太短
    with pytest.raises(sg.IronLawViolation):
        sg._fn_weighted([5])                # 行非列表
    with pytest.raises(sg.IronLawViolation):
        sg._fn_weighted('x')                # 非列表


def test_fn_fold_credit_matrix():
    assert sg._fn_fold_credit(100, [[0, 2]]) == 110
    assert sg._fn_fold_credit(100, [[1, 1]]) == 70
    assert sg._fn_fold_credit(0, [[1, 3]]) == 0          # 钳零
    with pytest.raises(sg.IronLawViolation):
        sg._fn_fold_credit(100, [[2, 1]])                # 未知 kind
    with pytest.raises(sg.IronLawViolation):
        sg._fn_fold_credit(100, [[0]])                   # 事件太短
    with pytest.raises(sg.IronLawViolation):
        sg._fn_fold_credit('x', [])                      # init 非整数
    with pytest.raises(sg.IronLawViolation):
        sg._fn_fold_credit(100, 5)                       # events 非列表


def test_fn_split_floor_matrix():
    assert sg._fn_split_floor([['a', 1], ['b', 3]], 100) == [['a', 25], ['b', 75]]
    with pytest.raises(sg.IronLawViolation):
        sg._fn_split_floor([['a', 0]], 10)               # total 0 → DivByZero
    with pytest.raises(sg.IronLawViolation):
        sg._fn_split_floor([['a']], 10)                  # 行太短
    with pytest.raises(sg.IronLawViolation):
        sg._fn_split_floor('x', 10)
    with pytest.raises(sg.IronLawViolation):
        sg._fn_split_floor([['a', 1]], '10')             # reward 非整数


def test_fn_enumerate_ledger_matrix():
    assert sg._fn_enumerate_ledger([[9, 5, 1], [8, 3, 2]]) == [[1, 1, 5], [2, 2, 3]]
    with pytest.raises(sg.IronLawViolation):
        sg._fn_enumerate_ledger([[9, 5, 0]])             # NotTraceable
    with pytest.raises(sg.IronLawViolation):
        sg._fn_enumerate_ledger([[9, -1, 1]])            # 负金额
    with pytest.raises(sg.IronLawViolation):
        sg._fn_enumerate_ledger([[9, 5]])                # 条目太短
    with pytest.raises(sg.IronLawViolation):
        sg._fn_enumerate_ledger(5)


def test_fn_option_and_map_get():
    with pytest.raises(sg.IronLawViolation):
        sg._fn_option_some(None)
    assert sg._fn_option_some(5) == 5
    with pytest.raises(sg.IronLawViolation):
        sg._fn_map_get([1], 'k')
    assert sg._fn_map_get({'a': 1}, 'a') == 1
    assert sg._fn_map_get({}, 'zz') is None


# ---------------------------------------------------------------------------
# 8. SigmaEngine：节点种类 / 条件 / 前置 / 表驱动 / 语料运行
# ---------------------------------------------------------------------------

def _node_spec(bodies):
    ops = []
    for i, body in enumerate(bodies):
        ops.append({
            'name': f'k{i}', 'fingerprint': f'0xF{i:03d}',
            'signature': {'params': [], 'returns': 'Any'},
            'laws': [{'forall': [], 'predicate': 'p', 'description': ''}],
            'definition': {'kind': 'expression', 'params': [], 'body': body},
            'tests': [],
        })
    return {'spec': 'nodes', 'version': '1.0.0', 'fingerprint_prefix': '0xF',
            'types': [], 'operations': ops}


def test_engine_eval_node_kinds():
    eng = sg.SigmaEngine(_node_spec([
        None, True, 3.5, 'hello', [1, ['x']], {'op': 'k2', 'args': []},
        {'list': [1, 2]}, {'map': {'a': 1, 'b': {'fn': 'add', 'args': [1, 1]}}},
        {'if': {'expr': '1 > 0'}, 'then': {'fn': 'add', 'args': [1, 2]}, 'else': 0},
        {'if': False, 'then': 1, 'else': 2},
        {'if': {'fn': 'eq', 'args': [1, 1]}, 'then': 'y', 'else': 'n'},
        {'if': {'not': {'expr': '0'}}, 'then': 1, 'else': 0},
        {'if': {'and': [{'expr': '1'}, {'expr': '2'}]}, 'then': 1, 'else': 0},
        {'if': {'or': [{'expr': '0'}, {'expr': '1'}]}, 'then': 1, 'else': 0},
        {'fn': 'add', 'args': [1, 2]},
    ]))
    assert eng.eval('k0', []) is None
    assert eng.eval('k1', []) is True
    assert eng.eval('k2', []) == 3.5
    assert eng.eval('k3', []) == 'hello'
    assert eng.eval('k4', []) == [1, ['x']]
    assert eng.eval('k5', []) == 3.5
    assert eng.eval('k6', []) == [1, 2]
    assert eng.eval('k7', []) == {'a': 1, 'b': 2}
    assert eng.eval('k8', []) == 3
    assert eng.eval('k9', []) == 2
    assert eng.eval('k10', []) == 'y'
    assert eng.eval('k11', []) == 1
    assert eng.eval('k12', []) == 1
    assert eng.eval('k13', []) == 1
    assert eng.eval('k14', []) == 3


def test_engine_dollar_before_and_after():
    eng = sg.SigmaEngine(_node_spec(['$_']))
    with pytest.raises(sg.SpecValidationError):
        eng.eval('k0', [])                     # '$_' 在任何结果之前
    eng2 = sg.SigmaEngine(_node_spec([7, '$_']))
    assert eng2.eval('k0', []) == 7
    assert eng2.eval('k1', []) == 7            # '$_' 复用上一次结果


def test_engine_rejects_bad_nodes():
    eng = sg.SigmaEngine(_node_spec([{'fn': 'nosuchfn', 'args': [1]}]))
    with pytest.raises(sg.IronLawViolation):
        eng.eval('k0', [])
    eng2 = sg.SigmaEngine(_node_spec([{'zzz': 1}]))
    with pytest.raises(sg.SpecValidationError):
        eng2.eval('k0', [])
    eng3 = sg.SigmaEngine(_node_spec([1]))
    with pytest.raises(sg.SpecValidationError):
        eng3._eval_node((1, 2), {})            # 非 JSON 节点类型


def _cond_spec(body):
    return {'spec': 'c', 'version': '1.0.0', 'fingerprint_prefix': '0xF', 'types': [],
            'operations': [{'name': 'k0', 'fingerprint': '0xF001',
                            'signature': {'params': ['List'], 'returns': 'Any'},
                            'laws': [{'forall': [], 'predicate': 'p', 'description': ''}],
                            'definition': {'kind': 'expression', 'params': ['st'],
                                           'body': body},
                            'tests': []}]}


def test_engine_field_condition():
    eng = sg.SigmaEngine(_cond_spec(
        {'if': {'field': 0, 'eq': 1}, 'then': 'yes', 'else': 'no'}))
    assert eng.eval('k0', [[1, 9]]) == 'yes'
    assert eng.eval('k0', [[2, 9]]) == 'no'
    eng2 = sg.SigmaEngine(_cond_spec(
        {'if': {'field': 0, 'eq': {'fn': 'add', 'args': [0, 1]}},
         'then': 'yes', 'else': 'no'}))
    assert eng2.eval('k0', [[1, 9]]) == 'yes'      # 比较目标为节点


def test_engine_field_condition_rejected():
    eng = sg.SigmaEngine(_cond_spec({'if': {'field': 0}, 'then': 'y', 'else': 'n'}))
    with pytest.raises(sg.SpecValidationError):
        eng.eval('k0', [5])                        # 无比较符且无列表 ctx
    eng2 = sg.SigmaEngine(_cond_spec({'if': {'bogus': 1}, 'then': 'y', 'else': 'n'}))
    with pytest.raises(sg.SpecValidationError):
        eng2.eval('k0', [[1]])
    eng3 = sg.SigmaEngine(_cond_spec({'if': 'nope', 'then': 'y', 'else': 'n'}))
    with pytest.raises(sg.SpecValidationError):
        eng3.eval('k0', [[1]])


def _pre_spec(pres):
    return {'spec': 'p', 'version': '1.0.0', 'fingerprint_prefix': '0xF', 'types': [],
            'operations': [{'name': 'k0', 'fingerprint': '0xF001',
                            'signature': {'params': ['num'], 'returns': 'num'},
                            'laws': [{'forall': [], 'predicate': 'p', 'description': ''}],
                            'preconditions': pres,
                            'definition': {'kind': 'expression', 'params': ['x'],
                                           'body': 'x'},
                            'tests': []}]}


def test_engine_precondition_contract():
    eng = sg.SigmaEngine(_pre_spec(
        [{'expr': 'x > 0', 'error': 'QuotaExhausted', 'description': 'pos'}]))
    assert eng.eval('k0', [5]) == 5
    with pytest.raises(sg.IronLawViolation) as ei:
        eng.eval('k0', [-1])
    assert ei.value.name == 'QuotaExhausted'
    with pytest.raises(sg.IronLawViolation) as ei2:
        sg.SigmaEngine(_pre_spec([{'expr': '1/0'}])).eval('k0', [1])
    assert ei2.value.name == 'DivByZero'
    with pytest.raises(sg.SpecValidationError):
        sg.SigmaEngine(_pre_spec([{'expr': 'nosuchhelper(1)'}])).eval('k0', [1])
    with pytest.raises(sg.SpecValidationError):
        sg.SigmaEngine(_pre_spec([{'error': 'TypeError'}])).eval('k0', [1])   # 无 expr


def _table_op(name, fp, params, definition):
    return {'name': name, 'fingerprint': fp,
            'signature': {'params': params, 'returns': 'List'},
            'laws': [{'forall': [], 'predicate': 't', 'description': ''}],
            'preconditions': [],
            'definition': definition,
            'tests': []}


_TABLE_SPEC = {
    'spec': 'flow', 'version': '1.0.0', 'fingerprint_prefix': '0xB', 'types': [],
    'operations': [
        _table_op('advance', '0xB001', ['List'], {
            'kind': 'table', 'default_error': 'StateError',
            'table': [
                {'when': {'field': 0, 'eq': 0}, 'set': {'field': 0, 'value': 1}},
                {'when': {'field': 1, 'eq': 7}, 'guard': {'field': 0, 'eq': 1},
                 'set': [{'field': 0, 'value': 2}, {'field': 1, 'value': 5}]},
                {'set': {'field': 0, 'value': 9}},
            ]}),
        _table_op('stuck', '0xB002', ['List'], {
            'kind': 'table', 'default_error': 'StateError',
            'table': [{'when': {'field': 0, 'eq': 7}, 'set': {'field': 0, 'value': 1}}]}),
        _table_op('gated', '0xB003', ['List'], {
            'kind': 'table', 'default_error': 'StateError',
            'table': [{'guard': {'field': 0, 'eq': 9, 'error': 'QuotaExhausted'},
                       'set': {'field': 0, 'value': 1}}]}),
        _table_op('grow', '0xB004', ['List'], {
            'kind': 'table', 'default_error': 'StateError',
            'table': [{'set': {'field': 2, 'value': 7}}]}),
        _table_op('nodev', '0xB005', ['List'], {
            'kind': 'table', 'default_error': 'StateError',
            'table': [{'set': {'field': 1, 'value': {'fn': 'add', 'args': [1, 2]}}}]}),
        _table_op('badset', '0xB006', ['List'], {
            'kind': 'table', 'default_error': 'StateError',
            'table': [{'set': {'value': 1}}]}),
        _table_op('kindless', '0xB007', ['num'], {'kind': 'wat'}),
    ],
}


def test_engine_table_transition():
    eng = sg.SigmaEngine(_TABLE_SPEC)
    assert eng.eval('advance', [[0, 7]]) == [1, 7]     # when 命中 + 单 set
    assert eng.eval('advance', [[1, 7]]) == [2, 5]     # guard 通过 + 多 set
    assert eng.eval('advance', [[8, 9]]) == [9, 9]     # 兜底行（无 when）
    assert eng.eval('grow', [[0]]) == [0, 0, 7]        # set 越界自动补零
    assert eng.eval('nodev', [[0]]) == [0, 3]          # set 值为函数节点


def test_engine_table_errors():
    eng = sg.SigmaEngine(_TABLE_SPEC)
    with pytest.raises(sg.IronLawViolation) as ei:
        eng.eval('advance', [5])
    assert ei.value.name == 'TypeError'                # 非列表状态
    with pytest.raises(sg.IronLawViolation) as ei2:
        eng.eval('gated', [[0, 0]])
    assert ei2.value.name == 'QuotaExhausted'          # guard 自定义错误
    with pytest.raises(sg.IronLawViolation) as ei3:
        eng.eval('stuck', [[0, 0]])
    assert ei3.value.name == 'StateError'              # 无行匹配
    with pytest.raises(sg.SpecValidationError):
        eng.eval('badset', [[0, 0]])                   # set 缺 field
    with pytest.raises(sg.SpecValidationError):
        eng.eval('kindless', [1])                      # 未知 kind


def _corpus_spec():
    return {
        'spec': 'c', 'version': '1.0.0', 'fingerprint_prefix': '0xC', 'types': [],
        'operations': [
            {'name': 'firstdollar', 'fingerprint': '0xC000',
             'signature': {'params': ['Any'], 'returns': 'Any'},
             'laws': [{'forall': [], 'predicate': 'p', 'description': ''}],
             'definition': {'kind': 'expression', 'params': ['x'], 'body': 'x'},
             'tests': [{'input': ['$_'], 'output': 1}]},
            {'name': 'idty', 'fingerprint': '0xC001',
             'signature': {'params': ['Any'], 'returns': 'Any'},
             'laws': [{'forall': [], 'predicate': 'p', 'description': ''}],
             'definition': {'kind': 'expression', 'params': ['x'], 'body': 'x'},
             'tests': [
                 {'input': ['5'], 'output': 5},
                 {'input': [[1, 2]], 'output': [1, 2]},
                 {'input': ['$_'], 'output': [1, 2]},
                 {'input': ['1 ⊕ 1'], 'output': 2},
                 {'input': [{'fn': 'add', 'args': [2, 3]}], 'output': 5},
                 {'input': ['zz'], 'output': 'keep-raw'},
             ]},
            {'name': 'n0div', 'fingerprint': '0xC002',
             'signature': {'params': [], 'returns': 'num'},
             'laws': [{'forall': [], 'predicate': 'p', 'description': ''}],
             'definition': {'kind': 'expression', 'params': [],
                            'body': {'fn': 'add', 'args': [1, 2]}},
             'tests': [{'input': [], 'error': 'DivByZero'}]},
            {'name': 'rawtable', 'fingerprint': '0xC003',
             'signature': {'params': ['List'], 'returns': 'List'},
             'laws': [{'forall': [], 'predicate': 'p', 'description': ''}],
             'definition': {'kind': 'table', 'table': [5]},
             'tests': [{'input': [[0]], 'output': [0]}]},
        ],
    }


def test_run_corpus_reports_each_row_honestly():
    eng = sg.SigmaEngine(_corpus_spec())
    rows = eng.run_corpus()
    by_op = {}
    for name, t, ok, detail in rows:
        by_op.setdefault(name, []).append((ok, detail))
    fd = by_op['firstdollar'][0]
    assert fd[0] is False and 'SpecValidationError' in fd[1]
    nd = by_op['n0div'][0]
    assert nd[0] is False and 'expected error DivByZero' in nd[1]
    rt = by_op['rawtable'][0]
    assert rt[0] is False and 'unexpected exception AttributeError' in rt[1]
    idty_rows = by_op['idty']
    assert [ok for ok, _ in idty_rows] == [True, True, True, True, True, False]


def test_engine_from_spec(tmp_path):
    p = tmp_path / 'self.json'
    p.write_text(json.dumps(_corpus_spec()), encoding='utf-8')
    eng = sg.SigmaEngine.from_spec(str(p))
    assert eng.eval('idty', [eng._resolve_input_node('7')]) == 7
    with pytest.raises(sg.UnknownOpError):
        eng.eval('nope', [])


# ---------------------------------------------------------------------------
# 9. judge_spec / bootstrap / 语言路由
# ---------------------------------------------------------------------------

def _self_spec():
    return sg.to_spec_json(sg.parse_module_text(_GOOD_MD))


def test_spec_to_assertions_filter_and_preconditions():
    spec = _self_spec()
    ids = [a['id'] for a in sg.spec_to_assertions(spec)]
    assert 'idty#t1' in ids and 'idty#t2' in ids and 'idty#law1' in ids
    assert sg.spec_to_assertions(spec, ops_filter=['nope']) == []
    spec2 = json.loads(json.dumps(spec))
    spec2['operations'][0]['preconditions'] = [
        {'expr': 'arg0 ≥ 0', 'error': 'TypeError', 'description': 'd'}]
    ids2 = [a['id'] for a in sg.spec_to_assertions(spec2)]
    assert 'idty#pre1' in ids2


def test_judge_spec_requires_input():
    with pytest.raises(sg.SpecError):
        sg.judge_spec()


def test_judge_spec_invalid_spec_early_return(tmp_path):
    res = sg.judge_spec(spec={'spec': 'x'}, report_path=str(tmp_path / 'r.json'))
    assert res['exit_code'] == 1 and res['spec_errors']
    assert res['verdicts'] == [] and res['summary']['fail'] >= 1
    assert (tmp_path / 'r.json').exists()


_IMPL_SRC = '''from vools.actus.sigma import IronLawViolation


class DivByZero(IronLawViolation):
    pass


def idty(x):
    return x


def raiser(x):
    raise DivByZero("simulated")


def raw_raise(x):
    raise RuntimeError("raw")


def doomed_input(x):
    return x
'''


def test_judge_spec_against_implementation(tmp_path):
    impl = tmp_path / 'impl_judge_r94.py'
    impl.write_text(_IMPL_SRC, encoding='utf-8')
    spec = {'spec': 'j', 'version': '1.0.0', 'fingerprint_prefix': '0xE', 'types': [],
            'operations': [
                {'name': 'idty', 'fingerprint': '0xE001',
                 'signature': {'params': ['Any'], 'returns': 'Any'},
                 'laws': [{'forall': [], 'predicate': 'p', 'description': ''}],
                 'definition': {'kind': 'expression', 'params': ['x'], 'body': 'x'},
                 'tests': [{'input': ['5'], 'output': 5}]},
                {'name': 'raiser', 'fingerprint': '0xE002',
                 'signature': {'params': ['Any'], 'returns': 'Any'},
                 'laws': [{'forall': [], 'predicate': 'p', 'description': ''}],
                 'definition': {'kind': 'expression', 'params': ['x'], 'body': 'x'},
                 'tests': [
                     {'input': ['7'], 'output': None, 'error': 'DivByZero'},
                     {'input': ['7'], 'output': None, 'error': 'QuotaExhausted'},
                 ]},
                {'name': 'raw_raise', 'fingerprint': '0xE003',
                 'signature': {'params': ['Any'], 'returns': 'Any'},
                 'laws': [{'forall': [], 'predicate': 'p', 'description': ''}],
                 'definition': {'kind': 'expression', 'params': ['x'], 'body': 'x'},
                 'tests': [{'input': ['7'], 'output': 7}]},
                {'name': 'ghost', 'fingerprint': '0xE004',
                 'signature': {'params': ['Any'], 'returns': 'Any'},
                 'laws': [{'forall': [], 'predicate': 'p', 'description': ''}],
                 'definition': {'kind': 'expression', 'params': ['x'], 'body': 'x'},
                 'tests': [{'input': ['7'], 'output': 7}]},
                {'name': 'doomed_input', 'fingerprint': '0xE005',
                 'signature': {'params': ['Any'], 'returns': 'Any'},
                 'laws': [{'forall': [], 'predicate': 'p', 'description': ''}],
                 'definition': {'kind': 'expression', 'params': ['x'], 'body': 'x'},
                 'tests': [{'input': ['$_'], 'output': 1}]},
            ]}
    res = sg.judge_spec(spec=spec, submission_path=str(impl))
    v = {a['id']: a for a in res['verdicts']}
    assert v['idty#t1']['verdict'] == 'PASS'
    assert v['raiser#t1']['verdict'] == 'PASS'                       # 命名错误匹配
    assert v['raiser#t2']['verdict'] == 'WA'
    assert 'QuotaExhausted' in v['raiser#t2']['detail']
    assert v['raw_raise#t1']['verdict'] == 'WA'
    assert 'RuntimeError' in v['raw_raise#t1']['detail']
    assert v['ghost']['verdict'] == 'WA'
    assert 'implementation missing' in v['ghost']['detail']
    assert v['doomed_input#t1']['verdict'] == 'WA'
    assert 'input resolve failed' in v['doomed_input#t1']['detail']
    assert res['exit_code'] == 1


def test_write_report_tolerates_bad_path():
    sg._write_report('', {'a': 1})   # open('') → OSError 被吞


def test_module_from_spec_skips_bad_tests():
    spec = {'spec': 'm', 'operations': [
        {'name': 'a', 'fingerprint': '0x01',
         'signature': {'params': ['ℕ'], 'returns': 'ℕ'},
         'laws': [{'predicate': 'p'}],
         'tests': ['not-a-dict', {'input': ['5'], 'output': 5}]},
    ]}
    m = sg._module_from_spec(spec)
    assert m['ops'][0]['tests'] == [('5', '5')]


def test_join_input_nodes_and_plain_to_sigma():
    assert sg._join_input_nodes(5) == '5'
    assert sg._join_input_nodes([1, 'a']) == '1, a'
    assert sg._plain_to_sigma(None) == '⊥'
    assert sg._plain_to_sigma(True) == 'true'
    assert sg._plain_to_sigma(False) == 'false'
    assert sg._plain_to_sigma(5) == '5'
    assert sg._plain_to_sigma(0.5) == '0.5'
    assert sg._plain_to_sigma('s') == 's'
    assert sg._plain_to_sigma([1, 2]) == '[1, 2]'
    assert sg._plain_to_sigma({'a': 1}) == '{"a": 1}'


def test_load_impl_symbols_contract(tmp_path):
    with pytest.raises(sg.SpecError, match='实现文件不存在'):
        sg._load_impl_symbols(str(tmp_path / 'nope.py'))
    txt = tmp_path / 'impl.txt'
    txt.write_text('x = 1', encoding='utf-8')
    with pytest.raises(sg.SpecError, match='无法加载'):
        sg._load_impl_symbols(str(txt))
    crashing = tmp_path / 'crash_impl_r94.py'
    crashing.write_text('raise ValueError("boom")\n', encoding='utf-8')
    with pytest.raises(sg.SpecError, match='实现导入失败'):
        sg._load_impl_symbols(str(crashing))
    good = tmp_path / 'ops_impl_r94.py'
    good.write_text(
        'OPERATIONS = {"op_a": lambda x: x + 1}\n'
        'def module_fn(x):\n    return x * 2\n', encoding='utf-8')
    syms = sg._load_impl_symbols(str(good))
    assert syms['op_a'](1) == 2
    assert syms['module_fn'](3) == 6


def test_render_impl_skeleton_includes_preconditions():
    spec = {'spec': 'sk', 'version': '1.0.0',
            'operations': [{'name': 'f', 'fingerprint': '0x01',
                            'signature': {'params': ['ℕ'], 'returns': 'ℕ'},
                            'laws': [{'predicate': 'p'}],
                            'preconditions': [{'expr': 'arg0 ≥ 0', 'error': 'TypeError'}],
                            'definition': {'kind': 'expression', 'params': ['arg0'],
                                           'body': 'arg0'},
                            'tests': []}]}
    skel = sg.render_impl_skeleton(spec)
    assert '# pre: arg0 ≥ 0  else -> TypeError' in skel
    assert 'def f(arg0):' in skel and 'OPERATIONS' in skel


def test_bootstrap_reports_law_and_test_failures():
    bad_md = _GOOD_MD.replace('# Version: 1.0.0', '# Version: not-semver') \
                     .replace('| 5 | 5 |', '| 5 | 6 |')
    rep = sg.bootstrap(module=sg.parse_module_text(bad_md), out_dir='')
    s = rep['steps'][0]
    assert s['step'] == 'spec_readable' and s['ok'] is False
    assert 'MalformedVersion' in s['detail']
    assert '规范测试失败 1/2' in s['detail']
    assert rep['ok'] is False and len(rep['steps']) == 1


def test_bootstrap_self_consistent_roundtrip(tmp_path):
    rep = sg.bootstrap(module=sg.parse_module_text(_GOOD_MD), out_dir=str(tmp_path))
    assert [s['step'] for s in rep['steps']] == [
        'spec_readable', 'spec_json_valid', 'impl_exists', 'judge']
    assert all(s['ok'] for s in rep['steps'])
    assert rep['ok'] is True and rep['rounds'] == 1
    assert (tmp_path / 'goodmod.spec.json').exists()


def test_bootstrap_spec_json_valid_gate():
    spec = _self_spec()
    spec['operations'][0]['preconditions'] = [
        {'expr': 'arg0 ≥ 0', 'error': 'QuotaExhausted', 'description': 'p'}]
    rep = sg.bootstrap(spec=spec, out_dir='')
    assert rep['steps'][1]['step'] == 'spec_json_valid' and rep['steps'][1]['ok'] is False
    assert rep.get('spec_errors')
    assert rep['ok'] is False


def test_bootstrap_generates_skeleton_when_impl_missing(tmp_path):
    rep = sg.bootstrap(spec=_self_spec(),
                       impl_path=str(tmp_path / 'no_impl.py'),
                       out_dir=str(tmp_path / 'out'))
    last = rep['steps'][-1]
    assert last['step'] == 'impl_exists' and last['ok'] is False
    assert 'needs_impl' in last['detail']
    assert (tmp_path / 'out' / 'impl_skeleton.py').exists()
    assert 'skeleton' in rep['artifacts']


def test_bootstrap_judges_real_implementation(tmp_path):
    impl = tmp_path / 'idty_impl.py'
    impl.write_text('def idty(x):\n    return x\n', encoding='utf-8')
    rep = sg.bootstrap(spec=_self_spec(), impl_path=str(impl),
                       out_dir=str(tmp_path / 'o2'))
    # 真实契约：负向用例的输入（'0 ⊘ 0'）在对实现求值前就被解析成命名错误
    # 哨兵并抛出 → judge 实现通道判 WA 'input resolve failed' → 重试 3 轮仍不过。
    assert rep['ok'] is False and rep['rounds'] == 3
    assert rep['steps'][-1]['step'] == 'judge' and rep['steps'][-1]['ok'] is False
    assert rep['steps'][-1]['detail'] == 'pass 1/2'
    wa = [v for v in rep['judge']['verdicts'] if v['verdict'] == 'WA']
    assert len(wa) == 1 and 'input resolve failed' in wa[0]['detail']


def test_run_sigma_block_guards():
    out, err, code = sg.run_sigma_block('')
    assert out == '' and code == 1 and '为空' in err
    out2, err2, code2 = sg.run_sigma_block('## Operation: f\nf : ℕ → ℕ\n')
    assert code2 == 1 and '没有任何 Operation' in err2
    assert sg.sigma_block_is_loadable('') == (False, 'sigma 规约块为空')
    assert sg.sigma_block_is_loadable('## Operation: f\nf : ℕ → ℕ\n')[0] is False
    assert sg.sigma_block_is_loadable(_GOOD_MD) == (True, None)


_SUPP_MD = '''# Module: suppmod
# Version: 1.0.0

## Imports
import core

## Proof
some proof prose

## Operation: idty
Fingerprint: 0xD001
idty : ℕ → ℕ

### Laws
∀a . idty(a) ≡ a

### Tests
| 5 | 5 |
| 0 ⊘ 0 | ⊥ DivByZero |

### Definition
arg0
'''


def test_run_sigma_block_prints_supplemental_section():
    out, err, code = sg.run_sigma_block(_SUPP_MD)
    assert code == 1
    assert '补充细则' in out
    assert 'check_proof_structure' in out
    assert 'MissingModel' in out
