"""
Markdown 解析器

将 Markdown 文本解析为结构化 AST（Abstract Syntax Tree）。
AST 节点类型：
  - Document: 根节点，包含 children
  - Heading: 标题 (level 1-6)
  - Paragraph: 段落
  - CodeBlock: 代码块（fenced ```）
  - BlockQuote: 引用块
  - ListItem: 列表项
    - MdList: 有序/无序列表
  - Divider: 水平分割线 (---, ***, ___)
  - InlineText: 行内文本（含 bold/italic/code/link 等）
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import re


# ─── AST 节点定义 ───

@dataclass
class InlineText:
    """行内文本节点，支持 bold/italic/code/link/strikethrough"""
    text: str
    bold: bool = False
    italic: bool = False
    code: bool = False
    strikethrough: bool = False
    link: Optional[str] = None
    html: Optional[str] = None  # HTML 行内标签（如 <br>, <sup>, <sub>）

    def __repr__(self):
        tags = []
        if self.bold: tags.append("B")
        if self.italic: tags.append("I")
        if self.code: tags.append("C")
        if self.strikethrough: tags.append("S")
        if self.link: tags.append(f"L:{self.link}")
        if self.html: tags.append(f"H:{self.html}")
        tag_str = f"[{' '.join(tags)}]" if tags else ""
        return f"InlineText({tag_str}{self.text!r})"


@dataclass
class Heading:
    """标题节点"""
    level: int  # 1-6
    children: List[InlineText] = field(default_factory=list)


@dataclass
class Paragraph:
    """段落节点"""
    children: List[InlineText] = field(default_factory=list)


@dataclass
class CodeBlock:
    """代码块节点"""
    code: str
    language: str = ""


@dataclass
class BlockQuote:
    """引用块节点"""
    children: List[Any] = field(default_factory=list)  # 嵌套块节点


@dataclass
class ListItem:
    """列表项节点"""
    checked: Optional[bool] = None  # None=非任务项, True=已选, False=未选
    children: List[InlineText] = field(default_factory=list)


@dataclass
class MdList:
    """列表节点"""
    ordered: bool = False
    items: List[ListItem] = field(default_factory=list)


@dataclass
class Divider:
    """水平分割线节点"""
    pass


@dataclass
class Document:
    """文档根节点"""
    children: List[Any] = field(default_factory=list)


# ─── 行内解析 ───

def _parse_inline(text: str) -> List[InlineText]:
    """解析行内文本，提取 bold/italic/code/link/strikethrough"""
    result = []
    buf = []  # 累积普通文本字符
    i = 0

    def _flush():
        if buf:
            result.append(InlineText(text=''.join(buf)))
            buf.clear()

    while i < len(text):
        # 自动链接 <https://example.com>（先于 HTML 标签检查）
        if text[i] == '<':
            auto_link_match = re.match(r'<(https?://[^>]+)>', text[i:])
            if auto_link_match:
                _flush()
                result.append(InlineText(text=auto_link_match.group(1), link=auto_link_match.group(1)))
                i += auto_link_match.end()
                continue

            # HTML 行内标签 <br>, <sup>, <sub>, <kbd>, <mark> 等
            html_match = re.match(r'<([a-zA-Z][a-zA-Z0-9]*)\b([^>]*)>', text[i:])
            if html_match:
                _flush()
                tag = html_match.group(1)
                attrs = html_match.group(2).strip()
                if tag in ('br', 'hr', 'img', 'input', 'meta', 'link'):
                    result.append(InlineText(text=f'<{tag}{attrs}>', html=tag))
                elif attrs:
                    result.append(InlineText(text=f'<{tag}{attrs}>', html=tag))
                else:
                    result.append(InlineText(text=f'<{tag}>', html=tag))
                i += html_match.end()
                continue

        # 行内代码 `code`
        if text[i] == '`':
            _flush()
            end = text.find('`', i + 1)
            if end != -1:
                result.append(InlineText(text=text[i+1:end], code=True))
                i = end + 1
                continue

        # 链接 [text](url)
        if text[i] == '[':
            _flush()
            link_match = re.match(r'\[([^\]]+)\]\(([^)]+)\)', text[i:])
            if link_match:
                result.append(InlineText(
                    text=link_match.group(1),
                    link=link_match.group(2)
                ))
                i += link_match.end()
                continue

            # 参考式链接 [text][ref] 或 [text]
            ref_match = re.match(r'\[([^\]]+)\]\[([^\]]+)\]', text[i:])
            if ref_match:
                result.append(InlineText(
                    text=ref_match.group(1),
                    link=f'#ref:{ref_match.group(2)}'
                ))
                i += ref_match.end()
                continue

            # 简化参考式 [text]（无显式 ref）
            simple_ref = re.match(r'\[([^\]]+)\]', text[i:])
            if simple_ref and not re.match(r'\[([^\]]+)\]\(', text[i:]):
                result.append(InlineText(
                    text=simple_ref.group(1),
                    link=f'#ref:{simple_ref.group(1).lower()}'
                ))
                i += simple_ref.end()
                continue

        # 自动链接 <https://example.com>
        if text[i] == '<' and re.match(r'<(https?://[^>]+)>', text[i:]):
            _flush()
            url_match = re.match(r'<(https?://[^>]+)>', text[i:])
            result.append(InlineText(text=url_match.group(1), link=url_match.group(1)))
            i += url_match.end()
            continue

        # 粗体 **text** 或 __text__
        if i + 1 < len(text) and text[i:i+2] in ('**', '__'):
            _flush()
            sep = text[i:i+2]
            end = text.find(sep, i + 2)
            if end != -1:
                result.append(InlineText(text=text[i+2:end], bold=True))
                i = end + 2
                continue

        # 斜体 *text* 或 _text_
        if text[i] in ('*', '_') and i + 1 < len(text) and text[i+1] != text[i]:
            _flush()
            end = text.find(text[i], i + 1)
            if end != -1 and end > i + 1:
                result.append(InlineText(text=text[i+1:end], italic=True))
                i = end + 1
                continue

        # 删除线 ~~text~~
        if i + 1 < len(text) and text[i:i+2] == '~~':
            _flush()
            end = text.find('~~', i + 2)
            if end != -1:
                result.append(InlineText(text=text[i+2:end], strikethrough=True))
                i = end + 2
                continue

        # 普通字符累积
        buf.append(text[i])
        i += 1

    _flush()
    return result


# ─── 块级解析 ───

def _parse_fenced_code(lines: List[str], start: int) -> tuple:
    """解析 fenced code block (``` 或 ~~~)"""
    fence_line = lines[start].strip()
    fence_char = fence_line[0] if fence_line else '`'

    # 计算 fence 长度（连续相同字符数）
    fence_len = 0
    for ch in fence_line:
        if ch == fence_char:
            fence_len += 1
        else:
            break

    # 提取语言（fence 之后的内容）
    language = fence_line[fence_len:].strip()

    # 找结束 fence
    code_lines = []
    i = start + 1
    while i < len(lines):
        end_line = lines[i].strip()
        if end_line.startswith(fence_char * fence_len) and len(end_line) >= fence_len:
            break
        code_lines.append(lines[i])
        i += 1

    return CodeBlock(code='\n'.join(code_lines), language=language), i + 1


def _parse_heading(line: str) -> Optional[Heading]:
    """解析标题行 # ## ### 等"""
    m = re.match(r'^(#{1,6})\s+(.+)$', line)
    if m:
        level = len(m.group(1))
        children = _parse_inline(m.group(2).strip())
        return Heading(level=level, children=children)
    return None


def _parse_divider(line: str) -> Optional[Divider]:
    """解析水平分割线 --- *** ___"""
    stripped = line.strip()
    if re.match(r'^(-{3,}|\*{3,}|_{3,})\s*$', stripped):
        return Divider()
    return None


def _parse_blockquote(lines: List[str], start: int) -> tuple:
    """解析引用块 >"""
    children = []
    i = start
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        if stripped.startswith('>'):
            content = stripped[1:].strip()
            # 递归解析引用内容
            if content:
                heading = _parse_heading(content)
                if heading:
                    children.append(heading)
                else:
                    children.append(Paragraph(children=_parse_inline(content)))
            i += 1
        else:
            break

    return BlockQuote(children=children), i


def _parse_list(lines: List[str], start: int) -> tuple:
    """解析有序/无序列表"""
    ordered = False
    items = []
    i = start

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # 无序列表项
        unordered_match = re.match(r'^[-*+]\s+(.+)$', stripped)
        # 有序列表项
        ordered_match = re.match(r'^(\d+)\.\s+(.+)$', stripped)
        # 任务列表项
        task_match = re.match(r'^[-*+]\s+\[([ xX])\]\s+(.+)$', stripped)

        if task_match:
            checked = task_match.group(1).lower() == 'x'
            items.append(ListItem(
                checked=checked,
                children=_parse_inline(task_match.group(2))
            ))
            ordered = False
            i += 1
            continue

        if unordered_match:
            items.append(ListItem(children=_parse_inline(unordered_match.group(1))))
            ordered = False
            i += 1
            continue

        if ordered_match:
            items.append(ListItem(children=_parse_inline(ordered_match.group(2))))
            ordered = True
            i += 1
            continue

        # 列表结束：遇到非列表行或空行后跟非列表内容
        break

    if not items:
        return None, start

    return MdList(ordered=ordered, items=items), i


def _parse_paragraph(lines: List[str], start: int) -> tuple:
    """解析段落（连续非空行）"""
    content_lines = []
    i = start
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            break
        # 检查是否是块级元素起始
        if stripped.startswith('```') or stripped.startswith('~~~'):
            break
        if stripped.startswith('#'):
            break
        if stripped.startswith('>'):
            break
        if re.match(r'^(-{3,}|\*{3,}|_{3,})\s*$', stripped):
            break
        # 遇到缩进行（可能是定义列表的定义部分），停止段落
        if line.startswith('    ') or line.startswith('\t'):
            break
        content_lines.append(stripped)
        i += 1

    if not content_lines:
        return None, start

    # 合并行内换行
    text = '\n'.join(content_lines)
    return Paragraph(children=_parse_inline(text)), i


# ─── 主解析函数 ───

def parse(markdown_text: str) -> Document:
    """
    解析 Markdown 文本为 AST。

    Args:
        markdown_text: Markdown 源文本

    Returns:
        Document 节点（根节点）

    Example:
        >>> doc = parse("# Hello\\n\\nWorld")
        >>> doc.children[0].level
        1
    """
    lines = markdown_text.split('\n')
    # 去掉 trailing empty lines
    while lines and not lines[-1].strip():
        lines.pop()

    doc = Document()
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # 空行跳过
        if not stripped:
            i += 1
            continue

        # fenced code block
        if stripped.startswith('```') or stripped.startswith('~~~'):
            node, i = _parse_fenced_code(lines, i)
            doc.children.append(node)
            continue

        # heading
        heading = _parse_heading(line)
        if heading:
            doc.children.append(heading)
            i += 1
            continue

        # divider
        divider = _parse_divider(line)
        if divider:
            doc.children.append(divider)
            i += 1
            continue

        # blockquote
        if stripped.startswith('>'):
            node, i = _parse_blockquote(lines, i)
            doc.children.append(node)
            continue

        # list
        list_match = re.match(r'^[-*+]\s+', stripped) or re.match(r'^\d+\.\s+', stripped)
        if list_match:
            node, i = _parse_list(lines, i)
            if node:
                doc.children.append(node)
            continue

        # paragraph
        node, i = _parse_paragraph(lines, i)
        if node:
            doc.children.append(node)
        else:
            i += 1

    return doc


def parse_to_dict(markdown_text: str) -> dict:
    """
    解析 Markdown 文本为字典结构（便于序列化）。

    Returns:
        dict 格式的 AST
    """
    def node_to_dict(node):
        if isinstance(node, Document):
            return {'type': 'document', 'children': [node_to_dict(c) for c in node.children]}
        elif isinstance(node, Heading):
            return {'type': 'heading', 'level': node.level,
                    'children': [_inline_to_dict(c) for c in node.children]}
        elif isinstance(node, Paragraph):
            return {'type': 'paragraph',
                    'children': [_inline_to_dict(c) for c in node.children]}
        elif isinstance(node, CodeBlock):
            return {'type': 'code_block', 'code': node.code, 'language': node.language}
        elif isinstance(node, BlockQuote):
            return {'type': 'blockquote', 'children': [node_to_dict(c) for c in node.children]}
        elif isinstance(node, MdList):
            return {'type': 'list', 'ordered': node.ordered,
                    'items': [_list_item_to_dict(it) for it in node.items]}
        elif isinstance(node, Divider):
            return {'type': 'divider'}
        return {'type': 'unknown'}

    def _inline_to_dict(node):
        return {
            'type': 'inline',
            'text': node.text,
            'bold': node.bold,
            'italic': node.italic,
            'code': node.code,
            'strikethrough': node.strikethrough,
            'link': node.link,
        }

    def _list_item_to_dict(item):
        return {
            'type': 'list_item',
            'checked': item.checked,
            'children': [_inline_to_dict(c) for c in item.children],
        }

    return node_to_dict(parse(markdown_text))


__all__ = [
    'BlockQuote',
    'CodeBlock',
    'Divider',
    'Document',
    'Heading',
    'InlineText',
    'ListItem',
    'MdList',
    'Paragraph',
    'parse',
    'parse_to_dict'
]
