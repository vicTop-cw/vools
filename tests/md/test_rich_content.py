"""
vools.md.rich 富内容扫描测试（BRIDGES_MD_RICH_CONTENT_PLAN P0）

测试范围：
- #!rich 指令解析
- 图片引用提取
- SVG 提取
- HTML 代码块提取
- 混合文档扫描
- 正文去富
- 包级导入
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from vools.md.rich import (
    scan_rich, parse_rich_directive, RichDoc, RichContent,
)
from vools.md import scan_rich as pkg_scan_rich


class TestParseRichDirective:
    """#!rich 指令解析"""

    def test_empty_text_returns_empty(self):
        assert parse_rich_directive("") == {}

    def test_no_directive(self):
        text = "# Title\n\nSome content\n"
        assert parse_rich_directive(text) == {}

    def test_basic_directive(self):
        text = "#!rich=allow-local=true,allow-remote=false\n"
        d = parse_rich_directive(text)
        assert d['allow-local'] is True
        assert d['allow-remote'] is False

    def test_numeric_value(self):
        text = "#!rich=max-inline-size=2048\n"
        d = parse_rich_directive(text)
        assert d['max-inline-size'] == 2048

    def test_string_value(self):
        text = "#!rich=hot-reload=l2\n"
        d = parse_rich_directive(text)
        assert d['hot-reload'] == 'l2'

    def test_directive_mid_document(self):
        text = "# Title\n\n#!rich=allow-remote=true\n\nContent\n"
        d = parse_rich_directive(text)
        assert d['allow-remote'] is True


class TestScanRichImages:
    """图片引用提取"""

    def test_simple_image(self):
        doc = scan_rich("![alt](image.png)\n")
        assert len(doc.contents) == 1
        c = doc.contents[0]
        assert c.kind == 'image'
        assert c.source == 'image.png'
        assert c.alt == 'alt'

    def test_image_with_data_uri(self):
        doc = scan_rich("![x](data:image/png;base64,abc123)\n")
        assert len(doc.contents) == 1
        assert doc.contents[0].source.startswith('data:')

    def test_image_no_alt(self):
        doc = scan_rich("![](image.png)\n")
        assert len(doc.contents) == 1
        assert doc.contents[0].alt == ''


class TestScanRichSvg:
    """SVG 提取"""

    def test_simple_svg(self):
        doc = scan_rich('<svg width="100"><rect/></svg>\n')
        assert len(doc.contents) == 1
        assert doc.contents[0].kind == 'svg'

    def test_svg_with_namespace(self):
        doc = scan_rich('<svg xmlns="http://www.w3.org/2000/svg"><circle/></svg>\n')
        assert len(doc.contents) == 1
        assert 'svg' in doc.contents[0].source


class TestScanRichHtml:
    """HTML 代码块提取"""

    def test_html_block(self):
        doc = scan_rich("```html\n<div>hi</div>\n```\n")
        assert len(doc.contents) == 1
        assert doc.contents[0].kind == 'html'
        assert doc.contents[0].language == 'html'

    def test_webview2_block(self):
        doc = scan_rich("```webview2\n<button>x</button>\n```\n")
        assert len(doc.contents) == 1
        assert doc.contents[0].language == 'webview2'


class TestScanRichMixed:
    """混合文档"""

    def test_mixed_contents(self):
        text = (
            "#!rich=allow-remote=true\n\n"
            "![img](a.png)\n\n"
            "<svg></svg>\n\n"
            "```html\n<b>x</b>\n```\n"
        )
        doc = scan_rich(text)
        assert len(doc.contents) == 3
        assert doc.directive['allow-remote'] is True
        kinds = {c.kind for c in doc.contents}
        assert kinds == {'image', 'svg', 'html'}

    def test_body_strips_rich(self):
        text = "![img](a.png)\n\n<svg></svg>\n"
        doc = scan_rich(text)
        assert '![img]' not in doc.body
        assert '<svg>' not in doc.body

    def test_body_preserves_plain_text(self):
        text = "![img](a.png)\n\nSome plain text\n"
        doc = scan_rich(text)
        assert 'Some plain text' in doc.body


class TestRichDocStructure:
    """RichDoc 数据结构"""

    def test_len_and_bool(self):
        assert len(scan_rich("")) == 0
        assert not scan_rich("")
        assert len(scan_rich("![x](a.png)\n")) == 1
        assert scan_rich("![x](a.png)\n")

    def test_by_kind(self):
        text = "![img](a.png)\n\n<svg></svg>\n"
        doc = scan_rich(text)
        assert len(doc.by_kind('image')) == 1
        assert len(doc.by_kind('svg')) == 1
        assert len(doc.by_kind('html')) == 0

    def test_to_dict(self):
        doc = scan_rich("![x](a.png)\n")
        d = doc.to_dict()
        assert 'contents' in d
        assert 'directive' in d
        assert 'body' in d
        assert len(d['contents']) == 1

    def test_defaults_merged(self):
        doc = scan_rich("# Title\n")
        assert doc.directive['allow-local'] is True
        assert doc.directive['svg-sanitize'] is True
        assert doc.directive['hot-reload'] == 'l2'


class TestPackageImport:
    """包级导入"""

    def test_package_import(self):
        assert pkg_scan_rich is scan_rich

    def test_rich_doc_importable(self):
        from vools.md import RichDoc, RichContent
        assert RichDoc is not None
        assert RichContent is not None
