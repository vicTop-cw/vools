"""vools.md 阶段6测试：文档生态工具（DOCX/PDF/模板/预览/合规）"""
import sys, os, tempfile, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vools.md.parser import parse
from vools.md.ecosystem import (
    markdown_to_docx, markdown_to_pdf, markdown_to_pdf_via_cli,
    render_template, render_template_file, TemplateContext,
    PreviewServer, start_preview_server,
    check_compliance, compliance_report, compliance_score,
    ComplianceIssue,
)


# ═══════════════════════════════════════════════════════
# T0.1: DOCX 导出
# ═══════════════════════════════════════════════════════

def test_markdown_to_docx_basic():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.docx', delete=False, encoding='utf-8') as f:
        path = f.name
    result = markdown_to_docx('# Hello\n\nWorld paragraph', path, title='Test')
    assert result == path
    assert os.path.exists(path)
    os.unlink(path)
    print('OK: docx basic')


def test_markdown_to_docx_no_title():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.docx', delete=False, encoding='utf-8') as f:
        path = f.name
    result = markdown_to_docx('# Hello\n\nWorld', path)
    assert result == path
    os.unlink(path)
    print('OK: docx no title')


# ═══════════════════════════════════════════════════════
# T0.2: PDF 导出
# ═══════════════════════════════════════════════════════

def test_markdown_to_pdf_fallback():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.pdf', delete=False, encoding='utf-8') as f:
        path = f.name
    # 无 playwright 时应降级为 HTML
    result = markdown_to_pdf('# Hello\n\nWorld', path, theme='minimal')
    assert os.path.exists(result)
    if result != path:
        # 降级路径
        assert result.endswith('.html')
    os.unlink(result)
    print('OK: pdf fallback')


def test_markdown_to_pdf_via_cli():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.pdf', delete=False, encoding='utf-8') as f:
        path = f.name
    result = markdown_to_pdf_via_cli('# Hello', path)
    assert os.path.exists(result)
    os.unlink(result)
    print('OK: pdf via cli')


# ═══════════════════════════════════════════════════════
# T0.3: 模板渲染
# ═══════════════════════════════════════════════════════

def test_template_variable():
    result = render_template('Hello {{ name }}!', {'name': 'World'})
    assert result == 'Hello World!'
    print('OK: template variable')


def test_template_conditional():
    template = '{% if visible %}Show{% endif %}'
    result = render_template(template, {'visible': True})
    assert result == 'Show'
    result2 = render_template(template, {'visible': False})
    assert result2 == ''
    print('OK: template conditional')


def test_template_loop():
    template = '{% for item in items %}{{ item }} {% endfor %}'
    result = render_template(template, {'items': ['a', 'b', 'c']})
    assert 'a' in result and 'b' in result and 'c' in result
    print('OK: template loop')


def test_template_if_else():
    template = '{% if count %}Has items{% else %}Empty{% endif %}'
    assert render_template(template, {'count': 0}) == 'Empty'
    assert render_template(template, {'count': 5}) == 'Has items'
    print('OK: template if/else')


def test_render_template_file():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.tmpl', delete=False, encoding='utf-8') as f:
        f.write('Hello {{ name }}!')
        tmpl_path = f.name
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        out_path = f.name
    result = render_template_file(tmpl_path, {'name': 'World'}, out_path)
    assert result == out_path
    with open(out_path, 'r', encoding='utf-8') as f:
        assert f.read() == 'Hello World!'
    os.unlink(tmpl_path)
    os.unlink(out_path)
    print('OK: template file')


# ═══════════════════════════════════════════════════════
# T0.4: 实时预览服务器
# ═══════════════════════════════════════════════════════

def test_preview_server_start():
    with tempfile.TemporaryDirectory() as tmpdir:
        md_path = os.path.join(tmpdir, 'test.md')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write('# Hello\n\nWorld')
        server = PreviewServer(tmpdir, theme='github', port=8851)
        url = server.start(blocking=False)
        assert url.startswith('http://localhost:8851')
        server.stop()
        print('OK: preview server start/stop')


def test_preview_server_find_md():
    with tempfile.TemporaryDirectory() as tmpdir:
        md_path = os.path.join(tmpdir, 'doc.md')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write('# Test')
        server = PreviewServer(tmpdir, port=8852)
        content = server._find_first_md()
        assert content == '# Test'
        print('OK: preview find md')


def test_preview_server_compute_hash():
    with tempfile.TemporaryDirectory() as tmpdir:
        md_path = os.path.join(tmpdir, 'test.md')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write('# A')
        server = PreviewServer(tmpdir, port=8853)
        h1 = server._compute_hash()
        assert h1
        # 修改文件后哈希应变化
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write('# B')
        h2 = server._compute_hash()
        assert h1 != h2
        print('OK: preview compute hash')


# ═══════════════════════════════════════════════════════
# T0.5: 合规检查
# ═══════════════════════════════════════════════════════

def test_compliance_clean():
    md = '# Hello\n\nWorld paragraph\n'
    issues = check_compliance(md)
    assert len(issues) == 0
    print('OK: compliance clean')


def test_compliance_heading_skip():
    md = '# H1\n### H3\n'
    issues = check_compliance(md)
    assert any(i.rule == 'heading-skip' for i in issues)
    print('OK: compliance heading skip')


def test_compliance_trailing_whitespace():
    md = 'Hello world   \n'
    issues = check_compliance(md)
    assert any(i.rule == 'trailing-whitespace' for i in issues)
    print('OK: compliance trailing whitespace')


def test_compliance_code_unclosed():
    md = '# Hello\n```python\nprint(1)\n'
    issues = check_compliance(md)
    assert any(i.rule == 'code-block-unclosed' for i in issues)
    print('OK: compliance code unclosed')


def test_compliance_report():
    md = '# H1\n### H3\n'
    report = compliance_report(md)
    assert 'Compliance Report' in report
    assert 'heading-skip' in report
    print('OK: compliance report')


def test_compliance_score():
    md = '# Hello\n\nWorld\n'
    score = compliance_score(md)
    assert score == 100.0
    md_bad = '# H1\n### H3\n'
    score_bad = compliance_score(md_bad)
    assert score_bad < 100.0
    print('OK: compliance score')


if __name__ == '__main__':
    test_markdown_to_docx_basic()
    test_markdown_to_docx_no_title()
    test_markdown_to_pdf_fallback()
    test_markdown_to_pdf_via_cli()
    test_template_variable()
    test_template_conditional()
    test_template_loop()
    test_template_if_else()
    test_render_template_file()
    test_preview_server_start()
    test_preview_server_find_md()
    test_preview_server_compute_hash()
    test_compliance_clean()
    test_compliance_heading_skip()
    test_compliance_trailing_whitespace()
    test_compliance_code_unclosed()
    test_compliance_report()
    test_compliance_score()
    print()
    print('All 18 phase-6 tests passed!')
