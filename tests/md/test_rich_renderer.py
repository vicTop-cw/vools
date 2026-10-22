"""
vools.md.rich.renderer 富内容渲染测试（BRIDGES_MD_RICH_CONTENT_PLAN P1）

测试范围：
- 图片渲染（本地/远程/data URI）
- SVG 渲染与净化
- HTML 代码块渲染
- RichDoc 整体渲染
- render_with_rich 扩展 to_html
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from vools.md.rich import (
    render_image, render_svg, render_html,
    render_rich_doc, render_with_rich,
)
from vools.md.rich import scan_rich


class TestRenderImage:
    """图片渲染"""

    def test_local_image(self):
        html = render_image("image.png", "alt text")
        assert "<img" in html
        assert "image.png" in html
        assert "alt text" in html

    def test_remote_blocked_by_default(self):
        html = render_image("https://example.com/img.png", "x")
        assert html == ""

    def test_remote_allowed(self):
        html = render_image("https://example.com/img.png", "x",
                            {'allow-remote': True})
        assert "<img" in html

    def test_data_uri(self):
        html = render_image("data:image/png;base64,abc", "x")
        assert "<img" in html
        assert "data:" in html

    def test_local_blocked(self):
        html = render_image("local.png", "x", {'allow-local': False})
        assert html == ""

    def test_html_escape(self):
        html = render_image('"><script>', "x")
        assert "&lt;" in html or "&quot;" in html


class TestRenderSvg:
    """SVG 渲染与净化"""

    def test_basic_svg(self):
        svg = "<svg><circle/></svg>"
        html = render_svg(svg, {'svg-sanitize': False})
        assert html == svg

    def test_sanitize_removes_script(self):
        svg = "<svg><script>alert(1)</script></svg>"
        clean = render_svg(svg, {'svg-sanitize': True})
        assert "script" not in clean

    def test_sanitize_removes_event(self):
        svg = '<svg onclick="alert(1)"><rect/></svg>'
        clean = render_svg(svg, {'svg-sanitize': True})
        assert "onclick" not in clean

    def test_sanitize_removes_external_ref(self):
        svg = '<svg><image href="https://x.com/img.png"/></svg>'
        clean = render_svg(svg, {'svg-sanitize': True})
        assert "https://x.com" not in clean

    def test_no_sanitize(self):
        svg = "<svg onclick='x'><script>y</script></svg>"
        html = render_svg(svg, {'svg-sanitize': False})
        assert html == svg


class TestRenderHtml:
    """HTML 代码块渲染"""

    def test_basic_html(self):
        html = render_html("<div>hi</div>")
        assert html == "<div>hi</div>"

    def test_html_with_language(self):
        html = render_html("<b>x</b>", "html")
        assert html == "<b>x</b>"


class TestRenderRichDoc:
    """RichDoc 整体渲染"""

    def test_image_only(self):
        doc = scan_rich("![img](a.png)\n")
        html = render_rich_doc(doc)
        assert "<img" in html

    def test_svg_only(self):
        doc = scan_rich("<svg><circle/></svg>\n")
        html = render_rich_doc(doc)
        assert "<svg" in html

    def test_mixed(self):
        doc = scan_rich("![img](a.png)\n\n<svg><circle/></svg>\n")
        html = render_rich_doc(doc)
        assert "<img" in html
        assert "<svg" in html

    def test_empty_doc(self):
        doc = scan_rich("# Title\n")
        html = render_rich_doc(doc)
        assert html == ""


class TestRenderWithRich:
    """render_with_rich 扩展 to_html"""

    def test_image_inline(self):
        full = render_with_rich("![img](a.png)\n\nHello\n")
        assert "<img" in full
        assert "Hello" in full

    def test_no_rich_content(self):
        full = render_with_rich("# Title\n\nText\n")
        assert "rich-content" not in full
        assert "Title" in full

    def test_directive_override(self):
        full = render_with_rich("![img](https://x.com/a.png)\n",
                                {'allow-remote': True})
        assert "<img" in full

    def test_package_import(self):
        from vools.md import render_with_rich as pkg
        assert pkg is render_with_rich
