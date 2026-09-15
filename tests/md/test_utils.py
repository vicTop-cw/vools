"""tests/md/test_utils.py — 工具函数测试"""
import pytest
import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from vools.md.utils import (
    extract_metadata, generate_toc, generate_toc_markdown,
    extract_code_blocks, count_words, strip_markdown, find_headings,
    to_json, to_org_mode, to_plain_text,
)


class TestExtractMetadata:
    """元数据提取测试"""

    def test_yaml_front_matter(self):
        text = '---\ntitle: Hello\nauthor: World\n---\n# Content'
        meta = extract_metadata(text)
        assert meta.get('title') == 'Hello'
        assert meta.get('author') == 'World'

    def test_no_metadata(self):
        text = '# Hello\n\nWorld'
        meta = extract_metadata(text)
        assert meta == {}

    def test_empty_string(self):
        meta = extract_metadata('')
        assert meta == {}

    def test_incomplete_front_matter(self):
        text = '---\ntitle: Hello\n# No closing'
        meta = extract_metadata(text)
        assert meta == {}


class TestGenerateToc:
    """目录生成测试"""

    def test_basic_toc(self):
        text = '# Hello\n## Sub\n### Deep'
        toc = generate_toc(text)
        assert len(toc) == 3
        assert toc[0]['level'] == 1
        assert toc[0]['text'] == 'Hello'

    def test_max_level(self):
        text = '# H1\n## H2\n### H3\n#### H4'
        toc = generate_toc(text, max_level=2)
        assert len(toc) == 2

    def test_empty(self):
        toc = generate_toc('')
        assert toc == []

    def test_anchor_id(self):
        text = '# Hello World'
        toc = generate_toc(text)
        assert toc[0]['id'] == 'hello_world'


class TestGenerateTocMarkdown:
    """Markdown 目录生成测试"""

    def test_toc_markdown(self):
        text = '# Hello\n## Sub'
        result = generate_toc_markdown(text)
        assert '## 目录' in result
        assert '[Hello]' in result


class TestExtractCodeBlocks:
    """代码块提取测试"""

    def test_extract_python(self):
        text = '```python\nprint(1)\n```'
        blocks = extract_code_blocks(text)
        assert len(blocks) == 1
        assert blocks[0]['language'] == 'python'
        assert 'print(1)' in blocks[0]['code']

    def test_extract_multiple(self):
        text = '```python\na\n```\n\n```javascript\nb\n```'
        blocks = extract_code_blocks(text)
        assert len(blocks) == 2

    def test_filter_by_language(self):
        text = '```python\na\n```\n```javascript\nb\n```'
        blocks = extract_code_blocks(text, language='python')
        assert len(blocks) == 1
        assert blocks[0]['language'] == 'python'

    def test_no_code_blocks(self):
        blocks = extract_code_blocks('# Hello\nWorld')
        assert blocks == []


class TestCountWords:
    """词数统计测试"""

    def test_basic_count(self):
        text = 'Hello world'
        count = count_words(text)
        assert count >= 2

    def test_empty(self):
        count = count_words('')
        assert count == 0


class TestStripMarkdown:
    """Markdown 剥离测试"""

    def test_strip_bold(self):
        result = strip_markdown('**bold**')
        assert result == 'bold'

    def test_strip_italic(self):
        result = strip_markdown('*italic*')
        assert result == 'italic'

    def test_strip_heading(self):
        result = strip_markdown('# Hello')
        assert 'Hello' in result
        assert '#' not in result


class TestFindHeadings:
    """标题查找测试"""

    def test_find_headings(self):
        text = '# H1\n## H2\n### H3'
        headings = find_headings(text)
        assert len(headings) >= 3


class TestToJson:
    """JSON 转换测试"""

    def test_to_json(self):
        text = '# Hello'
        result = to_json(text)
        assert isinstance(result, str)
        assert 'Hello' in result


class TestToOrgMode:
    """Org-mode 转换测试"""

    def test_to_org(self):
        text = '# Hello\n\nWorld'
        result = to_org_mode(text)
        assert isinstance(result, str)
        assert 'Hello' in result


class TestToPlainText:
    """纯文本转换测试"""

    def test_to_plain(self):
        text = '# Hello\n\n**World**'
        result = to_plain_text(text)
        assert 'Hello' in result
        assert 'World' in result
        assert '**' not in result
