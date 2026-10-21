"""
测试：Parser 配置块解析（ConfigBlock / LangBlock）

覆盖：
  - #!config json 块解析为 ConfigBlock
  - #!lang toml/yaml/lua 块解析为 LangBlock
  - parse_to_dict 序列化
  - AST 往返一致性
"""

import pytest
from vools.md.parser import parse, parse_to_dict, ConfigBlock, LangBlock


class TestConfigBlockParsing:
    """#!config json 块解析测试"""

    def test_config_block_basic(self):
        md = '''```#!config json
{"executor": "default", "timeout": 30}
```'''
        doc = parse(md)
        assert len(doc.children) == 1
        node = doc.children[0]
        assert isinstance(node, ConfigBlock)
        assert node.config_type == "json"
        assert '"executor"' in node.content

    def test_config_block_multiple(self):
        md = '''```#!config json
{"a": 1}
```

Some text

```#!config json
{"b": 2}
```'''
        doc = parse(md)
        config_blocks = [n for n in doc.children if isinstance(n, ConfigBlock)]
        assert len(config_blocks) == 2

    def test_config_block_content_preserved(self):
        md = '''```#!config json
{
  "name": "test",
  "nested": {
    "key": "value"
  }
}
```'''
        doc = parse(md)
        node = doc.children[0]
        assert isinstance(node, ConfigBlock)
        assert '"nested"' in node.content


class TestLangBlockParsing:
    """#!lang 块解析测试"""

    def test_lang_block_toml(self):
        md = '''```#!lang toml
[dependencies]
nim = "0.9.0"
```'''
        doc = parse(md)
        assert len(doc.children) == 1
        node = doc.children[0]
        assert isinstance(node, LangBlock)
        assert node.language == "toml"
        assert "nim" in node.content

    def test_lang_block_yaml(self):
        md = '''```#!lang yaml
language: nim
version: "0.9.0"
```'''
        doc = parse(md)
        node = doc.children[0]
        assert isinstance(node, LangBlock)
        assert node.language == "yaml"

    def test_lang_block_lua(self):
        md = '''```#!lang lua
return { name = "test" }
```'''
        doc = parse(md)
        node = doc.children[0]
        assert isinstance(node, LangBlock)
        assert node.language == "lua"

    def test_lang_block_multiple(self):
        md = '''```#!lang toml
[deps]
nim = "0.9.0"
```

```#!lang yaml
lang: nim
```

```#!lang lua
return {}
```'''
        doc = parse(md)
        lang_blocks = [n for n in doc.children if isinstance(n, LangBlock)]
        assert len(lang_blocks) == 3
        assert lang_blocks[0].language == "toml"
        assert lang_blocks[1].language == "yaml"
        assert lang_blocks[2].language == "lua"

    def test_lang_block_with_context(self):
        md = '''```#!lang toml
[project]
name = "myapp"
```'''
        doc = parse(md)
        node = doc.children[0]
        assert isinstance(node, LangBlock)
        assert "project" in node.content


class TestParseToDictConfig:
    """parse_to_dict 配置块序列化测试"""

    def test_config_block_dict(self):
        md = '''```#!config json
{"key": "value"}
```'''
        d = parse_to_dict(md)
        assert d["type"] == "document"
        children = d["children"]
        assert len(children) == 1
        assert children[0]["type"] == "config_block"
        assert children[0]["config_type"] == "json"

    def test_lang_block_dict(self):
        md = '''```#!lang toml
key = "value"
```'''
        d = parse_to_dict(md)
        children = d["children"]
        assert children[0]["type"] == "lang_block"
        assert children[0]["language"] == "toml"


class TestMixedContent:
    """混合内容测试"""

    def test_config_and_heading(self):
        md = '''# Title

```#!config json
{"key": "value"}
```

Some paragraph'''
        doc = parse(md)
        types = [type(n).__name__ for n in doc.children]
        assert "Heading" in types
        assert "ConfigBlock" in types
        assert "Paragraph" in types

    def test_config_and_code_block(self):
        md = '''```python
print("hello")
```

```#!config json
{"key": "value"}
```'''
        doc = parse(md)
        from vools.md.parser import CodeBlock
        code_blocks = [n for n in doc.children if isinstance(n, CodeBlock)]
        config_blocks = [n for n in doc.children if isinstance(n, ConfigBlock)]
        assert len(code_blocks) == 1
        assert len(config_blocks) == 1
        assert code_blocks[0].language == "python"

    def test_empty_config_block(self):
        md = '''```#!config json
```'''
        doc = parse(md)
        node = doc.children[0]
        assert isinstance(node, ConfigBlock)
        assert node.content == ""


class TestEdgeCases:
    """边界情况测试"""

    def test_config_without_type(self):
        md = '''```#!config
{"key": "value"}
```'''
        doc = parse(md)
        node = doc.children[0]
        assert isinstance(node, ConfigBlock)
        assert node.config_type == "json"  # 默认 json

    def test_lang_without_type(self):
        md = '''```#!lang
some content
```'''
        doc = parse(md)
        node = doc.children[0]
        assert isinstance(node, LangBlock)
        assert node.language == ""  # 空语言

    def test_config_block_not_confused_with_code(self):
        """确保 #!config 前缀不会被当作普通代码块"""
        md = '''```json
{"key": "value"}
```'''
        doc = parse(md)
        from vools.md.parser import CodeBlock
        node = doc.children[0]
        assert isinstance(node, CodeBlock)
        assert node.language == "json"
