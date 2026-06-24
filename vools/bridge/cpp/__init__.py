"""
vools.bridge.cpp - C++ 语言桥接模块

提供 C++ 动态编译和 DLL 调用支持，包括：
- C++ 编译器检测和配置
- 动态编译装饰器 @cpp
- extern "C" 导出（避免 name mangling）
- 编译缓存机制

用法：
    from vools.bridge.cpp import cpp, cpp_compiler_available, load_cpp_dll

    # 方式 1: 动态编译装饰器
    @cpp
    def add(a: int, b: int) -> int:
        return "return a + b;"

    result = add(1, 2)  # 编译并执行

    # 方式 2: 直接加载 C++ DLL（extern "C" 导出）
    lib = load_cpp_dll("mylib.dll")
    result = lib.add(1, 2)
"""

import os
import sys
import tempfile
import hashlib
import platform
import asyncio
import inspect
import functools
import ctypes
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Any

from vools.bridge.core.loader import load_from_path, SharedLibrary
from vools.bridge.core.types import CTypeMapper
from vools.bridge.manager import manager, setup_runtime as _setup_lang_runtime
from vools.bridge._base import LangBridge, FunctionSpec, FunctionParser

# 平台判断
_IS_WINDOWS = platform.system() == 'Windows'
_IS_LINUX = platform.system() == 'Linux'
_IS_MACOS = platform.system() == 'Darwin'

# ============================================================================
# 编译器配置
# ============================================================================

def _get_cpp_config():
    """获取 C++ 语言配置"""
    return manager.get_config('cpp')


def _setup_cpp_env():
    """设置 C++ 编译环境"""
    _setup_lang_runtime('cpp')


_setup_cpp_env()


def _get_cpp_compiler():
    """
    获取 C++ 编译器路径和类型

    返回：
        tuple: (compiler_path, compiler_type)
        compiler_type: 'gcc', 'clang', 'msvc'
    """
    config = _get_cpp_config()
    if not config:
        return None, None

    compiler_path = manager.get_compiler_path('cpp')
    if not compiler_path:
        return None, None

    # 判断编译器类型
    compiler_type = 'gcc'
    if _IS_WINDOWS:
        # Windows 上可能是 MinGW GCC 或 MSVC
        if 'clang' in compiler_path.lower():
            compiler_type = 'clang'
        elif 'msvc' in compiler_path.lower() or 'cl.exe' in compiler_path:
            compiler_type = 'msvc'
    else:
        # Linux/macOS 上可能是 GCC 或 Clang
        try:
            result = subprocess.run(
                [compiler_path, '--version'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True,
                timeout=5
            )
            if 'clang' in result.stdout.lower():
                compiler_type = 'clang'
        except Exception:
            pass

    return compiler_path, compiler_type


def cpp_compiler_available():
    """
    检查 C++ 编译器是否可用

    返回：
        bool: 如果 C++ 编译器可用返回 True，否则返回 False
    """
    return manager.is_available('cpp')


def get_cpp_compiler_info():
    """
    获取 C++ 编译器详细信息

    返回：
        dict: {
            'available': bool,
            'path': str or None,
            'type': 'gcc'/'clang'/'msvc' or None,
            'version': str or None
        }
    """
    status = manager.get_status('cpp')
    compiler_path, compiler_type = _get_cpp_compiler()

    return {
        'available': status.available,
        'path': compiler_path,
        'type': compiler_type if status.available else None,
        'version': status.version,
    }


# ============================================================================
# 编译函数
# ============================================================================

def _generate_cpp_wrapper(func_name: str, args: tuple, cpp_body: str,
                           ret_type: str = 'int', arg_names: list = None) -> str:
    """
    生成完整的 C++ 代码

    使用 extern "C" 导出，避免 name mangling，确保 ctypes 可以正确调用。

    参数：
        func_name: 函数名
        args: 参数元组
        cpp_body: C++ 函数体代码
        ret_type: 返回类型
        arg_names: 参数名列表

    返回：
        完整的 C++ 代码字符串
    """
    # 类型映射
    type_mapping = {
        'int': 'int',
        'float': 'double',
        'bool': 'bool',
        'str': 'const char*',
        'bytes': 'const char*',
        'void': 'void',
    }

    actual_ret_type = type_mapping.get(ret_type, ret_type)

    # 生成参数列表
    params = []
    for i, arg in enumerate(args):
        arg_type = type_mapping.get(CTypeMapper.get_py_type(arg), 'int')
        if arg_names and i < len(arg_names):
            param_name = arg_names[i]
        else:
            param_name = f'arg{i}'
        params.append(f'{arg_type} {param_name}')

    params_str = ', '.join(params)

    # 处理函数体缩进
    indented_body = ''
    for line in cpp_body.split('\n'):
        if line.strip():
            indented_body += '    ' + line + '\n'
        else:
            indented_body += '\n'

    # 生成 extern "C" 导出函数
    if actual_ret_type == 'void':
        code = f'''extern "C" void {func_name}({params_str}) {{
{indented_body}}}
'''
    else:
        code = f'''extern "C" {actual_ret_type} {func_name}({params_str}) {{
{indented_body}}}
'''
    return code


def _compile_cpp_code(code: str, func_name: str, cache_dir: str = None) -> str:
    """
    编译 C++ 代码并返回共享库路径

    参数：
        code: C++ 代码字符串
        func_name: 函数名（用于生成文件名）
        cache_dir: 缓存目录

    返回：
        编译后的共享库路径
    """
    if cache_dir is None:
        cache_dir = os.path.join(tempfile.gettempdir(), 'vools_cpp_cache')

    os.makedirs(cache_dir, exist_ok=True)

    # 生成唯一文件名
    code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
    lib_name = f'cpp_{func_name}_{code_hash}'

    if _IS_WINDOWS:
        lib_path = os.path.join(cache_dir, f'{lib_name}.dll')
    elif _IS_LINUX:
        lib_path = os.path.join(cache_dir, f'lib{lib_name}.so')
    elif _IS_MACOS:
        lib_path = os.path.join(cache_dir, f'lib{lib_name}.dylib')
    else:
        lib_path = os.path.join(cache_dir, f'{lib_name}.so')

    # 检查缓存
    if os.path.exists(lib_path):
        return lib_path

    # 写入临时 .cpp 文件
    cpp_file = os.path.join(cache_dir, f'{lib_name}.cpp')
    with open(cpp_file, 'w', encoding='utf-8') as f:
        f.write(code)

    # 获取编译器
    compiler_path, compiler_type = _get_cpp_compiler()
    if not compiler_path:
        raise RuntimeError('C++ compiler not available')

    # 构建编译命令
    if compiler_type == 'msvc':
        # MSVC 编译命令
        compile_cmd = [
            'cl',  # MSVC 编译器
            '/LD',  # 生成 DLL
            '/MD',  # 使用多线程 DLL 运行时
            f'/Fe:{lib_path}',
            '/O2',  # 优化
            cpp_file
        ]
    elif compiler_type == 'clang':
        # Clang 编译命令
        if _IS_WINDOWS:
            compile_cmd = [
                compiler_path,
                '-shared',
                '-o', lib_path,
                '-O2',
                '-fPIC',
                cpp_file
            ]
        else:
            compile_cmd = [
                compiler_path,
                '-shared',
                '-fPIC',
                '-o', lib_path,
                '-O2',
                cpp_file
            ]
    else:
        # GCC 编译命令
        if _IS_WINDOWS:
            compile_cmd = [
                compiler_path,
                '-shared',
                '-o', lib_path,
                '-O2',
                cpp_file
            ]
        else:
            compile_cmd = [
                compiler_path,
                '-shared',
                '-fPIC',
                '-o', lib_path,
                '-O2',
                cpp_file
            ]

    # 执行编译
    result = subprocess.run(
        compile_cmd,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True,
        cwd=cache_dir
    )

    if result.returncode != 0:
        raise RuntimeError(
            f'C++ compilation failed:\n{result.stderr}\n{result.stdout}'
        )

    # 清理临时文件
    try:
        os.remove(cpp_file)
    except OSError:
        pass

    return lib_path


def _call_cpp_func(lib_path: str, func_name: str, args: tuple, ret_type=None):
    """
    调用 C++ 编译的函数

    参数：
        lib_path: 共享库路径
        func_name: 函数名
        args: 参数元组
        ret_type: 返回类型（ctypes 类型）

    返回：
        函数返回值
    """
    lib = ctypes.CDLL(lib_path)
    func = getattr(lib, func_name)

    # 使用 core 层的类型映射
    argtypes = CTypeMapper.infer_arg_types(args)
    func.argtypes = argtypes
    if ret_type is not None:
        func.restype = ret_type

    # 转换参数
    converted_args = CTypeMapper.convert_args(args, argtypes)

    # 调用函数
    result = func(*converted_args)

    # 处理字符串返回值
    if ret_type == ctypes.c_char_p and result:
        result = result.decode('utf-8')

    return result


# ============================================================================
# 类型映射
# ============================================================================

PY_TO_CPP_TYPE = {
    int: 'int',
    float: 'double',
    bool: 'bool',
    str: 'const char*',
    bytes: 'const char*',
}

CPP_TO_CTYPES = {
    'int': ctypes.c_int,
    'double': ctypes.c_double,
    'bool': ctypes.c_bool,
    'const char*': ctypes.c_char_p,
    'char*': ctypes.c_char_p,
    'void': None,
}


# ============================================================================
# 异步执行器
# ============================================================================

_executor = ThreadPoolExecutor(max_workers=4)


# ============================================================================
# 装饰器
# ============================================================================

def cpp(func=None, *, cache_dir=None, ret_type=None, async_mode=False, fallback=None,
        includes=None, link_libs=None):
    """
    C++ 动态编译装饰器

    使用方式：
        @cpp
        def add(a: int, b: int) -> int:
            return "return a + b;"

        @cpp(ret_type='double')
        def multiply(a: float, b: float) -> float:
            return "return a * b;"

        @cpp(includes=['<vector>', '<algorithm>'])
        def sort_sum(arr: list) -> int:
            return '''
            std::vector<int> v;
            for (int i = 0; i < arr.size(); i++) v.push_back(arr[i]);
            std::sort(v.begin(), v.end());
            int sum = 0;
            for (int x : v) sum += x;
            return sum;
            '''

    参数：
        func: 被装饰的函数
        cache_dir: 编译缓存目录
        ret_type: 返回类型 ('int', 'float', 'double', 'bool', 'const char*')
        async_mode: 是否异步执行
        fallback: 回退函数
        includes: 头文件列表（如 ['<vector>', '<algorithm>']）
        link_libs: 需要链接的库列表
    """
    def decorator(f):
        func_name = f.__name__

        # 获取函数参数名
        sig = inspect.signature(f)
        arg_names = list(sig.parameters.keys())

        def _compile_and_call(*args, **kwargs):
            # 调用原始函数获取 C++ 代码
            cpp_body = f(*args, **kwargs)

            # 使用局部变量存储实际返回类型
            actual_ret_type = ret_type

            # 获取返回类型注解
            ann = f.__annotations__.get('return')
            if actual_ret_type is None and ann is not None:
                if ann in PY_TO_CPP_TYPE:
                    actual_ret_type = PY_TO_CPP_TYPE[ann]
                elif ann is type(None) or str(ann).lower() == 'none':
                    actual_ret_type = 'void'
                else:
                    actual_ret_type = 'int'

            # 生成完整 C++ 代码
            full_code = _generate_cpp_wrapper(
                func_name, args, cpp_body,
                actual_ret_type or 'int',
                arg_names
            )

            # 添加头文件
            if includes:
                includes_code = '\n'.join(f'#include {inc}' for inc in includes)
                full_code = includes_code + '\n\n' + full_code

            # 编译
            lib_path = _compile_cpp_code(full_code, func_name, cache_dir)

            # 调用函数
            c_ret_type = CPP_TO_CTYPES.get(actual_ret_type, ctypes.c_int) if actual_ret_type != 'void' else None

            return _call_cpp_func(lib_path, func_name, args, c_ret_type)

        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            if not cpp_compiler_available():
                if fallback is not None:
                    return fallback(*args, **kwargs)
                raise RuntimeError(
                    f"C++ compiler is not available and no fallback provided "
                    f"for function '{func_name}'"
                )
            try:
                return _compile_and_call(*args, **kwargs)
            except Exception:
                if fallback is not None:
                    return fallback(*args, **kwargs)
                raise

        @functools.wraps(f)
        async def async_wrapper(*args, **kwargs):
            if not cpp_compiler_available():
                if fallback is not None:
                    result = fallback(*args, **kwargs)
                    if inspect.iscoroutine(result):
                        return await result
                    return result
                raise RuntimeError(
                    f"C++ compiler is not available and no fallback provided "
                    f"for function '{func_name}'"
                )
            try:
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(
                    _executor,
                    lambda: _compile_and_call(*args, **kwargs)
                )
            except Exception:
                if fallback is not None:
                    result = fallback(*args, **kwargs)
                    if inspect.iscoroutine(result):
                        return await result
                    return result
                raise

        if async_mode:
            return async_wrapper
        else:
            return wrapper

    if func is not None:
        return decorator(func)

    return decorator


# ============================================================================
# 便捷函数
# ============================================================================

def compile_and_run(cpp_code: str, func_name: str = 'main',
                    args: tuple = (), ret_type: str = 'int',
                    cache_dir: str = None, includes=None):
    """
    直接编译并运行 C++ 代码

    参数：
        cpp_code: C++ 代码字符串
        func_name: 函数名（默认 'main'）
        args: 参数元组
        ret_type: 返回类型
        cache_dir: 缓存目录
        includes: 头文件列表

    返回：
        函数返回值
    """
    full_code = _generate_cpp_wrapper(func_name, args, cpp_code, ret_type)

    if includes:
        includes_code = '\n'.join(f'#include {inc}' for inc in includes)
        full_code = includes_code + '\n\n' + full_code

    lib_path = _compile_cpp_code(full_code, func_name, cache_dir)
    c_ret_type = CPP_TO_CTYPES.get(ret_type, ctypes.c_int) if ret_type != 'void' else None

    return _call_cpp_func(lib_path, func_name, args, c_ret_type)


def load_cpp_dll(dll_path):
    """
    加载 C++ 编译的 DLL

    注意：DLL 中的函数必须使用 extern "C" 导出，否则 ctypes 无法调用。

    参数：
        dll_path: DLL 文件路径

    返回：
        SharedLibrary 实例，加载失败返回 None
    """
    return load_from_path(dll_path)


def call_cpp_func(dll_path, func_name, args=None, ret_type=None):
    """
    调用 C++ DLL 中的函数

    参数：
        dll_path: DLL 文件路径
        func_name: 函数名称（extern "C" 导出的）
        args: 参数列表
        ret_type: 返回类型

    返回：
        函数返回值
    """
    if args is None:
        args = []

    lib = load_cpp_dll(dll_path)
    if lib is None:
        raise FileNotFoundError(f"Failed to load C++ DLL: {dll_path}")

    argtypes = CTypeMapper.infer_arg_types(args)
    converted_args = CTypeMapper.convert_args(args, argtypes)
    restype = CTypeMapper.infer_ret_type(ret_type)

    try:
        func = lib.get_function(func_name, argtypes=argtypes, restype=restype)
    except AttributeError:
        raise AttributeError(
            f"Function '{func_name}' not found in C++ DLL: {dll_path}. "
            f"Make sure the function is exported with extern \"C\"."
        )

    result = func(*converted_args)

    if restype is ctypes.c_char_p and isinstance(result, bytes):
        result = result.decode('utf-8')

    return result


# ============================================================================
# CppBridge - C++ 桥接实现（继承 LangBridge）
# ============================================================================

class CppBridge(LangBridge):
    """
    C++ 语言桥接实现

    继承 LangBridge 抽象基类，实现 C++ 特定的代码生成、编译和调用。
    """

    name = 'cpp'
    file_ext = '.cpp'
    lib_ext = '.dll' if _IS_WINDOWS else ('.dylib' if _IS_MACOS else '.so')

    def __init__(self):
        super().__init__()
        _setup_cpp_env()
        self._includes = []
        self._link_libs = []

    def compiler_available(self) -> bool:
        """编译器是否可用"""
        return cpp_compiler_available()

    def generate_code(self, spec: FunctionSpec) -> str:
        """
        生成 C++ 代码

        包含：
        1. module_code（用户提供的模块级代码）
        2. 依赖函数（从 deps 参数生成）
        3. 主函数
        """
        parts = []

        # 添加头文件
        if self._includes:
            for inc in self._includes:
                parts.append(f'#include {inc}')
            parts.append('')

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
        """生成单个函数的 C++ 代码"""
        arg_names = []
        cpp_argtypes = []

        for name, ann in spec.annotations.items():
            if name == 'return':
                continue
            arg_names.append(name)
            if ann is None or ann is inspect.Parameter.empty:
                cpp_argtypes.append('int')
            else:
                cpp_argtypes.append(PY_TO_CPP_TYPE.get(ann, 'int'))

        ret_type = 'int'
        if 'return' in spec.annotations:
            ann = spec.annotations['return']
            if ann is type(None) or str(ann).lower() == 'none':
                ret_type = 'void'
            else:
                ret_type = PY_TO_CPP_TYPE.get(ann, 'int')

        params = []
        for i, cpp_t in enumerate(cpp_argtypes):
            name = arg_names[i] if i < len(arg_names) else f'arg{i}'
            params.append(f'{cpp_t} {name}')

        params_str = ', '.join(params)

        indented_body = ''
        for line in spec.body.split('\n'):
            if line.strip():
                indented_body += '    ' + line + '\n'
            else:
                indented_body += '\n'

        if ret_type == 'void':
            return f'''extern "C" void {spec.name}({params_str}) {{
{indented_body}}}'''
        else:
            return f'''extern "C" {ret_type} {spec.name}({params_str}) {{
{indented_body}}}'''

    def compile_code(self, code: str, func_name: str, cache_dir: str = None) -> str:
        """编译 C++ 代码"""
        return _compile_cpp_code(code, func_name, cache_dir)

    def compile_project(self, project_dir: str, entry: str, output_dir: str = None) -> str:
        """
        编译 C++ 项目

        扫描 project_dir 下所有 .cpp 和 .c 文件，调用 g++ 编译器编译。
        entry='main' 时生成可执行文件，否则生成共享库。
        """
        output_dir = output_dir or self.default_cache_dir()
        os.makedirs(output_dir, exist_ok=True)

        src_files = []
        for root, dirs, files in os.walk(project_dir):
            for f in files:
                if f.endswith('.cpp') or f.endswith('.c'):
                    src_files.append(os.path.join(root, f))

        if not src_files:
            raise RuntimeError(f'No .cpp or .c files found in project directory: {project_dir}')

        src_files.sort()

        project_name = os.path.basename(os.path.abspath(project_dir))

        compiler_path, compiler_type = _get_cpp_compiler()
        if not compiler_path:
            raise RuntimeError('C++ compiler not available')

        if entry == 'main':
            if _IS_WINDOWS:
                output_path = os.path.join(output_dir, f'{project_name}.exe')
            else:
                output_path = os.path.join(output_dir, project_name)
            compile_cmd = [compiler_path, '-O2', '-o', output_path] + src_files
        else:
            if _IS_WINDOWS:
                output_path = os.path.join(output_dir, f'{project_name}.dll')
                compile_cmd = [compiler_path, '-shared', '-O2', '-o', output_path] + src_files
            elif _IS_MACOS:
                output_path = os.path.join(output_dir, f'lib{project_name}.dylib')
                compile_cmd = [compiler_path, '-shared', '-fPIC', '-O2', '-o', output_path] + src_files
            else:
                output_path = os.path.join(output_dir, f'lib{project_name}.so')
                compile_cmd = [compiler_path, '-shared', '-fPIC', '-O2', '-o', output_path] + src_files

        result = subprocess.run(
            compile_cmd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
            cwd=output_dir
        )

        if result.returncode != 0:
            raise RuntimeError(
                f'C++ project compilation failed:\n'
                f'stderr:\n{result.stderr}\n'
                f'stdout:\n{result.stdout}\n'
                f'files: {src_files}'
            )

        return output_path

    def call_func(self, lib_path: str, func_name: str,
                  args: tuple, ret_type=None) -> Any:
        """调用 C++ 编译的函数"""
        c_ret_type = None
        if ret_type is not None:
            c_ret_type = CPP_TO_CTYPES.get(ret_type, ctypes.c_int)
        return _call_cpp_func(lib_path, func_name, args, c_ret_type)

    def set_includes(self, includes: list):
        """设置头文件列表"""
        self._includes = includes or []

    def set_link_libs(self, link_libs: list):
        """设置链接库列表"""
        self._link_libs = link_libs or []


# 全局 CppBridge 实例
_cpp_bridge = CppBridge()


# ============================================================================
# 导出
# ============================================================================

__all__ = [
    'cpp',
    'cpp_compiler_available',
    'get_cpp_compiler_info',
    'compile_and_run',
    'load_cpp_dll',
    'call_cpp_func',
    'PY_TO_CPP_TYPE',
    'CPP_TO_CTYPES',
    'CppBridge',
]