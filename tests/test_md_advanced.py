"""vools.md 阶段2：高级块级解析（表格/脚注/定义列表/HTML块）"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vools.md.parser import (
    parse, Document, Heading, Paragraph, CodeBlock, BlockQuote,
    MdList, ListItem, Divider, InlineText, parse_to_dict,
    _parse_inline, _parse_fenced_code, _parse_heading, _parse_divider,
    _parse_blockquote, _parse_list, _parse_paragraph
)
from vools.md.generator import generate
from vools.md.html import to_html

import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


# ─── 新增 AST 节点 ───

@dataclass
class Table:
    """GFM 表格节点"""
    headers: List[List[InlineText]] = field(default_factory=list)
    rows: List[List[List[InlineText]]] = field(default_factory=list)
    align: List[str] = field(default_factory=list)  # 'left', 'center', 'right'


@dataclass
class Footnote:
    """脚注定义节点"""
    label: str
    children: List[InlineText] = field(default_factory=list)


@dataclass
class DefinitionList:
    """定义列表节点"""
    terms: List[str] = field(default_factory=list)
    definitions: List[List[InlineText]] = field(default_factory=list)


@dataclass
class HtmlBlock:
    """HTML 块级标签节点"""
    tag: str
    content: str
    attrs: Dict[str, str] = field(default_factory=dict)


# ─── 表格解析 ───

def _parse_table(lines: List[str], start: int) -> tuple:
    """解析 GFM 表格

    格式：
        | Col1 | Col2 |
        |------|------|
        | A    | B    |
    """
    # 检查是否有分隔行
    if start + 1 >= len(lines):
        return None, start

    header_line = lines[start].strip()
    sep_line = lines[start + 1].strip()

    # 确认是表格（有 | 分隔符和对齐行）
    if '|' not in header_line:
        return None, start

    # 解析对齐行
    align = []
    cells = header_line.strip('|').split('|')
    for cell in cells:
        cell = cell.strip()
        if cell.startswith(':') and cell.endswith(':'):
            align.append('center')
        elif cell.endswith(':'):
            align.append('right')
        elif cell.startswith(':'):
            align.append('left')
        else:
            align.append('left')

    # 解析表头
    headers = [_parse_inline(cell.strip()) for cell in cells]

    # 解析数据行
    rows = []
    i = start + 2
    while i < len(lines):
        line = lines[i].strip()
        if not line or '|' not in line:
            break
        row_cells = line.strip('|').split('|')
        rows.append([_parse_inline(cell.strip()) for cell in row_cells])
        i += 1

    return Table(headers=headers, rows=rows, align=align), i


# ─── 脚注解析 ───

def _parse_footnote(lines: List[str], start: int) -> tuple:
    """解析脚注定义

    格式：
        [^label]: content
        [^label]:
            multi-line content
    """
    line = lines[start].strip()
    match = re.match(r'^\[\^([^\]]+)\]:\s*(.*)$', line)
    if not match:
        return None, start

    label = match.group(1)
    content = match.group(2)

    # 多行脚注
    i = start + 1
    children = _parse_inline(content) if content else []

    while i < len(lines):
        next_line = lines[i].strip()
        if not next_line or re.match(r'^\[\^[^\]]+\]:', next_line):
            break
        # 缩进的连续行属于当前脚注
        if next_line.startswith('  ') or next_line.startswith('\t'):
            children.extend(_parse_inline(next_line.strip()))
            i += 1
        else:
            break

    return Footnote(label=label, children=children), i


# ─── 定义列表解析 ───

def _parse_definition_list(lines: List[str], start: int) -> tuple:
    """解析定义列表

    格式：
        term1
        term2
            : definition for term2
    """
    # 先收集术语（非缩进行，不是其他块级元素）
    terms = []
    i = start
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            break
        # 术语行：无缩进，不是其他块级元素
        if (not line.startswith('    ') and not line.startswith('\t')
                and not re.match(r'^[-*+]\s+', stripped)
                and not re.match(r'^\d+\.\s+', stripped)
                and not stripped.startswith('#')
                and not stripped.startswith('>')
                and not stripped.startswith('```')
                and '|' not in stripped):
            terms.append(stripped)
            i += 1
        else:
            break

    if not terms:
        return None, start

    # 检查是否有缩进的定义行
    if i >= len(lines):
        return None, start  # 没有定义，不是定义列表

    next_line = lines[i]
    if not (next_line.startswith('    ') or next_line.startswith('\t')):
        return None, start  # 没有缩进定义，不是定义列表

    # 解析定义
    definitions = []
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        # 定义行以 4 空格缩进
        if line.startswith('    ') or line.startswith('\t'):
            content = stripped
            # 跳过 : 前缀
            if content.startswith(':'):
                content = content[1:].strip()
            definitions.append(_parse_inline(content))
            i += 1
        else:
            break

    return DefinitionList(terms=terms, definitions=definitions), i


# ─── HTML 块解析 ───

def _parse_html_block(lines: List[str], start: int) -> tuple:
    """解析 HTML 块级标签

    支持：<div>, <section>, <article>, <table>, <ul>, <ol>, <pre>, <code> 等
    """
    line = lines[start].strip()
    match = re.match(r'^<([a-zA-Z][a-zA-Z0-9]*)\b([^>]*)>(.*)$', line)
    if not match:
        return None, start

    tag = match.group(1).lower()
    attrs_str = match.group(2)
    content = match.group(3)

    # 解析属性
    attrs = {}
    attr_matches = re.findall(r'(\w+)\s*=\s*["\']([^"\']*)["\']', attrs_str)
    for k, v in attr_matches:
        attrs[k] = v

    # 收集连续 HTML 行
    i = start + 1
    while i < len(lines):
        next_line = lines[i].strip()
        if not next_line:
            break
        # 遇到 Markdown 语法则停止
        if next_line.startswith('#') or next_line.startswith('```') or next_line.startswith('>'):
            break
        content += '\n' + next_line
        i += 1

    return HtmlBlock(tag=tag, content=content, attrs=attrs), i


# ─── 增强主解析函数 ───

def parse_advanced(markdown_text: str) -> Document:
    """
    增强版解析器，支持表格、脚注、定义列表、HTML 块。

    Args:
        markdown_text: Markdown 源文本

    Returns:
        Document 节点（含新增节点类型）
    """
    lines = markdown_text.split('\n')
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

        # table (GFM)
        if '|' in stripped and i + 1 < len(lines):
            table_node, new_i = _parse_table(lines, i)
            if table_node:
                doc.children.append(table_node)
                i = new_i
                continue

        # footnote
        if re.match(r'^\[\^[^\]]+\]:', stripped):
            node, new_i = _parse_footnote(lines, i)
            if node:
                doc.children.append(node)
                i = new_i
                continue

        # definition list (look ahead for indented definitions after terms)
        if (not stripped.startswith('#') and not stripped.startswith('>')
                and not stripped.startswith('```') and '|' not in stripped
                and not re.match(r'^[-*+]\s+', stripped)
                and not re.match(r'^\d+\.\s+', stripped)
                and not re.match(r'^\[\^[^\]]+\]:', stripped)
                and not re.match(r'^<[a-zA-Z]', stripped)
                and i + 1 < len(lines)):
            # Look ahead up to 5 lines for an indented definition line
            found_indented = False
            for j in range(i + 1, min(i + 6, len(lines))):
                if lines[j].startswith('    ') or lines[j].startswith('\t'):
                    found_indented = True
                    break
                if not lines[j].strip():
                    continue
                # If we hit another block-level element, stop looking
                if lines[j].strip().startswith('#') or lines[j].strip().startswith('>'):
                    break
            if found_indented:
                node, new_i = _parse_definition_list(lines, i)
                if node:
                    doc.children.append(node)
                    i = new_i
                    continue

        # HTML block
        html_match = re.match(r'^<[a-zA-Z][a-zA-Z0-9]*\b', stripped)
        if html_match:
            node, new_i = _parse_html_block(lines, i)
            if node:
                doc.children.append(node)
                i = new_i
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


# ─── 测试 ───

def test_table():
    md = "| Col1 | Col2 |\n|------|------|\n| A | B |\n| C | D |"
    doc = parse_advanced(md)
    assert isinstance(doc.children[0], Table)
    assert len(doc.children[0].headers) == 2
    assert len(doc.children[0].rows) == 2
    print('OK: table')


def test_footnote():
    md = "Text[^1].\n\n[^1]: This is a footnote."
    doc = parse_advanced(md)
    # 脚注定义在文末
    footnotes = [c for c in doc.children if isinstance(c, Footnote)]
    assert len(footnotes) == 1
    assert footnotes[0].label == '1'
    print('OK: footnote')


def test_definition_list():
    md = "term1\nterm2\n    : def for term2"
    doc = parse_advanced(md)
    defs = [c for c in doc.children if isinstance(c, DefinitionList)]
    assert len(defs) == 1
    assert len(defs[0].terms) == 2
    print('OK: definition list')


def test_html_block():
    md = "<div class=\"test\">\ncontent\n</div>"
    doc = parse_advanced(md)
    htmls = [c for c in doc.children if isinstance(c, HtmlBlock)]
    assert len(htmls) == 1
    assert htmls[0].tag == 'div'
    assert htmls[0].attrs.get('class') == 'test'
    print('OK: html block')


def test_complex_advanced():
    md = """# Title

| A | B |
|---|---|
| 1 | 2 |

Text[^1].

[^1]: Footnote.

term
    : definition

<div>html</div>

Regular paragraph."""
    doc = parse_advanced(md)
    assert len(doc.children) >= 6
    print('OK: complex advanced document')


if __name__ == '__main__':
    test_table()
    test_footnote()
    test_definition_list()
    test_html_block()
    test_complex_advanced()
    print()
    print('All 5 advanced parsing tests passed!')
