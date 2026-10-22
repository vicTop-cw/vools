"""
vools.md.rich.renderer — 富内容渲染器（BRIDGES_MD_RICH_CONTENT_PLAN P1）

将 RichDoc 中的富内容渲染为 HTML 片段，并扩展 to_html() 支持图片渲染。

核心功能：
- render_image(): 图片引用 → <img> HTML
- render_svg(): SVG → 内联 HTML（含净化开关）
- render_html(): HTML 代码块 → 内联 HTML
- render_rich_doc(): 整个 RichDoc → HTML 片段
- render_with_rich(): 扩展 to_html()，在正文中内联富内容
"""

from ..parser import parse
from ..html import _escape
from .scanner import scan_rich
from .sanitizer import sanitize_svg, SVGSanitizerError
from typing import Optional, Dict, Any
import re

__all__ = [
    'render_image', 'render_svg', 'render_html',
    'render_rich_doc', 'render_with_rich',
]


# 图片 URL 类型分类
_IMAGE_URL_RE = re.compile(r'^(data:|https?://|file://|/)')


def render_image(source: str, alt: str = '',
                 directive: Optional[Dict[str, Any]] = None) -> str:
    """渲染图片引用为 <img> HTML。

    Args:
        source: 图片 URL 或路径
        alt: 替代文本
        directive: #!rich 指令（控制 allow-local/allow-remote）

    Returns:
        <img> HTML 字符串；不允许时返回空串
    """
    dir = directive or {}
    allow_local = dir.get('allow-local', True)
    allow_remote = dir.get('allow-remote', False)

    # 分类 URL
    if source.startswith('data:'):
        url_type = 'data'
    elif source.startswith(('http://', 'https://')):
        url_type = 'remote'
    elif source.startswith('file://'):
        url_type = 'local'
    elif source.startswith('/'):
        url_type = 'local'
    else:
        url_type = 'local'

    # 按指令过滤
    if url_type == 'remote' and not allow_remote:
        return ''
    if url_type == 'local' and not allow_local:
        return ''

    # 大小限制（仅对本地文件）
    max_size = int(dir.get('max-inline-size', 1048576))
    if url_type == 'local' and not source.startswith('data:'):
        # 本地文件路径不在此渲染层检查大小（由宿主环境决定）
        pass

    return f'<img src="{_escape(source)}" alt="{_escape(alt)}" />'


def render_svg(svg_content: str,
               directive: Optional[Dict[str, Any]] = None) -> str:
    """渲染 SVG 为内联 HTML。

    Args:
        svg_content: SVG 原文
        directive: #!rich 指令（控制 svg-sanitize）

    Returns:
        SVG HTML 字符串；净化失败时返回空串
    """
    dir = directive or {}
    sanitize = dir.get('svg-sanitize', True)

    if sanitize:
        try:
            svg_content = sanitize_svg(svg_content)
        except SVGSanitizerError:
            return ''

    return svg_content


def render_html(html_content: str, language: str = '',
                directive: Optional[Dict[str, Any]] = None) -> str:
    """渲染 HTML 代码块为内联 HTML。

    Args:
        html_content: HTML 原文
        language: 代码块语言标记
        directive: #!rich 指令

    Returns:
        HTML 字符串
    """
    return html_content


def render_rich_doc(doc) -> str:
    """将整个 RichDoc 渲染为 HTML 片段。

    Args:
        doc: RichDoc 实例（来自 scan_rich）

    Returns:
        HTML 片段字符串
    """
    parts = []
    for c in doc.contents:
        if c.kind == 'image':
            html = render_image(c.source, c.alt, c.directive)
            if html:
                parts.append(html)
        elif c.kind == 'svg':
            html = render_svg(c.source, c.directive)
            if html:
                parts.append(html)
        elif c.kind == 'html':
            html = render_html(c.source, c.language, c.directive)
            if html:
                parts.append(html)
    return '\n'.join(parts)


def render_with_rich(markdown_text: str,
                     directive: Optional[Dict[str, Any]] = None) -> str:
    """扩展 to_html()，在正文中内联富内容。

    流程：
    1. scan_rich() 提取富内容
    2. to_html() 渲染正文
    3. 在正文中插入富内容 HTML

    Args:
        markdown_text: Markdown 原文
        directive: 可选的 #!rich 指令覆盖

    Returns:
        含富内容的完整 HTML
    """
    doc = scan_rich(markdown_text)
    if directive:
        merged = {**doc.directive, **directive}
        doc.directive = merged
        # 同步更新每条内容的 directive（render_image 等用 c.directive）
        for c in doc.contents:
            c.directive = merged

    # 渲染正文
    body_html = _escape(doc.body)

    # 渲染富内容
    rich_html = render_rich_doc(doc)

    # 合并：富内容在前，正文在后
    if rich_html and body_html:
        return f'<div class="rich-content">\n{rich_html}\n</div>\n{body_html}'
    elif rich_html:
        return f'<div class="rich-content">\n{rich_html}\n</div>'
    else:
        return body_html
