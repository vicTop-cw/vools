# -*- coding: utf-8 -*-
"""omega.py 的查找与断言校验（扫第二档发现）。

缺陷：
  1. **`_find_action_file` 是全仓第 5 份查找实现**，且判据更宽松：
     `f'"{action_id}"' in content` —— 既误命中「描述里提到该 id」的文件，
     又**认不出**新格式 `.actus.schema.md` 的 YAML `id: xxx`（无引号）。
     实测连种子动作 `actus.basics.calculator` 都返回 None，
     导致 `_find_omega_spec` 的「与动作同目录找 spec」分支永远失效。
  2. `validate_spec`：`assertions='abc'` 报错后**仍逐字符迭代**（噪音）、
     `[None]` 裸 TypeError、**未知 type 值不校验**（`bogus` 一路放行）
  3. `check_assertion(None, x)` 抛裸 AttributeError；
     `exists` 通过时也返回「字段 '' 不存在」（消息与结论矛盾）
"""
import os

import pytest

from vools.actus.omega import (ASSERTION_TYPES, _find_action_file,
                               check_assertion, validate_spec)

ACTIONS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "vools", "actus", "actions")


# --------------------------------------------------------------------------
# 查找（第 5 份实现收口）
# --------------------------------------------------------------------------
def test_finds_new_format_seed_action():
    """新格式动作必须能找到（修前全是 None）。"""
    hit = _find_action_file("actus.basics.calculator", ACTIONS)
    assert hit is not None, "种子动作找不到"
    assert hit.endswith("calculator.actus.schema.md")


def test_find_unknown_returns_none():
    assert _find_action_file("no.such.action", ACTIONS) is None


# --------------------------------------------------------------------------
# validate_spec
# --------------------------------------------------------------------------
BASE = {"action_id": "a", "version": "1", "output_schema": {}}


def test_assertions_string_not_iterated():
    """此前对字符串继续迭代，把 'abc' 报成 3 条子项错误。"""
    ok, errs = validate_spec(dict(BASE, assertions="abc"))
    assert ok is False
    assert errs == ["assertions 必须是数组"], errs


def test_assertion_non_dict_item():
    ok, errs = validate_spec(dict(BASE, assertions=[None]))
    assert ok is False
    assert "必须是对象" in errs[0], errs


def test_assertion_missing_type():
    ok, errs = validate_spec(dict(BASE, assertions=[{}]))
    assert ok is False
    assert "缺少 type" in errs[0], errs


def test_assertion_unknown_type_rejected():
    """`bogus` 此前一路放行，到 check_assertion 才表现为「断言不通过」。"""
    ok, errs = validate_spec(dict(BASE, assertions=[{"type": "bogus"}]))
    assert ok is False
    assert "未知 type" in errs[0], errs


@pytest.mark.parametrize("atype", sorted(ASSERTION_TYPES))
def test_all_declared_types_accepted(atype):
    ok, errs = validate_spec(dict(BASE, assertions=[{"type": atype}]))
    assert ok is True, (atype, errs)


def test_valid_spec_passes():
    ok, errs = validate_spec({"action_id": "a", "version": "1",
                              "output_schema": {"type": "object"},
                              "assertions": [{"type": "exists", "field": "x"}]})
    assert ok is True and errs == []


# --------------------------------------------------------------------------
# check_assertion
# --------------------------------------------------------------------------
def test_check_assertion_rejects_non_dict():
    with pytest.raises(TypeError) as exc:
        check_assertion(None, 1)
    assert "必须是 dict" in str(exc.value), exc.value


def test_exists_message_matches_verdict():
    """通过时不能返回「不存在」（消息与结论矛盾）。"""
    ok, msg = check_assertion({"type": "exists", "field": "x"}, {"x": 1})
    assert ok is True
    assert "存在" in msg and "不存在" not in msg, msg

    ok2, msg2 = check_assertion({"type": "exists", "field": "y"}, {"x": 1})
    assert ok2 is False
    assert "不存在" in msg2, msg2


def test_equals_and_not_equals():
    assert check_assertion({"type": "equals", "field": "x", "value": 1},
                           {"x": 1})[0] is True
    assert check_assertion({"type": "equals", "field": "x", "value": 2},
                           {"x": 1})[0] is False
    assert check_assertion({"type": "not_equals", "field": "x", "value": 2},
                           {"x": 1})[0] is True


def test_nested_field_path():
    assert check_assertion({"type": "equals", "field": "a.b", "value": 5},
                           {"a": {"b": 5}})[0] is True
