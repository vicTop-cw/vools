"""highlight.py —— Shiki 代码高亮封装。

通过 Node.js 子进程调用 Shiki，为 .actus.md 中的代码块提供
终端 ANSI 高亮输出和 HTML 高亮输出。

依赖: shiki (npm install -g shiki)
主题: 复用 VS Code 主题 (github-dark, one-dark-pro, dracula 等)
"""

import os
import subprocess
import sys
from typing import Optional


# ── 配置 ──

SHIKI_SCRIPT = os.path.join(os.path.dirname(__file__), "_shiki", "render.mjs")

# 语言映射：文件扩展名 → Shiki 语言标识
LANGUAGE_MAP = {
    "py": "python",
    "python": "python",
    "js": "javascript",
    "javascript": "javascript",
    "ts": "typescript",
    "typescript": "typescript",
    "tsx": "tsx",
    "jsx": "jsx",
    "go": "go",
    "rs": "rust",
    "rust": "rust",
    "sh": "bash",
    "bash": "bash",
    "zsh": "bash",
    "shell": "bash",
    "json": "json",
    "yaml": "yaml",
    "yml": "yaml",
    "toml": "toml",
    "md": "markdown",
    "markdown": "markdown",
    "html": "html",
    "css": "css",
    "sql": "sql",
    "dockerfile": "dockerfile",
    "docker": "dockerfile",
    "ini": "ini",
    "xml": "xml",
}

# fenced code block 语言 → Shiki 语言标识（从 .actus.md 中的语言标记映射）
CODEBLOCK_LANG_MAP = {
    "py": "python",
    "python": "python",
    "js": "javascript",
    "ts": "typescript",
    "tsx": "tsx",
    "go": "go",
    "rs": "rust",
    "sh": "bash",
    "bash": "bash",
    "shell": "bash",
    "json": "json",
    "yaml": "yaml",
    "yml": "yaml",
    "toml": "toml",
    "md": "markdown",
    "html": "html",
    "css": "css",
    "sql": "sql",
    "dockerfile": "dockerfile",
    "cfg": "ini",
    "ini": "ini",
}


def _resolve_lang(lang: str) -> str:
    """解析语言标识。"""
    return CODEBLOCK_LANG_MAP.get(lang.lower(), lang.lower())


def check_shiki_available() -> bool:
    """检查 Shiki 是否可用。"""
    try:
        result = subprocess.run(
            ["node", SHIKI_SCRIPT, "python", "github-dark", "terminal"],
            input="print('test')",
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def highlight_code(code: str, lang: str = "python",
                    theme: str = "github-dark",
                    mode: str = "terminal") -> str:
    """对代码字符串进行高亮。

    参数:
        code: 源代码字符串。
        lang: 语言标识。
        theme: Shiki 主题名称。
        mode: 输出模式，"terminal" (ANSI) 或 "html"。

    返回:
        高亮后的字符串。
    """
    shiki_lang = _resolve_lang(lang)
    try:
        result = subprocess.run(
            ["node", SHIKI_SCRIPT, shiki_lang, theme, mode],
            input=code,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return code  # 失败时返回原代码
        return result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return code


def highlight_file(filepath: str, theme: str = "github-dark",
                   mode: str = "terminal") -> str:
    """对文件内容进行高亮。

    参数:
        filepath: 文件路径。
        theme: Shiki 主题。
        mode: 输出模式。

    返回:
        高亮后的字符串。
    """
    ext = os.path.splitext(filepath)[1].lstrip(".")
    lang = LANGUAGE_MAP.get(ext, ext)
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            code = f.read()
        return highlight_code(code, lang, theme=theme, mode=mode)
    except (OSError, UnicodeDecodeError):
        return ""


def highlight_actus_md(content: str, theme: str = "github-dark",
                       mode: str = "terminal") -> str:
    """对 .actus.md 内容中的代码块进行高亮。

    解析 fenced code blocks (```lang ... ```)，对其中的代码进行高亮，
    非代码部分保持不变。

    参数:
        content: .actus.md 文件内容。
        theme: Shiki 主题。
        mode: 输出模式。

    返回:
        高亮后的内容。
    """
    import re

    result = []
    last_end = 0
    # 匹配 ```lang ... ``` 代码块
    pattern = re.compile(r"```(\w+)\n(.*?)```", re.DOTALL)

    for match in pattern.finditer(content):
        # 添加代码块之前的文本
        result.append(content[last_end:match.start()])
        lang = match.group(1)
        code = match.group(2)
        highlighted = highlight_code(code, lang, theme=theme, mode=mode)
        if mode == "html":
            result.append(f"\n```{lang}\n{highlighted}\n```\n")
        else:
            result.append(f"\n```{lang}\n{highlighted}```\n")
        last_end = match.end()

    # 添加最后一段
    result.append(content[last_end:])
    return "".join(result)


def highlight_actus_file(filepath: str, theme: str = "github-dark",
                         mode: str = "terminal") -> str:
    """读取 .actus.md 文件并对其中代码块进行高亮。"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        return highlight_actus_md(content, theme=theme, mode=mode)
    except (OSError, UnicodeDecodeError):
        return ""


def get_available_themes() -> list:
    """获取可用的 Shiki 主题列表。"""
    return [
        "github-dark",
        "github-light",
        "one-dark-pro",
        "dracula",
        "nord",
        "min-dark",
        "min-light",
        "vitesse-dark",
        "vitesse-light",
        "slack-dark",
        "slack-ochin",
        "solarized-dark",
        "solarized-light",
    ]


def get_available_languages() -> list:
    """获取可用的 Shiki 语言列表。"""
    return sorted(set(LANGUAGE_MAP.values()))


# ── 便捷函数 ──

def preview_terminal(code: str, lang: str = "python",
                    theme: str = "github-dark") -> str:
    """终端高亮预览。"""
    return highlight_code(code, lang, theme=theme, mode="terminal")


def preview_html(code: str, lang: str = "python",
                 theme: str = "github-dark") -> str:
    """HTML 高亮预览。"""
    return highlight_code(code, lang, theme=theme, mode="html")


def preview_file_terminal(filepath: str, theme: str = "github-dark") -> str:
    """文件终端高亮预览。"""
    return highlight_file(filepath, theme=theme, mode="terminal")


def preview_file_html(filepath: str, theme: str = "github-dark") -> str:
    """文件 HTML 高亮预览。"""
    return highlight_file(filepath, theme=theme, mode="html")


__all__ = [
    'CODEBLOCK_LANG_MAP',
    'LANGUAGE_MAP',
    'SHIKI_SCRIPT',
    'check_shiki_available',
    'get_available_languages',
    'get_available_themes',
    'highlight_actus_file',
    'highlight_actus_md',
    'highlight_code',
    'highlight_file',
    'preview_file_html',
    'preview_file_terminal',
    'preview_html',
    'preview_terminal'
]
