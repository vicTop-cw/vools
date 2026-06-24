"""
vools.bridge.perl.compiler - Perl 语言桥接编译器实现

提供 PerlBridge 类，继承 LangBridge 抽象基类，实现 Perl 特定的代码生成、
编译（解释执行）和调用逻辑。
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


# ----------------------------------------------------------------------------
# 平台判断
# ----------------------------------------------------------------------------
_IS_WINDOWS = platform.system() == 'Windows'
_IS_LINUX = platform.system() == 'Linux'
_IS_MACOS = platform.system() == 'Darwin'

# 编译器名
_PERL_COMPILER = 'perl'

# 常用 PATH 搜索
_PERL_SEARCH_PATHS_WINDOWS = [
    r"C:\Perl\bin",
    r"C:\Strawberry\perl\bin",
    r"C:\ActivePerl\bin",
    os.path.expanduser("~/perl/bin"),
]
_PERL_SEARCH_PATHS_UNIX = [
    "/usr/bin",
    "/usr/local/bin",
    "/opt/homebrew/bin",
    "/home/linuxbrew/.linuxbrew/bin",
]


def _setup_perl_env() -> str:
    """设置 Perl 运行环境（PATH）；返回 perl 可执行路径"""
    search_paths = _PERL_SEARCH_PATHS_WINDOWS if _IS_WINDOWS else _PERL_SEARCH_PATHS_UNIX
    env_paths = os.environ.get('PATH', '').split(os.pathsep)

    for p in search_paths:
        if os.path.exists(p) and p not in env_paths:
            os.environ['PATH'] = p + os.pathsep + os.environ.get('PATH', '')

    return _get_perl_path()


def _get_perl_path() -> str:
    """获取 perl 解释器路径"""
    found = shutil.which(_PERL_COMPILER)
    if found:
        return found

    search_paths = _PERL_SEARCH_PATHS_WINDOWS if _IS_WINDOWS else _PERL_SEARCH_PATHS_UNIX
    exe_suffix = '.exe' if _IS_WINDOWS else ''
    for p in search_paths:
        candidate = os.path.join(p, _PERL_COMPILER + exe_suffix)
        if os.path.exists(candidate):
            return candidate
    return _PERL_COMPILER


_PERL_PATH = _setup_perl_env()


def perl_compiler_available() -> bool:
    """检查 Perl 解释器是否可用（执行 `perl --version`）"""
    try:
        result = subprocess.run(
            [_PERL_PATH, '--version'],
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
_PERL_CACHE_DIR = os.path.join(tempfile.gettempdir(), 'vools_perl_cache')


# ----------------------------------------------------------------------------
# Python ↔ Perl 类型映射
# ----------------------------------------------------------------------------

PY_TO_PERL_TYPE = {
    int: 'int',
    float: 'num',
    bool: 'bool',
    str: 'str',
    bytes: 'str',
    list: 'array',
    dict: 'hash',
    tuple: 'array',
    type(None): 'undef',
}

_PERL_TYPE_ALIASES = {
    'int': 'int',
    'integer': 'int',
    'float': 'num',
    'double': 'num',
    'num': 'num',
    'number': 'num',
    'bool': 'bool',
    'boolean': 'bool',
    'str': 'str',
    'string': 'str',
    'bytes': 'str',
    'array': 'array',
    'list': 'array',
    'hash': 'hash',
    'dict': 'hash',
    'undef': 'undef',
    'none': 'undef',
    'nonetype': 'undef',
}


def get_perl_type(py_type):
    """根据 Python 类型获取 Perl 端类型字符串"""
    if py_type in PY_TO_PERL_TYPE:
        return PY_TO_PERL_TYPE[py_type]

    if isinstance(py_type, str):
        normalized = py_type.strip().lower()
        if normalized in _PERL_TYPE_ALIASES:
            return _PERL_TYPE_ALIASES[normalized]
        short = normalized.split('.')[-1]
        if short in _PERL_TYPE_ALIASES:
            return _PERL_TYPE_ALIASES[short]
        return 'str'

    return 'str'


def infer_perl_argtypes(args):
    """根据运行时值推断 Perl 端入参类型"""
    result = []
    for arg in args:
        if isinstance(arg, bool):
            result.append('bool')
        elif isinstance(arg, int):
            result.append('int')
        elif isinstance(arg, float):
            result.append('num')
        elif isinstance(arg, str):
            result.append('str')
        elif isinstance(arg, (bytes, bytearray)):
            result.append('str')
        elif isinstance(arg, (list, tuple)):
            result.append('array')
        elif isinstance(arg, dict):
            result.append('hash')
        else:
            result.append('str')
    return result


# ----------------------------------------------------------------------------
# Perl 代码生成
# ----------------------------------------------------------------------------

def _preprocess_perl_body(body: str, auto_signature: bool) -> str:
    """预处理 Perl 函数体"""
    if not auto_signature:
        return body

    indented_lines = []
    for raw_line in body.split('\n'):
        line = raw_line.rstrip()
        if not line:
            indented_lines.append('')
            continue
        indented_lines.append('    ' + line)

    while indented_lines and not indented_lines[0]:
        indented_lines.pop(0)
    while indented_lines and not indented_lines[-1]:
        indented_lines.pop()

    return '\n'.join(indented_lines)


def _generate_perl_source(
    func_name: str,
    arg_names: list,
    arg_perl_types: list,
    ret_perl_type: str,
    body: str,
    auto_signature: bool = True,
    args_json: str = None,
) -> str:
    """
    生成完整的 Perl 源码

    参数：
        func_name: 函数名
        arg_names: 参数名列表
        arg_perl_types: Perl 端入参类型列表
        ret_perl_type: Perl 端返回类型
        body: 函数体代码
        auto_signature: 是否自动生成签名
        args_json: JSON 编码的参数（用于传递 Python 参数）

    返回：
        完整 Perl 源码字符串
    """
    params_str = ', '.join(arg_names) if arg_names else ''

    if auto_signature:
        type_hint = ''
        if arg_perl_types:
            type_hint = ' # ' + ', '.join(arg_perl_types)

        # 生成参数赋值代码
        if arg_names:
            assign_lines = []
            for i, arg in enumerate(arg_names):
                assign_lines.append(f'    my ${arg} = $args->[{i}];')
            assign_code = '\n'.join(assign_lines)
        else:
            assign_code = ''

        code = f'''use strict;
use warnings;
use JSON::PP;

# 解析参数
my $args_json = '{args_json}';
my $args = decode_json($args_json);

# 主函数定义
sub {func_name} {{
{assign_code}
    {body}
}}

# 调用函数并输出结果
my $result = {func_name}();

# 输出结果（JSON 格式）
if (not defined $result) {{
    print "null";
}} elsif (ref($result) eq 'ARRAY') {{
    print encode_json($result);
}} elsif (ref($result) eq 'HASH') {{
    print encode_json($result);
}} elsif (ref($result) eq '') {{
    if ($result eq 'true' or $result eq 'false') {{
        print $result;
    }} else {{
        print $result;
    }}
}} else {{
    print $result;
}}
'''
    else:
        code = f'''use strict;
use warnings;
use JSON::PP;

my $args_json = '{args_json}';
my $args = decode_json($args_json);

{body}
'''
    return code


# ----------------------------------------------------------------------------
# 执行逻辑
# ----------------------------------------------------------------------------

def _execute_perl_code(code: str, func_name: str, cache_dir: str = None,
                       force: bool = False) -> str:
    """
    执行 Perl 代码并返回输出

    参数：
        code: 完整 Perl 源代码
        func_name: 函数名（用于生成文件名）
        cache_dir: 缓存目录，None 则使用 _PERL_CACHE_DIR
        force: 强制重新执行（忽略缓存）

    返回：
        Perl 执行的输出结果（字符串）
    """
    if cache_dir is None:
        cache_dir = _PERL_CACHE_DIR

    os.makedirs(cache_dir, exist_ok=True)

    code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
    base_name = f'perl_{func_name}_{code_hash}'
    src_path = os.path.join(cache_dir, f'{base_name}.pl')

    if not force and os.path.exists(src_path):
        result = subprocess.run(
            [_PERL_PATH, src_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            return result.stdout.strip()

    with open(src_path, 'w', encoding='utf-8') as f:
        f.write(code)

    result = subprocess.run(
        [_PERL_PATH, src_path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True,
        timeout=60,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f'Perl 执行失败:\n'
            f'stderr:\n{result.stderr}\n'
            f'stdout:\n{result.stdout}\n'
            f'代码:\n{code}'
        )

    return result.stdout.strip()


def _parse_perl_output(output: str, ret_type: str):
    """
    解析 Perl 输出结果

    参数：
        output: Perl 输出的字符串
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
    elif ret_type == 'num':
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
    elif ret_type in ('array', 'list'):
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return output
    elif ret_type in ('hash', 'dict'):
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return output
    elif ret_type == 'str':
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
        base_name = f'perl_{func_name}_{code_hash}'
        src_path = os.path.join(_PERL_CACHE_DIR, f'{base_name}.pl')
        os.makedirs(_PERL_CACHE_DIR, exist_ok=True)
        with open(src_path, 'w', encoding='utf-8') as f:
            f.write(code)
        _code_cache[func_name] = (code, src_path)
        return src_path


# ----------------------------------------------------------------------------
# 异步支持
# ----------------------------------------------------------------------------
from concurrent.futures import ThreadPoolExecutor


class PerlFuture:
    """Perl 异步执行结果封装"""

    def __init__(self, future):
        self._future = future

    def result(self, timeout=None):
        return self._future.result(timeout=timeout)


def _run_async(code: str, func_name: str, args: tuple,
               ret_type: Optional[type] = None, cache_dir: str = None) -> PerlFuture:
    """异步执行 Perl 代码"""
    executor = ThreadPoolExecutor(max_workers=1)

    def _execute():
        perl_ret_type = get_perl_type(ret_type) if ret_type else 'str'
        args_json = json.dumps(list(args))

        # 生成完整的可执行代码
        arg_names = [f'arg{i}' for i in range(len(args))]
        arg_perl_types = infer_perl_argtypes(args)

        full_code = _generate_perl_source(
            func_name=func_name,
            arg_names=arg_names,
            arg_perl_types=arg_perl_types,
            ret_perl_type=perl_ret_type,
            body=code,
            auto_signature=False,
            args_json=args_json,
        )

        output = _execute_perl_code(full_code, func_name, cache_dir)
        return _parse_perl_output(output, perl_ret_type)

    future = executor.submit(_execute)
    executor.shutdown(wait=False)
    return PerlFuture(future)


# ============================================================================
# PerlBridge - Perl 桥接实现（继承 LangBridge）
# ============================================================================

class PerlBridge(LangBridge):
    """
    Perl 语言桥接实现

    继承 LangBridge 抽象基类，实现 Perl 特定的代码生成、
    解释执行和调用逻辑。
    """

    name = 'perl'
    file_ext = '.pl'
    lib_ext = '.so'

    def __init__(self):
        super().__init__()
        _setup_perl_env()

    def compiler_available(self) -> bool:
        """解释器是否可用"""
        return perl_compiler_available()

    def generate_code(self, spec: FunctionSpec) -> str:
        """
        生成 Perl 代码

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
        for dep in spec.dependencies:
            dep_code = self._generate_function(dep)
            if dep_code:
                parts.append(dep_code)
                parts.append('')

        # 主函数
        main_code = self._generate_function(spec)
        parts.append(main_code)

        return '\n'.join(parts)

    def _generate_function(self, spec: FunctionSpec) -> str:
        """生成单个函数的 Perl 代码"""
        arg_names = []
        perl_argtypes = []

        for name, ann in spec.annotations.items():
            if name == 'return':
                continue
            arg_names.append(name)
            if ann is None or ann is inspect.Parameter.empty:
                perl_argtypes.append('str')
            else:
                perl_argtypes.append(get_perl_type(ann))

        ret_type = 'str'
        if 'return' in spec.annotations:
            ann = spec.annotations['return']
            if ann is type(None) or str(ann).lower() == 'none':
                ret_type = 'undef'
            else:
                ret_type = get_perl_type(ann)

        params_str = ', '.join(arg_names) if arg_names else ''

        body = spec.body
        if body:
            body = textwrap.dedent(body).strip()

        if params_str:
            return f'sub {spec.name} {{\n    my ({params_str}) = @_;\n    {body}\n}}'
        else:
            return f'sub {spec.name} {{\n    {body}\n}}'

    def compile_code(self, code: str, func_name: str, cache_dir: str = None) -> str:
        """
        编译 Perl 代码（对于解释型语言，直接保存源文件并返回路径）

        参数：
            code: Perl 源代码
            func_name: 函数名（用于生成文件名）
            cache_dir: 缓存目录

        返回：
            源文件路径
        """
        if cache_dir is None:
            cache_dir = _PERL_CACHE_DIR

        os.makedirs(cache_dir, exist_ok=True)

        code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
        base_name = f'perl_{func_name}_{code_hash}'
        src_path = os.path.join(cache_dir, f'{base_name}.pl')

        with open(src_path, 'w', encoding='utf-8') as f:
            f.write(code)

        return src_path

    def compile_project(self, project_dir: str, entry: str, output_dir: str = None) -> str:
        """
        编译（处理）Perl 项目

        Perl 是解释型语言，project 模式的含义是：
        - 扫描 project_dir 下所有 .pl 文件
        - entry='main' 时：返回主文件路径（project_dir/main.pl），后续由调用方执行
        - entry!='main' 时：把所有 .pl 文件打包成一个可执行的 pl 文件，
          在文件末尾调用入口函数

        参数：
            project_dir: 项目目录路径
            entry: 入口函数名，'main' 表示执行主文件
            output_dir: 输出目录

        返回：
            产物路径（主文件路径 或 打包后的 pl 文件路径）
        """
        output_dir = output_dir or _PERL_CACHE_DIR
        os.makedirs(output_dir, exist_ok=True)

        pl_files = []
        for root, dirs, files in os.walk(project_dir):
            for f in files:
                if f.endswith('.pl'):
                    pl_files.append(os.path.join(root, f))

        if not pl_files:
            raise RuntimeError(f'No .pl files found in project directory: {project_dir}')

        pl_files.sort()

        project_name = os.path.basename(os.path.abspath(project_dir))

        if entry == 'main':
            # entry='main' 时，直接返回主文件路径
            main_pl = os.path.join(project_dir, 'main.pl')
            if not os.path.exists(main_pl):
                # 如果没有 main.pl，就用第一个 pl 文件
                main_pl = pl_files[0]
            return main_pl
        else:
            # entry!='main' 时，打包所有 pl 文件到一个文件，并在末尾调用入口函数
            project_hash = hashlib.md5(project_dir.encode('utf-8')).hexdigest()[:12]
            output_path = os.path.join(output_dir, f'perl_proj_{project_name}_{entry}_{project_hash}.pl')

            # 如果缓存存在，直接返回
            if os.path.exists(output_path):
                return output_path

            # 拼接所有 pl 文件内容
            all_code = []
            all_code.append('#!/usr/bin/env perl')
            all_code.append(f'# Auto-generated from project: {project_name}')
            all_code.append('use strict;')
            all_code.append('use warnings;')
            all_code.append('use JSON::PP;')
            all_code.append('')

            for pl_file in pl_files:
                rel_path = os.path.relpath(pl_file, project_dir)
                all_code.append(f'# --- {rel_path} ---')
                with open(pl_file, 'r', encoding='utf-8') as f:
                    all_code.append(f.read())
                all_code.append('')

            # 添加入口函数调用
            all_code.append('# Entry point call')
            all_code.append(f'my $result = {entry}();')
            all_code.append('')
            all_code.append('# Output result')
            all_code.append('if (not defined $result) { print "null"; }')
            all_code.append('elsif (ref($result) eq "ARRAY") { print encode_json($result); }')
            all_code.append('elsif (ref($result) eq "HASH") { print encode_json($result); }')
            all_code.append('else { print $result; }')

            final_code = '\n'.join(all_code)

            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(final_code)

            return output_path

    def call_func(self, src_path: str, func_name: str,
                  args: tuple, ret_type=None) -> Any:
        """
        调用 Perl 函数（通过执行 pl 文件）

        参数：
            src_path: Perl 源文件路径
            func_name: 函数名
            args: 参数元组
            ret_type: 返回类型

        返回：
            函数返回值
        """
        perl_ret_type = get_perl_type(ret_type) if ret_type else 'str'

        # 将参数编码为 JSON
        args_json = json.dumps(list(args))

        # 读取源文件内容，添加入口调用
        with open(src_path, 'r', encoding='utf-8') as f:
            code = f.read()

        # 生成完整的可执行代码（包含参数解析和结果输出）
        arg_names = [f'arg{i}' for i in range(len(args))]
        arg_perl_types = infer_perl_argtypes(args)

        full_code = _generate_perl_source(
            func_name=func_name,
            arg_names=arg_names,
            arg_perl_types=arg_perl_types,
            ret_perl_type=perl_ret_type,
            body=code,
            auto_signature=False,
            args_json=args_json,
        )

        output = _execute_perl_code(full_code, func_name)
        return _parse_perl_output(output, perl_ret_type)

    def run_project(self, project_dir: str, entry: str = 'main',
                    args: tuple = (), cache_dir: str = None) -> Any:
        """
        运行 Perl 项目

        entry='main' 时：直接执行 perl project_dir/main.pl，返回 (returncode, stdout, stderr)
        entry!='main' 时：打包所有 pl 文件后调用入口函数，返回函数结果
        """
        if entry == 'main':
            main_pl = os.path.join(project_dir, 'main.pl')
            if not os.path.exists(main_pl):
                # 找第一个 pl 文件
                pl_files = []
                for root, dirs, files in os.walk(project_dir):
                    for f in files:
                        if f.endswith('.pl'):
                            pl_files.append(os.path.join(root, f))
                if not pl_files:
                    raise RuntimeError(f'No .pl files found in project directory: {project_dir}')
                main_pl = pl_files[0]

            result = subprocess.run(
                [_PERL_PATH, main_pl] + list(args),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True,
                timeout=60,
            )
            return (result.returncode, result.stdout, result.stderr)
        else:
            artifact_path = self.compile_project(project_dir, entry, cache_dir)
            return self.call_func(artifact_path, entry, args)


# 全局 PerlBridge 实例
_perl_bridge = PerlBridge()


def compile_and_run(code: str, func_name: str = 'main',
                    args: tuple = (), ret_type=None,
                    cache_dir: str = None) -> Any:
    """
    编译并运行 Perl 代码的便捷函数

    参数：
        code: Perl 源代码
        func_name: 函数名
        args: 参数元组
        ret_type: 返回类型
        cache_dir: 缓存目录

    返回：
        函数执行结果
    """
    bridge = _perl_bridge
    src_path = bridge.compile_code(code, func_name, cache_dir)
    return bridge.call_func(src_path, func_name, args, ret_type)


# 别名
_perl_bridge = PerlBridge()

perl = _perl_bridge.decorator
pl = perl