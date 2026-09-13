"""vools.md 测试套件"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from vools.md import (
    parse, generate, to_html, extract_metadata, generate_toc,
    extract_code_blocks, strip_markdown, find_headings, count_words,
)
from vools.md.parser import (
    Document, Heading, Paragraph, CodeBlock, BlockQuote,
    MdList, ListItem, Divider, InlineText, parse_to_dict,
)


def test_heading():
    doc = parse("# Hello\n\nWorld")
    assert len(doc.children) == 2
    assert isinstance(doc.children[0], Heading)
    assert doc.children[0].level == 1
    assert isinstance(doc.children[1], Paragraph)
    assert doc.children[1].children[0].text == "World"


def test_code_block():
    md = "```python\nprint(1)\n```"
    doc = parse(md)
    assert isinstance(doc.children[0], CodeBlock)
    assert doc.children[0].language == "python"
    assert doc.children[0].code == "print(1)"


def test_list():
    doc = parse("- item1\n- item2\n- item3")
    assert isinstance(doc.children[0], MdList)
    assert len(doc.children[0].items) == 3
    assert doc.children[0].ordered == False


def test_ordered_list():
    doc = parse("1. first\n2. second\n3. third")
    assert isinstance(doc.children[0], MdList)
    assert doc.children[0].ordered == True
    assert len(doc.children[0].items) == 3


def test_task_list():
    doc = parse("- [x] done\n- [ ] todo")
    assert isinstance(doc.children[0], MdList)
    assert doc.children[0].items[0].checked == True
    assert doc.children[0].items[1].checked == False


def test_blockquote():
    doc = parse("> quoted text")
    assert isinstance(doc.children[0], BlockQuote)


def test_divider():
    doc = parse("---")
    assert isinstance(doc.children[0], Divider)


def test_inline_bold():
    doc = parse("**bold** text")
    para = doc.children[0]
    assert para.children[0].bold
    assert para.children[0].text == "bold"


def test_inline_italic():
    doc = parse("*italic* text")
    para = doc.children[0]
    assert para.children[0].italic
    assert para.children[0].text == "italic"


def test_inline_code():
    doc = parse("`code` text")
    para = doc.children[0]
    assert para.children[0].code
    assert para.children[0].text == "code"


def test_inline_link():
    doc = parse("[link](https://example.com)")
    para = doc.children[0]
    assert para.children[0].link == "https://example.com"
    assert para.children[0].text == "link"


def test_inline_strikethrough():
    doc = parse("~~deleted~~ text")
    para = doc.children[0]
    assert para.children[0].strikethrough
    assert para.children[0].text == "deleted"


def test_generator():
    ast = parse("# Hello\n\nWorld")
    md = generate(ast)
    assert "# Hello" in md
    assert "World" in md


def test_html():
    html = to_html("# Hello")
    assert "<h1>Hello</h1>" in html


def test_html_code_block():
    md = "```python\nprint('hi')\n```"
    html = to_html(md)
    assert "<pre>" in html
    assert "<code" in html
    assert "python" in html


def test_html_list():
    html = to_html("- a\n- b")
    assert "<ul>" in html
    assert "<li>" in html


def test_metadata():
    md = "---\ntitle: Test\ndate: 2024-01-01\n---\n# Body"
    meta = extract_metadata(md)
    assert meta["title"] == "Test"
    assert meta["date"] == "2024-01-01"


def test_metadata_empty():
    meta = extract_metadata("# No front matter")
    assert meta == {}


def test_toc():
    toc = generate_toc("# Title\n## Sub1\n### Sub2")
    assert len(toc) == 3
    assert toc[0]["level"] == 1
    assert toc[1]["level"] == 2
    assert toc[2]["level"] == 3


def test_toc_markdown():
    md = "# Title\n## Sub"
    toc_md = __import__("vools.md", fromlist=["generate_toc_markdown"]).generate_toc_markdown(md)
    assert "目录" in toc_md
    assert "Title" in toc_md
    assert "Sub" in toc_md


def test_code_blocks_extract():
    md = "```python\nprint(1)\n```\n\n```js\nconsole.log(1)\n```"
    blocks = extract_code_blocks(md)
    assert len(blocks) == 2
    assert blocks[0]["language"] == "python"
    assert blocks[1]["language"] == "js"


def test_code_blocks_filter():
    md = "```python\nprint(1)\n```\n\n```js\nconsole.log(1)\n```"
    blocks = extract_code_blocks(md, language="python")
    assert len(blocks) == 1
    assert blocks[0]["language"] == "python"


def test_strip_markdown():
    text = strip_markdown("# **Bold** Title\n\nSome *italic* text")
    assert "Bold" in text
    assert "Title" in text


def test_find_headings():
    headings = find_headings("# H1\n## H2\n### H3")
    assert len(headings) == 3
    assert headings[0]["level"] == 1
    assert headings[1]["level"] == 2


def test_count_words():
    count = count_words("Hello world\n\nThis is a test")
    assert count >= 5


def test_parse_to_dict():
    result = parse_to_dict("# Hello")
    assert isinstance(result, dict)
    assert result["type"] == "document"


def test_complex_document():
    md = """# Title

Some **bold** and *italic* text.

```python
print("hello")
```

- item 1
- item 2

> quote

---

End."""
    doc = parse(md)
    assert len(doc.children) >= 7
    # Check heading
    assert isinstance(doc.children[0], Heading)
    assert doc.children[0].level == 1
    # Check code block
    assert isinstance(doc.children[2], CodeBlock)
    # Check list
    assert isinstance(doc.children[3], MdList)
    # Check blockquote
    assert isinstance(doc.children[4], BlockQuote)
    # Check divider
    assert isinstance(doc.children[5], Divider)


def test_round_trip():
    md = "# Hello\n\nThis is **bold** text."
    ast = parse(md)
    generated = generate(ast)
    # Should contain the key elements
    assert "# Hello" in generated
    assert "bold" in generated
