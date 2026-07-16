"""
vools.bridge.lua.compiler - Lua 语言桥接编译器实现

提供 LuaBridge 类，继承 LangBridge 抽象基类，实现 Lua 特定的代码生成、
解释执行和调用逻辑。
"""

import os
import sys
import tempfile
import hashlib
import platform
import inspect
import json
import shutil
import subprocess
import threading
import textwrap
from typing import Any, Optional

from .._base import LangBridge, FunctionSpec, FunctionParser
from ..core.types import LangType

# ----------------------------------------------------------------------------
# 平台判断
# ----------------------------------------------------------------------------
_IS_WINDOWS = platform.system() == 'Windows'
_IS_LINUX = platform.system() == 'Linux'
_IS_MACOS = platform.system() == 'Darwin'

# 编译器名
_LUA_COMPILER = 'lua'
_LUA_COMPILER_ALT = 'lua5.3'
_LUA_COMPILER_LUAJIT = 'luajit'

# 常用 PATH 搜索
_LUA_SEARCH_PATHS_WINDOWS = [
    r"C:\lua",
    r"C:\Program Files\Lua",
    os.path.expanduser("~/AppData/Local/Programs/Lua"),
]
_LUA_SEARCH_PATHS_UNIX = [
    "/usr/bin",
    "/usr/local/bin",
    "/opt/homebrew/bin",
    os.path.expanduser("~/.luarocks/bin"),
]


def _setup_lua_env() -> str:
    """设置 Lua 运行环境（PATH）；返回 lua 可执行路径"""
    search_paths = _LUA_SEARCH_PATHS_WINDOWS if _IS_WINDOWS else _LUA_SEARCH_PATHS_UNIX
    env_paths = os.environ.get('PATH', '').split(os.pathsep)

    for p in search_paths:
        if os.path.exists(p) and p not in env_paths:
            os.environ['PATH'] = p + os.pathsep + os.environ.get('PATH', '')

    return _get_lua_path()


def _get_lua_path() -> str:
    """获取 lua 解释器路径"""
    # 依次尝试 lua, lua5.3, luajit
    for compiler in (_LUA_COMPILER, _LUA_COMPILER_ALT, _LUA_COMPILER_LUAJIT):
        found = shutil.which(compiler)
        if found:
            return found

    search_paths = _LUA_SEARCH_PATHS_WINDOWS if _IS_WINDOWS else _LUA_SEARCH_PATHS_UNIX
    exe_suffix = '.exe' if _IS_WINDOWS else ''
    for compiler in (_LUA_COMPILER, _LUA_COMPILER_ALT, _LUA_COMPILER_LUAJIT):
        for p in search_paths:
            candidate = os.path.join(p, compiler + exe_suffix)
            if os.path.exists(candidate):
                return candidate
    return _LUA_COMPILER


_LUA_PATH = _setup_lua_env()


def lua_compiler_available() -> bool:
    """检查 Lua 解释器是否可用（执行 `lua -v`）"""
    try:
        result = subprocess.run(
            [_LUA_PATH, '-v'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, OSError):
        return False
    except Exception:
        return False


# ----------------------------------------------------------------------------
# 缓存目录
# ----------------------------------------------------------------------------
_LUA_CACHE_DIR = os.path.join(tempfile.gettempdir(), 'vools_lua_cache')


# ----------------------------------------------------------------------------
# Python ↔ Lua 类型映射
# ----------------------------------------------------------------------------

_LUA_TYPE_ALIASES = {
    'int': 'integer',
    'integer': 'integer',
    'float': 'number',
    'double': 'number',
    'number': 'number',
    'bool': 'boolean',
    'boolean': 'boolean',
    'str': 'string',
    'string': 'string',
    'list': 'table',
    'array': 'table',
    'dict': 'table',
    'hash': 'table',
    'table': 'table',
    'nil': 'nil',
    'none': 'nil',
    'nonetype': 'nil',
}


def get_lua_type(py_type):
    """根据 Python 类型获取 Lua 端类型字符串"""
    if py_type in {
        int: 'integer',
        float: 'number',
        bool: 'boolean',
        str: 'string',
        bytes: 'string',
        list: 'table',
        dict: 'table',
        tuple: 'table',
        type(None): 'nil',
    }:
        return {
            int: 'integer',
            float: 'number',
            bool: 'boolean',
            str: 'string',
            bytes: 'string',
            list: 'table',
            dict: 'table',
            tuple: 'table',
            type(None): 'nil',
        }.get(py_type, 'string')

    if isinstance(py_type, str):
        normalized = py_type.strip().lower()
        if normalized in _LUA_TYPE_ALIASES:
            return _LUA_TYPE_ALIASES[normalized]
        short = normalized.split('.')[-1]
        if short in _LUA_TYPE_ALIASES:
            return _LUA_TYPE_ALIASES[short]
        return 'string'

    return 'string'


def infer_lua_argtypes(args):
    """根据运行时值推断 Lua 端入参类型"""
    result = []
    for arg in args:
        if isinstance(arg, bool):
            result.append('boolean')
        elif isinstance(arg, int):
            result.append('integer')
        elif isinstance(arg, float):
            result.append('number')
        elif isinstance(arg, str):
            result.append('string')
        elif isinstance(arg, (bytes, bytearray)):
            result.append('string')
        elif isinstance(arg, (list, tuple)):
            result.append('table')
        elif isinstance(arg, dict):
            result.append('table')
        else:
            result.append('string')
    return result


# ----------------------------------------------------------------------------
# Lua 代码生成
# ----------------------------------------------------------------------------

def _preprocess_lua_body(body: str, auto_signature: bool) -> str:
    """预处理 Lua 函数体"""
    if not auto_signature:
        return body

    # 使用 textwrap.dedent 保留格式
    indented_lines = []
    for raw_line in body.split('\n'):
        line = raw_line.rstrip()
        if not line:
            indented_lines.append('')
            continue
        indented_lines.append('  ' + line)

    while indented_lines and not indented_lines[0]:
        indented_lines.pop(0)
    while indented_lines and not indented_lines[-1]:
        indented_lines.pop()

    return '\n'.join(indented_lines)


def _generate_lua_source(
    func_name: str,
    arg_names: list,
    arg_lua_types: list,
    ret_lua_type: str,
    body: str,
    auto_signature: bool = True,
    args_json: str = None,
    module_code: str = '',
    deps_code: str = '',
) -> str:
    """
    生成完整的 Lua 源码

    参数：
        func_name: 函数名
        arg_names: 参数名列表
        arg_lua_types: Lua 端入参类型列表
        ret_lua_type: Lua 端返回类型
        body: 函数体代码
        auto_signature: 是否自动生成签名
        args_json: JSON 编码的参数（用于传递 Python 参数）
        module_code: 模块级代码
        deps_code: 依赖函数代码

    返回：
        完整 Lua 源码字符串
    """
    params_str = ', '.join(arg_names) if arg_names else ''

    indented_body = _preprocess_lua_body(body, auto_signature)
    if indented_body:
        indented_body = '\n' + indented_body + '\n'
    else:
        indented_body = '\n'

    code_parts = []

    # shebang 和编码声明
    code_parts.append('#!/usr/bin/env lua')
    code_parts.append('')

    # JSON 解析（Lua 5.3+ 内置）
    code_parts.append('-- 解析参数')
    code_parts.append(f'local args_json = [[{args_json}]]')
    code_parts.append('local json = require("json") or {}')
    code_parts.append('local function parse_json(s)')
    code_parts.append('  local ok, result = pcall(function()')
    code_parts.append('    if json.decode then return json.decode(s) end')
    code_parts.append('    -- 简单 JSON 解析（无外部库时）')
    code_parts.append('    if s == "null" or s == "nil" then return nil end')
    code_parts.append('    if s:sub(1,1) == "[" then')
    code_parts.append('      local t = {}')
    code_parts.append('      for v in s:gmatch("[^,%[%]]+") do')
    code_parts.append('        local num = tonumber(v)')
    code_parts.append('        table.insert(t, num or v)')
    code_parts.append('      end')
    code_parts.append('      return t')
    code_parts.append('    end')
    code_parts.append('    if s:sub(1,1) == "{" then')
    code_parts.append('      local t = {}')
    code_parts.append('      for k,v in s:gmatch("([^:,]+):([^,]+)") do')
    code_parts.append('        t[k] = v')
    code_parts.append('      end')
    code_parts.append('      return t')
    code_parts.append('    end')
    code_parts.append('    local num = tonumber(s)')
    code_parts.append('    if num then return num end')
    code_parts.append('    if s == "true" then return true end')
    code_parts.append('    if s == "false" then return false end')
    code_parts.append('    return s')
    code_parts.append('  end)')
    code_parts.append('  if ok then return result else return nil end')
    code_parts.append('end')
    code_parts.append('local args = parse_json(args_json)')
    code_parts.append('')

    # 模块级代码
    if module_code:
        code_parts.append('-- 模块级代码')
        code_parts.append(module_code)
        code_parts.append('')

    # 依赖函数代码
    if deps_code:
        code_parts.append('-- 依赖函数')
        code_parts.append(deps_code)
        code_parts.append('')

    # 主函数定义
    if auto_signature:
        code_parts.append(f'local function {func_name}({params_str}){indented_body}end')
    else:
        code_parts.append(body)

    # 调用函数并输出结果
    code_parts.append('')
    code_parts.append('-- 调用函数并输出结果')
    code_parts.append(f'local result = {func_name}(unpack(args))')

    # 结果输出
    code_parts.append('-- 输出结果（JSON 格式）')
    code_parts.append('local function serialize(v)')
    code_parts.append('  if v == nil then return "null" end')
    code_parts.append('  if type(v) == "boolean" then return tostring(v) end')
    code_parts.append('  if type(v) == "number" then return tostring(v) end')
    code_parts.append('  if type(v) == "string" then return json.encode and json.encode(v) or string.format("%q", v) end')
    code_parts.append('  if type(v) == "table" then')
    code_parts.append('    local is_array = #v > 0 or next(v) == nil')
    code_parts.append('    local items = {}')
    code_parts.append('    if is_array then')
    code_parts.append('      for i, val in ipairs(v) do')
    code_parts.append('        items[i] = serialize(val)')
    code_parts.append('      end')
    code_parts.append('      return "[" .. table.concat(items, ",") .. "]"')
    code_parts.append('    else')
    code_parts.append('      for k, val in pairs(v) do')
    code_parts.append('        table.insert(items, tostring(k) .. ":" .. serialize(val))')
    code_parts.append('      end')
    code_parts.append('      return "{" .. table.concat(items, ",") .. "}"')
    code_parts.append('    end')
    code_parts.append('  end')
    code_parts.append('  return "null"')
    code_parts.append('end')
    code_parts.append('print(serialize(result))')

    return '\n'.join(code_parts)


# ----------------------------------------------------------------------------
# 执行逻辑
# ----------------------------------------------------------------------------

def _execute_lua_code(code: str, func_name: str, cache_dir: str = None,
                      force: bool = False) -> str:
    """
    执行 Lua 代码并返回输出

    参数：
        code: 完整 Lua 源代码
        func_name: 函数名（用于生成文件名）
        cache_dir: 缓存目录，None 则使用 _LUA_CACHE_DIR
        force: 强制重新执行（忽略缓存）

    返回：
        Lua 执行的输出结果（字符串）
    """
    if cache_dir is None:
        cache_dir = _LUA_CACHE_DIR

    os.makedirs(cache_dir, exist_ok=True)

    code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
    base_name = f'lua_{func_name}_{code_hash}'
    src_path = os.path.join(cache_dir, f'{base_name}.lua')

    if not force and os.path.exists(src_path):
        result = subprocess.run(
            [_LUA_PATH, src_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            return result.stdout.strip()

    with open(src_path, 'w', encoding='utf-8') as f:
        f.write(code)

    result = subprocess.run(
        [_LUA_PATH, src_path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True,
        timeout=60,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f'Lua 执行失败:\n'
            f'stderr:\n{result.stderr}\n'
            f'stdout:\n{result.stdout}\n'
            f'代码:\n{code}'
        )

    return result.stdout.strip()


def _parse_lua_output(output: str, ret_type: str):
    """
    解析 Lua 输出结果

    参数：
        output: Lua 输出的字符串
        ret_type: 期望的返回类型

    返回：
        Python 端的解码结果
    """
    if output == 'null' or output == '' or output == 'nil':
        return None

    if ret_type == 'integer':
        try:
            return int(output)
        except ValueError:
            return output
    elif ret_type == 'number' or ret_type == 'float':
        try:
            return float(output)
        except ValueError:
            return output
    elif ret_type == 'boolean':
        if output.lower() in ('true', '1'):
            return True
        elif output.lower() in ('false', '0'):
            return False
        return output
    elif ret_type in ('table', 'array', 'list', 'dict', 'hash'):
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return output
    elif ret_type == 'string':
        return output

    try:
        return json.loads(output)
    except json.JSONDecodeError:
        try:
            return int(output)
        except ValueError:
            try:
                return float(output)
            except ValueError:
                return output


# ----------------------------------------------------------------------------
# 缓存
# ----------------------------------------------------------------------------

_code_cache = {}
_cache_lock = threading.Lock()


def _get_cached_code(func_name: str, code: str, force: bool = False) -> str:
    """获取缓存的代码路径，必要时重新生成"""
    with _cache_lock:
        cached = _code_cache.get(func_name)
        if not force and cached and cached[0] == code and os.path.exists(cached[1]):
            return cached[1]
        code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
        base_name = f'lua_{func_name}_{code_hash}'
        src_path = os.path.join(_LUA_CACHE_DIR, f'{base_name}.lua')
        os.makedirs(_LUA_CACHE_DIR, exist_ok=True)
        with open(src_path, 'w', encoding='utf-8') as f:
            f.write(code)
        _code_cache[func_name] = (code, src_path)
        return src_path


# ----------------------------------------------------------------------------
# LuaFuture - 异步结果封装
# ----------------------------------------------------------------------------

class LuaFuture:
    """Lua 异步执行结果封装"""

    def __init__(self, proc, src_path: str, func_name: str, ret_type: str):
        self.proc = proc
        self.src_path = src_path
        self.func_name = func_name
        self.ret_type = ret_type

    def result(self, timeout=None):
        """获取执行结果"""
        stdout, stderr = self.proc.communicate(timeout=timeout)
        output = stdout.strip() if stdout else ''
        if self.proc.returncode != 0:
            raise RuntimeError(f'Lua 执行失败: {stderr}')
        return _parse_lua_output(output, self.ret_type)


# ============================================================================
# LuaBridge - Lua 桥接实现（继承 LangBridge）
# ============================================================================

class LuaBridge(LangBridge):
    """
    Lua 语言桥接实现

    继承 LangBridge 抽象基类，实现 Lua 特定的代码生成、
    解释执行和调用逻辑。
    """

    name = 'lua'
    is_compiled = False
    lang_type = LangType.INTERPRETED
    file_ext = '.lua'
    lib_ext = '.so'

    def __init__(self):
        super().__init__()
        _setup_lua_env()

    def compiler_available(self) -> bool:
        """解释器是否可用"""
        return lua_compiler_available()

    def _execute_code(self, package_path, func_name, args, ret_type=None):
        """解包并执行代码。"""
        import zipfile, tempfile, subprocess, os, shutil
        
        tmpdir = tempfile.mkdtemp()
        try:
            with zipfile.ZipFile(package_path, 'r') as zf:
                zf.extractall(tmpdir)
            
            source_file = os.path.join(tmpdir, self.get_source_filename(func_name))
            
            cmd = ['lua', source_file]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                raise RuntimeError("Execution failed: " + result.stderr)
            return result.stdout.strip()
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def generate_code(self, spec: FunctionSpec) -> str:
        """
        生成 Lua 代码

        包含：
        1. module_code（用户提供的模块级代码）
        2. 依赖函数（从 deps 参数生成）
        3. 主函数
        """
        parts = []

        # 模块级代码
        if spec.module_code:
            parts.append(spec.module_code)
            parts.append('')

        # 依赖函数（按顺序生成）
        deps_code_parts = []
        for dep in spec.dependencies:
            dep_code = self._generate_function(dep)
            if dep_code:
                deps_code_parts.append(dep_code)
        deps_code = '\n\n'.join(deps_code_parts)

        # 主函数
        main_code = self._generate_function(spec)
        parts.append(main_code)

        return '\n\n'.join(parts)

    def _generate_function(self, spec: FunctionSpec) -> str:
        """生成单个函数的 Lua 代码"""
        arg_names = []
        lua_argtypes = []

        for name, ann in spec.annotations.items():
            if name == 'return':
                continue
            arg_names.append(name)
            if ann is None or ann is inspect.Parameter.empty:
                lua_argtypes.append('integer')
            else:
                lua_argtypes.append(get_lua_type(ann))

        ret_type = 'integer'
        if 'return' in spec.annotations:
            ann = spec.annotations['return']
            if ann is type(None) or str(ann).lower() == 'none':
                ret_type = 'nil'
            else:
                ret_type = get_lua_type(ann)

        params_str = ', '.join(arg_names) if arg_names else ''

        indented_body = _preprocess_lua_body(spec.body, True)
        if indented_body:
            indented_body = '\n' + indented_body + '\n'
        else:
            indented_body = '\n'

        return f'function {spec.name}({params_str}){indented_body}end'

    def compile_code(self, code: str, func_name: str, cache_dir: str = None) -> str:
        """
        编译 Lua 代码（对于解释型语言，直接保存源文件并返回路径）

        参数：
            code: Lua 源代码
            func_name: 函数名（用于生成文件名）
            cache_dir: 缓存目录

        返回：
            源文件路径
        """
        if cache_dir is None:
            cache_dir = _LUA_CACHE_DIR

        os.makedirs(cache_dir, exist_ok=True)

        code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
        base_name = f'lua_{func_name}_{code_hash}'
        src_path = os.path.join(cache_dir, f'{base_name}.lua')

        with open(src_path, 'w', encoding='utf-8') as f:
            f.write(code)

        return src_path

    def compile_project(self, project_dir: str, entry: str, output_dir: str = None) -> str:
        """
        编译（处理）Lua 项目

        Lua 是解释型语言，project 模式的含义是：
        - 扫描 project_dir 下所有 .lua 文件
        - entry='main' 时：返回主文件路径（project_dir/main.lua），后续由调用方执行
        - entry!='main' 时：把所有 .lua 文件打包成一个可执行的 lua 文件，
          在文件末尾调用入口函数

        参数：
            project_dir: 项目目录路径
            entry: 入口函数名，'main' 表示执行主文件
            output_dir: 输出目录

        返回：
            产物路径（主文件路径 或 打包后的 lua 文件路径）
        """
        output_dir = output_dir or _LUA_CACHE_DIR
        os.makedirs(output_dir, exist_ok=True)

        lua_files = []
        for root, dirs, files in os.walk(project_dir):
            for f in files:
                if f.endswith('.lua'):
                    lua_files.append(os.path.join(root, f))

        if not lua_files:
            raise RuntimeError(f'No .lua files found in project directory: {project_dir}')

        lua_files.sort()

        project_name = os.path.basename(os.path.abspath(project_dir))

        if entry == 'main':
            # entry='main' 时，直接返回主文件路径
            main_lua = os.path.join(project_dir, 'main.lua')
            if not os.path.exists(main_lua):
                # 如果没有 main.lua，就用第一个 lua 文件
                main_lua = lua_files[0]
            return main_lua
        else:
            # entry!='main' 时，打包所有 lua 文件到一个文件，并在末尾调用入口函数
            project_hash = self._get_project_hash(project_dir)[:12]
            output_path = os.path.join(output_dir, f'lua_proj_{project_name}_{entry}_{project_hash}.lua')

            # 如果缓存存在，直接返回
            if os.path.exists(output_path):
                return output_path

            # 拼接所有 lua 文件内容
            all_code = []
            all_code.append('#!/usr/bin/env lua')
            all_code.append(f'-- Auto-generated from project: {project_name}')
            all_code.append('')

            for lua_file in lua_files:
                rel_path = os.path.relpath(lua_file, project_dir)
                all_code.append(f'-- --- {rel_path} ---')
                with open(lua_file, 'r', encoding='utf-8') as f:
                    all_code.append(f.read())
                all_code.append('')

            # 添加入口函数调用
            all_code.append(f'-- Entry point call')
            all_code.append('local args = arg or {}')
            all_code.append(f'local result = {entry}(unpack(args))')
            all_code.append('')

            # 输出结果
            all_code.append('-- Output result')
            all_code.append('if result == nil then')
            all_code.append("  print('null')")
            all_code.append('elseif type(result) == "table" then')
            all_code.append('  -- 简单 table 输出')
            all_code.append('  local is_array = #result > 0 or next(result) == nil')
            all_code.append('  if is_array then')
            all_code.append("    local items = {}")
            all_code.append('    for i, v in ipairs(result) do')
            all_code.append('      table.insert(items, tostring(v))')
            all_code.append('    end')
            all_code.append("    print('[' .. table.concat(items, ',') .. ']')")
            all_code.append('  else')
            all_code.append("    local items = {}")
            all_code.append('    for k, v in pairs(result) do')
            all_code.append('      table.insert(items, tostring(k) .. ":" .. tostring(v))')
            all_code.append('    end')
            all_code.append("    print('{' .. table.concat(items, ',') .. '}')")
            all_code.append('  end')
            all_code.append('else')
            all_code.append('  print(tostring(result))')
            all_code.append('end')

            final_code = '\n'.join(all_code)

            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(final_code)

            return output_path

    def call_func(self, src_path: str, func_name: str,
                  args: tuple, ret_type=None) -> Any:
        """
        调用 Lua 函数（通过执行 lua 文件）

        参数：
            src_path: Lua 源文件路径
            func_name: 函数名
            args: 参数元组
            ret_type: 返回类型

        返回：
            函数返回值
        """
        lua_ret_type = get_lua_type(ret_type) if ret_type else 'integer'

        # 将参数编码为 JSON
        args_json = json.dumps(list(args))

        # 读取源文件内容，提取函数定义
        with open(src_path, 'r', encoding='utf-8') as f:
            code = f.read()

        # 生成完整的可执行代码（包含参数解析和结果输出）
        arg_names = [f'arg{i}' for i in range(len(args))]
        arg_lua_types = infer_lua_argtypes(args)

        full_code = _generate_lua_source(
            func_name=func_name,
            arg_names=arg_names,
            arg_lua_types=arg_lua_types,
            ret_lua_type=lua_ret_type,
            body=code,
            auto_signature=False,
            args_json=args_json,
        )

        output = _execute_lua_code(full_code, func_name)
        return _parse_lua_output(output, lua_ret_type)

    def run_project(self, project_dir: str, entry: str = 'main',
                    args: tuple = (), cache_dir: str = None) -> Any:
        """
        运行 Lua 项目

        entry='main' 时：直接执行 lua project_dir/main.lua，返回 (returncode, stdout, stderr)
        entry!='main' 时：打包所有 lua 文件后调用入口函数，返回函数结果
        """
        if entry == 'main':
            main_lua = os.path.join(project_dir, 'main.lua')
            if not os.path.exists(main_lua):
                # 找第一个 lua 文件
                lua_files = []
                for root, dirs, files in os.walk(project_dir):
                    for f in files:
                        if f.endswith('.lua'):
                            lua_files.append(os.path.join(root, f))
                if not lua_files:
                    raise RuntimeError(f'No .lua files found in project directory: {project_dir}')
                main_lua = lua_files[0]

            result = subprocess.run(
                [_LUA_PATH, main_lua] + list(args),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True,
                timeout=60,
            )
            return (result.returncode, result.stdout, result.stderr)
        else:
            artifact_path = self.compile_project(project_dir, entry, cache_dir)
            return self.call_func(artifact_path, entry, args)


# 全局 LuaBridge 实例
_lua_bridge = LuaBridge()
lua = _lua_bridge.decorator

luae = lua


# ----------------------------------------------------------------------------
# 便捷入口
# ----------------------------------------------------------------------------

def compile_and_run(
    lua_code: str,
    func_name: str = 'main',
    args: tuple = (),
    ret_type: str = 'integer',
    cache_dir: str = None,
):
    """
    直接执行一段 Lua 源码（无装饰器）

    参数：
        lua_code: 完整 Lua 源码
        func_name: 要调用的函数名
        args: Python 位置参数
        ret_type: 返回类型（Lua 端类型字符串）
        cache_dir: 缓存目录（可选）

    返回：
        函数调用结果
    """
    actual_cache_dir = cache_dir or _LUA_CACHE_DIR
    os.makedirs(actual_cache_dir, exist_ok=True)

    arg_lua_types = infer_lua_argtypes(args)
    args_json = json.dumps(list(args))

    lua_source = _generate_lua_source(
        func_name=func_name,
        arg_names=['arg{}'.format(i) for i in range(len(args))],
        arg_lua_types=arg_lua_types,
        ret_lua_type=ret_type,
        body=lua_code,
        auto_signature=False,
        args_json=args_json,
    )

    output = _execute_lua_code(lua_source, func_name, actual_cache_dir)
    return _parse_lua_output(output, ret_type)
