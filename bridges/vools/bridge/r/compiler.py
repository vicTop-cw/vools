"""
vools.bridge.r.compiler - R 动态执行装饰器

通过 WSL 调用 Rscript 执行 R 代码，提供 @r 装饰器。

使用方式::

    @r
    def fib(n: int) -> int:
        return \"\"\"
        if (n <= 1) {
            return(1)
        } else {
            return(fib(n - 1) + fib(n - 2))
        }
        \"\"\"

    result = fib(10)

参数：
    func: 被装饰的函数
    mode: 运行模式
        DEBUG: 强制重新生成脚本并执行
        FORCE: 只生成脚本不执行
        NORMAL: 命中缓存跳过生成；未命中则生成
        ONLY_RUN: 只在有缓存时执行；没有则报错
        ONLY_CODE: 只生成 R 代码，不执行
    cache_dir: 脚本缓存目录，None 则使用系统临时目录
    ret_type: 返回类型，None 时从注解推断
    async_mode: 是否异步执行（默认 False）
    auto_signature: 是否自动根据参数类型生成签名（默认 True）
    fallback: 回退函数（R 不可用时调用）
    use_wsl: 是否使用 WSL（Windows 默认 True，Linux 默认 False）
"""

import os
import sys
import tempfile
import hashlib
import platform
import asyncio
import inspect
import functools
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, Future

from typing import Any

from .types import (
    RTypeMapper,
    get_r_type,
    infer_r_types,
    serialize_args,
    deserialize_result,
)
from .templates import RCodeGenerator, generate_from_python_func


_IS_WINDOWS = platform.system() == 'Windows'
_IS_LINUX = platform.system() == 'Linux'

_SCRIPT_CACHE_DIR = os.path.join(tempfile.gettempdir(), 'vools_r_cache')

_executor = ThreadPoolExecutor(max_workers=4)

_jsonlite_available = None
_jsonlite_check_lock = threading.Lock()

_r_available = None
_r_available_lock = threading.Lock()


def _is_jsonlite_available(use_wsl=None):
    """检查并缓存 jsonlite 是否可用"""
    global _jsonlite_available
    with _jsonlite_check_lock:
        if _jsonlite_available is None:
            _jsonlite_available = _check_jsonlite_available(use_wsl)
        return _jsonlite_available


def _safe_subprocess_run(cmd, input_data=None, timeout=120):
    """
    安全执行子进程，处理编码问题

    使用二进制模式读取输出，然后用 replace 模式解码，
    避免 WSL 非 UTF-8 输出导致的 UnicodeDecodeError。
    """
    result = subprocess.run(
        cmd,
        input=input_data.encode('utf-8') if input_data else None,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=timeout
    )

    stdout = result.stdout.decode('utf-8', errors='replace')
    stderr = result.stderr.decode('utf-8', errors='replace')

    class _Result:
        pass

    r = _Result()
    r.returncode = result.returncode
    r.stdout = stdout
    r.stderr = stderr
    return r


def _check_wsl_available():
    """检查 WSL 是否可用（仅 Windows）"""
    if not _IS_WINDOWS:
        return False
    try:
        result = _safe_subprocess_run(['wsl', '--version'], timeout=10)
        return result.returncode == 0
    except Exception:
        return False


def _check_rscript_available(use_wsl=None):
    """检查 Rscript 是否可用"""
    if use_wsl is None:
        use_wsl = _IS_WINDOWS

    try:
        if use_wsl:
            result = _safe_subprocess_run(['wsl', 'which', 'Rscript'], timeout=15)
            if result.returncode != 0 or result.stdout.strip() == '':
                return False
        else:
            result = _safe_subprocess_run(['which', 'Rscript'], timeout=5)
            if result.returncode != 0:
                return False

        version_cmd = ['wsl', 'Rscript', '--version'] if use_wsl else ['Rscript', '--version']
        result = _safe_subprocess_run(version_cmd, timeout=15)
        return result.returncode == 0
    except Exception:
        return False


def _check_jsonlite_available(use_wsl=None):
    """检查 jsonlite 包是否可用"""
    if use_wsl is None:
        use_wsl = _IS_WINDOWS

    test_code = 'cat(suppressPackageStartupMessages(require(jsonlite)))'
    try:
        if use_wsl:
            result = _safe_subprocess_run(
                ['wsl', 'Rscript', '-'], input_data=test_code, timeout=30
            )
        else:
            result = _safe_subprocess_run(
                ['Rscript', '-'], input_data=test_code, timeout=15
            )
        return 'TRUE' in result.stdout
    except Exception:
        return False


def _windows_to_wsl_path(windows_path):
    """将 Windows 路径转换为 WSL 路径"""
    if not _IS_WINDOWS:
        return windows_path

    abs_path = os.path.abspath(windows_path)
    drive = abs_path[0].lower()
    path_part = abs_path[2:].replace('\\', '/')
    return f'/mnt/{drive}{path_part}'


def r_compiler_available():
    """
    检查 R 环境是否可用（结果缓存，避免反复探测 WSL）

    返回：
        bool: 如果 Rscript 可用返回 True，否则返回 False
    """
    global _r_available
    with _r_available_lock:
        if _r_available is None:
            use_wsl = _IS_WINDOWS
            if use_wsl and not _check_wsl_available():
                _r_available = False
            else:
                _r_available = _check_rscript_available(use_wsl)
        return _r_available


_dll_cache = {}
_cache_lock = threading.Lock()


def _get_cached_script(func_name, full_script):
    """获取缓存的脚本路径，必要时重新写入"""
    with _cache_lock:
        cached = _dll_cache.get(func_name)
        code_hash = hashlib.md5(full_script.encode('utf-8')).hexdigest()[:12]

        if cached and cached[0] == code_hash and os.path.exists(cached[1]):
            return cached[1]

        os.makedirs(_SCRIPT_CACHE_DIR, exist_ok=True)
        script_path = os.path.join(_SCRIPT_CACHE_DIR, f'r_{func_name}_{code_hash}.R')

        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(full_script)

        _dll_cache[func_name] = (code_hash, script_path)
        return script_path


def _remove_cached_script(func_name):
    """移除缓存的脚本（用于强制重新生成）"""
    with _cache_lock:
        cached = _dll_cache.pop(func_name, None)
        if cached:
            script_path = cached[1]
            try:
                if os.path.exists(script_path):
                    os.remove(script_path)
            except OSError:
                pass


def _run_r_script(r_script_path, args_tuple, ret_type=None, use_wsl=None):
    """
    执行 R 脚本并返回结果

    参数：
        r_script_path: R 脚本文件路径（Windows 路径）
        args_tuple: 参数元组
        ret_type: Python 返回类型注解
        use_wsl: 是否使用 WSL

    返回：
        函数返回值（已反序列化）
    """
    if use_wsl is None:
        use_wsl = _IS_WINDOWS

    input_data = serialize_args(list(args_tuple))

    if use_wsl:
        wsl_script_path = _windows_to_wsl_path(r_script_path)
        cmd = ['wsl', 'Rscript', wsl_script_path]
    else:
        cmd = ['Rscript', r_script_path]

    result = _safe_subprocess_run(cmd, input_data=input_data, timeout=120)

    if result.returncode != 0:
        error_msg = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(
            f'R 脚本执行失败 (exit code {result.returncode}):\n{error_msg}'
        )

    stdout = result.stdout.strip()
    return deserialize_result(stdout, ret_type)





def _execute_sync(
    func, sig, func_name, param_annotations,
    cache_dir, ret_type, mode, auto_signature,
    fallback, use_wsl, args, kwargs
):
    """同步执行 R 脚本编译和函数调用"""
    mode_upper = mode.upper() if isinstance(mode, str) else 'NORMAL'

    try:
        r_code_body = func(*[None] * len(sig.parameters))
    except Exception as e:
        if fallback is not None:
            return fallback(*args, **kwargs)
        raise RuntimeError(f'获取 R 代码失败: {e}')

    actual_ret_type = ret_type
    if actual_ret_type is None:
        ann = func.__annotations__.get('return')
        actual_ret_type = ann

    if mode_upper == 'ONLY_CODE':
        if auto_signature:
            return generate_from_python_func(
                func_name, sig, actual_ret_type, r_code_body, auto_signature
            )
        return r_code_body

    if not r_compiler_available():
        if fallback is not None:
            return fallback(*args, **kwargs)
        raise RuntimeError('R 环境不可用且未提供 fallback')

    if auto_signature:
        r_func_code = generate_from_python_func(
            func_name, sig, actual_ret_type, r_code_body, auto_signature
        )
    else:
        r_func_code = r_code_body

    full_script = RCodeGenerator.generate_script_code(
        r_func_code, func_name, use_jsonlite=True
    )

    if mode_upper in ('DEBUG', 'FORCE'):
        _remove_cached_script(func_name)

    if mode_upper == 'ONLY_RUN':
        with _cache_lock:
            cached = _dll_cache.get(func_name)
            code_hash = hashlib.md5(full_script.encode('utf-8')).hexdigest()[:12]
            if cached and cached[0] == code_hash and os.path.exists(cached[1]):
                script_path = cached[1]
            else:
                raise FileNotFoundError(
                    f'ONLY_RUN 模式: 未找到缓存的脚本 {func_name}'
                )
    else:
        script_path = _get_cached_script(func_name, full_script)

    if mode_upper == 'FORCE':
        return script_path

    try:
        result = _run_r_script(script_path, args, actual_ret_type, use_wsl)
        return result
    except Exception as e:
        if fallback is not None:
            return fallback(*args, **kwargs)
        raise RuntimeError(f'R 脚本执行失败: {e}')


def compile_and_run(r_code: str, func_name: str = 'main',
                    args: tuple = (), ret_type: str = 'integer',
                    cache_dir: str = None, use_wsl: bool = None):
    """
    直接生成并运行 R 代码

    参数：
        r_code: R 函数体代码（不含签名）
        func_name: 函数名（默认 'main'）
        args: 参数元组
        ret_type: 返回类型
        cache_dir: 脚本缓存目录
        use_wsl: 是否使用 WSL

    返回：
        函数返回值
    """
    if use_wsl is None:
        use_wsl = _IS_WINDOWS

    r_types = infer_r_types(list(args))
    params = [(f'arg{i}', rt) for i, rt in enumerate(r_types)]

    r_func_code = RCodeGenerator.generate_function_signature(
        func_name, params, ret_type, r_code
    )
    full_script = RCodeGenerator.generate_script_code(
        r_func_code, func_name
    )

    script_path = _get_cached_script(func_name, full_script)
    return _run_r_script(script_path, args, ret_type, use_wsl)


async def compile_and_run_async(r_code: str, func_name: str = 'main',
                                 args: tuple = (), ret_type: str = 'integer',
                                 cache_dir: str = None, use_wsl: bool = None):
    """
    异步生成并运行 R 代码

    参数：
        r_code: R 函数体代码（不含签名）
        func_name: 函数名（默认 'main'）
        args: 参数元组
        ret_type: 返回类型
        cache_dir: 脚本缓存目录
        use_wsl: 是否使用 WSL

    返回：
        函数返回值（awaitable）
    """
    loop = asyncio.get_event_loop()

    def _run():
        return compile_and_run(r_code, func_name, args, ret_type, cache_dir, use_wsl)

    return await loop.run_in_executor(_executor, _run)


def r_module(name=None, cache_dir=None, use_wsl=None):
    """
    R 模块装饰器

    将一个类标记为 R 模块，类中的所有方法自动使用 R 实现。

    参数：
        name: 模块名称（可选）
        cache_dir: 脚本缓存目录（可选）
        use_wsl: 是否使用 WSL（可选）

    用法：
        @r_module(name='math_ops')
        class MathOps:
            def add(a: int, b: int) -> int:
                return "return(a + b)"

            def mul(a: float, b: float) -> float:
                return "return(a * b)"
    """
    def decorator(cls):
        for method_name in dir(cls):
            if not method_name.startswith('_'):
                method = getattr(cls, method_name)
                if callable(method):
                    decorated_method = r(
                        method,
                        cache_dir=cache_dir,
                    )
                    setattr(cls, method_name, decorated_method)

        return cls

    return decorator


# ============================================================================
# RBridge - R 语言桥接实现（继承 LangBridge）
# ============================================================================

from .._base import LangBridge, FunctionSpec
from ..core.types import LangType


class RBridge(LangBridge):
    """
    R 语言桥接实现

    继承 LangBridge 抽象基类，实现 R 特定的代码生成、
    解释执行和调用逻辑。
    """

    name = 'r'
    is_compiled = False
    lang_type = LangType.INTERPRETED
    file_ext = '.R'
    lib_ext = '.R'

    def __init__(self):
        super().__init__()
        self._use_wsl = _IS_WINDOWS

    def compiler_available(self) -> bool:
        """解释器是否可用"""
        return r_compiler_available()

    def _execute_code(self, package_path, func_name, args, ret_type=None):
        """解包并执行代码。"""
        import zipfile, tempfile, os, shutil
        
        tmpdir = tempfile.mkdtemp()
        try:
            with zipfile.ZipFile(package_path, 'r') as zf:
                zf.extractall(tmpdir)
            
            source_file = os.path.join(tmpdir, self.get_source_filename(func_name))
            
            with open(source_file, 'r', encoding='utf-8') as f:
                func_code = f.read()
            
            use_jsonlite = _is_jsonlite_available(self._use_wsl)
            full_script = RCodeGenerator.generate_script_code(
                func_code, func_name, use_jsonlite=use_jsonlite
            )
            
            temp_script = os.path.join(tmpdir, f'_exec_{func_name}_{os.getpid()}.R')
            with open(temp_script, 'w', encoding='utf-8') as f:
                f.write(full_script)
            
            input_data = serialize_args(list(args))
            
            if self._use_wsl:
                wsl_temp_path = _windows_to_wsl_path(temp_script)
                cmd = ['wsl', 'Rscript', wsl_temp_path]
            else:
                cmd = ['Rscript', temp_script]
            
            result = _safe_subprocess_run(cmd, input_data=input_data, timeout=120)
            
            if result.returncode != 0:
                error_msg = result.stderr.strip() or result.stdout.strip()
                raise RuntimeError(
                    f'R script execution failed (exit code {result.returncode}):\n{error_msg}'
                )
            
            return deserialize_result(result.stdout.strip(), ret_type)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def generate_code(self, spec: FunctionSpec) -> str:
        """
        生成 R 代码

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
        """生成单个函数的 R 代码"""
        import inspect

        arg_names = []
        r_argtypes = []

        for name, ann in spec.annotations.items():
            if name == 'return':
                continue
            arg_names.append(name)
            if ann is None or ann is inspect.Parameter.empty:
                r_argtypes.append('integer')
            else:
                r_argtypes.append(get_r_type(ann))

        ret_type = 'integer'
        if 'return' in spec.annotations:
            ann = spec.annotations['return']
            if ann is type(None) or str(ann).lower() == 'none':
                ret_type = 'NULL'
            else:
                ret_type = get_r_type(ann)

        params = list(zip(arg_names, r_argtypes))

        preamble, clean_body = RCodeGenerator.extract_preamble(spec.body)

        func_code = RCodeGenerator.generate_function_signature(
            spec.name, params, ret_type, clean_body
        )

        if preamble:
            preamble_code = '\n'.join(preamble)
            full_code = f'{preamble_code}\n\n{func_code}'
        else:
            full_code = func_code

        return full_code

    def compile_code(self, code: str, func_name: str, cache_dir: str = None) -> str:
        """
        编译 R 代码（对于解释型语言，直接保存源文件并返回路径）

        参数：
            code: R 源代码
            func_name: 函数名（用于生成文件名）
            cache_dir: 缓存目录

        返回：
            源文件路径
        """
        cache_dir = cache_dir or _SCRIPT_CACHE_DIR
        os.makedirs(cache_dir, exist_ok=True)

        code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
        base_name = f'r_{func_name}_{code_hash}'
        src_path = os.path.join(cache_dir, f'{base_name}.R')

        with open(src_path, 'w', encoding='utf-8') as f:
            f.write(code)

        return src_path

    def compile_project(self, project_dir: str, entry: str, output_dir: str = None) -> str:
        """
        编译（处理）R 项目

        R 是解释型语言，project 模式的含义是：
        - 扫描 project_dir 下所有 .R 文件
        - entry='main' 时：返回主文件路径（project_dir/main.R），后续由调用方执行
        - entry!='main' 时：把所有 .R 文件打包成一个可执行的 R 文件，
          在文件末尾调用入口函数

        参数：
            project_dir: 项目目录路径
            entry: 入口函数名，'main' 表示执行主文件
            output_dir: 输出目录

        返回：
            产物路径（主文件路径 或 打包后的 R 文件路径）
        """
        output_dir = output_dir or _SCRIPT_CACHE_DIR
        os.makedirs(output_dir, exist_ok=True)

        r_files = []
        for root, dirs, files in os.walk(project_dir):
            for f in files:
                if f.endswith('.R'):
                    r_files.append(os.path.join(root, f))

        if not r_files:
            raise RuntimeError(f'No .R files found in project directory: {project_dir}')

        r_files.sort()

        project_name = os.path.basename(os.path.abspath(project_dir))

        if entry == 'main':
            main_r = os.path.join(project_dir, 'main.R')
            if not os.path.exists(main_r):
                main_r = r_files[0]
            return main_r
        else:
            project_hash = self._get_project_hash(project_dir)[:12]
            output_path = os.path.join(output_dir, f'r_proj_{project_name}_{entry}_{project_hash}.R')

            if os.path.exists(output_path):
                return output_path

            all_code = []
            all_code.append('options(encoding = "UTF-8")')
            all_code.append(f'# Auto-generated from project: {project_name}')
            all_code.append('')

            for r_file in r_files:
                rel_path = os.path.relpath(r_file, project_dir)
                all_code.append(f'# --- {rel_path} ---')
                with open(r_file, 'r', encoding='utf-8') as f:
                    all_code.append(f.read())
                all_code.append('')

            all_code.append(f'# Entry point call')
            all_code.append(f'.args <- commandArgs(trailingOnly = TRUE)')
            all_code.append(f'if (length(.args) > 0) {{')
            all_code.append(f'  .parsed <- lapply(.args, function(x) eval(parse(text=x)))')
            all_code.append(f'  result <- do.call({entry}, .parsed)')
            all_code.append(f'}} else {{')
            all_code.append(f'  result <- {entry}()')
            all_code.append(f'}}')

            final_code = '\n'.join(all_code)

            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(final_code)

            return output_path

    def call_func(self, src_path: str, func_name: str,
                  args: tuple, ret_type=None) -> Any:
        """
        调用 R 函数（通过执行 R 脚本文件）

        参数：
            src_path: R 源文件路径
            func_name: 函数名
            args: 参数元组
            ret_type: 返回类型

        返回：
            函数返回值
        """
        use_wsl = self._use_wsl

        with open(src_path, 'r', encoding='utf-8') as f:
            code = f.read()

        r_types = infer_r_types(list(args))
        params = [(f'arg{i}', rt) for i, rt in enumerate(r_types)]

        r_ret_type = get_r_type(ret_type) if ret_type else 'integer'

        r_func_code = RCodeGenerator.generate_function_signature(
            func_name, params, r_ret_type, code
        )

        full_script = RCodeGenerator.generate_script_code(
            r_func_code, func_name, use_jsonlite=_is_jsonlite_available(use_wsl)
        )

        input_data = serialize_args(list(args))

        if use_wsl:
            wsl_script_path = _windows_to_wsl_path(src_path)
            cmd = ['wsl', 'Rscript', wsl_script_path]
        else:
            cmd = ['Rscript', src_path]

        temp_dir = os.path.dirname(src_path)
        temp_script = os.path.join(temp_dir, f'_call_{func_name}_{os.getpid()}.R')
        with open(temp_script, 'w', encoding='utf-8') as f:
            f.write(full_script)

        try:
            if use_wsl:
                wsl_temp_path = _windows_to_wsl_path(temp_script)
                cmd = ['wsl', 'Rscript', wsl_temp_path]
            else:
                cmd = ['Rscript', temp_script]

            result = _safe_subprocess_run(cmd, input_data=input_data, timeout=120)

            if result.returncode != 0:
                error_msg = result.stderr.strip() or result.stdout.strip()
                raise RuntimeError(
                    f'R 脚本执行失败 (exit code {result.returncode}):\n{error_msg}'
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
        运行 R 项目

        entry='main' 时：直接执行 Rscript project_dir/main.R，返回 (returncode, stdout, stderr)
        entry!='main' 时：打包所有 R 文件后调用入口函数，返回函数结果
        """
        use_wsl = self._use_wsl

        if entry == 'main':
            main_r = os.path.join(project_dir, 'main.R')
            if not os.path.exists(main_r):
                r_files = []
                for root, dirs, files in os.walk(project_dir):
                    for f in files:
                        if f.endswith('.R'):
                            r_files.append(os.path.join(root, f))
                if not r_files:
                    raise RuntimeError(f'No .R files found in project directory: {project_dir}')
                main_r = r_files[0]

            if use_wsl:
                wsl_main_r = _windows_to_wsl_path(main_r)
                cmd = ['wsl', 'Rscript', wsl_main_r] + list(args)
            else:
                cmd = ['Rscript', main_r] + list(args)

            result = _safe_subprocess_run(cmd, timeout=120)
            return (result.returncode, result.stdout, result.stderr)
        else:
            artifact_path = self.compile_project(project_dir, entry, cache_dir)
            return self.call_func(artifact_path, entry, args)


_r_bridge = RBridge()

# 统一装饰器接口（使用 LangBridge 标准装饰器）
r = _r_bridge.decorator
