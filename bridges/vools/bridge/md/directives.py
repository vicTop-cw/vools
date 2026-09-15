"""
vools.bridge.md directives — #! 指令定义/解析/校验
"""
import re
from typing import Dict, List

# ═══════════════════════════════════════════════════════
# 指令常量
# ═══════════════════════════════════════════════════════

FILE_DIRECTIVE_KEYS: set[str] = {
    "config", "deps", "build-dir", "entry", "only"
}

BLOCK_DIRECTIVE_KEYS: set[str] = {
    "run", "compile", "only-code", "skip",
    "export", "import", "env", "workdir",
    "args", "stdin", "timeout", "tag", "output",
    "breakpoint", "bp", "prelude", "test", "setup",
}

# ═══════════════════════════════════════════════════════
# 块级指令解析
# ═══════════════════════════════════════════════════════

_DIRECTIVE_RE = re.compile(r'#!([a-zA-Z_][\w-]*)(?:=([^\s]+))?')
_BARE_KEY_RE = re.compile(r'(?:^|\s)([a-zA-Z_][\w-]*)(?:=(\S+))?(?=\s|$)')


def parse_block_directives(directive_str: str) -> Dict[str, str]:
    """
    解析代码块内的 #! 指令。

    支持格式：
    - `#!run` 或 `#!run export=main`（#! 前缀 + 空格分隔的键值对）
    - `#!run #!export=main`（多个 #! 前缀）
    - `tag=main`（裸键值对）
    - `run`（裸指令，无值）

    Returns:
        指令字典
    """
    directives: Dict[str, str] = {}

    if not directive_str or not directive_str.strip():
        directives["run"] = ""
        return directives

    directive_str = directive_str.strip()

    # 先找所有 #! 前缀的指令（#!key 或 #!key=value）
    for match in _DIRECTIVE_RE.finditer(directive_str):
        key = match.group(1)
        value = match.group(2) or ""
        directives[key] = value

    # 再找裸指令（key 或 key=value，不带 #!）
    for match in _BARE_KEY_RE.finditer(directive_str):
        key = match.group(1)
        value = match.group(2)
        if key not in directives:  # 不覆盖已有 #! 前缀的指令
            directives[key] = value or ""

    # 无显式指令时默认 run
    if not directives:
        directives["run"] = ""

    return directives


# ═══════════════════════════════════════════════════════
# 指令校验
# ═══════════════════════════════════════════════════════

def validate_directives(directives: Dict[str, str], language: str) -> List[str]:
    """
    校验指令合法性。

    Args:
        directives: 指令字典
        language: 代码块语言

    Returns:
        错误列表（空列表 = 无错误）
    """
    errors: List[str] = []

    for key in directives:
        if key not in BLOCK_DIRECTIVE_KEYS:
            errors.append(f"未知指令: {key}")

    # 互斥检查
    has_run = "run" in directives
    has_compile = "compile" in directives
    has_only_code = "only-code" in directives
    has_skip = "skip" in directives

    action_count = sum([has_run, has_compile, has_only_code, has_skip])
    if action_count > 1:
        errors.append("块级指令互斥: run/compile/only-code/skip 不能同时使用")

    # timeout 必须是整数
    if "timeout" in directives:
        try:
            int(directives["timeout"])
        except ValueError:
            errors.append(f"timeout 必须是整数: {directives['timeout']}")

    # export 和 import 不能同时用
    if "export" in directives and "import" in directives:
        errors.append("export 和 import 不能同时使用")

    return errors
