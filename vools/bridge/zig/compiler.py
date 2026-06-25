"""
vools.bridge.zig.compiler - Zig 语言桥接编译器实现

继承 LangBridge 抽象基类，实现 Zig 特定的代码生成、编译和调用。
支持异步模式和回退机制。
"""

import os
import sys
import platform
import subprocess
import tempfile
import textwrap
import ctypes
import asyncio
import shutil
from typing import Optional, Any, Dict, List

from .._base import LangBridge, FunctionSpec
from ...core.asyncio_compat import run as asyncio_run
from .types import PY_TO_ZIG_TYPE, ZIG_TO_CTYPES, get_zig_type, get_zig_ctype


def zig_compiler_available() -> bool:
    """检查 Zig 编译器是否可用"""
    try:
        result = subprocess.run(
            ['zig', 'version'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
            timeout=10
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def compile_and_run(code: str, args: tuple = (), ret_type: type = int) -> Any:
    """便捷函数：编译并运行 Zig 代码"""
    if not zig_compiler_available():
        raise RuntimeError("Zig compiler not available")

    bridge = _zig_bridge
    func_name = "main"
    spec = FunctionSpec(
        name=func_name,
        annotations={'return': ret_type},
        args=args,
        defaults={},
        body=code
    )
    zig_code = bridge.generate_code(spec)

    with tempfile.TemporaryDirectory() as tmpdir:
        src_path = os.path.join(tmpdir, f'{func_name}.zig')
        with open(src_path, 'w', encoding='utf-8') as f:
            f.write(zig_code)

        lib_path = bridge.compile_code(zig_code, func_name, tmpdir)
        return bridge.call_func(lib_path, func_name, args, ret_type)


class ZigFuture:
    """Zig 异步调用结果封装"""

    def __init__(self, executor, lib_path, func_name, args, ret_type):
        self._executor = executor
        self._lib_path = lib_path
        self._func_name = func_name
        self._args = args
        self._ret_type = ret_type
        self._loop = None
        self._future = None

    def _execute(self):
        bridge = _zig_bridge
        return bridge.call_func(self._lib_path, self._func_name, self._args, self._ret_type)

    async def _run_async(self):
        if self._loop is None:
            self._loop = asyncio.get_event_loop()
        return await self._loop.run_in_executor(self._executor, self._execute)

    def result(self, timeout: Optional[float] = None) -> Any:
        """同步获取结果"""
        if self._future is None:
            self._future = asyncio_run(self._run_async())
        return self._future

    async def async_result(self) -> Any:
        """异步获取结果"""
        return await self._run_async()


class ZigBridge(LangBridge):
    """Zig 语言桥接实现

    继承 LangBridge 抽象基类，实现 Zig 特定的代码生成、编译和调用。
    """

    name = 'zig'
    file_ext = '.zig'
    lib_ext = '.dll' if platform.system() == 'Windows' else '.so'

    def __init__(self):
        super().__init__()
        self._zig_executable = 'zig'
        self._executor: Optional[asyncio.AbstractEventLoop] = None

    def compiler_available(self) -> bool:
        """检查 Zig 编译器是否可用"""
        return zig_compiler_available()

    def generate_code(self, spec: FunctionSpec) -> str:
        """根据函数规格生成 Zig 代码

        包含:
        1. module_code（用户提供的模块级代码）
        2. 依赖函数（从 deps 参数生成）
        3. 主函数

        Args:
            spec: 函数规格

        Returns:
            str: 完整的 Zig 源文件代码
        """
        parts = []

        # 头部包含
        parts.append('const std = @import("std");')
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
        """生成单个函数的 Zig 代码"""
        import inspect as _inspect

        arg_names = []
        zig_arg_types = []
        arg_list = []

        for name, ann in spec.annotations.items():
            if name == 'return':
                continue
            arg_names.append(name)
            if ann is None or ann is _inspect.Parameter.empty:
                zig_arg_types.append('i64')
            else:
                zig_arg_types.append(get_zig_type(ann))

        for i, arg_name in enumerate(arg_names):
            zig_type = zig_arg_types[i] if i < len(zig_arg_types) else 'i64'
            arg_list.append(f'{arg_name}: {zig_type}')

        params_str = ', '.join(arg_list)

        ret_type = 'void'
        if 'return' in spec.annotations:
            ann = spec.annotations['return']
            if ann is not None and ann is not _inspect.Parameter.empty:
                ret_type = get_zig_type(ann)

        # 处理函数体，保留格式
        body = spec.body
        if body:
            body = textwrap.dedent(body).strip()

        # 构建导出函数
        export_name = f'vools_{spec.name}'

        if ret_type == 'void':
            return f'''export fn {export_name}({params_str}) void {{
{body}
}}'''
        else:
            return f'''export fn {export_name}({params_str}) {ret_type} {{
{body}
return {body.strip()};
}}'''

    def compile_code(self, code: str, func_name: str, cache_dir: Optional[str] = None) -> str:
        """编译 Zig 代码为动态库

        使用 zig build-lib 命令编译。

        Args:
            code: Zig 源代码字符串
            func_name: 函数名称，用于生成临时文件名
            cache_dir: 缓存目录，为 None 时使用系统临时目录

        Returns:
            str: 编译生成的动态库文件路径

        Raises:
            RuntimeError: 编译失败时抛出
        """
        if not self.compiler_available():
            raise RuntimeError("Zig compiler not available")

        cache_dir = cache_dir or tempfile.gettempdir()
        os.makedirs(cache_dir, exist_ok=True)

        # 创建临时目录存放源文件
        with tempfile.TemporaryDirectory(dir=cache_dir) as tmpdir:
            src_path = os.path.join(tmpdir, f'{func_name}.zig')
            with open(src_path, 'w', encoding='utf-8') as f:
                f.write(code)

            # 确定输出库路径
            if platform.system() == 'Windows':
                output_lib = os.path.join(tmpdir, f'{func_name}.dll')
            else:
                output_lib = os.path.join(tmpdir, f'lib{func_name}.so')

            # Zig 编译命令: zig build-lib -dynamic -femit-bin=output
            cmd = [
                self._zig_executable,
                'build-lib',
                '-dynamic',
                '-femit-bin=' + output_lib,
                src_path
            ]

            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True,
                cwd=tmpdir,
                timeout=120
            )

            if result.returncode != 0:
                error_msg = result.stderr or result.stdout
                raise RuntimeError(f'Zig compilation failed:\n{error_msg}')

            if not os.path.exists(output_lib):
                raise RuntimeError(f'Library not generated at {output_lib}')

            # 复制到缓存目录
            final_lib = os.path.join(cache_dir, os.path.basename(output_lib))
            shutil.copy2(output_lib, final_lib)

            return final_lib

    def compile_project(self, project_dir: str, entry: str, output_dir: Optional[str] = None) -> str:
        """编译整个 Zig 项目目录

        使用 zig build 命令编译项目。

        Args:
            project_dir: 项目根目录路径
            entry: 入口函数名，'main' 表示编译为可执行文件
            output_dir: 输出目录，为 None 时使用默认输出目录

        Returns:
            str: 编译产物路径（可执行文件或动态库）

        Raises:
            RuntimeError: 编译失败时抛出
        """
        if not os.path.isdir(project_dir):
            raise RuntimeError(f'Project directory not found: {project_dir}')

        if not self.compiler_available():
            raise RuntimeError("Zig compiler not available")

        output_dir = output_dir or self.default_cache_dir()
        os.makedirs(output_dir, exist_ok=True)

        project_name = os.path.basename(os.path.abspath(project_dir))

        # 确定编译目标
        if entry == 'main':
            cmd = [self._zig_executable, 'build']
        else:
            # 编译为库
            build_file = os.path.join(project_dir, 'build.zig')
            if not os.path.exists(build_file):
                raise RuntimeError(f'build.zig not found in project directory: {project_dir}')
            cmd = [self._zig_executable, 'build-lib', '-dynamic']

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
            cwd=project_dir,
            timeout=300
        )

        if result.returncode != 0:
            raise RuntimeError(
                f'Zig build failed:\n'
                f'stderr:\n{result.stderr}\n'
                f'stdout:\n{result.stdout}'
            )

        # 查找编译产物
        artifact_path = None
        if entry == 'main':
            if platform.system() == 'Windows':
                exe_name = f'{project_name}.exe'
            else:
                exe_name = project_name
            artifact_path = os.path.join(project_dir, 'zig-out', 'bin', exe_name)
            if not os.path.exists(artifact_path):
                artifact_path = os.path.join(project_dir, exe_name)
        else:
            if platform.system() == 'Windows':
                lib_name = f'{project_name}.dll'
            else:
                lib_name = f'lib{project_name}.so'
            artifact_path = os.path.join(project_dir, 'zig-out', 'lib', lib_name)
            if not os.path.exists(artifact_path):
                artifact_path = os.path.join(project_dir, lib_name)

        if not os.path.exists(artifact_path):
            raise RuntimeError(f'Build artifact not found in {project_dir}')

        # 复制到输出目录
        output_path = os.path.join(output_dir, os.path.basename(artifact_path))
        shutil.copy2(artifact_path, output_path)

        return output_path

    def call_func(self, lib_path: str, func_name: str,
                  args: tuple, ret_type: Optional[type] = None) -> Any:
        """调用编译后的动态库中的函数

        使用 ctypes 调用编译的 .so/.dll 文件。

        Args:
            lib_path: 动态库文件路径
            func_name: 要调用的函数名称（会自动添加 vools_ 前缀）
            args: 传递给函数的参数元组
            ret_type: 返回值类型，用于类型转换，为 None 时使用默认转换

        Returns:
            Any: 函数执行后的返回值
        """
        lib = ctypes.CDLL(lib_path)

        # Zig 导出的函数名有 vools_ 前缀
        export_name = f'vools_{func_name}'

        try:
            func = getattr(lib, export_name)
        except AttributeError:
            func = getattr(lib, func_name)

        # 设置参数类型
        ctypes_args = []
        for arg in args:
            if isinstance(arg, int):
                ctypes_args.append(ctypes.c_int64(arg))
            elif isinstance(arg, float):
                ctypes_args.append(ctypes.c_double(arg))
            elif isinstance(arg, str):
                ctypes_args.append(arg.encode('utf-8'))
            elif isinstance(arg, bool):
                ctypes_args.append(ctypes.c_bool(arg))
            else:
                ctypes_args.append(arg)

        func.argtypes = [type(a) for a in ctypes_args]

        # 设置返回值类型
        if ret_type is not None:
            zig_ret_type = get_zig_type(ret_type)
            ctype_ret = get_zig_ctype(zig_ret_type)
            func.restype = ctype_ret if ctype_ret is not None else ctypes.c_void_p
        else:
            func.restype = ctypes.c_int64

        result = func(*ctypes_args)

        # 处理字符串返回值
        if func.restype == ctypes.c_char_p and result:
            if isinstance(result, bytes):
                return result.decode('utf-8')

        return result

    def set_zig_executable(self, path: str):
        """设置 Zig 编译器路径"""
        self._zig_executable = path


# 全局 ZigBridge 实例
_zig_bridge = ZigBridge()

# 装饰器别名
zig = _zig_bridge.decorator
zigc = zig
