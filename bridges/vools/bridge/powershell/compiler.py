"""
vools.bridge.powershell.compiler - PowerShell 语言桥接编译器实现

提供 PowerShellBridge 类，继承 LangBridge 抽象基类，实现 PowerShell 特定的代码生成、
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

from .._base import LangBridge, FunctionSpec
from ..core.types import LangType


# ----------------------------------------------------------------------------
# 平台判断
# ----------------------------------------------------------------------------
_IS_WINDOWS = platform.system() == 'Windows'
_IS_LINUX = platform.system() == 'Linux'
_IS_MACOS = platform.system() == 'Darwin'

# PowerShell 可执行文件候选列表
_PS_CANDIDATES = ['pwsh', 'pwsh-preview', 'powershell.exe']

# 常用 PATH 搜索
_PS_SEARCH_PATHS_WINDOWS = [
    r"C:\Windows\System32\WindowsPowerShell\v1.0",
    r"C:\Program Files\PowerShell\7",
    os.path.expanduser("~\\AppData\\Local\\Microsoft\\WindowsApps"),
]
_PS_SEARCH_PATHS_UNIX = [
    "/usr/bin",
    "/usr/local/bin",
    "/opt/microsoft/powershell/7",
    "/snap/bin",
    "/home/linuxbrew/.linuxbrew/bin",
    "/opt/homebrew/bin",
]


def _setup_ps_env() -> str:
    """设置 PowerShell 运行环境（PATH）；返回 powershell 可执行路径"""
    search_paths = _PS_SEARCH_PATHS_WINDOWS if _IS_WINDOWS else _PS_SEARCH_PATHS_UNIX
    env_paths = os.environ.get('PATH', '').split(os.pathsep)

    for p in search_paths:
        if os.path.exists(p) and p not in env_paths:
            os.environ['PATH'] = p + os.pathsep + os.environ.get('PATH', '')

    return _get_ps_path()


def _get_ps_path() -> str:
    """获取 PowerShell 解释器路径"""
    for candidate in _PS_CANDIDATES:
        found = shutil.which(candidate)
        if found:
            return found

    search_paths = _PS_SEARCH_PATHS_WINDOWS if _IS_WINDOWS else _PS_SEARCH_PATHS_UNIX
    exe_suffix = '.exe' if _IS_WINDOWS else ''
    for p in search_paths:
        for candidate in _PS_CANDIDATES:
            candidate_exe = candidate if candidate.endswith('.exe') else candidate + exe_suffix
            candidate_path = os.path.join(p, candidate_exe)
            if os.path.exists(candidate_path):
                return candidate_path
    return _PS_CANDIDATES[0]


_PS_PATH = _setup_ps_env()


def powershell_compiler_available() -> bool:
    """检查 PowerShell 解释器是否可用（执行 `$PSVersionTable`）"""
    try:
        result = subprocess.run(
            [_PS_PATH, '-NoProfile', '-Command', '$PSVersionTable.PSVersion.ToString()'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, OSError):
        return False
    except Exception:
        return False


# ----------------------------------------------------------------------------
# 缓存目录
# ----------------------------------------------------------------------------
_PS_CACHE_DIR = os.path.join(tempfile.gettempdir(), 'vools_powershell_cache')


# ----------------------------------------------------------------------------
# Python ↔ PowerShell 类型映射
# ----------------------------------------------------------------------------

PY_TO_PS_TYPE = {
    int: 'int',
    float: 'double',
    bool: 'bool',
    str: 'string',
    bytes: 'string',
    list: 'object[]',
    dict: 'hashtable',
    tuple: 'object[]',
    type(None): 'void',
}

_PS_TYPE_ALIASES = {
    'int': 'int',
    'int32': 'int',
    'long': 'long',
    'int64': 'long',
    'float': 'float',
    'single': 'float',
    'double': 'double',
    'num': 'double',
    'number': 'double',
    'bool': 'bool',
    'boolean': 'bool',
    'str': 'string',
    'string': 'string',
    'bytes': 'string',
    'array': 'object[]',
    'list': 'object[]',
    'object[]': 'object[]',
    'hashtable': 'hashtable',
    'hash': 'hashtable',
    'dict': 'hashtable',
    'void': 'void',
    'none': 'void',
    'nonetype': 'void',
}


def get_ps_type(py_type):
    """根据 Python 类型获取 PowerShell 端类型字符串"""
    if py_type in PY_TO_PS_TYPE:
        return PY_TO_PS_TYPE[py_type]

    if isinstance(py_type, str):
        normalized = py_type.strip().lower()
        if normalized in _PS_TYPE_ALIASES:
            return _PS_TYPE_ALIASES[normalized]
        short = normalized.split('.')[-1]
        if short in _PS_TYPE_ALIASES:
            return _PS_TYPE_ALIASES[short]
        return 'string'

    return 'string'


def infer_ps_argtypes(args):
    """根据运行时值推断 PowerShell 端入参类型"""
    result = []
    for arg in args:
        if isinstance(arg, bool):
            result.append('bool')
        elif isinstance(arg, int):
            result.append('int')
        elif isinstance(arg, float):
            result.append('double')
        elif isinstance(arg, str):
            result.append('string')
        elif isinstance(arg, (bytes, bytearray)):
            result.append('string')
        elif isinstance(arg, (list, tuple)):
            result.append('object[]')
        elif isinstance(arg, dict):
            result.append('hashtable')
        else:
            result.append('string')
    return result


# ----------------------------------------------------------------------------
# PowerShell 代码生成
# ----------------------------------------------------------------------------

def _generate_ps_source(
    func_name: str,
    arg_names: list,
    arg_ps_types: list,
    ret_ps_type: str,
    body: str,
    auto_signature: bool = True,
    args_json: str = None,
) -> str:
    """
    生成完整的 PowerShell 源码

    参数：
        func_name: 函数名
        arg_names: 参数名列表
        arg_ps_types: PowerShell 端入参类型列表
        ret_ps_type: PowerShell 端返回类型
        body: 函数体代码
        auto_signature: 是否自动生成签名
        args_json: JSON 编码的参数（用于传递 Python 参数）

    返回：
        完整 PowerShell 源码字符串
    """
    if auto_signature:
        if arg_names:
            param_lines = []
            for i, (name, pstype) in enumerate(zip(arg_names, arg_ps_types)):
                if pstype == 'bool':
                    param_lines.append(f'    [bool]${name} = $args[{i}]')
                elif pstype == 'int':
                    param_lines.append(f'    [int]${name} = $args[{i}]')
                elif pstype == 'long':
                    param_lines.append(f'    [long]${name} = $args[{i}]')
                elif pstype == 'double':
                    param_lines.append(f'    [double]${name} = $args[{i}]')
                elif pstype == 'float':
                    param_lines.append(f'    [float]${name} = $args[{i}]')
                else:
                    param_lines.append(f'    ${name} = $args[{i}]')
            param_code = '\n'.join(param_lines)
        else:
            param_code = ''

        indented_body = textwrap.dedent(body).strip()
        body_lines = []
        for line in indented_body.split('\n'):
            if line.strip():
                body_lines.append('    ' + line)
            else:
                body_lines.append('')
        body_indented = '\n'.join(body_lines)

        code = f'''$ErrorActionPreference = "Stop"

# 解析参数
$argsJson = @'
{args_json}
'@
$args = $argsJson | ConvertFrom-Json

# 主函数定义
function {func_name} {{
{param_code}
{body_indented}
}}

# 调用函数并输出结果
$result = {func_name} @args

# 输出结果（JSON 格式）
if ($null -eq $result) {{
    "null"
}} elseif ($result -is [array] -or $result -is [System.Collections.IList]) {{
    $result | ConvertTo-Json -Depth 10 -Compress
}} elseif ($result -is [hashtable] -or $result -is [System.Collections.IDictionary]) {{
    $result | ConvertTo-Json -Depth 10 -Compress
}} elseif ($result -is [bool]) {{
    $result.ToString().ToLower()
}} else {{
    $result.ToString()
}}
'''
    else:
        code = f'''$ErrorActionPreference = "Stop"

$argsJson = @'
{args_json}
'@
$args = $argsJson | ConvertFrom-Json

{body}
'''
    return code


# ----------------------------------------------------------------------------
# 执行逻辑
# ----------------------------------------------------------------------------

def _execute_ps_code(code: str, func_name: str, cache_dir: str = None,
                     force: bool = False) -> str:
    """
    执行 PowerShell 代码并返回输出

    参数：
        code: 完整 PowerShell 源代码
        func_name: 函数名（用于生成文件名）
        cache_dir: 缓存目录，None 则使用 _PS_CACHE_DIR
        force: 强制重新执行（忽略缓存）

    返回：
        PowerShell 执行的输出结果（字符串）
    """
    if cache_dir is None:
        cache_dir = _PS_CACHE_DIR

    os.makedirs(cache_dir, exist_ok=True)

    code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
    base_name = f'ps_{func_name}_{code_hash}'
    src_path = os.path.join(cache_dir, f'{base_name}.ps1')

    if not force and os.path.exists(src_path):
        result = subprocess.run(
            [_PS_PATH, '-NoProfile', '-File', src_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=60,
        )
        if result.returncode == 0:
            return result.stdout.strip()

    with open(src_path, 'w', encoding='utf-8') as f:
        f.write(code)

    result = subprocess.run(
        [_PS_PATH, '-NoProfile', '-File', src_path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        universal_newlines=True,
        timeout=60,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f'PowerShell 执行失败:\n'
            f'stderr:\n{result.stderr}\n'
            f'stdout:\n{result.stdout}\n'
            f'代码:\n{code}'
        )

    return result.stdout.strip()


def _parse_ps_output(output: str, ret_type: str):
    """
    解析 PowerShell 输出结果

    参数：
        output: PowerShell 输出的字符串
        ret_type: 期望的返回类型

    返回：
        Python 端的解码结果
    """
    if output == 'null' or output == '':
        return None

    if ret_type == 'int':
        try:
            return int(output)
        except ValueError:
            return output
    elif ret_type in ('double', 'float'):
        try:
            return float(output)
        except ValueError:
            return output
    elif ret_type == 'bool':
        if output.lower() in ('true', '1', 'yes'):
            return True
        elif output.lower() in ('false', '0', 'no', 'null'):
            return False
        return output
    elif ret_type in ('object[]', 'array', 'list'):
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return output
    elif ret_type in ('hashtable', 'dict', 'hash'):
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
        base_name = f'ps_{func_name}_{code_hash}'
        src_path = os.path.join(_PS_CACHE_DIR, f'{base_name}.ps1')
        os.makedirs(_PS_CACHE_DIR, exist_ok=True)
        with open(src_path, 'w', encoding='utf-8') as f:
            f.write(code)
        _code_cache[func_name] = (code, src_path)
        return src_path


# ----------------------------------------------------------------------------
# 异步支持
# ----------------------------------------------------------------------------
from concurrent.futures import ThreadPoolExecutor


class PowerShellFuture:
    """PowerShell 异步执行结果封装"""

    def __init__(self, future):
        self._future = future

    def result(self, timeout=None):
        return self._future.result(timeout=timeout)


def _run_async(code: str, func_name: str, args: tuple,
               ret_type: Optional[type] = None, cache_dir: str = None) -> PowerShellFuture:
    """异步执行 PowerShell 代码"""
    executor = ThreadPoolExecutor(max_workers=1)

    def _execute():
        ps_ret_type = get_ps_type(ret_type) if ret_type else 'string'
        args_json = json.dumps(list(args))

        arg_names = [f'arg{i}' for i in range(len(args))]
        arg_ps_types = infer_ps_argtypes(args)

        full_code = _generate_ps_source(
            func_name=func_name,
            arg_names=arg_names,
            arg_ps_types=arg_ps_types,
            ret_ps_type=ps_ret_type,
            body=code,
            auto_signature=False,
            args_json=args_json,
        )

        output = _execute_ps_code(full_code, func_name, cache_dir)
        return _parse_ps_output(output, ps_ret_type)

    future = executor.submit(_execute)
    executor.shutdown(wait=False)
    return PowerShellFuture(future)


# ============================================================================
# PowerShellBridge - PowerShell 桥接实现（继承 LangBridge）
# ============================================================================

class PowerShellBridge(LangBridge):
    """
    PowerShell 语言桥接实现

    继承 LangBridge 抽象基类，实现 PowerShell 特定的代码生成、
    解释执行和调用逻辑。
    """

    name = 'powershell'
    is_compiled = False
    lang_type = LangType.INTERPRETED
    file_ext = '.ps1'
    lib_ext = '.ps1'

    def __init__(self):
        super().__init__()
        _setup_ps_env()

    def compiler_available(self) -> bool:
        """解释器是否可用"""
        return powershell_compiler_available()

    def _execute_code(self, package_path, func_name, args, ret_type=None):
        """解包并执行代码，传递参数并调用函数。"""
        import zipfile, tempfile, subprocess, os, shutil, json
        
        tmpdir = tempfile.mkdtemp()
        try:
            with zipfile.ZipFile(package_path, 'r') as zf:
                zf.extractall(tmpdir)
            
            source_file = os.path.join(tmpdir, self.get_source_filename(func_name))
            
            with open(source_file, 'r', encoding='utf-8') as f:
                code = f.read()
            
            args_json = json.dumps(list(args))
            
            ps_ret_type = get_ps_type(ret_type) if ret_type else 'string'
            
            full_code = '''$ErrorActionPreference = "Stop"

$argsJson = @'
{args_json}
'@
$args = $argsJson | ConvertFrom-Json

{code}

$result = {func_name} @args

if ($null -eq $result) {{
    "null"
}} elseif ($result -is [array] -or $result -is [System.Collections.IList]) {{
    $result | ConvertTo-Json -Depth 10 -Compress
}} elseif ($result -is [hashtable] -or $result -is [System.Collections.IDictionary]) {{
    $result | ConvertTo-Json -Depth 10 -Compress
}} elseif ($result -is [bool]) {{
    $result.ToString().ToLower()
}} else {{
    $result.ToString()
}}
'''.format(args_json=args_json, code=code, func_name=func_name)
            
            tmp_script = os.path.join(tmpdir, '_exec.ps1')
            with open(tmp_script, 'w', encoding='utf-8') as f:
                f.write(full_code)
            
            result = subprocess.run(
                ['powershell', '-NoProfile', '-File', tmp_script],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                universal_newlines=True,
                timeout=30,
            )
            if result.returncode != 0:
                raise RuntimeError("Execution failed: " + result.stderr)
            
            return _parse_ps_output(result.stdout.strip(), ps_ret_type)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def generate_code(self, spec: FunctionSpec) -> str:
        """
        生成 PowerShell 代码

        包含：
        1. module_code（用户提供的模块级代码）
        2. 依赖函数（从 deps 参数生成）
        3. 主函数
        """
        parts = []

        if spec.module_code:
            parts.append(spec.module_code)
            parts.append('')

        for dep in spec.dependencies:
            dep_code = self._generate_function(dep)
            if dep_code:
                parts.append(dep_code)
                parts.append('')

        main_code = self._generate_function(spec)
        parts.append(main_code)

        return '\n'.join(parts)

    def _generate_function(self, spec: FunctionSpec) -> str:
        """生成单个函数的 PowerShell 代码"""
        arg_names = []
        ps_argtypes = []

        for name, ann in spec.annotations.items():
            if name == 'return':
                continue
            arg_names.append(name)
            if ann is None or ann is inspect.Parameter.empty:
                ps_argtypes.append('string')
            else:
                ps_argtypes.append(get_ps_type(ann))

        ret_type = 'string'
        if 'return' in spec.annotations:
            ann = spec.annotations['return']
            if ann is type(None) or str(ann).lower() == 'none':
                ret_type = 'void'
            else:
                ret_type = get_ps_type(ann)

        body = spec.body
        if body:
            body = textwrap.dedent(body).strip()

        if arg_names:
            param_block = '    param(\n'
            param_items = []
            for name, pstype in zip(arg_names, ps_argtypes):
                if pstype == 'bool':
                    param_items.append(f'        [bool]${name}')
                elif pstype == 'int':
                    param_items.append(f'        [int]${name}')
                elif pstype == 'long':
                    param_items.append(f'        [long]${name}')
                elif pstype == 'double':
                    param_items.append(f'        [double]${name}')
                elif pstype == 'float':
                    param_items.append(f'        [float]${name}')
                elif pstype == 'string':
                    param_items.append(f'        [string]${name}')
                else:
                    param_items.append(f'        ${name}')
            param_block += ',\n'.join(param_items)
            param_block += '\n    )'

            body_lines = []
            for line in body.split('\n'):
                if line.strip():
                    body_lines.append('    ' + line)
                else:
                    body_lines.append('')
            body_indented = '\n'.join(body_lines)

            return f'function {spec.name} {{\n{param_block}\n{body_indented}\n}}'
        else:
            body_lines = []
            for line in body.split('\n'):
                if line.strip():
                    body_lines.append('    ' + line)
                else:
                    body_lines.append('')
            body_indented = '\n'.join(body_lines)

            return f'function {spec.name} {{\n{body_indented}\n}}'

    def compile_code(self, code: str, func_name: str, cache_dir: str = None) -> str:
        """
        编译 PowerShell 代码（对于解释型语言，直接保存源文件并返回路径）

        参数：
            code: PowerShell 源代码
            func_name: 函数名（用于生成文件名）
            cache_dir: 缓存目录

        返回：
            源文件路径
        """
        if cache_dir is None:
            cache_dir = _PS_CACHE_DIR

        os.makedirs(cache_dir, exist_ok=True)

        code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
        base_name = f'ps_{func_name}_{code_hash}'
        src_path = os.path.join(cache_dir, f'{base_name}.ps1')

        with open(src_path, 'w', encoding='utf-8') as f:
            f.write(code)

        return src_path

    def compile_project(self, project_dir: str, entry: str, output_dir: str = None) -> str:
        """
        编译（处理）PowerShell 项目

        PowerShell 是解释型语言，project 模式的含义是：
        - 扫描 project_dir 下所有 .ps1 文件
        - entry='main' 时：返回主文件路径（project_dir/main.ps1），后续由调用方执行
        - entry!='main' 时：把所有 .ps1 文件打包成一个可执行的 ps1 文件，
          在文件末尾调用入口函数

        参数：
            project_dir: 项目目录路径
            entry: 入口函数名，'main' 表示执行主文件
            output_dir: 输出目录

        返回：
            产物路径（主文件路径 或 打包后的 ps1 文件路径）
        """
        output_dir = output_dir or _PS_CACHE_DIR
        os.makedirs(output_dir, exist_ok=True)

        ps_files = []
        for root, dirs, files in os.walk(project_dir):
            for f in files:
                if f.endswith('.ps1'):
                    ps_files.append(os.path.join(root, f))

        if not ps_files:
            raise RuntimeError(f'No .ps1 files found in project directory: {project_dir}')

        ps_files.sort()

        project_name = os.path.basename(os.path.abspath(project_dir))

        if entry == 'main':
            main_ps = os.path.join(project_dir, 'main.ps1')
            if not os.path.exists(main_ps):
                main_ps = ps_files[0]
            return main_ps
        else:
            project_hash = hashlib.md5(project_dir.encode('utf-8')).hexdigest()[:12]
            output_path = os.path.join(output_dir, f'ps_proj_{project_name}_{entry}_{project_hash}.ps1')

            if os.path.exists(output_path):
                return output_path

            all_code = []
            all_code.append('# Auto-generated PowerShell project bundle')
            all_code.append(f'# Project: {project_name}')
            all_code.append(f'# Entry: {entry}')
            all_code.append('$ErrorActionPreference = "Stop"')
            all_code.append('')

            for ps_file in ps_files:
                rel_path = os.path.relpath(ps_file, project_dir)
                all_code.append(f'# --- {rel_path} ---')
                with open(ps_file, 'r', encoding='utf-8') as f:
                    all_code.append(f.read())
                all_code.append('')

            all_code.append('# Entry point call')
            all_code.append(f'$result = {entry} @args')
            all_code.append('')
            all_code.append('# Output result')
            all_code.append('if ($null -eq $result) { "null" }')
            all_code.append('elseif ($result -is [array] -or $result -is [System.Collections.IList]) {')
            all_code.append('    $result | ConvertTo-Json -Depth 10 -Compress')
            all_code.append('}')
            all_code.append('elseif ($result -is [hashtable] -or $result -is [System.Collections.IDictionary]) {')
            all_code.append('    $result | ConvertTo-Json -Depth 10 -Compress')
            all_code.append('}')
            all_code.append('elseif ($result -is [bool]) { $result.ToString().ToLower() }')
            all_code.append('else { $result.ToString() }')

            final_code = '\n'.join(all_code)

            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(final_code)

            return output_path

    def call_func(self, src_path: str, func_name: str,
                  args: tuple, ret_type=None) -> Any:
        """
        调用 PowerShell 函数（通过执行 ps1 文件）

        参数：
            src_path: PowerShell 源文件路径
            func_name: 函数名
            args: 参数元组
            ret_type: 返回类型

        返回：
            函数返回值
        """
        ps_ret_type = get_ps_type(ret_type) if ret_type else None

        args_json = json.dumps(list(args))

        with open(src_path, 'r', encoding='utf-8') as f:
            code = f.read()

        full_code = f'''$ErrorActionPreference = "Stop"

$argsJson = @'
{args_json}
'@
$args = $argsJson | ConvertFrom-Json

{code}

$result = {func_name} @args

if ($null -eq $result) {{
    "null"
}} elseif ($result -is [array] -or $result -is [System.Collections.IList]) {{
    $result | ConvertTo-Json -Depth 10 -Compress
}} elseif ($result -is [hashtable] -or $result -is [System.Collections.IDictionary]) {{
    $result | ConvertTo-Json -Depth 10 -Compress
}} elseif ($result -is [bool]) {{
    $result.ToString().ToLower()
}} else {{
    $result.ToString()
}}
'''

        output = _execute_ps_code(full_code, func_name)
        return _parse_ps_output(output, ps_ret_type)

    def run_project(self, project_dir: str, entry: str = 'main',
                    args: tuple = (), cache_dir: str = None) -> Any:
        """
        运行 PowerShell 项目

        entry='main' 时：直接执行 powershell project_dir/main.ps1，返回 (returncode, stdout, stderr)
        entry!='main' 时：打包所有 ps1 文件后调用入口函数，返回函数结果
        """
        if entry == 'main':
            main_ps = os.path.join(project_dir, 'main.ps1')
            if not os.path.exists(main_ps):
                ps_files = []
                for root, dirs, files in os.walk(project_dir):
                    for f in files:
                        if f.endswith('.ps1'):
                            ps_files.append(os.path.join(root, f))
                if not ps_files:
                    raise RuntimeError(f'No .ps1 files found in project directory: {project_dir}')
                main_ps = ps_files[0]

            result = subprocess.run(
                [_PS_PATH, '-NoProfile', '-File', main_ps] + list(args),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                universal_newlines=True,
                timeout=60,
            )
            return (result.returncode, result.stdout, result.stderr)
        else:
            artifact_path = self.compile_project(project_dir, entry, cache_dir)
            return self.call_func(artifact_path, entry, args)


# 全局 PowerShellBridge 实例
_powershell_bridge = PowerShellBridge()


def compile_and_run(code: str, func_name: str = 'main',
                    args: tuple = (), ret_type=None,
                    cache_dir: str = None) -> Any:
    """
    编译并运行 PowerShell 代码的便捷函数

    参数：
        code: PowerShell 源代码
        func_name: 函数名
        args: 参数元组
        ret_type: 返回类型
        cache_dir: 缓存目录

    返回：
        函数执行结果
    """
    bridge = _powershell_bridge
    src_path = bridge.compile_code(code, func_name, cache_dir)
    return bridge.call_func(src_path, func_name, args, ret_type)


# 装饰器别名
powershell = _powershell_bridge.decorator
ps = powershell
