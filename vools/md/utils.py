"""
Markdown 工具函数

提供元数据提取、TOC 生成、代码块提取等常用工具。
"""

from .parser import (
    parse, Document, Heading, Paragraph, CodeBlock, MdList, BlockQuote, Divider, InlineText, ListItem,
    ConfigBlock, LangBlock
)
from .config_parser import parse_config_block, render_config as _render_config
from typing import List, Dict, Optional, Tuple, Any
import re
import json


# ─── 元数据提取 ───
def _normalize_metadata(value):
    """将 PyYAML 推断出的 datetime.date/datetime.datetime 值转回 ISO 字符串。

    extract_metadata 的契约是返回 str/int/float/bool/list/dict；
    PyYAML 会把 `2024-01-01` 解析为 datetime.date，破坏该契约。
    """
    import datetime as _dt
    if isinstance(value, dict):
        return {k: _normalize_metadata(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize_metadata(v) for v in value]
    if isinstance(value, (_dt.date, _dt.datetime)):
        return value.isoformat()
    return value


# ─── 元数据提取 ───


def extract_metadata(markdown_text: str) -> Dict[str, Any]:
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
        值类型自动推断（str/int/float/bool/list/dict）

    Example:
        >>> meta = extract_metadata("---\\ntitle: Hello\\n---\\n# World")
        >>> meta['title']
        'Hello'
    """
    lines = markdown_text.split('\n')

    # 检查前两行是否是 --- 分隔符
    if len(lines) < 2 or lines[0].strip() != '---':
        return {}

    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == '---':
            end_idx = i
            break

    if end_idx is None:
        return {}

    # 提取 front matter 内容
    frontmatter_text = '\n'.join(lines[1:end_idx])

    # 使用 config_parser 解析（支持嵌套/类型推断）
    try:
        from .config_parser import parse_yaml
        return _normalize_metadata(parse_yaml(frontmatter_text))
    except Exception:
        # 回退到简单解析
        meta = {}
        for line in lines[1:end_idx]:
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue
            if ':' in stripped:
                key, _, value = stripped.partition(':')
                meta[key.strip()] = value.strip()
        return meta


def extract_frontmatter(markdown_text: str) -> Dict[str, Any]:
    """
    提取并解析 YAML front matter（增强版）。

    与 extract_metadata 相同，但明确返回 Dict[str, Any]，
    支持嵌套结构、数组、类型推断。

    Returns:
        解析后的 front matter 字典
    """
    return extract_metadata(markdown_text)


# ─── 配置块提取 ───

def extract_configs(markdown_text: str) -> List[Dict]:
    """
    提取文档中所有配置块（#!config + #!lang）。

    Args:
        markdown_text: Markdown 源文本

    Returns:
        配置块列表，每项包含：
        - type: "config" | "lang"
        - subtype: "json" | "toml" | "yaml" | "lua"
        - content: 原始文本
        - parsed: 解析后的 Python 对象（解析失败时为 None）
    """
    doc = parse(markdown_text)
    results = []

    for node in doc.children:
        if isinstance(node, ConfigBlock):
            item = {
                'type': 'config',
                'subtype': node.config_type,
                'content': node.content,
                'parsed': None,
            }
            try:
                item['parsed'] = parse_config_block(node.content, node.config_type)
            except Exception:
                pass
            results.append(item)
        elif isinstance(node, LangBlock):
            item = {
                'type': 'lang',
                'subtype': node.language,
                'content': node.content,
                'parsed': None,
            }
            try:
                item['parsed'] = parse_config_block(node.content, node.language)
            except Exception:
                pass
            results.append(item)

    return results


def extract_config_blocks(markdown_text: str) -> List[Dict]:
    """
    提取 #!config json 块（Actus 引擎自身配置）。

    Returns:
        配置块列表，每项包含 subtype/content/parsed
    """
    doc = parse(markdown_text)
    results = []

    for node in doc.children:
        if isinstance(node, ConfigBlock):
            item = {
                'subtype': node.config_type,
                'content': node.content,
                'parsed': None,
            }
            try:
                item['parsed'] = parse_config_block(node.content, node.config_type)
            except Exception:
                pass
            results.append(item)

    return results


def extract_lang_blocks(markdown_text: str, language: Optional[str] = None) -> List[Dict]:
    """
    提取 #!lang 块（嵌套语言配置），可按语言过滤。

    Args:
        markdown_text: Markdown 源文本
        language: 按语言过滤（如 "toml"、"yaml"、"lua"），None 表示全部

    Returns:
        配置块列表，每项包含 language/content/parsed
    """
    doc = parse(markdown_text)
    results = []

    for node in doc.children:
        if isinstance(node, LangBlock):
            if language is not None and node.language != language:
                continue
            item = {
                'language': node.language,
                'content': node.content,
                'parsed': None,
            }
            try:
                item['parsed'] = parse_config_block(node.content, node.language)
            except Exception:
                pass
            results.append(item)

    return results


def render_config(parsed: Any, language: str) -> str:
    """
    将 Python 对象渲染为指定格式的配置文本。

    Args:
        parsed: Python 对象（dict/list/str 等）
        language: "json" | "toml" | "yaml"

    Returns:
        配置文本
    """
    return _render_config(parsed, language)


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
        elif isinstance(node, ConfigBlock):
            word_count += len(node.content.split())
        elif isinstance(node, LangBlock):
            word_count += len(node.content.split())
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
        elif isinstance(node, ConfigBlock):
            lines.append(node.content)
        elif isinstance(node, LangBlock):
            lines.append(node.content)

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
        elif isinstance(node, ConfigBlock):
            lines.append('#+BEGIN_SRC ' + node.config_type)
            lines.append(node.content)
            lines.append('#+END_SRC')
            lines.append('')
        elif isinstance(node, LangBlock):
            lines.append('#+BEGIN_SRC ' + node.language)
            lines.append(node.content)
            lines.append('#+END_SRC')
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


__all__ = [
    'count_words',
    'extract_code_blocks',
    'extract_configs',
    'extract_config_blocks',
    'extract_lang_blocks',
    '_normalize_metadata',
    'extract_metadata',
    'extract_frontmatter',
    'find_headings',
    'generate_toc',
    'generate_toc_markdown',
    'render_config',
    'strip_markdown',
    'to_json',
    'to_org_mode',
    'to_plain_text'
]
