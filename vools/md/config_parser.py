"""
vools/md/config_parser.py — 多格式配置解析器

支持格式：
  - JSON:  stdlib json（零依赖）
  - TOML:  tomllib (py3.11+) 或 tomli 回退，最终回退到简化解析器
  - YAML:  PyYAML 可选导入，缺失时回退到简化解析器
  - Lua:   lupa 可选导入，缺失时回退到字符串模板引擎

依赖策略：全部为可选导入（optional import），核心零强制依赖。
"""

from typing import Any, Dict, List, Optional, Union
import json
import re


class ConfigParseError(Exception):
    """配置解析错误"""
    pass


# ═══════════════════════════════════════════════════════════════
# JSON 解析（stdlib，始终可用）
# ═══════════════════════════════════════════════════════════════

def parse_json(text: str) -> Any:
    """解析 JSON 文本 → Python 对象（stdlib json）"""
    # BUG-521: 入参零校验——parse_yaml(None) 静默返回 {}（空配置），
    # parse_toml(None) 抛裸 AttributeError: 'NoneType' object has no attribute
    # 'replace'，parse_json(None) 抛底层 json 的 TypeError（无函数名）。
    if not isinstance(text, str):
        raise TypeError(
            f"parse_json() 的 text 必须是字符串，收到 {type(text).__name__}: {text!r}")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ConfigParseError(f"JSON 解析失败: {e}") from e


# ═══════════════════════════════════════════════════════════════
# TOML 解析（三级回退：tomllib → tomli → 简化解析器）
# ═══════════════════════════════════════════════════════════════

def _toml_parse_with_tomllib(text: str) -> Dict:
    """使用 tomllib (py3.11+ stdlib)"""
    import tomllib
    return tomllib.loads(text)


def _toml_parse_with_tomli(text: str) -> Dict:
    """使用 tomli (兼容 py3.6-3.10)"""
    import tomli
    return tomli.loads(text)


def _toml_parse_simple(text: str) -> Dict:
    """
    简化 TOML 解析器（回退方案）。

    支持：
      - [section] 表头
      - key = value 键值对
      - 字符串 "..." / '...'
      - 整数、浮点数、布尔值
      - 数组 [...]
      - 嵌套表 [a.b.c]
    """
    result: Dict[str, Any] = {}
    current_section = result
    section_stack: List[str] = []

    for line_no, line in enumerate(text.split('\n'), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue

        # [section] 表头
        table_match = re.match(r'^\[([^\]]+)\]$', stripped)
        if table_match:
            parts = table_match.group(1).split('.')
            current_section = result
            for part in parts:
                part = part.strip().strip('"').strip("'")
                if part not in current_section:
                    current_section[part] = {}
                current_section = current_section[part]
            section_stack = parts
            continue

        # key = value
        kv_match = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.+)$', stripped)
        if kv_match:
            key = kv_match.group(1)
            value_str = kv_match.group(2).strip()
            current_section[key] = _toml_parse_value(value_str)
            continue

        # 无法解析的行
        raise ConfigParseError(
            f"TOML 解析失败 (行 {line_no}): 无法解析 '{stripped}'"
        )

    return result


def _toml_parse_value(s: str) -> Any:
    """解析 TOML 值（简化版）"""
    s = s.strip()

    # 字符串
    if (s.startswith('"') and s.endswith('"')) or \
       (s.startswith("'") and s.endswith("'")):
        return s[1:-1]

    # 布尔
    if s == 'true':
        return True
    if s == 'false':
        return False

    # 数组
    if s.startswith('[') and s.endswith(']'):
        inner = s[1:-1].strip()
        if not inner:
            return []
        items = []
        for item in _split_array_items(inner):
            items.append(_toml_parse_value(item.strip()))
        return items

    # 内联表 { key = "value", ... }
    if s.startswith('{') and s.endswith('}'):
        inner = s[1:-1].strip()
        result = {}
        if not inner:
            return result
        pairs = _split_array_items(inner)
        for pair in pairs:
            pair = pair.strip()
            if not pair:
                continue
            kv = re.match(r'([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.+)', pair)
            if kv:
                result[kv.group(1)] = _toml_parse_value(kv.group(2).strip())
        return result

    # 整数
    if re.match(r'^-?\d+$', s):
        return int(s)

    # 浮点数
    if re.match(r'^-?\d+\.\d+$', s):
        return float(s)

    # 未加引号的字符串（简化处理）
    raise ConfigParseError(f"TOML 值解析失败: '{s}'")


def _split_array_items(s: str) -> List[str]:
    """按逗号分割数组元素（处理嵌套括号**与引号内的逗号**）。

    寻虫修复（2026-10-22）：旧实现只看括号深度，`'"a,b", "c"'` 会从
    引号内部切开（实测 3 项），TOML 数组/内联表值含逗号即损坏。
    """
    items = []
    depth = 0
    quote = None
    current = ''
    for ch in s:
        if quote is not None:
            current += ch
            if ch == quote:
                quote = None
        elif ch in ('"', "'"):
            quote = ch
            current += ch
        elif ch in '([{':
            depth += 1
            current += ch
        elif ch in ')]}':
            depth -= 1
            current += ch
        elif ch == ',' and depth == 0:
            items.append(current)
            current = ''
        else:
            current += ch
    if current.strip():
        items.append(current)
    return items


def parse_toml(text: str) -> Dict:
    """
    解析 TOML 文本 → dict。

    回退链：tomllib (3.11+) → tomli → 简化解析器
    """
    # BUG-521: 入参零校验——parse_yaml(None) 静默返回 {}（空配置），
    # parse_toml(None) 抛裸 AttributeError: 'NoneType' object has no attribute
    # 'replace'，parse_json(None) 抛底层 json 的 TypeError（无函数名）。
    if not isinstance(text, str):
        raise TypeError(
            f"parse_toml() 的 text 必须是字符串，收到 {type(text).__name__}: {text!r}")
    # 优先尝试 tomllib
    try:
        return _toml_parse_with_tomllib(text)
    except ImportError:
        pass

    # 尝试 tomli
    try:
        return _toml_parse_with_tomli(text)
    except ImportError:
        pass

    # 回退到简化解析器
    return _toml_parse_simple(text)


# ═══════════════════════════════════════════════════════════════
# YAML 解析（两级回退：PyYAML → 简化解析器）
# ═══════════════════════════════════════════════════════════════

def _yaml_parse_with_pyyaml(text: str) -> Dict:
    """使用 PyYAML"""
    import yaml
    result = yaml.safe_load(text)
    if result is None:
        # 空/注释-only 输入：PyYAML 返回 None，按契约返回空 dict
        return {}
    if not isinstance(result, dict):
        # 标量顶层值（非 dict）也归入空 dict，保持 Dict 返回契约
        return {}
    return result


def _yaml_parse_simple(text: str) -> Dict:
    """
    简化 YAML 解析器（回退方案）。

    支持：
      - key: value 键值对
      - 缩进嵌套
      - 列表项 - item
      - 字符串、整数、浮点、布尔
      - 引号字符串
      - 多行列表
    """
    lines = text.split('\n')
    result, _ = _yaml_parse_lines(lines, 0, 0)
    return result


def _yaml_parse_lines(lines: List[str], start: int, indent: int) -> tuple:
    """递归解析 YAML 行（按缩进层级）"""
    result: Dict[str, Any] = {}
    current_list: List[Any] = None
    i = start

    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.strip().startswith('#'):
            i += 1
            continue

        line_indent = _get_indent(line)
        if line_indent < indent:
            break

        stripped = line.strip()

        # 列表项
        if stripped.startswith('- '):
            item_value = stripped[2:].strip()
            if current_list is None:
                current_list = []
            current_list.append(_yaml_parse_scalar(item_value))
            i += 1
            continue

        # 字典项
        if ':' in stripped:
            # 如果之前在收集列表，先结束它
            if current_list is not None:
                # 将列表附加到上一个键
                _attach_list(result, current_list)
                current_list = None

            key, _, value = stripped.partition(':')
            key = key.strip()
            value = value.strip()

            if value:
                result[key] = _yaml_parse_scalar(value)
            else:
                # 检查下一行是否有更深缩进的子内容
                if i + 1 < len(lines) and _get_indent(lines[i + 1]) > line_indent:
                    child_indent = _get_indent(lines[i + 1])
                    # 检查子内容是列表还是字典
                    next_stripped = lines[i + 1].strip()
                    if next_stripped.startswith('- '):
                        # 列表（寻虫修复 2026-10-22：原实现用共享变量
                        # current_list 收集后又赋给 result[key]，但没把
                        # current_list 置 None——函数末尾 _attach_list 会把
                        # 同一个列表对象再附加一次，列表内容翻倍。
                        # 且 '- name: a' 字典项被当纯文本、其缩进续行被
                        # 丢弃/泄漏到外层。改为逐项解析：
                        #   '- k: v' → 字典项（吸收更深缩进的续行）
                        #   '- scalar' → 标量项
                        items: List[Any] = []
                        j = i + 1
                        while j < len(lines):
                            if not lines[j].strip() or lines[j].strip().startswith('#'):
                                j += 1
                                continue
                            if _get_indent(lines[j]) < child_indent:
                                break
                            item_line = lines[j].strip()
                            if not item_line.startswith('- '):
                                break
                            item_body = item_line[2:].strip()
                            item_col = _get_indent(lines[j]) + 2
                            if ':' in item_body and not (
                                    item_body.startswith('"') and item_body.endswith('"')):
                                # 字典列表项：'- key: value'
                                k, _, v = item_body.partition(':')
                                entry = {k.strip(): _yaml_parse_scalar(v.strip() or '')}
                                j += 1
                                # 吸收同项的更深缩进续行（'  port: 1'）
                                while j < len(lines):
                                    if not lines[j].strip():
                                        j += 1
                                        continue
                                    if _get_indent(lines[j]) >= item_col and ':' in lines[j] and not lines[j].strip().startswith('- '):
                                        k2, _, v2 = lines[j].strip().partition(':')
                                        entry[k2.strip()] = _yaml_parse_scalar(v2.strip() or '')
                                        j += 1
                                    else:
                                        break
                                items.append(entry)
                            else:
                                items.append(_yaml_parse_scalar(item_body))
                                j += 1
                        result[key] = items
                        i = j
                        continue
                    else:
                        # 嵌套字典
                        child, j = _yaml_parse_lines(lines, i + 1, child_indent)
                        result[key] = child
                        i = j
                        continue
                else:
                    result[key] = ""
            i += 1
            continue

        i += 1

    # 处理剩余的列表项
    if current_list is not None:
        _attach_list(result, current_list)

    return result, i


def _get_indent(line: str) -> int:
    """获取行的缩进级别"""
    count = 0
    for ch in line:
        if ch == ' ':
            count += 1
        elif ch == '\t':
            count += 4
        else:
            break
    return count


def _yaml_parse_scalar(value: str) -> Any:
    """解析 YAML 标量值"""
    value = value.strip()

    # 引号字符串
    if (value.startswith('"') and value.endswith('"')) or \
       (value.startswith("'") and value.endswith("'")):
        return value[1:-1]

    # 布尔
    if value.lower() in ('true', 'yes'):
        return True
    if value.lower() in ('false', 'no'):
        return False
    if value.lower() in ('null', '~', 'none'):
        return None

    # 整数
    if re.match(r'^-?\d+$', value):
        return int(value)

    # 浮点数
    if re.match(r'^-?\d+\.\d+$', value):
        return float(value)

    # 普通字符串
    return value


def _attach_list(result: Dict, items: List[Any]):
    """将列表附加到结果字典"""
    # 简化处理：将列表作为最后一个键的值
    if items:
        # 找到最后一个键并附加
        last_key = None
        for k in reversed(result):
            last_key = k
            break
        if last_key is not None:
            existing = result.get(last_key)
            if isinstance(existing, list):
                existing.extend(items)
            else:
                result[last_key] = items


def parse_yaml(text: str) -> Dict:
    """
    解析 YAML 文本 → dict。

    回退链：PyYAML → 简化解析器
    """
    # BUG-521: 入参零校验——parse_yaml(None) 静默返回 {}（空配置），
    # parse_toml(None) 抛裸 AttributeError: 'NoneType' object has no attribute
    # 'replace'，parse_json(None) 抛底层 json 的 TypeError（无函数名）。
    if not isinstance(text, str):
        raise TypeError(
            f"parse_yaml() 的 text 必须是字符串，收到 {type(text).__name__}: {text!r}")
    if not text or not text.strip():
        return {}

    # 优先尝试 PyYAML
    try:
        return _yaml_parse_with_pyyaml(text)
    except ImportError:
        pass

    # 回退到简化解析器
    return _yaml_parse_simple(text)


# ═══════════════════════════════════════════════════════════════
# Lua 配置执行（两级回退：lupa → 字符串模板引擎）
# ═══════════════════════════════════════════════════════════════

def _lua_execute_with_lupa(text: str, context: Optional[Dict] = None) -> Dict:
    """使用 lupa 执行 Lua 配置代码"""
    from lupa import LuaRuntime

    lua = LuaRuntime()

    # 注入上下文
    if context:
        for k, v in context.items():
            lua.globals()[k] = v

    # 执行 Lua 代码
    func = lua.execute(text)
    if callable(func):
        result = func()
    else:
        result = func

    # 转换 Lua table → Python dict
    return _lua_table_to_dict(result)


def _lua_table_to_dict(lua_val) -> Any:
    """将 Lua 值转换为 Python 对象"""
    from lupa import lua_type

    if lua_type(lua_val) == 'NONE':
        return None
    elif lua_type(lua_val) == 'BOOLEAN':
        return bool(lua_val)
    elif lua_type(lua_val) == 'NUMBER':
        return float(lua_val)
    elif lua_type(lua_val) == 'STRING':
        return str(lua_val)
    elif lua_type(lua_val) == 'TABLE':
        # 尝试当作字典
        result = {}
        for key in lua_val.keys():
            result[str(key)] = _lua_table_to_dict(lua_val[key])
        if result:
            return result
        # 可能是数组
        arr = []
        for i in range(1, len(lua_val) + 1):
            arr.append(_lua_table_to_dict(lua_val[i]))
        if arr:
            return arr
        return {}
    return None


def _lua_execute_simple(text: str, context: Optional[Dict] = None) -> Dict:
    """
    简化 Lua 配置执行器（回退方案）。

    支持：
      - return { key = "value", ... } 返回 table
      - string.format 模板
      - 简单变量插值
    """
    # 提取 return 语句
    return_match = re.search(r'return\s+(.+)', text, re.DOTALL)
    if not return_match:
        return {}

    table_str = return_match.group(1).strip()

    # 解析 Lua table 语法
    result = _parse_lua_table(table_str)

    # 应用上下文变量替换
    if context:
        for k, v in context.items():
            result.setdefault(k, v)

    return result


def _parse_lua_table(table_str: str) -> Dict:
    """解析 Lua table 语法 → Python dict"""
    result: Dict[str, Any] = {}
    # 移除外层大括号
    inner = table_str.strip()
    if inner.startswith('{'):
        inner = inner[1:]
    if inner.endswith('}'):
        inner = inner[:-1]

    # 按逗号分割键值对（处理嵌套）
    pairs = _split_table_items(inner)
    for pair in pairs:
        pair = pair.strip()
        if not pair:
            continue
        # 解析 key = value 或 key = "value"
        kv_match = re.match(r'([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.+)', pair)
        if kv_match:
            key = kv_match.group(1)
            value_str = kv_match.group(2).strip()
            result[key] = _parse_lua_value(value_str)
        elif pair.startswith('['):
            # 数组项
            pass

    return result


def _parse_lua_value(s: str) -> Any:
    """解析 Lua 值"""
    s = s.strip()
    # 字符串
    if (s.startswith('"') and s.endswith('"')) or \
       (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    # 数字
    if re.match(r'^-?\d+$', s):
        return int(s)
    if re.match(r'^-?\d+\.\d+$', s):
        return float(s)
    # 布尔
    if s == 'true':
        return True
    if s == 'false':
        return False
    # nil
    if s == 'nil':
        return None
    # table
    if s.startswith('{') and s.endswith('}'):
        return _parse_lua_table(s)
    # 默认字符串
    return s


def _split_table_items(s: str) -> List[str]:
    """按逗号分割 table 元素（处理嵌套大括号与引号内的逗号）。

    寻虫修复（2026-10-22）：同 _split_array_items，旧实现不感知引号，
    `key = "a,b"` 这类 Lua 值会从引号内切开。
    """
    items = []
    depth = 0
    quote = None
    current = ''
    for ch in s:
        if quote is not None:
            current += ch
            if ch == quote:
                quote = None
        elif ch in ('"', "'"):
            quote = ch
            current += ch
        elif ch == '{':
            depth += 1
            current += ch
        elif ch == '}':
            depth -= 1
            current += ch
        elif ch == ',' and depth == 0:
            items.append(current)
            current = ''
        else:
            current += ch
    if current.strip():
        items.append(current)
    return items


def execute_lua(text: str, context: Optional[Dict] = None) -> Dict:
    """
    执行 Lua 配置代码，返回生成的配置 dict。

    Lua 块约定：通过 return 返回一个 table，
    该 table 会被转换为 Python dict。

    回退链：lupa → 字符串模板引擎
    """
    # 优先尝试 lupa
    try:
        return _lua_execute_with_lupa(text, context)
    except ImportError:
        pass

    # 回退到简化解析器
    return _lua_execute_simple(text, context)


# ═══════════════════════════════════════════════════════════════
# 统一入口
# ═══════════════════════════════════════════════════════════════

def parse_config_block(content: str, language: str) -> Any:
    """
    解析配置块内容。

    Args:
        content: 配置块文本内容
        language: "json" | "toml" | "yaml" | "lua"

    Returns:
        解析后的 Python 对象（dict/list/str 等）

    Raises:
        ConfigParseError: 解析失败
    """
    # BUG-521: language=None 抛裸 AttributeError: 'NoneType' object has no attribute
    # 'lower'；content=None 也只会落到下游解析器。
    if not isinstance(language, str) or not language.strip():
        raise ValueError(
            f"parse_config_block() 的 language 必须是非空字符串，收到 "
            f"{type(language).__name__}: {language!r}")
    if not isinstance(content, str):
        raise TypeError(
            f"parse_config_block() 的 content 必须是字符串，收到 "
            f"{type(content).__name__}: {content!r}")
    lang = language.lower().strip()

    if lang == 'json':
        return parse_json(content)
    elif lang == 'toml':
        return parse_toml(content)
    elif lang in ('yaml', 'yml'):
        return parse_yaml(content)
    elif lang == 'lua':
        return execute_lua(content)
    else:
        raise ConfigParseError(f"不支持的配置语言: {language}")


def validate_config(parsed: Any, schema: Optional[Dict] = None) -> bool:
    """
    校验配置是否符合预期结构。

    Args:
        parsed: 解析后的配置对象
        schema: 期望的结构（可选，用于校验）

    Returns:
        True 如果配置有效

    Note:
        基础校验：解析结果必须是最基本类型（dict/list/str/int/float/bool）。
        ``schema`` 给出时再做一层**浅层结构校验**（顶层键必须存在；schema 值为
        类型时要求 isinstance 匹配）。完整 schema 校验可集成 jsonschema 等库。

        BUG-521: 原实现**完全忽略 schema**——传了 schema 也恒返回 True，
        调用方以为校验通过（如 validate_config({"a": "x"}, {"a": int}) -> True）。
    """
    if parsed is None:
        return False
    if not isinstance(parsed, (dict, list, str, int, float, bool)):
        return False
    if schema is None:
        return True
    if not isinstance(schema, dict):
        raise TypeError(
            f"validate_config() 的 schema 必须是 dict 或 None，收到 "
            f"{type(schema).__name__}: {schema!r}")
    if not isinstance(parsed, dict):
        return False
    for _key, _expected in schema.items():
        if _key not in parsed:
            return False
        if isinstance(_expected, type) and not isinstance(parsed[_key], _expected):
            return False
    return True


# ═══════════════════════════════════════════════════════════════
# 配置文本生成
# ═══════════════════════════════════════════════════════════════

def render_config(parsed: Any, language: str) -> str:
    """
    将 Python 对象渲染为指定格式的配置文本。

    Args:
        parsed: Python 对象（dict/list/str 等）
        language: "json" | "toml" | "yaml"

    Returns:
        配置文本

    Raises:
        ConfigParseError: 不支持的渲染格式
    """
    lang = language.lower().strip()

    if lang == 'json':
        return json.dumps(parsed, ensure_ascii=False, indent=2)
    elif lang == 'toml':
        return _render_toml(parsed)
    elif lang in ('yaml', 'yml'):
        return _render_yaml(parsed)
    else:
        raise ConfigParseError(f"不支持的渲染格式: {language}")


def _render_toml(obj: Any, indent: int = 0) -> str:
    """将 Python 对象渲染为 TOML 文本"""
    lines = []
    pad = ' ' * indent

    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(value, dict):
                lines.append(f'{pad}[{key}]')
                lines.append(_render_toml(value, indent + 4))
            elif isinstance(value, list):
                lines.append(f'{pad}{key} = {_toml_value(value)}')
            else:
                lines.append(f'{pad}{key} = {_toml_value(value)}')
    elif isinstance(obj, list):
        lines.append(_toml_value(obj))
    else:
        lines.append(_toml_value(obj))

    return '\n'.join(lines)


def _toml_value(value: Any) -> str:
    """将 Python 值渲染为 TOML 值"""
    if isinstance(value, str):
        return f'"{value}"'
    elif isinstance(value, bool):
        return 'true' if value else 'false'
    elif isinstance(value, (int, float)):
        return str(value)
    elif isinstance(value, list):
        items = ', '.join(_toml_value(v) for v in value)
        return f'[{items}]'
    elif value is None:
        return '""'
    return str(value)


def _render_yaml(obj: Any, indent: int = 0) -> str:
    """将 Python 对象渲染为 YAML 文本"""
    lines = []
    pad = ' ' * indent

    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(value, dict):
                lines.append(f'{pad}{key}:')
                lines.append(_render_yaml(value, indent + 4))
            elif isinstance(value, list):
                lines.append(f'{pad}{key}:')
                for item in value:
                    if isinstance(item, dict):
                        for k2, v2 in item.items():
                            lines.append(f'{pad}  - {k2}: {_yaml_scalar(v2)}')
                    else:
                        lines.append(f'{pad}  - {_yaml_scalar(item)}')
            else:
                lines.append(f'{pad}{key}: {_yaml_scalar(value)}')
    elif isinstance(obj, list):
        for item in obj:
            lines.append(f'{pad}- {_yaml_scalar(item)}')
    else:
        lines.append(f'{pad}{_yaml_scalar(obj)}')

    return '\n'.join(lines)


def _yaml_scalar(value: Any) -> str:
    """将 Python 值渲染为 YAML 标量"""
    if isinstance(value, str):
        if ':' in value or value.startswith(' '):
            return f'"{value}"'
        return value
    elif isinstance(value, bool):
        return 'true' if value else 'false'
    elif value is None:
        return 'null'
    return str(value)


__all__ = [
    'ConfigParseError',
    'parse_json',
    'parse_toml',
    'parse_yaml',
    'execute_lua',
    'parse_config_block',
    'validate_config',
    'render_config',
]
