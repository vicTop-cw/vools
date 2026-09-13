"""
MD → HTML 转换器

将 AST 或 Markdown 文本转换为 HTML。
"""

from .parser import (
    Document, Heading, Paragraph, CodeBlock, BlockQuote,
    MdList, ListItem, Divider, InlineText, parse
)


def _inline_to_html(node: InlineText) -> str:
    """行内节点 → HTML"""
    text = node.text

    if node.code:
        return f'<code>{_escape(text)}</code>'

    if node.link:
        return f'<a href="{_escape(node.link)}">{_escape(text)}</a>'

    result = _escape(text)
    if node.bold:
        result = f'<strong>{result}</strong>'
    if node.italic:
        result = f'<em>{result}</em>'
    if node.strikethrough:
        result = f'<del>{result}</del>'
    return result


def _escape(text: str) -> str:
    """HTML 转义"""
    return (text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;'))


def _node_to_html(node, indent: int = 0) -> str:
    """AST 节点 → HTML"""
    pad = '\n' + '  ' * indent

    if isinstance(node, Document):
        body = '\n'.join(_node_to_html(c, indent) for c in node.children)
        return f'<div class="markdown-body">{pad}{body}{pad}</div>'

    elif isinstance(node, Heading):
        children_html = ''.join(_inline_to_html(c) for c in node.children)
        tag = f'h{node.level}'
        return f'<{tag}>{children_html}</{tag}>'

    elif isinstance(node, Paragraph):
        children_html = ''.join(_inline_to_html(c) for c in node.children)
        return f'<p>{children_html}</p>'

    elif isinstance(node, CodeBlock):
        lang_class = f' class="language-{_escape(node.language)}"' if node.language else ''
        return (f'<pre><code{lang_class}>'
                f'{_escape(node.code)}</code></pre>')

    elif isinstance(node, BlockQuote):
        children_html = '\n'.join(_node_to_html(c, indent) for c in node.children)
        return f'<blockquote>\n{children_html}\n</blockquote>'

    elif isinstance(node, MdList):
        if node.ordered:
            open_tag, close_tag = '<ol>', '</ol>'
        else:
            open_tag, close_tag = '<ul>', '</ul>'
        items_html = '\n'.join(_list_item_to_html(it, indent) for it in node.items)
        return f'{open_tag}\n{items_html}\n{close_tag}'

    elif isinstance(node, ListItem):
        return _list_item_to_html(node, indent)

    elif isinstance(node, Divider):
        return '<hr />'

    return f'<!-- unknown node: {type(node).__name__} -->'


def _list_item_to_html(item: ListItem, indent: int) -> str:
    """列表项 → HTML"""
    children_html = ''.join(_inline_to_html(c) for c in item.children)
    if item.checked is not None:
        checkbox = (
            '<input type="checkbox" checked disabled /> '
            if item.checked
            else '<input type="checkbox" disabled /> '
        )
        return f'<li>{checkbox}{children_html}</li>'
    return f'<li>{children_html}</li>'


def to_html(source) -> str:
    """
    将 Markdown 文本或 AST 转换为 HTML。

    Args:
        source: Markdown 文本 (str) 或 AST 节点 (Document/Heading/...)

    Returns:
        HTML 字符串

    Example:
        >>> from vools.md import to_html
        >>> to_html("# Hello")
        '<h1>Hello</h1>'
    """
    if isinstance(source, str):
        ast = parse(source)
    else:
        ast = source
    return _node_to_html(ast)


def to_html_file(source, filepath: str) -> str:
    """
    将 Markdown 文本或 AST 转换为 HTML 并写入文件。

    Args:
        source: Markdown 文本或 AST 节点
        filepath: 输出文件路径

    Returns:
        写入的文件路径
    """
    html = to_html(source)
    # 包裹完整 HTML 文档
    full_html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Markdown Document</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; max-width: 800px; margin: 2em auto; padding: 0 1em; }}
        code {{ background: #f0f0f0; padding: 2px 4px; border-radius: 3px; }}
        pre {{ background: #f6f8fa; padding: 1em; border-radius: 6px; overflow-x: auto; }}
        blockquote {{ border-left: 4px solid #dfe2e5; padding-left: 1em; color: #6a737d; }}
    </style>
</head>
<body>
{html}
</body>
</html>'''
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(full_html)
    return filepath
