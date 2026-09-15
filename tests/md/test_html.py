"""tests/md/test_html.py — HTML 转换测试"""
import pytest
import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from vools.md.html import to_html, to_html_file
from vools.md.parser import parse, Document, Heading, Paragraph, CodeBlock, InlineText


class TestToHtml:
    """HTML 转换测试"""

    def test_heading(self):
        result = to_html('# Hello')
        assert '<h1>Hello</h1>' in result

    def test_paragraph(self):
        result = to_html('Hello world')
        assert '<p>' in result
        assert 'Hello world' in result

    def test_code_block(self):
        result = to_html('```python\nprint(1)\n```')
        assert '<pre>' in result
        assert '<code' in result
        assert 'print(1)' in result

    def test_bold(self):
        result = to_html('**bold**')
        assert '<strong>bold</strong>' in result

    def test_italic(self):
        result = to_html('*italic*')
        assert '<em>italic</em>' in result

    def test_link(self):
        result = to_html('[link](https://example.com)')
        assert '<a href="https://example.com">link</a>' in result

    def test_strikethrough(self):
        result = to_html('~~deleted~~')
        assert '<del>deleted</del>' in result

    def test_code_inline(self):
        result = to_html('`code`')
        assert '<code>code</code>' in result

    def test_blockquote(self):
        result = to_html('> quoted')
        assert '<blockquote>' in result

    def test_unordered_list(self):
        result = to_html('- item 1\n- item 2')
        assert '<ul>' in result
        assert '<li>' in result

    def test_ordered_list(self):
        result = to_html('1. first\n2. second')
        assert '<ol>' in result
        assert '<li>' in result

    def test_divider(self):
        result = to_html('---')
        assert '<hr' in result

    def test_html_escaping(self):
        result = to_html('<script>alert(1)</script>')
        assert '<script>' not in result
        assert '&lt;script&gt;' in result

    def test_from_ast(self):
        ast = Document(children=[Heading(level=1, children=[InlineText(text='Title')])])
        result = to_html(ast)
        assert '<h1>Title</h1>' in result

    def test_markdown_body_wrapper(self):
        result = to_html('# Test')
        assert 'markdown-body' in result


class TestToHtmlFile:
    """HTML 文件生成测试"""

    def test_to_html_file(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
            filepath = f.name
        try:
            result = to_html_file('# Hello', filepath)
            assert result == filepath
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            assert '<!DOCTYPE html>' in content
            assert '<h1>Hello</h1>' in content
        finally:
            os.unlink(filepath)
