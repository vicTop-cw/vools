'''
vools.bridge.freebasic.compiler - FreeBASIC 动态编译装饰器

使用方式::

    @fbc
    def fib(n: int) -> int:
        return \"\"\"
        If n <= 1 Then
            Return 1
        Else
            Return fib(n-1) + fib(n-2)
        End If
        \"\"\"

    @fbc
    def sum_arr(arr: list) -> int:
        return \'\'
        Dim total As Long = 0
        For i As Long = 0 To n - 1
            total += arr[i]
        Next i
        Return total
        \'\'

    result = fib(10)
    result = sum_arr([1, 2, 3, 4, 5])

参数：
    func: 被装饰的函数
    mode: 运行模式
        DEBUG: 强制重编译并执行
        FORCE: 强制重编译但不执行
        NORMAL: 命中缓存跳过编译；未命中则编译
        ONLY_RUN: 只在有缓存时执行；没有则报错
        ONLY_CODE: 只生成 FreeBASIC 代码，不编译 DLL
    cache_dir: 编译缓存目录，None 则使用系统临时目录
    ret_type: 返回类型 ('int', 'float', 'string', 'bool')，None 时从注解推断
    async_mode: 是否异步执行（默认 False）
    auto_signature: 是否自动根据参数类型生成签名（默认 True）

设计目标：免序列化（serialization-free）交互
- list 参数走 POINTER + 长度，不走 CSV/JSON
- 通过 transport 模块可注入 zero-copy 实现（zinc）
'''
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
from typing import Any, List, Callable, Optional

from ..manager import get_helper
from .._base import LangBridge, FunctionSpec, FunctionParser
from ..core.types import LangType
from .types import (
    PY_TO_FB_TYPE,
    get_fb_type,
    infer_fb_argtypes,
    is_array_type,
    FB_TO_CTYPES,
)
from .transport import get_transport, Transport

# 平台判断
_IS_WINDOWS = platform.system() == 'Windows'

# 使用 manager 的编译器辅助
_freebasic_helper = get_helper('freebasic')


def _setup_fbc_env():
    """设置 FreeBASIC 编译环境（使用 manager）"""
    _freebasic_helper.setup_env()


_setup_fbc_env()


def _get_fbc_path():
    """获取 fbc64 编译器路径（使用 manager）"""
    return _freebasic_helper.get_compiler_path() or 'fbc64'


def fbc_compiler_available():
    """
    检查 FreeBASIC 编译器 (fbc64) 是否可用

    使用 manager 统一管理。

    返回：
        bool: 如果 fbc64 编译器可用返回 True，否则返回 False
    """
    return _freebasic_helper.is_available()


# 编译缓存目录
_BAS_CACHE_DIR = os.path.join(tempfile.gettempdir(), 'vools_fbc_cache')


# ============================================================================
# FbcBridge - FreeBASIC 桥接实现（继承 LangBridge）
# ============================================================================

class FbcBridge(LangBridge):
    """
    FreeBASIC 语言桥接实现

    继承 LangBridge 抽象基类，实现 FreeBASIC 特定的代码生成、编译和调用。

    注意：FreeBASIC 不支持函数嵌套，依赖函数通过 deps 参数声明，
    自动提升为模块级函数。
    """

    name = 'freebasic'
    file_ext = '.bas'
    lib_ext = '.dll' if os.name == 'nt' else '.so'
    lang_type = LangType.COMPILED

    def __init__(self):
        super().__init__()
        _setup_fbc_env()

    def supports_nested_functions(self) -> bool:
        """FreeBASIC 不支持函数嵌套"""
        return False

    def compiler_available(self) -> bool:
        """编译器是否可用"""
        return fbc_compiler_available()

    def generate_code(self, spec: FunctionSpec) -> str:
        """
        生成 FreeBASIC 代码

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
        """生成单个函数的 FreeBASIC 代码"""
        arg_names = []
        fb_argtypes = []

        for name, ann in spec.annotations.items():
            if name == 'return':
                continue
            arg_names.append(name)
            if ann is None or ann is inspect.Parameter.empty:
                fb_argtypes.append('Long')
            else:
                fb_argtypes.append(get_fb_type(ann))

        ret_type = 'Long'
        if 'return' in spec.annotations:
            ret_type = get_fb_type(spec.annotations['return'])

        params = []
        n_params = []

        for i, fb_t in enumerate(fb_argtypes):
            name = arg_names[i] if i < len(arg_names) else f'arg{i}'
            if is_array_type(fb_t):
                params.append(f'ByVal {name} As {fb_t}')
                n_params.append('ByVal n As Long')
            else:
                params.append(f'ByVal {name} As {fb_t}')

        params_str = ', '.join(params + n_params) if n_params else ', '.join(params)

        indented_body = ''
        for line in spec.body.split('\n'):
            if line.strip():
                indented_body += '    ' + line + '\n'
            else:
                indented_body += '\n'

        if ret_type == 'Void':
            return f'''Function {spec.name} cdecl Alias "{spec.name}"({params_str}) Export
{indented_body}End Function'''
        else:
            return f'''Function {spec.name} cdecl Alias "{spec.name}"({params_str}) As {ret_type} Export
{indented_body}End Function'''

    def compile_code(self, code: str, func_name: str, cache_dir: str = None) -> str:
        """编译 FreeBASIC 代码"""
        cache_dir = self.get_cache_dir(cache_dir)
        os.makedirs(cache_dir, exist_ok=True)

        # 使用哈希命名避免 DLL 文件锁定问题
        cache_key = self.get_cache_key(code, func_name)
        if _IS_WINDOWS:
            dll_path = os.path.join(cache_dir, f'{cache_key}.dll')
        else:
            dll_path = os.path.join(cache_dir, f'lib{cache_key}.so')

        # 如果已编译则直接返回
        if os.path.exists(dll_path):
            return dll_path

        bas_path = os.path.join(cache_dir, f'{cache_key}.bas')
        with open(bas_path, 'w', encoding='utf-8') as f:
            f.write(code)

        fbc_path = _get_fbc_path()
        if _IS_WINDOWS:
            compile_cmd = [fbc_path, '-s', 'gui', '-dll', '-export', bas_path]
        else:
            compile_cmd = [fbc_path, '-dll', '-export', bas_path]

        import subprocess
        result = subprocess.run(
            compile_cmd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
            cwd=cache_dir
        )

        if result.returncode != 0:
            raise RuntimeError(
                f'FreeBASIC 编译失败:\nstderr:\n{result.stderr}\nstdout:\n{result.stdout}\n代码:\n{code}'
            )

        return dll_path

    def compile_project(self, project_dir: str, entry: str, output_dir: str = None) -> str:
        """
        编译 FreeBASIC 项目

        扫描 project_dir 下所有 .bas 文件，调用 fbc 编译器编译。
        entry='main' 时生成 exe，否则生成 dll。
        """
        import subprocess
        import glob

        output_dir = output_dir or _BAS_CACHE_DIR
        os.makedirs(output_dir, exist_ok=True)

        bas_files = []
        for root, dirs, files in os.walk(project_dir):
            for f in files:
                if f.endswith('.bas'):
                    bas_files.append(os.path.join(root, f))

        if not bas_files:
            raise RuntimeError(f'No .bas files found in project directory: {project_dir}')

        bas_files.sort()

        project_name = os.path.basename(os.path.abspath(project_dir))

        fbc_path = _get_fbc_path()
        compile_cmd = [fbc_path]

        if _IS_WINDOWS:
            compile_cmd.extend(['-s', 'gui'])

        if entry == 'main':
            compile_cmd.append('-exe')
            if _IS_WINDOWS:
                output_path = os.path.join(output_dir, f'{project_name}.exe')
            else:
                output_path = os.path.join(output_dir, project_name)
        else:
            compile_cmd.extend(['-dll', '-export'])
            if _IS_WINDOWS:
                output_path = os.path.join(output_dir, f'{project_name}.dll')
            else:
                output_path = os.path.join(output_dir, f'lib{project_name}.so')

        compile_cmd.extend(['-x', output_path])
        compile_cmd.extend(bas_files)

        result = subprocess.run(
            compile_cmd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
            cwd=output_dir
        )

        if result.returncode != 0:
            raise RuntimeError(
                f'FreeBASIC project compilation failed:\n'
                f'stderr:\n{result.stderr}\n'
                f'stdout:\n{result.stdout}\n'
                f'files: {bas_files}'
            )

        return output_path

    def call_func(self, lib_path: str, func_name: str,
                  args: tuple, ret_type=None) -> Any:
        """调用 FreeBASIC 编译的函数"""
        transport = get_transport()
        lib = ctypes.CDLL(lib_path)
        func = getattr(lib, func_name)

        fb_argtypes = infer_fb_argtypes(args)

        c_args = []
        c_argtypes = []
        for arg, fb_t in zip(args, fb_argtypes):
            if is_array_type(fb_t):
                val, ctype = transport.prepare_arg(arg, fb_t)
                c_args.append(val)
                c_argtypes.append(ctype)
                c_args.append(ctypes.c_long(len(arg) if arg else 0))
                c_argtypes.append(ctypes.c_long)
            else:
                val, ctype = transport.prepare_arg(arg, fb_t)
                c_args.append(val)
                c_argtypes.append(ctype)

        func.argtypes = c_argtypes
        
        if ret_type is None:
            fb_ret_type = 'Long'
        else:
            fb_ret_type = get_fb_type(ret_type)
        
        func.restype = transport.prepare_ret(fb_ret_type)

        result = func(*c_args)
        return transport.decode_result(result, fb_ret_type)


# 全局 FbcBridge 实例
_fbc_bridge = FbcBridge()

# 装饰器：直接使用基类的 decorator 方法
fbc = _fbc_bridge.decorator


def _compile_fbc_code(code: str, func_name: str, cache_dir: str = None,
                      extra_includes: list = None,
                      inc_paths: list = None,
                      lib_paths: list = None) -> str:
    """
    编译 FreeBASIC 代码并返回 DLL 路径

    参数：
        code: 完整 FreeBASIC 源代码
        func_name: 函数名（用于生成文件名）
        cache_dir: 缓存目录，None 则使用 _BAS_CACHE_DIR
        extra_includes: 额外的源码片段（字符串列表，会在主代码前注入，可包含 #include 指令）
        inc_paths: 额外的头文件搜索路径（通过 -i 参数传给 fbc）
        lib_paths: 额外的库搜索路径（通过 -p 参数传给 fbc，让链接器能找到 .dll/.a）

    返回：
        编译后的 DLL 路径

    抛出：
        RuntimeError: 编译失败
    """
    if cache_dir is None:
        cache_dir = _BAS_CACHE_DIR

    os.makedirs(cache_dir, exist_ok=True)

    # 生成唯一文件名（基于代码 MD5 + 额外 include）
    full_source = '\n'.join(extra_includes or []) + '\n' + code
    code_hash = hashlib.md5(full_source.encode('utf-8')).hexdigest()[:12]
    dll_name = f'fbc_{func_name}_{code_hash}'

    if _IS_WINDOWS:
        dll_path = os.path.join(cache_dir, f'{dll_name}.dll')
    else:
        dll_path = os.path.join(cache_dir, f'{dll_name}.so')

    # 检查缓存
    if os.path.exists(dll_path):
        return dll_path

    # 写入临时 .bas 文件
    bas_path = os.path.join(cache_dir, f'{dll_name}.bas')
    with open(bas_path, 'w', encoding='utf-8') as f:
        f.write(full_source)

    # 编译命令（不切换工作目录，用 cwd 参数）
    fbc_path = _get_fbc_path()
    if _IS_WINDOWS:
        compile_cmd = [fbc_path, '-s', 'gui', '-dll', '-export']
    else:
        compile_cmd = [fbc_path, '-dll', '-export']

    # 添加头文件搜索路径
    for inc in (inc_paths or []):
        compile_cmd.extend(['-i', inc])

    # 添加库搜索路径（让链接器能找到 .dll/.a）
    for lp in (lib_paths or []):
        compile_cmd.extend(['-p', lp])

    compile_cmd.append(bas_path)

    import subprocess
    result = subprocess.run(
        compile_cmd,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True,
        cwd=cache_dir
    )

    if result.returncode != 0:
        raise RuntimeError(
            f'FreeBASIC 编译失败:\nstderr:\n{result.stderr}\nstdout:\n{result.stdout}\n代码:\n{code}'
        )

    # 清理临时 .bas 文件（可选，保留有助于调试）
    # try:
    #     os.remove(bas_path)
    # except OSError:
    #     pass

    return dll_path


def _load_fbc_dll(dll_path: str, lib_paths: list = None):
    """加载 FreeBASIC 编译的 DLL"""
    if not os.path.exists(dll_path):
        raise FileNotFoundError(f'FreeBASIC 共享库不存在: {dll_path}')

    # 在 Windows 上，把依赖库所在目录加入搜索路径（Python 3.8+）
    if _IS_WINDOWS and lib_paths:
        for lp in lib_paths:
            lp_abs = os.path.abspath(lp)
            if os.path.isdir(lp_abs):
                try:
                    os.add_dll_directory(lp_abs)
                except (AttributeError, OSError):
                    pass
        # 加上 DLL 自身的目录
        dll_dir = os.path.dirname(os.path.abspath(dll_path))
        try:
            os.add_dll_directory(dll_dir)
        except (AttributeError, OSError):
            pass

    return ctypes.CDLL(dll_path)


def _call_fbc_func(dll_path: str, func_name: str, args: tuple, ret_type: str = 'Long',
                   lib_paths: list = None):
    """
    调用 FreeBASIC 编译的函数（免序列化）

    参数：
        dll_path: DLL 路径
        func_name: 函数名
        args: 参数元组
        ret_type: 返回类型（FB 类型字符串）
        lib_paths: DLL 搜索路径（用于解决依赖）

    返回：
        函数返回值（已通过 transport.decode_result 解码）
    """
    transport = get_transport()
    lib = _load_fbc_dll(dll_path, lib_paths=lib_paths)
    func = getattr(lib, func_name)

    # 推断 FB 入参类型
    fb_argtypes = infer_fb_argtypes(args)

    # 通过 transport 准备入参
    c_args = []
    c_argtypes = []
    for arg, fb_t in zip(args, fb_argtypes):
        if is_array_type(fb_t):
            # 数组：拆为 (ptr, length) 两个参数
            val, ctype = transport.prepare_arg(arg, fb_t)
            c_args.append(val)
            c_argtypes.append(ctype)
            c_args.append(ctypes.c_long(len(arg) if arg else 0))
            c_argtypes.append(ctypes.c_long)
        else:
            val, ctype = transport.prepare_arg(arg, fb_t)
            c_args.append(val)
            c_argtypes.append(ctype)

    # 设置签名
    func.argtypes = c_argtypes
    func.restype = transport.prepare_ret(ret_type)

    # 调用
    result = func(*c_args)

    # 解码返回值
    return transport.decode_result(result, ret_type)


# 类型映射 - 内部使用
PY_TO_FB = dict(PY_TO_FB_TYPE)

# 兼容别名
_FB_TYPE_ALIASES = {
    'int': 'Long',
    'float': 'Double',
    'bool': 'Boolean',
    'string': 'ZString Ptr',
    'void': 'Void',
}


def _resolve_fb_ret_type(annotation):
    """从函数返回类型注解解析 FB 类型"""
    if annotation is None or annotation is type(None):
        return 'Void'
    if isinstance(annotation, type):
        return PY_TO_FB.get(annotation, 'Long')
    if isinstance(annotation, str):
        return _FB_TYPE_ALIASES.get(annotation.lower().split('.')[-1], 'Long')
    return 'Long'


def _generate_fbc_wrapper(
    func_name: str,
    py_argtypes: list,
    fbc_body: str,
    ret_type: str = 'Long',
    arg_names: list = None,
):
    """
    生成完整的 FreeBASIC 代码

    参数：
        func_name: 函数名
        py_argtypes: 与参数位置对应的 FB 类型字符串列表（含数组 ptr 项）
        fbc_body: 函数体代码
        ret_type: 返回类型
        arg_names: 参数名列表

    返回：
        完整的 FreeBASIC 代码字符串
    """
    # 数组入参会在签名中展开为 (ptr, n) 两个参数
    params = []
    n_params = []

    for i, fb_t in enumerate(py_argtypes):
        name = (arg_names[i] if arg_names and i < len(arg_names) else f'arg{i}')
        if is_array_type(fb_t):
            params.append(f'ByVal {name} As {fb_t}')  # 使用实际类型（Long Ptr / Double Ptr）
            n_params.append('ByVal n As Long')
        else:
            params.append(f'ByVal {name} As {fb_t}')

    params_str = ', '.join(params + n_params) if n_params else ', '.join(params)

    # 处理函数体缩进
    indented_body = ''
    for line in fbc_body.split('\n'):
        if line.strip():
            indented_body += '    ' + line + '\n'
        else:
            indented_body += '\n'

    if ret_type == 'Void':
        code = f'''Function {func_name} cdecl Alias "{func_name}"({params_str}) Export
{indented_body}End Function
'''
    else:
        code = f'''Function {func_name} cdecl Alias "{func_name}"({params_str}) As {ret_type} Export
{indented_body}End Function
'''
    return code


# 异步执行器
_executor = ThreadPoolExecutor(max_workers=4)


class FbcFuture:
    """异步 FreeBASIC 函数调用的 Future 封装"""

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


# 缓存：func_name -> (code, dll_path) 映射
_dll_cache = {}
_cache_lock = threading.Lock()


def _get_cached_dll(func_name: str, code: str) -> str:
    """获取缓存的 DLL 路径，必要时重新编译"""
    with _cache_lock:
        cached = _dll_cache.get(func_name)
        if cached and cached[0] == code and os.path.exists(cached[1]):
            return cached[1]
        # 编译
        dll_path = _compile_fbc_code(code, func_name)
        _dll_cache[func_name] = (code, dll_path)
        return dll_path


def _remove_cached_dll(func_name: str):
    """移除缓存的 DLL（用于强制重编译）"""
    with _cache_lock:
        cached = _dll_cache.pop(func_name, None)
        if cached:
            dll_path = cached[1]
            try:
                if os.path.exists(dll_path):
                    os.remove(dll_path)
            except OSError:
                pass





def compile_and_run(fbc_code: str, func_name: str = 'main',
                    args: tuple = (), ret_type: str = 'Long',
                    cache_dir: str = None,
                    extra_includes: list = None,
                    inc_paths: list = None,
                    lib_paths: list = None):
    """
    直接编译并运行 FreeBASIC 代码

    参数：
        fbc_code: FreeBASIC 函数体代码（不含签名）
        func_name: 函数名（默认 'main'）
        args: 参数元组
        ret_type: 返回类型
        cache_dir: 编译缓存目录
        extra_includes: 额外的源码片段（字符串列表，会在主代码前注入）
        inc_paths: 额外的头文件搜索路径
        lib_paths: 额外的库搜索路径

    返回：
        函数返回值
    """
    full_code = _generate_fbc_wrapper(
        func_name,
        infer_fb_argtypes(args),
        fbc_code,
        ret_type,
    )
    dll_path = _compile_fbc_code(full_code, func_name, cache_dir,
                                 extra_includes=extra_includes,
                                 inc_paths=inc_paths,
                                 lib_paths=lib_paths)
    return _call_fbc_func(dll_path, func_name, args, ret_type, lib_paths=lib_paths)


async def compile_and_run_async(fbc_code: str, func_name: str = 'main',
                                args: tuple = (), ret_type: str = 'Long',
                                cache_dir: str = None,
                                extra_includes: list = None,
                                inc_paths: list = None,
                                lib_paths: list = None):
    """
    异步编译并运行 FreeBASIC 代码

    参数：
        fbc_code: FreeBASIC 函数体代码（不含签名）
        func_name: 函数名（默认 'main'）
        args: 参数元组
        ret_type: 返回类型
        cache_dir: 编译缓存目录
        extra_includes: 额外的源码片段
        inc_paths: 额外的头文件搜索路径
        lib_paths: 额外的库搜索路径

    返回：
        函数返回值（awaitable）

    使用示例：
        result = await compile_and_run_async("Return a + b", args=(3, 4))
    """
    loop = asyncio.get_event_loop()

    def _run():
        full_code = _generate_fbc_wrapper(
            func_name,
            infer_fb_argtypes(args),
            fbc_code,
            ret_type,
        )
        dll_path = _compile_fbc_code(full_code, func_name, cache_dir,
                                     extra_includes=extra_includes,
                                     inc_paths=inc_paths,
                                     lib_paths=lib_paths)
        return _call_fbc_func(dll_path, func_name, args, ret_type, lib_paths=lib_paths)

    return await loop.run_in_executor(_executor, _run)
