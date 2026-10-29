# -*- coding: utf-8 -*-
"""`sigma.py` 契约测试（第 32 轮，T0r4 系列：覆盖 46% 的最大单模块）。

`sigma.py` 是 Sigma 规约语言的三端之一：**词法/字面量 → 表达求值 → 参考操作语义
→ 模块解析 → Iron Laws 校验 → spec JSON 互喂 → 引擎执行 → 块入口**。
本文件按这条链逐段钉住可观察契约，全部**不依赖外部工具/网络/真实用户目录**。

区别于 `tests/test_sigma_gates.py`（那篇钉门禁语义修复）：本文件覆盖
值层/运算符/32 个参考操作/25 条 Iron Law 的解析与判定/spec JSON/引擎/块入口。

每条 docstring 写「退步了会怎样」。
"""
import json
import os
import tempfile

import pytest

from vools.actus import sigma as S


# ═══════════════════════════════════════════════════════════════════
# 夹具：一份"结构合法、规范测试全过"的最小规约（与 sigma 语法一致）
# ═══════════════════════════════════════════════════════════════════

BASE_MODULE = """# Module: audit.demo
# Version: 0.1.0
## Imports
import core
## Exports
f
## Operation: f (ℕ)
### Signature
f: ℕ → ℕ
### Laws
∀x: f(x) ≡ x
### Tests
| Input | Output |
| 1 ⊕ 1 | 2 |
| 0 ⊘ 0 | ⊥ DivByZero |
### Definition
arg0
Fingerprint: 0xA001
"""


@pytest.fixture
def module():
    return S.parse_module_text(BASE_MODULE)


@pytest.fixture
def spec(module):
    return S.to_spec_json(module)


# ═══════════════════════════════════════════════════════════════════
# ① 字面量 / 值层（parse_val / parse_list / split_* / fmt_val）
# ═══════════════════════════════════════════════════════════════════


def test_parse_val_accepts_numeric_and_nested_literals():
    """退步了会怎样：字面量语法（整数/浮点/嵌套列表/元组/Unicode 负号）被收窄 →
    大量合法规约用例判成 `unparseable`，三端（Rust/Elixir/Python）判定漂移。
    """
    assert S.parse_val('42') == ('num', 42)
    assert S.parse_val('-7') == ('num', -7)
    assert S.parse_val('0.5') == ('fnum', 0.5)
    assert S.parse_val('−3') == ('num', -3)          # U+2212 负号
    assert S.parse_val('[1,2]')[0] == 'list'
    assert S.parse_val('(1,2)')[0] == 'list'         # 元组按列表处理
    assert S.parse_val('[1,[2,3]]')[0] == 'list'


def test_parse_val_returns_none_for_invalid_literal():
    """退步了会怎样：非法字面量被"猜"成某个值（例如 '+5' → 5）→ 规约作者写错的
    输入被静默接受，测试变成假绿。契约是**返回 None**，由调用方报 unparseable。
    """
    for bad in ('+5', '1e3', 'abc', '[1,2', ''):
        assert S.parse_val(bad) is None, bad


def test_parse_list_handles_empty_and_malformed():
    """退步了会怎样：空列表 `[]` 解析失败 / 半截列表被当成部分列表 → 值层面就丢数据。
    """
    assert S.parse_list('') == ('list', [])
    assert S.parse_list('1,2')[0] == 'list'
    assert S.parse_list('1,{') is None


def test_split_top_level_respects_nesting():
    """退步了会怎样：按字符硬切（不跟踪括号深度）→ `[[1,2],[3,4]]` 被切碎，
    嵌套列表/矩阵语义全错。
    """
    assert S.split_top_level('1 ⊕ [2,3]', '⊕') == ('1 ', ' [2,3]')
    assert S.split_top_level('no-sep', '⊕') is None
    assert S.split_all_top_level('[1,2],[3,4]', ',') == ['[1,2]', '[3,4]']


def test_fmt_val_roundtrips_with_parse_val():
    """退步了会怎样：格式化与解析不对称（fmt 出 'fnum' 的 `0.5` 解析不回来）→
    规范测试的"expected"渲染出来再解析会漂移。
    """
    for text in ('1', '-3', '[1,2,[3,4]]'):
        val = S.parse_val(text)
        assert S.parse_val(S.fmt_val(val)) == val


def test_elemwise_ops_and_shape_errors():
    """退步了会怎样：逐元素运算遇到形状不符时抛裸异常/静默截断 → 规约求值崩溃或
    给出错误答案（应为 `'ShapeError'` 哨兵，与上游 Err 语义一致）。
    """
    add = S.elemwise_add
    assert add(('num', 1), ('num', 2)) == ('num', 3)
    assert add(('num', 1), ('fnum', 0.5)) == ('fnum', 1.5)
    assert add(('list', [('num', 1)]), ('list', [('num', 2)])) == ('list', [('num', 3)])
    assert add(('list', [('num', 1), ('num', 2)]), ('list', [('num', 3)])) == 'ShapeError'
    assert add(('list', [('num', 1)]), ('num', 2)) == 'ShapeError'
    assert S.elemwise_sub(('num', 5), ('num', 2)) == ('num', 3)
    assert S.elemwise_mul(('num', 3), ('num', 4)) == ('num', 12)
    assert S.elemwise_div(('num', 1), ('num', 0)) == 'DivByZero'   # 除零 → 哨兵
    assert S.elemwise_div(('fnum', 1.0), ('num', 2)) == ('fnum', 0.5)


def test_mat_mul_semantics_and_dim_mismatch():
    """退步了会怎样：矩阵乘法维度校验缺失 → 越界 IndexError 或错误矩阵被接受。

    契约（`mat_mul` 源码）：左操作数是**行列表**，右操作数是**列向量**（元素为标量）；
    行宽必须等于列向量长度，否则返回 `'ShapeError'`。
    """
    matrix = ('list', [('list', [('num', 1), ('num', 2)]),
                       ('list', [('num', 3), ('num', 4)])])
    column = ('list', [('num', 1), ('num', 1)])
    assert S.mat_mul(matrix, column) == ('list', [('num', 3), ('num', 7)])
    ident = ('list', [('list', [('num', 1), ('num', 0)]),
                      ('list', [('num', 0), ('num', 1)])])
    assert S.mat_mul(ident, column) == column
    assert S.mat_mul(matrix, matrix) == 'TypeError'           # 右侧元素不是标量
    assert S.mat_mul(('num', 1), ('num', 2)) == 'ShapeError'  # 非列表


def test_value_eq_cmp_in_semantics():
    """退步了会怎样：≡/≥/≤/∈ 的类型判定缺失 → 跨类型比较被当成 False/True，
    沉默地改变规约判定（契约是返回 `'TypeError'` 哨兵）。
    """
    assert S.value_eq(('num', 1), ('num', 1)) == ('num', 1)
    assert S.value_eq(('num', 1), ('num', 2)) == ('num', 0)
    assert S.value_eq(('num', 1), ('fnum', 1.0)) == 'TypeError'      # 类型不同 → 哨兵
    assert S.value_eq(('list', [('num', 1)]), ('list', [('num', 1)])) == ('num', 1)
    assert S.value_eq(('list', [('num', 1)]), ('list', [('num', 1), ('num', 2)])) == ('num', 0)
    assert S.value_cmp(('num', 2), ('num', 1), 'ge') == ('num', 1)
    assert S.value_cmp(('num', 1), ('num', 2), 'le') == ('num', 1)
    assert S.value_cmp(('list', [('num', 1)]), ('num', 1), 'ge') == 'TypeError'
    assert S.value_in(('num', 1), ('list', [('num', 2), ('num', 1)])) == ('num', 1)
    assert S.value_in(('num', 9), ('list', [('num', 2)])) == ('num', 0)
    assert S.value_in(('num', 1), ('num', 1)) == 'TypeError'


def test_collect_path_and_index_into():
    """退步了会怎样：路径索引（`index(xs, [i,j])`）越界返回垃圾/抛裸异常，
    而契约是 `'OutOfBounds'` 哨兵、非列表返回 `'TypeError'`。
    """
    assert S.collect_path(('num', 1)) == [1]
    assert S.collect_path(('list', [('num', 1), ('num', 2)])) == [1, 2]
    assert S.collect_path(('fnum', 1.0)) == []
    nested = ('list', [('list', [('num', 7)]), ('list', [('num', 8)])])
    assert S.index_into(nested, ('list', [('num', 1), ('num', 0)])) == ('num', 8)
    assert S.index_into(nested, ('num', 5)) == 'OutOfBounds'
    assert S.index_into(('num', 1), ('num', 0)) == 'TypeError'


# ═══════════════════════════════════════════════════════════════════
# ② 表达式求值（eval_expr / eval_test）
# ═══════════════════════════════════════════════════════════════════

_ERROR_SENTINELS = {
    'ShapeError', 'TypeError', 'DivByZero', 'OutOfBounds', 'AuthError',
    'UnknownAsset', 'StateError', 'NotFound', 'QuotaExceeded',
}


def test_eval_expr_constants_and_literals():
    """退步了会怎样：常量/单位矩阵 `I₂`/`points_new()` 求值漂移 → 用它们写的
    规约全部失效（这些是跨端约定的固定值）。
    """
    assert S.eval_expr('I₂') == ('list', [('list', [('num', 1), ('num', 0)]),
                                         ('list', [('num', 0), ('num', 1)])])
    assert S.eval_expr('points_new()') == ('list', [('num', 0), ('num', 0)])
    assert S.eval_expr('42') == ('num', 42)
    assert S.eval_expr('  [1,2]  ')[0] == 'list'


def test_eval_expr_unparseable_is_sentinel_not_exception():
    """退步了会怎样：非法表达式抛异常而不是返回 `unparseable:` 哨兵 → 一条测试
    用例写错就让整个模块验证崩掉（契约：错误以字符串返回，由 eval_test 记失败）。
    """
    for bad in ('+5', '', 'unknown_op(1)'):
        result = S.eval_expr(bad)
        assert isinstance(result, str) and result.startswith('unparseable:'), (bad, result)


def test_eval_expr_operator_precedence_is_right_associative():
    """退步了会怎样：运算符顺序/结合性改变（Rust/Elixir 是固定 if-chain 右结合）→
    同一条规约在三端算出不同结果。本用例钉住 Python 端与文档一致的顺序。
    """
    assert S.eval_expr('1 ⊕ 2') == ('num', 3)
    assert S.eval_expr('10 ⊖ 3') == ('num', 7)
    assert S.eval_expr('2 ⊙ 3') == ('num', 6)
    assert S.eval_expr('[1,2] ⊕ [3,4]') == ('list', [('num', 4), ('num', 6)])
    assert S.eval_expr('1 ⊘ 0') == 'DivByZero'
    assert S.eval_expr('[1,2] ≡ [1,2]') == ('num', 1)
    assert S.eval_expr('1 ≥ 2') == ('num', 0)
    assert S.eval_expr('1 ∈ [1,2]') == ('num', 1)
    assert S.eval_expr('1 ⊗ 2') == 'ShapeError'


def test_eval_expr_index_op_bounds():
    """退步了会怎样：`index()` 越界不再回 OutOfBounds（改成抛异常/回垃圾）→
    负向用例 `| ... | ⊥ OutOfBounds |` 全判失败。
    """
    assert S.eval_expr('index([1,2,3], 1)') == ('num', 2)
    assert S.eval_expr('index([1,2], 5)') == 'OutOfBounds'
    assert S.eval_expr('index([1,2], bad)') == 'bad index: bad'


def test_eval_expr_op_arity_guard():
    """退步了会怎样：参数不足的参考操作被"静默按缺省"求值 → 作者写漏参数，
    规约照样过（契约：返回 `bad <op> args:` 哨兵）。
    """
    result = S.eval_expr('task_accept(1)')
    assert isinstance(result, str) and result.startswith('bad task_accept args:'), result


def test_eval_test_pass_fail_and_negative_cases():
    """退步了会怎样：规范测试的通过/失败/`⊥`（预期错误）三态判定错 → 门禁
    要么放过坏规约，要么把好规约误杀。
    """
    assert S.eval_test('1 ⊕ 1', '2') is None                 # 通过
    assert S.eval_test('1 ⊕ 1', '3') == 'expected 3, got 2'  # 期望不符
    assert S.eval_test('0 ⊘ 0', '⊥ DivByZero') is None       # 负向用例通过
    assert S.eval_test('1 ⊕ 1', '⊥') == 'expected error, got 2'
    assert S.eval_test('unknown_op(1)', '1').startswith('evaluation failed:')
    assert S.eval_test('1', 'zzz') == 'unparseable expectation: zzz'


def test_eval_compat_test_returns_bool():
    """退步了会怎样：兼容性测试（compat tests）的通过/失败判定改变 → 上层把
    失败当通过（假绿）。契约：True=兼容；不兼容返回差异描述字符串（同 eval_test）。
    """
    assert S.eval_compat_test('1 ⊕ 1', '2') is True
    mismatch = S.eval_compat_test('1 ⊕ 1', '3')
    assert isinstance(mismatch, str) and 'expected 3' in mismatch, mismatch


# ═══════════════════════════════════════════════════════════════════
# ③ 32 个参考操作（REFERENCE_OPS）：派发可达性 + 关键语义
# ═══════════════════════════════════════════════════════════════════


def test_every_reference_op_is_dispatchable():
    """退步了会怎样：REFERENCE_OPS 表中某个操作被改名/漏接 → 用到它的规约全部
    变成 `unparseable`（三端语义表漂移）。本用例逐个派发，保证每个名字都可达，
    且返回"值元组或已知错误哨兵"，不抛裸异常。

    参数形状按 `_REF_MIN_ARGS` 分两类：登记了最小实参数的操作按逗号切分，
    未登记的操作按**单条表达式**整体求值（与上游 if-chain 一致）。
    """
    arg_table = {
        'index': '[1,2,3], 1', 'task_create': '1, 3', 'accept_task': '1, 2',
        'task_submit': '[1,3,0,0]', 'task_accept': 'task_create(1,3)',
        'review_merge': '[1,2,3]', 'contribution_score': '[1,2,3]',
        'credit_score': '[1,2,3]', 'portfolio_new': '100',
        'buy': 'portfolio_new(100), 10, 5', 'sell': 'portfolio_new(100), 10, 5',
        'portfolio_value': '[100,0,0]', 'risk_score': '5',
        'quota_new': '5', 'quota_use': 'quota_new(5), 2',
        'quota_reset': '[5,5]', 'quota_advance': '[5,5]',
        'points_hold': '[10,0], 3', 'points_release': '[10,3], 2',
        'points_withdraw': '[10,3], 2', 'badge_level': '15',
        'badge_issue': '15, 0, 1', 'dispute_review': '[1,2,3]',
        'team_create': '1, 2, 3', 'team_join': 'team_create(1,2,3), 4',
        'team_share': 'team_create(1,2,3), 5', 'points_ledger': '[1,2,3]',
        'inventory_new': '10, 3', 'receive_stock': 'inventory_new(10,3), 1',
        'ship_stock': 'inventory_new(10,3), 1',
        'stock_level': 'inventory_new(10, 3), 1', 'fill_rate': '3, 4',
    }
    missing = [name for name, _ in S.REFERENCE_OPS if name not in arg_table]
    assert not missing, "新加操作没在本用例登记: %s" % missing

    for name, _handler in S.REFERENCE_OPS:
        result = S.eval_expr("%s(%s)" % (name, arg_table[name]))
        ok = isinstance(result, tuple) or (
            isinstance(result, str)
            and (result in _ERROR_SENTINELS or result.startswith('bad ')))
        assert ok, "%s 派发结果异常: %r" % (name, result)


def test_reference_op_exact_semantics():
    """退步了会怎样：参考操作的算术语义被改（配额/积分/库存/费率）→ 规约判定的
    数值全错，而且错得很隐蔽（结构对、数值错）。这些值是与上游 if-chain 对齐的。
    """
    assert S.eval_expr('task_create(1, 3)') == ('list', [('num', 1), ('num', 3),
                                                        ('num', 0), ('num', 0)])
    assert S.eval_expr('fill_rate(3, 4)') == ('fnum', 0.75)
    assert S.eval_expr('quota_new(5)') == ('list', [('num', 5), ('num', 5)])
    assert S.eval_expr('quota_use(quota_new(5), 2)') == ('list', [('num', 5), ('num', 3)])
    assert S.eval_expr('quota_reset(quota_new(5))') == ('list', [('num', 5), ('num', 5)])
    assert S.eval_expr('quota_advance(quota_new(5))') == ('list', [('num', 5), ('num', 10)])
    assert S.eval_expr('points_hold([10,0], 3)') == ('list', [('num', 13), ('num', 0)])
    assert S.eval_expr('points_release([10,3], 2)') == ('list', [('num', 8), ('num', 5)])
    assert S.eval_expr('points_withdraw([10,3], 2)') == ('list', [('num', 10), ('num', 1)])
    assert S.eval_expr('portfolio_new(100)') == ('list', [('num', 100), ('num', 0), ('num', 0)])
    assert S.eval_expr('portfolio_value(portfolio_new(100))') == ('num', 100)
    assert S.eval_expr('inventory_new(10, 3)') == ('list', [('num', 10), ('num', 3)])
    assert S.eval_expr('stock_level(inventory_new(10, 3), 1)') == ('num', 3)
    assert S.eval_expr('team_create(1, 2, 3)') == ('list', [('num', 1), ('num', 2),
                                                           ('num', 1), ('num', 3)])


def test_reference_op_error_sentinels():
    """退步了会怎样：错误语义（越权/未知资产/状态不符）被吞成正常值 →
    负向用例无法通过，安全边界静默消失。
    """
    assert S.eval_expr('badge_issue(15, 0, 1)') == 'AuthError'      # 越权发徽章
    assert S.eval_expr('task_submit(task_create(1,3))') == 'StateError'
    assert S.eval_expr('buy(portfolio_new(100), 10, 5)') == 'UnknownAsset'


# ═══════════════════════════════════════════════════════════════════
# ④ spec 求值函数（_fn_*）与参数守卫（_require_*）
# ═══════════════════════════════════════════════════════════════════


def test_fn_value_semantics():
    """退步了会怎样：spec 内建函数（len/min/max/fold_add/map/div/floordiv/mod）的
    语义漂移 → 用它们写的 spec 求值全错。
    """
    assert S._fn_len([1, 2]) == 2
    assert S._fn_min([3, 1, 2]) == 1
    assert S._fn_max(4, 9) == 9
    assert S._fn_fold_add([[1, 2], [3, 4]]) == 6      # 列表的最后一列求和
    assert S._fn_fold_add([1, 2, 3]) == 6             # 纯整数列表
    assert S._fn_map([[1, 2], [3, 4]], 1) == [2, 4]
    assert S._fn_floordiv(7, 2) == 3
    assert S._fn_div(1, 2) == 0.5
    assert S._fn_mod(7, 3) == 1
    assert S._cmp('lt')(1, 2) is True


def test_spec_fn_shape_guards_are_structured():
    """退步了会怎样（A1/A2/A3，第 32 轮修）：spec 内建函数遇到越界/空表/混合类型时
    改前抛**裸 IndexError / ValueError / TypeError**，与同族 `_fn_index` 的结构化
    `ShapeError` 不一致 —— 上层无法把"spec 输入不合法"与"引擎 bug"区分，
    裸异常会穿透成 CLI/MCP 内部错误。修复后统一是 `IronLawViolation`。
    """
    cases = [
        ('A1 map 字段越界', lambda: S._fn_map([[1, 2]], 5), 'ShapeError'),
        ('A1 map 行非列表', lambda: S._fn_map([1, 2], 0), 'TypeError'),
        ('A2 min 空列表', lambda: S._fn_min([]), 'ShapeError'),
        ('A2 max 空列表', lambda: S._fn_max([]), 'ShapeError'),
        ('A2 min 零实参', lambda: S._fn_min(), 'ShapeError'),
        ('A3 fold_add 混合', lambda: S._fn_fold_add([1, [2, 3]]), 'TypeError'),
        ('A3 fold_add 空行', lambda: S._fn_fold_add([[]]), 'ShapeError'),
        ('A3 fold_add 行尾非整数', lambda: S._fn_fold_add([[1, 'x']]), 'TypeError'),
    ]
    for label, fn, err_name in cases:
        with pytest.raises(S.IronLawViolation) as exc:
            fn()
        assert type(exc.value).__name__ == err_name, (label, type(exc.value).__name__)
        assert not isinstance(exc.value, (IndexError, ValueError)) or \
            isinstance(exc.value, S.IronLawViolation), label


def test_spec_fn_guards_keep_normal_paths():
    """退步了会怎样：补守卫时把正常路径也拦了（空列表合法返回 0 / 正常 map 失效）
    → 修 bug 引入回归，正常 spec 全部求值失败。
    """
    assert S._fn_fold_add([]) == 0
    assert S._fn_fold_add([1, 2, 3]) == 6
    assert S._fn_fold_add([[1, 2], [3, 4]]) == 6
    assert S._fn_map([[1, 2], [3, 4]], 1) == [2, 4]
    assert S._fn_map([[1, 2]], -1) == [2]
    assert S._fn_min([3, 1, 2]) == 1
    assert S._fn_max(4, 9) == 9


def test_fn_div_guards_are_structured():
    """退步了会怎样：除零走裸 ZeroDivisionError（而不是结构化 DivByZero）→
    上层无法把它归因到规约输入，只能当成引擎崩溃。
    """
    for fn in (S._fn_div, S._fn_floordiv, S._fn_mod):
        with pytest.raises(S.IronLawViolation) as exc:
            fn(1, 0)
        assert 'DivByZero' in str(exc.value) or 'division by zero' in str(exc.value)


def test_fn_index_bounds_is_structured():
    """退步了会怎样：索引越界抛裸 IndexError → 与 div 的处置不一致，上层分类错乱。
    """
    with pytest.raises(S.IronLawViolation) as exc:
        S._fn_index([1], 5)
    assert 'out of range' in str(exc.value)


def test_require_guards_reject_wrong_types():
    """退步了会怎样：`_require_*` 守卫失效 → spec 里写错类型时不再有清晰报错，
    而是深层 TypeError（排查成本极高）。注意：守卫抛的是**动态 IronLawViolation
    子类**（类名就叫 TypeError），不是内置 TypeError。
    """
    for fn, bad in ((S._require_int, 'x'), (S._require_list, 1), (S._require_str, 1)):
        with pytest.raises(S.IronLawViolation) as exc:
            fn(bad, 'probe')
        assert 'probe' in str(exc.value)
        assert type(exc.value).__name__ == 'TypeError', type(exc.value).__name__


def test_fn_string_option_map_helpers():
    """退步了会怎样：字符串/Option/Map 辅助函数语义漂移 → 用它们写的前置条件
    静默通过或误报。
    """
    assert S._fn_str_len('abc') == 3
    assert S._fn_str_concat('a', 'b') == 'ab'
    assert S._fn_str_contains('abc', 'b') is True
    assert S._fn_str_contains('abc', 'z') is False
    assert S._fn_option_some(3) == 3
    assert S._fn_map_get({'a': 1}, 'a') == 1
    assert S._fn_map_get({'a': 1}, 'z') is None


# ═══════════════════════════════════════════════════════════════════
# ⑤ 模块解析（parse_module_text / parse_module）
# ═══════════════════════════════════════════════════════════════════


def test_parse_module_prologue_fields(module):
    """退步了会怎样：`# Module:` / `# Version:` 前言解析失效 → 指纹计算与报告
    里的模块名全空，跨端对账（fingerprint）整体错位。
    """
    assert module['name'] == 'audit.demo'
    assert module['version'] == '0.1.0'
    assert module['imports'] == ['core']
    assert module['exports'] == ['f']


def test_parse_module_separates_ops_and_declared_fns():
    """退步了会怎样：带指纹的 Operation 被当声明 fn（或反之）→ ops/fns 计数错，
    "零操作规约"会真空通过所有 Iron Law（Law I 不可达）。
    """
    with_fp = S.parse_module_text(BASE_MODULE)
    assert len(with_fp['ops']) == 1 and with_fp['fns'] == []
    assert with_fp['ops'][0]['fp'] == '0xA001'
    assert with_fp['ops'][0]['name'] == 'f'
    # tests 存的是 (输入表达式, 期望输出) 元组
    assert [t[0] for t in with_fp['ops'][0]['tests']] == ['1 ⊕ 1', '0 ⊘ 0']

    no_fp = S.parse_module_text(
        "# Module: m\n## Operation: g (ℕ)\n### Signature\ng: ℕ → ℕ\n")
    assert no_fp['ops'] == [] and len(no_fp['fns']) == 1


def test_parse_module_sections_are_recognised():
    """退步了会怎样：Proof/Guarantee/Determinism/Signature/Shadowing/Timing/
    Capabilities 等章节不再被识别 → 对应 Iron Law 全部误判（要么永远 skipped、
    要么永远 violation）。
    """
    text = """# Module: sec.demo
# Version: 0.2.0
# Expected: PASS
# Package: std/demo
## Exports
a, b
## Proof
### Model
### Invariant
## Guarantee
metric: latency
threshold: 100
dataset: golden
## Determinism
precision: exact
rounding: half-up
sort_stability: stable
## Signature
signer: alice
pubkey_fp: ABCDEF
algorithm: ed25519
signature: sig
## Shadowing
shadow other.op → reason
## Timing
max_latency: 100
max_retries: 3
timeout_budget: 2
## Capabilities
network, filesystem
## Compat Tests
| 1 | 2 |
"""
    m = S.parse_module_text(text)
    assert m['expected'] == 'PASS'
    assert m['package'] == 'std/demo'
    assert m['exports'] == ['a', 'b']
    assert m['proof_declared'] and m['proof_has_model'] and m['proof_has_invariant']
    assert m['guarantee_declared'] and m['guarantee_metric'] == 'latency'
    assert str(m['guarantee_threshold']) == '100'
    assert m['determinism_declared'] and m['determinism_precision'] == 'exact'
    assert m['signature_declared'] and m['signature_algorithm'] == 'ed25519'
    assert m['shadow_targets'] == ['other.op']
    assert m['timing_contract'] and m['timing_contract']['max_retries'] == '3'
    assert m['capabilities'] == ['network', 'filesystem']
    assert m['compat_tests'] == [('1', '2')], m['compat_tests']


def test_parse_module_garbage_yields_empty_module_not_exception():
    """退步了会怎样：垃圾文本抛异常（上层 `sigma_block_is_loadable` 只好吞掉，
    或直接崩）→ 契约是返回空模块，由调用方按"无操作"报错。
    """
    m = S.parse_module_text('this is not a sigma module')
    assert m['ops'] == [] and m['fns'] == []
    assert m['name'] == 'parsed_module'


def test_parse_module_from_file(isolated_sigma_tmp):
    """退步了会怎样：`parse_module(path)` 不读文件/编码错 → .md 模块无法从磁盘解析。
    """
    path = os.path.join(isolated_sigma_tmp, "m.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(BASE_MODULE)
    m = S.parse_module(path)
    assert m['name'] == 'audit.demo' and len(m['ops']) == 1


# ═══════════════════════════════════════════════════════════════════
# ⑥ Iron Laws 判定（check_iron_laws / verify_module / 单条 law）
# ═══════════════════════════════════════════════════════════════════


def test_valid_module_passes_all_laws(module):
    """退步了会怎样：一份合法规约被 law 误杀（假阳性）→ 没人能通过门禁；
    或测试结果没并入 passed（P1 老 bug 回归）→ 坏规约也能过。
    """
    report = S.check_iron_laws(module)
    assert report['passed'] is True, report['failed_laws']
    assert report['failed_laws'] == []
    assert report['tests'] == {'passed': 2, 'total': 2, 'failures': []}
    assert report['fingerprint'].startswith('sha256:')
    assert S.verify_module(module)['verdict'] == 'pass'


def test_failing_canonical_test_fails_module(module):
    """退步了会怎样：规范测试失败但 `passed=True`（历史 P1）→ 门禁形同虚设。
    """
    bad = S.parse_module_text(BASE_MODULE.replace('| 1 ⊕ 1 | 2 |', '| 1 ⊕ 1 | 3 |'))
    report = S.check_iron_laws(bad)
    assert report['passed'] is False
    assert report['tests']['failures']
    assert S.verify_module(bad)['verdict'] == 'fail'


def test_law_report_shape_is_stable(module):
    """退步了会怎样：报告结构改键/丢字段 → 调用方（CLI/MCP/发布门禁）取
    `failed_laws/violations` 时 KeyError 或静默读空。
    """
    report = S.check_iron_laws(module)
    for key in ('module', 'fingerprint', 'laws', 'passed', 'failed_laws',
                'violations', 'tests', 'strict', 'skipped_laws'):
        assert key in report, key
    assert isinstance(report['laws'], list) and report['laws'], "laws 明细不得为空"
    # 每条 law 条目以 id/key 标识（name 不是键名，en/zh 才是人类可读名）
    assert all('id' in law and 'key' in law for law in report['laws'])


def test_individual_laws_report_violations():
    """退步了会怎样：单条 Iron Law 的实现失效（永远返回 []）→ 该条定律变成装饰，
    而整体 passed 仍可能为 True（其它定律都过）。
    """
    empty = S._new_module('empty.demo')
    # Law VII：没有 core import
    violations = S.check_dependencies(empty)
    assert any('NoCoreImport' in v for v in violations), violations
    # Law I：Operation 缺指纹必须报 MissingFingerprint（历史 P1 回归点）
    m = S.parse_module_text(
        "# Module: m\n## Imports\nimport core\n"
        "## Operation: g (ℕ)\n### Signature\ng: ℕ → ℕ\n### Tests\n| 1 | 1 |\n"
        "### Definition\narg0\n")
    assert any('MissingFingerprint' in v for v in S.check_no_implementation(m) or []) \
        or any('MissingFingerprint' in str(v) for v in S.check_iron_laws(m)['violations'])


def test_strict_vs_loose_and_skipped_laws(module):
    """退步了会怎样：strict=False 不再把未声明章节的定律降级为 skipped → 缺
    `## Guarantee` 的模块被判 fail（假阴性）；或 skipped 不再如实披露。
    """
    strict = S.check_iron_laws(module, strict=True)
    loose = S.check_iron_laws(module, strict=False)
    assert loose['strict'] is False
    # skipped_laws 是**列表**（每项含 id/key/skip_reason/skip_kind 等）
    assert isinstance(loose['skipped_laws'], list)
    assert isinstance(S._skipped_law_ids(module), dict)
    assert S._skipped_law_ids(module).get('XVII'), "缺 Guarantee 应记入 skipped"
    assert strict['passed'] is True and loose['passed'] is True


# ═══════════════════════════════════════════════════════════════════
# ⑦ spec JSON 互喂（to_spec_json / validate / load / fingerprint / judge）
# ═══════════════════════════════════════════════════════════════════


def test_to_spec_json_has_required_top_level(spec):
    """退步了会怎样：spec 互喂缺顶层字段 → `validate_spec_json` 全报错、
    `SigmaEngine` 加载失败，模块↔spec 闭环断裂。
    """
    for key in ('spec', 'version', 'fingerprint_prefix', 'types', 'operations'):
        assert key in spec, key
    assert spec['spec'] == 'audit.demo'
    assert isinstance(spec['operations'], list) and spec['operations']


def test_validate_spec_json_reports_missing_fields():
    """退步了会怎样：坏 spec 被判"没问题"（fail-open）→ 引擎加载后才炸/静默不执行。
    """
    errors = S.validate_spec_json({})
    assert errors, "空 spec 必须报错"
    assert any("'spec'" in e for e in errors), errors
    assert S.validate_spec_json(None) == ['spec JSON must be an object']
    assert S.validate_spec_json(S.to_spec_json(S.parse_module_text(BASE_MODULE))) == []


def test_load_spec_json_roundtrip(spec, isolated_sigma_tmp):
    """退步了会怎样：`load_spec_json` 读不回自己写出的 spec（编码/结构）→
    语料互喂（docs/41 §A3）失效。
    """
    path = os.path.join(isolated_sigma_tmp, "spec.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(spec, fh, ensure_ascii=False)
    loaded = S.load_spec_json(path)
    assert loaded['spec'] == spec['spec']
    assert S.validate_spec_json(loaded) == []


def test_fingerprint_is_stable_and_content_sensitive(module):
    """退步了会怎样：指纹不稳定（同内容两次不同）或对内容不敏感（改了还是同指纹）
    → 规约防篡改/对账失去意义。
    """
    a = S.fingerprint_of(S.parse_module_text(BASE_MODULE))
    b = S.fingerprint_of(S.parse_module_text(BASE_MODULE))
    c = S.fingerprint_of(S.parse_module_text(BASE_MODULE.replace('0.1.0', '0.2.0')))
    assert a == b and a.startswith('sha256:')
    assert a != c, "内容改了指纹却不变"
    assert S.fingerprint_of_spec(S.to_spec_json(module)).startswith('sha256:')


def test_spec_to_assertions_and_judge_spec(spec, module):
    """退步了会怎样：spec → 断言集漂移（漏规范测试/漏定律）→ 互喂断言不完整；
    judge 对**含 `⊥` 负向用例的合法 spec** 判 WA（第 32 轮 A4 修复前：拿输入串
    直接比，`expected error DivByZero, got '0 ⊘ 0'`）→ 任何带负向用例的 spec
    恒 exit 1，bootstrap/语料互喂闭环失效。
    """
    assertions = S.spec_to_assertions(spec)
    ids = {a.get('id') for a in assertions}
    assert ids == {'f#t1', 'f#t2', 'f#law1'}, ids

    judged = S.judge_spec(spec=spec)          # 含 1 条正向 + 1 条 ⊥ 负向用例
    assert judged['summary'] == {'total': 2, 'pass': 2, 'wa': 0}, judged['summary']
    assert judged['exit_code'] == 0
    neg = [v for v in judged['verdicts'] if v.get('expect_error')]
    assert neg and neg[0]['verdict'] == 'PASS', neg


def test_judge_spec_still_flags_wrong_spec():
    """退步了会怎样：A4 修复把负向用例放开过头 —— 连"期望值写错""错误名写错"
    的 spec 也判 PASS → judge 变成永远绿（假验收）。
    """
    wrong_out = S.to_spec_json(
        S.parse_module_text(BASE_MODULE.replace('| 1 ⊕ 1 | 2 |', '| 1 ⊕ 1 | 7 |')))
    judged = S.judge_spec(spec=wrong_out)
    assert judged['summary']['wa'] >= 1 and judged['exit_code'] == 1

    wrong_err = S.to_spec_json(
        S.parse_module_text(BASE_MODULE.replace('| 0 ⊘ 0 | ⊥ DivByZero |',
                                                '| 0 ⊘ 0 | ⊥ TypeError |')))
    judged2 = S.judge_spec(spec=wrong_err)
    assert judged2['summary']['wa'] >= 1 and judged2['exit_code'] == 1


def test_render_impl_skeleton_produces_ops(spec):
    """退步了会怎样：实现骨架生成器丢操作/输出非法内容 → bootstrap 闭环
    （spec → impl → verify）变成假功能。
    """
    skeleton = S.render_impl_skeleton(spec)
    assert isinstance(skeleton, str) and skeleton.strip()
    assert 'def ' in skeleton, "骨架里应包含函数定义"
    assert 'f' in skeleton


# ═══════════════════════════════════════════════════════════════════
# ⑧ 引擎（SigmaEngine / _ExprEvaluator）
# ═══════════════════════════════════════════════════════════════════


def test_engine_evaluates_spec_operations(spec):
    """退步了会怎样：引擎按 spec 求值失败（或返回 None）→ 语料互喂执行端整体失效。
    """
    engine = S.SigmaEngine(spec)
    assert 'f' in engine.operations
    assert engine.eval('f', [('num', 3)]) == ('num', 3)


def test_engine_rejects_wrong_arity_and_unknown_op(spec):
    """退步了会怎样：参数个数不校验/未知操作不报错 → spec 写错也"跑成功"
    （假绿），门禁形同虚设。
    """
    engine = S.SigmaEngine(spec)
    with pytest.raises(S.IronLawViolation):
        engine.eval('f', [])
    with pytest.raises(S.UnknownOpError):
        engine.eval('nope', [('num', 1)])


def test_engine_rejects_bad_spec_shape():
    """退步了会怎样：坏 spec（operations 不是列表 / op 无 name）被接受 → 引擎在
    更深的位置抛 KeyError，排查困难。
    """
    with pytest.raises(S.SpecValidationError):
        S.SigmaEngine({'operations': 'nope'})
    with pytest.raises(S.SpecValidationError):
        S.SigmaEngine({'operations': [{}]})


def test_engine_precondition_failure_is_structured():
    """退步了会怎样：前置条件失败被吞（或抛裸断言）→ 规约的 pre 条件变成装饰。

    spec 结构（与 `to_spec_json` 生成的形状一致）：`preconditions[].expr` 是
    **可求值的表达式字符串**（在 params 环境里 eval），`definition.body` 同理。
    """
    spec = {
        'spec': 'x.y', 'version': '0.1.0', 'fingerprint_prefix': '0xA0000',
        'types': [], 'operations': [{
            'name': 'g', 'signature': {'params': ['a']},
            'preconditions': [{'expr': 'a[1] >= 0', 'error': 'StateError',
                               'description': 'must be >= 0'}],
            'definition': {'kind': 'expression', 'params': ['a'], 'body': 'a'},
        }],
    }
    engine = S.SigmaEngine(spec)
    assert engine.eval('g', [('num', 1)]) == ('num', 1)
    with pytest.raises(S.IronLawViolation) as exc:
        engine.eval('g', [('num', -1)])
    assert 'must be >= 0' in str(exc.value)


# ═══════════════════════════════════════════════════════════════════
# ⑨ 块入口（extract / scan_fenced / loadable / run）
# ═══════════════════════════════════════════════════════════════════


def test_extract_sigma_block_variants():
    """退步了会怎样：围栏提取把正文/前后记混进来，或没有围栏时返回非空 →
    解析到混合内容、失败原因误导。
    """
    text = "说明文字\n```sigma\n" + BASE_MODULE + "```\n后记\n"
    body = S.extract_sigma_block(text)
    assert body.strip().startswith('# Module: audit.demo')
    assert '后记' not in body
    assert S.extract_sigma_block('no fence at all') == ''


def test_scan_fenced_greedy_modes():
    """退步了会怎样：greedy/non-greedy 两种扫描语义互换 → 多块文档里解析到错误的块
    （首个 vs 全部），三端行为不一致。
    """
    two = "```sigma\n# Module: a\n```\n```sigma\n# Module: b\n```\n"
    assert S._scan_fenced(two, False).strip() == '# Module: a'
    greedy = S._scan_fenced(two, True)
    assert '# Module: a' in greedy and '# Module: b' in greedy


def test_sigma_block_is_loadable_edges():
    """退步了会怎样：空块/只有签名声明被判可加载（历史 P1）→ 零操作规约真空通过。
    """
    assert S.sigma_block_is_loadable('') == (False, 'sigma 规约块为空')
    ok, err = S.sigma_block_is_loadable(BASE_MODULE)
    assert (ok, err) == (True, None)
    ok2, err2 = S.sigma_block_is_loadable(
        "# Module: x\n## Operation: g (ℕ)\n### Signature\ng: ℕ → ℕ\n")
    assert ok2 is False and '没有任何 Operation' in err2


def test_run_sigma_block_contracts():
    """退步了会怎样：块入口的 exit code 与 stdout/stderr 契约漂移 → md 引擎
    会把失败规约当成功执行（假绿）。
    """
    out, err, rc = S.run_sigma_block(BASE_MODULE)
    assert rc == 0 and 'PASS' in out.upper()
    assert err == ''

    bad = BASE_MODULE.replace('| 1 ⊕ 1 | 2 |', '| 1 ⊕ 1 | 3 |')
    out2, _err2, rc2 = S.run_sigma_block(bad)
    assert rc2 == 1 and 'FAIL' in out2.upper()

    out3, err3, rc3 = S.run_sigma_block('garbage')
    assert rc3 == 1 and '未定义任何操作' in err3

    out_json, _e, rc4 = S.run_sigma_block(BASE_MODULE, as_json=True)
    payload = json.loads(out_json)
    assert rc4 == 0 and payload['verdict'] == 'pass'


def test_is_sigma_language_and_package():
    """退步了会怎样：语言标记判定放宽/收紧 → 非 sigma 块被当规约执行（或反之）；
    包前言解析失效 → L1/L2 包模块无法识别。
    """
    assert S.is_sigma_language('sigma') is True
    assert S.is_sigma_language('python') is False
    assert S.parse_package('/tmp/definitely-missing-pkg') is None


@pytest.fixture
def isolated_sigma_tmp():
    """隔离临时目录（不碰真实用户目录）。"""
    d = tempfile.mkdtemp(prefix="sigma-r32-")
    yield d
