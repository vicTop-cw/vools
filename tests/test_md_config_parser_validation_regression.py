# -*- coding: utf-8 -*-
"""回归测试：md.config_parser 的入参零校验 + validate_config 忽略 schema（BUG-521）。

修复前：

    parse_yaml(None)      # 静默返回 {}（把"没给文本"当成"空配置"）
    parse_toml(None)      # AttributeError: 'NoneType' object has no attribute 'replace'
    parse_json(None)      # 底层 json 的 TypeError（看不出是哪个函数）
    parse_config_block('x', None)   # AttributeError: 'NoneType' object has no attribute 'lower'
    validate_config({"a": "x"}, {"a": int})   # -> True  ❌ 类型不符却通过
    validate_config({"b": 1}, {"a": int})     # -> True  ❌ 缺键却通过

根因：validate_config 的 docstring 写着"schema: 期望的结构（可选，用于校验）"，
但实现**完全忽略 schema**，只要 parsed 是基本类型就返回 True。

修复：
- parse_json/parse_yaml/parse_toml 入口校验 text 为字符串；
- parse_config_block 校验 language（非空字符串）与 content（字符串）；
- validate_config 在给出 schema 时做浅层结构校验（顶层键必须存在；schema 值为
  类型时要求 isinstance 匹配），未给 schema 时行为与旧版一致。
"""

import importlib

import pytest

cp = importlib.import_module("vools.md.config_parser")


class TestParserInputValidation:
    @pytest.mark.parametrize("fn_name", ["parse_json", "parse_yaml", "parse_toml"])
    @pytest.mark.parametrize("bad", [None, 123, ["a"]])
    def test_non_str_text(self, fn_name, bad):
        with pytest.raises(TypeError) as ei:
            getattr(cp, fn_name)(bad)
        assert fn_name in str(ei.value)

    @pytest.mark.parametrize("bad", [None, 123, ""])
    def test_config_block_language(self, bad):
        with pytest.raises((ValueError, TypeError)):
            cp.parse_config_block('{"a": 1}', bad)

    @pytest.mark.parametrize("bad", [None, 123])
    def test_config_block_content(self, bad):
        with pytest.raises(TypeError) as ei:
            cp.parse_config_block(bad, "json")
        assert "content" in str(ei.value)


class TestValidateConfigUsesSchema:
    def test_type_mismatch_rejected(self):
        assert cp.validate_config({"a": "x"}, {"a": int}) is False

    def test_type_match_accepted(self):
        assert cp.validate_config({"a": 1}, {"a": int}) is True

    def test_missing_key_rejected(self):
        assert cp.validate_config({"b": 1}, {"a": int}) is False

    def test_non_type_schema_value_only_requires_presence(self):
        # schema 值不是类型时只要求键存在
        assert cp.validate_config({"a": "anything"}, {"a": "expected"}) is True

    def test_non_dict_parsed_with_schema_rejected(self):
        assert cp.validate_config([1, 2], {"a": int}) is False

    @pytest.mark.parametrize("bad", ["x", 123, [1]])
    def test_bad_schema_type(self, bad):
        with pytest.raises(TypeError) as ei:
            cp.validate_config({}, bad)
        assert "schema" in str(ei.value)


class TestBehaviourUnchanged:
    def test_yaml_empty_still_empty_dict(self):
        assert cp.parse_yaml("") == {}
        assert cp.parse_yaml("   ") == {}

    def test_normal_parsing(self):
        assert cp.parse_json('{"a": 1}') == {"a": 1}
        assert cp.parse_yaml("a: 1") == {"a": 1}
        assert cp.parse_toml("a = 1") == {"a": 1}

    def test_config_block_all_languages(self):
        assert cp.parse_config_block('{"a": 1}', "json") == {"a": 1}
        assert cp.parse_config_block("a: 1", "yaml") == {"a": 1}
        assert cp.parse_config_block("a = 1", "toml") == {"a": 1}

    def test_unknown_language_loud(self):
        with pytest.raises(cp.ConfigParseError):
            cp.parse_config_block("x", "xml")

    @pytest.mark.parametrize("value", [{"a": 1}, [1, 2], "s", 42, 3.5, True])
    def test_no_schema_basic_types(self, value):
        assert cp.validate_config(value) is True

    def test_none_invalid(self):
        assert cp.validate_config(None) is False

    def test_render_config(self):
        assert '"a": 1' in cp.render_config({"a": 1}, "json")
