# -*- coding: utf-8 -*-
"""回归测试：to_html 非法输入 + 导出函数类型校验（BUG-468）。

修复前 ``to_html(None)`` 会一路落到 ``_node_to_html`` 的兜底分支，产出
**静默垃圾 HTML**：

    to_html(None)   # -> '<!-- unknown node: NoneType -->'
    to_html(123)    # -> '<!-- unknown node: int -->'

``render_html_with_theme(None)`` / ``export_html_theme(None, ...)`` 同样把这段
注释写进文档/文件（调用方以为渲染成功）；``markdown_to_docx(None)`` 抛
``'NoneType' object has no attribute 'split'``。

修复后 ``to_html`` 要求 str 或已知 AST 节点，导出函数要求字符串输入；
合法路径（str / AST 节点 / 空文档）行为不变。
"""

import pytest

import vools.md as md


class TestToHtmlValidation:
    @pytest.mark.parametrize("bad", [None, 123, 1.5, ["# H"], {"a": 1}])
    def test_invalid_input_rejected(self, bad):
        with pytest.raises(TypeError) as ei:
            md.to_html(bad)
        assert "source" in str(ei.value)

    def test_no_silent_unknown_node_comment(self):
        """修复前会返回 '<!-- unknown node: NoneType -->'。"""
        with pytest.raises(TypeError):
            md.to_html(None)

    def test_str_input(self):
        html = md.to_html("# H")
        assert "<h1>H</h1>" in html

    def test_ast_input(self):
        html = md.to_html(md.parse("# H"))
        assert "<h1>H</h1>" in html

    def test_empty_string(self):
        assert "markdown-body" in md.to_html("")


class TestExportValidation:
    def test_render_html_with_theme_none(self):
        with pytest.raises(TypeError) as ei:
            md.render_html_with_theme(None)
        assert "markdown_text" in str(ei.value)

    def test_export_html_theme_none(self, tmp_path):
        with pytest.raises(TypeError):
            md.export_html_theme(None, "github", str(tmp_path / "a.html"))

    def test_markdown_to_docx_none(self, tmp_path):
        with pytest.raises(TypeError) as ei:
            md.markdown_to_docx(None, str(tmp_path / "a.docx"))
        assert "markdown_text" in str(ei.value)

    def test_markdown_to_pdf_none(self, tmp_path):
        with pytest.raises(TypeError):
            md.markdown_to_pdf(None, str(tmp_path / "a.pdf"))

    def test_markdown_to_pdf_via_cli_none(self, tmp_path):
        with pytest.raises(TypeError):
            md.markdown_to_pdf_via_cli(None, str(tmp_path / "a.pdf"))


class TestValidExportPaths:
    def test_render_html_with_theme(self):
        html = md.render_html_with_theme("# H")
        assert "<h1>H</h1>" in html
        assert "<!DOCTYPE html>" in html

    def test_export_html_theme_writes_file(self, tmp_path):
        out = tmp_path / "doc.html"
        returned = md.export_html_theme("# H", "github", str(out))
        assert out.exists()
        assert out.read_text(encoding="utf-8")

    @pytest.mark.parametrize("theme", ["github", "gitlab", "stackoverflow", "minimal"])
    def test_all_themes(self, theme):
        assert "<h1>" in md.render_html_with_theme("# H", theme)

    def test_unknown_theme_loud(self):
        with pytest.raises(ValueError):
            md.render_html_with_theme("# H", "nope")
