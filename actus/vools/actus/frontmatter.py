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


def strip_frontmatter(text: str) -> str:
    """剥离首个 YAML front-matter 区段，返回其余正文。

    - 文件不以 --- 开头 → 原样返回；
    - 只有开头的 --- 无闭合 → 原样返回（交给下游按规范报错）；
    - 闭合行之后的全部内容原样返回（保留换行结构）。
    """
    lines = text.split('\n')
    if not lines or lines[0].strip() != _FM_OPEN:
        return text.lstrip('\n') if text.startswith('\n') else text
    for i in range(1, len(lines)):
        if lines[i].strip() == _FM_CLOSE:
            return '\n'.join(lines[i + 1:]).lstrip('\n')
    return text


def parse_action_metadata(text: str) -> tuple:
    """解析 .actus.schema.md 区域 1 的 YAML front-matter 元数据。

    返回 (meta_dict, remaining_body)：
    - meta_dict: 解析后的元数据字典（无 front-matter 时为 {}）
    - remaining_body: 剥离元数据后的正文（保留换行结构）

    规则：
    - 正文不以 --- 开头 → 返回 ({}, text)
    - 只有开头的 --- 无闭合 → 返回 ({}, text)
    - 解析失败 → 抛出 ActionError
    """
    lines = text.split('\n')
    if not lines or lines[0].strip() != _FM_OPEN:
        return {}, text

    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == _FM_CLOSE:
            end_idx = i
            break
    if end_idx is None:
        return {}, text

    yaml_text = '\n'.join(lines[1:end_idx])
    remaining = '\n'.join(lines[end_idx + 1:]).lstrip('\n')

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
