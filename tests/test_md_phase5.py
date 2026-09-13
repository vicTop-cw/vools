"""vools.md 阶段5测试：从 advanced 模块导入并验证所有功能"""
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vools.md.parser import parse
from vools.md.advanced import (
    get_theme, list_themes, render_html_with_theme, export_html_theme,
    ast_to_tree, ast_to_mermaid,
    benchmark_parse, benchmark_generate, benchmark_to_html,
    benchmark_full_pipeline, benchmark_report,
    stream_parse, stream_parse_stats,
    extract_cross_references, resolve_cross_references,
    generate_reference_table, CrossReference,
)


def test_get_theme():
    t = get_theme('github')
    assert t['body_font']
    assert len(list_themes()) >= 4
    print('OK: theme')


def test_render_html_theme():
    html = render_html_with_theme('# Hello', 'github')
    assert '<h1>Hello</h1>' in html
    print('OK: render html theme')


def test_export_html_theme():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
        path = f.name
    result = export_html_theme('# Hello', 'minimal', path)
    assert result == path
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    assert '<h1>Hello</h1>' in content
    os.unlink(path)
    print('OK: export html theme')


def test_ast_to_tree():
    doc = parse('# Hello\n\nWorld')
    tree = ast_to_tree(doc)
    assert 'Document' in tree
    assert 'Heading' in tree
    assert 'Paragraph' in tree
    print('OK: ast to tree')


def test_ast_to_mermaid():
    doc = parse('# Hello\n\nWorld')
    mmd = ast_to_mermaid(doc)
    assert 'graph TD' in mmd
    assert 'Document' in mmd
    print('OK: ast to mermaid')


def test_benchmark_parse():
    r = benchmark_parse('# Hello\n\nWorld', iterations=10)
    assert r['avg_ms'] > 0
    assert r['iterations'] == 10
    print('OK: benchmark parse')


def test_benchmark_generate():
    doc = parse('# Hello\n\nWorld')
    r = benchmark_generate(doc, iterations=10)
    assert r['avg_ms'] > 0
    print('OK: benchmark generate')


def test_benchmark_to_html():
    r = benchmark_to_html('# Hello', iterations=10)
    assert r['avg_ms'] > 0
    print('OK: benchmark to html')


def test_benchmark_full_pipeline():
    r = benchmark_full_pipeline('# Hello\n\nWorld', iterations=5)
    assert r['avg_ms'] > 0
    print('OK: benchmark full pipeline')


def test_benchmark_report():
    report = benchmark_report('# Hello\n\nWorld', iterations=10)
    assert 'Performance Benchmark' in report
    assert 'Parse' in report
    print('OK: benchmark report')


def test_stream_parse_stats():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
        f.write('# A\n\nText\n\n# B\n\nMore\n')
        path = f.name
    stats = stream_parse_stats(path, chunk_size=10)
    assert stats['chunk_count'] >= 1
    assert stats['total_nodes'] > 0
    os.unlink(path)
    print('OK: stream parse stats')


def test_extract_cross_refs():
    md = 'See [docs][ref1] and [notes]'
    refs = extract_cross_references(md)
    assert len(refs) >= 2
    print('OK: extract cross refs')


def test_resolve_cross_refs():
    md = 'See [docs][ref1]'
    refs = resolve_cross_references(md, {'ref1': 'https://example.com'})
    assert refs[0].resolved == True
    assert refs[0].target == 'https://example.com'
    print('OK: resolve cross refs')


def test_generate_ref_table():
    refs = [
        CrossReference('ref1', 'docs', 1, True, 'https://example.com'),
        CrossReference('ref2', 'notes', 2, False),
    ]
    table = generate_reference_table(refs)
    assert 'References' in table
    assert 'docs' in table
    assert 'notes' in table
    print('OK: generate ref table')


if __name__ == '__main__':
    test_get_theme()
    test_render_html_theme()
    test_export_html_theme()
    test_ast_to_tree()
    test_ast_to_mermaid()
    test_benchmark_parse()
    test_benchmark_generate()
    test_benchmark_to_html()
    test_benchmark_full_pipeline()
    test_benchmark_report()
    test_stream_parse_stats()
    test_extract_cross_refs()
    test_resolve_cross_refs()
    test_generate_ref_table()
    print()
    print('All 14 phase-5 tests passed!')
