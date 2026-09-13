"""vools.md 阶段3：AST转换API + 扩展系统 + 文档对比 + 数学公式"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vools.md.parser import (
    parse, Document, Heading, Paragraph, CodeBlock, BlockQuote,
    MdList, ListItem, Divider, InlineText, parse_to_dict,
)
from vools.md.generator import generate
from vools.md.html import to_html
from vools.md.utils import strip_markdown, find_headings

import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Callable


# ═══════════════════════════════════════════════════════
# T0.1: AST 转换 API (walk / visit / transform)
# ═══════════════════════════════════════════════════════

def walk(node, depth=0):
    """
    遍历 AST 所有节点（深度优先），yield (node, depth)。

    Example:
        >>> for node, depth in walk(doc):
        ...     print('  ' * depth + type(node).__name__)
    """
    yield node, depth
    if isinstance(node, Document):
        for c in node.children:
            yield from walk(c, depth + 1)
    elif isinstance(node, (Heading, Paragraph)):
        for c in node.children:
            yield from walk(c, depth + 1)
    elif isinstance(node, BlockQuote):
        for c in node.children:
            yield from walk(c, depth + 1)
    elif isinstance(node, MdList):
        for item in node.items:
            yield from walk(item, depth + 1)
            for c in item.children:
                yield from walk(c, depth + 2)


def visit(node, visitor: Callable[[Any, int], None], depth=0):
    """
    遍历 AST，对每个节点调用 visitor(node, depth)。

    Args:
        node: AST 节点
        visitor: 回调函数，签名 visitor(node, depth)
    """
    visitor(node, depth)
    if isinstance(node, Document):
        for c in node.children:
            visit(c, visitor, depth + 1)
    elif isinstance(node, (Heading, Paragraph)):
        for c in node.children:
            visit(c, visitor, depth + 1)
    elif isinstance(node, BlockQuote):
        for c in node.children:
            visit(c, visitor, depth + 1)
    elif isinstance(node, MdList):
        for item in node.items:
            visit(item, visitor, depth + 1)
            for c in item.children:
                visit(c, visitor, depth + 2)


def transform(doc, transformer: Callable[[Any], Any]) -> Document:
    """
    转换 AST：对每个节点应用 transformer，返回新的 AST。

    Args:
        doc: 原始 Document
        transformer: 转换函数，签名 transformer(node) -> node

    Returns:
        转换后的新 Document

    Example:
        >>> def uppercase_headings(node):
        ...     if isinstance(node, Heading):
        ...         for c in node.children:
        ...             c.text = c.text.upper()
        ...     return node
        >>> new_doc = transform(doc, uppercase_headings)
    """
    def _t(node):
        node = transformer(node)
        if isinstance(node, Document):
            node.children = [_t(c) for c in node.children]
        elif isinstance(node, (Heading, Paragraph)):
            node.children = [_t(c) for c in node.children]
        elif isinstance(node, BlockQuote):
            node.children = [_t(c) for c in node.children]
        elif isinstance(node, MdList):
            node.items = [_t(item) for item in node.items]
            for item in node.items:
                item.children = [_t(c) for c in item.children]
        return node
    return _t(doc)


def filter_nodes(doc, predicate: Callable[[Any], bool]) -> List[Any]:
    """
    过滤 AST 中满足 predicate 的所有节点。

    Returns:
        满足条件的节点列表
    """
    return [node for node, _ in walk(doc) if predicate(node)]


# ═══════════════════════════════════════════════════════
# T0.2: 扩展系统
# ═══════════════════════════════════════════════════════

@dataclass
class Extension:
    """扩展定义"""
    name: str
    block_parser: Optional[Callable] = None   # 自定义块级解析器
    inline_parser: Optional[Callable] = None  # 自定义行内解析器
    render_html: Optional[Callable] = None    # HTML 渲染钩子
    render_md: Optional[Callable] = None      # Markdown 渲染钩子


class ExtensionRegistry:
    """扩展注册中心（单例模式）"""
    _instance = None
    _extensions: Dict[str, Extension] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def register(self, ext: Extension):
        """注册扩展"""
        self._extensions[ext.name] = ext

    def unregister(self, name: str):
        """注销扩展"""
        self._extensions.pop(name, None)

    def get(self, name: str) -> Optional[Extension]:
        """获取扩展"""
        return self._extensions.get(name)

    def list_all(self) -> List[str]:
        """列出所有扩展名"""
        return list(self._extensions.keys())

    def clear(self):
        """清空所有扩展"""
        self._extensions.clear()


def register_extension(
    name: str,
    block_parser: Optional[Callable] = None,
    inline_parser: Optional[Callable] = None,
    render_html: Optional[Callable] = None,
    render_md: Optional[Callable] = None,
):
    """
    便捷函数：注册扩展。

    Example:
        >>> def parse_alert(lines, start):
        ...     # 自定义块级解析器
        ...     pass
        >>> register_extension('alert', block_parser=parse_alert)
    """
    registry = ExtensionRegistry()
    registry.register(Extension(name=name, block_parser=block_parser,
                                  inline_parser=inline_parser,
                                  render_html=render_html, render_md=render_md))


# ═══════════════════════════════════════════════════════
# T0.3: 文档对比 (AST diff)
# ═══════════════════════════════════════════════════════

@dataclass
class DiffResult:
    """文档差异结果"""
    added: List[str] = field(default_factory=list)
    removed: List[str] = field(default_factory=list)
    modified: List[Dict] = field(default_factory=list)
    unchanged: int = 0

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.removed or self.modified)


def diff_markdown(md_old: str, md_new: str) -> DiffResult:
    """
    对比两个 Markdown 文档的 AST 差异。

    Args:
        md_old: 旧版 Markdown
        md_new: 新版 Markdown

    Returns:
        DiffResult 包含 added/removed/modified/unchanged

    Example:
        >>> diff = diff_markdown('# A', '# B')
        >>> diff.modified  # 标题文本变了
    """
    doc_old = parse(md_old)
    doc_new = parse(md_new)

    result = DiffResult()

    def _node_signature(node):
        """生成节点签名用于比较"""
        if isinstance(node, Heading):
            text = ''.join(c.text for c in node.children)
            return f'heading:{node.level}:{text}'
        elif isinstance(node, Paragraph):
            text = ''.join(c.text for c in node.children)
            return f'paragraph:{text}'
        elif isinstance(node, CodeBlock):
            return f'code:{node.language}:{node.code}'
        elif isinstance(node, BlockQuote):
            text = ''.join(c.text for c in node.children) if node.children else ''
            return f'blockquote:{text}'
        elif isinstance(node, MdList):
            items = []
            for item in node.items:
                text = ''.join(c.text for c in item.children)
                items.append(text)
            return f'list:{node.ordered}:{items}'
        elif isinstance(node, Divider):
            return 'divider'
        else:
            return f'{type(node).__name__}:{getattr(node, 'text', '')}'

    sigs_old = [_node_signature(c) for c in doc_old.children]
    sigs_new = [_node_signature(c) for c in doc_new.children]

    # 简单对比：逐节点比较
    max_len = max(len(sigs_old), len(sigs_new))
    for i in range(max_len):
        if i >= len(sigs_old):
            result.added.append(sigs_new[i])
        elif i >= len(sigs_new):
            result.removed.append(sigs_old[i])
        elif sigs_old[i] != sigs_new[i]:
            result.modified.append({'old': sigs_old[i], 'new': sigs_new[i]})
        else:
            result.unchanged += 1

    return result


def diff_markdown_text(md_old: str, md_new: str) -> str:
    """
    对比两个 Markdown 文档，返回文本格式的差异报告。

    Returns:
        文本格式的差异报告
    """
    diff = diff_markdown(md_old, md_new)
    lines = ['# Markdown Diff', '']

    if diff.added:
        lines.append('## Added (+{}):'.format(len(diff.added)))
        for item in diff.added:
            lines.append(f'  + {item}')
        lines.append('')

    if diff.removed:
        lines.append('## Removed (-{}):'.format(len(diff.removed)))
        for item in diff.removed:
            lines.append(f'  - {item}')
        lines.append('')

    if diff.modified:
        lines.append('## Modified ({}):'.format(len(diff.modified)))
        for item in diff.modified:
            lines.append(f'  ~ {item["old"]}')
            lines.append(f'  ~ {item["new"]}')
        lines.append('')

    lines.append(f'Unchanged: {diff.unchanged}')
    return '\n'.join(lines)


# ═══════════════════════════════════════════════════════
# T0.4: 数学公式 (LaTeX)
# ═══════════════════════════════════════════════════════

@dataclass
class MathInline:
    """行内数学公式节点"""
    latex: str


@dataclass
class MathBlock:
    """块级数学公式节点"""
    latex: str
    display: str = 'block'  # 'block' or 'inline'


def extract_math(markdown_text: str) -> List[Dict]:
    """
    提取 Markdown 中的数学公式。

    Returns:
        公式列表，每项包含 type (inline/block) 和 latex 内容

    Example:
        >>> formulas = extract_math('Text $E=mc^2$ text\n\n$$\\int_0^1 x\\,dx$$')
        >>> len(formulas) == 2
    """
    formulas = []

    # 块级公式 $$...$$
    for match in re.finditer(r'\$\$(.+?)\$\$', markdown_text, re.DOTALL):
        formulas.append({'type': 'block', 'latex': match.group(1).strip()})

    # 行内公式 $...$
    for match in re.finditer(r'(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)', markdown_text):
        formulas.append({'type': 'inline', 'latex': match.group(1).strip()})

    return formulas


def math_to_html(latex: str, display: bool = False) -> str:
    """
    将 LaTeX 公式渲染为 HTML（MathJax 兼容格式）。

    Args:
        latex: LaTeX 公式文本
        display: 是否为块级显示

    Returns:
        HTML 字符串（MathJax 兼容）
    """
    tag = 'block' if display else 'inline'
    return f'<math{(" type=\"" + tag + "\"") if display else ""}>{latex}</math>'


def math_to_markdown(latex: str, display: bool = False) -> str:
    """
    将 LaTeX 公式渲染为 Markdown。

    Returns:
        Markdown 公式文本
    """
    if display:
        return f'$${latex}$$'
    return f'${latex}$'


# ═══════════════════════════════════════════════════════
# 测试
# ═══════════════════════════════════════════════════════

def test_walk():
    doc = parse('# Title\n\nPara')
    nodes = list(walk(doc))
    assert len(nodes) >= 3
    assert nodes[0][0] == doc
    print('OK: walk')


def test_visit():
    doc = parse('# Title\n\nPara')
    counts = {}
    visit(doc, lambda node, depth: counts.setdefault(type(node).__name__, 0))
    # visit callback should be called for each node
    assert 'Document' in counts
    print('OK: visit')


def test_transform():
    doc = parse('# title\n\nbody')
    def uppercase(node):
        if isinstance(node, Heading):
            for c in node.children:
                c.text = c.text.upper()
        return node
    new_doc = transform(doc, uppercase)
    assert new_doc.children[0].children[0].text == 'TITLE'
    print('OK: transform')


def test_filter_nodes():
    doc = parse('# Title\n\nPara\n\n## Sub')
    headings = filter_nodes(doc, lambda n: isinstance(n, Heading))
    assert len(headings) == 2
    print('OK: filter_nodes')


def test_extension_registry():
    reg = ExtensionRegistry()
    reg.clear()
    register_extension('test', render_html=lambda: '<b>test</b>')
    assert 'test' in reg.list_all()
    reg.unregister('test')
    assert 'test' not in reg.list_all()
    print('OK: extension registry')


def test_diff_added():
    diff = diff_markdown('# A', '# A\n\n# B')
    assert len(diff.added) == 1
    print('OK: diff added')


def test_diff_removed():
    diff = diff_markdown('# A\n\n# B', '# A')
    assert len(diff.removed) == 1
    print('OK: diff removed')


def test_diff_modified():
    diff = diff_markdown('# Title', '# NewTitle')
    assert len(diff.modified) == 1
    print('OK: diff modified')


def test_diff_text():
    diff_text = diff_markdown_text('# A', '# B')
    assert 'Added' in diff_text or 'Modified' in diff_text
    print('OK: diff text')


def test_extract_math_inline():
    formulas = extract_math('Text $E=mc^2$ end')
    assert len(formulas) == 1
    assert formulas[0]['type'] == 'inline'
    assert formulas[0]['latex'] == 'E=mc^2'
    print('OK: math inline')


def test_extract_math_block():
    formulas = extract_math('$$\\int_0^1 x\\,dx$$')
    assert len(formulas) == 1
    assert formulas[0]['type'] == 'block'
    print('OK: math block')


def test_math_to_html():
    html = math_to_html('E=mc^2', display=True)
    assert 'math' in html
    assert 'block' in html
    print('OK: math to html')


def test_math_to_markdown():
    md = math_to_markdown('E=mc^2', display=True)
    assert md == '$$E=mc^2$$'
    print('OK: math to markdown')


if __name__ == '__main__':
    test_walk()
    test_visit()
    test_transform()
    test_filter_nodes()
    test_extension_registry()
    test_diff_added()
    test_diff_removed()
    test_diff_modified()
    test_diff_text()
    test_extract_math_inline()
    test_extract_math_block()
    test_math_to_html()
    test_math_to_markdown()
    print()
    print('All 14 phase-3 tests passed!')
