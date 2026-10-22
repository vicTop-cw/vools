"""
vools.md.rich — 富内容扫描与数据结构（BRIDGES_MD_RICH_CONTENT_PLAN P0）

提供 Markdown 文档中富内容（图片、SVG、HTML）的提取与结构化表示。

核心组件：
- RichDoc: 富内容文档数据结构
- RichContent: 单条富内容记录
- scan_rich(): 从 Markdown 文本中提取富内容
- parse_rich_directive(): 解析 #!rich 文件级指令

P0 范围：基础解析（不涉及渲染、安全净化、热更新）
"""

from ..core.dataclass_compat import dataclass, field
from typing import List, Optional, Dict, Any
import re

__all__ = [
    'RichDoc', 'RichContent', 'scan_rich', 'parse_rich_directive',
    'RICH_DIRECTIVE_RE',
]


# #!rich 文件级指令正则
# 格式: #!rich=key=val,key=val,...
RICH_DIRECTIVE_RE = re.compile(
    r'^#!rich\s*=\s*(.+)$', re.MULTILINE
)

# 图片引用正则: ![alt](url)
IMAGE_RE = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')

# 顶层 SVG: <svg ...>...</svg>（非嵌套，从行首开始）
SVG_RE = re.compile(r'^\s*<svg[^>]*>.*?</svg>', re.DOTALL | re.MULTILINE)

# HTML 代码块语言标记（在 ``` 代码块内）
HTML_LANGS = frozenset({'html', 'webview2', 'htm', 'xhtml'})

# #!rich 指令默认值
RICH_DEFAULTS: Dict[str, Any] = {
    'allow-local': True,
    'allow-remote': False,
    'max-inline-size': 1048576,  # 1MB
    'svg-sanitize': True,
    'hot-reload': 'l2',  # l1 / l2 / off
}


@dataclass
class RichContent:
    """单条富内容记录。

    Attributes:
        kind: 内容类型 — 'image' / 'svg' / 'html'
        source: 原始引用（URL/路径/代码内容）
        alt: 图片替代文本（仅 image）
        language: 代码块语言标记（仅 html）
        line: 在源文档中的起始行号（0-based，未知为 -1）
        directive: 关联的 #!rich 指令（可为 None）
    """
    kind: str = ''
    source: str = ''
    alt: str = ''
    language: str = ''
    line: int = -1
    directive: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'kind': self.kind,
            'source': self.source,
            'alt': self.alt,
            'language': self.language,
            'line': self.line,
            'directive': self.directive,
        }


@dataclass
class RichDoc:
    """富内容文档数据结构。

    从 Markdown 文本中提取的全部富内容集合。

    Attributes:
        contents: 富内容列表
        directive: 解析后的 #!rich 指令（含默认值合并）
        body: 去除富内容后的正文（保留 Markdown 结构）
    """
    contents: List[RichContent] = field(default_factory=list)
    directive: Dict[str, Any] = field(default_factory=dict)
    body: str = ''

    def to_dict(self) -> Dict[str, Any]:
        return {
            'contents': [c.to_dict() for c in self.contents],
            'directive': self.directive,
            'body': self.body,
        }

    def by_kind(self, kind: str) -> List[RichContent]:
        """按类型过滤富内容。"""
        return [c for c in self.contents if c.kind == kind]

    def __len__(self) -> int:
        return len(self.contents)

    def __bool__(self) -> bool:
        return len(self.contents) > 0


def parse_rich_directive(text: str) -> Dict[str, Any]:
    """解析 #!rich 文件级指令。

    格式: ``#!rich=key=val,key=val,...``

    Args:
        text: Markdown 原文

    Returns:
        指令字典（含默认值合并）；无指令时返回空 dict
    """
    directive: Dict[str, Any] = {}
    m = RICH_DIRECTIVE_RE.search(text)
    if not m:
        return directive

    raw = m.group(1).strip()
    for pair in raw.split(','):
        pair = pair.strip()
        if not pair:
            continue
        parts = pair.split('=', 1)
        if len(parts) != 2:
            continue
        key = parts[0].strip()
        val = parts[1].strip()
        # 类型推断
        if val.lower() in ('true', 'false'):
            directive[key] = val.lower() == 'true'
        elif val.isdigit():
            directive[key] = int(val)
        else:
            directive[key] = val

    return directive


def scan_rich(text: str) -> RichDoc:
    """从 Markdown 文本中提取富内容（P0：基础扫描）。

    扫描三类富内容：
      1. 图片引用: ``![alt](url)``
      2. 顶层 SVG: ``<svg>...</svg>``（行首开始）
      3. HTML 代码块: ```html / ```webview2 ```

    Args:
        text: Markdown 原文

    Returns:
        RichDoc 实例，含富内容列表、指令、去富后的正文
    """
    doc = RichDoc()

    # 1. 解析 #!rich 指令
    directive = parse_rich_directive(text)
    doc.directive = {**RICH_DEFAULTS, **directive}

    # 2. 提取图片引用
    for m in IMAGE_RE.finditer(text):
        alt = m.group(1)
        source = m.group(2)
        line = text[:m.start()].count('\n')
        doc.contents.append(RichContent(
            kind='image',
            source=source,
            alt=alt,
            line=line,
            directive=doc.directive,
        ))

    # 3. 提取顶层 SVG
    for m in SVG_RE.finditer(text):
        line = text[:m.start()].count('\n')
        doc.contents.append(RichContent(
            kind='svg',
            source=m.group(0),
            line=line,
            directive=doc.directive,
        ))

    # 4. 提取 HTML 代码块
    for m in re.finditer(r'```(\w+)\n(.*?)```', text, re.DOTALL):
        lang = m.group(1).strip().lower()
        if lang in HTML_LANGS:
            line = text[:m.start()].count('\n')
            doc.contents.append(RichContent(
                kind='html',
                source=m.group(2),
                language=lang,
                line=line,
                directive=doc.directive,
            ))

    # 5. 生成去富后的正文（P0：简单移除，不做深度重建）
    body = text
    # 移除图片引用（保留 alt 文本）
    body = IMAGE_RE.sub(lambda m: m.group(1) or '', body)
    # 移除顶层 SVG
    body = SVG_RE.sub('', body)
    # 移除 #!rich 指令行
    body = RICH_DIRECTIVE_RE.sub('', body)

    doc.body = body

    return doc
