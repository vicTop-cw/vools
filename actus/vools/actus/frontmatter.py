"""AIGC 声明式 YAML 前置区剥离 + 动作元数据解析。

Actus 仓库内所有书写文件（含动作）头部带 AIGC 合规 front-matter（--- 包裹的
声明式 YAML，非 Toml 风格）。vools.bridge.md 的文件级指令提取要求 `#!` 行位于
文件开头，因此执行核心必须先剥离 front-matter 再交由 vools 解析。
剥离只裁剪首部 `---...---` 区段，不修改落盘文件（执行核心对书写物只读）。

新版 .actus.schema.md 格式（v0.1+）：
- strip_frontmatter() 剥离区域 0（AIGC 合规留痕）
- parse_action_metadata() 解析区域 1（动作元数据 YAML front-matter）
"""

__all__ = ['strip_frontmatter', 'parse_action_metadata']

_FM_OPEN = '---'
_FM_CLOSE = '---'

# AIGC 合规块的特征键（区域 0）——strip_frontmatter 只剥这一块，
# 不再无差别剥首个 front-matter（存量 bug：单 front-matter 的 .actus.schema.md
# 会被剥掉唯一元数据块，导致 parse_action_metadata 拿到空 meta）。
_AIGC_KEYS = ('AIGC', 'aigc', 'generated-by', 'generated-by-at')


def _split_frontmatter_blocks(text: str):
    """把文件拆成 [(kind, yaml_text, body_after), ...] front-matter 序列 + 尾随正文。

    kind ∈ ('aigc', 'meta')：按块内特征键判别。
    返回 (blocks, body)：blocks 是前导 front-matter 块列表，body 是最后一个
    front-matter 闭合行之后的正文。
    """
    lines = text.split('\n')
    blocks = []
    i = 0
    # 跳过文件开头的空行（不改变既有"不以 --- 开头 → 原样返回"语义）
    while i < len(lines) and not lines[i].strip():
        i += 1
    while i < len(lines) and lines[i].strip() == _FM_OPEN:
        end_idx = None
        for j in range(i + 1, len(lines)):
            if lines[j].strip() == _FM_CLOSE:
                end_idx = j
                break
        if end_idx is None:
            break  # 无闭合 → 不当 front-matter（交给下游按规范报错）
        yaml_text = '\n'.join(lines[i + 1:end_idx])
        # 判别：任一行以 AIGC:/aigc:/generated-by: 起始 → AIGC 合规块，否则元数据块
        kind = 'meta'
        for ln in yaml_text.split('\n'):
            if ln.strip().startswith(('AIGC:', 'aigc:', 'generated-by:')):
                kind = 'aigc'
                break
        blocks.append((kind, yaml_text))
        i = end_idx + 1
    return blocks, '\n'.join(lines[i:]).lstrip('\n')


def strip_frontmatter(text: str) -> str:
    """剥离区域 0（AIGC 合规留痕），返回其余正文（含区域 1 元数据 front-matter）。

    - 文件不以 --- 开头 → 原样返回；
    - 只有开头的 --- 无闭合 → 原样返回（交给下游按规范报错）；
    - **只剥 AIGC 特征块**：元数据块（含 id/name/... 等动作字段）原样保留，
      供 parse_action_metadata 解析（存量 bug 修复：此前无差别剥首个块，
      单 front-matter 的 .actus.schema.md 会丢掉唯一元数据）。
    """
    blocks, body = _split_frontmatter_blocks(text)
    if not blocks:
        return text.lstrip('\n') if text.startswith('\n') else text
    # 把非 AIGC 块重新拼回正文前部（它们本来就是元数据，不是要剥的合规块）
    kept = []
    for kind, yaml_text in blocks:
        if kind != 'aigc':
            kept.append(f'{_FM_OPEN}\n{yaml_text}\n{_FM_CLOSE}')
    prefix = ('\n'.join(kept) + '\n') if kept else ''
    return (prefix + body).lstrip('\n')


def parse_action_metadata(text: str) -> tuple:
    """解析 .actus.schema.md 区域 1 的 YAML front-matter 元数据。

    返回 (meta_dict, remaining_body)：
    - meta_dict: 解析后的元数据字典（无 front-matter 时为 {}）
    - remaining_body: 剥离元数据后的正文（保留换行结构）

    规则：
    - 正文不以 --- 开头 → 返回 ({}, text)
    - 只有开头的 --- 无闭合 → 返回 ({}, text)
    - 解析失败 → 抛出 ActionError
    - AIGC 合规块（区域 0）自动跳过，只取元数据块（区域 1）
    """
    blocks, body = _split_frontmatter_blocks(text)
    meta_blocks = [b for b in blocks if b[0] == 'meta']
    if not meta_blocks:
        return {}, text

    yaml_text = meta_blocks[0][1]
    # 若 AIGC 块在元数据块之前，它已被 _split 剔除；remaining 需要把
    # 后续非首个元数据块之后的内容拼回来（正常文件只有一个元数据块）
    remaining = body
    for kind, yt in meta_blocks[1:]:
        remaining = f'{_FM_OPEN}\n{yt}\n{_FM_CLOSE}\n{remaining}'

    try:
        import yaml
        meta = yaml.safe_load(yaml_text)
    except ImportError:
        # 无 PyYAML 时退化为简单 key: value 解析
        meta = _simple_yaml_parse(yaml_text)
    except Exception as e:
        from .errors import ActionError
        raise ActionError('action_invalid', f'动作元数据 YAML 解析失败: {e}') from e

    if not isinstance(meta, dict):
        from .errors import ActionError
        raise ActionError('action_invalid', '动作元数据必须是 YAML mapping')

    return meta, remaining


def _simple_yaml_parse(text: str) -> dict:
    """极简 YAML 解析（仅支持 key: value 格式，无嵌套）。

    用于 PyYAML 不可用时的降级方案。
    """
    result = {}
    for line in text.split('\n'):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        if ':' in stripped:
            key, _, value = stripped.partition(':')
            key = key.strip()
            value = value.strip()
            # 简单类型推断
            if value.startswith('[') and value.endswith(']'):
                # 简单列表
                value = [v.strip().strip("'\"") for v in value[1:-1].split(',') if v.strip()]
            elif value.lower() in ('true', 'yes'):
                value = True
            elif value.lower() in ('false', 'no'):
                value = False
            elif value.lower() in ('null', '~', ''):
                value = None
            else:
                # 尝试数字
                try:
                    value = int(value)
                except ValueError:
                    try:
                        value = float(value)
                    except ValueError:
                        value = value.strip("'\"")
            result[key] = value
    return result
