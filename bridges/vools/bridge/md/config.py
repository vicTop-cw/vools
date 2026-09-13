"""
vools.bridge.md config — Lua 配置加载

复用 vools.bridge.lua 桥接执行 Lua 配置代码，结果 JSON 回传。
"""
import os, json
from typing import Dict, Any, Optional


def load_config(config_path: Optional[str], md_dir: str) -> Dict[str, Any]:
    """
    加载 Lua 配置文件。

    Args:
        config_path: 配置文件路径（None 时自动查找同目录 config.lua）
        md_dir: md 文件所在目录

    Returns:
        配置字典
    """
    if config_path is None:
        # 自动查找
        auto_path = os.path.join(md_dir, "config.lua")
        if os.path.exists(auto_path):
            config_path = auto_path
        else:
            return {}

    if not config_path or not os.path.exists(config_path):
        return {}

    with open(config_path, 'r', encoding='utf-8') as f:
        lua_code = f.read()

    return _execute_lua_config(lua_code, config_path)


def load_config_from_block(block, helper) -> Dict[str, Any]:
    """
    从 #!config 代码块加载配置。

    Args:
        block: CodeBlock 对象
        helper: bridge.lua 的 helper 对象

    Returns:
        配置字典
    """
    if not block or not block.language == "lua":
        return {}

    try:
        result = helper.execute_code(block.content, func_name="__md_config")
        # result 应该是 JSON 字符串或 dict
        if isinstance(result, bytes):
            result = result.decode('utf-8')
        if isinstance(result, str):
            return json.loads(result)
        return result if isinstance(result, dict) else {}
    except Exception:
        return {}


def _execute_lua_config(lua_code: str, config_path: str) -> Dict[str, Any]:
    """
    通过 bridge.lua 执行 Lua 配置代码。

    Args:
        lua_code: Lua 代码
        config_path: 配置文件路径（用于错误提示）

    Returns:
        配置字典
    """
    try:
        from vools.bridge import get_helper
        helper = get_helper("lua")
        if not helper.is_available():
            return {}

        # 包装成返回 JSON 的 Lua 代码
        wrapper = f'''
        local result = (function()
            {lua_code}
        end)()
        return json.encode(result or {{}})
        '''

        result = helper.execute_code(wrapper, func_name="__md_config")
        if isinstance(result, bytes):
            result = result.decode('utf-8')
        if isinstance(result, str):
            return json.loads(result)
        return result if isinstance(result, dict) else {}

    except ImportError:
        return {}
    except Exception:
        return {}
