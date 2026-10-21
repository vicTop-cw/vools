"""
测试：Generator 和 HTML 配置块渲染

覆盖：
  - generate() 将 ConfigBlock/LangBlock 渲染回 Markdown
  - to_html() 将 ConfigBlock/LangBlock 渲染为 HTML
"""

import pytest
from vools.md import parse, generate, to_html
from vools.md.parser import ConfigBlock, LangBlock


class TestGeneratorConfig:
    """Generator 配置块测试"""

    def test_config_block_roundtrip(self):
        md = '''```#!config json
{"key": "value"}
```'''
        ast = parse(md)
        generated = generate(ast)
        # 检查生成的 Markdown 包含 #!config json
        assert '#!config json' in generated
        assert '"key"' in generated

    def test_lang_block_roundtrip(self):
        md = '''```#!lang toml
[deps]
nim = "0.9.0"
```'''
        ast = parse(md)
        generated = generate(ast)
        assert '#!lang toml' in generated
        assert 'nim' in generated

    def test_multiple_config_blocks(self):
        md = '''```#!config json
{"a": 1}
```

```#!lang yaml
b: 2
```'''
        ast = parse(md)
        generated = generate(ast)
        assert '#!config json' in generated
        assert '#!lang yaml' in generated

    def test_config_block_not_confused_with_code(self):
        md = '''```python
print("hello")
```'''
        ast = parse(md)
        generated = generate(ast)
        assert '```python' in generated
        assert '#!config' not in generated


class TestHtmlConfig:
    """HTML 配置块测试"""

    def test_config_block_html(self):
        md = '''```#!config json
{"key": "value"}
```'''
        html = to_html(md)
        # 检查生成的 HTML 包含配置内容
        assert 'language-config-json' in html
        assert 'key' in html

    def test_lang_block_html(self):
        md = '''```#!lang toml
[deps]
nim = "0.9.0"
```'''
        html = to_html(md)
        assert 'language-toml' in html
        assert 'nim' in html

    def test_config_block_escaping(self):
        md = '''```#!config json
{"html": "<script>"}
```'''
        html = to_html(md)
        # 检查 HTML 转义
        assert '&lt;script&gt;' in html
        assert '<script>' not in html
