"""
vools.md.rich.sanitizer — SVG 净化器（BRIDGES_MD_RICH_CONTENT_PLAN P2）

基于白名单 + 黑名单双重策略，使用 xml.etree.ElementTree 解析。

白名单：仅允许安全 SVG 元素/属性
黑名单：禁止 script/foreignObject/on*/javascript: href 等
"""

import re
import xml.etree.ElementTree as ET
from typing import Optional, Set, Dict

__all__ = ['sanitize_svg', 'SVGSanitizerError']


class SVGSanitizerError(Exception):
    """SVG 净化错误"""


# ─── 白名单 ───

# 允许的 SVG 元素
ALLOWED_SVG_ELEMENTS: Set[str] = frozenset({
    'svg', 'g', 'path', 'rect', 'circle', 'ellipse', 'line',
    'polyline', 'polygon', 'text', 'tspan', 'title', 'desc',
    'defs', 'linearGradient', 'radialGradient', 'stop',
    'clipPath', 'mask', 'pattern', 'use', 'symbol', 'marker',
    'filter', 'feGaussianBlur', 'feOffset', 'feMerge',
    'feColorMatrix', 'feBlend', 'feComposite', 'image',
    'style', 'metadata', 'switch',
})

# 允许的全局属性（所有元素可用）
ALLOWED_GLOBAL_ATTRS: Set[str] = frozenset({
    'id', 'class', 'style', 'transform', 'opacity',
    'fill', 'fill-opacity', 'fill-rule', 'stroke', 'stroke-width',
    'stroke-linecap', 'stroke-linejoin', 'stroke-dasharray',
    'stroke-dashoffset', 'stroke-opacity', 'visibility',
    'display', 'overflow', 'clip-path', 'mask',
})

# 允许的本地属性（按元素分类）
ALLOWED_LOCAL_ATTRS: Dict[str, Set[str]] = {
    'svg': frozenset({'xmlns', 'width', 'height', 'viewBox', 'preserveAspectRatio',
                       'version', 'x', 'y', 'cx', 'cy', 'r', 'rx', 'ry',
                       'x1', 'y1', 'x2', 'y2', 'points',
                       'd', 'cx', 'cy', 'r', 'fx', 'fy', 'fr',
                       'offset', 'stop-color', 'stop-opacity',
                       'href', 'xlink:href', 'x', 'y',
                       'gradientUnits', 'gradientTransform',
                       'spreadMethod', 'cx', 'cy', 'r', 'fx', 'fy',
                       'width', 'height', 'patternUnits', 'patternTransform',
                       'refX', 'refY', 'markerWidth', 'markerHeight',
                       'markerUnits', 'orient',
                       'color', 'stdDeviation', 'dx', 'dy',
                       'in', 'in2', 'result', 'mode', 'k1', 'k2', 'k3', 'k4',
                       'x', 'y', 'width', 'height', 'xlink:href',
                       'font-family', 'font-size', 'font-style', 'font-weight',
                       'text-anchor', 'text-decoration', 'dominant-baseline',
                       'x', 'y', 'dx', 'dy', 'rotate', 'textLength', 'lengthAdjust'}),
    'text': frozenset({'font-family', 'font-size', 'font-style', 'font-weight',
                        'text-anchor', 'text-decoration', 'dominant-baseline'}),
    'tspan': frozenset({'x', 'y', 'dx', 'dy', 'rotate', 'textLength', 'lengthAdjust'}),
    'image': frozenset({'href', 'xlink:href', 'width', 'height'}),
    'use': frozenset({'href', 'xlink:href', 'x', 'y', 'width', 'height'}),
    'stop': frozenset({'offset', 'stop-color', 'stop-opacity'}),
    'feGaussianBlur': frozenset({'stdDeviation', 'in', 'result'}),
    'feOffset': frozenset({'dx', 'dy', 'in', 'result'}),
    'feMerge': frozenset({'in', 'in2', 'result'}),
    'feColorMatrix': frozenset({'in', 'type', 'values', 'result'}),
    'feBlend': frozenset({'in', 'in2', 'mode', 'result'}),
    'feComposite': frozenset({'in', 'in2', 'operator', 'k1', 'k2', 'k3', 'k4', 'result'}),
    'linearGradient': frozenset({'x1', 'y1', 'x2', 'y2', 'gradientUnits',
                                  'gradientTransform', 'spreadMethod'}),
    'radialGradient': frozenset({'cx', 'cy', 'r', 'fx', 'fy', 'fr',
                                  'gradientUnits', 'gradientTransform', 'spreadMethod'}),
}

# ─── 黑名单 ───

# 禁止的元素
FORBIDDEN_ELEMENTS: Set[str] = frozenset({
    'script', 'foreignObject', 'set', 'animate', 'animateTransform',
    'animateMotion', 'discard', 'handler',
})

# 禁止的属性前缀（on* 事件）
FORBIDDEN_ATTR_PREFIXES = ('on',)

# 禁止的 URL scheme（href/xlink:href 中的外部引用）
FORBIDDEN_URL_SCHEMES = frozenset({
    'javascript:', 'data:text/html', 'data:application/javascript',
    'vbscript:', 'file:',
})


def _is_attr_allowed(tag: str, attr: str) -> bool:
    """检查属性是否允许。"""
    # on* 事件一律禁止
    if any(attr.startswith(p) for p in FORBIDDEN_ATTR_PREFIXES):
        return False
    # 全局属性
    if attr in ALLOWED_GLOBAL_ATTRS:
        return True
    # 本地属性
    local = ALLOWED_LOCAL_ATTRS.get(tag, frozenset())
    if attr in local:
        return True
    # xmlns 相关
    if attr.startswith('xmlns'):
        return True
    return False


def _is_url_safe(url: str) -> bool:
    """检查 URL 是否安全（无 javascript:/data:text/html/外部 URL 等）。"""
    url_lower = url.strip().lower()
    # 禁止的 scheme
    for scheme in FORBIDDEN_URL_SCHEMES:
        if url_lower.startswith(scheme):
            return False
    # 外部 URL（http/https）在 href/xlink:href 中一律禁止
    if url_lower.startswith(('http://', 'https://')):
        return False
    return True


def _sanitize_element(elem: ET.Element) -> Optional[ET.Element]:
    """净化单个元素（递归）。

    Returns:
        净化后的元素；如果元素本身被禁止则返回 None
    """
    tag = elem.tag
    # 去除命名空间（ET 使用 {ns}localname 格式）
    if tag.startswith('{'):
        tag = tag.split('}', 1)[1]
        elem.tag = tag
    elif ':' in tag:
        tag = tag.split(':', 1)[1]
        elem.tag = tag

    # 禁止元素
    if tag in FORBIDDEN_ELEMENTS:
        return None

    # 白名单检查
    if tag not in ALLOWED_SVG_ELEMENTS:
        return None

    # 净化属性
    for attr_name in list(elem.attrib.keys()):
        # 属性名也可能带命名空间
        clean_attr = attr_name
        if clean_attr.startswith('{'):
            clean_attr = clean_attr.split('}', 1)[1]
        elif ':' in clean_attr:
            clean_attr = clean_attr.split(':', 1)[1]

        if not _is_attr_allowed(tag, clean_attr):
            del elem.attrib[attr_name]
            continue
        # URL 属性安全检查
        attr_lower = clean_attr.lower()
        if attr_lower in ('href', 'xlink:href', 'src', 'action', 'formaction'):
            if not _is_url_safe(elem.attrib[attr_name]):
                del elem.attrib[attr_name]

    # style 属性：仅允许 CSS 属性白名单
    for k in list(elem.attrib.keys()):
        clean_k = k
        if clean_k.startswith('{'):
            clean_k = clean_k.split('}', 1)[1]
        elif ':' in clean_k:
            clean_k = clean_k.split(':', 1)[1]
        if clean_k == 'style':
            elem.attrib[k] = _sanitize_style(elem.attrib[k])

    # 递归净化子元素
    for child in list(elem):
        cleaned = _sanitize_element(child)
        if cleaned is not None:
            elem.append(cleaned)
        else:
            elem.remove(child)

    return elem


def _sanitize_style(style: str) -> str:
    """净化 CSS style 属性。

    仅允许安全的 CSS 属性（颜色、背景、边框等），
    禁止 position:fixed/absolute、z-index、expression() 等。
    """
    # 禁止的 CSS 属性
    forbidden_css = frozenset({
        'position', 'z-index', 'overflow', 'clip', 'clip-path',
        'pointer-events', 'cursor', 'filter', 'transform',
    })
    parts = []
    for decl in style.split(';'):
        decl = decl.strip()
        if not decl:
            continue
        prop = decl.split(':', 1)[0].strip().lower()
        if prop in forbidden_css:
            continue
        # 禁止 expression()
        if 'expression(' in decl.lower():
            continue
        parts.append(decl)
    return '; '.join(parts)


def sanitize_svg(svg_content: str) -> str:
    """净化 SVG 内容。

    Args:
        svg_content: SVG 原文

    Returns:
        净化后的 SVG 字符串

    Raises:
        SVGSanitizerError: SVG 格式无效时
    """
    try:
        # 解析 SVG
        root = ET.fromstring(svg_content)
    except ET.ParseError as e:
        raise SVGSanitizerError(f"SVG 解析失败: {e}") from e

    # 净化根元素
    cleaned = _sanitize_element(root)
    if cleaned is None:
        raise SVGSanitizerError("SVG 根元素被禁止")

    # 序列化回字符串
    return ET.tostring(cleaned, encoding='unicode')
