"""
vools.bridge.md.rich.renderer — 内嵌卡片渲染抽象

计划 §4.2 / §5：卡片是 L1 静态 HTML 的受控容器：
- L1 卡片：标题 + 过滤后正文，无任何脚本；
- L4 源码卡片：转义源码 + 复制/折叠按钮（data 属性驱动，宿主脚本实现交互，
  绝不内联用户 JS —— 不可信动作不可越权提升）。

所有卡片 HTML 均为静态结构，交互动作通过 data-rich-* 属性暴露给宿主
（webview2 注入脚本 / CLI 文本提示），保证用户内容永远无法自提升权限。
"""

import html as _html
from typing import Optional

from ..errors import MDRichRenderError

# ═══════════════════════════════════════════════════════
# 卡片结构常量
# ═══════════════════════════════════════════════════════

_CARD_LEVEL_CLASS = {1: "md-rich-l1", 2: "md-rich-l2", 3: "md-rich-l3", 4: "md-rich-l4"}

#: 卡片最小内嵌样式（随卡片输出，宿主可覆盖）
_CARD_STYLE = (
    "<style>"
    ".md-rich-card{display:block;margin:8px 0;padding:12px 16px;"
    "border:1px solid #d0d7de;border-radius:8px;background:#f6f8fa;"
    "font-family:-apple-system,'Segoe UI',sans-serif;font-size:14px;}"
    ".md-rich-card-head{display:flex;align-items:center;gap:8px;"
    "padding-bottom:8px;margin-bottom:8px;border-bottom:1px solid #d0d7de;}"
    ".md-rich-card-title{font-weight:600;color:#24292f;}"
    ".md-rich-card-tag{font-size:12px;color:#57606a;"
    "background:#eaeef2;padding:1px 8px;border-radius:10px;}"
    ".md-rich-card pre.md-rich-source{max-height:480px;overflow:auto;"
    "background:#24292f;color:#e6edf3;padding:12px;border-radius:6px;"
    "white-space:pre;word-break:normal;}"
    ".md-rich-card code{font-family:'SFMono-Regular',Consolas,monospace;}"
    ".md-rich-card .md-rich-actions{margin-left:auto;display:flex;gap:6px;}"
    ".md-rich-card .md-rich-btn{font-size:12px;padding:3px 10px;"
    "border:1px solid #d0d7de;border-radius:6px;background:#fff;color:#24292f;"
    "cursor:pointer;}"
    "</style>"
)


def escape_html(text: str) -> str:
    """HTML 转义（源码展示用）。"""
    return _html.escape(text, quote=True)


def _safe_attr(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# ═══════════════════════════════════════════════════════
# 卡片渲染
# ═══════════════════════════════════════════════════════


def render_card(
    block_id: str,
    kind: str,
    title: Optional[str],
    body_html: str,
    *,
    level: int = 1,
    meta: Optional[dict] = None,
    include_style: bool = True,
) -> str:
    """渲染 L1-L3 内嵌卡片。

    Args:
        block_id: 来源块标识（data-rich-block 回显）
        kind: 卡片类型（如 "text" / "table" / "html"）
        title: 卡片标题（可空）
        body_html: 已过滤的正文 HTML（调用方需先过 sanitize）
        level: 展示档位（1-3；L4 用 render_source_card）
        meta: 附加元数据（写入 data-rich-meta JSON，宿主只读）
        include_style: 是否内联最小样式

    Returns:
        卡片 HTML 片段（纯静态，无脚本）
    """
    if level not in (1, 2, 3):
        raise MDRichRenderError(
            f"L1-L3 卡片不支持 level={level}",
            code="E_LEVEL_VIOLATION",
        )
    if not isinstance(body_html, str):
        raise MDRichRenderError(
            f"body_html 必须是 str，收到 {type(body_html).__name__}",
            code="E_LEVEL_VIOLATION",
        )

    block_attr = _safe_attr(str(block_id))
    kind_attr = _safe_attr(str(kind))
    level_cls = _CARD_LEVEL_CLASS.get(level, "md-rich-l1")

    meta_attr = ""
    if meta:
        import json

        meta_attr = ' data-rich-meta="' + _safe_attr(json.dumps(meta, ensure_ascii=False)) + '"'

    style_part = _CARD_STYLE if include_style else ""
    title_part = ""
    if title:
        title_part = (
            f'<div class="md-rich-card-head">'
            f'<span class="md-rich-card-title">{escape_html(title)}</span>'
            f'<span class="md-rich-card-tag">{kind_attr}</span>'
            f"</div>"
        )

    return (
        f"{style_part}"
        f'<div class="md-rich-card {level_cls}" '
        f'data-rich-block="{block_attr}" data-rich-kind="{kind_attr}"'
        f"{meta_attr}>"
        f"{title_part}"
        f'<div class="md-rich-card-body">{body_html}</div>'
        f"</div>"
    )


def render_source_card(
    block_id: str,
    language: str,
    source: str,
    *,
    level: int = 4,
    foldable: bool = True,
    include_style: bool = True,
    collapsed: bool = False,
    fold_label: str = "\u70b9\u51fb\u5c55\u5f00",
) -> str:
    """渲染 L4 源码展示卡片（含复制/折叠按钮）。

    按钮仅为静态标记：
    - data-rich-copy：宿主脚本点击后复制 <pre> 文本；
    - data-rich-fold：宿主脚本折叠/展开源码区；
    - data-rich-collapsed：初始是否收起（宿主脚本读取此标记决定初始状态）。
    卡片自身不含任何 <script>，交互由宿主实现（不可信动作不可越权提升）。

    Args:
        block_id: 来源块标识
        language: 源码语言标签
        source: 源码原文（渲染前整体转义）
        level: 固定 4（L4 源码展示档位）
        foldable: 是否输出折叠按钮
        include_style: 是否内联最小样式
        collapsed: 初始是否收起（仅当 foldable=True 时有效）
        fold_label: 折叠按钮文案

    Returns:
        源码卡片 HTML 片段（纯静态）
    """
    if level != 4:
        raise MDRichRenderError(
            f"源码卡片仅支持 level=4，收到 level={level}",
            code="E_LEVEL_VIOLATION",
        )

    block_attr = _safe_attr(str(block_id))
    lang_attr = _safe_attr(str(language))
    escaped = escape_html(source)
    safe_fold_label = _safe_attr(str(fold_label)) if fold_label else ""

    style_part = _CARD_STYLE if include_style else ""

    fold_btn = ""
    source_attr = ""
    if foldable:
        fold_btn = (
            '<button type="button" class="md-rich-btn" '
            'data-rich-fold data-rich-block="' + block_attr + '">'
            + (f'{safe_fold_label}' if safe_fold_label else '折叠')
            + "</button>"
        )
        if collapsed:
            source_attr = ' data-rich-collapsed="true"'

    return (
        f"{style_part}"
        f'<div class="md-rich-card md-rich-l4" '
        f'data-rich-block="{block_attr}" data-rich-kind="source"'
        f'{" data-rich-collapsed=\"true\"" if (foldable and collapsed) else ""}>'
        f'<div class="md-rich-card-head">'
        f'<span class="md-rich-card-title">源码</span>'
        f'<span class="md-rich-card-tag">{lang_attr}</span>'
        f'<span class="md-rich-actions">'
        f'<button type="button" class="md-rich-btn" '
        f'data-rich-copy data-rich-block="{block_attr}">复制</button>'
        f"{fold_btn}"
        f"</span>"
        f"</div>"
        f'<pre class="md-rich-source" data-rich-source="{block_attr}"'
        f'{source_attr}>'
        f"<code>{escaped}</code>"
        f"</pre>"
        f"</div>"
    )


# ═══════════════════════════════════════════════════════
# RichDoc 渲染（计划 §5.2 render()）
# ═══════════════════════════════════════════════════════

from typing import Dict, List as _List

from ...core.compat.dataclass_compat import dataclass, field
from .scanner import FileLink, RichDoc


@dataclass
class RenderResult:
    """render() 产物（计划 §5.2）。"""

    html: str  # 完整富内容文档（<html> 根）
    csp: str = ""  # 建议 CSP（宿主可覆盖）
    links: _List[FileLink] = field(default_factory=list)  # 文件链接（含状态）
    open_requests: _List[FileLink] = field(default_factory=list)  # 需要宿主打开的链接
    inline_count: int = 0  # 内联富内容数（svg+html）
    hot_reload_patch: str = ""  # 由 hotreload 模块生成，宿主执行


def _render_body(doc: RichDoc, hot_reload: str) -> str:
    """组装正文 + 内联富内容。"""
    parts: _List[str] = []
    if doc.body_html:
        parts.append(doc.body_html)

    for svg in doc.inline_svgs:
        if svg.safe:
            parts.append(
                f'<div class="md-rich-svg" data-rich-svg="{svg.index}">{svg.safe}</div>'
            )

    for frag in doc.inline_htmls:
        if not frag.safe:
            continue
        if hot_reload == "l2":
            parts.append(
                f'<section data-rich-l2="frag-{frag.index}" class="md-rich-frag">'
                f"{frag.safe}</section>"
            )
        else:
            parts.append(f'<section class="md-rich-frag">{frag.safe}</section>')

    return "\n".join(parts)


def build_preview_page(inner_html: str, *, frame_id: str = "__md_rich_preview__") -> str:
    """L1 热更新的外层预览页：iframe srcdoc 承载富内容文档。"""
    srcdoc = _safe_attr(inner_html)
    return (
        "<!DOCTYPE html>\n<html>\n<head>\n<meta charset=\"utf-8\">\n"
        "</head>\n<body>\n"
        f'<iframe id="{frame_id}" data-rich-l1 style="width:100%;height:96vh;'
        'border:0;" srcdoc="' + srcdoc + '"></iframe>\n'
        "</body>\n</html>"
    )


def render(
    doc: RichDoc,
    *,
    interactive: bool = False,
    hot_reload: str = "l1",
    frame_id: str = "__md_rich_preview__",
) -> RenderResult:
    """将 RichDoc 渲染为完整 HTML（计划 §5.2）。

    Args:
        doc: scan_rich() 产出的 RichDoc
        interactive: True 时生成预览外层页（L1 iframe），False 生成纯富内容文档
        hot_reload: l1/l2；l2 时受控区域带 data-rich-l2 标记
        frame_id: L1 预览 iframe 的 id

    Returns:
        RenderResult（html/csp/links/open_requests/inline_count）
    """
    from .hotreload import parse_hot_reload_mode
    from .sanitize import build_csp

    mode = parse_hot_reload_mode(hot_reload)
    body = _render_body(doc, mode)
    inline_count = sum(1 for s in doc.inline_svgs if s.safe) + sum(
        1 for h in doc.inline_htmls if h.safe
    )

    allow_remote_images = bool(
        doc.config and doc.config.allow_remote_images
    )
    csp = build_csp(level=1, allow_remote_images=allow_remote_images)

    inner = (
        "<!DOCTYPE html>\n<html>\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        + csp.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")
        + "\n</head>\n<body>\n"
        + body
        + "\n</body>\n</html>"
    )

    if interactive and mode == "l1":
        html = build_preview_page(inner, frame_id=frame_id)
    else:
        html = inner

    return RenderResult(
        html=html,
        csp=csp,
        links=list(doc.file_links),
        open_requests=[l for l in doc.file_links if l.resolved_path],
        inline_count=inline_count,
    )
