# -*- coding: utf-8 -*-
"""omega.py 契约测试（Round 52）。

覆盖：fnv1a64 指纹、_find_omega_spec 四级查找、load_spec 缓存与失效、
validate_spec、_get_nested 路径解析、check_assertion 全部 16 种断言类型、
_validate_schema、run_gate、generate_diff_report、compute_output_fingerprint /
check_fingerprint、run_omega_loop、verify_output、learn_spec_from_history、
generate_spec_template / _infer_schema、batch_verify、format_report、__all__。

隔离：全部用 tmp_path / monkeypatch，不触碰仓库真实 actions/。
"""
import json
import os

import pytest

from vools.actus import omega


# ── fnv1a64 ──

class TestFnv1a64:
    def test_deterministic(self):
        assert omega.fnv1a64("abc") == omega.fnv1a64("abc")

    def test_known_value(self):
        # FNV-1a 64 已知向量：空串 -> cbf29ce484222325（偏移基值）
        assert omega.fnv1a64("") == "cbf29ce484222325"
        # 标准向量 'a'
        assert omega.fnv1a64("a") == "af63dc4c8601ec8c"

    def test_differs_for_different_input(self):
        assert omega.fnv1a64("abc") != omega.fnv1a64("abd")

    def test_unicode(self):
        assert omega.fnv1a64("中文") == omega.fnv1a64("中文")
        assert omega.fnv1a64("中文") != omega.fnv1a64("english")


# ── _find_omega_spec ──

class TestFindOmegaSpec:
    def test_none_actions_dir_defaults_to_repo_actions(self, tmp_path, monkeypatch):
        """actions_dir=None → indexer._repo_root()/actions。"""
        fake = tmp_path / "actions"
        (fake / "public" / "omega").mkdir(parents=True)
        (fake / "public" / "omega" / "x.spec.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr("vools.actus.indexer._repo_root", lambda: str(tmp_path))
        got = omega._find_omega_spec("x", None)
        assert got == os.path.join(str(fake), "public", "omega", "x.spec.json")

    def test_priority_private_omega_dir(self, tmp_path):
        acts = tmp_path / "actions"
        for vis in ("private", "public"):
            (acts / vis / "omega").mkdir(parents=True)
            (acts / vis / "omega" / "a.spec.json").write_text("{}", encoding="utf-8")
        got = omega._find_omega_spec("a", str(acts))
        assert got == os.path.join(str(acts), "private", "omega", "a.spec.json")

    def test_falls_to_public_omega_dir(self, tmp_path):
        acts = tmp_path / "actions"
        (acts / "public" / "omega").mkdir(parents=True)
        (acts / "public" / "omega" / "a.spec.json").write_text("{}", encoding="utf-8")
        got = omega._find_omega_spec("a", str(acts))
        assert "public" in got and got.endswith("a.spec.json")

    def test_short_name_fallback(self, tmp_path):
        """全限定 id 不命中 → 末段短名命中。"""
        acts = tmp_path / "actions"
        (acts / "public" / "omega").mkdir(parents=True)
        (acts / "public" / "omega" / "push.spec.json").write_text("{}", encoding="utf-8")
        got = omega._find_omega_spec("actus.private.jump_push", str(acts))
        # jump_push ≠ push：短名是 rsplit('.')[-1]，'actus.private.jump_push'→'jump_push'
        # push.spec.json 不命中 → None
        assert got is None

    def test_short_name_matches(self, tmp_path):
        acts = tmp_path / "actions"
        (acts / "public" / "omega").mkdir(parents=True)
        (acts / "public" / "omega" / "jump_push.spec.json").write_text("{}", encoding="utf-8")
        got = omega._find_omega_spec("actus.private.jump_push", str(acts))
        assert got is not None and "jump_push.spec.json" in got

    def test_recursive_omega_subdir(self, tmp_path):
        acts = tmp_path / "actions"
        nested = acts / "group" / "sub" / "omega"
        nested.mkdir(parents=True)
        (nested / "r.spec.json").write_text("{}", encoding="utf-8")
        got = omega._find_omega_spec("r", str(acts))
        assert got is not None and got.endswith("r.spec.json")

    def test_same_dir_as_action(self, tmp_path, monkeypatch):
        """无 omega 目录 → 与动作文件同目录找。"""
        import vools.actus.resolver as resolver
        acts = tmp_path / "actions"
        adir = acts / "public"
        adir.mkdir(parents=True)
        (adir / "s.actus.md").write_text("action", encoding="utf-8")
        (adir / "s.spec.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(resolver, "find_action_file",
                            lambda aid, d: str(adir / "s.actus.md"))
        got = omega._find_omega_spec("s", str(acts))
        assert got == os.path.join(str(adir), "s.spec.json")

    def test_not_found_returns_none(self, tmp_path):
        acts = tmp_path / "actions"
        acts.mkdir()
        assert omega._find_omega_spec("ghost", str(acts)) is None

    def test_find_action_file_delegates_and_swallows(self, monkeypatch):
        """_find_action_file 委托 resolver；异常吞掉返回 None。"""
        import vools.actus.resolver as resolver
        monkeypatch.setattr(resolver, "find_action_file",
                            lambda aid, d: (_ for _ in ()).throw(RuntimeError("boom")))
        assert omega._find_action_file("x", "d") is None


# ── load_spec / clear_spec_cache ──

class TestLoadSpec:
    def test_load_and_cache(self, tmp_path):
        p = tmp_path / "a.spec.json"
        p.write_text('{"action_id": "a"}', encoding="utf-8")
        assert omega.load_spec(str(p)) == {"action_id": "a"}
        assert omega.load_spec(str(p)) == {"action_id": "a"}

    def test_cache_invalidated_on_change(self, tmp_path):
        p = tmp_path / "a.spec.json"
        p.write_text('{"v": 1}', encoding="utf-8")
        omega.load_spec(str(p))
        p.write_text('{"v": 2}', encoding="utf-8")
        os.utime(str(p), ns=(0, 0))  # mtime 变化（write 可能同 ns）
        assert omega.load_spec(str(p)) == {"v": 2}

    def test_use_cache_false_bypasses(self, tmp_path):
        p = tmp_path / "a.spec.json"
        p.write_text('{"v": 1}', encoding="utf-8")
        omega.load_spec(str(p))
        p.write_text('{"v": 2}', encoding="utf-8")
        os.utime(str(p), ns=(1, 1))
        assert omega.load_spec(str(p), use_cache=False) == {"v": 2}

    def test_clear_cache(self, tmp_path):
        p = tmp_path / "a.spec.json"
        p.write_text('{"v": 1}', encoding="utf-8")
        omega.load_spec(str(p))
        omega.clear_spec_cache()
        assert omega._spec_cache == {}


# ── validate_spec ──

class TestValidateSpec:
    def _spec(self, **over):
        # 注意：不能用 {"type": "status_ok"} —— BUG-O1：ASSERTION_TYPES 白名单
        # 少了 check_assertion 实际支持的 6 种类型（status_ok/all_of/not_empty/
        # path_exists/json_path/schema），含它们的 spec 过不了 validate_spec。
        base = {
            "action_id": "a.b",
            "version": "1.0.0",
            "output_schema": {"type": "object"},
            "assertions": [{"type": "exists", "field": "status"}],
        }
        base.update(over)
        return base

    def test_valid(self):
        ok, errors = omega.validate_spec(self._spec())
        assert ok is True and errors == []

    def test_bug_o1_whitelist_missing_supported_types(self):
        """BUG-O1（已修复验证）：validate_spec 的 ASSERTION_TYPES 白名单
        现已包含 check_assertion 支持的全部类型（含 status_ok/all_of/
        not_empty/path_exists/json_path/schema）。修复后这些类型应通过验证。

        正确行为：白名单包含全部 20 种类型；修 BUG 后改此断言为 ok is True。
        """
        for atype in ("status_ok", "all_of", "not_empty", "path_exists",
                      "json_path", "schema"):
            ok, errors = omega.validate_spec(
                self._spec(assertions=[{"type": atype}]))
            assert ok is True, atype
            assert errors == [], (atype, errors)
        # 而 check_assertion 明明支持它们（运行时不拦）
        ok, _ = omega.check_assertion({"type": "status_ok"}, {"status": "ok"})
        assert ok is True

    def test_bug_o1_template_cannot_pass_own_validator(self):
        """BUG-O1（已修复验证）：generate_spec_template 的输出直接喂
        validate_spec → 应通过验证（白名单已含 status_ok）。

        修复前生成器与验证器自相矛盾（模板含 status_ok，白名单没有它）。
        修复后模板应能通过自己的验证器。
        """
        template = omega.generate_spec_template("t.a", {"status": "ok"})
        ok, errors = omega.validate_spec(template)
        assert ok is True, errors

    def test_missing_required_fields(self):
        ok, errors = omega.validate_spec({})
        for key in ("action_id", "version", "output_schema", "assertions"):
            assert any(key in e for e in errors), errors

    def test_output_schema_not_dict(self):
        ok, errors = omega.validate_spec(self._spec(output_schema="x"))
        assert ok is False
        assert any("output_schema" in e for e in errors)

    def test_assertions_not_list(self):
        ok, errors = omega.validate_spec(self._spec(assertions="abc"))
        assert ok is False
        assert any("assertions" in e for e in errors)

    def test_assertion_not_object(self):
        ok, errors = omega.validate_spec(self._spec(assertions=[None]))
        # None 项：报"必须是对象"而不是裸 TypeError
        assert ok is False
        assert any("NoneType" in e or "None" in e for e in errors)

    def test_assertion_missing_type(self):
        ok, errors = omega.validate_spec(self._spec(assertions=[{"field": "x"}]))
        assert ok is False
        assert any("缺少 type" in e for e in errors)

    def test_assertion_unknown_type(self):
        ok, errors = omega.validate_spec(self._spec(assertions=[{"type": "bogus"}]))
        assert ok is False
        assert any("bogus" in e for e in errors)

    def test_assertion_string_not_iterated_charwise(self):
        """字符串 assertions 只报「不是数组」，不再逐字符噪音。"""
        ok, errors = omega.validate_spec(self._spec(assertions="abc"))
        n_charwise = sum(1 for e in errors if "assertions[0]" in e
                         and "缺少 type" in e)
        assert n_charwise == 0


# ── _get_nested ──

class TestGetNested:
    def test_empty_path_returns_obj(self):
        assert omega._get_nested({"a": 1}, "") == {"a": 1}

    def test_top_level(self):
        assert omega._get_nested({"a": 1}, "a") == 1

    def test_nested_dotted(self):
        assert omega._get_nested({"a": {"b": 2}}, "a.b") == 2

    def test_array_index(self):
        assert omega._get_nested({"items": [10, 20]}, "items[1]") == 20

    def test_mixed_path(self):
        obj = {"data": {"items": [{"name": "x"}]}}
        assert omega._get_nested(obj, "data.items[0].name") == "x"

    def test_missing_key_returns_none(self):
        assert omega._get_nested({"a": 1}, "b") is None

    def test_index_out_of_range_returns_none(self):
        assert omega._get_nested({"items": []}, "items[0]") is None

    def test_index_on_non_list_returns_none(self):
        assert omega._get_nested({"items": 5}, "items[0]") is None

    def test_indexed_field_missing_in_dict_returns_none(self):
        assert omega._get_nested({"other": 1}, "items[0]") is None


# ── check_assertion（16 种类型）──

class TestCheckAssertion:
    # 基础
    def test_non_dict_raises_typeerror(self):
        with pytest.raises(TypeError):
            omega.check_assertion(None, {})

    def test_default_type_is_exists(self):
        ok, _ = omega.check_assertion({"field": "a"}, {"a": 1})
        assert ok is True

    # exists / not_exists
    def test_exists_pass_and_message(self):
        ok, msg = omega.check_assertion({"type": "exists", "field": "a"}, {"a": 1})
        assert ok and "存在" in msg

    def test_exists_fail(self):
        ok, msg = omega.check_assertion({"type": "exists", "field": "z"}, {"a": 1})
        assert not ok and "不存在" in msg

    def test_not_exists_pass(self):
        ok, _ = omega.check_assertion({"type": "not_exists", "field": "z"}, {"a": 1})
        assert ok

    def test_not_exists_fail(self):
        ok, _ = omega.check_assertion({"type": "not_exists", "field": "a"}, {"a": 1})
        assert not ok

    # type
    def test_type_str_alias(self):
        for name in ("str", "string"):
            ok, _ = omega.check_assertion({"type": "type", "field": "a", "value": name},
                                          {"a": "s"})
            assert ok

    def test_type_number_accepts_int_and_float(self):
        for v in (1, 1.5):
            ok, _ = omega.check_assertion({"type": "type", "field": "a", "value": "number"},
                                          {"a": v})
            assert ok

    def test_type_unknown_falls_back_to_str(self):
        ok, _ = omega.check_assertion({"type": "type", "field": "a", "value": "bogus"},
                                      {"a": "s"})
        assert ok
        ok2, _ = omega.check_assertion({"type": "type", "field": "a", "value": "bogus"},
                                       {"a": 5})
        assert not ok2

    def test_type_bool(self):
        ok, _ = omega.check_assertion({"type": "type", "field": "a", "value": "bool"},
                                      {"a": True})
        assert ok

    def test_type_array_alias(self):
        ok, _ = omega.check_assertion({"type": "type", "field": "a", "value": "array"},
                                      {"a": [1]})
        assert ok

    def test_type_object_alias(self):
        ok, _ = omega.check_assertion({"type": "type", "field": "a", "value": "object"},
                                      {"a": {}})
        assert ok

    # equals / not_equals
    def test_equals(self):
        ok, _ = omega.check_assertion({"type": "equals", "field": "a", "value": 1},
                                      {"a": 1})
        assert ok
        ok2, _ = omega.check_assertion({"type": "equals", "field": "a", "value": 1},
                                       {"a": 2})
        assert not ok2

    def test_not_equals(self):
        ok, _ = omega.check_assertion({"type": "not_equals", "field": "a", "value": 1},
                                      {"a": 2})
        assert ok
        ok2, _ = omega.check_assertion({"type": "not_equals", "field": "a", "value": 1},
                                       {"a": 1})
        assert not ok2

    # approx
    def test_approx_within_epsilon(self):
        ok, _ = omega.check_assertion({"type": "approx", "field": "a", "value": 1.0,
                                       "epsilon": 0.1}, {"a": 1.05})
        assert ok

    def test_approx_outside(self):
        ok, _ = omega.check_assertion({"type": "approx", "field": "a", "value": 1.0,
                                       "epsilon": 0.1}, {"a": 2.0})
        assert not ok

    def test_approx_non_numeric(self):
        ok, msg = omega.check_assertion({"type": "approx", "field": "a", "value": 1.0},
                                        {"a": "abc"})
        assert not ok and "无法做数值比较" in msg

    # regex
    def test_regex_match(self):
        ok, _ = omega.check_assertion({"type": "regex", "field": "a", "value": r"^\d+$"},
                                      {"a": "123"})
        assert ok

    def test_regex_no_match(self):
        ok, _ = omega.check_assertion({"type": "regex", "field": "a", "value": r"^\d+$"},
                                      {"a": "abc"})
        assert not ok

    def test_regex_none_value_fails(self):
        ok, _ = omega.check_assertion({"type": "regex", "field": "a", "value": "."},
                                      {"a": None})
        assert not ok

    # contains / not_contains
    def test_contains_str(self):
        ok, _ = omega.check_assertion({"type": "contains", "field": "a", "value": "ell"},
                                      {"a": "hello"})
        assert ok
        ok2, _ = omega.check_assertion({"type": "contains", "field": "a", "value": "zz"},
                                       {"a": "hello"})
        assert not ok2

    def test_contains_list(self):
        ok, _ = omega.check_assertion({"type": "contains", "field": "a", "value": 2},
                                      {"a": [1, 2, 3]})
        assert ok

    def test_contains_non_str_list(self):
        ok, msg = omega.check_assertion({"type": "contains", "field": "a", "value": "x"},
                                        {"a": 5})
        assert not ok and "不是字符串或数组" in msg

    def test_not_contains_str(self):
        ok, _ = omega.check_assertion({"type": "not_contains", "field": "a", "value": "zz"},
                                      {"a": "hello"})
        assert ok

    def test_not_contains_list(self):
        ok, _ = omega.check_assertion({"type": "not_contains", "field": "a", "value": 9},
                                      {"a": [1, 2]})
        assert ok

    def test_not_contains_non_str_list(self):
        ok, _ = omega.check_assertion({"type": "not_contains", "field": "a", "value": "x"},
                                      {"a": {"k": 1}})
        assert not ok

    # length
    def test_length_in_range(self):
        ok, _ = omega.check_assertion({"type": "length", "field": "a", "min": 1, "max": 3},
                                      {"a": [1, 2]})
        assert ok

    def test_length_too_short(self):
        ok, _ = omega.check_assertion({"type": "length", "field": "a", "min": 3, "max": 5},
                                      {"a": "ab"})
        assert not ok

    def test_length_on_non_container(self):
        ok, msg = omega.check_assertion({"type": "length", "field": "a"},
                                        {"a": 5})
        assert not ok and "长度" in msg

    # range
    def test_range_within(self):
        ok, _ = omega.check_assertion({"type": "range", "field": "a", "min": 1, "max": 10},
                                      {"a": 5})
        assert ok

    def test_range_outside(self):
        ok, _ = omega.check_assertion({"type": "range", "field": "a", "min": 1, "max": 10},
                                      {"a": 50})
        assert not ok

    def test_range_non_numeric(self):
        ok, msg = omega.check_assertion({"type": "range", "field": "a"},
                                        {"a": "abc"})
        assert not ok and "无法做范围比较" in msg

    # subset / superset
    def test_subset_pass(self):
        ok, _ = omega.check_assertion({"type": "subset", "field": "a",
                                       "value": ["x", "y"]}, {"a": ["x"]})
        assert ok

    def test_subset_extra_values_fail(self):
        ok, msg = omega.check_assertion({"type": "subset", "field": "a",
                                         "value": ["x"]}, {"a": ["x", "z"]})
        assert not ok and "不允许的值" in msg

    def test_subset_scalar_wraps(self):
        ok, _ = omega.check_assertion({"type": "subset", "field": "a",
                                       "value": ["x"]}, {"a": "x"})
        assert ok

    def test_subset_none_fails(self):
        ok, msg = omega.check_assertion({"type": "subset", "field": "a",
                                         "value": ["x"]}, {"a": None})
        assert not ok and "不是数组" in msg

    def test_superset_pass(self):
        ok, _ = omega.check_assertion({"type": "superset", "field": "a",
                                       "value": ["x"]}, {"a": ["x", "y"]})
        assert ok

    def test_superset_missing_fail(self):
        ok, msg = omega.check_assertion({"type": "superset", "field": "a",
                                         "value": ["x", "z"]}, {"a": ["x"]})
        assert not ok and "缺少必需的值" in msg

    def test_superset_on_dict_fails(self):
        ok, msg = omega.check_assertion({"type": "superset", "field": "a",
                                         "value": ["x"]}, {"a": {"k": 1}})
        assert not ok and "不是数组" in msg

    # any_of / all_of
    def test_any_of_one_passes(self):
        a = {"type": "any_of", "field": "a", "assertions": [
            {"type": "equals", "field": "a", "value": 9},
            {"type": "equals", "field": "a", "value": 1},
        ]}
        ok, _ = omega.check_assertion(a, {"a": 1})
        assert ok

    def test_any_of_none_passes(self):
        a = {"type": "any_of", "field": "a", "assertions": [
            {"type": "equals", "field": "a", "value": 9},
        ]}
        ok, msg = omega.check_assertion(a, {"a": 1})
        assert not ok and "any_of" in msg

    def test_all_of_pass(self):
        a = {"type": "all_of", "field": "a", "assertions": [
            {"type": "type", "field": "a", "value": "int"},
            {"type": "equals", "field": "a", "value": 1},
        ]}
        ok, _ = omega.check_assertion(a, {"a": 1})
        assert ok

    def test_all_of_fail_carries_sub_message(self):
        a = {"type": "all_of", "field": "a", "assertions": [
            {"type": "equals", "field": "a", "value": 9},
        ]}
        ok, msg = omega.check_assertion(a, {"a": 1})
        assert not ok and "all_of 失败" in msg

    # not_empty
    def test_not_empty_pass(self):
        ok, _ = omega.check_assertion({"type": "not_empty", "field": "a"},
                                      {"a": [1]})
        assert ok

    def test_not_empty_fail_empty_list(self):
        ok, msg = omega.check_assertion({"type": "not_empty", "field": "a"},
                                        {"a": []})
        assert not ok and "不应为空" in msg

    def test_not_empty_none(self):
        ok, msg = omega.check_assertion({"type": "not_empty", "field": "a"},
                                        {"a": None})
        assert not ok and "为空" in msg

    def test_not_empty_scalar_true(self):
        ok, _ = omega.check_assertion({"type": "not_empty", "field": "a"},
                                      {"a": 5})
        assert ok

    # path_exists
    def test_path_exists_true(self, tmp_path):
        p = tmp_path / "f.txt"
        p.write_text("x", encoding="utf-8")
        ok, _ = omega.check_assertion({"type": "path_exists", "field": "p"},
                                      {"p": str(p)})
        assert ok

    def test_path_exists_false(self, tmp_path):
        ok, _ = omega.check_assertion({"type": "path_exists", "field": "p"},
                                      {"p": str(tmp_path / "nope")})
        assert not ok

    def test_path_exists_non_str(self):
        ok, msg = omega.check_assertion({"type": "path_exists", "field": "p"},
                                        {"p": 5})
        assert not ok and "不是路径字符串" in msg

    # json_path
    def test_json_path_match(self):
        a = {"type": "json_path", "value": "data.count", "expected": 3}
        ok, _ = omega.check_assertion(a, {"data": {"count": 3}})
        assert ok

    def test_json_path_mismatch(self):
        a = {"type": "json_path", "value": "data.count", "expected": 3}
        ok, _ = omega.check_assertion(a, {"data": {"count": 4}})
        assert not ok

    # status_ok
    def test_status_ok_pass(self):
        ok, _ = omega.check_assertion({"type": "status_ok"}, {"status": "ok"})
        assert ok

    def test_status_ok_fail(self):
        ok, _ = omega.check_assertion({"type": "status_ok"}, {"status": "error"})
        assert not ok

    def test_status_ok_non_dict(self):
        ok, _ = omega.check_assertion({"type": "status_ok"}, "string")
        assert not ok

    # schema
    def test_schema_pass(self):
        a = {"type": "schema", "value": {"type": "object",
                                         "properties": {"n": {"type": "integer"}}}}
        ok, _ = omega.check_assertion(a, {"n": 1})
        assert ok

    def test_schema_fail(self):
        a = {"type": "schema", "value": {"type": "object",
                                         "properties": {"n": {"type": "integer"}}}}
        ok, _ = omega.check_assertion(a, {"n": "s"})
        assert not ok

    # 未知类型（validate_spec 拦不住的直调路径）
    def test_unknown_type_is_noop_pass(self):
        """check_assertion 对未知 type 走到函数末尾恒 (True, '')。

        契约现状：运行时不再二次校验 type（validate_spec 是唯一守门）。
        """
        ok, msg = omega.check_assertion({"type": "bogus", "field": "a"}, {"a": 1})
        assert ok is True and msg == ""


# ── _validate_schema ──

class TestValidateSchema:
    def test_object_ok(self):
        ok, _ = omega._validate_schema({"a": 1}, {"type": "object"})
        assert ok

    def test_object_type_mismatch(self):
        ok, msg = omega._validate_schema([1], {"type": "object"})
        assert not ok and "对象" in msg

    def test_object_property_validation(self):
        schema = {"type": "object",
                  "properties": {"n": {"type": "integer"}}}
        ok, _ = omega._validate_schema({"n": 1}, schema)
        assert ok
        ok2, msg2 = omega._validate_schema({"n": "s"}, schema)
        assert not ok2 and "n" in msg2

    def test_object_required_missing(self):
        schema = {"type": "object", "properties": {}, "required": ["x"]}
        ok, msg = omega._validate_schema({}, schema)
        assert not ok and "x" in msg

    def test_array_items(self):
        schema = {"type": "array", "items": {"type": "string"}}
        ok, _ = omega._validate_schema(["a", "b"], schema)
        assert ok
        ok2, msg2 = omega._validate_schema(["a", 1], schema)
        assert not ok2 and "[1]" in msg2

    def test_array_type_mismatch(self):
        ok, _ = omega._validate_schema("s", {"type": "array"})
        assert not ok

    def test_string_type(self):
        ok, _ = omega._validate_schema("s", {"type": "string"})
        assert ok
        ok2, _ = omega._validate_schema(1, {"type": "string"})
        assert not ok2

    def test_integer_type(self):
        ok, _ = omega._validate_schema(1, {"type": "integer"})
        assert ok
        ok2, _ = omega._validate_schema("1", {"type": "integer"})
        assert not ok2

    def test_unknown_type_always_passes(self):
        ok, _ = omega._validate_schema("anything", {"type": "bogus"})
        assert ok


# ── run_gate ──

class TestRunGate:
    def test_all_pass(self):
        spec = {"assertions": [
            {"type": "equals", "field": "status", "value": "ok"},
            {"type": "exists", "field": "data"},
        ]}
        r = omega.run_gate(spec, {"status": "ok", "data": 1})
        assert r["passed"] is True
        assert r["accuracy"] == 100.0
        assert r["passed_count"] == 2 and r["failed_count"] == 0 and r["total"] == 2

    def test_partial_fail(self):
        spec = {"assertions": [
            {"type": "equals", "field": "status", "value": "ok"},
            {"type": "equals", "field": "status", "value": "nope"},
        ]}
        r = omega.run_gate(spec, {"status": "ok"})
        assert r["passed"] is False
        assert r["passed_count"] == 1 and r["failed_count"] == 1
        assert r["accuracy"] == 50.0
        assert len(r["details"]) == 2
        assert r["details"][1]["passed"] is False

    def test_empty_assertions_accuracy_100(self):
        r = omega.run_gate({"assertions": []}, {})
        assert r["passed"] is True and r["accuracy"] == 100.0 and r["total"] == 0


# ── generate_diff_report ──

class TestGenerateDiffReport:
    def _spec(self, props):
        return {"output_schema": {"properties": props}}

    def test_match(self):
        spec = self._spec({"a": {"type": "string"}})
        d = omega.generate_diff_report(spec, {"a": "x"})
        assert d["status"] == "match"
        assert d["missing_fields"] == [] and d["extra_fields"] == []

    def test_missing_required_field(self):
        spec = self._spec({"a": {"type": "string", "required": True}})
        d = omega.generate_diff_report(spec, {})
        assert d["status"] == "mismatch"
        assert "a" in d["missing_fields"]

    def test_missing_optional_field_not_reported(self):
        spec = self._spec({"a": {"type": "string", "required": False}})
        d = omega.generate_diff_report(spec, {})
        assert d["missing_fields"] == [] and d["status"] == "match"

    def test_extra_field(self):
        spec = self._spec({})
        d = omega.generate_diff_report(spec, {"extra": 1})
        assert d["status"] == "extra"
        assert "extra" in d["extra_fields"]

    def test_type_mismatch(self):
        spec = self._spec({"a": {"type": "string"}})
        d = omega.generate_diff_report(spec, {"a": 5})
        assert d["status"] == "mismatch"
        assert d["type_mismatches"][0]["field"] == "a"

    def test_number_accepts_int_and_float(self):
        spec = self._spec({"a": {"type": "number"}})
        for v in (1, 1.5):
            d = omega.generate_diff_report(spec, {"a": v})
            assert d["type_mismatches"] == []

    def test_enum_mismatch(self):
        spec = self._spec({"a": {"type": "string", "enum": ["x", "y"]}})
        d = omega.generate_diff_report(spec, {"a": "z"})
        assert d["status"] == "mismatch"
        assert d["value_mismatches"][0]["actual"] == "z"

    def test_non_dict_actual_no_crash(self):
        """actual 非 dict 时不崩溃，expected 全部按 missing 处理。"""
        spec = self._spec({"a": {"type": "string"}})
        d = omega.generate_diff_report(spec, None)
        assert "a" in d["missing_fields"]


# ── fingerprint ──

class TestFingerprint:
    def test_compute_canonical(self):
        a = omega.compute_output_fingerprint({"b": 1, "a": 2})
        b = omega.compute_output_fingerprint({"a": 2, "b": 1})
        assert a == b  # 键序无关

    def test_check_no_fingerprint_in_spec(self):
        match, exp, act = omega.check_fingerprint({}, {"x": 1})
        assert match is True and exp == "" and act == ""

    def test_check_match(self):
        out = {"status": "ok"}
        spec = {"fingerprint": omega.compute_output_fingerprint(out)}
        match, exp, act = omega.check_fingerprint(spec, out)
        assert match is True and exp == act

    def test_check_mismatch(self):
        spec = {"fingerprint": "0" * 16}
        match, exp, act = omega.check_fingerprint(spec, {"x": 1})
        assert match is False and exp == "0" * 16 and act != "0" * 16


# ── run_omega_loop ──

class TestRunOmegaLoop:
    def test_first_round_passes(self):
        spec = {"assertions": [{"type": "status_ok"}]}
        r = omega.run_omega_loop(spec, {"status": "ok"}, max_rounds=3)
        assert r["converged"] is True
        assert r["total_rounds"] == 1
        assert r["final_accuracy"] == 100.0

    def test_never_converges_within_max_rounds(self):
        spec = {"assertions": [{"type": "equals", "field": "status", "value": "ok"}]}
        r = omega.run_omega_loop(spec, {"status": "error"}, max_rounds=3)
        assert r["converged"] is False
        assert r["total_rounds"] == 3
        assert all(not rd["passed"] for rd in r["rounds"])
        assert all(r["rounds"][0]["failed_details"] == rd["failed_details"]
                   for rd in r["rounds"])

    def test_empty_rounds_converged_true(self):
        """max_rounds=0 → rounds 空 → 收敛恒 True（契约现状）。"""
        r = omega.run_omega_loop({"assertions": []}, {}, max_rounds=0)
        assert r["converged"] is True
        assert r["total_rounds"] == 0
        assert r["final_accuracy"] == 100.0

    def test_failed_details_only_failures(self):
        spec = {"assertions": [
            {"type": "status_ok"},
            {"type": "equals", "field": "x", "value": 1},
        ]}
        r = omega.run_omega_loop(spec, {"status": "ok", "x": 2}, max_rounds=2)
        assert len(r["rounds"][0]["failed_details"]) == 1


# ── verify_output ──

class TestVerifyOutput:
    def _write_spec(self, tmp_path, **over):
        spec = {
            "action_id": "t.a",
            "version": "1.0.0",
            "output_schema": {"type": "object",
                              "properties": {"status": {"type": "string"}}},
            "assertions": [{"type": "equals", "field": "status",
                             "value": "ok"}],
        }
        spec.update(over)
        p = tmp_path / "t.spec.json"
        p.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        return str(p), spec

    def test_pass(self, tmp_path):
        path, _ = self._write_spec(tmp_path)
        r = omega.verify_output(path, {"status": "ok"})
        assert r["status"] == "pass"
        assert r["gate"]["passed"] is True
        assert r["fingerprint"]["match"] is True
        assert "loop" not in r

    def test_fail_gate(self, tmp_path):
        path, _ = self._write_spec(tmp_path)
        r = omega.verify_output(path, {"status": "error"})
        assert r["status"] == "fail"

    def test_spec_error(self, tmp_path):
        path, _ = self._write_spec(tmp_path, assertions=[{"type": "bogus"}])
        r = omega.verify_output(path, {"status": "ok"})
        assert r["status"] == "spec_error"
        assert r["errors"]

    def test_fingerprint_mismatch_fails(self, tmp_path):
        path, spec = self._write_spec(tmp_path,
                                      fingerprint=omega.fnv1a64("zzz"))
        r = omega.verify_output(path, {"status": "ok"})
        assert r["status"] == "fail"
        assert r["fingerprint"]["match"] is False

    def test_enable_loop_on_fail(self, tmp_path):
        path, _ = self._write_spec(
            tmp_path,
            assertions=[{"type": "equals", "field": "status", "value": "ok"}])
        r = omega.verify_output(path, {"status": "error"}, enable_loop=True)
        assert r["status"] == "fail"
        assert r["loop"]["converged"] is False
        assert r["loop"]["total_rounds"] >= 1

    def test_enable_loop_not_added_on_pass(self, tmp_path):
        path, _ = self._write_spec(tmp_path)
        r = omega.verify_output(path, {"status": "ok"}, enable_loop=True)
        assert "loop" not in r


# ── learn_spec_from_history ──

class TestLearnSpecFromHistory:
    def test_empty_history(self):
        assert omega.learn_spec_from_history([]) == {}

    def test_non_dict_results_skipped(self):
        """result 非 dict 的记录被跳过（不崩溃）。"""
        spec = omega.learn_spec_from_history([{"result": "not-a-dict"},
                                              {"result": None}])
        assert spec.get("output_schema", {}).get("properties", {}) == {}

    def test_type_inference_and_required(self):
        history = [
            {"result": {"status": "ok", "count": 1}},
            {"result": {"status": "ok", "count": 5}},
            {"result": {"status": "error", "count": 9}},
        ]
        spec = omega.learn_spec_from_history(history)
        props = spec["output_schema"]["properties"]
        assert props["status"]["type"] == "string"
        assert props["count"]["type"] == "integer"
        assert spec["output_schema"]["required"] == ["status", "count"]
        assert spec["learned_from"] == 3

    def test_numeric_range(self):
        history = [{"result": {"n": 2}}, {"result": {"n": 8}}]
        spec = omega.learn_spec_from_history(history)
        prop = spec["output_schema"]["properties"]["n"]
        assert prop["minimum"] == 2 and prop["maximum"] == 8

    def test_enum_from_short_strings(self):
        history = [{"result": {"s": "a"}}, {"result": {"s": "b"}}]
        spec = omega.learn_spec_from_history(history)
        prop = spec["output_schema"]["properties"]["s"]
        assert prop["enum"] == ["a", "b"]

    def test_long_string_not_enum(self):
        long_val = "x" * 150
        history = [{"result": {"s": long_val}}]
        spec = omega.learn_spec_from_history(history)
        prop = spec["output_schema"]["properties"]["s"]
        assert "enum" not in prop

    def test_mixed_numeric_non_numeric_not_range(self):
        history = [{"result": {"m": 1}}, {"result": {"m": "s"}}]
        spec = omega.learn_spec_from_history(history)
        prop = spec["output_schema"]["properties"]["m"]
        assert "minimum" not in prop and "maximum" not in prop

    def test_low_frequency_not_required(self):
        history = [{"result": {"a": 1, "b": 2}}, {"result": {"a": 3}},
                   {"result": {"a": 4}}, {"result": {"a": 5}},
                   {"result": {"a": 6}}]
        spec = omega.learn_spec_from_history(history)
        assert "a" in spec["output_schema"]["required"]
        assert "b" not in spec["output_schema"]["required"]

    def test_field_stats_reported(self):
        history = [{"result": {"a": 1}}]
        spec = omega.learn_spec_from_history(history)
        assert spec["field_stats"]["a"]["count"] == 1
        assert spec["field_stats"]["a"]["types"] == {"int": 1}

    def test_wrapper_format_result_key(self):
        """记录形如 {"result": {...}} 时读内层。"""
        spec = omega.learn_spec_from_history([{"result": {"x": 1}}])
        assert "x" in spec["output_schema"]["properties"]


# ── generate_spec_template / _infer_schema ──

class TestSpecTemplate:
    def test_infer_scalars(self):
        assert omega._infer_schema("s") == {"type": "string"}
        assert omega._infer_schema(True) == {"type": "boolean"}
        assert omega._infer_schema(1) == {"type": "integer"}
        assert omega._infer_schema(1.5) == {"type": "number"}
        assert omega._infer_schema(None) == {"type": "string"}

    def test_infer_dict_nested(self):
        s = omega._infer_schema({"a": {"b": 1}})
        assert s["type"] == "object"
        assert s["properties"]["a"]["properties"]["b"]["type"] == "integer"

    def test_infer_list_items(self):
        s = omega._infer_schema([1, 2])
        assert s == {"type": "array", "items": {"type": "integer"}}

    def test_infer_empty_list(self):
        assert omega._infer_schema([]) == {"type": "array", "items": {}}

    def test_template_fields(self):
        ex = {"status": "ok", "data": {"n": 1}}
        t = omega.generate_spec_template("a.b", ex)
        assert t["action_id"] == "a.b"
        assert t["version"] == "1.0.0"
        assert t["output_schema"]["properties"]["data"]["type"] == "object"
        assert {"type": "status_ok"} in t["assertions"]
        assert {"type": "exists", "field": "status"} in t["assertions"]
        assert t["fingerprint"] == omega.compute_output_fingerprint(ex)


# ── batch_verify ──

class TestBatchVerify:
    def _spec_path(self, tmp_path):
        spec = {
            "action_id": "b.v", "version": "1.0.0",
            "output_schema": {"type": "object"},
            "assertions": [{"type": "equals", "field": "status",
                             "value": "ok"}],
        }
        p = tmp_path / "b.spec.json"
        p.write_text(json.dumps(spec), encoding="utf-8")
        return str(p)

    def test_mixed_results(self, tmp_path):
        path = self._spec_path(tmp_path)
        r = omega.batch_verify(path, [{"status": "ok"}, {"status": "err"},
                                      {"status": "ok"}])
        assert r["total"] == 3 and r["passed"] == 2 and r["failed"] == 1
        assert r["pass_rate"] == 66.7
        assert len(r["results"]) == 3

    def test_empty_outputs_zero_rate(self, tmp_path):
        path = self._spec_path(tmp_path)
        r = omega.batch_verify(path, [])
        assert r["total"] == 0 and r["pass_rate"] == 0 and r["passed"] == 0


# ── format_report ──

class TestFormatReport:
    def test_spec_error_format(self):
        text = omega.format_report({"status": "spec_error",
                                    "errors": ["缺少必填字段: action_id"]})
        assert "SPEC_ERROR" in text
        assert "缺少必填字段" in text

    def test_pass_format(self):
        report = {
            "status": "pass",
            "gate": {"accuracy": 100.0, "passed_count": 2, "total": 2,
                     "passed": True},
            "fingerprint": {"match": True, "expected": omega.fnv1a64("x"),
                            "actual": omega.fnv1a64("x")},
            "diff": {"status": "match"},
        }
        text = omega.format_report(report)
        assert "PASS" in text
        assert "100.0%" in text
        assert "✓" in text

    def test_fail_format_shows_failed_details(self):
        report = {
            "status": "fail",
            "gate": {"accuracy": 50.0, "passed_count": 1, "total": 2,
                     "passed": False,
                     "details": [
                         {"passed": True, "message": "ok"},
                         {"passed": False, "message": "字段 'a' 不存在"},
                     ]},
            "diff": {"status": "mismatch",
                     "missing_fields": ["z"],
                     "type_mismatches": [{"field": "a", "expected": "string",
                                          "actual": "int"}]},
            "fingerprint": {"match": False, "expected": omega.fnv1a64("x"),
                            "actual": omega.fnv1a64("y")},
        }
        text = omega.format_report(report)
        assert "FAIL" in text
        assert "失败详情" in text
        assert "字段 'a' 不存在" in text
        assert "缺失字段: z" in text
        assert "类型不匹配: a" in text
        assert "✗" in text

    def test_extra_only_diff_has_no_mismatch_lines(self):
        report = {
            "status": "pass",
            "gate": {"accuracy": 100.0, "passed": True},
            "diff": {"status": "extra", "missing_fields": [],
                     "type_mismatches": []},
            "fingerprint": {},
        }
        text = omega.format_report(report)
        assert "缺失字段" not in text
        assert "类型不匹配" not in text

    def test_unknown_status(self):
        text = omega.format_report({"status": "weird"})
        assert "WEIRD" in text


# ── __all__ ──

class TestModuleExports:
    def test_all_names_importable(self):
        for name in omega.__all__:
            assert hasattr(omega, name), name

    def test_expected_symbols(self):
        for sym in ("run_gate", "verify_output", "batch_verify",
                    "check_assertion", "validate_spec", "load_spec",
                    "fnv1a64", "format_report", "learn_spec_from_history",
                    "generate_spec_template"):
            assert sym in omega.__all__
