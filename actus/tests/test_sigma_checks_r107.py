# -*- coding: utf-8 -*-
"""actus/tests/test_sigma_checks_r107.py — sigma 门禁校验家族专项（统帅轮-13时）。

测什么 / 为什么
---------------
`sigma.py` 的 check_* 家族（Law I-XVII，module dict → List[str] 错误清单契约）
此前 grep 全 tests/ 零直接引用（COVERAGE_AUDIT_R105 审计锁定 14-16 个零覆盖，
高价值第一批：误判=坏动作放行/好动作误杀，直接影响信任模型）。本文件逐 Law
覆盖「合法 module 通过 + 针对性破坏命中 + 边界形态」。

怎么测
------
* `_module()` 工厂造默认合法基线，各 Law 用 kwargs 覆盖破坏点；
* Law XIII（consensus）按实现语义是 advisory 恒空——如实测恒空契约；
* eval_compat_test / 独立 0/1 锚正则（_CALIBRATION_ANCHOR_RE）边界一并锚定。

py3.8+（pyproject requires-python>=3.8），标准库。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

from vools.actus.sigma import (  # noqa: E402
    check_backward_compat,
    check_calibration,
    check_capabilities,
    check_compat_proof,
    check_consensus,
    check_dependencies,
    check_effect_transparency,
    check_encoding,
    check_export_completeness,
    check_fingerprint_uniqueness,
    check_guarantee,
    check_law_declaration,
    check_negative_tests,
    check_no_implementation,
    check_resource_linearity,
    check_tests_mandatory,
    check_timing_contract,
)


# ---------------------------------------------------------------------------
# module dict 工厂：默认完全合法基线
# ---------------------------------------------------------------------------

def _op(**kw):
    base = {
        "name": "core.add",
        "fp": "a1b2c3d4e5f60718",
        "sig": "core.add: (ℕ, ℕ) → ℕ",
        "laws": ["Law: 加法交换律（0 与 1 锚定校准）"],
        "tests": [("1+1", "2"), ("⊥", "⊥")],
        "definition": [],
    }
    base.update(kw)
    return base


def _module(**kw):
    base = {
        "name": "core",
        "version": "1.0.0",
        "ops": [_op()],
        "fns": [],
        "imports": ["core"],
        "timing_contract": {"latency": "sync"},
        "capabilities": [],
        "exports": ["core.add"],
        "compat_tests": [],
        "guarantee_declared": False,
    }
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# Law I 指纹唯一性
# ---------------------------------------------------------------------------

def test_law1_unique_fingerprints_pass():
    m = _module(ops=[_op(fp="aa11"), _op(name="core.sub", fp="bb22")])
    assert check_fingerprint_uniqueness(m) == []


def test_law1_missing_fingerprint_hits():
    m = _module(ops=[_op(fp=None)])
    out = check_fingerprint_uniqueness(m)
    assert out == ["MissingFingerprint(core.add)"]


def test_law1_conflict_hits():
    m = _module(ops=[_op(fp="aa11"), _op(name="core.sub", fp="aa11")])
    out = check_fingerprint_uniqueness(m)
    assert out == ["FingerprintConflict(core.sub, aa11)"]


# ---------------------------------------------------------------------------
# Law II 编码声明（审计修正口径：空壳声明不算、签名结构化对应）
# ---------------------------------------------------------------------------

def test_law2_numeric_return_passes():
    m = _module()          # 默认 op 返回 ℕ（数值）
    assert check_encoding(m) == []


def test_law2_non_numeric_without_encoder_hits():
    m = _module(ops=[_op(sig="core.label: ℕ → Str")])
    out = check_encoding(m)
    assert out == ["MissingEncoding(core.add)"]


def test_law2_hollow_encoder_rejected():
    """审计修正回归：空壳 encoder（无指纹无定义）不满足编码要求。"""
    m = _module(
        fns=[{"name": "encode_label", "sig": "encode_label: Str → ℕ",
              "fp": None, "definition": []}],
        ops=[_op(sig="core.label: ℕ → Str")],
    )
    out = check_encoding(m)
    assert out == ["MissingEncoding(core.add)"]


def test_law2_real_encoder_satisfies():
    """有指纹的真 encoder，签名结构化对应（参数含 Str、返回 ℕ）→ 通过。"""
    m = _module(
        fns=[{"name": "encode_label", "sig": "encode_label: Str → ℕ",
              "fp": "cc33", "definition": ["..."]}],
        ops=[_op(sig="core.label: ℕ → Str")],
    )
    assert check_encoding(m) == []


# ---------------------------------------------------------------------------
# Law III/IV 定律与测试声明
# ---------------------------------------------------------------------------

def test_law3_no_laws_hits():
    m = _module(ops=[_op(laws=[])])
    assert check_law_declaration(m) == ["NoLawsDeclared(core.add)"]


def test_law4_no_tests_hits():
    m = _module(ops=[_op(tests=[])])
    assert check_tests_mandatory(m) == ["NoTestsDefined(core.add)"]


# ---------------------------------------------------------------------------
# Law V 实现泄漏
# ---------------------------------------------------------------------------

def test_law5_clean_passes():
    assert check_no_implementation(_module()) == []


def test_law5_forbidden_keyword_hits():
    m = _module(ops=[_op(definition=["use a for loop to iterate"])])
    assert check_no_implementation(m) == ["ImplementationLeak(core.add)"]


# ---------------------------------------------------------------------------
# Law VI 版本形态
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("version,ok", [
    ("1.0.0", True), ("0.9.0", True), ("10.20.30", True),
    ("1.0", False), ("v1.0.0", False), ("1.0.0-beta", False), ("", False),
])
def test_law6_semver_shapes(version, ok):
    m = _module(version=version)
    out = check_backward_compat(m)
    assert (out == []) is ok


# ---------------------------------------------------------------------------
# Law VII 依赖
# ---------------------------------------------------------------------------

def test_law7_dependencies_ok():
    """module name 不得出现在自己的 imports（SelfDependency 判据），
    合法基线用 name=basemod + imports=[core]。"""
    m = _module(name="basemod", imports=["core"])
    assert check_dependencies(m) == []


def test_law7_no_core_and_self_and_dup_hits():
    m = _module(name="basemod", imports=["util", "util", "core2"])
    out = check_dependencies(m)
    assert "NoCoreImport(basemod)" in out
    assert "DuplicateImport(util)" in out
    m2 = _module(name="core", imports=["core", "core"])
    out2 = check_dependencies(m2)
    assert "SelfDependency(core)" in out2


# ---------------------------------------------------------------------------
# Law VIII 时序契约
# ---------------------------------------------------------------------------

def test_law8_io_without_contract_hits():
    m = _module(ops=[_op(definition=["print(value)"])],
                timing_contract=None)
    assert check_timing_contract(m) == ["NoTimingContract(core)"]


def test_law8_io_with_contract_passes():
    m = _module(ops=[_op(definition=["print(value)"])],
                timing_contract={"latency": "async"})
    assert check_timing_contract(m) == []


def test_law8_no_io_no_contract_required():
    m = _module(ops=[_op(definition=[])], timing_contract=None)
    assert check_timing_contract(m) == []


# ---------------------------------------------------------------------------
# Law IX 校准锚（独立 0/1 字面量）
# ---------------------------------------------------------------------------

def test_law9_conf_with_anchors_passes():
    m = _module(ops=[_op(sig="core.score: (ℕ) → Conf",
                         laws=["校准锚：0 表示不一致，1 表示一致"])])
    assert check_calibration(m) == []


def test_law9_conf_without_anchors_hits():
    m = _module(ops=[_op(sig="core.score: (ℕ) → Conf",
                         laws=["见 RFC 1.0 的锚定"])])
    out = check_calibration(m)
    assert out == ["Uncalibrated(core.add)"]


def test_law9_decimal_contamination_rejected():
    """1.0/10/0.5 里夹带的 0/1 不算独立字面量（边界回归）。"""
    m = _module(ops=[_op(sig="core.score: (ℕ) → Conf",
                         laws=["锚定值 1.0 与 10 一致"])])
    assert check_calibration(m) == ["Uncalibrated(core.add)"]


# ---------------------------------------------------------------------------
# Law X 效应声明
# ---------------------------------------------------------------------------

def test_law10_undeclared_effect_hits():
    m = _module(ops=[_op(definition=["print(value)"])],
                capabilities=[], timing_contract={})
    assert check_effect_transparency(m) == ["UndeclaredEffect(core.add, IO)"]


def test_law10_declared_effect_passes():
    m = _module(ops=[_op(definition=["print(value)"])],
                capabilities=["IO"], timing_contract={})
    assert check_effect_transparency(m) == []


# ---------------------------------------------------------------------------
# Law XI 能力声明（marker 表逐字移植）
# ---------------------------------------------------------------------------

def test_law11_missing_capability_hits():
    m = _module(ops=[_op(definition=["read_file(path)"])], capabilities=[])
    out = check_capabilities(m)
    assert out == ["MissingCapability(core.add, ReadFile)"]


def test_law11_all_markers_table():
    """marker 表五族逐一命中（CmdExec/Network/SpawnAgent/WriteFile）。"""
    cases = [
        ("exec(cmd)", "CmdExec"),
        ("http_get(url)", "Network"),
        ("spawn(worker)", "SpawnAgent"),
        ("write_file(p)", "WriteFile"),
    ]
    for body, cap in cases:
        m = _module(ops=[_op(definition=[body])], capabilities=[])
        assert check_capabilities(m) == [
            "MissingCapability(core.add, %s)" % cap], body


def test_law11_declared_capability_passes():
    m = _module(ops=[_op(definition=["read_file(path)"])], capabilities=["ReadFile"])
    assert check_capabilities(m) == []


# ---------------------------------------------------------------------------
# Law XII 资源线性（open 恰好 close 一次）
# ---------------------------------------------------------------------------

def test_law12_resource_leak_hits():
    m = _module(ops=[_op(definition=["open(f)", "use(f)"])])
    assert check_resource_linearity(m) == ["ResourceLeak(core.add:f)"]


def test_law12_double_close_hits():
    m = _module(ops=[_op(definition=["open(f)", "close(f)", "close(f)"])])
    assert check_resource_linearity(m) == ["DoubleClose(core.add:f)"]


def test_law12_use_after_close_hits():
    m = _module(ops=[_op(definition=["open(f)", "close(f)", "use(f)"])])
    assert check_resource_linearity(m) == ["UseAfterClose(core.add:f)"]


def test_law12_balanced_passes():
    m = _module(ops=[_op(definition=["open(f)", "use(f)", "close(f)"])])
    assert check_resource_linearity(m) == []


# ---------------------------------------------------------------------------
# Law XIII 共识（advisory 恒空契约）
# ---------------------------------------------------------------------------

def test_law13_advisory_always_empty():
    """实现语义：单端无法判定共识，记 advisory 恒空——不判失败也不谎报通过。"""
    assert check_consensus(_module()) == []


# ---------------------------------------------------------------------------
# Law XIV 负向测试
# ---------------------------------------------------------------------------

def test_law14_no_negative_test_hits():
    m = _module(ops=[_op(tests=[("1+1", "2")])])
    assert check_negative_tests(m) == ["NoNegativeTest(core.add)"]


def test_law14_bottom_test_passes():
    m = _module(ops=[_op(tests=[("⊥", "⊥")])])
    assert check_negative_tests(m) == []


# ---------------------------------------------------------------------------
# Law XV 导出完整性
# ---------------------------------------------------------------------------

def test_law15_ghost_export_hits():
    m = _module(exports=["core.add", "core.ghost"])
    out = check_export_completeness(m)
    assert "GhostExport(core.ghost)" in out


def test_law15_hidden_export_hits():
    m = _module(ops=[_op(), _op(name="core.hidden")],
                exports=["core.add"])
    assert "HiddenExport(core.hidden)" in check_export_completeness(m)


def test_law15_empty_exports_policy():
    """无 Exports 块不检查（v0.1 政策）。"""
    assert check_export_completeness(_module(exports=[])) == []


# ---------------------------------------------------------------------------
# Law XVI Compat Tests
# ---------------------------------------------------------------------------

def test_law16_empty_compat_tests_passes():
    assert check_compat_proof(_module()) == []


def test_law16_failing_compat_test_hits():
    m = _module(compat_tests=[("1+1", "3")])   # 显然失败
    out = check_compat_proof(m)
    assert out and out[0].startswith("CompatTestFailed(1+1)")


# ---------------------------------------------------------------------------
# Law XVII 概率保证
# ---------------------------------------------------------------------------

def test_law17_undeclared_guarantee_skips():
    assert check_guarantee(_module(guarantee_declared=False)) == []
