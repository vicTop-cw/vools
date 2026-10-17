"""
vools.bridge.md.rich.sanitize — HTML 基础过滤（L1 静态）与 CSP 策略表

计划 §5 安全模型（决策 3）：
- L1 静态档：剥离一切可执行 / 可交互越权元素（script、on* 事件、iframe、
  object、embed、form 控件、javascript:/data:text/html 协议），仅保留基础
  排版标签与本地资源引用。
- 远程图片默认禁止 + opt-in（决策 2）：img src 只允许相对路径与 data:image/*；
  http(s) 远程图片默认剥离，仅 allow_remote_images=True 时放行并配套放宽 CSP。
- 不可信动作不可越权提升：sanitize 输出永远不含 <script>、不含 on* 属性、
  不含 javascript:/data:text/html、不含 iframe/object/embed。复制/折叠等
  交互由宿主（webview2 / CLI）通过 data 属性驱动，绝不内联用户 JS。

实现：纯标准库 html.parser 白名单过滤，不引入重型依赖（Apache-2.0 兼容）。
"""


__all__ = [
    "L1Sanitizer",
    "sanitize_html_fragment",
    "build_csp",
    "build_csp_meta",
    "handle_starttag",
    "handle_startendtag",
    "handle_endtag",
    "handle_data",
    "handle_comment",
    "handle_decl",
    "handle_pi",
    "L1_TAGS",
    "VOID_TAGS",
    "COMMON_ATTRS",
    "A_ATTRS",
    "IMG_ATTRS",
    "BANNED_SCHEMES",
    "DANGEROUS_CONTAINERS",
    "SVG_TAGS",
    "SVG_ATTRS",
    "sanitize_svg",
]

import re
from html.parser import HTMLParser
from typing import List, Tuple, Optional

from ..errors import MDRichSanitizeError

# ═══════════════════════════════════════════════════════
# L1 标签 / 属性白名单
# ═══════════════════════════════════════════════════════

L1_TAGS = frozenset(
    {
        # 结构
        "article", "aside", "section", "header", "footer", "nav", "main",
        "div", "span", "br", "hr",
        # 标题与段落
        "h1", "h2", "h3", "h4", "h5", "h6", "p",
        # 列表
        "ul", "ol", "li", "dl", "dt", "dd",
        # 表格
        "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption",
        # 行内语义
        "strong", "em", "b", "i", "u", "s", "small", "mark", "sub", "sup",
        "code", "pre", "blockquote", "q",
        # 链接与图片（属性经协议校验）
        "a", "img",
        # 图片容器
        "figure", "figcaption",
    }
)

#: 自闭合 / 无内容标签（HTMLParser 不回调 handle_data 的原子标签）
VOID_TAGS = frozenset({"br", "hr", "img"})

#: 通用属性白名单（id 额外做字符集校验）
COMMON_ATTRS = frozenset({"title", "class", "id"})

#: a 标签允许属性
A_ATTRS = frozenset({"href", "title", "class", "id", "target"})

#: img 标签允许属性
IMG_ATTRS = frozenset({"src", "alt", "title", "class", "id", "width", "height"})

#: 禁止协议（大小写不敏感；data:text/html 也在禁止列表）
BANNED_SCHEMES = frozenset({"javascript", "vbscript", "data:text/html", "file"})

#: data: 允许的图片前缀
_DATA_IMAGE_PREFIX = "data:image/"

#: id 属性字符集校验
_ID_RE = re.compile(r"^[A-Za-z0-9_:-]+$")

#: 数值属性（width/height）校验
_NUMERIC_ATTR_RE = re.compile(r"^\d+$")


class L1Sanitizer(HTMLParser):
    """L1 静态 HTML 过滤器。

    行为：
    - 标签不在 L1_TAGS 白名单 → 剥离（含全部子内容除外：script/style/iframe/
      object/embed/form 等危险容器直接丢弃子树）
    - on* 事件属性 / style / 非白名单属性 → 剥离
    - a[href] / img[src] 协议非法（javascript: vbscript: data:text/html file:）
      → 剥离该属性；远程图片 http(s) 默认剥离（allow_remote_images=True 时放行）
    - 危险容器标签（script/style/iframe/object/embed/form/input/button/select/
      textarea/meta/link/base）→ 丢弃整棵子树
    """

    DANGEROUS_CONTAINERS = frozenset(
        {"script", "style", "iframe", "object", "embed", "form", "input",
         "button", "select", "textarea", "meta", "link", "base", "template"}
    )

    def __init__(self, allow_remote_images: bool = False):
        super().__init__(convert_charrefs=True)
        self.allow_remote_images = allow_remote_images
        self.parts: List[str] = []
        #: 剥离记录（供测试断言 / 审计日志）
        self.removed: List[str] = []
        self._drop_depth = 0

    # ── 标签处理 ─────────────────────────────────────────

    def handle_starttag(self, tag: str, attrs):
        tag_l = tag.lower()
        if self._drop_depth:
            self._drop_depth += 1
            return
        if tag_l in self.DANGEROUS_CONTAINERS:
            self._drop_depth = 1
            self.removed.append(f"<{tag_l}>")
            return
        if tag_l not in L1_TAGS:
            self.removed.append(f"<{tag_l}>")
            return
        safe_attrs = self._filter_attrs(tag_l, dict(attrs))
        if tag_l in VOID_TAGS:
            self.parts.append(self._format_void(tag_l, safe_attrs))
        else:
            self.parts.append(self._format_start(tag_l, safe_attrs))

    def handle_startendtag(self, tag: str, attrs):
        # XHTML 风格 <br/> 等
        self.handle_starttag(tag, attrs)
        if tag.lower() not in VOID_TAGS and not self._drop_depth:
            self.parts.append(f"</{tag.lower()}>")

    def handle_endtag(self, tag: str):
        tag_l = tag.lower()
        if self._drop_depth:
            self._drop_depth -= 1
            return
        if tag_l in self.DANGEROUS_CONTAINERS:
            return
        if tag_l in L1_TAGS and tag_l not in VOID_TAGS:
            self.parts.append(f"</{tag_l}>")

    def handle_data(self, data: str):
        if not self._drop_depth:
            self.parts.append(data)

    def handle_comment(self, data: str):
        # 注释不输出（避免隐藏内容/条件注释注入）
        self.removed.append("<!--comment-->")

    def handle_decl(self, decl: str):
        self.removed.append(f"<!{decl}>")

    def handle_pi(self, data: str):
        self.removed.append("<?pi?>")

    # ── 属性过滤 ─────────────────────────────────────────

    def _filter_attrs(self, tag: str, attrs: dict) -> List[Tuple[str, str]]:
        if tag == "a":
            allowed = A_ATTRS
        elif tag == "img":
            allowed = IMG_ATTRS
        else:
            allowed = COMMON_ATTRS

        safe: List[Tuple[str, str]] = []
        for key, value in attrs.items():
            key_l = key.lower()
            # 事件属性一律剥离
            if key_l.startswith("on"):
                self.removed.append(f"{tag}[{key_l}]")
                continue
            if key_l == "style":
                # L1 静态：内联样式剥离，避免 CSS url() 远程拉取与视觉钓鱼
                self.removed.append(f"{tag}[style]")
                continue
            if key_l not in allowed:
                self.removed.append(f"{tag}[{key_l}]")
                continue
            if key_l == "id" and value and not _ID_RE.match(value):
                self.removed.append(f"{tag}[id]")
                continue
            if key_l in ("width", "height") and value and not _NUMERIC_ATTR_RE.match(value):
                self.removed.append(f"{tag}[{key_l}]")
                continue
            if key_l in ("href", "src"):
                value = self._sanitize_url(value, is_image=(tag == "img"))
                if value is None:
                    self.removed.append(f"{tag}[{key_l}]")
                    continue
            safe.append((key_l, value))
        return safe

    def _sanitize_url(self, url: str, is_image: bool) -> Optional[str]:
        """协议 / 远程图片策略校验，返回清洗后 URL 或 None（剥离）。"""
        url = url.strip()
        if not url:
            return None

        lower = url.lower()
        # 锚点 / 相对路径：放行
        if lower.startswith("#"):
            return url
        if "://" not in lower and not lower.startswith("//"):
            # 无 scheme 相对路径：剥离 javascript: 写法（如 "javascript:alert(1)" 无 //）
            scheme_match = re.match(r"^([a-zA-Z][a-zA-Z0-9+.-]*):", lower)
            if scheme_match:
                scheme = scheme_match.group(1)
                if scheme in ("javascript", "vbscript"):
                    return None
                if is_image and scheme == "data":
                    if not lower.startswith(_DATA_IMAGE_PREFIX):
                        return None
                    return url
                if not is_image and scheme == "data":
                    # 链接的 data: 一律拒绝（data:text/html 尤甚）
                    return None
                # 未知 scheme（如 mailto:）仅对链接放行
                if is_image:
                    return None
                return url
            return url

        # 带 scheme：解析 scheme
        scheme = lower.split("://", 1)[0]
        if scheme in ("javascript", "vbscript", "file"):
            return None
        if scheme == "data":
            if is_image and lower.startswith(_DATA_IMAGE_PREFIX):
                return url
            return None
        # 远程 http(s)
        if scheme in ("http", "https"):
            if is_image and not self.allow_remote_images:
                return None  # 远程图片默认禁止（决策 2）
            return url
        # 其他 scheme 一律拒绝
        return None

    # ── 格式化输出 ───────────────────────────────────────

    @staticmethod
    def _format_start(tag: str, attrs: List[Tuple[str, str]]) -> str:
        if not attrs:
            return f"<{tag}>"
        return f"<{tag} " + " ".join(f'{k}="{_escape_attr(v)}"' for k, v in attrs) + ">"

    @staticmethod
    def _format_void(tag: str, attrs: List[Tuple[str, str]]) -> str:
        if not attrs:
            return f"<{tag}>"
        return f"<{tag} " + " ".join(f'{k}="{_escape_attr(v)}"' for k, v in attrs) + ">"


def _escape_attr(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# ═══════════════════════════════════════════════════════
# 对外 API
# ═══════════════════════════════════════════════════════


def sanitize_html_fragment(
    html_fragment: str,
    *,
    allow_remote_images: bool = False,
) -> Tuple[str, List[str]]:
    """L1 过滤 HTML 片段，返回 (安全 HTML, 剥离记录)。

    Args:
        html_fragment: 待过滤 HTML（可为完整文档或片段，文档外壳标签会被剥离）
        allow_remote_images: 决策 2 的 opt-in；True 时放行 http(s) 图片

    Returns:
        (safe_html, removed)：removed 为被剥离元素的审计列表
    """
    if not isinstance(html_fragment, str):
        raise MDRichSanitizeError(
            f"HTML 片段必须是 str，收到 {type(html_fragment).__name__}",
            code="E_SANITIZE_BLOCKED",
        )
    sanitizer = L1Sanitizer(allow_remote_images=allow_remote_images)
    try:
        sanitizer.feed(html_fragment)
        sanitizer.close()
    except Exception as e:
        raise MDRichSanitizeError(f"HTML 解析失败: {e}", code="E_SANITIZE_BLOCKED")
    return "".join(sanitizer.parts), sanitizer.removed


# ═══════════════════════════════════════════════════════
# CSP 策略表（与 sanitize 同源，供 webview2 / CLI 注入）
# ═══════════════════════════════════════════════════════

#: 基础指令：禁止脚本/对象/框架/表单/远程连接，仅允许本地与 data: 图片
_CSP_BASE = (
    "default-src 'none'"
    "; script-src 'none'"
    "; object-src 'none'"
    "; frame-src 'none'"
    "; style-src 'unsafe-inline'"
    "; base-uri 'none'"
    "; form-action 'none'"
    "; connect-src 'none'"
)


def build_csp(level: int = 1, allow_remote_images: bool = False) -> str:
    """按渲染档位构建 CSP 策略字符串。

    - L1：静态展示，script-src 'none'（用户 HTML 不含任何 JS）
    - L4：源码展示同样无用户 JS；复制/折叠交互由宿主脚本驱动，
          宿主在注入时自行按需放宽 script-src，本函数保持最严基线
    - allow_remote_images=True（决策 2 opt-in）：img-src 追加 http(s)
    """
    img_src = "img-src 'self' data:" + (" http: https:" if allow_remote_images else "")
    return f"{_CSP_BASE}; {img_src}"


def build_csp_meta(level: int = 1, allow_remote_images: bool = False) -> str:
    """生成 <meta http-equiv="Content-Security-Policy" ...> 标签。"""
    policy = build_csp(level, allow_remote_images=allow_remote_images)
    escaped = policy.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")
    return (
        '<meta http-equiv="Content-Security-Policy" '
        f'content="{escaped}">'
    )


# ═══════════════════════════════════════════════════════
# SVG 净化（计划 P2/P3：SVG sanitize 内联渲染）
# ═══════════════════════════════════════════════════════

import xml.etree.ElementTree as _ET

#: SVG 元素白名单（静态矢量绘图子集；脚本/动画事件/外部对象一律拒绝）
SVG_TAGS = frozenset(
    {
        "svg", "g", "defs", "title", "desc",
        "rect", "circle", "ellipse", "line", "polyline", "polygon", "path",
        "text", "tspan",
        "use", "symbol", "marker",
        "linearGradient", "radialGradient", "stop",
        "clipPath", "mask", "pattern",
        "image",
        "filter", "feGaussianBlur", "feOffset", "feBlend", "feColorMatrix",
        "feFlood", "feMerge", "feMergeNode",
    }
)

#: SVG 属性白名单（图形/样式/几何；事件与 style 一律拒绝）
SVG_ATTRS = frozenset(
    {
        # 几何与视口
        "viewbox", "width", "height", "x", "y", "cx", "cy", "r", "rx", "ry",
        "d", "points", "x1", "y1", "x2", "y2", "dx", "dy",
        "transform", "preserveaspectratio",
        # 外观
        "fill", "fill-opacity", "stroke", "stroke-width", "stroke-opacity",
        "stroke-linecap", "stroke-linejoin", "stroke-dasharray", "opacity",
        "offset", "stop-color", "stop-opacity",
        # 文本
        "font-size", "font-family", "text-anchor", "dominant-baseline",
        # 通用
        "id", "class", "version",
    }
)

#: href 允许的前缀（本地引用 / data:image 白名单，外部 URL 一律拒绝）
_SVG_HREF_PREFIXES = ("#", "data:image/")


def _svg_local_name(tag: str) -> str:
    """去掉命名空间前缀取本地名（'…}rect' → 'rect'）。"""
    if isinstance(tag, str) and "}" in tag:
        return tag.split("}", 1)[1].lower()
    return str(tag).lower()


def _walk_svg(elem: _ET.Element, removed: List[str]) -> None:
    """递归清洗 SVG 子树：属性白名单 + 元素白名单 + 事件/样式剥离。"""
    tag_local = _svg_local_name(elem.tag)

    # 1. 属性清洗
    attrs_to_drop = []
    for key in list(elem.attrib):
        local = key.split("}")[-1].lower()
        value = elem.attrib[key].strip()
        if local.startswith("on") or local == "style":
            attrs_to_drop.append(key)
            removed.append(f"{tag_local}[{local}]")
        elif local in ("href", "xlink:href"):
            low = value.lower()
            if not low.startswith(_SVG_HREF_PREFIXES):
                attrs_to_drop.append(key)
                removed.append(f"{tag_local}[{local}]")
        elif local not in SVG_ATTRS:
            attrs_to_drop.append(key)
            removed.append(f"{tag_local}[{local}]")
    for key in attrs_to_drop:
        del elem.attrib[key]

    # 2. 子元素白名单（危险元素直接删除整棵子树）
    children_to_drop = []
    for child in list(elem):
        child_local = _svg_local_name(child.tag)
        if child_local not in SVG_TAGS:
            children_to_drop.append(child)
            removed.append(f"<{child_local}>")
        else:
            _walk_svg(child, removed)
    for child in children_to_drop:
        elem.remove(child)


def sanitize_svg(svg_text: str, *, max_size: int = 1048576) -> Tuple[str, List[str]]:
    """SVG 净化（计划 P2：SVG sanitize 内联渲染的前置）。

    策略：
    - 大小上限（max_size，默认 1MB，超出直接拒绝）
    - xml.etree.ElementTree 解析（标准库，不解析外部实体）
    - 元素/属性白名单；剥离 script/foreignObject/iframe/a 等危险元素，
      on* 事件、style、外部 href/xlink:href（仅 # 本地引用与 data:image 放行）
    - 解析失败返回空串 + 剥离记录（调用方降级为源码展示）

    Args:
        svg_text: 原始 SVG 文本
        max_size: 字节上限

    Returns:
        (safe_svg, removed)：safe_svg 为空串表示净化失败/超限
    """
    removed: List[str] = []
    if not isinstance(svg_text, str):
        removed.append("not-str")
        return "", removed
    if len(svg_text.encode("utf-8")) > max_size:
        removed.append("size-over-limit")
        return "", removed

    _ET.register_namespace("", "http://www.w3.org/2000/svg")
    _ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
    try:
        root = _ET.fromstring(svg_text)
    except _ET.ParseError as e:
        removed.append(f"parse-error:{e}")
        return "", removed

    root_local = _svg_local_name(root.tag)
    if root_local != "svg":
        removed.append(f"root-not-svg:<{root_local}>")
        return "", removed

    _walk_svg(root, removed)
    try:
        safe = _ET.tostring(root, encoding="unicode")
    except Exception as e:
        removed.append(f"serialize-error:{e}")
        return "", removed
    return safe, removed

