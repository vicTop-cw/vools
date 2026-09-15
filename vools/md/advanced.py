"""
vools.md 高级功能模块

包含：
- 渲染主题系统（github / gitlab / stackoverflow / minimal）
- AST 可视化（树形文本 / Mermaid 流程图）
- 性能基准测试
- 流式解析
- 交叉引用解析
"""
import re, time, os
from typing import List, Dict, Optional, Iterator
from dataclasses import dataclass

from .parser import (
    parse, Document, Heading, Paragraph, CodeBlock, BlockQuote,
    MdList, ListItem, Divider, InlineText,
)
from .generator import generate
from .html import to_html


# ═══════════════════════════════════════════════════════
# T0.1: 渲染主题系统
# ═══════════════════════════════════════════════════════

THEMES = {
    'github': {
        'body_font': '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
        'heading_color': '#24292e',
        'code_bg': '#f6f8fa',
        'code_border': '#e1e4e8',
        'quote_border': '#dfe2e5',
        'quote_color': '#6a737d',
        'link_color': '#0366d6',
        'max_width': '800px',
    },
    'gitlab': {
        'body_font': '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
        'heading_color': '#303030',
        'code_bg': '#f4f4f4',
        'code_border': '#dcdcde',
        'quote_border': '#dcdcde',
        'quote_color': '#6c6c6c',
        'link_color': '#1f6feb',
        'max_width': '720px',
    },
    'stackoverflow': {
        'body_font': 'Arial, "Helvetica Neue", sans-serif',
        'heading_color': '#555',
        'code_bg': '#f8f8f8',
        'code_border': '#ddd',
        'quote_border': '#ddd',
        'quote_color': '#888',
        'link_color': '#0a7d33',
        'max_width': '980px',
    },
    'minimal': {
        'body_font': 'Georgia, serif',
        'heading_color': '#111',
        'code_bg': '#f5f5f5',
        'code_border': '#ddd',
        'quote_border': '#ccc',
        'quote_color': '#666',
        'link_color': '#0066cc',
        'max_width': '680px',
    },
}


def get_theme(name: str) -> Dict:
    """
    获取主题配置。

    Args:
        name: 主题名称 ('github' / 'gitlab' / 'stackoverflow' / 'minimal')

    Returns:
        主题配置字典

    Raises:
        ValueError: 未知主题名称

    Example:
        >>> t = get_theme('github')
        >>> t['link_color']
        '#0366d6'
    """
    if name not in THEMES:
        raise ValueError(f'Unknown theme: {name}. Available: {list(THEMES.keys())}')
    return THEMES[name]


def list_themes() -> List[str]:
    """列出所有可用主题。"""
    return list(THEMES.keys())


def render_html_with_theme(markdown_text: str, theme: str = 'github') -> str:
    """
    使用指定主题渲染 Markdown 为完整 HTML。

    Args:
        markdown_text: Markdown 源文本
        theme: 主题名称

    Returns:
        完整 HTML 文档字符串

    Example:
        >>> html = render_html_with_theme('# Hello', 'github')
        >>> '<h1>Hello</h1>' in html
        True
    """
    t = get_theme(theme)
    body_html = to_html(markdown_text)

    css = (
        f'body {{ font-family: {t["body_font"]}; max-width: {t["max_width"]};'
        f'margin: 2em auto; padding: 0 1em; color: #333; }}'
        f'h1, h2, h3, h4, h5, h6 {{ color: {t["heading_color"]};'
        f'border-bottom: 1px solid {t["code_border"]}; padding-bottom: 0.3em; }}'
        f'code {{ background: {t["code_bg"]}; padding: 2px 6px; border-radius: 3px;'
        f'font-family: "Consolas", monospace; font-size: 0.9em; }}'
        f'pre {{ background: {t["code_bg"]}; border: 1px solid {t["code_border"]};'
        f'padding: 1em; border-radius: 6px; overflow-x: auto; }}'
        f'pre code {{ background: none; padding: 0; }}'
        f'blockquote {{ border-left: 4px solid {t["quote_border"]};'
        f'padding-left: 1em; color: {t["quote_color"]}; margin-left: 0; }}'
        f'a {{ color: {t["link_color"]}; }}'
        f'table {{ border-collapse: collapse; width: 100%; }}'
        f'th, td {{ border: 1px solid {t["code_border"]}; padding: 6px 13px; }}'
        f'th {{ background: {t["code_bg"]}; }}'
    )

    return (
        '<!DOCTYPE html>\n'
        '<html lang="zh-CN">\n'
        '<head>\n'
        '    <meta charset="UTF-8">\n'
        '    <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        '    <title>Markdown Document</title>\n'
        f'    <style>{css}</style>\n'
        '</head>\n'
        '<body>\n'
        f'{body_html}\n'
        '</body>\n'
        '</html>'
    )


def export_html_theme(markdown_text: str, theme: str, filepath: str) -> str:
    """
    导出为 HTML 文件。

    Args:
        markdown_text: Markdown 源文本
        theme: 主题名称
        filepath: 输出文件路径

    Returns:
        写入的文件路径
    """
    html = render_html_with_theme(markdown_text, theme)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html)
    return filepath


# ═══════════════════════════════════════════════════════
# T0.2: AST 可视化
# ═══════════════════════════════════════════════════════

def ast_to_tree(ast, indent: str = '') -> str:
    """
    将 AST 渲染为树形文本。

    Args:
        ast: AST 节点
        indent: 缩进字符串

    Returns:
        树形文本

    Example:
        >>> print(ast_to_tree(parse('# Hello')))
        Document(1 children)
          └── Heading(level=1, text='Hello')
              └── InlineText('Hello')
    """
    lines = []

    def _render(node, prefix, is_last):
        connector = '└── ' if is_last else '├── '
        label = _node_label(node)
        lines.append(f'{prefix}{connector}{label}')
        child_prefix = prefix + ('    ' if is_last else '│   ')

        children = _get_children(node)
        for i, child in enumerate(children):
            _render(child, child_prefix, i == len(children) - 1)

    def _node_label(node):
        if isinstance(node, Document):
            return f'Document({len(node.children)} children)'
        elif isinstance(node, Heading):
            text = ''.join(c.text for c in node.children)
            return f'Heading(level={node.level}, text={text!r})'
        elif isinstance(node, Paragraph):
            text = ''.join(c.text for c in node.children)
            return f'Paragraph({text!r})'
        elif isinstance(node, CodeBlock):
            return f'CodeBlock(lang={node.language!r}, lines={len(node.code.split(chr(10)))})'
        elif isinstance(node, BlockQuote):
            return f'BlockQuote({len(node.children)} children)'
        elif isinstance(node, MdList):
            return f'List(ordered={node.ordered}, items={len(node.items)})'
        elif isinstance(node, ListItem):
            text = ''.join(c.text for c in node.children)
            return f'ListItem({text!r})'
        elif isinstance(node, Divider):
            return 'Divider'
        elif isinstance(node, InlineText):
            tags = []
            if node.bold: tags.append('B')
            if node.italic: tags.append('I')
            if node.code: tags.append('C')
            if node.link: tags.append(f'L:{node.link}')
            tag_str = f'[{''.join(tags)}]' if tags else ''
            return f'InlineText{tag_str}({node.text!r})'
        else:
            return type(node).__name__

    def _get_children(node):
        if isinstance(node, Document):
            return node.children
        elif isinstance(node, (Heading, Paragraph)):
            return node.children
        elif isinstance(node, BlockQuote):
            return node.children
        elif isinstance(node, MdList):
            return node.items
        elif isinstance(node, ListItem):
            return node.children
        else:
            return []

    label = _node_label(ast)
    lines.append(label)
    children = _get_children(ast)
    for i, child in enumerate(children):
        _render(child, '  ', i == len(children) - 1)

    return '\n'.join(lines)


def ast_to_mermaid(ast) -> str:
    """
    将 AST 渲染为 Mermaid 流程图。

    Args:
        ast: AST 节点

    Returns:
        Mermaid 图表文本

    Example:
        >>> mmd = ast_to_mermaid(parse('# Hello'))
        >>> 'graph TD' in mmd
        True
    """
    lines = ['graph TD']

    def _render(node, node_id):
        label = _node_short_label(node)
        lines.append(f'    {node_id}["{label}"]')

        children = _get_children_mermaid(node)
        for i, child in enumerate(children):
            child_id = f'{node_id}_{i}'
            lines.append(f'    {node_id} --> {child_id}')
            _render(child, child_id)

    def _node_short_label(node):
        if isinstance(node, Document):
            return 'Document'
        elif isinstance(node, Heading):
            text = ''.join(c.text for c in node.children)[:20]
            return f'H{node.level}: {text}'
        elif isinstance(node, Paragraph):
            text = ''.join(c.text for c in node.children)[:20]
            return f'Para: {text}'
        elif isinstance(node, CodeBlock):
            return f'Code({node.language})'
        elif isinstance(node, BlockQuote):
            return 'Quote'
        elif isinstance(node, MdList):
            return f'List({len(node.items)})'
        elif isinstance(node, Divider):
            return 'Divider'
        else:
            return type(node).__name__

    def _get_children_mermaid(node):
        if isinstance(node, Document):
            return node.children
        elif isinstance(node, (Heading, Paragraph, ListItem)):
            return node.children
        elif isinstance(node, BlockQuote):
            return node.children
        elif isinstance(node, MdList):
            return node.items
        else:
            return []

    _render(ast, 'root')
    return '\n'.join(lines)


# ═══════════════════════════════════════════════════════
# T0.3: 性能基准
# ═══════════════════════════════════════════════════════

def benchmark_parse(text: str, iterations: int = 100) -> Dict:
    """
    基准测试：解析性能。

    Args:
        text: 要解析的 Markdown 文本
        iterations: 迭代次数

    Returns:
        包含 avg_ms / min_ms / max_ms / total_ms 的字典
    """
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        parse(text)
        times.append((time.perf_counter() - start) * 1000)
    return {
        'operation': 'parse',
        'iterations': iterations,
        'text_length': len(text),
        'avg_ms': sum(times) / len(times),
        'min_ms': min(times),
        'max_ms': max(times),
        'total_ms': sum(times),
    }


def benchmark_generate(ast, iterations: int = 100) -> Dict:
    """基准测试：生成性能。"""
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        generate(ast)
        times.append((time.perf_counter() - start) * 1000)
    return {
        'operation': 'generate',
        'iterations': iterations,
        'avg_ms': sum(times) / len(times),
        'min_ms': min(times),
        'max_ms': max(times),
        'total_ms': sum(times),
    }


def benchmark_to_html(text: str, iterations: int = 100) -> Dict:
    """基准测试：HTML 转换性能。"""
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        to_html(text)
        times.append((time.perf_counter() - start) * 1000)
    return {
        'operation': 'to_html',
        'iterations': iterations,
        'text_length': len(text),
        'avg_ms': sum(times) / len(times),
        'min_ms': min(times),
        'max_ms': max(times),
        'total_ms': sum(times),
    }


def benchmark_full_pipeline(text: str, iterations: int = 50) -> Dict:
    """基准测试：完整流水线（解析 → 生成 → HTML）。"""
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        ast = parse(text)
        generate(ast)
        to_html(text)
        times.append((time.perf_counter() - start) * 1000)
    return {
        'operation': 'full_pipeline',
        'iterations': iterations,
        'text_length': len(text),
        'avg_ms': sum(times) / len(times),
        'min_ms': min(times),
        'max_ms': max(times),
        'total_ms': sum(times),
    }


def benchmark_report(text: str, iterations: int = 100) -> str:
    """
    生成完整的性能基准报告。

    Args:
        text: 要测试的 Markdown 文本
        iterations: 迭代次数

    Returns:
        Markdown 格式的性能报告
    """
    parse_r = benchmark_parse(text, iterations)
    ast = parse(text)
    gen_r = benchmark_generate(ast, iterations)
    html_r = benchmark_to_html(text, iterations)
    full_r = benchmark_full_pipeline(text, iterations // 2)

    lines = [
        '# Markdown Performance Benchmark', '',
        f'**Text length:** {len(text)} chars',
        f'**Iterations:** {iterations}', '',
        '## Results', '',
        '| Operation | Avg (ms) | Min (ms) | Max (ms) | Total (ms) |',
        '|-----------|----------|----------|----------|------------|',
        f'| Parse | {parse_r["avg_ms"]:.3f} | {parse_r["min_ms"]:.3f} | {parse_r["max_ms"]:.3f} | {parse_r["total_ms"]:.1f} |',
        f'| Generate | {gen_r["avg_ms"]:.3f} | {gen_r["min_ms"]:.3f} | {gen_r["max_ms"]:.3f} | {gen_r["total_ms"]:.1f} |',
        f'| To HTML | {html_r["avg_ms"]:.3f} | {html_r["min_ms"]:.3f} | {html_r["max_ms"]:.3f} | {html_r["total_ms"]:.1f} |',
        f'| Full Pipeline | {full_r["avg_ms"]:.3f} | {full_r["min_ms"]:.3f} | {full_r["max_ms"]:.3f} | {full_r["total_ms"]:.1f} |',
    ]
    return '\n'.join(lines)


# ═══════════════════════════════════════════════════════
# T0.4: 流式解析
# ═══════════════════════════════════════════════════════

def stream_parse(
    file_path: str,
    chunk_size: int = 8192,
) -> Iterator[Dict]:
    """
    流式解析大文件，分块处理。

    Args:
        file_path: 文件路径
        chunk_size: 每块大小（字节）

    Yields:
        每个块的解析结果（元数据 + 块索引）

    Example:
        >>> for chunk in stream_parse('large.md', chunk_size=4096):
        ...     print(chunk['chunk_index'], chunk['node_count'])
    """
    chunk_idx = 0
    buffer = ''

    with open(file_path, 'r', encoding='utf-8') as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                if buffer:
                    doc = parse(buffer)
                    yield {
                        'chunk_index': chunk_idx,
                        'is_last': True,
                        'node_count': len(doc.children),
                        'text_length': len(buffer),
                    }
                break

            buffer += chunk
            last_newline = buffer.rfind('\n')
            if last_newline > 0:
                line_buffer = buffer[:last_newline + 1]
                buffer = buffer[last_newline + 1:]

                doc = parse(line_buffer)
                yield {
                    'chunk_index': chunk_idx,
                    'is_last': False,
                    'node_count': len(doc.children),
                    'text_length': len(line_buffer),
                }
                chunk_idx += 1


def stream_parse_stats(file_path: str, chunk_size: int = 8192) -> Dict:
    """
    流式解析并返回统计信息。

    Returns:
        包含 chunk_count / total_nodes / total_chars 的字典
    """
    stats = {'chunk_count': 0, 'total_nodes': 0, 'total_chars': 0}

    for chunk in stream_parse(file_path, chunk_size):
        stats['chunk_count'] += 1
        stats['total_nodes'] += chunk['node_count']
        stats['total_chars'] += chunk['text_length']

    return stats


# ═══════════════════════════════════════════════════════
# T0.5: 交叉引用解析
# ═══════════════════════════════════════════════════════

@dataclass
class CrossReference:
    """交叉引用"""
    ref_label: str
    text: str
    line: int
    resolved: bool = False
    target: Optional[str] = None


def extract_cross_references(markdown_text: str) -> List[CrossReference]:
    """
    提取所有交叉引用。

    格式：[text][ref] 或 [text]

    Returns:
        CrossReference 列表
    """
    refs = []
    lines = markdown_text.split('\n')

    for i, line in enumerate(lines, 1):
        for match in re.finditer(r'\[([^\]]+)\]\[([^\]]+)\]', line):
            refs.append(CrossReference(
                ref_label=match.group(2),
                text=match.group(1),
                line=i,
            ))

        for match in re.finditer(r'(?<!\[)\[([^\]]+)\](?!\()', line):
            text = match.group(1)
            if text.lower() not in ('', 'http', 'https'):
                refs.append(CrossReference(
                    ref_label=text.lower(),
                    text=text,
                    line=i,
                ))

    return refs


def resolve_cross_references(
    markdown_text: str,
    ref_definitions: Optional[Dict[str, str]] = None,
) -> List[CrossReference]:
    """
    解析交叉引用，匹配定义。

    Args:
        markdown_text: Markdown 源文本
        ref_definitions: 手动提供的引用定义 {'label': 'target_url'}

    Returns:
        已解析的 CrossReference 列表
    """
    refs = extract_cross_references(markdown_text)

    if ref_definitions is None:
        ref_definitions = {}
        for match in re.finditer(r'^\[\^([^\]]+)\]:\s*(.+)$', markdown_text, re.MULTILINE):
            ref_definitions[match.group(1)] = match.group(2).strip()

    for ref in refs:
        if ref.ref_label in ref_definitions:
            ref.resolved = True
            ref.target = ref_definitions[ref.ref_label]

    return refs


def generate_reference_table(refs: List[CrossReference]) -> str:
    """
    生成引用表。

    Returns:
        Markdown 格式的引用表
    """
    lines = ['## References', '', '| Text | Reference | Resolved | Target |',
             '|------|-----------|----------|--------|']

    for ref in refs:
        resolved = '✅' if ref.resolved else '❌'
        target = ref.target or '—'
        lines.append(f'| {ref.text} | `{ref.ref_label}` | {resolved} | {target} |')

    return '\n'.join(lines)


__all__ = [
    'CrossReference',
    'THEMES',
    'ast_to_mermaid',
    'ast_to_tree',
    'benchmark_full_pipeline',
    'benchmark_generate',
    'benchmark_parse',
    'benchmark_report',
    'benchmark_to_html',
    'export_html_theme',
    'extract_cross_references',
    'generate_reference_table',
    'get_theme',
    'list_themes',
    'render_html_with_theme',
    'resolve_cross_references',
    'stream_parse',
    'stream_parse_stats'
]
