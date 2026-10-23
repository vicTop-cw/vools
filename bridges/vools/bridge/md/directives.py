"""
vools.bridge.md directives — #! 指令定义/解析/校验
"""


__all__ = [
    "parse_block_directives",
    "validate_directives",
]

import re
from typing import Dict, List, Set

# ═══════════════════════════════════════════════════════
# 指令常量
# ═══════════════════════════════════════════════════════

FILE_DIRECTIVE_KEYS: Set[str] = {"config", "deps", "build-dir", "entry", "only"}

BLOCK_DIRECTIVE_KEYS: Set[str] = {
    "run",
    "compile",
    "only-code",
    "skip",
    "export",
    "import",
    "env",
    "workdir",
    "args",
    "stdin",
    "timeout",
    "tag",
    "output",
    "breakpoint",
    "bp",
    "prelude",
    "test",
    "setup",
    "name",
    # webview2 指令
    "title",
    "width",
    "height",
    "resizable",
    "fullscreen",
    "blocking",
    "html",
    "inject",
    # 富内容展示指令（计划 §4.2，P1）
    "svg",
    "rich",
    "level",
    # 折叠支持（新增）
    "fold",
    "collapse",
    "fold-label",
    # MCP 调用块
    "server",
    "tool",
    # ── 新增（角色 / 协议 / 数据库 / 静态块）──
    # 语义角色
    "role",
    # actus 动作配置块裸指令
    "configs",
    # protocol（http / mcp）
    "target",
    "method",
    "headers",
    "body",
    "url",
    # static 块
    "format",
    "schema",
    "validate",
    "render",
    "on_error",
    "quiet",
    "out",
}

# ═══════════════════════════════════════════════════════
# 块级指令解析
# ═══════════════════════════════════════════════════════

_DIRECTIVE_RE = re.compile(r'#!([a-zA-Z_][\w-]*)(?:=("[^"]*"|\'[^\']*\'|\S+))?')
# 裸 key=value：值支持**带引号且含空格**（`title="Calculator App"`）。
# 原模式值只取 `\S+`，于是 `title="Calculator App"` 被空格截断成 `"Calculator`，
# 且引号原样保留（实测种子动作的 title 解析出 `'"Calculator"'`）。
_BARE_KEY_RE = re.compile(
    r'(?:^|\s)([a-zA-Z_][\w-]*)(?:=("[^"]*"|\'[^\']*\'|\S*))?(?=\s|$)')


def _strip_quotes(value: str) -> str:
    """去掉成对的包裹引号（'…' 或 "…"）。"""
    if value and len(value) >= 2 and value[0] in ('"', "'") and value[-1] == value[0]:
        return value[1:-1]
    return value

# 支持空格分隔值的指令（如 `#!import d.md`、`#!config path.toml`、`import d.md`）。
# 这些指令的值通常是一个路径/URL/标识符，不含空格；
# 其它指令（如 `#!run export=main`）仍走 `_BARE_KEY_RE`。
_SPACE_VALUE_RE = re.compile(
    r'#?(import|config|schema|url|target|format|role|out|on_error|workdir|prelude)\s+(\S+)'
)


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
        # 去除引号（支持带空格的值，如 server="python a.py"）
        if len(value) >= 2 and value[0] in ('"', "'") and value[-1] == value[0]:
            value = value[1:-1]
        directives[key] = value

    # 回填 #!key value（空格分隔）的指令值，如 `#!import d.md`
    for match in _SPACE_VALUE_RE.finditer(directive_str):
        key = match.group(1)
        val = match.group(2)
        if not directives.get(key) and val:
            directives[key] = val

    # 再找裸指令（key 或 key=value，不带 #!）
    for match in _BARE_KEY_RE.finditer(directive_str):
        key = match.group(1)
        value = match.group(2)
        if key not in directives:  # 不覆盖已有 #! 前缀的指令
            directives[key] = _strip_quotes(value or "")

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

    # level 必须是 1-4 整数（富内容展示档位，计划 §4.2）
    if "level" in directives:
        try:
            lv = int(directives["level"])
        except ValueError:
            errors.append(f"level 必须是整数: {directives['level']}")
        else:
            if lv not in (1, 2, 3, 4):
                errors.append(f"level 必须是 1-4: {directives['level']}")

    # 折叠指令校验（新增）
    fold_val = directives.get("fold", "").strip().lower()
    if fold_val and fold_val not in ("auto", "manual"):
        errors.append(f"fold 值只允许 auto/manual: {directives['fold']}")

    collapse_val = directives.get("collapse", "").strip().lower()
    if collapse_val and collapse_val not in ("true", "false", "1", "0", "yes", "no", "on", "off"):
        errors.append(f"collapse 值只允许 true/false: {directives['collapse']}")

    fold_label = directives.get("fold-label", "")
    if fold_label and len(fold_label) > 30:
        errors.append(f"fold-label 长度不能超过 30 字符: {len(fold_label)}")

    # 富内容块（html/svg/rich）与执行指令互斥：富内容只做展示，不执行。
    # 无指令块会被 parse_block_directives 默认注入 {"run": ""}，空值放行（默认展示）。
    if language in ("html", "svg", "rich"):
        if "compile" in directives:
            errors.append(f"{language} 块是富内容展示块，不能带 compile 指令")
        if "run" in directives and directives["run"]:
            errors.append(f"{language} 块是富内容展示块，不能带 run= 执行指令")

    # ── 新增校验 ──

    # role 值校验
    if "role" in directives:
        role = directives["role"].strip().lower()
        valid_roles = {
            "deps", "runtime", "legacy", "gen-config", "action-config",
            "data", "diagram", "math", "build", "template", "generic",
        }
        if role and role not in valid_roles:
            errors.append(f"role 值只允许 {sorted(valid_roles)}: {directives['role']}")

    # configs 裸指令校验（#!configs 无值）
    if "configs" in directives and directives["configs"].strip():
        errors.append("configs 是裸指令，不接受值")

    # validate 值校验（syntax / schema / none）
    if "validate" in directives:
        val = directives["validate"].strip().lower()
        if val and val not in ("syntax", "schema", "none"):
            errors.append(f"validate 值只允许 syntax/schema/none: {directives['validate']}")

    # schema 必须与 json/yaml 块搭配
    if "schema" in directives and directives["schema"].strip():
        if language not in ("json", "yaml", "yml"):
            errors.append(f"schema 指令仅支持 json/yaml/yml 块（当前 {language}）")

    # method 值校验（http 块）
    if "method" in directives:
        method = directives["method"].strip().upper()
        valid_methods = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}
        if method and method not in valid_methods:
            errors.append(f"method 值只允许 {sorted(valid_methods)}: {directives['method']}")

    # on_error 值校验（fail / skip / report）
    if "on_error" in directives:
        val = directives["on_error"].strip().lower()
        if val and val not in ("fail", "skip", "report"):
            errors.append(f"on_error 值只允许 fail/skip/report: {directives['on_error']}")

    # target / url / headers / body 必须在协议或数据库块上
    for directive_key, allowed_langs in (
        ("headers", ("http",)),
        ("body", ("http",)),
        ("url", ("http",)),
        ("method", ("http",)),
    ):
        if directive_key in directives and directives[directive_key].strip():
            if language not in allowed_langs:
                errors.append(
                    f"{directive_key} 指令仅支持 {allowed_langs} 块（当前 {language}）"
                )

    # target 必须用于 database / protocol / build 块
    if "target" in directives and directives["target"].strip():
        allowed = (
            "sql", "sqlite", "mysql", "postgresql", "pgsql", "http", "mcp",
            "makefile", "make",
        )
        if language not in allowed:
            errors.append(f"target 指令仅支持 {allowed} 块（当前 {language}）")

    return errors

