"""
Markdown 生成器

将 AST 节点逆序生成 Markdown 文本。
"""

from .parser import (
    Document, Heading, Paragraph, CodeBlock, BlockQuote,
    MdList, ListItem, Divider, InlineText
)


def _inline_to_text(node: InlineText) -> str:
    """行内节点 → Markdown 文本"""
    text = node.text
    if node.code:
        text = f'`{text}`'
    elif node.bold and node.italic:
        text = f'***{text}***'
    elif node.bold:
        text = f'**{text}**'
    elif node.italic:
        text = f'*{text}*'
    if node.strikethrough:
        text = f'~~{text}~~'
    if node.link:
        text = f'[{text}]({node.link})'
    return text


def _node_to_md(node, indent: int = 0) -> str:
    """AST 节点 → Markdown 文本（带缩进）"""
    prefix = '  ' * indent

    if isinstance(node, Document):
        return '\n\n'.join(_node_to_md(c, indent) for c in node.children)

    elif isinstance(node, Heading):
        children_text = ''.join(_inline_to_text(c) for c in node.children)
        return f'{prefix}{"#" * node.level} {children_text}'

    elif isinstance(node, Paragraph):
        children_text = ''.join(_inline_to_text(c) for c in node.children)
        return f'{prefix}{children_text}'

    elif isinstance(node, CodeBlock):
        fence = '```'
        lang_line = f'{fence}{node.language}\n' if node.language else f'{fence}\n'
        return f'{prefix}{lang_line}{node.code}\n{prefix}{fence}'

    elif isinstance(node, BlockQuote):
        quote_text = '\n\n'.join(_node_to_md(c, indent) for c in node.children)
        return f'{prefix}> {quote_text}'

    elif isinstance(node, MdList):
        lines = []
        for idx, item in enumerate(node.items, 1):
            marker = f'{idx}.' if node.ordered else '-'
            if item.checked is not None:
                mark = '[x]' if item.checked else '[ ]'
                item_text = ''.join(_inline_to_text(c) for c in item.children)
                lines.append(f'{prefix}{marker} [{mark}] {item_text}')
            else:
                item_text = ''.join(_inline_to_text(c) for c in item.children)
                lines.append(f'{prefix}{marker} {item_text}')
        return '\n'.join(lines)

    elif isinstance(node, ListItem):
        item_text = ''.join(_inline_to_text(c) for c in node.children)
        return item_text

    elif isinstance(node, Divider):
        return f'{prefix}---'

    return f'{prefix}{node}'


def generate(ast) -> str:
    """
    将 AST 生成 Markdown 文本。

    Args:
        ast: Document 或任意 AST 节点

    Returns:
        Markdown 文本

    Example:
        >>> from vools.md import parse, generate
        >>> ast = parse("# Hello\\n\\nWorld")
        >>> generate(ast)
        '# Hello\\n\\nWorld'
    """
    return _node_to_md(ast)


def generate_to_file(ast, filepath: str) -> str:
    """
    将 AST 生成 Markdown 文本并写入文件。

    Args:
        ast: AST 节点
        filepath: 输出文件路径

    Returns:
        写入的文件路径
    """
    md_text = generate(ast)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(md_text)
    return filepath


__all__ = [
    'generate',
    'generate_to_file'
]
