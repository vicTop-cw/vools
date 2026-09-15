"""tests/md/test_generator.py — Markdown 生成器测试"""
import pytest
import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from vools.md.generator import generate, generate_to_file
from vools.md.parser import (
    parse, Document, Heading, Paragraph, CodeBlock,
    BlockQuote, MdList, ListItem, Divider, InlineText,
)


class TestGenerate:
    """生成函数测试"""

    def test_generate_heading(self):
        ast = Document(children=[Heading(level=1, children=[InlineText(text='Hello')])])
        result = generate(ast)
        assert '# Hello' in result

    def test_generate_paragraph(self):
        ast = Document(children=[Paragraph(children=[InlineText(text='Hello world')])])
        result = generate(ast)
        assert 'Hello world' in result

    def test_generate_code_block(self):
        ast = Document(children=[CodeBlock(code='print(1)', language='python')])
        result = generate(ast)
        assert '```python' in result
        assert 'print(1)' in result

    def test_generate_bold(self):
        ast = Document(children=[Paragraph(children=[InlineText(text='bold', bold=True)])])
        result = generate(ast)
        assert '**bold**' in result

    def test_generate_italic(self):
        ast = Document(children=[Paragraph(children=[InlineText(text='italic', italic=True)])])
        result = generate(ast)
        assert '*italic*' in result

    def test_generate_code_inline(self):
        ast = Document(children=[Paragraph(children=[InlineText(text='code', code=True)])])
        result = generate(ast)
        assert '`code`' in result

    def test_generate_strikethrough(self):
        ast = Document(children=[Paragraph(children=[InlineText(text='del', strikethrough=True)])])
        result = generate(ast)
        assert '~~del~~' in result

    def test_generate_link(self):
        ast = Document(children=[Paragraph(
            children=[InlineText(text='link', link='https://example.com')]
        )])
        result = generate(ast)
        assert '[link](https://example.com)' in result

    def test_generate_blockquote(self):
        ast = Document(children=[BlockQuote(
            children=[Paragraph(children=[InlineText(text='quoted')])]
        )])
        result = generate(ast)
        assert '> quoted' in result

    def test_generate_unordered_list(self):
        ast = Document(children=[MdList(ordered=False, items=[
            ListItem(children=[InlineText(text='item 1')]),
            ListItem(children=[InlineText(text='item 2')]),
        ])])
        result = generate(ast)
        assert '- item 1' in result
        assert '- item 2' in result

    def test_generate_ordered_list(self):
        ast = Document(children=[MdList(ordered=True, items=[
            ListItem(children=[InlineText(text='first')]),
            ListItem(children=[InlineText(text='second')]),
        ])])
        result = generate(ast)
        assert '1. first' in result
        assert '2. second' in result

    def test_generate_divider(self):
        ast = Document(children=[Divider()])
        result = generate(ast)
        assert '---' in result

    def test_generate_task_list(self):
        ast = Document(children=[MdList(ordered=False, items=[
            ListItem(checked=True, children=[InlineText(text='done')]),
            ListItem(checked=False, children=[InlineText(text='todo')]),
        ])])
        result = generate(ast)
        assert '[x]' in result
        assert '[ ]' in result

    def test_generate_bold_italic_combined(self):
        ast = Document(children=[Paragraph(
            children=[InlineText(text='bi', bold=True, italic=True)]
        )])
        result = generate(ast)
        assert '***bi***' in result

    def test_generate_empty_document(self):
        ast = Document(children=[])
        result = generate(ast)
        assert result == ''

    def test_roundtrip(self):
        """测试 parse → generate 往返"""
        original = '# Hello\n\nThis is **bold** text.\n\n- Item 1\n- Item 2'
        ast = parse(original)
        generated = generate(ast)
        # 重新解析生成的文本应得到相同结构
        ast2 = parse(generated)
        assert len(ast.children) == len(ast2.children)


class TestGenerateToFile:
    """文件生成测试"""

    def test_generate_to_file(self):
        ast = Document(children=[Heading(level=1, children=[InlineText(text='Title')])])
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            filepath = f.name
        try:
            result = generate_to_file(ast, filepath)
            assert result == filepath
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            assert '# Title' in content
        finally:
            os.unlink(filepath)
