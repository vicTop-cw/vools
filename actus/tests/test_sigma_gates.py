# -*- coding: utf-8 -*-
"""actus/tests/test_sigma_gates.py — sigma 门禁语义回归（审计修复的 4 条 P1 + P2）。

背景：`sigma.py`（3058 行）此前**零测试覆盖**，所以下面这些缺陷长期存在：
  1. `check_iron_laws().passed` 完全不含规范测试结果 → 一条 `0/2 全挂` 的规约照样
     pass、`verify_module` verdict=pass、`run_sigma_block` exit 0；
  2. `_module_from_spec()` 丢 imports/tests → `bootstrap(spec=...)` 永远过不了第 1 步
     （文档承诺的 spec → impl → verify 闭环 = 假功能）；
  3. spec 自洽 judge 用 `'1' == 1` 比较 → 任何合法 spec 恒 exit 1；
  4. 漏写 `Fingerprint:` 的 Operation 被静默降级成声明 fn → Law I 的
     MissingFingerprint 不可达，且"零操作"规约真空通过；
  5. Law IX 校准判据是子串（`RFC 1.0` 就算锚定 0/1）、Law II 空壳 encoder 即通过。

本文件逐条钉住修复后的语义（反例构造 + 显式断言）。不依赖本机装了什么。
py3.6 兼容：标准库 + % 格式化。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

from vools.actus import sigma  # noqa: E402


# 一份"结构合法且规范测试全过"的最小规约（sigma 运算符是 unicode 字形，不是 +-*/）
_BASE = """# Module: audit.demo
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
| 0 ⊘ 0 | ⊥ |
### Definition
arg0
Fingerprint: 0xA001
"""


def _module(text=_BASE):
    return sigma.parse_module_text(text)


# ---------------------------------------------------------------------------
# P1-1：规范测试失败必须拦住门禁
# ---------------------------------------------------------------------------

def test_failing_canonical_tests_block_gate():
    """测试 0/2 全挂 → passed=False / verdict=fail / run_sigma_block exit=1。"""
    bad = _BASE.replace("| 1 ⊕ 1 | 2 |", "| 1 ⊕ 1 | 3 |").replace(
        "| 0 ⊘ 0 | ⊥ |", "| 1 ⊕ 1 | 9 |")
    report = sigma.check_iron_laws(_module(bad))
    assert report["tests"]["total"] == 2
    assert len(report["tests"]["failures"]) == 2, report["tests"]
    assert report["passed"] is False, "测试全挂却判通过（P1 回归）"
    assert sigma.verify_module(_module(bad))["verdict"] == "fail"
    out, err, rc = sigma.run_sigma_block(bad)
    assert rc == 1, "run_sigma_block 未拦住全失败测试"
    assert "0/2" in out


def test_passing_tests_still_pass():
    """测试全过时不能被新判据误杀（反向保护）。"""
    report = sigma.check_iron_laws(_module())
    assert report["passed"] is True, report["failed_laws"]
    assert sigma.run_sigma_block(_BASE)[2] == 0


def test_strict_false_does_not_skip_tests():
    """宽松模式只能放宽补充细则，**不许**放过测试失败（lead 明确禁止双轨）。"""
    bad = _BASE.replace("| 1 ⊕ 1 | 2 |", "| 1 ⊕ 1 | 3 |")
    assert sigma.check_iron_laws(_module(bad), strict=False)["passed"] is False


# ---------------------------------------------------------------------------
# P1-2：spec JSON 往返可逆（imports + tests 不丢）
# ---------------------------------------------------------------------------

def test_spec_roundtrip_preserves_imports_and_tests():
    """to_spec_json → _module_from_spec 的 Iron Laws 结果与直接读 MD 等价。"""
    md_report = sigma.check_iron_laws(_module())
    spec = sigma.to_spec_json(_module())
    assert (spec.get("meta") or {}).get("imports") == ["core"]
    roundtrip = sigma._module_from_spec(spec)
    assert roundtrip["imports"] == ["core"], "imports 在 spec 往返中丢失"
    spec_report = sigma.check_iron_laws(roundtrip)
    assert spec_report["passed"] == md_report["passed"] is True, spec_report["failed_laws"]
    assert spec_report["tests"]["total"] == 2
    assert spec_report["tests"]["passed"] == md_report["tests"]["passed"] == 2
    assert roundtrip["ops"][0]["tests"] == [("1 ⊕ 1", "2"), ("0 ⊘ 0", "⊥")]


def test_bootstrap_spec_path_passes_step1():
    """spec JSON 路径不得因 NoCoreImport/NoTestsDefined 恒卡第 1 步。"""
    import tempfile
    spec = sigma.to_spec_json(_module())
    report = sigma.bootstrap(spec=spec, out_dir=tempfile.mkdtemp())
    steps = {s["step"]: s for s in report["steps"]}
    assert steps["spec_readable"]["ok"] is True, steps["spec_readable"]["detail"]
    assert steps["spec_json_valid"]["ok"] is True


# ---------------------------------------------------------------------------
# P1-3：judge 两侧归一（'1' 与 1 不算不同答案）
# ---------------------------------------------------------------------------

def test_judge_self_consistency_normalizes_literals():
    """常量定义 + 相同期望 → PASS；期望不同 → WA（两种 instance 都验）。"""
    pass_spec = sigma.to_spec_json(_module(
        _BASE.replace("| 1 ⊕ 1 | 2 |\n| 0 ⊘ 0 | ⊥ |", "| 1 | 1 |")))
    judged = sigma.judge_spec(spec=pass_spec)
    assert judged["exit_code"] == 0, judged["verdicts"]
    assert judged["summary"]["pass"] == judged["summary"]["total"] == 1

    wa_spec = sigma.to_spec_json(_module(
        _BASE.replace("| 1 ⊕ 1 | 2 |\n| 0 ⊘ 0 | ⊥ |", "| 1 | 2 |")))
    judged_wa = sigma.judge_spec(spec=wa_spec)
    assert judged_wa["exit_code"] == 1
    assert judged_wa["summary"]["wa"] == 1, judged_wa["verdicts"]


# ---------------------------------------------------------------------------
# P1-4：缺 Fingerprint 必须报 MissingFingerprint，且不许"零操作真空通过"
# ---------------------------------------------------------------------------

def test_missing_fingerprint_is_reported_not_silently_dropped():
    no_fp = _BASE.replace("Fingerprint: 0xA001\n", "")
    module = _module(no_fp)
    assert len(module["ops"]) == 1, "缺指纹的 Operation 被静默降级成 fn 了"
    report = sigma.check_iron_laws(module)
    law1 = next(entry for entry in report["laws"] if entry["id"] == "I")
    assert law1["violations"] == ["MissingFingerprint(f)"]
    assert report["passed"] is False
    assert sigma.run_sigma_block(no_fp)[2] == 1


def test_spec_with_no_operations_is_not_loadable():
    text = "# Module: audit.empty\n# Version: 0.1.0\n\n## Imports\nimport core\n"
    ok, reason = sigma.sigma_block_is_loadable(text)
    assert ok is False and "Operation" in reason
    assert sigma.run_sigma_block(text)[2] == 1


# ---------------------------------------------------------------------------
# P2：Law IX / Law II 判据强度
# ---------------------------------------------------------------------------

def test_law_ix_requires_real_calibration_anchor():
    """注释里的版本号 `RFC 1.0` 不再被当成 0/1 校准锚点。"""
    fake = (_BASE.replace("f: ℕ → ℕ", "f: ℕ → Conf")
                 .replace("∀x: f(x) ≡ x", "∀x: f(x) ≡ g(x) # 见 RFC 1.0"))
    law9 = next(entry for entry in sigma.check_iron_laws(_module(fake))["laws"] if entry["id"] == "IX")
    assert law9["violations"] == ["Uncalibrated(f)"]

    real = (_BASE.replace("f: ℕ → ℕ", "f: ℕ → Conf")
                 .replace("∀x: f(x) ≡ x", "∀x: f(x) ≡ 0 ∨ f(x) ≡ 1"))
    law9_ok = next(entry for entry in sigma.check_iron_laws(_module(real))["laws"] if entry["id"] == "IX")
    assert law9_ok["violations"] == []


def test_law_ii_rejects_bare_encoder_declaration():
    """只有签名、没有指纹/定义的 encoder 不足以满足"编码到 ℕ"。"""
    bare = (_BASE.replace("f: ℕ → ℕ", "f: ℕ → Str")
                 .replace("## Exports\nf",
                          "## Exports\nf\n\n## Operation: encode_str (Str)\n"
                          "### Signature\nencode: Str → ℕ\n"))
    law2 = next(entry for entry in sigma.check_iron_laws(_module(bare))["laws"] if entry["id"] == "II")
    assert law2["violations"] == ["MissingEncoding(f)"]

    real = bare.replace(
        "## Operation: encode_str (Str)\n### Signature\nencode: Str → ℕ\n",
        "## Operation: encode_str (Str)\n### Signature\nencode: Str → ℕ\n"
        "### Definition\n0\nFingerprint: 0xE001\n")
    law2_ok = next(entry for entry in sigma.check_iron_laws(_module(real))["laws"] if entry["id"] == "II")
    assert law2_ok["violations"] == []


# ---------------------------------------------------------------------------
# P3：未声明 → skipped（不是静默 pass）
# ---------------------------------------------------------------------------

def test_undeclared_sections_marked_skipped():
    text = _BASE.replace("## Exports\nf\n\n", "")
    report = sigma.check_iron_laws(_module(text))
    skipped_ids = {entry["id"] for entry in report["skipped_laws"]}
    assert "XV" in skipped_ids
    assert "XVII" in skipped_ids
    for entry in report["laws"]:
        if entry["id"] in ("XV", "XVII"):
            assert entry["status"] == "skipped", entry
    assert "check_package_signature" in report["supplemental_skipped"]


# ===========================================================================
# 追加覆盖：17 条 Iron Law 逐条反例（可机检 16 条）+ judge 对外部实现的归一
#
# 上面的用例覆盖 4 条 P1 的主线；这里补两块此前没有的、也是最有价值的：
#   A. 每条可机检定律各造**只破坏它**的反例，防止某条 check 退化成空实现；
#   B. judge 对着**外部实现**的正确/错误两种结果（P1#3 不能只验自洽）。
# ===========================================================================

def _law_of(result, law_id):
    """取某条定律的判定条目（不存在直接断言失败，避免静默跳过）。"""
    for entry in result["laws"]:
        if entry["id"] == law_id:
            return entry
    raise AssertionError("结果里没有 Law %r（实得 %s）" % (
        law_id, [entry["id"] for entry in result["laws"]]))


def _gate_variant(*replacements):
    """在 _BASE 上做定点替换构造反例；替换不中即失败（防止反例悄悄失效）。"""
    text = _BASE
    for old, new in replacements:
        assert old in text, "反例构造失败：_BASE 里没有 %r" % (old,)
        text = text.replace(old, new)
    return text


# (law_id, 只破坏该定律的规约, 预期违规名)
_COUNTEREXAMPLES = [
    ("I", _gate_variant(("Fingerprint: 0xA001\n", "")), "MissingFingerprint"),
    ("II", _gate_variant(("f: ℕ → ℕ", "f: ℕ → Str")), "MissingEncoding"),
    ("III", _gate_variant(("∀x: f(x) ≡ x\n", "")), "NoLawsDeclared"),
    ("IV", _gate_variant(("| Input | Output |\n| 1 ⊕ 1 | 2 |\n| 0 ⊘ 0 | ⊥ |\n", "")),
     "NoTestsDefined"),
    ("V", _gate_variant(("### Definition\narg0", "### Definition\nwhile loop {}")),
     "ImplementationLeak"),
    ("VI", _gate_variant(("# Version: 0.1.0", "# Version: 1.0")), "MalformedVersion"),
    ("VII", _gate_variant(("import core\n", "")), "NoCoreImport"),
    ("VIII", _gate_variant(("### Definition\narg0",
                            "### Definition\nprint(\"hi\")")), "NoTimingContract"),
    ("IX", _gate_variant(("f: ℕ → ℕ", "f: ℕ → Conf"),
                         ("∀x: f(x) ≡ x", "∀x: f(x) ≡ g(x)")), "Uncalibrated"),
    ("X", _gate_variant(("### Definition\narg0",
                         "### Definition\nread_file(p)")), "UndeclaredEffect"),
    ("XI", _gate_variant(("### Definition\narg0",
                          "### Definition\nread_file(p)")), "MissingCapability"),
    ("XII", _gate_variant(("### Definition\narg0",
                           "### Definition\nopen(r1)")), "ResourceLeak"),
    ("XIV", _gate_variant(("| 0 ⊘ 0 | ⊥ |\n", "")), "NoNegativeTest"),
    ("XV", _gate_variant(("## Exports\nf", "## Exports\nf, ghost")), "GhostExport"),
    ("XVI", _gate_variant(("Fingerprint: 0xA001",
                           "Fingerprint: 0xA001\n\n## Compat Tests\n"
                           "| Input | Output |\n| 1 ⊕ 1 | 3 |")), "CompatTestFailed"),
    ("XVII", _gate_variant(("Fingerprint: 0xA001",
                            "Fingerprint: 0xA001\n\n## Guarantee\n"
                            "metric: nonsense\nthreshold: 0.9\ndataset: d")),
     "MalformedGuarantee"),
]


@pytest.mark.parametrize("law_id,text,expected_violation", _COUNTEREXAMPLES,
                         ids=[case[0] for case in _COUNTEREXAMPLES])
def test_each_machine_checkable_iron_law_catches_its_counterexample(
        law_id, text, expected_violation):
    """退步了会怎样：某条定律的 check 变成空实现 / 漏掉某个判据 → 它的反例不再
    产生违规，门禁对该类缺陷彻底失明（不崩、不报错，只是静默放行）。

    对每条可机检定律只破坏对应的一处，断言：
    该定律 violations 非空且含预期违规名 + 整体 passed=False + run_sigma_block exit=1。
    （Law XIII verifier consensus 不可机检，单独用 advisory 用例钉住。）
    """
    result = sigma.check_iron_laws(_module(text))
    violations = _law_of(result, law_id)["violations"]

    assert any(expected_violation in item for item in violations), \
        "Law %s 没抓到自己的反例（期望违规含 %r，实得 %r）" % (
            law_id, expected_violation, violations)
    assert result["passed"] is False, "Law %s 违规时整体不该 pass" % law_id
    assert sigma.run_sigma_block(text)[2] == 1


def test_p1_failed_canonical_tests_alone_block_the_gate():
    """退步了会怎样（P1#1 精确面）：测试失败之外没有任何定律违规，门禁仍然 pass。

    与上面的 `test_failing_canonical_tests_block_gate` 互补：这里额外断言
    `failed_laws` 为空、`test_failures` 非零 —— 证明拦下它的是**测试门禁**
    而不是碰巧有别的定律违规（避免"用别的违规掩盖测试门禁失效"）。
    """
    bad = _BASE.replace("| 1 ⊕ 1 | 2 |", "| 1 ⊕ 1 | 3 |")
    report = sigma.check_iron_laws(_module(bad))

    assert report["failed_laws"] == [], "该反例不应违反任何定律: %r" % (
        [entry["id"] for entry in report["failed_laws"]],)
    assert report["test_failures"] >= 1
    assert report["passed"] is False, "只有测试失败也必须拦下（P1#1 复活）"


def test_p1_law13_consensus_is_advisory_not_fake_pass():
    """退步了会怎样：不可机检的 Law XIII 被当成 `pass` 混进「17 条全过」，
    冒充已由两个验证器对齐（单端根本没有 consensus 可判）。

    断言基线模块：XIII 在 advisory_laws、不在 failed_laws、无违规文本；
    passed 仍为 True（advisory 不阻断，但必须对消费方可见）。
    """
    report = sigma.check_iron_laws(_module())
    advisory_ids = [entry["id"] for entry in report["advisory_laws"]]

    assert "XIII" in advisory_ids, \
        "Law XIII 必须显式出现在 advisory_laws，实得 %r" % (advisory_ids,)
    assert "XIII" not in [entry["id"] for entry in report["failed_laws"]]
    assert _law_of(report, "XIII")["violations"] == []


def _judge_spec_for_definition(definition, tests):
    """用常量/带参 Definition 构造一份 spec（复用 _BASE 的 imports/exports/签名）。"""
    text = _BASE.replace("| 1 ⊕ 1 | 2 |\n| 0 ⊘ 0 | ⊥ |", tests)
    text = text.replace("### Definition\narg0", "### Definition\n" + definition)
    return sigma.to_spec_json(sigma.parse_module_text(text), spec_id="judge.demo")


@pytest.mark.parametrize("impl_value,should_pass", [(1, True), (2, False)],
                         ids=["correct-impl", "wrong-impl"])
def test_p1_judge_constant_definition_checks_external_impl(impl_value, should_pass):
    """退步了会怎样：judge 对「常量定义」要么恒过（错误实现也 PASS）要么恒 WA
    （正确实现也挂）—— P1#3 只修自洽、没修对外比较时就会这样。

    断言：实现返回 1 → PASS/exit 0；返回 2 → WA/exit 1。
    """
    spec = _judge_spec_for_definition("1", "| 1 | 1 |")
    result = sigma.judge_spec(spec=spec, impl={"f": lambda x: impl_value})

    if should_pass:
        assert result["exit_code"] == 0
        assert result["verdicts"][0]["verdict"] == "PASS"
    else:
        assert result["exit_code"] == 1
        assert result["verdicts"][0]["verdict"] == "WA"


@pytest.mark.parametrize("impl_value,should_pass", [(1, True), (2, False)],
                         ids=["correct-impl", "wrong-impl"])
def test_p1_judge_param_definition_checks_external_impl(impl_value, should_pass):
    """退步了会怎样（P1#3 带参定义）：identity 定义（`### Definition\\narg0`）下，
    judge 对着外部实现跑时正确实现被误判 WA / 错误实现被放行。

    断言：`lambda x: x`（输入 1 得 1）→ PASS/exit 0；
    `lambda x: x + 1`（得 2）→ WA/exit 1。
    """
    spec = _judge_spec_for_definition("arg0", "| 1 | 1 |")
    result = sigma.judge_spec(spec=spec, impl={"f": lambda x: impl_value})

    if should_pass:
        assert result["exit_code"] == 0
        assert result["verdicts"][0]["verdict"] == "PASS"
    else:
        assert result["exit_code"] == 1
        assert result["verdicts"][0]["verdict"] == "WA"
