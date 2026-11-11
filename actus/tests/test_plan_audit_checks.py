# -*- coding: utf-8 -*-
"""第 16 轮（ACTUS_REFACTOR_PLAN §六.6 复核）：审计脚本宽松判定收紧回归。

plan_audit_actus.py 早期三处宽松判定会误报 OK：
  1. kind 执行语义：正则 / 字符串包含匹配 executor.py，注释或字符串字面量里
     出现 `kind == 'alias'` 之类字样即可误判"已落地"；
  2. link/alias target 存在性：`'target' in validate.py 全文`（恒真）；
  3. md5 一致性：`'md5' in validate.py 全文`（恒真）。

收紧后：
  * kind → AST 精确收集真实代码中的 `kind == 'X'` / `kind in (..., 'X')`
    判定（_plan_audit_helpers.code_kind_comparisons，与审计脚本同实现）；
  * target / md5 → 真实行为验证（直接调 V.check_link_target /
    V.check_md5_consistency 断言 error / warning 语义）。

本文件保护上述收紧逻辑，防止回退到字符串包含或行为验证失真。
"""
import os
import sys
import json
import hashlib
from types import SimpleNamespace

import pytest

# 复用审计脚本的共享辅助（与 plan_audit_actus.py 同实现，防漂移）
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_AUDIT_DIR = os.path.join(_REPO_ROOT, "tools", "audit")
if _AUDIT_DIR not in sys.path:
    sys.path.insert(0, _AUDIT_DIR)

from _plan_audit_helpers import code_kind_comparisons  # noqa: E402

from vools.actus import validate as V  # noqa: E402

_EXECUTOR_PATH = os.path.join(_REPO_ROOT, "vools", "actus", "executor.py")


def _write_index(meta_dir, entries):
    meta_dir = str(meta_dir)
    os.makedirs(meta_dir, exist_ok=True)
    with open(os.path.join(meta_dir, "actions.index.json"), "w", encoding="utf-8") as f:
        json.dump({"actions": entries}, f)


# ── 1) kind 语义判定：AST 精确匹配 ─────────────────────────

def test_kind_collector_covers_all_six_kinds():
    """executor.py 真实代码中六种 kind 的执行语义判定全部存在（回归保护）。"""
    src = open(_EXECUTOR_PATH, encoding="utf-8").read()
    kinds = code_kind_comparisons(src)
    assert {"link", "alias", "bundle", "doc", "template", "demo"} <= kinds, (
        "executor.py 的 kind 判定集合应覆盖六种 kind: %r" % sorted(kinds))


def test_kind_collector_ignores_comments_and_string_literals():
    """注释 / docstring / 字符串字面量里的 `kind == 'x'` 字样不误报。"""
    src = (
        "kind = action.meta.get('kind') or 'exec'\n"
        "# 历史说明：曾用 `kind == 'alias'` 判定转发语义，现已改为 in 元组\n"
        "doc = '''此处举例：kind == 'link' 与 kind in ('bundle',) 都不算真实代码'''\n"
        "msg = \"kind == 'template' 只是提示文案\"\n"
        "if kind == 'demo':\n"
        "    pass\n"
    )
    kinds = code_kind_comparisons(src)
    assert kinds == {"demo"}, "只应收集真实代码判定: %r" % sorted(kinds)


def test_kind_collector_ignores_noteq_and_method_calls():
    """`kind != 'x'`（非等）与 `meta.get('kind') == 'x'`（调用表达式）不收集。"""
    src = (
        "kind = action.meta.get('kind') or 'exec'\n"
        "if kind != 'exec':\n"
        "    pass\n"
        "if meta.get('kind') == 'alias':\n"
        "    pass\n"
    )
    kinds = code_kind_comparisons(src)
    assert kinds == set(), "不应收集 NotEq 或调用表达式: %r" % sorted(kinds)


# ── 2) link/alias target 存在性：真实行为验证 ────────────────

def test_link_target_missing_reports_error():
    """kind=link 且 target 缺失 → check_link_target 必须报 error。"""
    action = SimpleNamespace(meta={"kind": "link", "target": "", "id": "stub.link"})
    errors = V.check_link_target(action, check_index=False)
    assert any("缺少 target" in e for e in errors), "target 缺失应报 error: %r" % errors


def test_link_target_not_in_index_warns(tmp_path):
    """target 不在索引 → check_index=True 必须报 warning（存在性校验真实生效）。"""
    _write_index(tmp_path, {"actus.real": {"id": "actus.real", "md5": "0" * 32}})
    action = SimpleNamespace(
        meta={"kind": "alias", "target": "actus.missing", "id": "stub.alias"})
    errors = V.check_link_target(action, check_index=True, meta_dir=str(tmp_path))
    assert any("未在索引中找到" in e for e in errors), (
        "target 不在索引应报 warning: %r" % errors)


def test_link_target_hit_index_silent(tmp_path):
    """target 在索引中 → 无告警。"""
    _write_index(tmp_path, {"actus.real": {"id": "actus.real", "md5": "0" * 32}})
    action = SimpleNamespace(
        meta={"kind": "link", "target": "actus.real", "id": "stub.link2"})
    errors = V.check_link_target(action, check_index=True, meta_dir=str(tmp_path))
    assert errors == [], "target 命中索引不应告警: %r" % errors


# ── 3) md5 一致性：真实文件内容比对 ──────────────────────────

def test_md5_inconsistent_warns(tmp_path):
    """索引 md5 与实际文件内容 md5 不一致 → 必须 warning（真实比对）。"""
    action_file = os.path.join(str(tmp_path), "stub_md5.txt")
    with open(action_file, "w", encoding="utf-8") as f:
        f.write("stub md5 body")
    real_md5 = hashlib.md5(open(action_file, "rb").read()).hexdigest()
    _write_index(tmp_path, {"stub.md5": {"id": "stub.md5", "md5": "f" * 32}})
    action = SimpleNamespace(meta={"id": "stub.md5"}, md5=real_md5, path=action_file)
    warnings = V.check_md5_consistency(action, meta_dir=str(tmp_path))
    assert any("索引 md5 与文件不一致" in w for w in warnings), (
        "md5 不一致应报 warning: %r" % warnings)


def test_md5_consistent_silent(tmp_path):
    """索引 md5 与文件实际 md5 一致 → 无告警。"""
    action_file = os.path.join(str(tmp_path), "stub_md5.txt")
    with open(action_file, "w", encoding="utf-8") as f:
        f.write("stub md5 body")
    real_md5 = hashlib.md5(open(action_file, "rb").read()).hexdigest()
    _write_index(tmp_path, {"stub.md5": {"id": "stub.md5", "md5": real_md5}})
    action = SimpleNamespace(meta={"id": "stub.md5"}, md5=real_md5, path=action_file)
    warnings = V.check_md5_consistency(action, meta_dir=str(tmp_path))
    assert warnings == [], "md5 一致不应告警: %r" % warnings


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-p", "no:cacheprovider"])
