"""tests/md/test_parser.py — Markdown 解析器测试"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from vools.md.parser import (
    parse, parse_to_dict,
    Document, Heading, Paragraph, CodeBlock,
    BlockQuote, MdList, ListItem, Divider, InlineText,
)


class TestInlineText:
    """行内文本节点测试"""

    def test_creation(self):
        node = InlineText(text='hello')
        assert node.text == 'hello'
        assert node.bold is False
        assert node.italic is False
        assert node.code is False
        assert node.strikethrough is False
        assert node.link is None

    def test_bold(self):
        node = InlineText(text='bold', bold=True)
        assert node.bold is True

    def test_italic(self):
        node = InlineText(text='italic', italic=True)
        assert node.italic is True

    def test_code(self):
        node = InlineText(text='code', code=True)
        assert node.code is True

    def test_strikethrough(self):
        node = InlineText(text='del', strikethrough=True)
        assert node.strikethrough is True

    def test_link(self):
        node = InlineText(text='link', link='https://example.com')
        assert node.link == 'https://example.com'

    def test_html(self):
        node = InlineText(text='<br>', html='br')
        assert node.html == 'br'

    def test_repr(self):
        node = InlineText(text='test', bold=True)
        r = repr(node)
        assert 'test' in r
        assert 'B' in r


class TestHeading:
    """标题节点测试"""

    def test_creation(self):
        h = Heading(level=1, children=[InlineText(text='Title')])
        assert h.level == 1
        assert len(h.children) == 1

    def test_level_range(self):
        for level in range(1, 7):
            h = Heading(level=level)
            assert h.level == level


class TestParagraph:
    """段落节点测试"""

    def test_creation(self):
        p = Paragraph(children=[InlineText(text='Hello')])
        assert len(p.children) == 1

    def test_empty(self):
        p = Paragraph()
        assert p.children == []


class TestCodeBlock:
    """代码块节点测试"""

    def test_creation(self):
        cb = CodeBlock(code='print(1)', language='python')
        assert cb.code == 'print(1)'
        assert cb.language == 'python'

    def test_no_language(self):
        cb = CodeBlock(code='plain')
        assert cb.language == ''


class TestBlockQuote:
    """引用块节点测试"""

    def test_creation(self):
        bq = BlockQuote(children=[Paragraph(children=[InlineText(text='quoted')])])
        assert len(bq.children) == 1


class TestMdList:
    """列表节点测试"""

    def test_ordered(self):
        lst = MdList(ordered=True)
        assert lst.ordered is True
        assert lst.items == []

    def test_unordered(self):
        lst = MdList(ordered=False)
        assert lst.ordered is False


class TestListItem:
    """列表项节点测试"""

    def test_task_checked(self):
        item = ListItem(checked=True)
        assert item.checked is True

    def test_task_unchecked(self):
        item = ListItem(checked=False)
        assert item.checked is False

    def test_non_task(self):
        item = ListItem(checked=None)
        assert item.checked is None


class TestDivider:
    """分割线节点测试"""

    def test_creation(self):
        d = Divider()
        assert d is not None


class TestDocument:
    """文档根节点测试"""

    def test_creation(self):
        doc = Document(children=[Heading(level=1, children=[])])
        assert len(doc.children) == 1

    def test_empty(self):
        doc = Document()
        assert doc.children == []


class TestParse:
    """解析函数测试"""

    def test_parse_heading(self):
        doc = parse('# Hello World')
        assert len(doc.children) == 1
        assert isinstance(doc.children[0], Heading)
        assert doc.children[0].level == 1

    def test_parse_multiple_headings(self):
        text = '# H1\n\n## H2\n\n### H3'
        doc = parse(text)
        assert len(doc.children) == 3
        assert doc.children[0].level == 1
        assert doc.children[1].level == 2
        assert doc.children[2].level == 3

    def test_parse_paragraph(self):
        doc = parse('Hello world')
        assert len(doc.children) == 1
        assert isinstance(doc.children[0], Paragraph)

    def test_parse_code_block(self):
        text = '```python\nprint("hello")\n```'
        doc = parse(text)
        assert len(doc.children) == 1
        assert isinstance(doc.children[0], CodeBlock)
        assert doc.children[0].language == 'python'
        assert 'print' in doc.children[0].code

    def test_parse_blockquote(self):
        text = '> quoted text'
        doc = parse(text)
        assert len(doc.children) == 1
        assert isinstance(doc.children[0], BlockQuote)

    def test_parse_unordered_list(self):
        text = '- item 1\n- item 2\n- item 3'
        doc = parse(text)
        assert len(doc.children) == 1
        assert isinstance(doc.children[0], MdList)
        assert doc.children[0].ordered is False
        assert len(doc.children[0].items) == 3

    def test_parse_ordered_list(self):
        text = '1. first\n2. second'
        doc = parse(text)
        assert len(doc.children) == 1
        assert isinstance(doc.children[0], MdList)
        assert doc.children[0].ordered is True

    def test_parse_divider(self):
        doc = parse('---')
        assert len(doc.children) == 1
        assert isinstance(doc.children[0], Divider)

    def test_parse_bold_inline(self):
        doc = parse('**bold text**')
        assert len(doc.children) == 1
        para = doc.children[0]
        assert isinstance(para, Paragraph)
        assert any(child.bold for child in para.children)

    def test_parse_italic_inline(self):
        doc = parse('*italic text*')
        para = doc.children[0]
        assert any(child.italic for child in para.children)

    def test_parse_code_inline(self):
        doc = parse('`code here`')
        para = doc.children[0]
        assert any(child.code for child in para.children)

    def test_parse_link_inline(self):
        doc = parse('[link](https://example.com)')
        para = doc.children[0]
        assert any(child.link == 'https://example.com' for child in para.children)

    def test_parse_strikethrough(self):
        doc = parse('~~deleted~~')
        para = doc.children[0]
        assert any(child.strikethrough for child in para.children)

    def test_parse_empty(self):
        doc = parse('')
        assert doc.children == []

    def test_parse_complex_document(self):
        text = """# Title

This is a **bold** paragraph with `code`.

## Section 1

- Item 1
- Item 2

> A quote

```
code block
```
"""
        doc = parse(text)
        assert len(doc.children) >= 5

    def test_parse_to_dict(self):
        result = parse_to_dict('# Hello')
        assert isinstance(result, dict)
