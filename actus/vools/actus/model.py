"""动作数据模型与元数据解析（支持 #!cfg JSON 和 .actus.schema.md YAML front-matter）。"""

__all__ = ['Action', 'parse_cfg', 'parse_cfg_from_file', 'parse_action_from_schema_md']

import json
import os
from dataclasses import dataclass, field
from typing import Optional, List

from .errors import ActionError
from .frontmatter import strip_frontmatter, parse_action_metadata
from .dependency import get_resolver

_REQUIRED = ('id', 'name', 'version', 'trust', 'entry')


@dataclass
class Action:
    """一个已解析的动作（含元数据与来源信息）。"""

    meta: dict
    path: str                 # 仓库相对路径，如 actions/hello.actus.md
    sha256: str               # 原始文件（含 front-matter）指纹
    raw: str                  # 原始文件全文
    body: str                 # 剥离 front-matter 后的正文（vools 可解析）
    blocks: List[dict] = field(default_factory=list)  # [{index,language,tag,directives}]
    file_directives: dict = field(default_factory=dict)  # entry/only/build-dir 等

    # —— 便捷读取 ——
    @property
    def id(self) -> str:
        return self.meta['id']

    @property
    def trust(self) -> str:
        return self.meta['trust']

    @property
    def entry(self) -> str:
        return self.meta['entry']

    @property
    def args_schema(self) -> Optional[dict]:
        return self.meta.get('args')

    @property
    def max_instances(self) -> int:
        """最大并发实例数（0=无上限，默认 0）。"""
        return self.meta.get('max_instances', 0)

    @property
    def tags(self) -> list:
        """动作分类标签，用于 AI 搜索和过滤。"""
        return self.meta.get('tags', [])

    @property
    def deps(self) -> list:
        """动作依赖列表（原始值）。"""
        return self.meta.get('deps', [])

    @property
    def dependencies(self) -> list:
        """解析后的依赖对象列表。"""
        from .dependency import get_resolver
        return get_resolver().parse_deps(self.deps)

    def brief(self) -> dict:
        """索引用的动作摘要（不含正文）。"""
        return {
            'id': self.meta['id'],
            'name': self.meta.get('name'),
            'version': self.meta.get('version'),
            'trust': self.meta.get('trust'),
            'entry': self.meta.get('entry'),
            'platform': self.meta.get('platform'),
            'description': self.meta.get('description'),
            'author': self.meta.get('author'),
            'permissions': self.meta.get('permissions'),
            'args': self.meta.get('args'),
            'deprecated': bool(self.meta.get('deprecated', False)),
            'max_instances': self.max_instances,
            'tags': self.tags,
            'deps': self.deps,
            'path': self.path,
            'sha256': self.sha256,
        }


def parse_cfg(body: str) -> dict:
    """从正文解析 ```json #!cfg 内联元数据块。

    规则（docs/03 §2 形式 A）：
    - 取第一个 language=json 且带 #!cfg 指令的代码块；
    - 解析为 dict；缺失/非法即 ActionError(action_invalid)。
    """
    from vools.bridge.md.parser import _extract_blocks_builtin
    from vools.bridge.md.directives import parse_block_directives

    for language, directive_str, content in _extract_blocks_builtin(body):
        directives = parse_block_directives(directive_str)
        if 'cfg' not in directives:
            continue
        if language.strip().lower() != 'json':
            raise ActionError('action_invalid', '#!cfg 元数据块必须是 ```json 标记',
                              {'hint': '见 docs/03 §2 形式 A'})
        try:
            meta = json.loads(content)
        except json.JSONDecodeError as e:
            raise ActionError('action_invalid', f'#!cfg 元数据不是合法 JSON: {e}',
                              {'hint': '见 docs/03 §2'}) from e
        if not isinstance(meta, dict):
            raise ActionError('action_invalid', '#!cfg 元数据必须是 JSON object')
        return meta

    raise ActionError('action_invalid', '缺少 ```json #!cfg 元数据块（docs/03 §2 形式 A）',
                      {'hint': '动作文件必须内联元数据，保证单文件自包含'})


def parse_cfg_from_file(path: str) -> Action:
    """读取动作文件：剥离 AIGC front-matter → 解析元数据 → 摘取块信息。

    支持双格式（docs/03 §2）：
    - 形式 A（JSON）：```json #!cfg 内联元数据块（向后兼容）
    - 形式 B（YAML）：.actus.schema.md 的 YAML front-matter（新规范）

    格式检测优先级：
    1. 文件后缀为 .actus.schema.md → 走 YAML front-matter 解析
    2. 否则 → 走传统 #!cfg JSON 解析
    """
    import hashlib

    from vools.bridge.md.parser import _extract_blocks_builtin
    from vools.bridge.md.directives import parse_block_directives

    with open(path, 'r', encoding='utf-8') as f:
        raw = f.read()

    sha = hashlib.sha256(raw.encode('utf-8')).hexdigest()

    # 格式检测：.actus.schema.md 后缀走 YAML front-matter 解析
    basename = os.path.basename(path)
    is_schema_md = basename.endswith('.actus.schema.md')

    if is_schema_md:
        return _parse_schema_md_action(raw, path, sha)

    # 传统 #!cfg JSON 解析（向后兼容）
    body = strip_frontmatter(raw)
    meta = parse_cfg(body)

    blocks = []
    for i, (language, directive_str, _content) in enumerate(_extract_blocks_builtin(body)):
        d = parse_block_directives(directive_str)
        blocks.append({
            'index': i,
            'language': language.strip().lower(),
            'tag': d.get('tag', '').split(',') if d.get('tag') else [],
            'directives': d,
        })

    # 汇集文件级指令（entry/only/build-dir），供 executor 参考
    fd = {}
    for line in body.split('\n'):
        s = line.strip()
        if s.startswith('#!') and not s.startswith('#!cfg'):
            parts = s[2:].split(None, 1)
            if parts:
                fd[parts[0]] = parts[1].strip() if len(parts) > 1 else ''

    return Action(meta=meta, path=path.replace(os.sep, '/'), sha256=sha,
                  raw=raw, body=body, blocks=blocks, file_directives=fd)


def _parse_schema_md_action(raw: str, path: str, sha: str) -> Action:
    """解析 .actus.schema.md 格式的动作文件。

    结构：
    - 区域 0: AIGC 合规 front-matter（由 strip_frontmatter 剥离）
    - 区域 1: 动作元数据 YAML front-matter（由 parse_action_metadata 解析）
    - 区域 2-7: Markdown 正文 + 结构化代码块
    """
    from vools.bridge.md.parser import _extract_blocks_builtin
    from vools.bridge.md.directives import parse_block_directives

    # 区域 0: 剥离 AIGC 合规 front-matter
    body = strip_frontmatter(raw)

    # 区域 1: 解析动作元数据 YAML front-matter
    meta, remaining_body = parse_action_metadata(body)

    # 校验必填字段
    _validate_meta_required(meta)

    # 从 remaining_body 中提取结构化代码块（用于 Input Schema / Dependencies / 实现）
    blocks = []
    for i, (language, directive_str, content) in enumerate(_extract_blocks_builtin(remaining_body)):
        d = parse_block_directives(directive_str)
        block = {
            'index': i,
            'language': language.strip().lower(),
            'tag': d.get('tag', '').split(',') if d.get('tag') else [],
            'directives': d,
            'content': content,
        }
        blocks.append(block)

        # 提取 Input Schema（json 代码块）
        if block['language'] == 'json' and 'args' not in meta:
            try:
                meta['args'] = json.loads(content)
            except (json.JSONDecodeError, ValueError):
                pass

        # 提取 Dependencies（yaml 代码块）
        if block['language'] == 'yaml' and 'dependencies' not in meta:
            try:
                import yaml as _yaml
                deps = _yaml.safe_load(content)
                if isinstance(deps, dict):
                    meta['dependencies'] = deps
            except Exception:
                pass

    # 汇集文件级指令（从 meta.entry 推导）
    fd = {}
    if meta.get('entry'):
        fd['entry'] = meta['entry']

    return Action(meta=meta, path=path.replace(os.sep, '/'), sha256=sha,
                  raw=raw, body=remaining_body, blocks=blocks, file_directives=fd)


def parse_action_from_schema_md(raw: str, path: str = '') -> Action:
    """从 .actus.schema.md 的原始文本解析为 Action。

    供编辑器/IDE 集成使用，无需读取文件。
    """
    import hashlib
    sha = hashlib.sha256(raw.encode('utf-8')).hexdigest()
    return _parse_schema_md_action(raw, path, sha)


def _validate_meta_required(meta: dict) -> None:
    """校验必填字段。"""
    for key in _REQUIRED:
        if key not in meta:
            raise ActionError('action_invalid', f'缺少必填字段: {key}',
                              {'hint': '见 ACTUS_SCHEMA_SPEC.md 区域 1'})
