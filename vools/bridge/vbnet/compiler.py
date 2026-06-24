"""
vools.bridge.vbnet.compiler - VB.NET 动态编译器

提供 @vbnet 装饰器，支持：
- 自动生成 VB.NET 代码和项目文件
- 调用 dotnet build 编译 DLL
- 基于 MD5 的代码缓存
- ctypes 调用导出函数
- 异步执行支持

使用 manager 统一管理编译器配置。
"""

import os
import subprocess
import hashlib
import tempfile
import ctypes
import inspect
import platform
import asyncio
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Any, Optional

from vools.bridge.manager import get_helper
from vools.bridge._base import LangBridge, FunctionSpec
from .types import get_vb_type, get_vb_ctype, infer_vb_argtypes, PY_TO_VB_TYPE, VB_TO_CTYPES
from .templates import generate_vb_method, generate_vb_class, generate_vbproj

_IS_WINDOWS = platform.system() == 'Windows'

_vbnet_helper = get_helper('vbnet')

_VBNET_CACHE_DIR = os.path.join(tempfile.gettempdir(), 'vools_vbnet_cache')

_executor = ThreadPoolExecutor(max_workers=4)


class VBNetFuture:
    """异步 VB.NET 函数调用的 Future 封装"""

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
        return asyncio.wrap_future(self._future).__await__()


def vbnet_compiler_available():
    """检查 VB.NET 编译器是否可用

    Returns:
        bool: dotnet 是否可用
    """
    return _vbnet_helper.is_available()


def _compile_vbnet_code(vb_code, func_name, cache_dir=None):
    """编译 VB.NET 代码为 DLL

    Args:
        vb_code: VB.NET 类代码（完整类定义）
        func_name: 函数名称（用于命名 DLL）
        cache_dir: 缓存目录，默认使用全局缓存

    Returns:
        DLL 文件路径

    Raises:
        RuntimeError: 编译失败时抛出
    """
    if cache_dir is None:
        cache_dir = _VBNET_CACHE_DIR

    os.makedirs(cache_dir, exist_ok=True)

    code_hash = hashlib.md5(vb_code.encode('utf-8')).hexdigest()[:12]
    dll_name = f'vb_{func_name}_{code_hash}'

    dll_path = os.path.join(cache_dir, dll_name + '.dll')
    if os.path.exists(dll_path):
        return dll_path

    project_dir = os.path.join(cache_dir, dll_name)
    os.makedirs(project_dir, exist_ok=True)

    vb_file = os.path.join(project_dir, 'Bridge.vb')
    vbproj_file = os.path.join(project_dir, 'Bridge.vbproj')

    with open(vb_file, 'w', encoding='utf-8') as f:
        f.write(vb_code)

    with open(vbproj_file, 'w', encoding='utf-8') as f:
        f.write(generate_vbproj())

    result = subprocess.run(
        ['dotnet', 'build', '-c', 'Release', '-o', cache_dir],
        cwd=project_dir,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(f'VB.NET 编译失败:\n{result.stderr}\n{result.stdout}')

    if not os.path.exists(dll_path):
        for file in os.listdir(cache_dir):
            if file.endswith('.dll') and file.startswith('vb_'):
                dll_path = os.path.join(cache_dir, file)
                break
        else:
            raise RuntimeError(f'DLL 未生成: {dll_path}')

    return dll_path


def _call_vbnet_func(dll_path, func_name, args, ret_type=None):
    """调用 VB.NET DLL 中的函数

    Args:
        dll_path: DLL 文件路径
        func_name: 函数名称
        args: 参数列表
        ret_type: Python 返回类型注解

    Returns:
        函数返回值
    """
    lib = ctypes.CDLL(dll_path)

    vb_types, ctypes_types = infer_vb_argtypes(args)

    func = getattr(lib, func_name)
    func.argtypes = ctypes_types

    if ret_type is None or ret_type is type(None):
        func.restype = None
    else:
        vb_ret = get_vb_type(ret_type)
        func.restype = get_vb_ctype(vb_ret)

    converted_args = []
    for arg, vb_type in zip(args, vb_types):
        if vb_type == 'String' and isinstance(arg, str):
            converted_args.append(arg.encode('utf-8'))
        else:
            converted_args.append(arg)

    result = func(*converted_args)

    if func.restype == ctypes.c_char_p and isinstance(result, bytes):
        return result.decode('utf-8')

    return result


def compile_and_run(vb_code, func_name='main', args=(), ret_type=int, cache_dir=None):
    """便捷函数：编译并运行 VB.NET 代码

    Args:
        vb_code: VB.NET 方法体代码
        func_name: 函数名称
        args: 参数列表
        ret_type: 返回类型
        cache_dir: 缓存目录

    Returns:
        函数返回值
    """
    params = []
    for i, arg in enumerate(args):
        vb_type = get_vb_type(type(arg), arg)
        params.append((f'arg{i}', vb_type))

    vb_ret = get_vb_type(ret_type)
    method_code = generate_vb_method(func_name, params, vb_ret, vb_code)
    class_code = generate_vb_class([method_code])

    dll_path = _compile_vbnet_code(class_code, func_name, cache_dir)
    return _call_vbnet_func(dll_path, func_name, args, ret_type)


class VBNetBridge(LangBridge):
    """VB.NET 语言桥接实现

    继承 LangBridge 抽象基类，实现 VB.NET 特定的代码生成、编译和调用。
    """

    name = 'vbnet'
    file_ext = '.vb'
    lib_ext = '.dll'

    def __init__(self):
        super().__init__()

    def compiler_available(self) -> bool:
        """编译器是否可用"""
        return vbnet_compiler_available()

    def generate_code(self, spec: FunctionSpec) -> str:
        """生成 VB.NET 代码

        包含：
        1. module_code（用户提供的模块级代码）
        2. 依赖函数（从 deps 参数生成）
        3. 主函数
        """
        methods = []

        for dep in spec.dependencies:
            dep_method = self._generate_method(dep)
            if dep_method:
                methods.append(dep_method)

        main_method = self._generate_method(spec)
        methods.append(main_method)

        class_code = generate_vb_class(methods)

        if spec.module_code:
            return spec.module_code + '\n' + class_code

        return class_code

    def _generate_method(self, spec: FunctionSpec) -> str:
        """生成单个方法的 VB.NET 代码"""
        params = []

        for name, ann in spec.annotations.items():
            if name == 'return':
                continue
            if ann is None or ann is inspect.Parameter.empty:
                vb_type = 'Integer'
            else:
                vb_type = PY_TO_VB_TYPE.get(ann, 'Integer')
            params.append((name, vb_type))

        ret_type = 'Integer'
        if 'return' in spec.annotations:
            ann = spec.annotations['return']
            if ann is type(None) or str(ann).lower() == 'none':
                ret_type = 'Void'
            else:
                ret_type = PY_TO_VB_TYPE.get(ann, 'Integer')

        return generate_vb_method(spec.name, params, ret_type, spec.body)

    def compile_code(self, code: str, func_name: str, cache_dir: str = None) -> str:
        """编译 VB.NET 代码"""
        return _compile_vbnet_code(code, func_name, cache_dir)

    def compile_project(self, project_dir: str, entry: str, output_dir: Optional[str] = None) -> str:
        """编译 VB.NET 项目

        使用 dotnet build 编译整个项目。
        entry='main' 时生成 exe，否则生成 dll。
        """
        output_dir = output_dir or _VBNET_CACHE_DIR
        os.makedirs(output_dir, exist_ok=True)

        vbproj_files = []
        for root, dirs, files in os.walk(project_dir):
            for f in files:
                if f.endswith('.vbproj'):
                    vbproj_files.append(os.path.join(root, f))

        if not vbproj_files:
            raise RuntimeError(f'No .vbproj file found in project directory: {project_dir}')

        vbproj_file = vbproj_files[0]
        project_dir = os.path.dirname(vbproj_file)

        result = subprocess.run(
            ['dotnet', 'build', '-c', 'Release', '-o', output_dir],
            cwd=project_dir,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True
        )

        if result.returncode != 0:
            raise RuntimeError(
                f'VB.NET project compilation failed:\n'
                f'stderr:\n{result.stderr}\n'
                f'stdout:\n{result.stdout}'
            )

        project_name = os.path.splitext(os.path.basename(vbproj_file))[0]

        if entry == 'main':
            if _IS_WINDOWS:
                output_path = os.path.join(output_dir, f'{project_name}.exe')
            else:
                output_path = os.path.join(output_dir, project_name)
        else:
            output_path = os.path.join(output_dir, f'{project_name}.dll')

        if not os.path.exists(output_path):
            for f in os.listdir(output_dir):
                if entry == 'main':
                    if f.endswith('.exe') or (not _IS_WINDOWS and not f.endswith('.dll') and os.path.isfile(os.path.join(output_dir, f))):
                        output_path = os.path.join(output_dir, f)
                        break
                else:
                    if f.endswith('.dll') and not f.endswith('.runtimeconfig.dev.json'):
                        output_path = os.path.join(output_dir, f)
                        break

        return output_path

    def call_func(self, lib_path: str, func_name: str,
                  args: tuple, ret_type=None) -> Any:
        """调用 VB.NET 编译的函数

        Args:
            lib_path: DLL 文件路径。
            func_name: 函数名称。
            args: 参数元组。
            ret_type: Python 返回类型，用于类型转换。

        Returns:
            函数返回值。
        """
        return _call_vbnet_func(lib_path, func_name, args, ret_type)


_vbnet_bridge = VBNetBridge()

vbnet = _vbnet_bridge.decorator
vb = vbnet
