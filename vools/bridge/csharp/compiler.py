"""
vools.bridge.csharp.compiler - C# 动态编译器

提供 @csharp 装饰器，支持：
- 自动生成 C# 代码和项目文件
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
import functools
import inspect
import platform
import asyncio
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Any

from vools.bridge.manager import get_helper
from vools.bridge._base import LangBridge, FunctionSpec
from .types import get_cs_type, get_cs_ctype, infer_cs_argtypes, PY_TO_CS_TYPE, CS_TO_CTYPES
from .templates import generate_cs_method, generate_cs_class, generate_csproj

_IS_WINDOWS = platform.system() == 'Windows'

# 使用 manager 的编译器辅助
_csharp_helper = get_helper('csharp')

# 缓存目录
_CS_CACHE_DIR = os.path.join(tempfile.gettempdir(), 'vools_csharp_cache')

# 异步执行器
_executor = ThreadPoolExecutor(max_workers=4)


class CsharpFuture:
    """异步 C# 函数调用的 Future 封装"""

    def __init__(self, future: Future, dll_path: str, func_name: str, ret_type):
        self._future = future
        self._dll_path = dll_path
        self._func_name = func_name
        self._ret_type = ret_type

    def result(self, timeout=None):
        """获取结果（阻塞）"""
        return self._future.result(timeout)

    def __iter__(self):
        return self

    def __next__(self):
        return self.result()

    def __await__(self):
        # 使用 asyncio.wrap_future 将 concurrent.futures.Future 转换为 asyncio Future
        return asyncio.wrap_future(self._future).__await__()


def csharp_compiler_available():
    """
    检查 C# 编译器是否可用

    使用 manager 统一管理。

    返回：
        bool: dotnet 是否可用
    """
    return _csharp_helper.is_available()


def _compile_csharp_code(cs_code, func_name, cache_dir=None):
    """
    编译 C# 代码为 DLL

    流程：
    1. 计算代码 MD5 哈希
    2. 检查缓存是否已存在 DLL
    3. 创建临时项目目录
    4. 写入 .cs 和 .csproj 文件
    5. 运行 dotnet build
    6. 返回 DLL 路径

    参数：
        cs_code: C# 类代码（完整类定义）
        func_name: 函数名称（用于命名 DLL）
        cache_dir: 缓存目录，默认使用全局缓存

    返回：
        DLL 文件路径

    异常：
        RuntimeError: 编译失败时抛出
    """
    if cache_dir is None:
        cache_dir = _CS_CACHE_DIR

    os.makedirs(cache_dir, exist_ok=True)

    # 计算哈希
    code_hash = hashlib.md5(cs_code.encode('utf-8')).hexdigest()[:12]
    dll_name = f'cs_{func_name}_{code_hash}'

    # 检查缓存
    dll_path = os.path.join(cache_dir, dll_name + '.dll')
    if os.path.exists(dll_path):
        return dll_path

    # 创建项目目录
    project_dir = os.path.join(cache_dir, dll_name)
    os.makedirs(project_dir, exist_ok=True)

    # 写入文件
    cs_file = os.path.join(project_dir, 'Bridge.cs')
    csproj_file = os.path.join(project_dir, 'Bridge.csproj')

    with open(cs_file, 'w', encoding='utf-8') as f:
        f.write(cs_code)

    with open(csproj_file, 'w', encoding='utf-8') as f:
        f.write(generate_csproj())

    # 编译
    result = subprocess.run(
        ['dotnet', 'build', '-c', 'Release', '-o', cache_dir],
        cwd=project_dir,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(f'C# 编译失败:\n{result.stderr}\n{result.stdout}')

    # 验证 DLL 是否生成
    if not os.path.exists(dll_path):
        # 可能 DLL 名称不同，查找生成的 DLL
        for file in os.listdir(cache_dir):
            if file.endswith('.dll') and file.startswith('cs_'):
                dll_path = os.path.join(cache_dir, file)
                break
        else:
            raise RuntimeError(f'DLL 未生成: {dll_path}')

    return dll_path


def _call_csharp_func(dll_path, func_name, args, ret_type=None):
    """
    调用 C# DLL 中的函数

    参数：
        dll_path: DLL 文件路径
        func_name: 函数名称
        args: 参数列表
        ret_type: Python 返回类型注解

    返回：
        函数返回值
    """
    lib = ctypes.CDLL(dll_path)

    # 推断类型
    cs_types, ctypes_types = infer_cs_argtypes(args)

    func = getattr(lib, func_name)
    func.argtypes = ctypes_types

    # 设置返回类型
    if ret_type is None or ret_type is type(None):
        func.restype = None
    else:
        cs_ret = get_cs_type(ret_type)
        func.restype = get_cs_ctype(cs_ret)

    # 转换参数（字符串需要特殊处理）
    converted_args = []
    for arg, cs_type in zip(args, cs_types):
        if cs_type == 'string' and isinstance(arg, str):
            # C# string 需要传递为字节串
            converted_args.append(arg.encode('utf-8'))
        else:
            converted_args.append(arg)

    result = func(*converted_args)

    # 处理返回值
    if func.restype == ctypes.c_char_p and isinstance(result, bytes):
        return result.decode('utf-8')

    return result


def csharp(func=None, mode='NORMAL', cache_dir=None, ret_type=None, auto_signature=True, async_mode=False):
    """
    C# 动态编译装饰器

    参数：
        func: 被装饰的函数
        mode: 运行模式
            - NORMAL: DLL 存在则用，不存在则编译
            - DEBUG: 强制重新编译
            - FORCE: 只编译不执行
            - ONLY_RUN: 只运行，DLL 不存在则报错
            - ONLY_CODE: 只生成代码不编译
        cache_dir: 缓存目录
        ret_type: 返回类型（可覆盖注解）
        auto_signature: 是否自动生成签名
        async_mode: 是否异步执行（默认 False）

    用法：
        @csharp
        def add(a: int, b: int) -> int:
            return "return a + b;"

        @csharp(mode='DEBUG')
        def greet(name: str) -> str:
            return "return $\"Hello, {name}!\";"

        @csharp(async_mode=True)
        async def compute(x: int) -> int:
            return "return x * x;"
    """
    def decorator(func):
        sig = inspect.signature(func)
        func_name = func.__name__

        def generate_full_cs_code(args_for_body=None):
            """
            生成完整的 C# 代码（包含签名和导出属性）

            参数：
                args_for_body: 可选的参数值列表，用于生成方法体
                            如果为 None，使用 None 参数调用 func
            """
            # 获取参数类型（从签名推断，不依赖实际参数）
            params = []
            for param_name, param in sig.parameters.items():
                py_type = param.annotation if param.annotation != param.empty else int
                cs_type = get_cs_type(py_type)
                params.append((param_name, cs_type))

            # 获取返回类型
            if ret_type is not None:
                py_ret = ret_type
            elif 'return' in func.__annotations__:
                py_ret = func.__annotations__['return']
            else:
                py_ret = int

            cs_ret = get_cs_type(py_ret)

            # 获取方法体
            # 对于 ONLY_CODE 模式或生成模板时，使用 None 参数
            # 对于实际执行时，使用实际参数
            if args_for_body is None:
                # 使用 None 参数调用 func 获取代码模板
                body = func(*[None] * len(sig.parameters))
            else:
                # 使用实际参数调用 func
                body = func(*args_for_body)

            # 生成方法代码
            method_code = generate_cs_method(func_name, params, cs_ret, body)

            # 生成类代码
            class_code = generate_cs_class([method_code])

            return class_code, cs_ret

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 确定缓存路径
            actual_cache_dir = cache_dir or _CS_CACHE_DIR

            dll_path = os.path.join(actual_cache_dir, f'cs_{func_name}.dll')

            mode_upper = mode.upper()

            # 处理 ONLY_CODE 模式 - 不使用实际参数，只生成模板
            if mode_upper == 'ONLY_CODE':
                cs_code, _ = generate_full_cs_code(None)
                return cs_code

            # 检查是否需要编译
            need_compile = (
                mode_upper in ('DEBUG', 'FORCE') or
                (mode_upper == 'NORMAL' and not os.path.exists(dll_path))
            )

            if need_compile:
                cs_code, cs_ret = generate_full_cs_code(args)

                try:
                    dll_path = _compile_csharp_code(cs_code, func_name, actual_cache_dir)
                except Exception as e:
                    raise RuntimeError(f'C# 编译失败: {e}')

                if mode_upper == 'FORCE':
                    return dll_path

            elif mode_upper == 'ONLY_RUN' and not os.path.exists(dll_path):
                raise FileNotFoundError(f'DLL 不存在: {dll_path}')

            # 调用函数
            py_ret = ret_type or func.__annotations__.get('return', int)
            return _call_csharp_func(dll_path, func_name, args, py_ret)

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            """异步执行包装器"""
            loop = asyncio.get_event_loop()

            def _run():
                # 确定缓存路径
                actual_cache_dir = cache_dir or _CS_CACHE_DIR

                dll_path = os.path.join(actual_cache_dir, f'cs_{func_name}.dll')

                mode_upper = mode.upper()

                # 处理 ONLY_CODE 模式 - 不使用实际参数
                if mode_upper == 'ONLY_CODE':
                    cs_code, _ = generate_full_cs_code(None)
                    return cs_code

                # 检查是否需要编译
                need_compile = (
                    mode_upper in ('DEBUG', 'FORCE') or
                    (mode_upper == 'NORMAL' and not os.path.exists(dll_path))
                )

                if need_compile:
                    cs_code, cs_ret = generate_full_cs_code(args)

                    try:
                        dll_path = _compile_csharp_code(cs_code, func_name, actual_cache_dir)
                    except Exception as e:
                        raise RuntimeError(f'C# 编译失败: {e}')

                    if mode_upper == 'FORCE':
                        return dll_path

                elif mode_upper == 'ONLY_RUN' and not os.path.exists(dll_path):
                    raise FileNotFoundError(f'DLL 不存在: {dll_path}')

                # 调用函数
                py_ret = ret_type or func.__annotations__.get('return', int)
                return _call_csharp_func(dll_path, func_name, args, py_ret)

            return await loop.run_in_executor(_executor, _run)

        # 根据 async_mode 返回不同的包装器
        if async_mode:
            return async_wrapper
        else:
            return wrapper

    if func is not None:
        return decorator(func)

    return decorator


def compile_and_run(cs_code, func_name='main', args=(), ret_type=int, cache_dir=None):
    """
    便捷函数：编译并运行 C# 代码

    参数：
        cs_code: C# 方法体代码
        func_name: 函数名称
        args: 参数列表
        ret_type: 返回类型
        cache_dir: 缓存目录

    返回：
        函数返回值
    """
    # 生成完整代码
    params = []
    for i, arg in enumerate(args):
        cs_type = get_cs_type(type(arg), arg)
        params.append((f'arg{i}', cs_type))

    cs_ret = get_cs_type(ret_type)
    method_code = generate_cs_method(func_name, params, cs_ret, cs_code)
    class_code = generate_cs_class([method_code])

    dll_path = _compile_csharp_code(class_code, func_name, cache_dir)
    return _call_csharp_func(dll_path, func_name, args, ret_type)


# ============================================================================
# CSharpBridge - C# 桥接实现（继承 LangBridge）
# ============================================================================

class CSharpBridge(LangBridge):
    """
    C# 语言桥接实现

    继承 LangBridge 抽象基类，实现 C# 特定的代码生成、编译和调用。
    """

    name = 'csharp'
    file_ext = '.cs'
    lib_ext = '.dll'

    def __init__(self):
        super().__init__()

    def compiler_available(self) -> bool:
        """编译器是否可用"""
        return csharp_compiler_available()

    def generate_code(self, spec: FunctionSpec) -> str:
        """
        生成 C# 代码

        包含：
        1. module_code（用户提供的模块级代码）
        2. 依赖函数（从 deps 参数生成）
        3. 主函数
        """
        methods = []

        # 依赖函数（按顺序生成）
        for dep in spec.dependencies:
            dep_method = self._generate_method(dep)
            if dep_method:
                methods.append(dep_method)

        # 主函数
        main_method = self._generate_method(spec)
        methods.append(main_method)

        # 生成类代码
        class_code = generate_cs_class(methods)

        # 如果有 module_code，暂时放在类前面（C# 中可以有额外的 using 或 namespace 代码）
        if spec.module_code:
            return spec.module_code + '\n' + class_code

        return class_code

    def _generate_method(self, spec: FunctionSpec) -> str:
        """生成单个方法的 C# 代码"""
        params = []

        for name, ann in spec.annotations.items():
            if name == 'return':
                continue
            if ann is None or ann is inspect.Parameter.empty:
                cs_type = 'int'
            else:
                cs_type = PY_TO_CS_TYPE.get(ann, 'int')
            params.append((name, cs_type))

        ret_type = 'int'
        if 'return' in spec.annotations:
            ann = spec.annotations['return']
            if ann is type(None) or str(ann).lower() == 'none':
                ret_type = 'void'
            else:
                ret_type = PY_TO_CS_TYPE.get(ann, 'int')

        return generate_cs_method(spec.name, params, ret_type, spec.body)

    def compile_code(self, code: str, func_name: str, cache_dir: str = None) -> str:
        """编译 C# 代码"""
        return _compile_csharp_code(code, func_name, cache_dir)

    def compile_project(self, project_dir: str, entry: str, output_dir: str = None) -> str:
        """
        编译 C# 项目

        使用 dotnet build 编译整个项目。
        entry='main' 时生成 exe，否则生成 dll。
        """
        output_dir = output_dir or _CS_CACHE_DIR
        os.makedirs(output_dir, exist_ok=True)

        # 检查是否有 .csproj 文件
        csproj_files = []
        for root, dirs, files in os.walk(project_dir):
            for f in files:
                if f.endswith('.csproj'):
                    csproj_files.append(os.path.join(root, f))

        if not csproj_files:
            raise RuntimeError(f'No .csproj file found in project directory: {project_dir}')

        csproj_file = csproj_files[0]
        project_dir = os.path.dirname(csproj_file)

        # 编译
        result = subprocess.run(
            ['dotnet', 'build', '-c', 'Release', '-o', output_dir],
            cwd=project_dir,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True
        )

        if result.returncode != 0:
            raise RuntimeError(
                f'C# project compilation failed:\n'
                f'stderr:\n{result.stderr}\n'
                f'stdout:\n{result.stdout}'
            )

        # 查找生成的产物
        project_name = os.path.splitext(os.path.basename(csproj_file))[0]

        if entry == 'main':
            if _IS_WINDOWS:
                output_path = os.path.join(output_dir, f'{project_name}.exe')
            else:
                output_path = os.path.join(output_dir, project_name)
        else:
            output_path = os.path.join(output_dir, f'{project_name}.dll')

        if not os.path.exists(output_path):
            # 尝试查找其他可能的输出
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
        """调用 C# 编译的函数

        Args:
            lib_path: DLL 文件路径。
            func_name: 函数名称。
            args: 参数元组。
            ret_type: Python 返回类型，用于类型转换。

        Returns:
            函数返回值。
        """
        return _call_csharp_func(lib_path, func_name, args, ret_type)


# 全局 CSharpBridge 实例
_csharp_bridge = CSharpBridge()

# 统一装饰器接口（使用 LangBridge 标准装饰器）
csharp = _csharp_bridge.decorator
cs = csharp