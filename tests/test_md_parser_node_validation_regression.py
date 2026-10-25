# -*- coding: utf-8 -*-
"""回归测试：Markdown AST 节点构造校验（BUG-469）。

修复前节点是纯 dataclass，**零校验**：

    to_html(Heading(0,  [InlineText('x')]))   # -> '<h0>x</h0>'     非法 HTML
    to_html(Heading(99, [InlineText('x')]))   # -> '<h99>x</h99>'
    generate(Document([Heading(99, …)]))      # -> 一行 99 个 '#'     非法 Markdown
    to_html(Heading(1, None))                 # -> 'NoneType' object is not iterable
    Document(None) / Paragraph(None) / …      # 构造通过，渲染期才炸

修复后 ``Heading.level`` 必须是 1..6 的 int，各节点的 ``children``/``items``
必须是 list/tuple；合法解析/渲染路径完全不变。
"""

import pytest

import vools.md as md
import vools.md.parser as p


def _inline(text="x"):
    return [p.InlineText(text)]


class TestHeadingLevel:
    @pytest.mark.parametrize("bad", [0, -1, 7, 99])
    def test_out_of_range(self, bad):
        with pytest.raises(ValueError) as ei:
            p.Heading(bad, _inline())
        assert "1..6" in str(ei.value)

    @pytest.mark.parametrize("bad", ["1", 1.5, True, None])
    def test_non_int(self, bad):
        with pytest.raises(TypeError) as ei:
            p.Heading(bad, _inline())
        assert "level" in str(ei.value)

    @pytest.mark.parametrize("level", [1, 2, 3, 4, 5, 6])
    def test_valid_levels(self, level):
        assert p.Heading(level, _inline()).level == level

    def test_no_invalid_html(self):
        """修复前 Heading(0) 渲染出 <h0>。"""
        with pytest.raises(ValueError):
            p.Heading(0, _inline())


class TestChildrenValidation:
    @pytest.mark.parametrize("make", [
        lambda: p.Document(None),
        lambda: p.Paragraph(None),
        lambda: p.BlockQuote(None),
        lambda: p.Heading(1, None),
        lambda: p.ListItem(children=None),
        lambda: p.MdList(items=None),
    ])
    def test_none_children_rejected(self, make):
        with pytest.raises(TypeError):
            make()

    def test_valid_children(self):
        assert p.Document([]).children == []
        assert p.Paragraph([p.InlineText("t")]).children
        assert p.MdList(items=[p.ListItem()]).items
        assert p.BlockQuote([p.Paragraph()]).children


class TestValidParseRenderUnchanged:
    def test_parse_and_to_html(self):
        doc = md.parse("# H1\n\n段落\n\n## H2\n\n- a\n- b\n\n> 引用\n\n---\n")
        html = md.to_html(doc)
        for tag in ("<h1>", "<h2>", "<ul>", "<blockquote>", "<hr"):
            assert tag in html

    def test_generate_roundtrip(self):
        doc = md.parse("# A\n\n- x\n")
        assert "# A" in md.generate(doc)

    def test_generate_toc(self):
        toc = md.generate_toc("# A\n\n## B\n")
        assert [t["level"] for t in toc] == [1, 2]

    def test_ast_node_input_to_to_html(self):
        heading = p.Heading(2, [p.InlineText("X")])
        assert md.to_html(heading) == "<h2>X</h2>"
