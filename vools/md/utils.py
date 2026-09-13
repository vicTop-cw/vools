"""
Markdown 工具函数

提供元数据提取、TOC 生成、代码块提取等常用工具。
"""

from .parser import (
    parse, Document, Heading, Paragraph, CodeBlock, MdList, BlockQuote, Divider, InlineText
)
from typing import List, Dict, Optional, Tuple
import re
import json


# ─── 元数据提取 ───

def extract_metadata(markdown_text: str) -> Dict[str, str]:
    """
    提取 Markdown 文件头部的 YAML front matter 元数据。

    支持格式：
        ---
        title: Hello
        date: 2024-01-01
        ---

    Args:
        markdown_text: Markdown 源文本

    Returns:
        元数据字典（空字典如果没有 front matter）

    Example:
        >>> meta = extract_metadata("---\\ntitle: Hello\\n---\\n# World")
        >>> meta['title']
        'Hello'
    """
    meta = {}
    lines = markdown_text.split('\n')

    # 检查前两行是否是 --- 分隔符
    if len(lines) < 2 or lines[0].strip() != '---':
        return meta

    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == '---':
            end_idx = i
            break

    if end_idx is None:
        return meta

    # 解析 YAML 格式的 key: value
    for line in lines[1:end_idx]:
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        if ':' in stripped:
            key, _, value = stripped.partition(':')
            meta[key.strip()] = value.strip()

    return meta


# ─── TOC 生成 ───

def generate_toc(markdown_text: str, max_level: int = 6) -> List[Dict]:
    """
    从 Markdown 文本生成目录（Table of Contents）。

    Args:
        markdown_text: Markdown 源文本
        max_level: 最大标题层级（默认 6）

    Returns:
        目录结构列表，每项包含 level/text/id/children

    Example:
        >>> toc = generate_toc("# Hello\\n## Sub")
        >>> toc[0]['level']
        1
    """
    doc = parse(markdown_text)
    headings = []

    for node in doc.children:
        if isinstance(node, Heading):
            if node.level > max_level:
                continue
            # 提取标题文本
            text = ''.join(c.text for c in node.children)
            # 生成 anchor id（小写 + 空格替换为 _）
            anchor = text.lower().replace(' ', '_').replace('\n', '_')
            headings.append({
                'level': node.level,
                'text': text,
                'id': anchor,
            })

    # 构建嵌套结构
    def build_nested(items, current_level):
        result = []
        for item in items:
            if item['level'] == current_level:
                children = build_nested(items[items.index(item) + 1:], current_level)
                item['children'] = children
                result.append(item)
        return result

    # 简化：扁平列表 + 层级
    return headings


def generate_toc_markdown(markdown_text: str, max_level: int = 6) -> str:
    """
    生成 Markdown 格式的目录。

    Args:
        markdown_text: Markdown 源文本
        max_level: 最大标题层级

    Returns:
        Markdown 格式的目录文本
    """
    headings = generate_toc(markdown_text, max_level)
    lines = ['## 目录', '']
    for h in headings:
        indent = '  ' * (h['level'] - 1)
        lines.append(f'{indent}- [{h["text"]}](#{h["id"]})')
    return '\n'.join(lines)


# ─── 代码块提取 ───

def extract_code_blocks(markdown_text: str, language: Optional[str] = None) -> List[Dict]:
    """
    提取 Markdown 中的所有代码块。

    Args:
        markdown_text: Markdown 源文本
        language: 按语言过滤（可选）

    Returns:
        代码块列表，每项包含 code/language

    Example:
        >>> blocks = extract_code_blocks("```python\\nprint(1)\\n```")
        >>> blocks[0]['language']
        'python'
    """
    doc = parse(markdown_text)
    blocks = []

    for node in doc.children:
        if isinstance(node, CodeBlock):
            if language is None or node.language == language:
                blocks.append({
                    'code': node.code,
                    'language': node.language,
                })

    return blocks


# ─── 其他工具 ───

def count_words(markdown_text: str) -> int:
    """统计 Markdown 文本的词数（排除代码块和标记符号）。"""
    doc = parse(markdown_text)
    word_count = 0

    def _count_node(node):
        nonlocal word_count
        if isinstance(node, Document):
            for c in node.children:
                _count_node(c)
        elif isinstance(node, (Heading, Paragraph)):
            for inline in node.children:
                word_count += len(inline.text.split())
        elif isinstance(node, CodeBlock):
            word_count += len(node.code.split())
        elif isinstance(node, (MdList, BlockQuote)):
            for item in node.items if isinstance(node, MdList) else node.children:
                _count_node(item)
                if isinstance(item, ListItem):
                    for inline in item.children:
                        word_count += len(inline.text.split())

    _count_node(doc)
    return word_count


def strip_markdown(markdown_text: str) -> str:
    """
    去除 Markdown 标记符号，返回纯文本。

    Args:
        markdown_text: Markdown 源文本

    Returns:
        纯文本（去除所有标记符号）

    Example:
        >>> strip_markdown("# **Hello** world")
        'Hello world'
    """
    doc = parse(markdown_text)
    lines = []

    def _strip_node(node, depth=0):
        if isinstance(node, Document):
            for c in node.children:
                _strip_node(c, depth)
        elif isinstance(node, Heading):
            text = ''.join(c.text for c in node.children)
            lines.append(text)
        elif isinstance(node, Paragraph):
            text = ''.join(c.text for c in node.children)
            lines.append(text)
        elif isinstance(node, CodeBlock):
            lines.append(node.code)
        elif isinstance(node, BlockQuote):
            for c in node.children:
                _strip_node(c, depth + 1)
        elif isinstance(node, MdList):
            for item in node.items:
                text = ''.join(c.text for c in item.children)
                prefix = '  ' * depth
                lines.append(f'{prefix}- {text}')
        elif isinstance(node, Divider):
            lines.append('---')

    _strip_node(doc)
    return '\n'.join(lines)


def find_headings(markdown_text: str) -> List[Dict]:
    """
    查找所有标题。

    Returns:
        标题列表，每项包含 level/text
    """
    doc = parse(markdown_text)
    headings = []
    for node in doc.children:
        if isinstance(node, Heading):
            text = ''.join(c.text for c in node.children)
            headings.append({'level': node.level, 'text': text})
    return headings


# ─── 多格式转换 ───

def to_json(markdown_text: str, indent: int = 2) -> str:
    """
    将 Markdown 解析为 JSON 格式。

    Args:
        markdown_text: Markdown 源文本
        indent: JSON 缩进

    Returns:
        JSON 字符串
    """
    from .parser import parse_to_dict
    return json.dumps(parse_to_dict(markdown_text), ensure_ascii=False, indent=indent)


def to_org_mode(markdown_text: str) -> str:
    """
    将 Markdown 转换为 Org-mode 格式。

    Args:
        markdown_text: Markdown 源文本

    Returns:
        Org-mode 字符串
    """
    doc = parse(markdown_text)
    lines = []

    def _node_to_org(node, depth=0):
        if isinstance(node, Document):
            for c in node.children:
                _node_to_org(c, depth)
        elif isinstance(node, Heading):
            lines.append('#' * node.level + ' ' + ''.join(c.text for c in node.children))
        elif isinstance(node, Paragraph):
            lines.append(''.join(c.text for c in node.children))
            lines.append('')
        elif isinstance(node, CodeBlock):
            lines.append('#+BEGIN_SRC ' + node.language)
            lines.append(node.code)
            lines.append('#+END_SRC')
            lines.append('')
        elif isinstance(node, BlockQuote):
            for c in node.children:
                _node_to_org(c, depth)
        elif isinstance(node, MdList):
            for item in node.items:
                item_text = ''.join(c.text for c in item.children)
                if node.ordered:
                    lines.append(f'{"  " * depth}{item_text}')
                else:
                    lines.append(f'{"  " * depth}- {item_text}')
        elif isinstance(node, Divider):
            lines.append('---')
            lines.append('')

    _node_to_org(doc)
    return '\n'.join(lines)


def to_plain_text(markdown_text: str) -> str:
    """
    将 Markdown 转换为纯文本（去除所有标记）。

    Returns:
        纯文本
    """
    return strip_markdown(markdown_text)

