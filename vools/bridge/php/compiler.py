"""
vools.bridge.php.compiler - PHP 语言桥接编译器实现

提供 PHPBridge 类，继承 LangBridge 抽象基类，实现 PHP 特定的代码生成、
解释执行和调用逻辑。
"""

import os
import sys
import json
import shutil
import hashlib
import tempfile
import subprocess
import platform
import inspect
import asyncio
import textwrap
import functools
import threading
from typing import Any, Optional, List, Callable
from concurrent.futures import ThreadPoolExecutor, Future

from .._base import LangBridge, FunctionSpec, FunctionParser
from ..core.types import LangType

# ----------------------------------------------------------------------------
# 平台判断
# ----------------------------------------------------------------------------
_IS_WINDOWS = platform.system() == 'Windows'
_IS_LINUX = platform.system() == 'Linux'
_IS_MACOS = platform.system() == 'Darwin'

# PHP 解释器
_PHP_COMPILER = 'php'

# 常用 PATH 搜索
_PHP_SEARCH_PATHS_WINDOWS = [
    r"C:\php",
    r"C:\xampp\php",
    r"C:\wamp64\bin\php",
    os.path.expanduser("~/php"),
]
_PHP_SEARCH_PATHS_UNIX = [
    "/usr/bin",
    "/usr/local/bin",
    "/opt/homebrew/bin",
]


def _setup_php_env() -> str:
    """设置 PHP 运行环境（PATH）；返回 php 可执行路径"""
    search_paths = _PHP_SEARCH_PATHS_WINDOWS if _IS_WINDOWS else _PHP_SEARCH_PATHS_UNIX
    env_paths = os.environ.get('PATH', '').split(os.pathsep)

    for p in search_paths:
        if os.path.exists(p) and p not in env_paths:
            os.environ['PATH'] = p + os.pathsep + os.environ.get('PATH', '')

    return _get_php_path()


def _get_php_path() -> str:
    """获取 php 解释器路径"""
    found = shutil.which(_PHP_COMPILER)
    if found:
        return found

    search_paths = _PHP_SEARCH_PATHS_WINDOWS if _IS_WINDOWS else _PHP_SEARCH_PATHS_UNIX
    exe_suffix = '.exe' if _IS_WINDOWS else ''
    for p in search_paths:
        candidate = os.path.join(p, _PHP_COMPILER + exe_suffix)
        if os.path.exists(candidate):
            return candidate
    return _PHP_COMPILER


_PHP_PATH = _setup_php_env()

# ----------------------------------------------------------------------------
# 缓存目录
# ----------------------------------------------------------------------------
_PHP_CACHE_DIR = os.path.join(tempfile.gettempdir(), 'vools_php_cache')

# ----------------------------------------------------------------------------
# 异步执行器
# ----------------------------------------------------------------------------
_executor = ThreadPoolExecutor(max_workers=4)


# ----------------------------------------------------------------------------
# 编译器检测
# ----------------------------------------------------------------------------

def php_compiler_available() -> bool:
    """检查 PHP 解释器是否可用（执行 `php --version`）"""
    try:
        result = subprocess.run(
            [_PHP_PATH, '--version'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, OSError):
        return False
    except Exception:
        return False


def get_php_version() -> Optional[str]:
    """获取 PHP 版本"""
    try:
        result = subprocess.run(
            [_PHP_PATH, '--version'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5,
        )
        if result.returncode == 0:
            first_line = result.stdout.strip().split('\n')[0]
            return first_line
    except Exception:
        pass
    return None


# ----------------------------------------------------------------------------
# 类型映射
# ----------------------------------------------------------------------------

PY_TO_PHP_TYPE = {
    int: 'int',
    float: 'float',
    str: 'string',
    bool: 'bool',
    list: 'array',
    dict: 'array',
    type(None): 'NULL',
}


def get_php_type(py_type):
    """根据 Python 类型获取 PHP 端类型字符串"""
    if py_type in PY_TO_PHP_TYPE:
        return PY_TO_PHP_TYPE[py_type]

    if isinstance(py_type, str):
        normalized = py_type.strip().lower()
        if normalized in ('int', 'integer'):
            return 'int'
        elif normalized in ('float', 'double'):
            return 'float'
        elif normalized in ('str', 'string'):
            return 'string'
        elif normalized in ('bool', 'boolean'):
            return 'bool'
        elif normalized in ('list', 'array'):
            return 'array'
        elif normalized in ('none', 'null', 'nonetype'):
            return 'NULL'
    return 'string'


def infer_php_argtypes(args):
    """根据运行时值推断 PHP 端入参类型"""
    result = []
    for arg in args:
        if isinstance(arg, bool):
            result.append('bool')
        elif isinstance(arg, int):
            result.append('int')
        elif isinstance(arg, float):
            result.append('float')
        elif isinstance(arg, str):
            result.append('string')
        elif isinstance(arg, (bytes, bytearray)):
            result.append('string')
        elif isinstance(arg, (list, tuple)):
            result.append('array')
        elif isinstance(arg, dict):
            result.append('array')
        else:
            result.append('string')
    return result


# ----------------------------------------------------------------------------
# 序列化 / 反序列化
# ----------------------------------------------------------------------------

def serialize_args(args: list) -> str:
    """将 Python 参数序列化为 JSON 字符串"""
    return json.dumps(args, ensure_ascii=False)


def deserialize_result(output: str, ret_type=None):
    """将 PHP 输出反序列化为 Python 对象"""
    output = output.strip()
    if not output:
        return None

    # 尝试 JSON 反序列化
    try:
        result = json.loads(output)
        return result
    except json.JSONDecodeError:
        pass

    # 处理 null / NULL
    if output.lower() in ('null', 'nil'):
        return None

    # 尝试解析为 PHP 标量类型
    if output.lower() == 'true':
        return True
    if output.lower() == 'false':
        return False

    # 尝试数字
    try:
        if '.' in output:
            return float(output)
        return int(output)
    except ValueError:
        return output


# ----------------------------------------------------------------------------
# PHP 代码生成
# ----------------------------------------------------------------------------

def _preprocess_php_body(body: str, auto_signature: bool) -> str:
    """预处理 PHP 函数体"""
    if not auto_signature:
        return body

    # 使用 textwrap.dedent 保持格式
    clean_body = textwrap.dedent(body).strip()
    return clean_body


def _generate_php_source(
    func_name: str,
    arg_names: list,
    arg_php_types: list,
    ret_php_type: str,
    body: str,
    auto_signature: bool = True,
    args_json: str = None,
) -> str:
    """
    生成完整的 PHP 源码

    参数：
        func_name: 函数名
        arg_names: 参数名列表
        arg_php_types: PHP 端入参类型列表
        ret_php_type: PHP 端返回类型
        body: 函数体代码
        auto_signature: 是否自动生成签名
        args_json: JSON 编码的参数（用于传递 Python 参数）

    返回：
        完整 PHP 源码字符串
    """
    params_str = ', '.join(arg_names) if arg_names else ''

    clean_body = _preprocess_php_body(body, auto_signature)

    if auto_signature:
        code = f'''<?php
// Auto-generated by vools.bridge.php

// 解析参数
$args_json = '{args_json}';
$args = json_decode($args_json, true);

// 定义函数
function {func_name}({params_str}) {{
{clean_body}
}}

// 调用函数并输出结果
$result = {func_name}(...$args);

// 输出结果（JSON 格式）
echo json_encode($result, JSON_UNESCAPED_UNICODE);
'''
    else:
        code = f'''<?php
// Auto-generated by vools.bridge.php

// 解析参数
$args_json = '{args_json}';
$args = json_decode($args_json, true);

{clean_body}
'''
    return code


# ----------------------------------------------------------------------------
# 执行逻辑
# ----------------------------------------------------------------------------

def _execute_php_code(code: str, func_name: str, cache_dir: str = None,
                      force: bool = False) -> str:
    """
    执行 PHP 代码并返回输出

    参数：
        code: 完整 PHP 源代码
        func_name: 函数名（用于生成文件名）
        cache_dir: 缓存目录，None 则使用 _PHP_CACHE_DIR
        force: 强制重新执行（忽略缓存）

    返回：
        PHP 执行的输出结果（字符串）
    """
    if cache_dir is None:
        cache_dir = _PHP_CACHE_DIR

    os.makedirs(cache_dir, exist_ok=True)

    code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
    base_name = f'php_{func_name}_{code_hash}'
    src_path = os.path.join(cache_dir, f'{base_name}.php')

    if not force and os.path.exists(src_path):
        result = subprocess.run(
            [_PHP_PATH, src_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            return result.stdout.strip()

    with open(src_path, 'w', encoding='utf-8') as f:
        f.write(code)

    result = subprocess.run(
        [_PHP_PATH, src_path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True,
        timeout=60,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f'PHP 执行失败:\n'
            f'stderr:\n{result.stderr}\n'
            f'stdout:\n{result.stdout}\n'
            f'代码:\n{code}'
        )

    return result.stdout.strip()


# ----------------------------------------------------------------------------
# PHPFuture - 异步封装
# ----------------------------------------------------------------------------

class PHPFuture:
    """异步 PHP 函数调用的 Future 封装"""

    def __init__(self, future: Future, src_path: str, func_name: str, ret_type):
        self._future = future
        self._src_path = src_path
        self._func_name = func_name
        self._ret_type = ret_type

    def result(self, timeout=None):
        return self._future.result(timeout)

    def __iter__(self):
        return self

    def __next__(self):
        return self.result()

    def __await__(self):
        return asyncio.wrap_future(self._future).__await__()





def compile_and_run(
    php_code: str,
    func_name: str = 'main',
    args: tuple = (),
    ret_type: Optional[type] = None,
    cache_dir: str = None,
):
    """
    直接生成并运行 PHP 代码

    参数：
        php_code: PHP 函数体代码（不含签名）
        func_name: 函数名（默认 'main'）
        args: 参数元组
        ret_type: 返回类型
        cache_dir: PHP 脚本缓存目录

    返回：
        函数返回值
    """
    php_types = infer_php_argtypes(list(args))
    params = [(f'arg{i}', pt) for i, pt in enumerate(php_types)]

    arg_names = [p[0] for p in params]
    php_ret_type = get_php_type(ret_type) if ret_type else 'mixed'

    php_func_code = _generate_php_source(
        func_name, arg_names, php_types, php_ret_type,
        php_code, auto_signature=True,
        args_json=serialize_args(list(args))
    )

    cache_dir = cache_dir or _PHP_CACHE_DIR
    return _execute_php_code(php_func_code, func_name, cache_dir, force=False)


async def compile_and_run_async(
    php_code: str,
    func_name: str = 'main',
    args: tuple = (),
    ret_type: Optional[type] = None,
    cache_dir: str = None,
):
    """
    异步生成并运行 PHP 代码

    参数：
        php_code: PHP 函数体代码（不含签名）
        func_name: 函数名（默认 'main'）
        args: 参数元组
        ret_type: 返回类型
        cache_dir: PHP 脚本缓存目录

    返回：
        函数返回值（awaitable）
    """
    loop = asyncio.get_event_loop()

    def _run():
        return compile_and_run(php_code, func_name, args, ret_type, cache_dir)

    return await loop.run_in_executor(_executor, _run)


# ----------------------------------------------------------------------------
# PHPBridge - LangBridge 实现
# ----------------------------------------------------------------------------


class PHPBridge(LangBridge):
    """
    PHP 语言桥接实现

    继承 LangBridge 抽象基类，实现 PHP 特定的代码生成、
    解释执行和调用逻辑。
    """

    name = 'php'
    is_compiled = False
    lang_type = LangType.INTERPRETED
    file_ext = '.php'
    lib_ext = '.so'

    def __init__(self):
        super().__init__()

    def compiler_available(self) -> bool:
        """解释器是否可用"""
        return php_compiler_available()

    def _execute_code(self, package_path, func_name, args, ret_type=None):
        """解包并执行代码。"""
        import zipfile, tempfile, subprocess, os, shutil
        
        tmpdir = tempfile.mkdtemp()
        try:
            with zipfile.ZipFile(package_path, 'r') as zf:
                zf.extractall(tmpdir)
            
            source_file = os.path.join(tmpdir, self.get_source_filename(func_name))
            
            cmd = ['php', source_file]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                raise RuntimeError("Execution failed: " + result.stderr)
            return result.stdout.strip()
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def generate_code(self, spec: FunctionSpec) -> str:
        """
        生成 PHP 代码

        包含：
        1. module_code（用户提供的模块级代码）
        2. 依赖函数（从 deps 参数生成）
        3. 主函数
        """
        parts = []

        if spec.module_code:
            parts.append(textwrap.dedent(spec.module_code).strip())
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
        """生成单个函数的 PHP 代码"""
        arg_names = []
        php_argtypes = []

        for name, ann in spec.annotations.items():
            if name == 'return':
                continue
            arg_names.append(name)
            if ann is None or ann is inspect.Parameter.empty:
                php_argtypes.append('mixed')
            else:
                php_argtypes.append(get_php_type(ann))

        ret_type = 'mixed'
        if 'return' in spec.annotations:
            ann = spec.annotations['return']
            if ann is type(None) or str(ann).lower() == 'none':
                ret_type = 'NULL'
            else:
                ret_type = get_php_type(ann)

        clean_body = textwrap.dedent(spec.body).strip() if spec.body else ''

        params_str = ', '.join(arg_names) if arg_names else ''

        func_code = f'''function {spec.name}({params_str}) {{
{clean_body}
}}'''
        return func_code

    def compile_code(self, code: str, func_name: str, cache_dir: str = None) -> str:
        """
        编译 PHP 代码（对于解释型语言，直接保存源文件并返回路径）

        参数：
            code: PHP 源代码
            func_name: 函数名（用于生成文件名）
            cache_dir: 缓存目录

        返回：
            源文件路径
        """
        cache_dir = cache_dir or _PHP_CACHE_DIR
        os.makedirs(cache_dir, exist_ok=True)

        code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
        base_name = f'php_{func_name}_{code_hash}'
        src_path = os.path.join(cache_dir, f'{base_name}.php')

        with open(src_path, 'w', encoding='utf-8') as f:
            f.write(code)

        return src_path

    def compile_project(self, project_dir: str, entry: str, output_dir: str = None) -> str:
        """
        处理 PHP 项目

        PHP 是解释型语言，project 模式的含义是：
        - 扫描 project_dir 下所有 .php 文件
        - entry='main' 时：返回主文件路径（project_dir/main.php），后续由调用方执行
        - entry!='main' 时：把所有 .php 文件打包成一个可执行的 PHP 文件，
          在文件末尾调用入口函数

        参数：
            project_dir: 项目目录路径
            entry: 入口函数名，'main' 表示执行主文件
            output_dir: 输出目录

        返回：
            产物路径（主文件路径 或 打包后的 PHP 文件路径）
        """
        output_dir = output_dir or _PHP_CACHE_DIR
        os.makedirs(output_dir, exist_ok=True)

        php_files = []
        for root, dirs, files in os.walk(project_dir):
            for f in files:
                if f.endswith('.php'):
                    php_files.append(os.path.join(root, f))

        if not php_files:
            raise RuntimeError(f'No .php files found in project directory: {project_dir}')

        php_files.sort()

        project_name = os.path.basename(os.path.abspath(project_dir))

        if entry == 'main':
            main_php = os.path.join(project_dir, 'main.php')
            if not os.path.exists(main_php):
                main_php = php_files[0]
            return main_php
        else:
            project_hash = hashlib.md5(project_dir.encode('utf-8')).hexdigest()[:12]
            output_path = os.path.join(output_dir, f'php_proj_{project_name}_{entry}_{project_hash}.php')

            if os.path.exists(output_path):
                return output_path

            all_code = []
            all_code.append('<?php')
            all_code.append(f'// Auto-generated from project: {project_name}')
            all_code.append('')

            for php_file in php_files:
                rel_path = os.path.relpath(php_file, project_dir)
                all_code.append(f'// --- {rel_path} ---')
                with open(php_file, 'r', encoding='utf-8') as f:
                    all_code.append(f.read())
                all_code.append('')

            all_code.append(f'// Entry point call')
            all_code.append(f'if (php_sapi_name() === "cli") {{')
            all_code.append(f'    $args = $argv;')
            all_code.append(f'    array_shift($args); // 移除脚本名')
            all_code.append(f'    if (count($args) > 0) {{')
            all_code.append(f'        $parsed = array_map("json_decode", $args);')
            all_code.append(f'        echo json_encode({entry}(...$parsed), JSON_UNESCAPED_UNICODE);')
            all_code.append(f'    }} else {{')
            all_code.append(f'        echo json_encode({entry}(), JSON_UNESCAPED_UNICODE);')
            all_code.append(f'    }}')
            all_code.append(f'}}')

            final_code = '\n'.join(all_code)

            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(final_code)

            return output_path

    def call_func(self, src_path: str, func_name: str,
                  args: tuple, ret_type=None) -> Any:
        """
        调用 PHP 函数（通过执行 PHP 脚本文件）

        参数：
            src_path: PHP 源文件路径
            func_name: 函数名
            args: 参数元组
            ret_type: 返回类型

        返回：
            函数返回值
        """
        with open(src_path, 'r', encoding='utf-8') as f:
            code = f.read()

        php_types = infer_php_argtypes(list(args))
        params = [(f'arg{i}', pt) for i, pt in enumerate(php_types)]

        arg_names = [p[0] for p in params]
        php_ret_type = get_php_type(ret_type) if ret_type else 'mixed'

        php_func_code = _generate_php_source(
            func_name, arg_names, php_types, php_ret_type, code,
            auto_signature=False, args_json=serialize_args(list(args))
        )

        temp_dir = os.path.dirname(src_path)
        temp_script = os.path.join(temp_dir, f'_call_{func_name}_{os.getpid()}.php')

        full_script = f'''<?php
// Wrapper for {func_name}
{php_func_code}

// Main execution
$result = {func_name}(...json_decode('{serialize_args(list(args))}', true));
echo json_encode($result, JSON_UNESCAPED_UNICODE);
'''

        with open(temp_script, 'w', encoding='utf-8') as f:
            f.write(full_script)

        try:
            result = subprocess.run(
                [_PHP_PATH, temp_script],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip() or result.stdout.strip()
                raise RuntimeError(
                    f'PHP 脚本执行失败 (exit code {result.returncode}):\n{error_msg}'
                )

            stdout = result.stdout.strip()
            return deserialize_result(stdout, ret_type)
        finally:
            try:
                if os.path.exists(temp_script):
                    os.remove(temp_script)
            except OSError:
                pass

    def run_project(self, project_dir: str, entry: str = 'main',
                    args: tuple = (), cache_dir: str = None) -> Any:
        """
        运行 PHP 项目

        entry='main' 时：直接执行 php project_dir/main.php，返回执行结果
        entry!='main' 时：打包所有 PHP 文件后调用入口函数，返回函数结果
        """
        if entry == 'main':
            main_php = os.path.join(project_dir, 'main.php')
            if not os.path.exists(main_php):
                php_files = []
                for root, dirs, files in os.walk(project_dir):
                    for f in files:
                        if f.endswith('.php'):
                            php_files.append(os.path.join(root, f))
                if not php_files:
                    raise RuntimeError(f'No .php files found in project directory: {project_dir}')
                main_php = php_files[0]

            cmd = [_PHP_PATH, main_php] + list(str(a) for a in args)

            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True,
                timeout=120,
            )
            return (result.returncode, result.stdout, result.stderr)
        else:
            artifact_path = self.compile_project(project_dir, entry, cache_dir)
            return self.call_func(artifact_path, entry, args)


_php_bridge = PHPBridge()

php = _php_bridge.decorator
phpe = php