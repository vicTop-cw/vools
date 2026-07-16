"""
vools.bridge.nim.compiler - Nim 异步动态编译装饰器

使用方式：
    @nim
    def my_func(x: int) -> int:
        return "x * 2"  # 返回 Nim 代码字符串

    result = my_func(5)  # 编译 Nim 代码并执行
"""

import os
import sys
import tempfile
import hashlib
import platform
import asyncio
import inspect
import functools
import warnings
import threading
import ctypes
import shutil
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Any

from ..core.types import CTypeMapper
from ..manager import manager, setup_runtime as _setup_lang_runtime
from .._base import LangBridge, FunctionSpec, FunctionParser
from ..core.types import LangType

# 平台判断
_IS_WINDOWS = platform.system() == 'Windows'
_IS_LINUX = platform.system() == 'Linux'

# 从 manager 获取配置
def _get_nim_config():
    """获取 Nim 语言配置"""
    return manager.get_config('nim')

def _setup_nim_env():
    """设置 Nim 编译环境（委托给 manager）"""
    # 使用 manager 设置运行时
    _setup_lang_runtime('nim')

    # 额外的 Windows DLL 路径（compiler.py 特有）
    if _IS_WINDOWS:
        config = _get_nim_config()
        if config:
            runtime_paths = config.runtime_paths
            add_dll_dir = getattr(os, 'add_dll_directory', None)
            if add_dll_dir:
                for p in runtime_paths:
                    if os.path.exists(p):
                        try:
                            add_dll_dir(p)
                        except OSError:
                            pass


_setup_nim_env()


def _get_nim_path():
    """获取 Nim 编译器路径（委托给 manager）"""
    return manager.get_compiler_path('nim') or 'nim'


def nim_compiler_available():
    """
    检查 Nim 编译器是否可用

    返回：
        bool: 如果 Nim 编译器可用返回 True，否则返回 False
    """
    return manager.is_available('nim')


def _compile_nim_code(code: str, func_name: str, cache_dir: str = None) -> str:
    """
    编译 Nim 代码并返回共享库路径

    参数：
        code: Nim 代码字符串
        func_name: 函数名（用于生成文件名）
        cache_dir: 缓存目录，None 则使用系统临时目录

    返回：
        编译后的共享库路径
    """
    if cache_dir is None:
        cache_dir = os.path.join(tempfile.gettempdir(), 'vools_nim_cache')

    os.makedirs(cache_dir, exist_ok=True)

    # 生成唯一文件名
    code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
    dll_name = f'nim_{func_name}_{code_hash}'

    if _IS_WINDOWS:
        dll_path = os.path.join(cache_dir, f'{dll_name}.dll')
    else:
        dll_path = os.path.join(cache_dir, f'lib{dll_name}.so')

    # 检查缓存
    if os.path.exists(dll_path):
        return dll_path

    # 写入临时 .nim 文件
    nim_file = os.path.join(cache_dir, f'{dll_name}.nim')
    with open(nim_file, 'w', encoding='utf-8') as f:
        f.write(code)

    # 编译命令
    nim_path = _get_nim_path()

    if _IS_WINDOWS:
        # 提取所有导出函数名，用于 MSVC /EXPORT 链接器标志
        # Nim 的 {.exportc.} 在 MSVC 下生成 N_LIB_PRIVATE（空符号），
        # 需要使用 /EXPORT 强制导出符号；/link 前缀将标志传递给 link.exe
        import re
        export_names = re.findall(r'\{\.exportc:\s*"(\w+)"', code)
        compile_cmd = [
            nim_path, 'c', '--app:lib',
            '--out:' + dll_path,
            '-d:release',
        ]
        if export_names:
            compile_cmd.append('--passL=/link')
            for name in export_names:
                compile_cmd.append('--passL=/EXPORT:' + name)
        compile_cmd.append(nim_file)
    else:
        compile_cmd = [
            nim_path, 'c', '--app:lib',
            '--out:' + dll_path,
            '--passL:-Wl,-E',  # 导出所有符号
            '-d:release',
            nim_file
        ]

    # 执行编译
    import subprocess
    result = subprocess.run(
        compile_cmd,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True,
        cwd=cache_dir
    )

    if result.returncode != 0:
        # Nim 可能在链接成功后仍返回非零退出码（如 nimcache JSON 写入失败）
        # 如果 DLL 已成功生成，则视为编译成功
        if os.path.exists(dll_path):
            pass  # DLL 已生成，忽略非致命错误
        else:
            raise RuntimeError(f'Nim 编译失败:\n{result.stderr}\n{result.stdout}')

    # 清理临时 .nim 文件
    try:
        os.remove(nim_file)
    except OSError:
        pass

    return dll_path


def _load_nim_dll(dll_path: str):
    """加载 Nim 共享库"""
    import ctypes

    if not os.path.exists(dll_path):
        raise FileNotFoundError(f'共享库不存在: {dll_path}')

    return ctypes.CDLL(dll_path)


def _call_nim_func(dll_path: str, func_name: str, args: tuple, ret_type=None):
    """
    调用 Nim 编译的函数

    参数：
        dll_path: 共享库路径
        func_name: 函数名
        args: 参数元组
        ret_type: 返回类型（ctypes 类型）

    返回：
        函数返回值
    """
    lib = _load_nim_dll(dll_path)
    func = getattr(lib, func_name)

    # 使用 core 层的类型映射
    argtypes = CTypeMapper.infer_arg_types(args)
    func.argtypes = argtypes
    if ret_type is not None:
        func.restype = ret_type

    # 转换参数（如 str -> bytes）
    converted_args = CTypeMapper.convert_args(args, argtypes)

    # 调用函数
    result = func(*converted_args)

    # 处理字符串返回值
    if ret_type == ctypes.c_char_p and result:
        result = result.decode('utf-8')

    return result


# 类型映射 - 使用 C 兼容类型以确保 ABI 兼容
PY_TO_NIM_TYPE = {
    int: 'cint',
    float: 'cdouble',
    bool: 'bool',
    str: 'cstring',
    bytes: 'cstring',
}

NIM_TO_CTYPES = {
    'cint': ctypes.c_int,
    'cdouble': ctypes.c_double,
    'bool': ctypes.c_bool,
    'cstring': ctypes.c_char_p,
    'string': ctypes.c_char_p,
    'int': ctypes.c_long,
    'float': ctypes.c_double,
}


def _generate_nim_wrapper(func_name: str, args: tuple, nim_body: str,
                          ret_type: str = 'cint', arg_names: list = None) -> str:
    """
    生成完整的 Nim 代码

    参数：
        func_name: 函数名
        args: 参数元组
        nim_body: Nim 函数体代码
        ret_type: 返回类型
        arg_names: 参数名列表（可选，None 则使用 arg0, arg1...）

    返回：
        完整的 Nim 代码字符串
    """
    # 确保返回类型是 C 兼容类型
    type_mapping = {
        'int': 'cint',
        'float': 'cdouble',
        'bool': 'bool',
        'string': 'cstring',
    }
    actual_ret_type = type_mapping.get(ret_type, ret_type)

    # 生成参数列表
    params = []
    for i, arg in enumerate(args):
        arg_type = PY_TO_NIM_TYPE.get(type(arg), 'cint')
        if arg_names and i < len(arg_names):
            param_name = arg_names[i]
        else:
            param_name = f'arg{i}'
        params.append(f'{param_name}: {arg_type}')

    params_str = ', '.join(params)

    # 处理函数体缩进 - 确保每一行都有正确的缩进
    indented_body = ''
    for line in nim_body.split('\n'):
        if line.strip():
            indented_body += '  ' + line + '\n'
        else:
            indented_body += '\n'

    # 生成导出函数 - 使用 exportc 确保正确的符号导出
    if actual_ret_type == 'void':
        code = f'''proc {func_name}*({params_str}) {{.exportc: "{func_name}".}} =
{indented_body}'''
    else:
        code = f'''proc {func_name}*({params_str}): {actual_ret_type} {{.exportc: "{func_name}".}} =
{indented_body}'''
    return code


# 异步执行器
_executor = ThreadPoolExecutor(max_workers=4)


class NimFuture:
    """异步 Nim 函数调用的 Future 封装"""

    def __init__(self, future: Future, dll_path: str, func_name: str, ret_type):
        self._future = future
        self._dll_path = dll_path
        self._func_name = func_name
        self._ret_type = ret_type

    def result(self, timeout=None):
        return self._future.result(timeout)

    def __iter__(self):
        return self

    def __next__(self):
        return self.result()

    def __await__(self):
        return self._future.__await__()





# 便捷函数：直接编译运行代码
def compile_and_run(nim_code: str, func_name: str = 'main',
                     args: tuple = (), ret_type: str = 'int',
                     cache_dir: str = None):
    """
    直接编译并运行 Nim 代码

    参数：
        nim_code: Nim 代码字符串
        func_name: 函数名（默认 'main'）
        args: 参数元组
        ret_type: 返回类型
        cache_dir: 缓存目录

    返回：
        函数返回值
    """
    full_code = _generate_nim_wrapper(func_name, args, nim_code, ret_type)
    dll_path = _compile_nim_code(full_code, func_name, cache_dir)
    c_ret_type = NIM_TO_CTYPES.get(ret_type, ctypes.c_long) if ret_type != 'void' else None

    return _call_nim_func(dll_path, func_name, args, c_ret_type)


# ============================================================================
# NimBridge - Nim 桥接实现（继承 LangBridge）
# ============================================================================

class NimBridge(LangBridge):
    """
    Nim 语言桥接实现

    继承 LangBridge 抽象基类，实现 Nim 特定的代码生成、编译和调用。
    """

    name = 'nim'
    file_ext = '.nim'
    lib_ext = '.dll' if _IS_WINDOWS else '.so'
    lang_type = LangType.COMPILED

    def __init__(self):
        super().__init__()
        _setup_nim_env()

    def compiler_available(self) -> bool:
        """编译器是否可用"""
        return nim_compiler_available()

    def generate_code(self, spec: FunctionSpec) -> str:
        """
        生成 Nim 代码

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
        """生成单个函数的 Nim 代码"""
        arg_names = []
        nim_argtypes = []

        for name, ann in spec.annotations.items():
            if name == 'return':
                continue
            arg_names.append(name)
            if ann is None or ann is inspect.Parameter.empty:
                nim_argtypes.append('cint')
            else:
                nim_argtypes.append(PY_TO_NIM_TYPE.get(ann, 'cint'))

        ret_type = 'cint'
        if 'return' in spec.annotations:
            ann = spec.annotations['return']
            if ann is type(None) or str(ann).lower() == 'none':
                ret_type = 'void'
            else:
                ret_type = PY_TO_NIM_TYPE.get(ann, 'cint')

        params = []
        for i, nim_t in enumerate(nim_argtypes):
            name = arg_names[i] if i < len(arg_names) else f'arg{i}'
            params.append(f'{name}: {nim_t}')

        params_str = ', '.join(params)

        indented_body = ''
        for line in spec.body.split('\n'):
            if line.strip():
                indented_body += '  ' + line + '\n'
            else:
                indented_body += '\n'

        if ret_type == 'void':
            return f'''proc {spec.name}*({params_str}) {{.exportc: "{spec.name}".}} =
{indented_body}'''
        else:
            return f'''proc {spec.name}*({params_str}): {ret_type} {{.exportc: "{spec.name}".}} =
{indented_body}'''

    def compile_code(self, code: str, func_name: str, cache_dir: str = None) -> str:
        """编译 Nim 代码"""
        return _compile_nim_code(code, func_name, cache_dir)

    def compile_project(self, project_dir: str, entry: str, output_dir: str = None) -> str:
        """
        编译 Nim 项目

        扫描 project_dir 下所有 .nim 文件，调用 nim 编译器编译。
        entry='main' 时生成可执行文件，否则生成共享库。
        """
        import subprocess

        output_dir = output_dir or os.path.join(tempfile.gettempdir(), 'vools_nim_cache')
        os.makedirs(output_dir, exist_ok=True)

        nim_files = []
        for root, dirs, files in os.walk(project_dir):
            for f in files:
                if f.endswith('.nim'):
                    nim_files.append(os.path.join(root, f))

        if not nim_files:
            raise RuntimeError(f'No .nim files found in project directory: {project_dir}')

        nim_files.sort()

        project_name = os.path.basename(os.path.abspath(project_dir))

        main_file = None
        entry_nim = f'{entry}.nim'
        for nf in nim_files:
            if os.path.basename(nf) == entry_nim:
                main_file = nf
                break
        if main_file is None:
            for nf in nim_files:
                if os.path.basename(nf) == 'main.nim':
                    main_file = nf
                    break
        if main_file is None:
            main_file = nim_files[0]

        nim_path = _get_nim_path()

        if entry == 'main':
            if _IS_WINDOWS:
                output_path = os.path.join(output_dir, f'{project_name}.exe')
            else:
                output_path = os.path.join(output_dir, project_name)
            compile_cmd = [
                nim_path, 'c',
                f'--out:{output_path}',
                '-d:release',
                main_file
            ]
        else:
            if _IS_WINDOWS:
                output_path = os.path.join(output_dir, f'{project_name}.dll')
            else:
                output_path = os.path.join(output_dir, f'lib{project_name}.so')
            compile_cmd = [
                nim_path, 'c',
                '--app:lib',
                '--noMain',
                f'--out:{output_path}',
                '-d:release',
                main_file
            ]

        result = subprocess.run(
            compile_cmd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
            cwd=output_dir
        )

        if result.returncode != 0:
            raise RuntimeError(
                f'Nim project compilation failed:\n'
                f'stderr:\n{result.stderr}\n'
                f'stdout:\n{result.stdout}\n'
                f'files: {nim_files}\n'
                f'main: {main_file}'
            )

        return output_path

    def call_func(self, lib_path: str, func_name: str,
                  args: tuple, ret_type=None) -> Any:
        """调用 Nim 编译的函数"""
        c_ret_type = None
        if ret_type is not None:
            # ret_type 可能是 Python 类型（如 int, float, bool）或字符串
            nim_type = PY_TO_NIM_TYPE.get(ret_type, ret_type)
            c_ret_type = NIM_TO_CTYPES.get(nim_type, ctypes.c_long)
        return _call_nim_func(lib_path, func_name, args, c_ret_type)


# 全局 NimBridge 实例
_nim_bridge = NimBridge()

# 装饰器：直接使用基类的 decorator 方法
nim = _nim_bridge.decorator

