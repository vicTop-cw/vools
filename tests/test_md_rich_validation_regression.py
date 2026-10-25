# -*- coding: utf-8 -*-
"""回归测试：md.rich / md.advanced 公共 API 的类型校验（BUG-467）。

修复前四个入口对非预期类型给出 cryptic 错误（或静默）：

    parse_rich_directive(None)      # TypeError: expected string or bytes-like object, got 'NoneType'
    extract_lang_blocks(None)       # AttributeError: 'NoneType' object has no attribute 'split'
    render_rich_doc(None)           # AttributeError: 'NoneType' object has no attribute 'contents'
    generate_reference_table(None)  # TypeError: 'NoneType' object is not iterable

修复后均抛带参数名的 TypeError；合法路径（含正确语法 `#!rich=key=val,…`、
`#!lang` 块、`RichDoc(contents=[...])`）行为不变。
"""

import pytest

import vools.md as md
import vools.md.rich as rich


class TestParseRichDirective:
    def test_none_rejected(self):
        with pytest.raises(TypeError) as ei:
            md.parse_rich_directive(None)
        assert "text" in str(ei.value)

    def test_valid_directive(self):
        assert md.parse_rich_directive("#!rich=allow-remote=true,max=10") == {
            "allow-remote": True, "max": 10}

    def test_no_directive_returns_empty(self):
        assert md.parse_rich_directive("# 普通文档") == {}

    def test_type_inference(self):
        parsed = md.parse_rich_directive("#!rich=a=false,b=42,c=text")
        assert parsed == {"a": False, "b": 42, "c": "text"}


class TestExtractLangBlocks:
    def test_none_rejected(self):
        with pytest.raises(TypeError) as ei:
            md.extract_lang_blocks(None)
        assert "markdown_text" in str(ei.value)

    def test_empty_document(self):
        assert md.extract_lang_blocks("") == []

    def test_plain_fence_is_not_lang_block(self):
        """普通代码围栏不是 #!lang 块（语义区分）。"""
        assert md.extract_lang_blocks("```python\nx = 1\n```\n") == []


class TestRenderRichDoc:
    def test_none_rejected(self):
        with pytest.raises(TypeError) as ei:
            md.render_rich_doc(None)
        assert "doc" in str(ei.value)

    def test_empty_rich_doc(self):
        assert md.render_rich_doc(rich.RichDoc()) == ""

    def test_image_content(self):
        doc = rich.RichDoc(contents=[rich.RichContent(kind="image", source="a.png")])
        assert md.render_rich_doc(doc) == '<img src="a.png" alt="" />'

    def test_unknown_kind_ignored(self):
        doc = rich.RichDoc(contents=[rich.RichContent(kind="unknown", source="x")])
        assert md.render_rich_doc(doc) == ""


class TestGenerateReferenceTable:
    def test_none_rejected(self):
        with pytest.raises(TypeError) as ei:
            md.generate_reference_table(None)
        assert "refs" in str(ei.value)

    def test_empty_list(self):
        table = md.generate_reference_table([])
        assert table.startswith("## References")
        assert "| Text | Reference | Resolved | Target |" in table

    def test_with_references(self):
        doc = "# H1\n\n见 [链接](#h1)\n"
        refs = md.extract_cross_references(doc)
        table = md.generate_reference_table(refs)
        assert "## References" in table
