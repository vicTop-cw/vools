"""
vools.bridge.md parser — Markdown 即代码解析器

从 .md 文件中提取：
- 文件级指令（#! 开头，md 顶部连续行）
- 代码块（fenced code block，带语言标识符和 #! 指令）
- 哈希计算（md_hash + block_hashes）

复用 vools.md 的解析器提取代码块，再叠加 #! 指令解析。
"""
import os, re, hashlib
from dataclasses import dataclass, field
from typing import List, Dict, Optional

# 复用 vools.md 的代码块提取
try:
    from vools.md.parser import parse as _md_parse
    from vools.md.parser import CodeBlock as _MdCodeBlock
    _HAS_VOOLS_MD = True
except ImportError:
    _HAS_VOOLS_MD = False


# ═══════════════════════════════════════════════════════
# 数据类
# ═══════════════════════════════════════════════════════

@dataclass
class FileDirectives:
    """文件级指令"""
    config: Optional[str] = None
    deps: Optional[str] = None
    build_dir: str = ".mdbuild"
    entry: Optional[str] = None
    only: List[str] = field(default_factory=list)


@dataclass
class CodeBlock:
    """代码块（含 #! 指令）"""
    index: int
    language: str
    directives: Dict[str, str]
    content: str
    tag: List[str] = field(default_factory=list)
    source_file: Optional[str] = None  # M3: 来源文件
    imported: bool = False             # M3: 是否来自 import


@dataclass
class ParsedMD:
    """解析结果"""
    path: str
    file_directives: FileDirectives
    blocks: List[CodeBlock]
    md_hash: str
    block_hashes: List[str]


# ═══════════════════════════════════════════════════════
# 文件级指令提取
# ═══════════════════════════════════════════════════════

_FILE_DIRECTIVE_RE = re.compile(r'^#!([a-zA-Z_][\w-]*)(?:\s+(.*))?$')


def _extract_file_directives(text: str) -> tuple[FileDirectives, str]:
    """
    从 md 文本顶部提取文件级指令。

    规则：
    - 文件开头的连续 #! 行
    - 被第一个非 #! 行或空行终止

    Returns:
        (FileDirectives, 剩余文本)
    """
    fd = FileDirectives()
    lines = text.split('\n')
    consumed = 0

    for i, line in enumerate(lines):
        if not line.strip():
            # 空行终止
            if consumed > 0:
                break
            continue
        m = _FILE_DIRECTIVE_RE.match(line.strip())
        if not m:
            # 非 #! 行终止
            break
        key = m.group(1)
        value = m.group(2).strip() if m.group(2) else None

        if key == 'config':
            fd.config = value
        elif key == 'deps':
            fd.deps = value
        elif key == 'build-dir':
            fd.build_dir = value or ".mdbuild"
        elif key == 'entry':
            fd.entry = value
        elif key == 'only':
            if value:
                fd.only = [t.strip() for t in value.split(',')]

        consumed += 1

    remaining = '\n'.join(lines[consumed:])
    return fd, remaining


# ═══════════════════════════════════════════════════════
# 代码块提取（复用 vools.md 或内置）
# ═══════════════════════════════════════════════════════

_FENCE_RE = re.compile(r'^```(\w*)\s*(.*)$')


def _extract_blocks_builtin(text: str) -> List[tuple]:
    """
    内置代码块提取（不依赖 vools.md）。

    Returns:
        [(language, directive_str, content), ...]
    """
    blocks = []
    lines = text.split('\n')
    i = 0

    while i < len(lines):
        m = _FENCE_RE.match(lines[i])
        if not m:
            i += 1
            continue

        language = m.group(1) or ''
        directive_str = m.group(2).strip()
        i += 1

        content_lines = []
        while i < len(lines) and not lines[i].strip().startswith('```'):
            content_lines.append(lines[i])
            i += 1

        # 跳过闭合 ```
        if i < len(lines):
            i += 1

        content = '\n'.join(content_lines)
        blocks.append((language, directive_str, content))

    return blocks


def _extract_blocks_vools_md(text: str) -> List[tuple]:
    """
    复用 vools.md 解析器提取代码块。

    Returns:
        [(language, directive_str, content), ...]
    """
    doc = _md_parse(text)
    blocks = []

    for node in doc.children:
        if isinstance(node, _MdCodeBlock):
            # vools.md 的 CodeBlock 有 language 和 code 属性
            # vools.md 把 ``` 后所有内容都放入 language，例如 "python #!run tag=main"
            # 需要从 language 中分离出真正的语言名和 #! 指令
            lang_raw = (node.language or '').strip()
            fence_directives = ''
            if ' #!' in lang_raw:
                # 形如 "python #!run tag=main"
                idx = lang_raw.index(' #!')
                language = lang_raw[:idx].strip()
                fence_directives = lang_raw[idx + 1:].strip()  # 去掉前导空格
            else:
                language = lang_raw

            # 从 code 中分离指令行（块内 #! 指令）
            lines = node.code.split('\n')
            directive_parts = []
            if fence_directives:
                directive_parts.append(fence_directives)
            content_lines = []

            for line in lines:
                if line.strip().startswith('#!'):
                    directive_parts.append(line.strip())
                else:
                    content_lines.append(line)

            directive_str = ' '.join(directive_parts)
            content = '\n'.join(content_lines)
            blocks.append((language, directive_str, content))

    return blocks


# ═══════════════════════════════════════════════════════
# 哈希计算
# ═══════════════════════════════════════════════════════

def _compute_md_hash(fd: FileDirectives, blocks: List[tuple]) -> str:
    """计算 md_hash：文件级指令 + 全部块内容。"""
    h = hashlib.md5()
    h.update((fd.config or '').encode())
    h.update(b'\n')
    h.update((fd.deps or '').encode())
    h.update(b'\n')
    h.update(fd.build_dir.encode())
    h.update(b'\n')
    h.update((fd.entry or '').encode())
    h.update(b'\n')
    h.update(','.join(fd.only).encode())

    for lang, directives, content in blocks:
        h.update(lang.encode())
        h.update(b'\n')
        h.update(directives.encode())
        h.update(b'\n')
        h.update(content.encode())
        h.update(b'\n')

    return h.hexdigest()


def _compute_block_hash(language: str, directives: str, content: str) -> str:
    """计算单块哈希。"""
    h = hashlib.md5()
    h.update(language.encode())
    h.update(b'\n')
    h.update(directives.encode())
    h.update(b'\n')
    h.update(content.encode())
    return h.hexdigest()


# ═══════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════

def parse_md(md_path: str) -> ParsedMD:
    """
    解析 Markdown 文件，提取指令和代码块。

    Args:
        md_path: .md 文件路径

    Returns:
        ParsedMD 对象
    """
    with open(md_path, 'r', encoding='utf-8') as f:
        text = f.read()

    # 1. 提取文件级指令
    fd, remaining = _extract_file_directives(text)

    # 2. 提取代码块
    if _HAS_VOOLS_MD:
        raw_blocks = _extract_blocks_vools_md(remaining)
    else:
        raw_blocks = _extract_blocks_builtin(remaining)

    # 3. 解析块级指令
    from .directives import parse_block_directives

    blocks: List[CodeBlock] = []
    block_hashes: List[str] = []

    for idx, (language, directive_str, content) in enumerate(raw_blocks):
        directives = parse_block_directives(directive_str)
        tag = directives.get('tag', '').split(',') if directives.get('tag') else []
        tag = [t.strip() for t in tag if t.strip()]

        blocks.append(CodeBlock(
            index=idx,
            language=language,
            directives=directives,
            content=content,
            tag=tag,
        ))

        bh = _compute_block_hash(language, directive_str, content)
        block_hashes.append(bh)

    # 4. 计算 md_hash
    md_hash = _compute_md_hash(fd, raw_blocks)

    return ParsedMD(
        path=md_path,
        file_directives=fd,
        blocks=blocks,
        md_hash=md_hash,
        block_hashes=block_hashes,
    )
