"""
vools.bridge.md manifest — YAML 清单读写

内置极简 YAML 子集解析/序列化器，优先使用 PyYAML。
支持原子写入（临时文件 + rename）。
"""
import os, tempfile
from typing import Dict, Any, Optional


# ═══════════════════════════════════════════════════════
# YAML 解析（优先 PyYAML，降级内置）
# ═══════════════════════════════════════════════════════

def minimal_yaml_parse(text: str) -> Dict[str, Any]:
    """
    解析 YAML 文本（极简子集）。

    支持：
    - 映射：key: value
    - 列表：- item
    - 嵌套映射：缩进 2 空格
    - 标量：字符串、整数

    Returns:
        嵌套字典
    """
    try:
        import yaml
        return yaml.safe_load(text) or {}
    except ImportError:
        return _minimal_yaml_parse(text)


def _minimal_yaml_parse(text: str) -> Dict[str, Any]:
    """内置极简 YAML 解析器。"""
    lines = text.split('\n')
    result: Dict[str, Any] = {}
    stack: list[tuple[int, dict]] = [(-1, result)]

    for line in lines:
        if not line.strip() or line.strip().startswith('#'):
            continue

        indent = len(line) - len(line.lstrip())
        content = line.strip()

        # 弹出栈顶直到找到同级或更高缩进
        while stack and indent < stack[-1][0]:
            stack.pop()

        current = stack[-1][1]

        if content.startswith('- '):
            # 列表项
            item = content[2:].strip()
            if not isinstance(current, list):
                # 找到最近的 list key
                key_path = list(stack)[-1][1]
                for k, v in reversed(list(stack)):
                    if isinstance(v, dict) and len(v) > 0:
                        last_key = list(v.keys())[-1]
                        if isinstance(v[last_key], list):
                            v[last_key].append(_parse_yaml_scalar(item))
                            break
            else:
                current.append(_parse_yaml_scalar(item))
        elif ':' in content:
            # 键值对
            key, _, value = content.partition(':')
            key = key.strip()
            value = value.strip()

            if value:
                current[key] = _parse_yaml_scalar(value)
            else:
                # 嵌套结构
                new_dict: Dict[str, Any] = {}
                current[key] = new_dict
                stack.append((indent, new_dict))

    return result


def _parse_yaml_scalar(s: str) -> Any:
    """解析 YAML 标量值。"""
    s = s.strip()

    # 字符串（引号）
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]

    # 整数
    try:
        return int(s)
    except ValueError:
        pass

    # 布尔
    if s == 'true':
        return True
    if s == 'false':
        return False

    if s == 'null' or s == '~':
        return None

    return s


# ═══════════════════════════════════════════════════════
# YAML 序列化（优先 PyYAML，降级内置）
# ═══════════════════════════════════════════════════════

def minimal_yaml_dump(data: Dict[str, Any]) -> str:
    """
    序列化字典为 YAML 文本。

    Args:
        data: 字典数据

    Returns:
        YAML 格式字符串
    """
    try:
        import yaml
        return yaml.safe_dump(data, allow_unicode=True, default_flow_style=False)
    except ImportError:
        return _minimal_yaml_dump(data)


def _minimal_yaml_dump(data: Dict[str, Any], indent: int = 0) -> str:
    """内置极简 YAML 序列化器。"""
    lines = []
    pad = '  ' * indent

    for key, value in data.items():
        if isinstance(value, dict):
            lines.append(f'{pad}{key}:')
            lines.append(_minimal_yaml_dump(value, indent + 1))
        elif isinstance(value, list):
            lines.append(f'{pad}{key}:')
            for item in value:
                if isinstance(item, dict):
                    lines.append(f'{pad}  -')
                    lines.append(_minimal_yaml_dump(item, indent + 2))
                else:
                    lines.append(f'{pad}  - {item}')
        else:
            lines.append(f'{pad}{key}: {value}')

    return '\n'.join(lines)


# ═══════════════════════════════════════════════════════
# 清单读写
# ═══════════════════════════════════════════════════════

def write_manifest(build_dir: str, report: Dict[str, Any]) -> str:
    """
    原子写入 build.yaml。

    Args:
        build_dir: 产物根目录
        report: 执行报告字典

    Returns:
        写入的文件路径
    """
    manifest_path = os.path.join(build_dir, 'build.yaml')

    # 原子写入：临时文件 + rename
    tmp_fd, tmp_path = tempfile.mkstemp(dir=build_dir, suffix='.yaml.tmp')
    try:
        with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
            f.write(minimal_yaml_dump(report))
        os.replace(tmp_path, manifest_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    return manifest_path


def read_manifest(build_dir: str) -> Optional[Dict[str, Any]]:
    """
    读取 build.yaml。

    Returns:
        清单字典，不存在返回 None
    """
    manifest_path = os.path.join(build_dir, 'build.yaml')
    if not os.path.exists(manifest_path):
        return None

    with open(manifest_path, 'r', encoding='utf-8') as f:
        text = f.read()

    return minimal_yaml_parse(text)
