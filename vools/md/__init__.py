"""
vools.md — Markdown 处理子包

提供 Markdown 解析、生成、HTML 转换和工具函数。

核心组件：
- parse: Markdown 文本 → AST
- generate: AST → Markdown 文本
- to_html: AST/文本 → HTML
- utils: 元数据提取、TOC 生成、代码块提取等
"""

from .parser import (
    parse, parse_to_dict,
    Document, Heading, Paragraph, CodeBlock,
    BlockQuote, MdList, ListItem, Divider, InlineText,
)
from .generator import generate, generate_to_file
from .html import to_html, to_html_file
from .utils import (
    extract_metadata, generate_toc, generate_toc_markdown,
    extract_code_blocks, count_words, strip_markdown, find_headings,
    to_json, to_org_mode, to_plain_text,
)
from .advanced import (
    get_theme, list_themes, render_html_with_theme, export_html_theme,
    ast_to_tree, ast_to_mermaid,
    benchmark_parse, benchmark_generate, benchmark_to_html,
    benchmark_full_pipeline, benchmark_report,
    stream_parse, stream_parse_stats,
    extract_cross_references, resolve_cross_references,
    generate_reference_table, CrossReference,
)
from .ecosystem import (
    markdown_to_docx, markdown_to_pdf, markdown_to_pdf_via_cli,
    render_template, render_template_file, TemplateContext,
    PreviewServer, start_preview_server,
    check_compliance, compliance_report, compliance_score,
    ComplianceIssue,
)

__all__ = [
    # 解析器
    'parse', 'parse_to_dict',
    'Document', 'Heading', 'Paragraph', 'CodeBlock',
    'BlockQuote', 'MdList', 'ListItem', 'Divider', 'InlineText',
    # 生成器
    'generate', 'generate_to_file',
    # HTML
    'to_html', 'to_html_file',
    # 工具函数
    'extract_metadata', 'generate_toc', 'generate_toc_markdown',
    'extract_code_blocks', 'count_words', 'strip_markdown', 'find_headings',
    # 多格式转换
    'to_json', 'to_org_mode', 'to_plain_text',
    # 高级功能
    'get_theme', 'list_themes', 'render_html_with_theme', 'export_html_theme',
    'ast_to_tree', 'ast_to_mermaid',
    'benchmark_parse', 'benchmark_generate', 'benchmark_to_html',
    'benchmark_full_pipeline', 'benchmark_report',
    'stream_parse', 'stream_parse_stats',
    'extract_cross_references', 'resolve_cross_references',
    'generate_reference_table', 'CrossReference',
    # 文档生态
    'markdown_to_docx', 'markdown_to_pdf', 'markdown_to_pdf_via_cli',
    'render_template', 'render_template_file', 'TemplateContext',
    'PreviewServer', 'start_preview_server',
    'check_compliance', 'compliance_report', 'compliance_score',
    'ComplianceIssue',
]
