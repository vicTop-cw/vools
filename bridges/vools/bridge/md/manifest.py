"""
vools.bridge.md manifest — YAML 清单读写

内置极简 YAML 子集解析/序列化器，优先使用 PyYAML。
支持原子写入（临时文件 + rename）。
"""

from __future__ import annotations

import os
import tempfile
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
    lines = text.split("\n")
    result: Dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(-1, result)]  # (indent, container)

    for line in lines:
        if not line.strip() or line.strip().startswith("#"):
            continue

        indent = len(line) - len(line.lstrip())
        content = line.strip()

        # 弹出栈顶直到找到同级或更低缩进（同级 key 应挂父容器）
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()

        current = stack[-1][1]

        if content.startswith("-") and not content.startswith("--"):
            # 列表项
            rest = content[1:].strip()

            # 定位目标 list 容器：优先栈中 list，其次当前 dict 最后一个 list 值
            target = None
            for _, c in reversed(stack):
                if isinstance(c, list):
                    target = c
                    break
            if target is None:
                for k, v in reversed(list(current.items())):
                    if isinstance(v, list):
                        target = v
                        break
            if target is None and isinstance(current, dict):
                # 当前容器是刚创建的空嵌套 dict：升级为 list
                parent = stack[-2][1] if len(stack) >= 2 else None
                if isinstance(parent, dict):
                    for k in parent:
                        if parent[k] is current:
                            lst: list[Any] = []
                            parent[k] = lst
                            stack[-1] = (stack[-1][0], lst)
                            target = lst
                            break
            if target is None:
                continue

            if not rest:
                # 空列表项（旧格式 `-` 换行）：新建 dict 元素，后续子 key 挂它
                entry: dict = {}
                target.append(entry)
                stack.append((indent, entry))
            elif ":" in rest:
                # `- key: value` 内联形式：新建 dict 元素
                key, _, value = rest.partition(":")
                key = key.strip()
                value = value.strip()
                entry = {}
                target.append(entry)
                stack.append((indent, entry))
                if value:
                    entry[key] = _parse_yaml_scalar(value)
                else:
                    entry[key] = {}
            else:
                target.append(_parse_yaml_scalar(rest))
        elif ":" in content:
            # 键值对
            key, _, value = content.partition(":")
            key = key.strip()
            value = value.strip()

            if value:
                if isinstance(current, dict):
                    current[key] = _parse_yaml_scalar(value)
            else:
                # 嵌套结构
                new_dict: dict = {}
                current[key] = new_dict
                stack.append((indent, new_dict))

    return result


def _parse_yaml_scalar(s: str) -> Any:
    """解析 YAML 标量值。"""
    s = s.strip()

    # 字符串（引号）
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1]
    if s.startswith("'") and s.endswith("'"):
        return s[1:-1]

    # 整数
    try:
        return int(s)
    except ValueError:
        pass

    # 布尔
    if s == "true":
        return True
    if s == "false":
        return False

    if s == "null" or s == "~":
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


def _yaml_scalar_str(v: Any) -> str:
    """标量转 YAML 文本（None/bool 需显式表达，避免回读成字符串）。"""
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def _minimal_yaml_dump(data: Dict[str, Any], indent: int = 0) -> str:
    """内置极简 YAML 序列化器。"""
    lines = []
    pad = "  " * indent

    for key, value in data.items():
        if isinstance(value, dict):
            lines.append(f"{pad}{key}:")
            lines.append(_minimal_yaml_dump(value, indent + 1))
        elif isinstance(value, list):
            if not value:
                lines.append(f"{pad}{key}: []")
                continue
            lines.append(f"{pad}{key}:")
            for item in value:
                if isinstance(item, dict):
                    has_nested = any(isinstance(v, (dict, list)) for v in item.values())
                    if has_nested:
                        # 含嵌套结构：旧格式 `-` 换行（解析器兼容）
                        lines.append(f"{pad}  -")
                        lines.append(_minimal_yaml_dump(item, indent + 2))
                    else:
                        # 纯标量：内联 `- key: value`，子字段缩进 4
                        first = True
                        for ik, iv in item.items():
                            if first:
                                lines.append(f"{pad}  - {ik}: {_yaml_scalar_str(iv)}")
                                first = False
                            else:
                                lines.append(f"{pad}    {ik}: {_yaml_scalar_str(iv)}")
                else:
                    lines.append(f"{pad}  - {_yaml_scalar_str(item)}")
        else:
            lines.append(f"{pad}{key}: {_yaml_scalar_str(value)}")

    return "\n".join(lines)


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
    manifest_path = os.path.join(build_dir, "build.yaml")

    # 原子写入：临时文件 + rename
    tmp_fd, tmp_path = tempfile.mkstemp(dir=build_dir, suffix=".yaml.tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
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
    manifest_path = os.path.join(build_dir, "build.yaml")
    if not os.path.exists(manifest_path):
        return None

    with open(manifest_path, "r", encoding="utf-8") as f:
        text = f.read()

    return minimal_yaml_parse(text)
