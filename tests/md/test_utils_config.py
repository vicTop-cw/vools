"""
测试：utils.py 配置提取函数

覆盖：
  - extract_configs 提取所有配置块
  - extract_config_blocks 提取 #!config 块
  - extract_lang_blocks 提取 #!lang 块（含过滤）
  - extract_frontmatter 升级版 frontmatter
  - render_config 配置文本生成
"""

import pytest
from vools.md.utils import (
    extract_configs, extract_config_blocks,
    extract_lang_blocks, extract_frontmatter,
    extract_metadata, render_config,
)


class TestExtractConfigs:
    """extract_configs 测试"""

    def test_all_configs(self):
        md = '''```#!config json
{"executor": "default"}
```

```#!lang toml
[deps]
nim = "0.9.0"
```

```#!lang yaml
lang: nim
```'''
        configs = extract_configs(md)
        assert len(configs) == 3
        assert configs[0]["type"] == "config"
        assert configs[0]["subtype"] == "json"
        assert configs[1]["type"] == "lang"
        assert configs[1]["subtype"] == "toml"
        assert configs[2]["type"] == "lang"
        assert configs[2]["subtype"] == "yaml"

    def test_configs_with_parsed(self):
        md = '''```#!config json
{"key": "value"}
```'''
        configs = extract_configs(md)
        assert len(configs) == 1
        assert configs[0]["parsed"] is not None
        assert configs[0]["parsed"]["key"] == "value"

    def test_no_configs(self):
        md = "# Just a heading\n\nSome text"
        configs = extract_configs(md)
        assert len(configs) == 0

    def test_invalid_json_returns_none_parsed(self):
        md = '''```#!config json
{"invalid":
```'''
        configs = extract_configs(md)
        assert len(configs) == 1
        assert configs[0]["parsed"] is None  # 解析失败


class TestExtractConfigBlocks:
    """extract_config_blocks 测试"""

    def test_only_config_blocks(self):
        md = '''```#!config json
{"a": 1}
```

```#!lang toml
b = "2"
```'''
        blocks = extract_config_blocks(md)
        assert len(blocks) == 1
        assert blocks[0]["subtype"] == "json"
        assert blocks[0]["parsed"]["a"] == 1

    def test_no_config_blocks(self):
        md = "# Title\n\n```python\nprint(1)\n```"
        blocks = extract_config_blocks(md)
        assert len(blocks) == 0


class TestExtractLangBlocks:
    """extract_lang_blocks 测试"""

    def test_all_lang_blocks(self):
        md = '''```#!lang toml
[deps]
nim = "0.9.0"
```

```#!lang yaml
lang: nim
```'''
        blocks = extract_lang_blocks(md)
        assert len(blocks) == 2

    def test_filter_by_language(self):
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
        blocks = extract_lang_blocks(md, language="toml")
        assert len(blocks) == 1
        assert blocks[0]["language"] == "toml"

        blocks_yaml = extract_lang_blocks(md, language="yaml")
        assert len(blocks_yaml) == 1
        assert blocks_yaml[0]["language"] == "yaml"

        blocks_lua = extract_lang_blocks(md, language="lua")
        assert len(blocks_lua) == 1
        assert blocks_lua[0]["language"] == "lua"

    def test_no_lang_blocks(self):
        md = "# Title\n\n```python\nprint(1)\n```"
        blocks = extract_lang_blocks(md)
        assert len(blocks) == 0


class TestExtractFrontmatter:
    """extract_frontmatter 测试"""

    def test_basic_frontmatter(self):
        md = '''---
title: Hello
date: 2024-01-01
---

# World'''
        result = extract_frontmatter(md)
        assert result["title"] == "Hello"
        assert result["date"] == "2024-01-01"

    def test_no_frontmatter(self):
        md = "# Just a heading"
        result = extract_frontmatter(md)
        assert result == {}

    def test_nested_frontmatter(self):
        md = '''---
title: Hello
meta:
  author: test
  version: 1.0
---

# World'''
        result = extract_frontmatter(md)
        assert result["title"] == "Hello"
        assert "meta" in result
        assert result["meta"]["author"] == "test"


class TestExtractMetadata:
    """extract_metadata 向后兼容测试"""

    def test_backward_compatible(self):
        md = '''---
title: Hello
date: 2024-01-01
---

# World'''
        result = extract_metadata(md)
        assert result["title"] == "Hello"

    def test_no_frontmatter_returns_empty(self):
        md = "# Just a heading"
        result = extract_metadata(md)
        assert result == {}

    def test_returns_dict(self):
        md = "---\nkey: value\n---\n# Title"
        result = extract_metadata(md)
        assert isinstance(result, dict)


class TestRenderConfig:
    """render_config 测试"""

    def test_render_json(self):
        result = render_config({"key": "value"}, "json")
        assert "key" in result
        assert "value" in result

    def test_render_toml(self):
        result = render_config({"name": "test"}, "toml")
        assert "name" in result
        assert "test" in result

    def test_render_yaml(self):
        result = render_config({"name": "test"}, "yaml")
        assert "name" in result
        assert "test" in result
