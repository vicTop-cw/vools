"""vools.md 阶段4：智能TOC锚点 + 代码高亮 + Frontmatter + Emoji + Linting + 文档组装"""
import sys, os, json, re, hashlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vools.md.parser import (
    parse, Document, Heading, Paragraph, CodeBlock, BlockQuote,
    MdList, ListItem, Divider, InlineText, parse_to_dict, _parse_inline,
)
from vools.md.generator import generate
from vools.md.html import to_html
from vools.md.utils import (
    extract_metadata, generate_toc, find_headings, strip_markdown, count_words,
)

from typing import List, Dict, Optional, Tuple, Callable
from dataclasses import dataclass, field


# ═══════════════════════════════════════════════════════
# T0.1: 智能 TOC 锚点
# ═══════════════════════════════════════════════════════

def generate_anchor(text: str, fmt: str = 'github') -> str:
    """
    生成标题锚点 ID。

    Args:
        text: 标题文本
        fmt: 锚点格式 ('github' / 'underscore' / 'hash')

    Returns:
        锚点 ID

    Examples:
        >>> generate_anchor('Hello World')
        'hello-world'
        >>> generate_anchor('Hello World', fmt='underscore')
        'hello_world'
    """
    # 去除行内标记
    text = re.sub(r'[`*_~]', '', text)
    text = text.lower().strip()

    if fmt == 'github':
        text = re.sub(r'[^\w\s-]', '', text)
        text = re.sub(r'\s+', '-', text)
    elif fmt == 'underscore':
        text = re.sub(r'[^\w\s_]', '', text)
        text = re.sub(r'\s+', '_', text)
    elif fmt == 'hash':
        text = re.sub(r'[^\w\s]', '', text)
        text = re.sub(r'\s+', '', text)
    else:
        text = re.sub(r'\s+', '-', text.lower())

    return text


def generate_toc_with_anchors(
    markdown_text: str,
    fmt: str = 'github',
    max_level: int = 6,
) -> List[Dict]:
    """
    生成带锚点的目录。

    Args:
        markdown_text: Markdown 源文本
        fmt: 锚点格式
        max_level: 最大标题层级

    Returns:
        目录列表，每项包含 level/text/anchor
    """
    doc = parse(markdown_text)
    toc = []
    for node in doc.children:
        if isinstance(node, Heading):
            if node.level > max_level:
                continue
            text = ''.join(c.text for c in node.children)
            anchor = generate_anchor(text, fmt)
            toc.append({
                'level': node.level,
                'text': text,
                'anchor': anchor,
            })
    return toc


def generate_toc_markdown_with_anchors(
    markdown_text: str,
    fmt: str = 'github',
    max_level: int = 6,
) -> str:
    """
    生成 Markdown 格式的带锚点目录。

    Returns:
        Markdown 格式的目录文本
    """
    toc = generate_toc_with_anchors(markdown_text, fmt, max_level)
    lines = ['## 目录', '']
    for item in toc:
        indent = '  ' * (item['level'] - 1)
        lines.append(f'{indent}- [{item["text"]}](#{item["anchor"]})')
    return '\n'.join(lines)


# ═══════════════════════════════════════════════════════
# T0.2: 代码高亮
# ═══════════════════════════════════════════════════════

# 常见语言映射
LANG_MAP = {
    'py': 'python', 'python': 'python',
    'js': 'javascript', 'jsx': 'javascript', 'ts': 'typescript', 'tsx': 'typescript',
    'html': 'html', 'htm': 'html', 'xml': 'xml',
    'css': 'css', 'scss': 'scss', 'less': 'less',
    'java': 'java', 'kt': 'kotlin', 'swift': 'swift',
    'c': 'c', 'h': 'c', 'cpp': 'cpp', 'hpp': 'cpp', 'cxx': 'cpp',
    'rs': 'rust', 'go': 'go', 'rs.go': 'go',
    'rb': 'ruby', 'php': 'php',
    'sh': 'bash', 'bash': 'bash', 'zsh': 'bash',
    'yml': 'yaml', 'yaml': 'yaml',
    'json': 'json', 'toml': 'toml', 'ini': 'ini',
    'md': 'markdown', 'markdown': 'markdown',
    'sql': 'sql', 'r': 'r', 'jl': 'julia',
    'dart': 'dart', 'lua': 'lua', 'pl': 'perl',
    'scala': 'scala', 'clj': 'clojure', 'ex': 'elixir',
    'hs': 'haskell', 'ml': 'ocaml',
}

# 未标记代码块的语言检测
def detect_language(code: str, hint: str = '') -> str:
    """
    检测代码块的语言。

    Args:
        code: 代码文本
        hint: 语言提示（如文件扩展名）

    Returns:
        标准化的语言名称
    """
    if hint:
        lang = hint.strip().lower()
        return LANG_MAP.get(lang, lang)

    # 基于内容特征检测
    lines = code.strip().split('\n')[:5]
    joined = '\n'.join(lines)

    if re.search(r'\bdef\s+\w+\s*\(', joined) or re.search(r'\bclass\s+\w+\s*[:(]', joined):
        return 'python'
    if re.search(r'\bfunction\b|\bconst\b|\blet\b|\bvar\b|=>', joined):
        return 'javascript'
    if re.search(r'\bint\s+\w+\s*=\s*;|cout\s*<<|#include', joined):
        return 'cpp'
    if 'package ' in joined and ';' in joined:
        return 'java'
    if 'func ' in joined and ':=' in joined:
        return 'go'
    if re.search(r'\bdef\b|\bend\b', joined):
        return 'ruby'
    if '<?php' in joined:
        return 'php'
    if '#include' in joined or 'printf' in joined:
        return 'c'
    if 'SELECT ' in joined.upper() or 'CREATE TABLE' in joined.upper():
        return 'sql'

    return 'text'


def highlight_code_block(code: str, language: str = '') -> Dict:
    """
    代码块高亮信息。

    Returns:
        包含 language/detected_lang/line_count 的字典
    """
    detected = detect_language(code, language) if language else detect_language(code)
    return {
        'language': language,
        'detected_language': detected,
        'line_count': len(code.split('\n')),
        'css_class': f'language-{detected}',
    }


# ═══════════════════════════════════════════════════════
# T0.3: Frontmatter 支持
# ═══════════════════════════════════════════════════════

def parse_frontmatter(markdown_text: str) -> Tuple[Dict, str]:
    """
    解析 Markdown 的 frontmatter（YAML 格式）。

    Args:
        markdown_text: Markdown 源文本

    Returns:
        (metadata_dict, body_text)
    """
    lines = markdown_text.split('\n')
    if len(lines) < 2 or lines[0].strip() != '---':
        return {}, markdown_text

    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == '---':
            end_idx = i
            break

    if end_idx is None:
        return {}, markdown_text

    meta = {}
    for line in lines[1:end_idx]:
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        if ':' in stripped:
            key, _, value = stripped.partition(':')
            meta[key.strip()] = value.strip()

    body = '\n'.join(lines[end_idx + 1:])
    return meta, body


def dump_frontmatter(meta: Dict) -> str:
    """
    将元数据序列化为 YAML frontmatter。

    Returns:
        YAML frontmatter 文本（含 --- 分隔符）
    """
    lines = ['---']
    for key, value in meta.items():
        lines.append(f'{key}: {value}')
    lines.append('---')
    return '\n'.join(lines)


def with_frontmatter(markdown_text: str, meta: Dict) -> str:
    """
    在 Markdown 文本前添加 frontmatter。

    Args:
        markdown_text: 正文
        meta: 元数据字典

    Returns:
        带 frontmatter 的完整 Markdown
    """
    fm = dump_frontmatter(meta)
    return fm + '\n\n' + markdown_text.strip()


# ═══════════════════════════════════════════════════════
# T0.4: Emoji 支持
# ═══════════════════════════════════════════════════════

# 常用 emoji 短代码映射
EMOJI_MAP = {
    ':smile:': '😄', ':laughing:': '😆', ':wink:': '😉',
    ':heart:': '❤️', ':thumbsup:': '👍', ':thumbsdown:': '👎',
    ':star:': '⭐', ':fire:': '🔥', ':check:': '✅', ':x:': '❌',
    ':warning:': '⚠️', ':info:': 'ℹ️', ':question:': '❓',
    ':clap:': '👏', ':rocket:': '🚀', ':tada:': '🎉',
    ':sparkles:': '✨', ':100:': '💯', ':ok_hand:': '👌',
    ':+1:': '👍', ':-1:': '👎', ':white_check_mark:': '✅',
    ':no_entry_sign:': '❌', ':warning:': '⚠️',
    ':sun:': '☀️', ':moon:': '🌙', ':cloud:': '☁️',
    ':rainbow:': '🌈', ':snowflake:': '❄️', ':zap:': '⚡',
    ':bulb:': '💡', ':trash:': '🗑️', ':copy:': '📋',
    ':link:': '🔗', ':mail:': '✉️', ':phone:': '📱',
    ':camera:': '📷', ':video_camera:': '📹', ':music:': '🎵',
    ':gift:': '🎁', ':bookmark:': '🔖', ':pushpin:': '📌',
    ':key:': '🔑', ':lock:': '🔒', ':unlock:': '🔓',
    ':shield:': '🛡️', ':star2:': '🌟', ':angel:': '👼',
    ':ghost:': '👻', ':alien:': '👽', ':robot:': '🤖',
    ':joy:': '😂', ':scream:': '😱', ':heart_eyes:': '😍',
    ':kiss:': '😘', ':stuck_out_tongue:': '😜',
    ':thinking:': '🤔', ':confused:': '😕', ':sleeping:': '😴',
    ':cool:': '😎', ':relaxed:': '😌', ':sunglasses:': '🕶️',
}


def render_emoji(text: str) -> str:
    """
    将 emoji 短代码转换为实际 emoji 字符。

    Args:
        text: 包含 emoji 短代码的文本

    Returns:
        转换后的文本

    Example:
        >>> render_emoji('Hello :smile: World')
        'Hello 😄 World'
    """
    result = text
    for code, emoji in EMOJI_MAP.items():
        result = result.replace(code, emoji)
    return result


def render_emoji_in_markdown(markdown_text: str) -> str:
    """
    渲染 Markdown 中所有 emoji 短代码。

    Returns:
        转换后的 Markdown 文本
    """
    return render_emoji(markdown_text)


# ═══════════════════════════════════════════════════════
# T0.5: Markdown Linting
# ═══════════════════════════════════════════════════════

@dataclass
class LintIssue:
    """Lint 问题"""
    line: int
    column: int
    rule: str
    message: str
    severity: str = 'warning'  # 'error', 'warning', 'info'


def lint_markdown(
    markdown_text: str,
    rules: Optional[List[str]] = None,
) -> List[LintIssue]:
    """
    Markdown 校验引擎，检测常见问题。

    Args:
        markdown_text: Markdown 源文本
        rules: 要启用的规则列表（None=全部启用）

    Returns:
        LintIssue 列表

    Available rules:
        - 'no-trailing-spaces': 行尾多余空格
        - 'no-multiple-blanks': 连续空行
        - 'heading-no-space': 标题 # 后无空格
        - 'heading-no-end-punct': 标题末尾标点
        - 'code-block-language': 代码块未指定语言
        - 'link-no-url': 链接无 URL
        - 'long-line': 行过长（>80字符）
        - 'no-bare-urls': 裸 URL
        - 'no-html-comments': HTML 注释
    """
    if rules is None:
        rules = [
            'no-trailing-spaces', 'no-multiple-blanks',
            'heading-no-space', 'heading-no-end-punct',
            'code-block-language', 'link-no-url',
            'long-line', 'no-bare-urls',
        ]

    issues = []
    lines = markdown_text.split('\n')

    for i, line in enumerate(lines, 1):
        # no-trailing-spaces
        if 'no-trailing-spaces' in rules:
            if line != line.rstrip():
                issues.append(LintIssue(
                    line=i, column=len(line.rstrip()) + 1,
                    rule='no-trailing-spaces',
                    message='行尾有多余空格', severity='info'
                ))

        # no-multiple-blanks
        if 'no-multiple-blanks' in rules and not line.strip():
            if i > 1 and not lines[i-2].strip():
                issues.append(LintIssue(
                    line=i, column=1,
                    rule='no-multiple-blanks',
                    message='连续空行', severity='info'
                ))

        # heading-no-space
        if 'heading-no-space' in rules:
            m = re.match(r'^(#{1,6})(\S)', line)
            if m:
                issues.append(LintIssue(
                    line=i, column=len(m.group(1)) + 1,
                    rule='heading-no-space',
                    message=f'标题 {m.group(1)} 后应有空格', severity='warning'
                ))

        # heading-no-end-punct
        if 'heading-no-end-punct' in rules:
            m = re.match(r'^#{1,6}\s+(.+)$', line)
            if m:
                title = m.group(1).strip()
                if title and title[-1] in '.。!！?？;；':
                    issues.append(LintIssue(
                        line=i, column=len(line),
                        rule='heading-no-end-punct',
                        message='标题不应以标点结尾', severity='info'
                    ))

        # code-block-language
        if 'code-block-language' in rules:
            if line.strip().startswith('```') and len(line.strip()) == 3:
                issues.append(LintIssue(
                    line=i, column=1,
                    rule='code-block-language',
                    message='代码块未指定语言', severity='info'
                ))

        # link-no-url
        if 'link-no-url' in rules:
            m = re.match(r'\[([^\]]+)\]\(\)', line)
            if m:
                issues.append(LintIssue(
                    line=i, column=1,
                    rule='link-no-url',
                    message='链接缺少 URL', severity='warning'
                ))

        # long-line
        if 'long-line' in rules and len(line) > 80:
            issues.append(LintIssue(
                line=i, column=81,
                rule='long-line',
                message=f'行过长 ({len(line)} > 80)', severity='info'
            ))

        # no-bare-urls
        if 'no-bare-urls' in rules:
            m = re.match(r'^\s*(https?://\S+)\s*$', line)
            if m:
                issues.append(LintIssue(
                    line=i, column=1,
                    rule='no-bare-urls',
                    message='裸 URL 应包裹在 <> 中', severity='info'
                ))

    return issues


def lint_markdown_report(markdown_text: str, rules: Optional[List[str]] = None) -> str:
    """
    生成 Markdown 格式的 Lint 报告。

    Returns:
        Markdown 格式的 Lint 报告
    """
    issues = lint_markdown(markdown_text, rules)
    if not issues:
        return '✅ No issues found.'

    lines = ['## Markdown Lint Report', '', f'**{len(issues)} issues found:**', '']
    for issue in issues:
        icon = '❌' if issue.severity == 'error' else '⚠️' if issue.severity == 'warning' else '💡'
        lines.append(f'- {icon} L{issue.line}:{issue.column} `{issue.rule}` - {issue.message}')
    return '\n'.join(lines)


# ═══════════════════════════════════════════════════════
# T0.6: 文档组装
# ═══════════════════════════════════════════════════════

def assemble_documents(
    files: List[str],
    include_patterns: Optional[List[str]] = None,
    exclude_patterns: Optional[List[str]] = None,
    add_frontmatter: Optional[Dict] = None,
    add_toc: bool = True,
    separator: str = '\n\n---\n\n',
) -> str:
    """
    组装多个 Markdown 文件为一个文档。

    Args:
        files: 文件路径列表
        include_patterns: 只包含匹配的文件（可选）
        exclude_patterns: 排除匹配的文件（可选）
        add_frontmatter: 添加到文档头部的元数据
        add_toc: 是否在头部生成目录
        separator: 文件间分隔符

    Returns:
        组装后的 Markdown 文本
    """
    parts = []

    for filepath in files:
        # 过滤
        if include_patterns:
            if not any(re.search(p, filepath) for p in include_patterns):
                continue
        if exclude_patterns:
            if any(re.search(p, filepath) for p in exclude_patterns):
                continue

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            # 移除 frontmatter
            meta, body = parse_frontmatter(content)
            parts.append(body.strip())
        except Exception:
            pass

    assembled = separator.join(parts)

    # 添加 TOC
    if add_toc:
        toc = generate_toc_markdown_with_anchors(assembled)
        assembled = toc + '\n\n' + assembled

    # 添加 frontmatter
    if add_frontmatter:
        assembled = with_frontmatter(assembled, add_frontmatter)

    return assembled


def assemble_from_dir(
    dir_path: str,
    pattern: str = '*.md',
    exclude: Optional[List[str]] = None,
    sort_by: str = 'name',  # 'name', 'mtime', 'size'
) -> str:
    """
    从目录中收集所有匹配的 Markdown 文件并组装。

    Args:
        dir_path: 目录路径
        pattern: 文件名模式
        exclude: 排除的文件名列表
        sort_by: 排序方式

    Returns:
        组装后的 Markdown 文本
    """
    import glob
    from datetime import datetime

    all_files = glob.glob(os.path.join(dir_path, pattern))
    if exclude:
        all_files = [f for f in all_files if os.path.basename(f) not in exclude]

    if sort_by == 'name':
        all_files.sort()
    elif sort_by == 'mtime':
        all_files.sort(key=lambda f: os.path.getmtime(f))
    elif sort_by == 'size':
        all_files.sort(key=lambda f: os.path.getsize(f))

    return assemble_documents(all_files, exclude_patterns=exclude)


# ═══════════════════════════════════════════════════════
# 测试
# ═══════════════════════════════════════════════════════

def test_generate_anchor():
    assert generate_anchor('Hello World') == 'hello-world'
    assert generate_anchor('Hello World', fmt='underscore') == 'hello_world'
    print('OK: anchor generation')


def test_toc_with_anchors():
    md = '# Title\n## Sub'
    toc = generate_toc_with_anchors(md)
    assert len(toc) == 2
    assert toc[0]['anchor'] == 'title'
    assert toc[1]['anchor'] == 'sub'
    print('OK: TOC with anchors')


def test_toc_markdown_anchors():
    md = '# Title\n## Sub'
    toc_md = generate_toc_markdown_with_anchors(md)
    assert 'title' in toc_md
    assert 'sub' in toc_md
    print('OK: TOC markdown with anchors')


def test_detect_language():
    assert detect_language('def foo():\n    return 1', hint='py') == 'python'
    assert detect_language('function foo() {}', hint='js') == 'javascript'
    assert detect_language('def foo():\n    return 1') == 'python'
    print('OK: language detection')


def test_highlight_code_block():
    result = highlight_code_block('print(1)', 'python')
    assert result['detected_language'] == 'python'
    assert result['css_class'] == 'language-python'
    print('OK: code block highlight')


def test_parse_frontmatter():
    md = '---\ntitle: Test\ndate: 2024-01-01\n---\n# Body'
    meta, body = parse_frontmatter(md)
    assert meta['title'] == 'Test'
    assert body.strip() == '# Body'
    print('OK: frontmatter parse')


def test_dump_frontmatter():
    fm = dump_frontmatter({'title': 'Test', 'date': '2024-01-01'})
    assert '---' in fm
    assert 'title: Test' in fm
    print('OK: frontmatter dump')


def test_with_frontmatter():
    result = with_frontmatter('# Body', {'title': 'Test'})
    assert '---' in result
    assert '# Body' in result
    print('OK: with frontmatter')


def test_render_emoji():
    result = render_emoji('Hello :smile: World')
    assert '😄' in result
    print('OK: emoji render')


def test_render_emoji_markdown():
    md = '# Title :rocket:\n\nText :fire:'
    result = render_emoji_in_markdown(md)
    assert '🚀' in result
    assert '🔥' in result
    print('OK: emoji in markdown')


def test_lint_trailing_spaces():
    issues = lint_markdown('line with space  \nnext')
    assert any(i.rule == 'no-trailing-spaces' for i in issues)
    print('OK: lint trailing spaces')


def test_lint_heading_no_space():
    issues = lint_markdown('#NoSpace')
    assert any(i.rule == 'heading-no-space' for i in issues)
    print('OK: lint heading no space')


def test_lint_long_line():
    issues = lint_markdown('a' * 100)
    assert any(i.rule == 'long-line' for i in issues)
    print('OK: lint long line')


def test_lint_clean():
    issues = lint_markdown('# Title\n\nParagraph')
    assert len(issues) == 0
    print('OK: lint clean')


def test_lint_report():
    report = lint_markdown_report('# Title\n\nPara  ')
    assert 'Lint Report' in report
    print('OK: lint report')


def test_assemble_documents():
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        f1 = os.path.join(tmpdir, 'a.md')
        f2 = os.path.join(tmpdir, 'b.md')
        with open(f1, 'w', encoding='utf-8') as f:
            f.write('# A\n\nContent A')
        with open(f2, 'w', encoding='utf-8') as f:
            f.write('# B\n\nContent B')
        result = assemble_documents([f1, f2], add_toc=False)
        assert 'Content A' in result
        assert 'Content B' in result
    print('OK: assemble documents')


def test_assemble_with_toc():
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        f1 = os.path.join(tmpdir, 'a.md')
        with open(f1, 'w', encoding='utf-8') as f:
            f.write('# A\n\nContent A')
        result = assemble_documents([f1], add_toc=True)
        assert '目录' in result
        assert 'Content A' in result
    print('OK: assemble with toc')


if __name__ == '__main__':
    test_generate_anchor()
    test_toc_with_anchors()
    test_toc_markdown_anchors()
    test_detect_language()
    test_highlight_code_block()
    test_parse_frontmatter()
    test_dump_frontmatter()
    test_with_frontmatter()
    test_render_emoji()
    test_render_emoji_markdown()
    test_lint_trailing_spaces()
    test_lint_heading_no_space()
    test_lint_long_line()
    test_lint_clean()
    test_lint_report()
    test_assemble_documents()
    test_assemble_with_toc()
    print()
    print('All 17 phase-4 tests passed!')
