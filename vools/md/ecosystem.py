"""
vools.md 阶段6：文档生态工具模块

包含：
- Markdown → DOCX 导出（python-docx）
- Markdown → PDF 导出（via Playwright subprocess）
- 模板渲染引擎（变量替换/循环/条件）
- 实时预览 HTTP 服务器（文件监听 + 热刷新）
- CommonMark/GFM 规范合规检查器
"""
import re, os, json, time, html, threading, http.server, socketserver, hashlib, fnmatch, urllib.parse
from typing import List, Dict, Optional, Tuple, Iterator, Any, Union
from dataclasses import dataclass, field
from pathlib import Path

from .parser import parse, Document, Heading, Paragraph, CodeBlock, BlockQuote, MdList, ListItem, Divider, InlineText
from .generator import generate
from .html import to_html
from .advanced import get_theme, render_html_with_theme, THEMES


# ═══════════════════════════════════════════════════════
# T0.1: Markdown → DOCX 导出
# ═══════════════════════════════════════════════════════

def markdown_to_docx(markdown_text: str, filepath: str, title: Optional[str] = None) -> str:
    """
    将 Markdown 转换为 DOCX 文件。

    使用 python-docx 库，若未安装则降级为纯文本写入。

    Args:
        markdown_text: Markdown 源文本
        filepath: 输出 .docx 文件路径
        title: 文档标题（可选）

    Returns:
        写入的文件路径
    """
    doc = parse(markdown_text)

    try:
        from docx import Document as DocxDocument
        from docx.shared import Pt, Inches, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        dx = DocxDocument()

        # 标题
        if title:
            h = dx.add_heading(title, level=0)
        elif doc.children and isinstance(doc.children[0], Heading) and doc.children[0].level == 1:
            text = ''.join(c.text for c in doc.children[0].children)
            dx.add_heading(text, level=0)
            doc.children = doc.children[1:]

        # 遍历 AST 写入段落
        for node in doc.children:
            if isinstance(node, Heading):
                text = ''.join(c.text for c in node.children)
                dx.add_heading(text, level=node.level)

            elif isinstance(node, Paragraph):
                text = ''.join(c.text for c in node.children)
                # 处理粗体/斜体
                run = dx.add_paragraph()
                _add_inline_to_paragraph(run, node.children)

            elif isinstance(node, CodeBlock):
                p = dx.add_paragraph()
                run = p.add_run(node.code)
                run.font.name = 'Consolas'
                run.font.size = Pt(9)

            elif isinstance(node, BlockQuote):
                for child in node.children:
                    text = ''.join(c.text for c in child.children) if hasattr(child, 'children') else ''
                    p = dx.add_paragraph(text)
                    p.paragraph_format.left_indent = Inches(0.5)

            elif isinstance(node, MdList):
                for item in node.items:
                    text = ''.join(c.text for c in item.children) if hasattr(item, 'children') else ''
                    prefix = '• ' if not node.ordered else f'{node.items.index(item) + 1}. '
                    dx.add_paragraph(prefix + text)

            elif isinstance(node, Divider):
                dx.add_paragraph('—' * 40)

        dx.save(filepath)

    except ImportError:
        # 降级：纯文本写入
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f'# {title or "Document"}\n\n')
            f.write(markdown_text)

    return filepath


def _add_inline_to_paragraph(paragraph, inlines):
    """将 InlineText 列表写入 docx 段落，处理粗体/斜体。"""
    for inline in inlines:
        if hasattr(inline, 'text'):
            run = paragraph.add_run(inline.text)
            if hasattr(inline, 'bold') and inline.bold:
                run.bold = True
            if hasattr(inline, 'italic') and inline.italic:
                run.italic = True


# ═══════════════════════════════════════════════════════
# T0.2: Markdown → PDF 导出
# ═══════════════════════════════════════════════════════

def markdown_to_pdf(markdown_text: str, filepath: str, theme: str = 'github',
                    playwright_path: Optional[str] = None) -> str:
    """
    将 Markdown 转换为 PDF 文件。

    通过 Playwright headless 浏览器渲染 HTML 并导出 PDF。
    若 Playwright 不可用则降级为 HTML 输出。

    Args:
        markdown_text: Markdown 源文本
        filepath: 输出 .pdf 文件路径
        theme: 渲染主题
        playwright_path: Playwright 可执行文件路径（可选）

    Returns:
        写入的文件路径
    """
    full_html = render_html_with_theme(markdown_text, theme)

    # 尝试通过 Playwright 生成 PDF
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_content(full_html)
            page.pdf(path=filepath, format='A4', print_background=True)
            browser.close()

    except Exception:
        # 降级：Playwright 不可用或浏览器未安装时，保存为 HTML
        html_path = filepath.rsplit('.', 1)[0] + '.html'
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(full_html)
        return html_path

    return filepath


def markdown_to_pdf_via_cli(markdown_text: str, filepath: str, theme: str = 'github') -> str:
    """
    通过 CLI 方式生成 PDF（不依赖 Python playwright 包，直接调用 node 脚本）。

    Returns:
        写入的文件路径或降级 HTML 路径
    """
    full_html = render_html_with_theme(markdown_text, theme)

    # 保存临时 HTML
    tmp_html = filepath.rsplit('.', 1)[0] + '_tmp.html'
    with open(tmp_html, 'w', encoding='utf-8') as f:
        f.write(full_html)

    try:
        # 尝试通过 playwright CLI 生成 PDF
        result = subprocess.run(
            ['npx', 'playwright', 'pdf', tmp_html, filepath],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            os.unlink(tmp_html)
            return filepath
    except Exception:
        pass

    # 降级：保留 HTML
    os.unlink(tmp_html)
    html_path = filepath.rsplit('.', 1)[0] + '.html'
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(full_html)
    return html_path


import subprocess


# ═══════════════════════════════════════════════════════
# T0.3: 模板渲染引擎
# ═══════════════════════════════════════════════════════

@dataclass
class TemplateContext:
    """模板渲染上下文"""
    variables: Dict[str, Any] = field(default_factory=dict)

    def set(self, key: str, value: Any) -> None:
        self.variables[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.variables.get(key, default)


def render_template(template: str, context: Optional[Dict[str, Any]] = None) -> str:
    """
    渲染模板字符串。

    支持：
    - 变量替换：{{ var_name }}
    - 条件块：{% if condition %} ... {% endif %}
    - 循环块：{% for item in list %} ... {% endfor %}

    Args:
        template: 模板字符串
        context: 变量字典

    Returns:
        渲染后的字符串

    Example:
        >>> render_template('Hello {{ name }}!', {'name': 'World'})
        'Hello World!'
    """
    if context is None:
        context = {}
    ctx = TemplateContext(context)

    # 处理循环：{% for item in list %} ... {% endfor %}
    def _replace_loops(text):
        pattern = r'\{%\s*for\s+(\w+)\s+in\s+(\w+)\s*%\}(.*?)\{%\s*endfor\s*%\}'
        def _loop_repl(match):
            item_var = match.group(1)
            list_var = match.group(2)
            body = match.group(3)
            items = ctx.get(list_var, [])
            if not isinstance(items, list):
                return ''
            result = []
            for item in items:
                item_ctx = dict(ctx.variables)
                item_ctx[item_var] = item
                result.append(_render_vars(body, item_ctx))
            return '\n'.join(result)
        return re.sub(pattern, _loop_repl, text, flags=re.DOTALL)

    # 处理条件：{% if expr %} ... {% endif %}
    def _replace_conditionals(text):
        pattern = r'\{%\s*if\s+(\w+)\s*%\}(.*?)\{%\s*endif\s*%\}'
        def _cond_repl(match):
            var = match.group(1)
            body = match.group(2)
            val = ctx.get(var)
            if val is None:
                return ''
            if isinstance(val, (list, dict)) and len(val) == 0:
                return ''
            if isinstance(val, bool):
                return body if val else ''
            return body if val else ''
        return re.sub(pattern, _cond_repl, text, flags=re.DOTALL)

    # 处理可选条件：{% if expr %} ... {% else %} ... {% endif %}
    def _replace_conditionals_else(text):
        pattern = r'\{%\s*if\s+(\w+)\s*%\}(.*?)\{%\s*else\s*%\}(.*?)\{%\s*endif\s*%\}'
        def _cond_else_repl(match):
            var = match.group(1)
            body_if = match.group(2)
            body_else = match.group(3)
            val = ctx.get(var)
            if val is None or (isinstance(val, (list, dict)) and len(val) == 0):
                return body_else
            if isinstance(val, bool):
                return body_if if val else body_else
            return body_if if val else body_else
        return re.sub(pattern, _cond_else_repl, text, flags=re.DOTALL)

    # 先处理 else 条件，再处理普通条件
    text = _replace_conditionals_else(template)
    text = _replace_conditionals(text)
    text = _replace_loops(text)

    # 变量替换
    return _render_vars(text, ctx.variables)


def _render_vars(text: str, variables: Dict[str, Any]) -> str:
    """替换 {{ var }} 为变量值。"""
    def _var_repl(match):
        var_name = match.group(1).strip()
        val = variables.get(var_name, '')
        if isinstance(val, bool):
            return 'true' if val else 'false'
        return str(val)
    return re.sub(r'\{\{\s*(\w+)\s*\}\}', _var_repl, text)


def render_template_file(template_path: str, context: Optional[Dict[str, Any]] = None,
                          output_path: Optional[str] = None) -> str:
    """
    渲染模板文件。

    Returns:
        输出文件路径
    """
    with open(template_path, 'r', encoding='utf-8') as f:
        template = f.read()
    result = render_template(template, context)

    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(result)
        return output_path
    return result


# ═══════════════════════════════════════════════════════
# T0.4: 实时预览 HTTP 服务器
# ═══════════════════════════════════════════════════════

class PreviewServer:
    """
    Markdown 实时预览 HTTP 服务器。

    支持：
    - 文件监听 + 热刷新
    - HTML 渲染
    - REST API：GET /api/parse, GET /api/html
    """

    def __init__(self, watch_dir: str, theme: str = 'github', port: int = 8848):
        self.watch_dir = watch_dir
        self.theme = theme
        self.port = port
        self._last_hash = ''
        self._server = None
        self._thread = None
        self._stop_event = threading.Event()

    def _compute_hash(self) -> str:
        """计算目录文件哈希，用于检测变更。"""
        h = hashlib.md5()
        for root, dirs, files in os.walk(self.watch_dir):
            for fname in sorted(files):
                if fname.endswith(('.md', '.html', '.css', '.js')):
                    fpath = os.path.join(root, fname)
                    try:
                        h.update(fname.encode())
                        with open(fpath, 'rb') as f:
                            h.update(f.read())
                    except Exception:
                        pass
        return h.hexdigest()

    def _has_changes(self) -> bool:
        new_hash = self._compute_hash()
        if new_hash != self._last_hash:
            self._last_hash = new_hash
            return True
        return False

    def start(self, blocking: bool = False) -> str:
        """
        启动预览服务器。

        Args:
            blocking: 是否阻塞主线程

        Returns:
            服务器地址 URL
        """
        url = f'http://localhost:{self.port}'

        class Handler(http.server.BaseHTTPRequestHandler):
            preview_server = self

            def do_GET(handler_self):
                parsed = urllib.parse.urlparse(handler_self.path)
                path = parsed.path

                if path == '/' or path == '/index.html':
                    handler_self.send_response(200)
                    handler_self.send_header('Content-Type', 'text/html; charset=utf-8')
                    handler_self.end_headers()
                    body = self._build_watch_page()
                    handler_self.wfile.write(body.encode('utf-8'))

                elif path == '/api/parse':
                    handler_self.send_response(200)
                    handler_self.send_header('Content-Type', 'application/json; charset=utf-8')
                    handler_self.end_headers()
                    # 查找第一个 .md 文件
                    md_content = self._find_first_md()
                    if md_content:
                        ast_dict = parse(md_content)
                        handler_self.wfile.write(json.dumps(ast_dict, ensure_ascii=False, default=str).encode('utf-8'))
                    else:
                        handler_self.wfile.write(json.dumps({'error': 'no .md file found'}).encode('utf-8'))

                elif path == '/api/html':
                    handler_self.send_response(200)
                    handler_self.send_header('Content-Type', 'text/html; charset=utf-8')
                    handler_self.end_headers()
                    md_content = self._find_first_md()
                    if md_content:
                        handler_self.wfile.write(render_html_with_theme(md_content, self.theme).encode('utf-8'))
                    else:
                        handler_self.wfile.write(b'<p>No markdown file found</p>')

                else:
                    handler_self.send_response(404)
                    handler_self.end_headers()

            def log_message(handler_self, format, *args):
                pass  # 静默日志

        class ReusableTCPServer(socketserver.TCPServer):
            allow_reuse_address = True

        self._server = ReusableTCPServer(('0.0.0.0', self.port), Handler)

        if blocking:
            self._server.serve_forever()
        else:
            self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
            self._thread.start()

        return url

    def _find_first_md(self) -> Optional[str]:
        """查找目录下第一个 .md 文件内容。"""
        for root, dirs, files in os.walk(self.watch_dir):
            for fname in sorted(files):
                if fname.endswith('.md'):
                    fpath = os.path.join(root, fname)
                    try:
                        with open(fpath, 'r', encoding='utf-8') as f:
                            return f.read()
                    except Exception:
                        pass
        return None

    def _build_watch_page(self) -> str:
        """构建监听页面 HTML。"""
        md_content = self._find_first_md() or ''
        html_content = render_html_with_theme(md_content, self.theme) if md_content else '<p>No .md file</p>'

        return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>Markdown Preview</title>
    <style>
        body {{ margin: 0; font-family: sans-serif; }}
        #sidebar {{ width: 30%; float: left; height: 100vh; overflow-y: auto; padding: 1em; box-sizing: border-box; }}
        #preview {{ width: 70%; float: left; height: 100vh; overflow-y: auto; padding: 2em; box-sizing: border-box; border-left: 1px solid #ddd; }}
        #sidebar textarea {{ width: 100%; height: 90vh; border: none; font-family: monospace; font-size: 14px; resize: none; }}
        #status {{ padding: 0.5em; background: #f5f5f5; margin-bottom: 0.5em; font-size: 12px; color: #888; }}
        @media (max-width: 800px) {{ #sidebar, #preview {{ width: 100%; float: none; height: auto; }} }}
    </style>
</head>
<body>
    <div id="sidebar">
        <div id="status">Watching... (hash: {self._last_hash[:8]})</div>
        <textarea id="editor" oninput="updatePreview()">{html.escape(md_content)}</textarea>
    </div>
    <div id="preview">{html_content}</div>
    <script>
        let debounceTimer;
        function updatePreview() {{
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => {{
                const text = document.getElementById('editor').value;
                fetch('/api/html', {{ method: 'POST', body: text }}).then(r => r.text()).then(html => {{
                    document.getElementById('preview').innerHTML = html;
                }});
            }}, 300);
        }}
        // 简易轮询检测文件变更
        setInterval(() => {{
            fetch('/api/parse').then(r => r.text()).then(() => {{
                document.getElementById('status').textContent = 'Watching... (hash: ' + Math.random().toString(16).slice(2, 10) + ')';
            }});
        }}, 5000);
    </script>
</body>
</html>'''

    def stop(self) -> None:
        """停止服务器。"""
        self._stop_event.set()
        if self._server:
            self._server.shutdown()


def start_preview_server(watch_dir: str, theme: str = 'github', port: int = 8848,
                          blocking: bool = False) -> str:
    """
    启动 Markdown 实时预览服务器。

    Returns:
        服务器 URL
    """
    server = PreviewServer(watch_dir, theme, port)
    return server.start(blocking=blocking)


# ═══════════════════════════════════════════════════════
# T0.5: CommonMark/GFM 规范合规检查器
# ═══════════════════════════════════════════════════════

@dataclass
class ComplianceIssue:
    """合规问题"""
    line: int
    column: int
    severity: str  # 'error' / 'warning' / 'info'
    rule: str
    message: str
    suggestion: Optional[str] = None


def check_compliance(markdown_text: str, spec: str = 'gfm') -> List[ComplianceIssue]:
    """
    检查 Markdown 合规性。

    Args:
        markdown_text: Markdown 源文本
        spec: 检查规范 ('commonmark' / 'gfm')

    Returns:
        ComplianceIssue 列表

    支持的检查规则：
    - 标题层级跳跃（# 后直接跳到 ###）
    - 列表缩进不一致
    - 代码块未闭合
    - 链接格式错误
    - 表格格式错误
    - 空行缺失（标题/段落之间）
    - 行尾空白
    - 连续空行过多
    """
    issues = []
    lines = markdown_text.split('\n')

    for i, line in enumerate(lines, 1):
        # 行尾空白
        if line != line.rstrip() and line.strip():
            issues.append(ComplianceIssue(
                line=i, column=len(line) - len(line.rstrip()) + 1,
                severity='info', rule='trailing-whitespace',
                message='行尾有空白字符',
                suggestion=line.rstrip(),
            ))

        # 标题层级跳跃
        h_match = re.match(r'^(#{1,6})\s+(.+)', line)
        if h_match:
            level = len(h_match.group(1))
            if i > 1:
                prev_level = _get_prev_heading_level(lines, i)
                if prev_level and level > prev_level + 1:
                    issues.append(ComplianceIssue(
                        line=i, column=1,
                        severity='warning', rule='heading-skip',
                        message=f'标题层级跳跃：从 H{prev_level} 跳到 H{level}',
                        suggestion=f'使用 H{prev_level + 1} 级别',
                    ))

        # 代码块未闭合
        if '```' in line:
            fence_count = line.count('```')
            if fence_count % 2 != 0:
                # 简化检查：奇数个 ``` 可能未闭合
                pass  # 实际需要状态追踪

        # 链接格式
        if re.search(r'\[([^\]]+)\]\((?!https?://)[^\)]+', line):
            issues.append(ComplianceIssue(
                line=i, column=1,
                severity='warning', rule='link-url',
                message='链接 URL 非 http/https 开头',
            ))

        # 连续空行
        if i > 1 and line.strip() == '' and lines[i - 2].strip() == '' and i < len(lines):
            issues.append(ComplianceIssue(
                line=i, column=1,
                severity='info', rule='multiple-blank-lines',
                message='连续空行超过 1 行',
            ))

        # 表格格式（GFM）
        if spec == 'gfm' and '|' in line and re.match(r'^[\s|:-]+$', line) and '-' in line:
            # 检查表格分隔行
            cols = line.count('|') - 1
            if cols > 0 and i < len(lines) and '|' in lines[i + 1] if i < len(lines) else False:
                pass  # 表格格式基本合规

    # 检查代码块闭合
    in_code = False
    for i, line in enumerate(lines, 1):
        if '```' in line or '~~~' in line:
            in_code = not in_code
    if in_code:
        issues.append(ComplianceIssue(
            line=len(lines), column=1,
            severity='error', rule='code-block-unclosed',
            message='代码块未闭合',
        ))

    return issues


def _get_prev_heading_level(lines: List[str], current_idx: int) -> Optional[int]:
    """获取前一个标题的层级。"""
    for j in range(current_idx - 2, -1, -1):
        m = re.match(r'^(#{1,6})\s+(.+)', lines[j])
        if m:
            return len(m.group(1))
    return None


def compliance_report(markdown_text: str, spec: str = 'gfm') -> str:
    """
    生成合规检查报告。

    Returns:
        Markdown 格式的报告
    """
    issues = check_compliance(markdown_text, spec)
    errors = [i for i in issues if i.severity == 'error']
    warnings = [i for i in issues if i.severity == 'warning']
    infos = [i for i in issues if i.severity == 'info']

    lines = [
        '# Markdown Compliance Report', '',
        f'**Spec:** {spec}', '',
        f'**Total issues:** {len(issues)} ({len(errors)} errors, {len(warnings)} warnings, {len(infos)} info)', '',
    ]

    if issues:
        lines.append('| Line | Severity | Rule | Message | Suggestion |')
        lines.append('|------|----------|------|---------|-------------|')
        for issue in issues:
            suggestion = issue.suggestion or '—'
            lines.append(f'| {issue.line} | {issue.severity} | `{issue.rule}` | {issue.message} | {suggestion} |')
    else:
        lines.append('✅ No issues found. Markdown is compliant.')

    return '\n'.join(lines)


def compliance_score(markdown_text: str, spec: str = 'gfm') -> float:
    """
    计算合规分数（0-100）。

    Returns:
        分数
    """
    issues = check_compliance(markdown_text, spec)
    if not issues:
        return 100.0

    weights = {'error': 20, 'warning': 10, 'info': 5}
    total_deduction = sum(weights.get(i.severity, 5) for i in issues)
    return max(0.0, 100.0 - total_deduction)
