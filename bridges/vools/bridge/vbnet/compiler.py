"""
vools.bridge.vbnet.compiler - VB.NET 动态编译器

提供 @vbnet 装饰器，支持：
- 自动生成 VB.NET 代码和项目文件
- 调用 dotnet build 编译为控制台 EXE
- 通过反射调用函数并捕获 stdout 输出
- 基于 MD5 的代码缓存
- 异步执行支持

使用 manager 统一管理编译器配置。
"""

import os
import subprocess
import hashlib
import tempfile
import inspect
import platform
import asyncio
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Any, Optional

from ..manager import get_helper
from .._base import LangBridge, FunctionSpec
from ..core.types import LangType
from .types import get_vb_type, PY_TO_VB_TYPE
from .templates import generate_vb_method, generate_vb_class, generate_vbproj

_IS_WINDOWS = platform.system() == 'Windows'

_vbnet_helper = get_helper('vbnet')

_VBNET_CACHE_DIR = os.path.join(tempfile.gettempdir(), 'vools_vbnet_cache')

_executor = ThreadPoolExecutor(max_workers=4)


class VBNetFuture:
    """异步 VB.NET 函数调用的 Future 封装"""

    def __init__(self, future: Future, exe_path: str, func_name: str, ret_type):
        self._future = future
        self._exe_path = exe_path
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
    """编译 VB.NET 代码为控制台 EXE

    Args:
        vb_code: VB.NET 类代码（完整类定义，包含 Main 模块）
        func_name: 函数名称（用于命名缓存）
        cache_dir: 缓存目录，默认使用全局缓存

    Returns:
        EXE 文件路径

    Raises:
        RuntimeError: 编译失败时抛出
    """
    if cache_dir is None:
        cache_dir = _VBNET_CACHE_DIR

    os.makedirs(cache_dir, exist_ok=True)

    code_hash = hashlib.md5(vb_code.encode('utf-8')).hexdigest()[:12]
    exe_name = 'vb_{0}_{1}'.format(func_name, code_hash)

    project_dir = os.path.join(cache_dir, exe_name)
    # 清理旧的失败项目目录，避免 MSB1011 错误
    import shutil
    if os.path.exists(project_dir):
        shutil.rmtree(project_dir)
    os.makedirs(project_dir, exist_ok=True)

    vb_file = os.path.join(project_dir, 'Bridge.vb')
    vbproj_file = os.path.join(project_dir, 'Bridge.vbproj')

    with open(vb_file, 'w', encoding='utf-8') as f:
        f.write(vb_code)

    with open(vbproj_file, 'w', encoding='utf-8') as f:
        f.write(generate_vbproj())

    result = subprocess.run(
        ['dotnet', 'build', '-c', 'Release'],
        cwd=project_dir,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, errors='replace'
    )

    if result.returncode != 0:
        raise RuntimeError('VB.NET 编译失败:\n{0}\n{1}'.format(result.stderr, result.stdout))

    # dotnet build 默认输出到 bin/Release/net9.0/
    # 将所有输出文件复制到项目目录（EXE 需要 DLL 在同一目录）
    build_output = os.path.join(project_dir, 'bin', 'Release', 'net9.0')
    if os.path.isdir(build_output):
        for f in os.listdir(build_output):
            src = os.path.join(build_output, f)
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(project_dir, f))
    else:
        raise RuntimeError('构建输出目录未找到: {0}'.format(build_output))

    return os.path.join(project_dir, 'Bridge.exe')


def _call_vbnet_func(exe_path, func_name, args, ret_type=None):
    """通过运行控制台 EXE 调用 VB.NET 函数

    Args:
        exe_path: EXE 文件路径
        func_name: 函数名称
        args: 参数列表
        ret_type: Python 返回类型注解

    Returns:
        函数返回值
    """
    # 将所有参数转换为字符串
    str_args = [func_name]
    for arg in args:
        if isinstance(arg, bool):
            # VB.NET 的 Boolean.Parse 接受 "True"/"False"
            str_args.append(str(arg))
        else:
            str_args.append(str(arg))

    result = subprocess.run(
        [exe_path] + str_args,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, errors='replace'
    )

    if result.returncode != 0:
        raise RuntimeError(
            'VB.NET 函数调用失败 (exit code {0}):\n{1}'.format(
                result.returncode, result.stderr
            )
        )

    output = result.stdout.strip()

    # 根据返回类型转换结果
    if ret_type is None or ret_type is type(None):
        return None
    elif ret_type == bool:
        return output.lower() == 'true'
    elif ret_type == int:
        return int(output) if output else 0
    elif ret_type == float:
        return float(output) if output else 0.0
    elif ret_type == str:
        return output
    else:
        # 尝试转换为期望的类型
        try:
            return ret_type(output)
        except (ValueError, TypeError):
            return output


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
        params.append(('arg{0}'.format(i), vb_type))

    vb_ret = get_vb_type(ret_type)
    method_code = generate_vb_method(func_name, params, vb_ret, vb_code)
    class_code = generate_vb_class([method_code])

    exe_path = _compile_vbnet_code(class_code, func_name, cache_dir)
    return _call_vbnet_func(exe_path, func_name, args, ret_type)


class VBNetBridge(LangBridge):
    """VB.NET 语言桥接实现

    继承 LangBridge 抽象基类，实现 VB.NET 特定的代码生成、编译和调用。
    使用控制台 EXE + 反射方式调用函数，不依赖 DllExport。
    """

    name = 'vbnet'
    file_ext = '.vb'
    lib_ext = '.exe'
    lang_type = LangType.DOTNET

    def __init__(self):
        super().__init__()

    def compiler_available(self) -> bool:
        """编译器是否可用"""
        return vbnet_compiler_available()

    def save_to_cache(self, code: str, func_name: str,
                      lib_path: str, cache_dir: Optional[str] = None) -> str:
        """将编译产物保存到缓存目录。

        .NET EXE 依赖同目录下的 DLL 和配置文件，因此需要复制所有输出文件。

        Args:
            code: 源代码字符串。
            func_name: 函数名称。
            lib_path: 编译生成的 EXE 文件路径（project_dir/Bridge.exe）。
            cache_dir: 缓存目录，为 None 时使用默认目录。

        Returns:
            str: 缓存中的 EXE 文件路径。
        """
        import shutil
        cache_dir = self.get_cache_dir(cache_dir)
        cache_key = self.get_cache_key(code, func_name)
        cached_dir = os.path.join(cache_dir, cache_key)
        os.makedirs(cached_dir, exist_ok=True)

        # lib_path 是 project_dir/Bridge.exe，复制所有输出文件到缓存子目录
        src_dir = os.path.dirname(lib_path)
        for f in os.listdir(src_dir):
            src = os.path.join(src_dir, f)
            if os.path.isfile(src):
                try:
                    shutil.copy2(src, os.path.join(cached_dir, f))
                except Exception:
                    pass

        return os.path.join(cached_dir, 'Bridge.exe')

    def check_cache(self, code: str, func_name: str,
                    cache_dir: Optional[str] = None) -> Optional[str]:
        """检查编译缓存是否存在。

        Args:
            code: 源代码字符串。
            func_name: 函数名称。
            cache_dir: 缓存目录，为 None 时使用默认目录。

        Returns:
            Optional[str]: 缓存的 EXE 文件路径，不存在则返回 None。
        """
        cache_dir = self.get_cache_dir(cache_dir)
        cache_key = self.get_cache_key(code, func_name)
        cached_exe = os.path.join(cache_dir, cache_key, 'Bridge.exe')
        if os.path.exists(cached_exe):
            return cached_exe
        return None

    def generate_code(self, spec: FunctionSpec) -> str:
        """生成 VB.NET 代码

        包含：
        1. module_code（用户提供的模块级代码）
        2. 依赖函数（从 deps 参数生成）
        3. 主函数
        4. Main 反射调度模块
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
            raise RuntimeError('No .vbproj file found in project directory: {0}'.format(project_dir))

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
                'VB.NET project compilation failed:\n'
                'stderr:\n{0}\n'
                'stdout:\n{1}'.format(result.stderr, result.stdout)
            )

        project_name = os.path.splitext(os.path.basename(vbproj_file))[0]

        if entry == 'main':
            if _IS_WINDOWS:
                output_path = os.path.join(output_dir, '{0}.exe'.format(project_name))
            else:
                output_path = os.path.join(output_dir, project_name)
        else:
            output_path = os.path.join(output_dir, '{0}.dll'.format(project_name))

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
            lib_path: EXE 文件路径。
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