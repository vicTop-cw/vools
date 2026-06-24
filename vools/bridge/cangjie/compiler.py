"""
vools.bridge.cangjie.compiler - 仓颉动态编译装饰器

使用方式::

    @cangjie
    def fib(n: int) -> int:
        return '''
        if n <= 1 {
            return 1
        } else {
            return fib(n - 1) + fib(n - 2)
        }
        '''

    @cangjie
    def add(a: int, b: int) -> int:
        return 'return a + b'

    result = fib(10)
    result = add(10, 20)

参数:
    func: 被装饰的函数
    mode: 运行模式
        DEBUG: 强制重编译并执行
        FORCE: 强制重编译但不执行
        NORMAL: 命中缓存跳过编译;未命中则编译
        ONLY_RUN: 只在有缓存时执行;没有则报错
        ONLY_CODE: 只生成仓颉代码,不编译 DLL
    cache_dir: 编译缓存目录,None 则使用系统临时目录
    ret_type: 返回类型 ('int', 'float', 'string', 'bool'),None 时从注解推断
    auto_signature: 是否自动根据参数类型生成签名(默认 True)

设计目标:免序列化(serialization-free)交互
- 通过 ctypes 直接调用 C ABI 兼容的仓颉函数
"""

import os
import sys
import tempfile
import hashlib
import platform
import inspect
import functools
import ctypes
import shutil
import threading
import asyncio
import subprocess
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Any

from vools.bridge.manager import get_helper
from vools.bridge._base import LangBridge, FunctionSpec, FunctionParser
from .types import (
    get_cj_type,
    infer_cj_argtypes,
    resolve_cj_ret_type,
    CJ_TO_CTYPES,
    get_ctype_for,
)
from .templates import generate_cj_code
from .loader import load_cj_dll, setup_cj_func, convert_args, convert_result

# 平台判断
_IS_WINDOWS = platform.system() == 'Windows'
_IS_LINUX = platform.system() == 'Linux'

# 使用 manager 的编译器辅助
_cangjie_helper = get_helper('cangjie')

# 编译缓存目录
_CJ_CACHE_DIR = os.path.join(tempfile.gettempdir(), 'vools_cangjie_cache')

# 缓存:func_name -> (code, dll_path) 映射
_dll_cache = {}
_cache_lock = threading.Lock()

# 异步执行器
_executor = ThreadPoolExecutor(max_workers=4)


class CjFuture:
    """
    异步仓颉函数调用的 Future 封装

    支持:
    - 同步等待: future.result()
    - 迭代器协议: for x in future
    - async/await: await future
    """

    def __init__(self, future: Future, dll_path: str, func_name: str, ret_type: str):
        self._future = future
        self._dll_path = dll_path
        self._func_name = func_name
        self._ret_type = ret_type

    def result(self, timeout=None):
        """等待并返回结果"""
        return self._future.result(timeout)

    def __iter__(self):
        """支持同步迭代"""
        return self

    def __next__(self):
        """同步迭代获取结果"""
        if not self._future.done():
            self._future.result()  # 等待完成
        return self._future.result()

    def __await__(self):
        """支持 async/await"""
        return self._future.__await__()


def _get_cjc_path():
    """获取 cjc 编译器路径（使用 manager）"""
    return _cangjie_helper.get_compiler_path() or 'cjc'


def cjc_compiler_available():
    """
    检查仓颉编译器 (cjc) 是否可用

    使用 manager 统一管理。

    返回:
        bool: 如果 cjc 编译器可用返回 True,否则返回 False
    """
    return _cangjie_helper.is_available()


def _compile_cj_code(code: str, func_name: str, cache_dir: str = None) -> str:
    """
    编译仓颉代码并返回 DLL 路径

    参数:
        code: 完整仓颉源代码
        func_name: 函数名(用于生成文件名)
        cache_dir: 缓存目录,None 则使用 _CJ_CACHE_DIR

    返回:
        编译后的 DLL 路径

    抛出:
        RuntimeError: 编译失败
    """
    if cache_dir is None:
        cache_dir = _CJ_CACHE_DIR

    os.makedirs(cache_dir, exist_ok=True)

    # 生成唯一文件名(基于代码 MD5)
    code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
    dll_name = f'cj_{func_name}_{code_hash}'

    if _IS_WINDOWS:
        dll_path = os.path.join(cache_dir, f'{dll_name}.dll')
    else:
        dll_path = os.path.join(cache_dir, f'lib{dll_name}.so')

    # 检查缓存
    if os.path.exists(dll_path):
        return dll_path

    # 写入临时 .cj 文件
    cj_path = os.path.join(cache_dir, f'{dll_name}.cj')
    with open(cj_path, 'w', encoding='utf-8') as f:
        f.write(code)

    # 编译命令(使用 --output-type=dylib)
    cjc_path = _get_cjc_path()
    compile_cmd = [cjc_path, '--output-type=dylib', cj_path]

    result = subprocess.run(
        compile_cmd,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True,
        cwd=cache_dir
    )

    if result.returncode != 0:
        raise RuntimeError(
            f'仓颉编译失败:\nstderr:\n{result.stderr}\nstdout:\n{result.stdout}\n代码:\n{code}'
        )

    # 仓颉编译器生成的 DLL 名称可能不同,需要查找
    # Windows: {dll_name}.dll
    # Linux: lib{dll_name}.so
    if _IS_WINDOWS:
        expected_dll = os.path.join(cache_dir, f'{dll_name}.dll')
    else:
        expected_dll = os.path.join(cache_dir, f'lib{dll_name}.so')

    # 如果预期路径不存在,查找实际生成的 DLL
    if not os.path.exists(expected_dll):
        # 查找缓存目录中的 DLL 文件
        dll_files = [f for f in os.listdir(cache_dir) if f.endswith('.dll') or f.endswith('.so')]
        if dll_files:
            # 使用最新的 DLL 文件
            dll_path = os.path.join(cache_dir, dll_files[0])
        else:
            raise FileNotFoundError(f'编译后未找到 DLL 文件: {cache_dir}')
    else:
        dll_path = expected_dll

    return dll_path


def _get_cached_dll(func_name: str, code: str) -> str:
    """获取缓存的 DLL 路径,必要时重新编译"""
    with _cache_lock:
        cached = _dll_cache.get(func_name)
        if cached and cached[0] == code and os.path.exists(cached[1]):
            return cached[1]
        # 编译
        dll_path = _compile_cj_code(code, func_name)
        _dll_cache[func_name] = (code, dll_path)
        return dll_path


def _remove_cached_dll(func_name: str):
    """移除缓存的 DLL(用于强制重编译)"""
    with _cache_lock:
        cached = _dll_cache.pop(func_name, None)
        if cached:
            dll_path = cached[1]
            try:
                if os.path.exists(dll_path):
                    os.remove(dll_path)
            except OSError:
                pass


def _call_cj_func(dll_path: str, func_name: str, args: tuple, ret_type: str = 'Int64'):
    """
    调用仓颉编译的函数

    参数:
        dll_path: DLL 路径
        func_name: 函数名
        args: 参数元组
        ret_type: 返回类型(仓颉类型字符串)

    返回:
        函数返回值
    """
    lib = load_cj_dll(dll_path)

    # 推断仓颉入参类型
    cj_argtypes = infer_cj_argtypes(args)

    # 获取 ctypes 类型
    c_argtypes = [get_ctype_for(cj_t) for cj_t in cj_argtypes]
    c_restype = get_ctype_for(ret_type)

    # 设置函数签名
    func = setup_cj_func(lib, func_name, c_argtypes, c_restype)

    # 转换参数
    converted_args = convert_args(args, c_argtypes)

    # 调用
    result = func(*converted_args)

    # 解码返回值
    return convert_result(result, ret_type)





def compile_and_run(cj_code: str, func_name: str = 'main',
                    args: tuple = (), ret_type: str = 'Int64',
                    cache_dir: str = None):
    """
    直接编译并运行仓颉代码

    参数:
        cj_code: 仓颉函数体代码(不含签名)
        func_name: 函数名(默认 'main')
        args: 参数元组
        ret_type: 返回类型
        cache_dir: 编译缓存目录

    返回:
        函数返回值
    """
    full_code = generate_cj_code(
        func_name,
        [],
        infer_cj_argtypes(args),
        ret_type,
        cj_code,
    )
    dll_path = _compile_cj_code(full_code, func_name, cache_dir)
    return _call_cj_func(dll_path, func_name, args, ret_type)


async def compile_and_run_async(cj_code: str, func_name: str = 'main',
                                 args: tuple = (), ret_type: str = 'Int64',
                                 cache_dir: str = None):
    """
    异步编译并运行仓颉代码

    参数:
        cj_code: 仓颉函数体代码(不含签名)
        func_name: 函数名(默认 'main')
        args: 参数元组
        ret_type: 返回类型
        cache_dir: 编译缓存目录

    返回:
        函数返回值
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _executor,
        lambda: compile_and_run(cj_code, func_name, args, ret_type, cache_dir)
    )


async def batch_compile_and_run_async(funcs):
    """
    批量异步编译并运行多个仓颉函数

    参数:
        funcs: 可迭代对象,每个元素为 (cj_code, func_name, args, ret_type)

    返回:
        结果列表
    """
    tasks = [
        compile_and_run_async(cj_code, func_name, args, ret_type)
        for cj_code, func_name, args, ret_type in funcs
    ]
    return await asyncio.gather(*tasks)


# ============================================================================
# CjBridge - 仓颉桥接实现（继承 LangBridge）
# ============================================================================

class CjBridge(LangBridge):
    """
    仓颉语言桥接实现

    继承 LangBridge 抽象基类，实现仓颉特定的代码生成、编译和调用。
    """

    name = 'cangjie'
    file_ext = '.cj'
    lib_ext = '.dll' if _IS_WINDOWS else '.so'

    def __init__(self):
        super().__init__()

    def compiler_available(self) -> bool:
        """编译器是否可用"""
        return cjc_compiler_available()

    def generate_code(self, spec: FunctionSpec) -> str:
        """
        生成仓颉代码

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
        """生成单个函数的仓颉代码"""
        arg_names = []
        cj_argtypes = []

        for name, ann in spec.annotations.items():
            if name == 'return':
                continue
            arg_names.append(name)
            if ann is None or ann is inspect.Parameter.empty:
                cj_argtypes.append('Int64')
            else:
                cj_argtypes.append(get_cj_type(ann))

        ret_type = 'Int64'
        if 'return' in spec.annotations:
            ann = spec.annotations['return']
            if ann is type(None) or str(ann).lower() == 'none':
                ret_type = 'Unit'
            else:
                ret_type = get_cj_type(ann)

        params = []
        for i, cj_t in enumerate(cj_argtypes):
            name = arg_names[i] if i < len(arg_names) else f'arg{i}'
            params.append(f'{name}: {cj_t}')

        params_str = ', '.join(params)

        indented_body = ''
        for line in spec.body.split('\n'):
            if line.strip():
                indented_body += '    ' + line + '\n'
            else:
                indented_body += '\n'

        if ret_type == 'Unit':
            return f'''func {spec.name}({params_str}) {{
{indented_body}}}'''
        else:
            return f'''func {spec.name}({params_str}): {ret_type} {{
{indented_body}}}'''

    def compile_code(self, code: str, func_name: str, cache_dir: str = None) -> str:
        """编译仓颉代码"""
        return _compile_cj_code(code, func_name, cache_dir)

    def compile_project(self, project_dir: str, entry: str, output_dir: str = None) -> str:
        """
        编译仓颉项目

        扫描 project_dir 下所有 .cj 文件，调用 cjc 编译器编译。
        entry='main' 时生成可执行文件，否则生成共享库。
        """
        output_dir = output_dir or _CJ_CACHE_DIR
        os.makedirs(output_dir, exist_ok=True)

        cj_files = []
        for root, dirs, files in os.walk(project_dir):
            for f in files:
                if f.endswith('.cj'):
                    cj_files.append(os.path.join(root, f))

        if not cj_files:
            raise RuntimeError(f'No .cj files found in project directory: {project_dir}')

        cj_files.sort()

        project_name = os.path.basename(os.path.abspath(project_dir))
        cjc_path = _get_cjc_path()

        if entry == 'main':
            if _IS_WINDOWS:
                output_path = os.path.join(output_dir, f'{project_name}.exe')
            else:
                output_path = os.path.join(output_dir, project_name)
            compile_cmd = [cjc_path, '--output-type=exe', '-o', output_path] + cj_files
        else:
            if _IS_WINDOWS:
                output_path = os.path.join(output_dir, f'{project_name}.dll')
            else:
                output_path = os.path.join(output_dir, f'lib{project_name}.so')
            compile_cmd = [cjc_path, '--output-type=dylib', '-o', output_path] + cj_files

        result = subprocess.run(
            compile_cmd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
            cwd=output_dir
        )

        if result.returncode != 0:
            raise RuntimeError(
                f'仓颉项目编译失败:\n'
                f'stderr:\n{result.stderr}\n'
                f'stdout:\n{result.stdout}\n'
                f'files: {cj_files}'
            )

        if not os.path.exists(output_path):
            dll_files = [
                f for f in os.listdir(output_dir)
                if f.endswith('.dll') or f.endswith('.so') or f.endswith('.exe')
            ]
            if dll_files:
                output_path = os.path.join(output_dir, dll_files[0])
            else:
                raise FileNotFoundError(f'编译后未找到产物文件: {output_dir}')

        return output_path

    def call_func(self, lib_path: str, func_name: str,
                  args: tuple, ret_type=None) -> Any:
        """调用仓颉编译的函数"""
        cj_ret_type = ret_type or 'Int64'
        return _call_cj_func(lib_path, func_name, args, cj_ret_type)


# 全局 CjBridge 实例
_cj_bridge = CjBridge()

# 装饰器：直接使用基类的 decorator 方法
cangjie = _cj_bridge.decorator
