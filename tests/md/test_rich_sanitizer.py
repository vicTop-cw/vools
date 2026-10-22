"""
vools.md.rich.sanitizer SVG 净化测试（BRIDGES_MD_RICH_CONTENT_PLAN P2）

安全测试：
- 白名单元素通过
- 黑名单元素移除（script/foreignObject/animate 等）
- on* 事件移除
- javascript:/data: href 移除
- 命名空间处理
- style 属性净化
- 非法 SVG 抛异常
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from vools.md.rich.sanitizer import sanitize_svg, SVGSanitizerError


class TestSanitizerBasics:
    """基本净化"""

    def test_simple_svg(self):
        svg = "<svg width=\"100\" height=\"100\"><circle cx=\"50\" cy=\"50\" r=\"40\"/></svg>"
        clean = sanitize_svg(svg)
        assert "circle" in clean

    def test_nested_group(self):
        svg = "<svg><g><circle/><rect/></g></svg>"
        clean = sanitize_svg(svg)
        assert "circle" in clean
        assert "rect" in clean

    def test_path_element(self):
        svg = "<svg><path d=\"M0 0L10 10\" stroke=\"red\" stroke-width=\"2\"/></svg>"
        clean = sanitize_svg(svg)
        assert "path" in clean


class TestSanitizerBlacklist:
    """黑名单移除"""

    def test_script_removed(self):
        svg = "<svg><script>alert(1)</script><circle/></svg>"
        clean = sanitize_svg(svg)
        assert "script" not in clean
        assert "circle" in clean

    def test_foreignObject_removed(self):
        svg = "<svg><foreignObject><div>x</div></foreignObject><circle/></svg>"
        clean = sanitize_svg(svg)
        assert "foreignObject" not in clean

    def test_animate_removed(self):
        svg = "<svg><animate attributeName=\"x\" to=\"10\"/><circle/></svg>"
        clean = sanitize_svg(svg)
        assert "animate" not in clean

    def test_unknown_element_removed(self):
        svg = "<svg><not-a-real-tag/><circle/></svg>"
        clean = sanitize_svg(svg)
        assert "not-a-real-tag" not in clean


class TestSanitizerEvents:
    """事件属性移除"""

    def test_onclick_removed(self):
        svg = "<svg onclick=\"alert(1)\"><circle/></svg>"
        clean = sanitize_svg(svg)
        assert "onclick" not in clean

    def test_onload_removed(self):
        svg = "<svg onload=\"alert(1)\"><circle/></svg>"
        clean = sanitize_svg(svg)
        assert "onload" not in clean

    def test_onmouseover_removed(self):
        svg = '<svg><circle onmouseover="alert(1)"/></svg>'
        clean = sanitize_svg(svg)
        assert "onmouseover" not in clean


class TestSanitizerUrls:
    """URL 安全"""

    def test_javascript_href_removed(self):
        svg = "<svg><a href=\"javascript:alert(1)\"><circle/></a></svg>"
        clean = sanitize_svg(svg)
        assert "javascript:" not in clean

    def test_data_html_href_removed(self):
        svg = '<svg><image href="data:text/html;base64,PHNjcmlwdD4"/></svg>'
        clean = sanitize_svg(svg)
        assert "data:text/html" not in clean

    def test_safe_href_kept(self):
        svg = '<svg><use href="#icon"/></svg>'
        clean = sanitize_svg(svg)
        assert "#icon" in clean


class TestSanitizerNamespace:
    """命名空间"""

    def test_namespace_svg(self):
        svg = '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></svg>'
        clean = sanitize_svg(svg)
        assert "path" in clean

    def test_namespace_nested(self):
        svg = '<svg xmlns="http://www.w3.org/2000/svg"><g><circle/></g></svg>'
        clean = sanitize_svg(svg)
        assert "circle" in clean


class TestSanitizerStyle:
    """style 属性"""

    def test_style_kept(self):
        svg = '<svg><circle style="fill: red; stroke: blue"/></svg>'
        clean = sanitize_svg(svg)
        assert "fill" in clean

    def test_style_position_removed(self):
        svg = '<svg><circle style="position: fixed; fill: red"/></svg>'
        clean = sanitize_svg(svg)
        assert "position" not in clean
        assert "fill" in clean

    def test_style_expression_removed(self):
        svg = '<svg><circle style="width: expression(alert(1))"/></svg>'
        clean = sanitize_svg(svg)
        assert "expression(" not in clean


class TestSanitizerErrors:
    """错误处理"""

    def test_invalid_xml(self):
        try:
            sanitize_svg("<svg><circle")
            assert False, "应该抛异常"
        except SVGSanitizerError:
            pass

    def test_root_forbidden(self):
        # script 作为根元素（虽然不太可能，但测试边界）
        try:
            sanitize_svg("<script>alert(1)</script>")
            assert False, "应该抛异常"
        except SVGSanitizerError:
            pass


class TestSanitizerRenderIntegration:
    """与 renderer 集成"""

    def test_render_svg_with_sanitize(self):
        from vools.md.rich import render_svg
        svg = "<svg onclick=\"x\"><script>y</script><circle/></svg>"
        rendered = render_svg(svg, {'svg-sanitize': True})
        assert "script" not in rendered
        assert "onclick" not in rendered
        assert "circle" in rendered

    def test_render_svg_without_sanitize(self):
        from vools.md.rich import render_svg
        svg = "<svg onclick=\"x\"><circle/></svg>"
        rendered = render_svg(svg, {'svg-sanitize': False})
        assert "onclick" in rendered
