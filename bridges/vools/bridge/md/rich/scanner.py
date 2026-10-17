"""
vools.bridge.md.rich.scanner — 正文扫描与富内容提取（计划 P0/P2）

决策 D1：`scan_rich()` 独立于 `parse_md()` 契约：
- `parse_md()` 只提取代码块，不保留正文；
- `scan_rich()` 在 `parse_md()` 基础上额外扫描正文中的富内容：
  顶层内联 SVG、内嵌 HTML 片段、图片引用、文件链接，并解析 `#!rich` 文件级指令。

`scan_rich()` 与 `parse_md()` 可独立调用，也可在 renderer 中组合使用。
"""

import os
import re
from typing import Dict, List, Optional, Tuple

from ...core.compat.dataclass_compat import dataclass, field
from ..parser import parse_md
from .sanitize import sanitize_svg
from .status import RichStatus, ok_status, error_status


# ═══════════════════════════════════════════════════════
# #!rich 文件级指令（计划 §2.3 / §3.3 D4）
# ═══════════════════════════════════════════════════════

_RICH_KEY_RE = re.compile(r"^#!rich(?:\s*=\s*(.*))?$", re.IGNORECASE)


@dataclass
class RichConfig:
    """#!rich 文件级指令解析结果（命令行参数可覆盖，见 CLI §5.3 --config）。"""

    allow_local: bool = True
    allow_absolute: bool = False
    allow_remote: bool = False
    allow_remote_images: bool = False
    max_inline_size: int = 1048576
    svg_sanitize: bool = True
    hot_reload: str = "l1"

    def to_dict(self) -> Dict:
        return {
            "allow_local": self.allow_local,
            "allow_absolute": self.allow_absolute,
            "allow_remote": self.allow_remote,
            "allow_remote_images": self.allow_remote_images,
            "max_inline_size": self.max_inline_size,
            "svg_sanitize": self.svg_sanitize,
            "hot_reload": self.hot_reload,
        }

    def merge(self, overrides: Optional[Dict]) -> "RichConfig":
        """合并命令行覆盖（计划 §5.3：命令行参数优先）。"""
        if not overrides:
            return self
        merged = RichConfig(
            allow_local=bool(overrides.get("allow_local", self.allow_local)),
            allow_absolute=bool(overrides.get("allow_absolute", self.allow_absolute)),
            allow_remote=bool(overrides.get("allow_remote", self.allow_remote)),
            allow_remote_images=bool(overrides.get("allow_remote_images", self.allow_remote_images)),
            max_inline_size=int(overrides.get("max_inline_size", self.max_inline_size)),
            svg_sanitize=bool(overrides.get("svg_sanitize", self.svg_sanitize)),
            hot_reload=str(overrides.get("hot_reload", self.hot_reload)),
        )
        return merged


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "on", "allow")


def parse_rich_config(value: Optional[str]) -> RichConfig:
    """解析 `#!rich=key=val,key2=val2` 字符串（计划 §2.3 示例）。"""
    config = RichConfig()
    if not value or not value.strip():
        return config

    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            # 裸 key：hot-reload=l2 / svg-sanitize=false 之外的开关按布尔 true 处理
            key = part.lower().replace("-", "_")
            if hasattr(config, key):
                setattr(config, key, True)
            continue
        key, val = part.split("=", 1)
        key = key.strip().lower().replace("-", "_")
        val = val.strip()
        if key == "max_inline_size":
            try:
                config.max_inline_size = int(val)
            except ValueError:
                pass
        elif key == "hot_reload":
            config.hot_reload = val.lower() if val.lower() in ("l1", "l2") else "l1"
        elif key == "svg_sanitize":
            config.svg_sanitize = _parse_bool(val)
        elif key == "allow_local":
            config.allow_local = _parse_bool(val)
        elif key == "allow_absolute":
            config.allow_absolute = _parse_bool(val)
        elif key == "allow_remote":
            config.allow_remote = _parse_bool(val)
        elif key == "allow_remote_images":
            config.allow_remote_images = _parse_bool(val)
    return config


def extract_rich_directive(text: str) -> Optional[str]:
    """从 md 顶部连续 #! 行中提取 #!rich 指令值（不修改 parse_md 契约）。"""
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if not stripped.startswith("#!"):
            break
        m = _RICH_KEY_RE.match(stripped)
        if m:
            return (m.group(1) or "").strip() or None
    return None


# ═══════════════════════════════════════════════════════
# 富内容数据结构（计划 §5.1）
# ═══════════════════════════════════════════════════════


@dataclass
class SVGFragment:
    """顶层内联 SVG 片段。"""

    index: int
    raw: str
    safe: str  # sanitize 后（svg_sanitize=False 时等于 raw 原文转义）
    meta: Dict = field(default_factory=dict)  # viewBox/width/height 等


@dataclass
class HTMLFragment:
    """顶层内嵌 HTML 片段（非 svg 富内容块）。"""

    index: int
    raw: str
    safe: str  # L1 过滤后
    level: int = 1


@dataclass
class FileLink:
    """正文中的文件链接。"""

    index: int
    text: str
    target: str  # 原文 target（相对路径 / file:// / http(s) / data:）
    resolved_path: Optional[str] = None  # 通过 RichPathResolver 校验后的绝对路径
    kind: str = "unknown"  # document/image/svg/html/json/archive/video/audio/text/binary/remote/data
    status: Optional[RichStatus] = None

    def to_dict(self) -> Dict:
        d: Dict = {
            "index": self.index,
            "text": self.text,
            "target": self.target,
            "kind": self.kind,
        }
        if self.resolved_path:
            d["resolved_path"] = self.resolved_path
        if self.status:
            d["status"] = self.status.to_dict()
        return d


@dataclass
class ArtifactRef:
    """产物引用（export 产物，计划 §5.1 artifacts 字段）。"""

    name: str
    path: str
    kind: str = "text"  # text/image/svg/html/json/binary（计划 D5）
    size: int = 0
    mtime: float = 0.0


@dataclass
class RichDoc:
    """md 文件的富内容视图（计划 §5.1）。"""

    source_path: str
    body_html: str
    inline_svgs: List[SVGFragment] = field(default_factory=list)
    inline_htmls: List[HTMLFragment] = field(default_factory=list)
    file_links: List[FileLink] = field(default_factory=list)
    artifacts: List[ArtifactRef] = field(default_factory=list)
    config: Optional[RichConfig] = None

    def to_dict(self) -> Dict:
        return {
            "source_path": self.source_path,
            "body_html": self.body_html,
            "inline_svgs": [vars(s) for s in self.inline_svgs],
            "inline_htmls": [vars(h) for h in self.inline_htmls],
            "file_links": [l.to_dict() for l in self.file_links],
            "artifacts": [vars(a) for a in self.artifacts],
            "config": self.config.to_dict() if self.config else None,
        }


# ═══════════════════════════════════════════════════════
# 正文扫描
# ═══════════════════════════════════════════════════════

_SVG_START_RE = re.compile(r"^\s*<svg[\s>]", re.IGNORECASE)
_HTML_START_RE = re.compile(r"^\s*<(?!svg\b)([a-zA-Z][a-zA-Z0-9-]*)[\s>]")
_IMG_MD_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_LINK_MD_RE = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)")
_IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
_ATTR_RE = re.compile(r'([a-zA-Z_:][a-zA-Z0-9_:.-]*)\s*=\s*"([^"]*)"')


def _extract_svg_tag(raw: str) -> Tuple[str, str]:
    """提取 `<svg ...>...</svg>` 顶层片段，返回 (svg_text, 剩余行)。"""
    lines = raw.split("\n")
    collected: List[str] = []
    depth = 0
    started = False
    for i, line in enumerate(lines):
        if not started and not _SVG_START_RE.match(line):
            continue
        started = True
        collected.append(line)
        depth += line.count("<svg") - line.count("</svg>")
        if depth <= 0 and "</svg>" in line:
            return "\n".join(collected), "\n".join(lines[i + 1 :])
    if started:
        return "\n".join(collected), ""
    return "", raw


def _mask_fence_lines(text: str) -> str:
    """将代码围栏（``` 块）内的行替换为空行，保留围栏标记与行数。

    顶层富内容扫描使用屏蔽后的文本，避免把围栏内 `<svg>` / `<div>` 误当正文富内容；
    `_body_to_html` 自身的 in_fence 逻辑仍可基于保留的 ``` 标记正确跳过。
    """
    lines = text.split("\n")
    in_fence = False
    for i, line in enumerate(lines):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            lines[i] = ""
    return "\n".join(lines)


def _extract_html_block(raw: str) -> Tuple[str, str]:
    """提取一个顶层 HTML 元素块（如 <div ...>...</div>），返回 (html_text, 剩余行)。"""
    lines = raw.split("\n")
    collected: List[str] = []
    depth = 0
    started = False
    tag_name = None
    for i, line in enumerate(lines):
        if not started:
            m = _HTML_START_RE.match(line)
            if not m:
                continue
            tag_name = m.group(1).lower()
            started = True
            collected.append(line)
            depth += line.count(f"<{tag_name}") - line.count(f"</{tag_name}>")
            if depth <= 0 and f"</{tag_name}>" in line:
                return "\n".join(collected), "\n".join(lines[i + 1 :])
            continue
        collected.append(line)
        depth += line.count(f"<{tag_name}") - line.count(f"</{tag_name}>")
        if depth <= 0 and f"</{tag_name}>" in line:
            return "\n".join(collected), "\n".join(lines[i + 1 :])
    if started:
        return "\n".join(collected), ""
    return "", raw


def _extract_attr(html: str, name: str) -> Optional[str]:
    for key, val in _ATTR_RE.findall(html):
        if key.lower() == name:
            return val
    return None


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _body_to_html(
    text: str,
    *,
    links_out: List[FileLink],
    allow_remote: bool,
) -> str:
    """轻量正文 → HTML（不引入 markdown 依赖）。

    处理：标题、列表、引用、段落、图片引用（![alt](src)）、链接（[t](target)）。
    代码围栏区域跳过（代码块由 parse_md / runner 处理）。
    """
    out: List[str] = []
    in_fence = False
    in_list = False
    idx = len(links_out)

    def close_list():
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        # 标题
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            close_list()
            level = len(m.group(1))
            out.append(f"<h{level}>{_escape(m.group(2))}</h{level}>")
            continue

        # 列表
        m = re.match(r"^[-*+]\s+(.*)$", stripped)
        if m:
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_escape(m.group(1))}</li>")
            continue

        # 引用
        if stripped.startswith(">"):
            close_list()
            out.append(f"<blockquote>{_escape(stripped[1:].strip())}</blockquote>")
            continue

        # 空行
        if not stripped:
            close_list()
            continue

        close_list()
        # 行内：图片 + 链接（链接收集到 links_out）
        line_html = _inline_to_html(stripped, links_out, allow_remote, idx)
        out.append(f"<p>{line_html}</p>")

    close_list()
    return "\n".join(out)


def _inline_to_html(
    text: str,
    links_out: List[FileLink],
    allow_remote: bool,
    start_index: int,
) -> str:
    """行内转换：图片 / 链接。链接按安全模型分类并收集。"""

    def replace_img(m: re.Match) -> str:
        alt = _escape(m.group(1))
        src = m.group(2).strip()
        return f'<img src="{_escape(src)}" alt="{alt}">'

    def replace_link(m: re.Match) -> str:
        text_ = _escape(m.group(1))
        target = m.group(2).strip()
        lower = target.lower()
        if lower.startswith("#") or lower.startswith("data:"):
            return f'<a href="{_escape(target)}">{text_}</a>'
        if lower.startswith(("http://", "https://")):
            # 远程链接：默认拒绝打开（记录为 remote，渲染为不可点击占位）
            status = ok_status("remote") if allow_remote else error_status("E_REMOTE_DISABLED", "http(s) 未 opt-in")
            links_out.append(
                FileLink(
                    index=len(links_out),
                    text=text_,
                    target=target,
                    kind="remote",
                    status=status,
                )
            )
            if allow_remote:
                return f'<a href="{_escape(target)}">{text_}</a>'
            return f'<span class="md-rich-denied" title="远程链接未 opt-in">{text_}</span>'
        # 本地文件链接（相对路径 / file://）
        if lower.startswith("file://"):
            resolved = target
            kind = "local"
        else:
            resolved = target
            kind = "local"
        links_out.append(
            FileLink(index=len(links_out), text=text_, target=target, kind=kind)
        )
        return f'<a href="{_escape(target)}" data-rich-link="{len(links_out) - 1}">{text_}</a>'

    text = _IMG_MD_RE.sub(replace_img, text)
    text = _LINK_MD_RE.sub(replace_link, text)
    return text


# ═══════════════════════════════════════════════════════
# 主入口（计划 D1 / §5.1）
# ═══════════════════════════════════════════════════════


def scan_rich(
    md_path: str,
    *,
    build_dir: Optional[str] = None,
    config: Optional[RichConfig] = None,
) -> RichDoc:
    """扫描 md 文件，提取正文与富内容。不修改 parse_md() 的行为。

    Args:
        md_path: .md 文件路径
        build_dir: 产物根目录（默认 md 所在目录的 .mdbuild，供产物引用）
        config: 预置 RichConfig（None 时从 #!rich 指令解析）

    Returns:
        RichDoc（正文 HTML + 顶层内联 SVG / 内嵌 HTML / 文件链接 / 产物引用）
    """
    parsed = parse_md(md_path)

    with open(md_path, "r", encoding="utf-8") as f:
        text = f.read()

    # 1. #!rich 文件级指令
    directive_value = extract_rich_directive(text)
    if config is None:
        config = parse_rich_config(directive_value)

    # 2. 剥离开文件级指令头，避免 #! 行进入正文
    body_text = text
    header_lines = 0
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#!"):
            header_lines += 1
            continue
        break
    body_text = "\n".join(text.split("\n")[header_lines:])

    # 3. 扫描顶层内联 SVG / 内嵌 HTML
    # 先屏蔽代码围栏内的行（围栏内 <svg>/<div> 由 parse_md/runner 处理，不得被顶层扫描捕获）
    inline_svgs: List[SVGFragment] = []
    inline_htmls: List[HTMLFragment] = []
    remaining = _mask_fence_lines(body_text)
    while True:
        svg_text, remaining = _extract_svg_tag(remaining)
        if svg_text:
            meta = {}
            for key in ("viewBox", "width", "height"):
                val = _extract_attr(svg_text.split("\n", 1)[0], key)
                if val:
                    meta[key] = val
            if config.svg_sanitize and len(svg_text.encode("utf-8")) <= config.max_inline_size:
                safe, _audit = sanitize_svg(svg_text)
            elif config.svg_sanitize:
                safe = _escape(svg_text)
            else:
                safe = svg_text
            inline_svgs.append(
                SVGFragment(index=len(inline_svgs), raw=svg_text, safe=safe, meta=meta)
            )
            continue
        html_text, remaining = _extract_html_block(remaining)
        if html_text:
            from .sanitize import sanitize_html_fragment

            if len(html_text.encode("utf-8")) <= config.max_inline_size:
                safe, _audit = sanitize_html_fragment(html_text)
            else:
                safe = _escape(html_text)
            inline_htmls.append(
                HTMLFragment(index=len(inline_htmls), raw=html_text, safe=safe)
            )
            continue
        break

    # 4. 正文 → HTML + 文件链接收集
    file_links: List[FileLink] = []
    body_html = _body_to_html(
        remaining,
        links_out=file_links,
        allow_remote=config.allow_remote,
    )

    # 5. 产物引用（export 产物，计划 D5 类型感知）
    artifacts: List[ArtifactRef] = []
    from ..artifacts import guess_type

    build = build_dir or os.path.join(os.path.dirname(os.path.abspath(md_path)), ".mdbuild")
    rich_dir = os.path.join(build, "artifacts", "rich")
    if os.path.isdir(rich_dir):
        for fname in sorted(os.listdir(rich_dir)):
            fpath = os.path.join(rich_dir, fname)
            if not os.path.isfile(fpath):
                continue
            try:
                size = os.path.getsize(fpath)
                mtime = os.path.getmtime(fpath)
            except OSError:
                continue
            artifacts.append(
                ArtifactRef(name=fname, path=fpath, kind=guess_type(fpath), size=size, mtime=mtime)
            )

    return RichDoc(
        source_path=os.path.abspath(md_path),
        body_html=body_html,
        inline_svgs=inline_svgs,
        inline_htmls=inline_htmls,
        file_links=file_links,
        artifacts=artifacts,
        config=config,
    )
