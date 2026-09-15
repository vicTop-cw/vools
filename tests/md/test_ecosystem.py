"""tests/md/test_ecosystem.py — 文档生态工具测试"""
import pytest
import sys
import os
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from vools.md.ecosystem import (
    TemplateContext, render_template, render_template_file,
    check_compliance, compliance_report, compliance_score,
    ComplianceIssue, PreviewServer, start_preview_server,
    markdown_to_docx, markdown_to_pdf,
)


class TestTemplateContext:
    """模板上下文测试"""

    def test_set_get(self):
        ctx = TemplateContext()
        ctx.set('name', 'World')
        assert ctx.get('name') == 'World'

    def test_get_default(self):
        ctx = TemplateContext()
        assert ctx.get('missing') is None
        assert ctx.get('missing', 'default') == 'default'

    def test_init_with_dict(self):
        ctx = TemplateContext({'key': 'value'})
        assert ctx.get('key') == 'value'


class TestRenderTemplate:
    """模板渲染测试"""

    def test_variable_substitution(self):
        result = render_template('Hello {{ name }}!', {'name': 'World'})
        assert result == 'Hello World!'

    def test_multiple_variables(self):
        result = render_template('{{ greeting }} {{ name }}', {'greeting': 'Hi', 'name': 'There'})
        assert result == 'Hi There'

    def test_no_variables(self):
        result = render_template('Plain text')
        assert result == 'Plain text'

    def test_condition_true(self):
        result = render_template('{% if show %}visible{% endif %}', {'show': True})
        assert result == 'visible'

    def test_condition_false(self):
        result = render_template('{% if show %}visible{% endif %}', {'show': False})
        assert result == ''

    def test_condition_else_true(self):
        result = render_template('{% if show %}yes{% else %}no{% endif %}', {'show': True})
        assert result == 'yes'

    def test_condition_else_false(self):
        result = render_template('{% if show %}yes{% else %}no{% endif %}', {'show': False})
        assert result == 'no'

    def test_for_loop(self):
        template = '{% for item in items %}{{ item }} {% endfor %}'
        result = render_template(template, {'items': ['a', 'b', 'c']})
        assert 'a' in result
        assert 'b' in result
        assert 'c' in result

    def test_for_loop_empty(self):
        template = '{% for item in items %}{{ item }}{% endfor %}'
        result = render_template(template, {'items': []})
        assert result == ''

    def test_boolean_true_renders_true(self):
        result = render_template('{{ flag }}', {'flag': True})
        assert result == 'true'

    def test_boolean_false_renders_false(self):
        result = render_template('{{ flag }}', {'flag': False})
        assert result == 'false'


class TestRenderTemplateFile:
    """文件模板渲染测试"""

    def test_render_file_to_string(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write('Hello {{ name }}')
            tpl_path = f.name
        try:
            result = render_template_file(tpl_path, {'name': 'World'})
            assert result == 'Hello World'
        finally:
            os.unlink(tpl_path)

    def test_render_file_to_output(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write('Value: {{ val }}')
            tpl_path = f.name
        with tempfile.NamedTemporaryFile(mode='w', suffix='.out', delete=False, encoding='utf-8') as f:
            out_path = f.name
        try:
            result = render_template_file(tpl_path, {'val': '42'}, out_path)
            assert result == out_path
            with open(out_path, 'r', encoding='utf-8') as f:
                assert 'Value: 42' in f.read()
        finally:
            os.unlink(tpl_path)
            if os.path.exists(out_path):
                os.unlink(out_path)


class TestMarkdownToDocx:
    """DOCX 导出测试"""

    def test_export_creates_file(self):
        text = '# Title\n\nHello **world**'
        with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as f:
            filepath = f.name
        try:
            result = markdown_to_docx(text, filepath)
            assert os.path.exists(result)
            assert os.path.getsize(result) > 0
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_export_with_title(self):
        text = '# My Title\n\nContent'
        with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as f:
            filepath = f.name
        try:
            result = markdown_to_docx(text, filepath, title='Custom Title')
            assert os.path.exists(result)
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)


class TestMarkdownToPdf:
    """PDF 导出测试（降级模式）"""

    def test_pdf_fallback_to_html(self):
        """测试 Playwright 不可用时降级为 HTML"""
        text = '# Hello\n\nWorld'
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            filepath = f.name
        try:
            result = markdown_to_pdf(text, filepath)
            # 应该返回 .html 路径（降级）
            assert result.endswith('.html')
            assert os.path.exists(result)
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)
            html_path = filepath.rsplit('.', 1)[0] + '.html'
            if os.path.exists(html_path):
                os.unlink(html_path)


class TestPreviewServer:
    """预览服务器测试"""

    def test_create_server(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            server = PreviewServer(tmpdir, port=18901)
            assert server is not None
            assert server.port == 18901

    def test_start_non_blocking(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建一个 .md 文件供预览
            with open(os.path.join(tmpdir, 'test.md'), 'w', encoding='utf-8') as f:
                f.write('# Preview Test\n\nHello')
            server = PreviewServer(tmpdir, port=18902)
            url = server.start(blocking=False)
            assert '8848' in url or '18902' in url
            server.stop()

    def test_start_preview_server_function(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, 'doc.md'), 'w', encoding='utf-8') as f:
                f.write('# Doc')
            url = start_preview_server(tmpdir, port=18903)
            assert '8848' in url or '18903' in url


class TestCheckCompliance:
    """合规检查测试"""

    def test_valid_markdown(self):
        text = '# Hello\n\nWorld'
        issues = check_compliance(text)
        # 有效 Markdown 应该只有少量 info 级别问题
        errors = [i for i in issues if i.severity == 'error']
        assert len(errors) == 0

    def test_unclosed_code_block(self):
        text = '# Title\n```\ncode without closing'
        issues = check_compliance(text)
        error_rules = [i.rule for i in issues if i.severity == 'error']
        assert 'code-block-unclosed' in error_rules

    def test_heading_skip(self):
        text = '# H1\n### H3'
        issues = check_compliance(text)
        warning_rules = [i.rule for i in issues if i.severity == 'warning']
        assert 'heading-skip' in warning_rules

    def test_trailing_whitespace(self):
        text = '# Title   \n\nWorld'
        issues = check_compliance(text)
        info_rules = [i.rule for i in issues if i.rule == 'trailing-whitespace']
        assert len(info_rules) >= 1

    def test_compliance_issue_attributes(self):
        issue = ComplianceIssue(line=1, column=1, severity='error', rule='test', message='test msg')
        assert issue.line == 1
        assert issue.column == 1
        assert issue.severity == 'error'
        assert issue.rule == 'test'
        assert issue.message == 'test msg'
        assert issue.suggestion is None

    def test_multiple_blank_lines(self):
        text = '# Title\n\n\n\nWorld'
        issues = check_compliance(text)
        blank_line_issues = [i for i in issues if i.rule == 'multiple-blank-lines']
        assert len(blank_line_issues) >= 1


class TestComplianceReport:
    """合规报告测试"""

    def test_report_contains_header(self):
        text = '# Hello'
        report = compliance_report(text)
        assert 'Compliance' in report or 'compliant' in report.lower()

    def test_report_with_issues(self):
        text = '# H1\n### H3'
        report = compliance_report(text)
        assert 'heading-skip' in report

    def test_report_clean_markdown(self):
        text = '# Title\n\nParagraph'
        report = compliance_report(text)
        assert '✅' in report or 'No issues' in report


class TestComplianceScore:
    """合规分数测试"""

    def test_perfect_score(self):
        text = '# Title\n\nContent'
        score = compliance_score(text)
        assert isinstance(score, float)
        assert 0 <= score <= 100

    def test_score_with_errors(self):
        text = '```\nunclosed code block'
        score = compliance_score(text)
        assert score < 100

    def test_score_not_negative(self):
        bad_text = '```\nunclosed\n```\n```\nanother unclosed'
        score = compliance_score(bad_text)
        assert score >= 0
