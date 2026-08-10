"""
vools.bridge.kotlin.compiler - Kotlin 编译支持

使用 kotlinc 编译 Kotlin 源码为 JAR，通过 kotlin 命令运行。
支持 WSL 环境（Windows 上通过 wsl 命令调用）。
"""

import os
import sys
import json
import tempfile
import hashlib
import platform
import subprocess
import textwrap
import logging
import asyncio
import functools
from typing import Optional, List, Any, Callable
from concurrent.futures import ThreadPoolExecutor

from .._base import LangBridge, FunctionSpec
from ..core.types import LangType

logger = logging.getLogger(__name__)

_IS_WINDOWS = platform.system() == 'Windows'
_IS_LINUX = platform.system() == 'Linux'
_IS_MACOS = platform.system() == 'Darwin'

_KOTLIN_CACHE_DIR = os.path.join(tempfile.gettempdir(), 'vools_kotlin_cache')


def _check_wsl() -> bool:
    """检查是否可以使用 WSL"""
    if not _IS_WINDOWS:
        return False
    try:
        result = subprocess.run(
            ['wsl', '--version'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _check_wsl_kotlin() -> bool:
    """检查 WSL 中是否有 kotlinc 和 kotlin"""
    try:
        result = subprocess.run(
            ['wsl', 'bash', '-c', 'source ~/.sdkman/bin/sdkman-init.sh 2>/dev/null; which kotlinc && which kotlin'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=15
        )
        return result.returncode == 0 and result.stdout.strip() != ''
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _check_local_kotlinc() -> bool:
    """检查本地是否有 kotlinc"""
    import shutil
    return shutil.which('kotlinc') is not None


def _check_local_kotlin() -> bool:
    """检查本地是否有 kotlin"""
    import shutil
    return shutil.which('kotlin') is not None


_USE_WSL = _IS_WINDOWS and not _check_local_kotlinc() and _check_wsl() and _check_wsl_kotlin()


def _to_wsl_path(windows_path: str) -> str:
    """将 Windows 路径转换为 WSL 路径"""
    if not os.path.isabs(windows_path):
        windows_path = os.path.abspath(windows_path)
    drive = windows_path[0].lower()
    rest = windows_path[2:].replace('\\', '/')
    return f'/mnt/{drive}{rest}'


def _wsl_run(cmd: List[str], **kwargs) -> subprocess.CompletedProcess:
    """通过 WSL 运行命令，自动加载 sdkman 环境"""
    wsl_cmd = ['wsl', 'bash', '-c',
               f'source ~/.sdkman/bin/sdkman-init.sh 2>/dev/null; {" ".join(cmd)}']
    return subprocess.run(wsl_cmd, **kwargs)


def _find_kotlinc() -> Optional[str]:
    """查找 kotlinc 命令路径"""
    import shutil
    path = shutil.which('kotlinc')
    if path:
        return path
    if _USE_WSL:
        return 'wsl:kotlinc'
    return None


def _find_kotlin() -> Optional[str]:
    """查找 kotlin 命令路径"""
    import shutil
    path = shutil.which('kotlin')
    if path:
        return path
    if _USE_WSL:
        return 'wsl:kotlin'
    return None


def is_kotlin_compiler_available() -> bool:
    """检查 kotlinc 编译器是否可用"""
    return _find_kotlinc() is not None


def is_kotlin_available() -> bool:
    """检查 Kotlin 运行时是否可用"""
    return _find_kotlin() is not None


def kotlin_compiler_available() -> bool:
    """检查 Kotlin 编译器是否可用（别名）"""
    return is_kotlin_compiler_available()


def get_kotlin_version() -> Optional[str]:
    """获取 Kotlin 版本信息"""
    kotlinc_path = _find_kotlinc()
    if kotlinc_path is None:
        return None

    try:
        if _USE_WSL:
            result = _wsl_run(['kotlinc', '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        else:
            result = subprocess.run(
                ['kotlinc', '-version'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=10,
            )
        return result.stderr.decode('utf-8', errors='replace').split('\n')[0]
    except Exception:
        return None


class KotlinFuture:
    """Kotlin 异步调用结果封装"""

    def __init__(self, future):
        self._future = future

    def result(self, timeout=None):
        return self._future.result(timeout=timeout)

    def done(self):
        return self._future.done()

    def cancelled(self):
        return self._future.cancelled()

    def __await__(self):
        return asyncio.wrap_future(self._future).__await__()


class KotlinBridge(LangBridge):
    """Kotlin 语言桥接实现

    使用 kotlinc 编译为 JAR，通过 kotlin 命令运行。
    Windows 上自动通过 WSL 调用。
    参数通过命令行传递（用 \x1f 分隔），返回值从 stdout 读取。
    """

    name = 'kotlin'
    lang_type = LangType.JVM
    file_ext = '.kt'
    lib_ext = '.jar'

    def __init__(self):
        super().__init__()
        self._executor = ThreadPoolExecutor(max_workers=4)

    def compiler_available(self) -> bool:
        return is_kotlin_compiler_available() and is_kotlin_available()

    def generate_code(self, spec: FunctionSpec) -> str:
        """生成 Kotlin 代码

        生成包含依赖函数、主函数和 main 入口的完整 Kotlin 源文件。
        通过命令行参数传递输入，通过 stdout 输出结果。
        """
        parts = []

        class_name = self._to_class_name(spec.name) + 'Kt'

        parts.append(f'@file:JvmName("{class_name}")')
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
        parts.append('')

        main_entry = self._generate_main_entry(spec)
        parts.append(main_entry)

        return '\n'.join(parts)

    def _generate_function(self, spec: FunctionSpec) -> str:
        """生成单个函数的 Kotlin 代码"""
        arg_names = []
        kotlin_argtypes = []

        for name, ann in spec.annotations.items():
            if name == 'return':
                continue
            arg_names.append(name)
            if ann is None:
                kotlin_argtypes.append('Int')
            else:
                kotlin_argtypes.append(self._get_kotlin_type(ann))

        ret_type = 'Unit'
        if 'return' in spec.annotations:
            ann = spec.annotations['return']
            if ann is type(None) or str(ann).lower() == 'none':
                ret_type = 'Unit'
            else:
                ret_type = self._get_kotlin_type(ann)

        params = []
        for i, kotlin_t in enumerate(kotlin_argtypes):
            name = arg_names[i] if i < len(arg_names) else f'arg{i}'
            params.append(f'{name}: {kotlin_t}')

        params_str = ', '.join(params)

        body = spec.body
        if body.startswith('    ') or body.startswith('\t'):
            body = textwrap.dedent(body)
        body = body.strip()

        return f'''fun {spec.name}({params_str}): {ret_type} {{
{body}
}}'''

    def _generate_main_entry(self, spec: FunctionSpec) -> str:
        """生成 main 函数作为入口点

        通过命令行参数传递（用 \x1f 分隔），结果输出到 stdout。
        """
        arg_names = []
        arg_types = []

        for name, ann in spec.annotations.items():
            if name == 'return':
                continue
            arg_names.append(name)
            if ann is None:
                arg_types.append('Int')
            else:
                arg_types.append(self._get_kotlin_type(ann))

        ret_type = 'Unit'
        if 'return' in spec.annotations:
            ann = spec.annotations['return']
            if ann is type(None) or str(ann).lower() == 'none':
                ret_type = 'Unit'
            else:
                ret_type = self._get_kotlin_type(ann)

        parse_lines = []
        for i, (atype, aname) in enumerate(zip(arg_types, arg_names)):
            if atype == 'Int':
                parse_lines.append(f'    val {aname}: {atype} = parts.getOrNull({i})?.toIntOrNull() ?: 0')
            elif atype == 'Double':
                parse_lines.append(f'    val {aname}: {atype} = parts.getOrNull({i})?.toDoubleOrNull() ?: 0.0')
            elif atype == 'Boolean':
                parse_lines.append(f'    val {aname}: {atype} = parts.getOrNull({i})?.toBoolean() ?: false')
            elif atype == 'String':
                parse_lines.append(f'    val {aname}: {atype} = parts.getOrNull({i}) ?: ""')
            else:
                parse_lines.append(f'    val {aname}: {atype} = parts.getOrNull({i}) ?: ""')

        call_args = ', '.join(arg_names)

        if ret_type == 'Unit':
            result_lines = [
                f'    {spec.name}({call_args})',
                '    println("OK")'
            ]
        else:
            result_lines = [
                f'    val result = {spec.name}({call_args})',
                '    println(result)'
            ]

        return f'''fun main(args: Array<String>) {{
    if (args.isEmpty()) return
    val parts = args[0].split("\\u001f")
{chr(10).join(parse_lines)}
{chr(10).join(result_lines)}
}}'''

    def _get_kotlin_type(self, py_type) -> str:
        """将 Python 类型转换为 Kotlin 类型"""
        from .types import get_kotlin_type
        return get_kotlin_type(py_type)

    def _to_class_name(self, func_name: str) -> str:
        """将函数名转换为类名（首字母大写）"""
        if not func_name:
            return 'VoolsKotlin'
        return func_name[0].upper() + func_name[1:]

    def compile_code(self, code: str, func_name: str, cache_dir: str = None) -> str:
        """编译 Kotlin 代码，返回 JAR 文件路径"""
        if cache_dir is None:
            cache_dir = _KOTLIN_CACHE_DIR

        os.makedirs(cache_dir, exist_ok=True)

        code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
        jar_name = f'kotlin_{func_name}_{code_hash}'
        jar_path = os.path.join(cache_dir, f'{jar_name}.jar')

        if os.path.exists(jar_path):
            return jar_path

        kt_file = os.path.join(cache_dir, f'{jar_name}.kt')
        with open(kt_file, 'w', encoding='utf-8') as f:
            f.write(code)

        if _USE_WSL:
            wsl_src = _to_wsl_path(kt_file)
            wsl_jar = _to_wsl_path(jar_path)
            result = _wsl_run(
                ['kotlinc', '-include-runtime', '-d', wsl_jar, wsl_src],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=180,
            )
        else:
            compile_cmd = [
                'kotlinc',
                '-include-runtime',
                '-d', jar_path,
                kt_file,
            ]
            result = subprocess.run(
                compile_cmd,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=180,
            )

        stderr = result.stderr.decode('utf-8', errors='replace')
        stdout = result.stdout.decode('utf-8', errors='replace')

        if result.returncode != 0:
            raise RuntimeError(
                f'Kotlin compilation failed:\n{stderr}\n{stdout}'
            )

        try:
            os.remove(kt_file)
        except OSError:
            pass

        return jar_path

    def compile_project(self, project_dir: str, entry: str, output_dir: str = None) -> str:
        """编译 Kotlin 项目

        扫描 project_dir 下所有 .kt 文件，调用 kotlinc 编译为 JAR。
        """
        output_dir = output_dir or _KOTLIN_CACHE_DIR
        os.makedirs(output_dir, exist_ok=True)

        kt_files = []
        for root, dirs, files in os.walk(project_dir):
            for f in files:
                if f.endswith('.kt'):
                    kt_files.append(os.path.join(root, f))

        if not kt_files:
            raise RuntimeError(f'No .kt files found in project directory: {project_dir}')

        kt_files.sort()

        project_name = os.path.basename(os.path.abspath(project_dir))
        jar_path = os.path.join(output_dir, f'{project_name}.jar')

        if _USE_WSL:
            wsl_jar = _to_wsl_path(jar_path)
            wsl_files = [_to_wsl_path(f) for f in kt_files]
            result = _wsl_run(
                ['kotlinc', '-include-runtime', '-d', wsl_jar] + wsl_files,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=180,
            )
        else:
            compile_cmd = ['kotlinc', '-include-runtime', '-d', jar_path] + kt_files
            result = subprocess.run(
                compile_cmd,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=180,
            )

        stderr = result.stderr.decode('utf-8', errors='replace')
        stdout = result.stdout.decode('utf-8', errors='replace')

        if result.returncode != 0:
            raise RuntimeError(
                f'Kotlin project compilation failed:\n'
                f'stderr:\n{stderr}\n'
                f'stdout:\n{stdout}\n'
                f'files: {kt_files}'
            )

        return jar_path

    def call_func(self, lib_path: str, func_name: str,
                  args: tuple, ret_type: Optional[type] = None) -> Any:
        """调用 Kotlin 编译的函数

        通过 subprocess 调用 kotlin 命令执行 JAR，
        使用 \x1f 分隔参数通过命令行传递。
        """
        str_args = [str(a) for a in args]
        input_arg = '\x1f'.join(str_args)

        class_name = self._to_class_name(func_name) + 'Kt'

        if _USE_WSL:
            wsl_jar = _to_wsl_path(lib_path)
            result = _wsl_run(
                ['kotlin', '-classpath', wsl_jar, class_name, f'"{input_arg}"'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=60,
            )
        else:
            cmd = [
                'kotlin',
                '-classpath', lib_path,
                class_name,
                input_arg,
            ]
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=60,
            )

        stderr = result.stderr.decode('utf-8', errors='replace')
        stdout = result.stdout.decode('utf-8', errors='replace')

        if result.returncode != 0:
            raise RuntimeError(
                f'Kotlin execution failed (code {result.returncode}):\n'
                f'stderr: {stderr}\n'
                f'stdout: {stdout}'
            )

        output = stdout.strip()
        if not output or output == 'OK':
            return None

        if ret_type is not None:
            if ret_type == int:
                try:
                    return int(output)
                except (ValueError, TypeError):
                    return output
            elif ret_type == float:
                try:
                    return float(output)
                except (ValueError, TypeError):
                    return output
            elif ret_type == bool:
                return output.lower() in ('true', '1', 'yes')
            elif ret_type == str:
                return output

        return output

    def call_func_async(self, lib_path: str, func_name: str,
                        args: tuple, ret_type: Optional[type] = None) -> KotlinFuture:
        """异步调用 Kotlin 函数"""
        future = self._executor.submit(
            lambda: self.call_func(lib_path, func_name, args, ret_type)
        )
        return KotlinFuture(future)

    def supports_nested_functions(self) -> bool:
        """Kotlin 支持嵌套函数定义"""
        return True

    def default_cache_dir(self) -> str:
        """获取默认的编译缓存目录"""
        return _KOTLIN_CACHE_DIR


_kotlin_bridge = KotlinBridge()
kotlin = _kotlin_bridge.decorator
kt = kotlin


def compile_and_run(
    code: str,
    func_name: str,
    args: tuple,
    ret_type: Optional[type] = None,
    cache_dir: Optional[str] = None,
) -> Any:
    """编译并运行 Kotlin 代码"""
    bridge = _kotlin_bridge
    jar_path = bridge.compile_code(code, func_name, cache_dir)
    return bridge.call_func(jar_path, func_name, args, ret_type)


__all__ = [
    'kotlin',
    'kt',
    'is_kotlin_compiler_available',
    'is_kotlin_available',
    'kotlin_compiler_available',
    'compile_and_run',
    'KotlinFuture',
    'KotlinBridge',
    '_kotlin_bridge',
    'get_kotlin_version',
]
