"""vools.md 阶段2集成测试：多格式转换 + CLI + 高级解析"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vools.md import (
    parse, generate, to_html, to_json, to_org_mode, to_plain_text,
    extract_metadata, generate_toc, extract_code_blocks, strip_markdown,
)


def test_json_serialization():
    md = "# Title\n\nSome text."
    json_str = to_json(md)
    data = json.loads(json_str)
    assert data['type'] == 'document'
    assert len(data['children']) == 2
    assert data['children'][0]['type'] == 'heading'
    assert data['children'][0]['level'] == 1


def test_org_mode_heading():
    md = "# Title\n## Subtitle"
    org = to_org_mode(md)
    assert '# Title' in org
    assert '## Subtitle' in org


def test_org_mode_code_block():
    md = "```python\nprint(1)\n```"
    org = to_org_mode(md)
    assert '#+BEGIN_SRC python' in org
    assert 'print(1)' in org
    assert '#+END_SRC' in org


def test_org_mode_list():
    md = "- item1\n- item2"
    org = to_org_mode(md)
    assert '- item1' in org
    assert '- item2' in org


def test_plain_text():
    md = "# **Bold** Title"
    text = to_plain_text(md)
    assert 'Bold' in text
    assert 'Title' in text


def test_cli_md2html():
    from vools.md.cli import cmd_md2html
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
        f.write('# Hello')
        md_path = f.name
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
        html_path = f.name
    class Args: pass
    args = Args()
    args.input = md_path
    args.output = html_path
    cmd_md2html(args)
    with open(html_path, 'r', encoding='utf-8') as f:
        content = f.read()
    assert '<h1>Hello</h1>' in content
    os.unlink(md_path)
    os.unlink(html_path)


def test_cli_md2json():
    from vools.md.cli import cmd_md2json
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
        f.write('# Hello')
        md_path = f.name
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
        json_path = f.name
    class Args: pass
    args = Args()
    args.input = md_path
    args.output = json_path
    args.indent = 2
    cmd_md2json(args)
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    assert data['type'] == 'document'
    os.unlink(md_path)
    os.unlink(json_path)


def test_cli_md2org():
    from vools.md.cli import cmd_md2org
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
        f.write('# Hello')
        md_path = f.name
    with tempfile.NamedTemporaryFile(mode='w', suffix='.org', delete=False, encoding='utf-8') as f:
        org_path = f.name
    class Args: pass
    args = Args()
    args.input = md_path
    args.output = org_path
    cmd_md2org(args)
    with open(org_path, 'r', encoding='utf-8') as f:
        content = f.read()
    assert '# Hello' in content
    os.unlink(md_path)
    os.unlink(org_path)


def test_advanced_inline_html():
    from vools.md.parser import _parse_inline, InlineText
    result = _parse_inline('text <br> more')
    assert any(n.html == 'br' for n in result)


def test_advanced_inline_auto_link():
    from vools.md.parser import _parse_inline, InlineText
    result = _parse_inline('Visit <https://example.com>')
    assert any(n.link == 'https://example.com' for n in result)


def test_advanced_inline_ref_link():
    from vools.md.parser import _parse_inline, InlineText
    result = _parse_inline('See [docs][ref1]')
    assert any(n.link == '#ref:ref1' for n in result)


def test_round_trip_complex():
    md = "# Title\n\n**bold** and *italic*.\n\n```python\nx=1```\n\n- a\n- b"
    ast = parse(md)
    generated = generate(ast)
    assert 'Title' in generated
    assert 'bold' in generated


def test_full_pipeline():
    """端到端：解析 → 生成 → HTML → JSON → Org → 纯文本"""
    md = "# Project\n\nA **summary**.\n\n```py\npass```\n\n- item"
    ast = parse(md)
    assert generate(ast)
    assert to_html(ast)
    assert to_json(md)
    assert to_org_mode(md)
    assert to_plain_text(md)
