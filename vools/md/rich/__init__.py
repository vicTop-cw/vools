"""
vools.md.rich — 富内容包（BRIDGES_MD_RICH_CONTENT_PLAN）

子模块：
- scanner: 富内容扫描（P0）
- renderer: 富内容渲染（P1）
"""

from .scanner import (
    RichDoc, RichContent, scan_rich, parse_rich_directive,
    RICH_DEFAULTS,
)
from .renderer import (
    render_image, render_svg, render_html,
    render_rich_doc, render_with_rich,
)

__all__ = [
    # 扫描器（P0）
    'RichDoc', 'RichContent', 'scan_rich', 'parse_rich_directive',
    'RICH_DEFAULTS',
    # 渲染器（P1）
    'render_image', 'render_svg', 'render_html',
    'render_rich_doc', 'render_with_rich',
]
