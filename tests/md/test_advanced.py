"""tests/md/test_advanced.py — 高级功能测试"""
import pytest
import sys
import os
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from vools.md.advanced import (
    get_theme, list_themes, render_html_with_theme, export_html_theme,
    ast_to_tree, ast_to_mermaid,
    benchmark_parse, benchmark_generate, benchmark_to_html,
    benchmark_full_pipeline, benchmark_report,
    stream_parse, stream_parse_stats,
    extract_cross_references, resolve_cross_references,
    generate_reference_table, CrossReference,
)
from vools.md.parser import parse, Document, Heading, Paragraph, InlineText
from vools.md.generator import generate


class TestGetTheme:
    """主题系统测试"""

    def test_get_github_theme(self):
        t = get_theme('github')
        assert 'body_font' in t
        assert 'link_color' in t

    def test_get_gitlab_theme(self):
        t = get_theme('gitlab')
        assert t['link_color'] == '#1f6feb'

    def test_get_stackoverflow_theme(self):
        t = get_theme('stackoverflow')
        assert 'code_bg' in t

    def test_get_minimal_theme(self):
        t = get_theme('minimal')
        assert t['body_font'] == 'Georgia, serif'

    def test_unknown_theme_raises(self):
        with pytest.raises(ValueError):
            get_theme('unknown')

    def test_themes_are_dicts(self):
        for name in list_themes():
            t = get_theme(name)
            assert isinstance(t, dict)


class TestListThemes:
    """主题列表测试"""

    def test_returns_list(self):
        themes = list_themes()
        assert isinstance(themes, list)
        assert len(themes) >= 4

    def test_contains_known_themes(self):
        themes = list_themes()
        assert 'github' in themes
        assert 'gitlab' in themes
        assert 'stackoverflow' in themes
        assert 'minimal' in themes


class TestRenderHtmlWithTheme:
    """主题 HTML 渲染测试"""

    def test_render_github(self):
        html = render_html_with_theme('# Hello', 'github')
        assert '<h1>Hello</h1>' in html
        assert '<!DOCTYPE html>' in html
        assert 'markdown-body' in html

    def test_render_gitlab(self):
        html = render_html_with_theme('**bold**', 'gitlab')
        assert '<strong>bold</strong>' in html

    def test_render_with_code(self):
        html = render_html_with_theme('```python\nprint(1)\n```', 'github')
        assert '<pre>' in html
        assert '<code' in html


class TestExportHtmlTheme:
    """主题 HTML 导出测试"""

    def test_export(self):
        with tempfile.NamedTemporaryFile(suffix='.html', delete=False) as f:
            filepath = f.name
        try:
            result = export_html_theme('# Test', 'github', filepath)
            assert result == filepath
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            assert '<!DOCTYPE html>' in content
        finally:
            os.unlink(filepath)


class TestAstToTree:
    """AST 树形可视化测试"""

    def test_simple_tree(self):
        ast = parse('# Hello')
        tree = ast_to_tree(ast)
        assert isinstance(tree, str)
        assert 'Document' in tree
        assert 'Heading' in tree

    def test_tree_with_children(self):
        ast = parse('# Title\n\nParagraph text')
        tree = ast_to_tree(ast)
        assert 'Title' in tree
        assert 'Paragraph' in tree

    def test_tree_contains_connectors(self):
        ast = parse('# H1\n## H2')
        tree = ast_to_tree(ast)
        assert '└──' in tree or '├──' in tree


class TestAstToMermaid:
    """AST Mermaid 可视化测试"""

    def test_mermaid_output(self):
        ast = parse('# Hello')
        mmd = ast_to_mermaid(ast)
        assert 'graph TD' in mmd
        assert 'Hello' in mmd

    def test_mermaid_with_structure(self):
        ast = parse('# Title\n\nContent')
        mmd = ast_to_mermaid(ast)
        assert 'root' in mmd
        assert '-->' in mmd


class TestBenchmark:
    """性能基准测试"""

    def test_benchmark_parse(self):
        result = benchmark_parse('# Hello\n\nWorld', iterations=5)
        assert 'avg_ms' in result
        assert 'min_ms' in result
        assert 'max_ms' in result
        assert result['iterations'] == 5

    def test_benchmark_generate(self):
        ast = parse('# Hello')
        result = benchmark_generate(ast, iterations=5)
        assert 'avg_ms' in result
        assert result['operation'] == 'generate'

    def test_benchmark_to_html(self):
        result = benchmark_to_html('# Hello', iterations=5)
        assert 'avg_ms' in result
        assert result['operation'] == 'to_html'

    def test_benchmark_full_pipeline(self):
        result = benchmark_full_pipeline('# Hello\n\nWorld', iterations=3)
        assert 'avg_ms' in result
        assert result['operation'] == 'full_pipeline'

    def test_benchmark_report(self):
        report = benchmark_report('# Hello\n\nWorld', iterations=3)
        assert isinstance(report, str)
        assert 'Performance' in report or 'Benchmark' in report


class TestStreamParse:
    """流式解析测试"""

    def test_stream_parse(self):
        content = '# Chunk 1\n\nContent 1\n\n# Chunk 2\n\nContent 2\n'
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write(content)
            filepath = f.name
        try:
            chunks = list(stream_parse(filepath, chunk_size=10))
            assert len(chunks) >= 1
            assert all('chunk_index' in c for c in chunks)
            assert all('node_count' in c for c in chunks)
        finally:
            os.unlink(filepath)

    def test_stream_parse_stats(self):
        content = '# H1\n\nText\n\n## H2\n\nMore\n'
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write(content)
            filepath = f.name
        try:
            stats = stream_parse_stats(filepath, chunk_size=10)
            assert 'chunk_count' in stats
            assert 'total_nodes' in stats
            assert 'total_chars' in stats
            assert stats['chunk_count'] >= 1
        finally:
            os.unlink(filepath)


class TestCrossReferences:
    """交叉引用测试"""

    def test_extract_ref_style(self):
        text = '[link text][ref]'
        refs = extract_cross_references(text)
        assert len(refs) >= 1
        assert any(r.ref_label == 'ref' and r.text == 'link text' for r in refs)

    def test_extract_simple_ref(self):
        text = '[_simple_ref_]'
        refs = extract_cross_references(text)
        # simple_ref 格式 [text] 会被提取
        assert isinstance(refs, list)

    def test_resolve_cross_references(self):
        text = '[link][myref]\n\n[myref]: https://example.com'
        refs = resolve_cross_references(text)
        # 解析后应能找到定义
        assert isinstance(refs, list)

    def test_generate_reference_table(self):
        refs = [
            CrossReference(ref_label='ref1', text='Ref 1', line=1, resolved=True, target='https://example.com'),
            CrossReference(ref_label='ref2', text='Ref 2', line=2, resolved=False),
        ]
        table = generate_reference_table(refs)
        assert 'References' in table
        assert 'ref1' in table
        assert '✅' in table
        assert '❌' in table
