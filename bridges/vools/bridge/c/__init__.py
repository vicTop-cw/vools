"""
vools.bridge.c - C 语言桥接模块

提供 C 语言 DLL 的加载和调用支持，包括自动类型推断、参数转换和便捷装饰器。
同时支持动态编译 C 代码。

用法：
    from vools.bridge.c import load_dll, call_func, c_dll, CDLLWrapper

    # 方式 1: 直接加载和调用
    lib = load_dll("mylib.dll")
    result = call_func("mylib.dll", "add", [1, 2], ret_type=int)

    # 方式 2: 使用装饰器
    @c_dll("mylib.dll")
    def add(a: int, b: int) -> int:
        pass

    # 方式 3: 使用 CDLLWrapper
    lib = CDLLWrapper("mylib.dll")
    result = lib.add(1, 2)
"""

import os
import sys
import tempfile
import hashlib
import platform
import inspect
import functools
import ctypes
import subprocess
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ..core.loader import load_from_path, SharedLibrary
from ..core.types import CTypeMapper, LangType
from ..manager import get_helper, manager
from .._base import LangBridge, FunctionSpec, FunctionParser

# 平台判断
_IS_WINDOWS = platform.system() == 'Windows'
_IS_LINUX = platform.system() == 'Linux'
_IS_MACOS = platform.system() == 'Darwin'

# 使用 manager 的编译器辅助
_c_helper = get_helper('c')


def _setup_c_env():
    """设置 C 编译环境"""
    _c_helper.setup_env()


_setup_c_env()


def _get_c_path():
    """获取 C 编译器路径"""
    c_path = _c_helper.get_compiler_path()
    if c_path:
        # 检测是否使用了 FreeBASIC 自带的损坏 gcc（缺少系统库）
        c_path_norm = os.path.normpath(c_path).lower()
        if 'freebasic' in c_path_norm:
            # 尝试从 C++ 桥接的 g++ 目录找到可用的 gcc
            try:
                cpp_path = manager.get_compiler_path('cpp')
                if cpp_path:
                    cpp_dir = os.path.dirname(cpp_path)
                    gcc_name = 'gcc.exe' if _IS_WINDOWS else 'gcc'
                    gcc_path = os.path.join(cpp_dir, gcc_name)
                    if os.path.isfile(gcc_path):
                        # 测试 gcc 是否可用
                        try:
                            result = subprocess.run(
                                [gcc_path, '--version'],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, timeout=10
                            )
                            if result.returncode == 0:
                                return gcc_path
                        except Exception:
                            pass
            except Exception:
                pass
        return c_path
    return 'gcc' if _IS_WINDOWS else 'cc'


def c_compiler_available():
    """检查 C 编译器是否可用"""
    return _c_helper.is_available()


# 编译缓存目录
_C_CACHE_DIR = os.path.join(tempfile.gettempdir(), 'vools_c_cache')

# 类型映射
PY_TO_C_TYPE = {
    int: 'int',
    float: 'double',
    bool: 'int',
    str: 'const char*',
    bytes: 'const char*',
}

C_TO_CTYPES = {
    'int': ctypes.c_int,
    'double': ctypes.c_double,
    'float': ctypes.c_float,
    'const char*': ctypes.c_char_p,
    'char*': ctypes.c_char_p,
    'void': None,
}

__all__ = [
    'load_dll',
    'call_func',
    'c_dll',
    'CDLLWrapper',
]


def load_dll(dll_path):
    """
    加载 C 动态链接库

    复用 core.loader 的 load_from_path，返回 SharedLibrary 实例。
    加载失败时返回 None。

    参数：
        dll_path: DLL 文件路径，可以是相对路径或绝对路径

    返回：
        SharedLibrary 实例，加载失败返回 None

    示例：
        >>> lib = load_dll("vools_crypto.dll")
        >>> if lib:
        ...     print("加载成功")
    """
    return load_from_path(dll_path)


def call_func(dll_path, func_name, args=None, ret_type=None):
    """
    调用 DLL 中的函数

    自动推断参数类型和返回类型，自动转换参数格式（如 str -> bytes），
    自动处理字符串返回值（bytes -> str）。

    参数：
        dll_path: DLL 文件路径
        func_name: 函数名称
        args: 参数列表，默认为空列表
        ret_type: 返回类型注解（如 int、str 等），为 None 时自动推断

    返回：
        函数返回值，字符串类型会自动从 bytes 转换为 str

    异常：
        FileNotFoundError: DLL 文件不存在或加载失败
        AttributeError: 函数不存在于 DLL 中

    示例：
        >>> result = call_func("vools_crypto.dll", "md5_hash",
        ...                    ["hello", 5], ret_type=str)
        >>> print(result)
        5d41402abc4b2a76b9719d911017c592
    """
    if args is None:
        args = []

    lib = load_dll(dll_path)
    if lib is None:
        raise FileNotFoundError("Failed to load DLL: %s" % dll_path)

    argtypes = CTypeMapper.infer_arg_types(args)
    converted_args = CTypeMapper.convert_args(args, argtypes)

    restype = CTypeMapper.infer_ret_type(ret_type)

    try:
        func = lib.get_function(func_name, argtypes=argtypes, restype=restype)
    except AttributeError:
        raise AttributeError(
            "Function '%s' not found in DLL: %s" % (func_name, dll_path)
        )

    result = func(*converted_args)

    if restype is ctypes.c_char_p and isinstance(result, bytes):
        result = result.decode('utf-8')

    return result


def _get_type_annotation(annotation):
    """
    从类型注解中提取 Python 类型

    参数：
        annotation: 类型注解

    返回：
        Python 类型，如果无法识别则返回 None
    """
    if annotation is inspect.Parameter.empty:
        return None
    if isinstance(annotation, type):
        return annotation
    return None


def c_dll(dll_path=None, func_name=None, **kwargs):
    """
    C DLL 函数装饰器

    根据函数签名的类型注解自动推断 ctypes 类型，生成可以直接调用的桥接函数。
    支持两种使用方式：

    1. 位置参数方式：@c_dll("mylib.dll")
    2. 关键字参数方式：@c_dll(dll_path="mylib.dll", func_name="add")

    参数：
        dll_path: DLL 文件路径
        func_name: DLL 中的函数名，默认为被装饰函数的名称
        **kwargs: 其他参数（预留）

    返回：
        装饰器函数

    异常：
        FileNotFoundError: DLL 文件不存在或加载失败时抛出
        AttributeError: 函数不存在于 DLL 中时抛出

    示例：
        >>> @c_dll("vools_crypto.dll")
        ... def md5_hash(data: str, length: int) -> str:
        ...     pass
        ...
        >>> result = md5_hash("hello", 5)
        >>> print(result)
        5d41402abc4b2a76b9719d911017c592

        >>> @c_dll(dll_path="vools_crypto.dll", func_name="md5_hash")
        ... def my_md5(data: str, length: int) -> str:
        ...     pass
    """
    def decorator(func):
        nonlocal dll_path, func_name

        if dll_path is None:
            raise ValueError("dll_path must be specified")

        if func_name is None:
            func_name = func.__name__

        sig = inspect.signature(func)
        params = list(sig.parameters.values())

        param_types = []
        for param in params:
            py_type = _get_type_annotation(param.annotation)
            param_types.append(py_type)

        ret_type = _get_type_annotation(sig.return_annotation)

        argtypes = []
        for py_type in param_types:
            if py_type is not None:
                c_type = CTypeMapper.get_ctype(py_type)
                if c_type is not None:
                    argtypes.append(c_type)
                else:
                    argtypes.append(ctypes.c_void_p)
            else:
                argtypes.append(ctypes.c_void_p)

        restype = CTypeMapper.infer_ret_type(ret_type)

        lib = load_dll(dll_path)
        if lib is None:
            raise FileNotFoundError(
                "Failed to load DLL: %s" % dll_path
            )

        try:
            c_func = lib.get_function(
                func_name, argtypes=argtypes, restype=restype
            )
        except AttributeError:
            raise AttributeError(
                "Function '%s' not found in DLL: %s" % (func_name, dll_path)
            )

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if kwargs:
                bound = sig.bind(*args, **kwargs)
                bound.apply_defaults()
                args = bound.arguments.values()
                args = list(args)

            converted_args = CTypeMapper.convert_args(args, argtypes)
            result = c_func(*converted_args)

            if restype is ctypes.c_char_p and isinstance(result, bytes):
                result = result.decode('utf-8')

            return result

        wrapper._dll_path = dll_path
        wrapper._func_name = func_name
        wrapper._argtypes = argtypes
        wrapper._restype = restype

        return wrapper

    if callable(dll_path) and func_name is None and not kwargs:
        actual_func = dll_path
        dll_path = None
        return decorator(actual_func)

    return decorator


class CDLLWrapper:
    """
    C DLL 便捷封装类

    封装一个 DLL，支持通过属性方式直接访问函数，
    自动进行类型推断和参数转换。

    支持预先注册函数签名以获得更好的类型安全和自动转换。

    属性：
        path: DLL 文件路径
        _lib: SharedLibrary 实例
        _signatures: 已注册的函数字典 {name: (argtypes, restype)}

    示例：
        >>> lib = CDLLWrapper("vools_crypto.dll")
        >>> lib.declare("md5_hash", [str, int], str)
        >>> result = lib.md5_hash("hello", 5)
        >>> print(result)
        5d41402abc4b2a76b9719d911017c592
    """

    def __init__(self, dll_path):
        """
        初始化 CDLLWrapper

        参数：
            dll_path: DLL 文件路径

        异常：
            FileNotFoundError: DLL 文件不存在或加载失败
        """
        self.path = os.path.abspath(dll_path)
        self._lib = load_dll(dll_path)
        if self._lib is None:
            raise FileNotFoundError(
                "Failed to load DLL: %s" % dll_path
            )
        self._func_cache = {}
        self._signatures = {}

    def declare(self, func_name, arg_types=None, ret_type=None):
        """
        注册函数签名

        参数：
            func_name: 函数名称
            arg_types: 参数类型列表（Python 类型），如 [str, int]
            ret_type: 返回类型（Python 类型），如 str、int

        返回：
            self，支持链式调用
        """
        argtypes = None
        if arg_types is not None:
            argtypes = []
            for py_type in arg_types:
                c_type = CTypeMapper.get_ctype(py_type)
                if c_type is not None:
                    argtypes.append(c_type)
                else:
                    argtypes.append(ctypes.c_void_p)

        restype = CTypeMapper.infer_ret_type(ret_type)

        self._signatures[func_name] = (argtypes, restype)

        if func_name in self._func_cache:
            del self._func_cache[func_name]

        return self

    def __getattr__(self, name):
        """
        通过属性访问 DLL 函数

        自动缓存已获取的函数，支持自动类型推断和参数转换。
        如果已通过 declare() 注册了函数签名，则使用注册的类型；
        否则根据参数值自动推断参数类型，返回值使用 ctypes 默认行为。

        参数：
            name: 函数名称

        返回：
            包装后的可调用函数对象

        异常：
            AttributeError: 函数不存在时抛出
        """
        if name.startswith('_'):
            raise AttributeError(name)

        if name in self._func_cache:
            return self._func_cache[name]

        try:
            c_func = getattr(self._lib, name)
        except AttributeError:
            raise AttributeError(
                "'CDLLWrapper' object has no attribute '%s'" % name
            )

        if name in self._signatures:
            argtypes, restype = self._signatures[name]
            if argtypes is not None:
                c_func.argtypes = argtypes
            if restype is not None:
                c_func.restype = restype

            @functools.wraps(c_func)
            def wrapper(*args, **kwargs):
                if argtypes is not None:
                    converted_args = CTypeMapper.convert_args(
                        list(args), argtypes
                    )
                else:
                    converted_args = list(args)
                result = c_func(*converted_args, **kwargs)
                if restype is ctypes.c_char_p and isinstance(result, bytes):
                    try:
                        return result.decode('utf-8')
                    except UnicodeDecodeError:
                        return result
                return result

            self._func_cache[name] = wrapper
            return wrapper

        @functools.wraps(c_func)
        def wrapper(*args, **kwargs):
            argtypes = CTypeMapper.infer_arg_types(args)
            converted_args = CTypeMapper.convert_args(args, argtypes)

            c_func.argtypes = argtypes
            result = c_func(*converted_args, **kwargs)

            if isinstance(result, bytes):
                try:
                    return result.decode('utf-8')
                except UnicodeDecodeError:
                    return result
            return result

        self._func_cache[name] = wrapper
        return wrapper

    def __repr__(self):
        """返回对象的字符串表示"""
        return "CDLLWrapper('%s')" % self.path


# ============================================================================
# 编译函数
# ============================================================================

def _compile_c_code(code: str, func_name: str, cache_dir: str = None) -> str:
    """
    编译 C 代码并返回共享库路径

    参数：
        code: C 代码字符串
        func_name: 函数名（用于生成文件名）
        cache_dir: 缓存目录

    返回：
        编译后的共享库路径
    """
    if cache_dir is None:
        cache_dir = _C_CACHE_DIR

    os.makedirs(cache_dir, exist_ok=True)

    code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
    lib_name = f'c_{func_name}_{code_hash}'

    if _IS_WINDOWS:
        lib_path = os.path.join(cache_dir, f'{lib_name}.dll')
    elif _IS_MACOS:
        lib_path = os.path.join(cache_dir, f'lib{lib_name}.dylib')
    else:
        lib_path = os.path.join(cache_dir, f'lib{lib_name}.so')

    if os.path.exists(lib_path):
        return lib_path

    c_file = os.path.join(cache_dir, f'{lib_name}.c')
    with open(c_file, 'w', encoding='utf-8') as f:
        f.write(code)

    compiler_path = _get_c_path()

    if _IS_WINDOWS:
        compile_cmd = [
            compiler_path, '-shared', '-o', lib_path,
            '-O2', c_file
        ]
    else:
        compile_cmd = [
            compiler_path, '-shared', '-fPIC',
            '-o', lib_path, '-O2', c_file
        ]

    result = subprocess.run(
        compile_cmd,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True,
        cwd=cache_dir
    )

    if result.returncode != 0:
        raise RuntimeError(
            f'C compilation failed:\n{result.stderr}\n{result.stdout}'
        )

    try:
        os.remove(c_file)
    except OSError:
        pass

    return lib_path


def _call_c_func(lib_path: str, func_name: str, args: tuple, ret_type=None):
    """
    调用 C 编译的函数

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

    argtypes = CTypeMapper.infer_arg_types(args)
    func.argtypes = argtypes
    if ret_type is not None:
        func.restype = ret_type

    converted_args = CTypeMapper.convert_args(args, argtypes)
    result = func(*converted_args)

    if ret_type == ctypes.c_char_p and result:
        result = result.decode('utf-8')

    return result


# ============================================================================
# CBridge - C 桥接实现（继承 LangBridge）
# ============================================================================

class CBridge(LangBridge):
    """
    C 语言桥接实现

    继承 LangBridge 抽象基类，实现 C 特定的代码生成、编译和调用。
    """

    name = 'c'
    file_ext = '.c'
    lib_ext = '.dll' if _IS_WINDOWS else ('.dylib' if _IS_MACOS else '.so')
    lang_type = LangType.COMPILED

    def __init__(self):
        super().__init__()
        _setup_c_env()
        self._includes = []

    def compiler_available(self) -> bool:
        """编译器是否可用"""
        return c_compiler_available()

    def generate_code(self, spec: FunctionSpec) -> str:
        """
        生成 C 代码

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
        """生成单个函数的 C 代码"""
        arg_names = []
        c_argtypes = []

        for name, ann in spec.annotations.items():
            if name == 'return':
                continue
            arg_names.append(name)
            if ann is None or ann is inspect.Parameter.empty:
                c_argtypes.append('int')
            else:
                c_argtypes.append(PY_TO_C_TYPE.get(ann, 'int'))

        ret_type = 'int'
        if 'return' in spec.annotations:
            ann = spec.annotations['return']
            if ann is type(None) or str(ann).lower() == 'none':
                ret_type = 'void'
            else:
                ret_type = PY_TO_C_TYPE.get(ann, 'int')

        params = []
        for i, c_t in enumerate(c_argtypes):
            name = arg_names[i] if i < len(arg_names) else f'arg{i}'
            params.append(f'{c_t} {name}')

        params_str = ', '.join(params) if params else 'void'

        indented_body = ''
        for line in spec.body.split('\n'):
            if line.strip():
                indented_body += '    ' + line + '\n'
            else:
                indented_body += '\n'

        return f'''{ret_type} {spec.name}({params_str}) {{
{indented_body}}}'''

    def compile_code(self, code: str, func_name: str, cache_dir: str = None) -> str:
        """编译 C 代码"""
        return _compile_c_code(code, func_name, cache_dir)

    def compile_project(self, project_dir: str, entry: str, output_dir: str = None) -> str:
        """
        编译 C 项目

        扫描 project_dir 下所有 .c 文件，调用 gcc 编译器编译。
        entry='main' 时生成 exe，否则生成 dll。
        """
        output_dir = output_dir or _C_CACHE_DIR
        os.makedirs(output_dir, exist_ok=True)

        c_files = []
        for root, dirs, files in os.walk(project_dir):
            for f in files:
                if f.endswith('.c'):
                    c_files.append(os.path.join(root, f))

        if not c_files:
            raise RuntimeError(f'No .c files found in project directory: {project_dir}')

        c_files.sort()

        project_name = os.path.basename(os.path.abspath(project_dir))

        compiler_path = _get_c_path()

        if entry == 'main':
            if _IS_WINDOWS:
                output_path = os.path.join(output_dir, f'{project_name}.exe')
            else:
                output_path = os.path.join(output_dir, project_name)
            compile_cmd = [compiler_path, '-O2', '-o', output_path] + c_files
        else:
            if _IS_WINDOWS:
                output_path = os.path.join(output_dir, f'{project_name}.dll')
                compile_cmd = [compiler_path, '-shared', '-O2', '-o', output_path] + c_files
            elif _IS_MACOS:
                output_path = os.path.join(output_dir, f'lib{project_name}.dylib')
                compile_cmd = [compiler_path, '-shared', '-fPIC', '-O2', '-o', output_path] + c_files
            else:
                output_path = os.path.join(output_dir, f'lib{project_name}.so')
                compile_cmd = [compiler_path, '-shared', '-fPIC', '-O2', '-o', output_path] + c_files

        result = subprocess.run(
            compile_cmd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
            cwd=output_dir
        )

        if result.returncode != 0:
            raise RuntimeError(
                f'C project compilation failed:\n'
                f'stderr:\n{result.stderr}\n'
                f'stdout:\n{result.stdout}\n'
                f'files: {c_files}'
            )

        return output_path

    def call_func(self, lib_path: str, func_name: str,
                  args: tuple, ret_type=None) -> Any:
        """调用 C 编译的函数"""
        c_ret_type = None
        if ret_type is not None:
            # ret_type 可能是 Python 类型（如 float）或 C 类型字符串（如 'double'）
            if isinstance(ret_type, type):
                c_type_str = PY_TO_C_TYPE.get(ret_type)
                if c_type_str:
                    c_ret_type = C_TO_CTYPES.get(c_type_str, ctypes.c_int)
                else:
                    c_ret_type = ctypes.c_int
            else:
                c_ret_type = C_TO_CTYPES.get(ret_type, ctypes.c_int)
        return _call_c_func(lib_path, func_name, args, c_ret_type)

    def set_includes(self, includes: list):
        """设置头文件列表"""
        self._includes = includes or []


# 全局 CBridge 实例
_c_bridge = CBridge()


# 更新导出
__all__.extend([
    'CBridge',
    'c_compiler_available',
    'PY_TO_C_TYPE',
    'C_TO_CTYPES',
])
