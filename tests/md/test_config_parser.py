"""
测试：配置解析器（config_parser.py）

覆盖：
  - JSON 解析
  - TOML 解析（简化解析器回退）
  - YAML 解析（简化解析器回退）
  - Lua 配置执行（简化解析器回退）
  - parse_config_block 统一入口
  - render_config 配置文本生成
"""

import pytest
from vools.md.config_parser import (
    parse_json, parse_toml, parse_yaml, execute_lua,
    parse_config_block, validate_config, render_config,
    ConfigParseError,
)


# ═══════════════════════════════════════════════════════════════
# JSON 解析
# ═══════════════════════════════════════════════════════════════

class TestParseJson:
    """JSON 解析测试"""

    def test_basic_object(self):
        result = parse_json('{"name": "test", "value": 42}')
        assert result == {"name": "test", "value": 42}

    def test_nested_object(self):
        result = parse_json('{"a": {"b": {"c": 1}}}')
        assert result == {"a": {"b": {"c": 1}}}

    def test_array(self):
        result = parse_json('[1, 2, 3]')
        assert result == [1, 2, 3]

    def test_array_of_objects(self):
        result = parse_json('[{"x": 1}, {"y": 2}]')
        assert result == [{"x": 1}, {"y": 2}]

    def test_invalid_json(self):
        with pytest.raises(ConfigParseError):
            parse_json('{"invalid": ')

    def test_empty_string(self):
        with pytest.raises(ConfigParseError):
            parse_json('')


# ═══════════════════════════════════════════════════════════════
# TOML 解析（简化解析器回退）
# ═══════════════════════════════════════════════════════════════

class TestParseToml:
    """TOML 解析测试"""

    def test_simple_key_value(self):
        result = parse_toml('name = "test"')
        assert result == {"name": "test"}

    def test_section(self):
        result = parse_toml('[server]\nhost = "localhost"\nport = 8080')
        assert result == {"server": {"host": "localhost", "port": 8080}}

    def test_nested_section(self):
        result = parse_toml('[a.b.c]\nvalue = 1')
        assert result == {"a": {"b": {"c": {"value": 1}}}}

    def test_array(self):
        result = parse_toml('items = [1, 2, 3]')
        assert result == {"items": [1, 2, 3]}

    def test_array_of_strings(self):
        result = parse_toml('deps = ["nim", "rust", "go"]')
        assert result == {"deps": ["nim", "rust", "go"]}

    def test_boolean(self):
        result = parse_toml('enabled = true\ndisabled = false')
        assert result == {"enabled": True, "disabled": False}

    def test_integer(self):
        result = parse_toml('count = 42')
        assert result == {"count": 42}

    def test_float(self):
        result = parse_toml('ratio = 3.14')
        assert result == {"ratio": 3.14}

    def test_comments_ignored(self):
        result = parse_toml('# This is a comment\nname = "test"')
        assert result == {"name": "test"}

    def test_mixed_sections(self):
        toml = '''
[dependencies]
nim = "0.9.0"
rust = { version = "1.70" }

[config]
timeout = 30
enabled = true
'''
        result = parse_toml(toml)
        assert "dependencies" in result
        assert "config" in result
        assert result["dependencies"]["nim"] == "0.9.0"
        assert result["config"]["timeout"] == 30


# ═══════════════════════════════════════════════════════════════
# YAML 解析（简化解析器回退）
# ═══════════════════════════════════════════════════════════════

class TestParseYaml:
    """YAML 解析测试"""

    def test_simple_key_value(self):
        result = parse_yaml('name: test')
        assert result == {"name": "test"}

    def test_nested(self):
        yaml = '''
server:
  host: localhost
  port: 8080
'''
        result = parse_yaml(yaml)
        assert "server" in result
        assert result["server"]["host"] == "localhost"

    def test_integer(self):
        result = parse_yaml('port: 8080')
        assert result == {"port": 8080}

    def test_boolean(self):
        result = parse_yaml('enabled: true')
        assert result == {"enabled": True}

    def test_string_with_colon(self):
        result = parse_yaml('url: "http://example.com"')
        assert result == {"url": "http://example.com"}

    def test_quoted_string(self):
        result = parse_yaml('name: "hello world"')
        assert result == {"name": "hello world"}

    def test_empty_value(self):
        result = parse_yaml('key: ')
        # 空值可以是 "" 或 None（取决于解析器）
        assert result["key"] in ("", None)

    def test_comments_ignored(self):
        result = parse_yaml('# comment\nname: test')
        assert result == {"name": "test"}


# ═══════════════════════════════════════════════════════════════
# Lua 配置执行（简化解析器回退）
# ═══════════════════════════════════════════════════════════════

class TestExecuteLua:
    """Lua 配置执行测试"""

    def test_simple_table(self):
        lua = 'return { name = "test", value = 42 }'
        result = execute_lua(lua)
        assert result["name"] == "test"
        assert result["value"] == 42

    def test_nested_table(self):
        lua = 'return { server = { host = "localhost", port = 8080 } }'
        result = execute_lua(lua)
        assert result["server"]["host"] == "localhost"
        assert result["server"]["port"] == 8080

    def test_with_context(self):
        lua = 'return { env = "production" }'
        result = execute_lua(lua, context={"env": "development"})
        assert "env" in result

    def test_no_return(self):
        lua = 'local config = { name = "test" }'
        result = execute_lua(lua)
        assert isinstance(result, dict)


# ═══════════════════════════════════════════════════════════════
# parse_config_block 统一入口
# ═══════════════════════════════════════════════════════════════

class TestParseConfigBlock:
    """parse_config_block 统一入口测试"""

    def test_json(self):
        result = parse_config_block('{"key": "value"}', "json")
        assert result == {"key": "value"}

    def test_toml(self):
        result = parse_config_block('key = "value"', "toml")
        assert result == {"key": "value"}

    def test_yaml(self):
        result = parse_config_block('key: value', "yaml")
        assert result == {"key": "value"}

    def test_lua(self):
        result = parse_config_block('return { key = "value" }', "lua")
        assert result["key"] == "value"

    def test_unsupported_language(self):
        with pytest.raises(ConfigParseError):
            parse_config_block('key = value', "xml")

    def test_case_insensitive(self):
        result = parse_config_block('{"key": "value"}', "JSON")
        assert result == {"key": "value"}


# ═══════════════════════════════════════════════════════════════
# validate_config
# ═══════════════════════════════════════════════════════════════

class TestValidateConfig:
    """validate_config 测试"""

    def test_dict(self):
        assert validate_config({"key": "value"}) is True

    def test_list(self):
        assert validate_config([1, 2, 3]) is True

    def test_string(self):
        assert validate_config("hello") is True

    def test_int(self):
        assert validate_config(42) is True

    def test_none(self):
        assert validate_config(None) is False

    def test_complex_object(self):
        assert validate_config({"nested": {"deep": [1, 2, 3]}}) is True


# ═══════════════════════════════════════════════════════════════
# render_config
# ═══════════════════════════════════════════════════════════════

class TestRenderConfig:
    """render_config 测试"""

    def test_json(self):
        result = render_config({"key": "value"}, "json")
        assert "key" in result
        assert "value" in result

    def test_toml(self):
        result = render_config({"name": "test"}, "toml")
        assert "name" in result
        assert "test" in result

    def test_yaml(self):
        result = render_config({"name": "test"}, "yaml")
        assert "name" in result
        assert "test" in result

    def test_unsupported_format(self):
        with pytest.raises(ConfigParseError):
            render_config({"key": "value"}, "xml")

    def test_nested_json(self):
        data = {"server": {"host": "localhost", "port": 8080}}
        result = render_config(data, "json")
        assert "server" in result
        assert "host" in result
