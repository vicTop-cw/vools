"""
vools.bridge.md deps — TOML 依赖解析与检查

内置极简 TOML 子集解析器，兼容 Python 3.6。
优先使用 tomli (3.11+ tomllib)，降级到内置解析器。
"""
import os, re
from dataclasses import dataclass, field
from typing import Dict, List, Any


# ═══════════════════════════════════════════════════════
# 极简 TOML 解析器
# ═══════════════════════════════════════════════════════

def parse_toml(text: str) -> Dict[str, Dict[str, Any]]:
    """
    解析 TOML 文本（极简子集）。

    支持：
    - 键值对：key = "value" / key = 30
    - 节标题：[section]
    - 数组：key = ["a", "b"]
    - 注释：# 行注释

    不支持：
    - 嵌套表、表数组、多行字符串

    Returns:
        嵌套字典 {section: {key: value}}
    """
    # 优先用 tomli/tomllib
    try:
        import tomllib  # Python 3.11+
        return tomllib.loads(text)
    except ImportError:
        try:
            import tomli
            return tomli.loads(text)
        except ImportError:
            return _minimal_toml_parse(text)


def _minimal_toml_parse(text: str) -> Dict[str, Dict[str, Any]]:
    """内置极简 TOML 解析器。"""
    result: Dict[str, Dict[str, Any]] = {}
    current_section = ""

    for line in text.split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue

        # 节标题
        section_match = re.match(r'^\[([^\]]+)\]', line)
        if section_match:
            current_section = section_match.group(1)
            if current_section not in result:
                result[current_section] = {}
            continue

        # 键值对
        kv_match = re.match(r'^(\w+)\s*=\s*(.+)$', line)
        if kv_match:
            key = kv_match.group(1)
            value_str = kv_match.group(2).strip()

            # 去除行尾注释
            if '#' in value_str:
                value_str = value_str[:value_str.index('#')].strip()

            # 解析值
            value = _parse_toml_value(value_str)

            if not current_section:
                if "_global" not in result:
                    result["_global"] = {}
                result["_global"][key] = value
            else:
                result[current_section][key] = value

    return result


def _parse_toml_value(s: str) -> Any:
    """解析单个 TOML 值。"""
    s = s.strip()

    # 字符串
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1]

    # 整数
    try:
        return int(s)
    except ValueError:
        pass

    # 数组
    if s.startswith('[') and s.endswith(']'):
        items = s[1:-1].split(',')
        return [_parse_toml_value(item.strip()) for item in items if item.strip()]

    # 裸字符串
    return s


# ═══════════════════════════════════════════════════════
# 依赖检查
# ═══════════════════════════════════════════════════════

@dataclass
class DepsReport:
    """依赖检查结果"""
    ok: List[str] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def check_deps(deps_path: str, md_dir: str) -> DepsReport:
    """
    检查依赖。

    Args:
        deps_path: deps.toml 路径
        md_dir: md 文件所在目录

    Returns:
        DepsReport
    """
    report = DepsReport()

    if not deps_path or not os.path.exists(deps_path):
        return report

    with open(deps_path, 'r', encoding='utf-8') as f:
        text = f.read()

    deps = parse_toml(text)

    # 检查 runtime 依赖
    runtime = deps.get('runtime', {})
    for lang, req in runtime.items():
        if _check_language_available(lang):
            report.ok.append(f"{lang} {req}")
        else:
            report.missing.append(f"{lang} {req}")

    # 检查 compiler 依赖
    compilers = deps.get('compilers', {})
    for compiler, req in compilers.items():
        if req == "optional":
            if _check_compiler_available(compiler):
                report.ok.append(f"{compiler} (optional)")
            else:
                report.warnings.append(f"{compiler} 未安装（optional）")
        else:
            if _check_compiler_available(compiler):
                report.ok.append(f"{compiler} {req}")
            else:
                report.missing.append(f"{compiler} {req}")

    return report


def _check_language_available(lang: str) -> bool:
    """检查语言解释器是否可用。"""
    try:
        from vools.bridge import get_helper
        helper = get_helper(lang)
        return helper.is_available()
    except Exception:
        return False


def _check_compiler_available(compiler: str) -> bool:
    """检查编译器是否可用。"""
    try:
        from vools.bridge import manager
        return manager.is_available(compiler)
    except Exception:
        return False
