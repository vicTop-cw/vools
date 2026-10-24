# -*- coding: utf-8 -*-
"""回归测试：check_compliance 的 spec 校验 + rich 渲染助手类型（BUG-466）。

修复前 ``check_compliance(markdown_text, spec=...)`` 的 ``spec`` **完全未使用**：

    check_compliance(doc, spec='nope')        # -> []   ← 未知规范静默"通过"
    check_compliance(doc, spec='commonmark')  # 与 'gfm' 完全一样（没有任何提示）

使用者会误以为切换了规则集。修复后只接受 ``gfm`` / ``commonmark``（大小写与
空白容错），其余抛 ValueError；``markdown_text`` 非字符串抛 TypeError。

同族修复：``render_html(None)`` 原来**原样返回 None**；``render_svg(None)`` /
``render_image(None)`` / ``render_image(alt=None)`` 抛 cryptic AttributeError。
"""

import pytest

import vools.md as md

DOC = "# H1\n\n正文\n\n## H2\n"


class TestComplianceSpecValidation:
    @pytest.mark.parametrize("bad", ["nope", "", "GFM2", 123, None])
    def test_unknown_spec_rejected(self, bad):
        with pytest.raises((ValueError, TypeError)) as ei:
            md.check_compliance(DOC, spec=bad)
        assert "spec" in str(ei.value) or "markdown_text" in str(ei.value)

    def test_non_str_markdown(self):
        with pytest.raises(TypeError) as ei:
            md.check_compliance(None)
        assert "markdown_text" in str(ei.value)

    def test_compliance_score_none(self):
        with pytest.raises(TypeError):
            md.compliance_score(None)

    @pytest.mark.parametrize("spec", ["gfm", "GFM", "commonmark", "CommonMark", " gfm "])
    def test_valid_specs_accepted(self, spec):
        assert isinstance(md.check_compliance(DOC, spec=spec), list)

    def test_default_spec(self):
        assert isinstance(md.check_compliance(DOC), list)
        assert isinstance(md.compliance_score(DOC), float)


class TestRenderHelperValidation:
    def test_render_html_none(self):
        """修复前 render_html(None) 静默返回 None。"""
        with pytest.raises(TypeError) as ei:
            md.render_html(None)
        assert "html_content" in str(ei.value)

    def test_render_svg_none(self):
        with pytest.raises(TypeError) as ei:
            md.render_svg(None)
        assert "svg_content" in str(ei.value)

    def test_render_image_none(self):
        with pytest.raises(TypeError) as ei:
            md.render_image(None)
        assert "source" in str(ei.value)

    def test_render_image_alt_none(self):
        with pytest.raises(TypeError) as ei:
            md.render_image("a.png", alt=None)
        assert "alt" in str(ei.value)


class TestRenderValidPaths:
    def test_render_html(self):
        assert md.render_html("<b>x</b>") == "<b>x</b>"
        assert md.render_html("") == ""

    def test_render_svg_sanitized(self):
        assert md.render_svg("<svg></svg>") == "<svg />"

    def test_render_image(self):
        assert md.render_image("a.png") == '<img src="a.png" alt="" />'
        assert md.render_image("a.png", alt="x") == '<img src="a.png" alt="x" />'

    def test_remote_image_dropped_by_default(self):
        assert md.render_image("http://x/a.png") == ""

    def test_remote_image_allowed_by_directive(self):
        assert md.render_image("http://x/a.png",
                               directive={"allow-remote": True}) == \
            '<img src="http://x/a.png" alt="" />'

    def test_local_image_blocked_by_directive(self):
        assert md.render_image("a.png", directive={"allow-local": False}) == ""
