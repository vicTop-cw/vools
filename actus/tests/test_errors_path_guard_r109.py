# -*- coding: utf-8 -*-
"""actus/tests/test_errors_path_guard_r109.py — errors.check_path_target 专项
（统帅轮-15时，COVERAGE_AUDIT_R105 第三批）。

测什么 / 为什么
---------------
`errors.check_path_target()` 是 scaffold/template 等模块共用的**写前检查**
（存在即拒绝 + force 放行），此前零直接测试。本文件锚定：
  * 目标不存在 → 原样返回 path（放行语义）；
  * 目标存在且未 force → ActionError(默认 code='action_exists')；
  * 自定义 code / what 消息词透传；
  * force=True → 原样放行（即便目标存在）。

py3.8+（pyproject requires-python>=3.8），标准库。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

from vools.actus.errors import ActionError, check_path_target  # noqa: E402


def test_missing_target_returns_path_unchanged(tmp_path):
    """目标不存在 → 原样返回（放行写入）。"""
    target = str(tmp_path / "new_dir" / "file.actus.md")
    assert check_path_target(target) == target


def test_existing_target_without_force_raises_default_code(tmp_path):
    """目标存在 + 未 force → ActionError(action_exists)。"""
    target = tmp_path / "existing.actus.md"
    target.write_text("x", encoding="utf-8")
    with pytest.raises(ActionError) as exc_info:
        check_path_target(str(target))
    assert exc_info.value.code == "action_exists"
    assert "拒绝覆盖" in exc_info.value.message
    assert exc_info.value.details.get("path") == str(target)


def test_existing_target_with_force_passes(tmp_path):
    """force=True → 即便目标存在也原样放行。"""
    target = tmp_path / "existing.actus.md"
    target.write_text("x", encoding="utf-8")
    assert check_path_target(str(target), force=True) == str(target)


def test_custom_code_and_what_propagate(tmp_path):
    """code 与 what 消息词透传（installer 族自定义错误码场景）。"""
    target = tmp_path / "f.md"
    target.write_text("x", encoding="utf-8")
    with pytest.raises(ActionError) as exc_info:
        check_path_target(str(target), what="模板", code="template_conflict")
    assert exc_info.value.code == "template_conflict"
    assert "模板已存在" in exc_info.value.message


def test_directory_target_also_guarded(tmp_path):
    """目录目标同样受保护（os.path.exists 对目录也 True）。"""
    d = tmp_path / "adir"
    d.mkdir()
    with pytest.raises(ActionError):
        check_path_target(str(d))
    assert check_path_target(str(d), force=True) == str(d)
