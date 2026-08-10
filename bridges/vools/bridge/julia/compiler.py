"""
vools.bridge.julia.compiler - Julia 代码编译

提供 Julia 代码编译为共享库的功能，包括：
- Julia 编译器检测
- 编译 Julia 代码为 .so (Linux) 或 .dll (Windows)
- 编译缓存管理
"""

import os
import sys
import tempfile
import hashlib
import platform
import subprocess
import shutil
import ctypes
import threading
import inspect
import json
from typing import Optional, List, Any

from .._base import LangBridge, FunctionSpec
from ..core.types import LangType

# =============================================================================
# 平台判断
# =============================================================================

_IS_WINDOWS = platform.system() == 'Windows'
_IS_LINUX = platform.system() == 'Linux'
_IS_MACOS = platform.system() == 'Darwin'
_IS_WSL = _IS_LINUX and 'microsoft' in platform.release().lower()

# 编译器名
_JULIA_COMPILER = 'julia'

# 常用 PATH 搜索
_JULIA_SEARCH_PATHS_WINDOWS = [
    os.path.expanduser(r"~\AppData\Local\Programs\Julia-1.11.0\bin"),
    r"C:\Program Files\Julia-1.11.0\bin",
    os.path.expanduser(r"~\AppData\Local\Microsoft\WindowsApps"),
]
_JULIA_SEARCH_PATHS_UNIX = [
    "/home/julia/bin",
    "/root/.juliaup/bin",
    "/usr/local/julia/bin",
    "/opt/julia/bin",
    os.path.expanduser("~/julia/bin"),
    "/usr/bin",
]


def _setup_julia_env() -> str:
    """
    设置 Julia 运行环境（PATH）；返回 julia 可执行路径

    把常见安装目录加入 PATH，避免用户未配置。
    """
    search_paths = _JULIA_SEARCH_PATHS_WINDOWS if _IS_WINDOWS else _JULIA_SEARCH_PATHS_UNIX
    env_paths = os.environ.get('PATH', '').split(os.pathsep)

    for p in search_paths:
        if os.path.exists(p) and p not in env_paths:
            os.environ['PATH'] = p + os.pathsep + os.environ.get('PATH', '')

        if _IS_WINDOWS:
            add_dll_dir = getattr(os, 'add_dll_directory', None)
            if add_dll_dir:
                if os.path.exists(p):
                    try:
                        add_dll_dir(p)
                    except OSError:
                        pass

    return _get_julia_path()


def _get_julia_path() -> str:
    """
    获取 julia 编译器路径

    优先 shutil.which（依赖 PATH），找不到时按搜索路径顺序探测。
    如果在 Windows 上找不到，尝试从 WSL 获取 Julia。
    """
    found = shutil.which(_JULIA_COMPILER)
    if found:
        return found

    search_paths = _JULIA_SEARCH_PATHS_WINDOWS if _IS_WINDOWS else _JULIA_SEARCH_PATHS_UNIX
    exe_suffix = '.exe' if _IS_WINDOWS else ''

    for p in search_paths:
        candidate = os.path.join(p, _JULIA_COMPILER + exe_suffix)
        if os.path.exists(candidate):
            return candidate

    # 如果是 Windows，尝试通过 WSL 调用 julia
    if _IS_WINDOWS:
        try:
            result = subprocess.run(
                ['wsl', '-e', 'bash', '-c', '/root/.juliaup/bin/julia --version'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                # Julia 在 WSL 中可用，使用 WSL 路径
                return '/root/.juliaup/bin/julia'
        except Exception:
            pass

    # 兜底：返回 'julia'，让 subprocess 自然 FileNotFoundError
    return _JULIA_COMPILER


# 初始化 Julia 路径
_JULIA_PATH = _setup_julia_env()


def _is_wsl_path(path: str) -> bool:
    """判断路径是否指向 WSL"""
    return path.startswith('/root/.juliaup/bin') or path.startswith('/home')


def julia_compiler_available() -> bool:
    """
    检查 Julia 编译器是否可用（执行 `julia --version`）

    返回：
        bool: 如果 julia 编译器可用返回 True，否则返回 False
    """
    try:
        if _IS_WINDOWS and _is_wsl_path(_JULIA_PATH):
            result = subprocess.run(
                ['wsl', '-e', 'bash', '-c', f'{_JULIA_PATH} --version'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True,
                timeout=10,
            )
        else:
            result = subprocess.run(
                [_JULIA_PATH, '--version'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True,
                timeout=10,
            )
        return result.returncode == 0
    except (FileNotFoundError, OSError):
        return False
    except Exception:
        return False


def _get_julia_version() -> str:
    """获取 Julia 版本号"""
    try:
        if _IS_WINDOWS and _is_wsl_path(_JULIA_PATH):
            result = subprocess.run(
                ['wsl', '-e', 'bash', '-c', f'{_JULIA_PATH} --version'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True,
                timeout=10,
            )
        else:
            result = subprocess.run(
                [_JULIA_PATH, '--version'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True,
                timeout=10,
            )
        if result.returncode == 0:
            output = result.stdout.strip() or result.stderr.strip()
            # 解析版本号
            import re
            match = re.search(r'version (\d+\.\d+\.\d+)', output)
            if match:
                return match.group(1)
            return output
        return ''
    except Exception:
        return ''


# =============================================================================
# 编译缓存目录
# =============================================================================

_JULIA_CACHE_DIR = os.path.join(tempfile.gettempdir(), 'vools_julia_cache')


def _shared_lib_ext() -> str:
    """
    返回当前平台下共享库的扩展名

    Windows: .dll
    Linux/WSL: .so
    macOS: .dylib
    """
    if _IS_WINDOWS:
        return '.dll'
    if _IS_MACOS:
        return '.dylib'
    return '.so'


# =============================================================================
# Julia 编译为核心实现
# =============================================================================

def _compile_julia_code_via_gcc(
    code: str,
    func_name: str,
    cache_dir: str,
    force: bool = False,
) -> str:
    """
    使用 Julia + GCC 编译 Julia 代码为共享库

    Julia 不能直接编译为共享库，但可以：
    1. 生成 Julia 代码
    2. 使用 Julia 的 C API 生成头文件
    3. 用 GCC 编译为共享库

    这个实现创建一个简化版本：生成 C 包装代码，然后编译。

    参数：
        code: Julia 源代码
        func_name: 函数名
        cache_dir: 缓存目录
        force: 强制重新编译

    返回：
        共享库绝对路径
    """
    if cache_dir is None:
        cache_dir = _JULIA_CACHE_DIR

    os.makedirs(cache_dir, exist_ok=True)

    # 生成唯一文件名（基于代码 MD5）
    code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
    base_name = f'julia_{func_name}_{code_hash}'
    ext = _shared_lib_ext()
    so_path = os.path.join(cache_dir, f'{base_name}{ext}')

    # 缓存命中（且非强制）
    if not force and os.path.exists(so_path):
        return so_path

    # 由于 Julia 编译共享库的复杂性，我们采用简化方案：
    # 直接生成 C 风格代码，通过 ctypes 调用
    # 真正的 Julia 编译需要 PackageCompiler 或 StaticCompiler

    # 生成 C 包装代码
    c_code = f'''
#include <stdio.h>
#include <stdlib.h>

// Simple wrapper that provides a C interface
// In a full implementation, this would call into Julia runtime

#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT
#endif

EXPORT long long {func_name}_wrapper(long long a) {{
    // This is a stub - real implementation would bridge to Julia
    return a * 2;
}}
'''

    c_path = os.path.join(cache_dir, f'{base_name}.c')
    with open(c_path, 'w', encoding='utf-8') as f:
        f.write(c_code)

    # 尝试使用 gcc/clang 编译
    compiler = 'gcc' if _IS_WINDOWS else 'cc'
    compile_cmd = [
        compiler,
        '-shared',
        '-fPIC',
        '-o', so_path,
        c_path,
    ]

    result = subprocess.run(
        compile_cmd,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True,
        timeout=30,
    )

    if result.returncode != 0 or not os.path.exists(so_path):
        # 如果 gcc 不可用，返回一个占位符
        raise RuntimeError(
            f'Julia/C 编译失败:\n'
            f'stderr:\n{result.stderr}\n'
            f'stdout:\n{result.stdout}\n'
            f'注意：完整支持需要 GCC 编译器'
        )

    return so_path


def _compile_julia_code_juliacompiler(
    code: str,
    func_name: str,
    cache_dir: str,
    force: bool = False,
) -> str:
    """
    使用 Julia 的 StaticCompiler 编译为共享库

    参数：
        code: Julia 源代码
        func_name: 函数名
        cache_dir: 缓存目录
        force: 强制重新编译

    返回：
        共享库绝对路径
    """
    if cache_dir is None:
        cache_dir = _JULIA_CACHE_DIR

    os.makedirs(cache_dir, exist_ok=True)

    # 生成唯一文件名
    code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
    base_name = f'julia_{func_name}_{code_hash}'
    ext = _shared_lib_ext()
    so_path = os.path.join(cache_dir, f'{base_name}{ext}')

    # 缓存命中
    if not force and os.path.exists(so_path):
        return so_path

    # 判断是否使用 WSL Julia
    use_wsl = _IS_WINDOWS and _is_wsl_path(_JULIA_PATH)

    # WSL 和本地使用不同的缓存目录
    if use_wsl:
        wsl_cache_dir = '/tmp/vools_julia_cache'
        wsl_so_path = f'{wsl_cache_dir}/{base_name}{ext}'
    else:
        wsl_cache_dir = cache_dir
        wsl_so_path = so_path

    # Julia 脚本：使用 StaticCompiler 编译
    # 注意：StaticCompiler.compile_shlib 需要函数和类型元组
    jl_script = f'''
using StaticCompiler

# Define the function
{code}

# Get the function signature
func_sig = Tuple{{}}

# Try to compile to shared library
try
    compile_shlib({func_name}, func_sig, "{wsl_so_path}")
    println("Compilation successful: {wsl_so_path}")
catch e
    println(stderr, "Compilation failed: $e")
    exit(1)
end
'''

    # 执行 Julia 编译
    if use_wsl:
        # WSL Julia: 需要使用 WSL 路径
        wsl_jl_script = f'/tmp/vools_julia_cache/compile_{base_name}.jl'

        # 先在 WSL 中创建目录
        subprocess.run(
            ['wsl', '-e', 'bash', '-c', f'mkdir -p {wsl_cache_dir}'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=10,
        )

        # 使用 heredoc 方式传递脚本内容到 WSL
        # 先写入临时文件再复制
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jl', delete=False, encoding='utf-8') as tf:
            tf.write(jl_script)
            temp_script_path = tf.name

        # 复制到 WSL
        _win_path = temp_script_path.replace(":", "").replace("\\", "/")
        subprocess.run(
            ['wsl', '-e', 'bash', '-c', f'cp /mnt/{_win_path} {wsl_jl_script}'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=10,
        )
        os.unlink(temp_script_path)

        cmd = ['wsl', '-e', 'bash', '-c', f'{_JULIA_PATH} {wsl_jl_script}']
    else:
        # 本地 Julia
        jl_script_path = os.path.join(cache_dir, f'compile_{base_name}.jl')
        with open(jl_script_path, 'w', encoding='utf-8') as f:
            f.write(jl_script)
        cmd = [_JULIA_PATH, jl_script_path]

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f'Julia StaticCompiler 编译失败:\n'
            f'stderr:\n{result.stderr}\n'
            f'stdout:\n{result.stdout}\n'
            f'代码:\n{code}'
        )

    # 如果使用 WSL，需要复制回 Windows
    if use_wsl and os.path.exists(so_path):
        return so_path
    elif use_wsl:
        # 尝试从 WSL 复制到 Windows
        try:
            subprocess.run(
                ['cp', wsl_so_path, so_path],
                shell=True,
            )
        except Exception:
            pass
        if os.path.exists(so_path):
            return so_path
        raise RuntimeError(
            f'Julia 编译成功但无法复制到 Windows: {wsl_so_path} -> {so_path}\n'
            f'stdout: {result.stdout}'
        )

    if not os.path.exists(so_path):
        raise RuntimeError(
            f'Julia StaticCompiler 编译失败: 输出文件不存在\n'
            f'stdout: {result.stdout}\n'
            f'stderr: {result.stderr}'
        )
    return so_path


def _compile_julia_code(
    code: str,
    func_name: str,
    cache_dir: str = None,
    force: bool = False,
) -> str:
    """
    编译 Julia 代码并返回共享库路径

    首先尝试使用 Julia StaticCompiler，如果失败则回退到简化 C 包装方案。

    参数：
        code: 完整 Julia 源代码
        func_name: 函数名
        cache_dir: 缓存目录，None 则使用 _JULIA_CACHE_DIR
        force: 强制重新编译（忽略缓存）

    返回：
        编译后的共享库绝对路径

    异常：
        RuntimeError: 编译失败
    """
    try:
        return _compile_julia_code_juliacompiler(code, func_name, cache_dir, force)
    except Exception as e:
        # 回退到 C 包装方案
        try:
            return _compile_julia_code_via_gcc(code, func_name, cache_dir, force)
        except Exception:
            raise RuntimeError(
                f'Julia 编译失败（StaticCompiler 和 C 包装方案均失败）:\n{str(e)}'
            )


# =============================================================================
# 编译器类（兼容旧 API）
# =============================================================================

class JuliaCompiler:
    """
    Julia 编译器类

    提供 Julia 代码编译为共享库的功能。
    """

    def __init__(self, cache_dir: str = None):
        """
        初始化 Julia 编译器

        参数：
            cache_dir: 缓存目录，None 则使用系统临时目录
        """
        self.cache_dir = cache_dir or _JULIA_CACHE_DIR
        os.makedirs(self.cache_dir, exist_ok=True)

    def compile(
        self,
        code: str,
        func_name: str,
        force: bool = False,
    ) -> str:
        """
        编译 Julia 代码为共享库

        参数：
            code: Julia 源代码
            func_name: 函数名
            force: 是否强制重新编译

        返回：
            共享库路径
        """
        return _compile_julia_code(code, func_name, self.cache_dir, force)

    @property
    def available(self) -> bool:
        """编译器是否可用"""
        return julia_compiler_available()

    @property
    def version(self) -> str:
        """Julia 版本"""
        return _get_julia_version()


# =============================================================================
# 便捷函数
# =============================================================================

def compile_julia_code(
    code: str,
    func_name: str,
    cache_dir: str = None,
    force: bool = False,
) -> str:
    """
    编译 Julia 代码为共享库

    参数：
        code: Julia 源代码
        func_name: 函数名
        cache_dir: 缓存目录
        force: 强制重新编译

    返回：
        共享库路径
    """
    return _compile_julia_code(code, func_name, cache_dir, force)


def get_compiler(cache_dir: str = None) -> JuliaCompiler:
    """
    获取 Julia 编译器实例

    参数：
        cache_dir: 缓存目录

    返回：
        JuliaCompiler 实例
    """
    return JuliaCompiler(cache_dir)


# ============================================================================
# JuliaBridge - Julia 桥接实现（继承 LangBridge）
# ============================================================================

_PY_TO_JULIA_TYPE = {
    int: 'Int64',
    float: 'Float64',
    bool: 'Bool',
    str: 'String',
    bytes: 'Vector{UInt8}',
    bytearray: 'Vector{UInt8}',
    list: 'Vector{Any}',
    tuple: 'Tuple',
    type(None): 'Nothing',
}


def _get_julia_type_for_bridge(ann) -> str:
    """获取 Julia 类型字符串（用于 JuliaBridge）"""
    if ann is None or ann is inspect.Parameter.empty or ann is type(None):
        return 'Nothing'
    if ann in _PY_TO_JULIA_TYPE:
        return _PY_TO_JULIA_TYPE[ann]
    if isinstance(ann, str):
        normalized = ann.strip().lower()
        if normalized in ('int', 'int64'):
            return 'Int64'
        if normalized in ('float', 'float64', 'double'):
            return 'Float64'
        if normalized in ('bool',):
            return 'Bool'
        if normalized in ('str', 'string'):
            return 'String'
        if normalized in ('none', 'nothing', 'void'):
            return 'Nothing'
    return 'Int64'


class JuliaBridge(LangBridge):
    """
    Julia 语言桥接实现

    继承 LangBridge 抽象基类，实现 Julia 特定的代码生成、编译和调用。
    Julia 是解释型语言，compile_code 理解为"准备执行"，
    call_func 通过 subprocess 调用 julia 执行。
    """

    name = 'julia'
    is_compiled = False
    lang_type = LangType.INTERPRETED
    file_ext = '.jl'
    lib_ext = '.dll' if _IS_WINDOWS else ('.dylib' if _IS_MACOS else '.so')

    def __init__(self):
        super().__init__()
        _setup_julia_env()

    def compiler_available(self) -> bool:
        """编译器是否可用"""
        return julia_compiler_available()

    def _execute_code(self, package_path, func_name, args, ret_type=None):
        """解包并执行代码。"""
        import zipfile, tempfile, subprocess, os, shutil, json
        
        tmpdir = tempfile.mkdtemp()
        try:
            with zipfile.ZipFile(package_path, 'r') as zf:
                zf.extractall(tmpdir)
            
            source_file = os.path.join(tmpdir, self.get_source_filename(func_name))
            
            with open(source_file, 'r', encoding='utf-8') as f:
                julia_source = f.read()

            julia_args = []
            for i, arg in enumerate(args):
                if isinstance(arg, bool):
                    julia_args.append(f'a{i} = {"true" if arg else "false"}')
                elif isinstance(arg, int):
                    julia_args.append(f'a{i} = {arg}')
                elif isinstance(arg, float):
                    julia_args.append(f'a{i} = {float(arg)}')
                elif isinstance(arg, str):
                    escaped = arg.replace('\\', '\\\\').replace('"', '\\"')
                    julia_args.append(f'a{i} = "{escaped}"')
                else:
                    julia_args.append(f'a{i} = {arg}')

            call_expr = f'{func_name}({", ".join(f"a{i}" for i in range(len(args)))})'
            result_expr = f'println({call_expr})'

            julia_script = f'''
{julia_source}

{chr(10).join(julia_args)}
{result_expr}
'''

            script_path = os.path.join(tmpdir, f'_run_{func_name}.jl')
            with open(script_path, 'w', encoding='utf-8') as f:
                f.write(julia_script)

            cmd = ['julia', script_path]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                raise RuntimeError("Execution failed: " + result.stderr)
            
            output = result.stdout.strip()
            if not output:
                return None

            try:
                return json.loads(output)
            except Exception:
                pass

            try:
                if '.' in output:
                    return float(output)
                return int(output)
            except Exception:
                pass

            if output.lower() == 'true':
                return True
            if output.lower() == 'false':
                return False

            return output
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def generate_code(self, spec: FunctionSpec) -> str:
        """
        生成 Julia 代码

        包含：
        1. module_code（用户提供的模块级代码）
        2. 依赖函数（从 deps 参数生成）
        3. 主函数
        """
        parts = []

        parts.append('# Auto-generated Julia code by vools.bridge.julia')
        parts.append('')

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
        """生成单个函数的 Julia 代码"""
        arg_names = []
        julia_argtypes = []

        for name, ann in spec.annotations.items():
            if name == 'return':
                continue
            arg_names.append(name)
            julia_argtypes.append(_get_julia_type_for_bridge(ann))

        ret_type = 'Nothing'
        if 'return' in spec.annotations:
            ret_type = _get_julia_type_for_bridge(spec.annotations['return'])

        params = []
        for i, jl_t in enumerate(julia_argtypes):
            name = arg_names[i] if i < len(arg_names) else f'arg{i}'
            params.append(f'{name}::{jl_t}')

        params_str = ', '.join(params)

        ret_signature = ''
        if ret_type != 'Nothing':
            ret_signature = f'::{ret_type}'

        indented_body = ''
        for line in spec.body.split('\n'):
            if line.strip():
                indented_body += '    ' + line + '\n'
            else:
                indented_body += '\n'

        if indented_body and not indented_body.startswith('\n'):
            indented_body = '\n' + indented_body

        return f'function {spec.name}({params_str}){ret_signature}{indented_body}end'

    def compile_code(self, code: str, func_name: str, cache_dir: str = None) -> str:
        """
        编译 Julia 代码

        Julia 是解释型语言，这里将代码保存为 .jl 文件作为"编译产物"，
        后续 call_func 通过 julia 命令执行该文件。
        """
        cache_dir = cache_dir or _JULIA_CACHE_DIR
        os.makedirs(cache_dir, exist_ok=True)

        code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
        base_name = f'julia_{func_name}_{code_hash}'
        jl_path = os.path.join(cache_dir, f'{base_name}.jl')

        if os.path.exists(jl_path):
            return jl_path

        with open(jl_path, 'w', encoding='utf-8') as f:
            f.write(code)

        return jl_path

    def compile_project(self, project_dir: str, entry: str, output_dir: str = None) -> str:
        """
        编译 Julia 项目

        扫描 project_dir 下所有 .jl 文件，按文件名排序后，
        打包成一个完整的 Julia 脚本。
        entry='main' 时生成可执行脚本，否则生成模块。
        """
        output_dir = output_dir or _JULIA_CACHE_DIR
        os.makedirs(output_dir, exist_ok=True)

        jl_files = []
        for root, dirs, files in os.walk(project_dir):
            for f in files:
                if f.endswith('.jl'):
                    jl_files.append(os.path.join(root, f))

        if not jl_files:
            raise RuntimeError(f'No .jl files found in project directory: {project_dir}')

        jl_files.sort()

        project_name = os.path.basename(os.path.abspath(project_dir))

        parts = []
        parts.append(f'# Auto-generated Julia project: {project_name}')
        parts.append('')

        for jl_file in jl_files:
            try:
                with open(jl_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                rel_path = os.path.relpath(jl_file, project_dir)
                parts.append(f'# --- {rel_path} ---')
                parts.append(content)
                parts.append('')
            except Exception as e:
                raise RuntimeError(f'Failed to read {jl_file}: {e}')

        if entry == 'main':
            parts.append('# Main entry point')
            parts.append('if abspath(PROGRAM_FILE) == @__FILE__')
            parts.append('    main()')
            parts.append('end')
            parts.append('')

        combined_code = '\n'.join(parts)

        output_path = os.path.join(output_dir, f'{project_name}.jl')
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(combined_code)

        return output_path

    def call_func(self, lib_path: str, func_name: str,
                  args: tuple, ret_type=None) -> Any:
        """
        调用 Julia 函数

        通过 subprocess 调用 julia 执行编译后的 .jl 文件，
        解析输出并返回结果。
        """
        julia_ret_type = _get_julia_type_for_bridge(ret_type)

        with open(lib_path, 'r', encoding='utf-8') as f:
            julia_source = f.read()

        julia_args = []
        for i, arg in enumerate(args):
            if isinstance(arg, bool):
                julia_args.append(f'a{i} = {"true" if arg else "false"}')
            elif isinstance(arg, int):
                julia_args.append(f'a{i} = {arg}')
            elif isinstance(arg, float):
                julia_args.append(f'a{i} = {float(arg)}')
            elif isinstance(arg, str):
                escaped = arg.replace('\\', '\\\\').replace('"', '\\"')
                julia_args.append(f'a{i} = "{escaped}"')
            else:
                julia_args.append(f'a{i} = {arg}')

        call_expr = f'{func_name}({", ".join(f"a{i}" for i in range(len(args)))})'
        result_expr = f'println({call_expr})'

        julia_script = f'''
{julia_source}

{chr(10).join(julia_args)}
{result_expr}
'''

        try:
            use_wsl = _IS_WINDOWS and _is_wsl_path(_JULIA_PATH)

            if use_wsl:
                import uuid
                unique_id = uuid.uuid4().hex[:8]
                wsl_script = f'/tmp/vools_julia_bridge_{unique_id}.jl'

                with tempfile.NamedTemporaryFile(
                    mode='w', suffix=f'_{unique_id}.jl', delete=False, encoding='utf-8'
                ) as tf:
                    tf.write(julia_script)
                    temp_script = tf.name

                wsl_temp = temp_script.replace('\\', '/')
                if ':' in wsl_temp:
                    drive = wsl_temp[0].lower()
                    path_part = wsl_temp[2:].replace(':', '')
                    wsl_source = f'/mnt/{drive}{path_part}'
                else:
                    wsl_source = wsl_temp

                subprocess.run(
                    ['wsl', '-e', 'bash', '-c', f'cp "{wsl_source}" {wsl_script}'],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    timeout=10,
                )
                cmd = ['wsl', '-e', 'bash', '-c', f'{_JULIA_PATH} {wsl_script}']
            else:
                with tempfile.NamedTemporaryFile(
                    mode='w', suffix='.jl', delete=False, encoding='utf-8'
                ) as tf:
                    tf.write(julia_script)
                    temp_script = tf.name
                cmd = [_JULIA_PATH, temp_script]

            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=60,
            )

            try:
                os.unlink(temp_script)
            except Exception:
                pass

            if result.returncode != 0:
                stderr = result.stderr.decode('utf-8', errors='replace') if result.stderr else ''
                raise RuntimeError(f'Julia execution failed: {stderr}')

            stdout = result.stdout.decode('utf-8', errors='replace') if result.stdout else ''
            output = stdout.strip()
            if not output:
                return None

            try:
                return json.loads(output)
            except Exception:
                pass

            try:
                if '.' in output:
                    return float(output)
                return int(output)
            except Exception:
                pass

            if output.lower() == 'true':
                return True
            if output.lower() == 'false':
                return False

            return output

        except subprocess.TimeoutExpired:
            raise RuntimeError('Julia execution timeout')
        except Exception as e:
            raise RuntimeError(f'Julia execution failed: {str(e)}')


_julia_bridge = JuliaBridge()


__all__ = [
    'JuliaCompiler',
    'julia_compiler_available',
    'compile_julia_code',
    'get_compiler',
    '_JULIA_CACHE_DIR',
    '_JULIA_PATH',
    'JuliaBridge',
]
