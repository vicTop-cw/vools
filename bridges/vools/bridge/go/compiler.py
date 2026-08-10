"""
vools.bridge.go.compiler - Go 语言桥接编译器实现

提供 Go 动态编译与跨语言桥接能力，对齐 vools.bridge.mojo / freebasic 的 API 形态。

设计目标：免序列化（serialization-free）交互
- 列表/切片参数走 unsafe.Pointer + 长度（C.longlong），不走 CSV/JSON
- 字符串参数走 *C.char（c_char_p），cgo 端由 //export 包装层做 C.CString/C.GoString 转换
- 通过 pygo 风格的 cgo + ctypes 模式：编译为 c-shared，ctypes 加载
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
import subprocess
from concurrent.futures import ThreadPoolExecutor
from typing import Any, List, Tuple

from ..core.types import CTypeMapper, infer_arg_types, infer_ret_type, convert_args, LangType
from ..manager import get_helper
from .._base import LangBridge, FunctionSpec, FunctionParser

# ----------------------------------------------------------------------------
# 平台判断
# ----------------------------------------------------------------------------
_IS_WINDOWS = platform.system() == 'Windows'
_IS_LINUX = platform.system() == 'Linux'
_IS_MACOS = platform.system() == 'Darwin'

# 使用 manager 的编译器辅助
_go_helper = get_helper('go')


def _setup_go_env() -> str:
    """
    设置 Go 运行环境（PATH）；返回 go 可执行路径

    委托给 manager 设置环境。
    """
    _go_helper.setup_env()
    return _go_helper.get_compiler_path() or 'go'


def _get_go_path() -> str:
    """
    获取 go 编译器路径

    使用 manager 统一管理。
    """
    return _go_helper.get_compiler_path() or 'go'


# 初始化环境
_GO_PATH = _setup_go_env()


def go_compiler_available() -> bool:
    """
    检查 Go 编译器是否可用

    使用 manager 统一管理。

    返回：
        bool: 如果 go 编译器可用返回 True，否则返回 False
    """
    return _go_helper.is_available()


# ----------------------------------------------------------------------------
# 编译缓存目录
# ----------------------------------------------------------------------------
_GO_CACHE_DIR = os.path.join(tempfile.gettempdir(), 'vools_go_cache')


def _shared_lib_ext() -> str:
    """
    返回当前平台下 c-shared 编译产物的扩展名

    Windows: .dll
    Linux:   .so
    macOS:   .dylib
    """
    if _IS_WINDOWS:
        return '.dll'
    if _IS_MACOS:
        return '.dylib'
    return '.so'


# ----------------------------------------------------------------------------
# Python ↔ Go 类型映射
# ----------------------------------------------------------------------------

# Python 类型 → Go 端 cgo 类型（c-shared 暴露的 C ABI 类型）
PY_TO_GO_TYPE = {
    int: 'C.longlong',
    float: 'C.double',
    bool: 'C.bool',
    str: '*C.char',
    bytes: 'unsafe.Pointer',  # 配 len 参数
    list: 'unsafe.Pointer',   # 配 len 参数
    type(None): 'C.void',  # 占位；实际无返回值场景不会用
}

# 字符串别名到 Go 类型的回退（用于 typing 或 str 形式注解）
_GO_TYPE_ALIASES = {
    'int': 'C.longlong',
    'int8': 'C.char',
    'int16': 'C.short',
    'int32': 'C.int',
    'int64': 'C.longlong',
    'uint': 'C.ulonglong',
    'uint8': 'C.uchar',
    'uint16': 'C.ushort',
    'uint32': 'C.uint',
    'uint64': 'C.ulonglong',
    'float': 'C.double',
    'float32': 'C.float',
    'float64': 'C.double',
    'double': 'C.double',
    'bool': 'C.bool',
    'str': '*C.char',
    'string': '*C.char',
    'bytes': 'unsafe.Pointer',
    'list': 'unsafe.Pointer',
    'array': 'unsafe.Pointer',
    'void': 'C.void',
    'none': 'C.void',
    'nonetype': 'C.void',
}


def get_go_type(py_type):
    """
    根据 Python 类型获取 Go 端 cgo 类型字符串

    参数：
        py_type: Python 类型 / 类型注解（可为字符串形式）

    返回：
        Go 端 cgo 类型字符串，未知则返回 'C.longlong'
    """
    # 直接匹配
    if py_type in PY_TO_GO_TYPE:
        return PY_TO_GO_TYPE[py_type]

    # 字符串形式注解（来自 typing 或 forward reference）
    if isinstance(py_type, str):
        normalized = py_type.strip().lower()
        # 处理 list[int] / list[float] / list[str] 等泛型形式
        if normalized.startswith('list[') or normalized.startswith('array['):
            return 'unsafe.Pointer'
        if normalized in _GO_TYPE_ALIASES:
            return _GO_TYPE_ALIASES[normalized]
        # 处理带模块前缀的，例如 'builtins.int' -> 'int'
        short = normalized.split('.')[-1]
        if short in _GO_TYPE_ALIASES:
            return _GO_TYPE_ALIASES[short]
        return 'C.longlong'

    return 'C.longlong'


def infer_go_argtypes(args):
    """
    根据运行时值推断 Go 端入参类型

    返回：
        Go 类型字符串列表
    """
    result = []
    for arg in args:
        if isinstance(arg, bool):
            result.append('C.bool')
        elif isinstance(arg, int):
            result.append('C.longlong')
        elif isinstance(arg, float):
            result.append('C.double')
        elif isinstance(arg, str):
            result.append('*C.char')
        elif isinstance(arg, (bytes, bytearray)):
            result.append('unsafe.Pointer')
        elif isinstance(arg, (list, tuple)):
            result.append('unsafe.Pointer')
        else:
            result.append('unsafe.Pointer')
    return result


def is_array_type(go_type: str) -> bool:
    """
    判断 Go 端入参类型是否为数组（unsafe.Pointer，需要配 len 参数）

    返回：
        bool
    """
    return go_type == 'unsafe.Pointer'


# Go 端 cgo 类型 → ctypes 类型（ctypes 端 C ABI 边界）
GO_TO_CTYPES = {
    'C.char': ctypes.c_int8,
    'C.uchar': ctypes.c_uint8,
    'C.short': ctypes.c_int16,
    'C.ushort': ctypes.c_uint16,
    'C.int': ctypes.c_int32,
    'C.uint': ctypes.c_uint32,
    'C.long': ctypes.c_long,
    'C.ulong': ctypes.c_ulong,
    'C.longlong': ctypes.c_int64,
    'C.ulonglong': ctypes.c_uint64,
    'C.float': ctypes.c_float,
    'C.double': ctypes.c_double,
    'C.bool': ctypes.c_bool,
    '*C.char': ctypes.c_char_p,
    'unsafe.Pointer': ctypes.c_void_p,
    'C.void': None,
}


def get_ctype_for(go_type: str):
    """
    根据 Go 端 cgo 类型获取 ctypes 类型

    返回：
        ctypes 类型；C.void 返回 None
    """
    return GO_TO_CTYPES.get(go_type, ctypes.c_int64)


def _resolve_go_ret_type(annotation):
    """
    从函数返回类型注解解析 Go 端 cgo 类型

    返回：
        Go 端 cgo 类型字符串
    """
    if annotation is None or annotation is type(None):
        return 'C.void'
    if isinstance(annotation, type):
        return PY_TO_GO_TYPE.get(annotation, 'C.longlong')
    if isinstance(annotation, str):
        return get_go_type(annotation)
    return 'C.longlong'


# ----------------------------------------------------------------------------
# 编译逻辑
# ----------------------------------------------------------------------------

def _find_c_compiler() -> str:
    """
    查找系统上可用的 C 编译器（用于 cgo）

    优先查找功能完整的 MinGW GCC，避免使用可能缺少头文件的
    精简版 GCC（如 FreeBasic 内置的 GCC）。

    返回：
        C 编译器路径或命令名
    """
    # 优先查找 MinGW GCC（在常见安装路径中）
    mingw_paths = [
        os.path.join(os.environ.get('LOCALAPPDATA', ''), 'mingw64', 'mingw64', 'bin'),
        os.path.join(os.environ.get('PROGRAMFILES', 'C:\\Program Files'), 'mingw64', 'bin'),
        'C:\\mingw64\\bin',
        'C:\\msys64\\mingw64\\bin',
        'C:\\msys64\\ucrt64\\bin',
    ]
    for cc_name in ('gcc', 'cc', 'clang', 'cl.exe'):
        # 优先检查 MinGW 路径
        for mp in mingw_paths:
            cc_path = os.path.join(mp, cc_name + '.exe')
            if os.path.isfile(cc_path):
                return cc_path
        # 回退到 PATH 搜索
        cc_path = shutil.which(cc_name)
        if cc_path:
            # 排除已知缺少头文件的精简版 GCC
            cc_lower = cc_path.lower()
            if 'freebasic' in cc_lower:
                continue
            return cc_path
    return 'gcc'


def _build_env_with_cc() -> dict:
    """
    构建包含 C 编译器路径的子进程环境

    返回：
        dict: 环境变量字典
    """
    env = os.environ.copy()
    cc_path = _find_c_compiler()
    cc_dir = os.path.dirname(cc_path)
    if cc_dir and cc_dir not in env.get('PATH', ''):
        env['PATH'] = cc_dir + os.pathsep + env.get('PATH', '')
    # 使用完整路径而非 basename，确保 Go 的 cgo 使用正确的 C 编译器
    env['CC'] = cc_path
    return env


def _compile_go_code(code: str, func_name: str, cache_dir: str = None,
                     force: bool = False) -> str:
    """
    编译 Go 代码并返回共享库路径

    参数：
        code: 完整 Go 源代码（package main，含 //export）
        func_name: 函数名（用于生成文件名）
        cache_dir: 缓存目录，None 则使用 _GO_CACHE_DIR
        force: 强制重新编译（忽略缓存）

    返回：
        编译后的共享库绝对路径

    异常：
        RuntimeError: 编译失败
    """
    if cache_dir is None:
        cache_dir = _GO_CACHE_DIR

    os.makedirs(cache_dir, exist_ok=True)

    # 生成唯一文件名（基于代码 MD5）
    code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
    base_name = f'go_{func_name}_{code_hash}'
    src_path = os.path.join(cache_dir, f'{base_name}.go')
    ext = _shared_lib_ext()
    so_path = os.path.join(cache_dir, f'{base_name}{ext}')

    # 缓存命中（且非强制）
    if not force and os.path.exists(so_path):
        return so_path

    # 写入 .go 源文件
    with open(src_path, 'w', encoding='utf-8') as f:
        f.write(code)

    # 编译命令：go build -buildmode=c-shared -o out src
    # 使用相对于 cwd 的源文件路径，避免 cgo 在 Windows 上因绝对路径解析失败
    src_rel = os.path.basename(src_path)
    compile_cmd = [
        _GO_PATH, 'build',
        '-buildmode=c-shared',
        '-o', so_path,
        src_rel,
    ]

    # 构建包含 C 编译器的子进程环境
    build_env = _build_env_with_cc()

    result = subprocess.run(
        compile_cmd,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True,
        timeout=60,
        env=build_env,
        cwd=cache_dir,
    )

    if result.returncode != 0 or not os.path.exists(so_path):
        raise RuntimeError(
            f'Go 编译失败:\n'
            f'stderr:\n{result.stderr}\n'
            f'stdout:\n{result.stdout}\n'
            f'代码:\n{code}'
        )

    return so_path


def _load_go_shared_lib(so_path: str):
    """
    加载 Go 编译的 c-shared 库

    Windows 上需要先把 dll 所在目录加入 dll search path，
    避免运行时找不到 libgo / 同伴 dll。
    """
    if not os.path.exists(so_path):
        raise FileNotFoundError(f'Go 共享库不存在: {so_path}')

    # Windows: 把 dll 所在目录加入 dll search path
    if _IS_WINDOWS:
        add_dll_dir = getattr(os, 'add_dll_directory', None)
        if add_dll_dir:
            dll_dir = os.path.dirname(os.path.abspath(so_path))
            try:
                add_dll_dir(dll_dir)
            except OSError:
                pass

    return ctypes.CDLL(so_path)


def _call_go_function(so_path: str, func_name: str, args: tuple,
                      param_go_types: List, ret_go_type: str):
    """
    调用 Go 编译的函数

    数组参数：param_go_types 中标记为 'unsafe.Pointer' 的项会被自动展开为
    (ptr, len) 两个 ctypes 入参。

    参数：
        so_path: 共享库绝对路径
        func_name: 函数名
        args: 原始 Python 参数
        param_go_types: 与 args 位置对应的 Go 端入参类型列表
        ret_go_type: Go 端返回类型字符串

    返回：
        Python 端的解码结果
    """
    lib = _load_go_shared_lib(so_path)
    func = getattr(lib, func_name)

    # 构造 ctypes argtypes：标量 + 数组（拆为 ptr + len）
    c_argtypes = []
    c_args = []
    for value, go_t in zip(args, param_go_types):
        if is_array_type(go_t):
            # 数组：拆为 (ptr, len)
            arr = value if value is not None else []
            n = len(arr)
            if n == 0:
                c_arr = (ctypes.c_int64 * 1)()
                c_args.append(ctypes.cast(c_arr, ctypes.c_void_p))
            else:
                # 元素类型：int 默认走 c_longlong
                elem_ct = ctypes.c_int64
                c_arr = (elem_ct * n)(*arr)
                c_args.append(ctypes.cast(c_arr, ctypes.c_void_p))
            c_argtypes.append(ctypes.c_void_p)
            c_args.append(ctypes.c_longlong(n))
            c_argtypes.append(ctypes.c_longlong)
        else:
            # 标量
            if go_t == '*C.char':
                if isinstance(value, str):
                    c_value = value.encode('utf-8')
                elif isinstance(value, bytes):
                    c_value = value
                else:
                    c_value = str(value).encode('utf-8')
                c_args.append(c_value)
                c_argtypes.append(ctypes.c_char_p)
            elif go_t == 'C.bool':
                c_args.append(ctypes.c_bool(bool(value)))
                c_argtypes.append(ctypes.c_bool)
            elif go_t in ('C.float',):
                c_args.append(ctypes.c_float(float(value)))
                c_argtypes.append(ctypes.c_float)
            elif go_t in ('C.double',):
                c_args.append(ctypes.c_double(float(value)))
                c_argtypes.append(ctypes.c_double)
            else:
                # 整数系列
                c_args.append(ctypes.c_int64(int(value)))
                c_argtypes.append(ctypes.c_int64)

    func.argtypes = c_argtypes

    # 设置返回类型
    restype = get_ctype_for(ret_go_type)
    func.restype = restype

    # 调用
    raw = func(*c_args)

    # 解码返回值
    if restype is ctypes.c_char_p and raw is not None:
        if isinstance(raw, bytes):
            return raw.decode('utf-8')
        return raw
    if restype is ctypes.c_bool:
        return bool(raw)
    return raw


# ----------------------------------------------------------------------------
# Go 代码生成
# ----------------------------------------------------------------------------

def _preprocess_go_body(body: str, auto_signature: bool) -> str:
    """
    预处理 Go 函数体

    - 剥离前导空行
    - auto_signature=True 时按行 4 空格缩进
    - 保留 ^import 等预处理行（与 fbc.py 的 preprocessor_lines 同款处理）
    """
    if not auto_signature:
        return body

    indented_lines = []
    for raw_line in body.split('\n'):
        line = raw_line.rstrip()
        if not line:
            indented_lines.append('')
            continue
        # 用户自定义 import 行不缩进（在签名内部出现时不常见，但保险起见保留缩进控制）
        indented_lines.append('    ' + line)

    # 去掉首尾空行
    while indented_lines and not indented_lines[0]:
        indented_lines.pop(0)
    while indented_lines and not indented_lines[-1]:
        indented_lines.pop()

    return '\n'.join(indented_lines)


def _generate_go_source(
    func_name: str,
    params: List,
    ret_go_type: str,
    body: str,
    auto_signature: bool = True,
) -> str:
    """
    生成完整的 Go 源码（含 cgo //export 导出）

    参数：
        func_name: 函数名
        params: _resolve_params_from_sig 返回的形参列表 [(name, go_type, is_array), ...]
        ret_go_type: Go 端返回类型
        body: 函数体代码
        auto_signature: 是否自动生成签名（True 时 body 按 4 空格缩进）

    返回：
        完整 Go 源码字符串
    """
    # 构造参数列表：数组参数拆为 (ptr, n) 两项
    c_params = []
    for name, go_t, is_arr in params:
        if is_arr:
            c_params.append(f'{name} unsafe.Pointer')
            c_params.append(f'{name}_n C.longlong')
        else:
            c_params.append(f'{name} {go_t}')

    params_str = ', '.join(c_params) if c_params else ''

    # 返回值 cgo 类型
    if ret_go_type == 'C.void':
        ret_signature = ''
    else:
        ret_signature = f' {ret_go_type}'

    # 缩进函数体
    indented_body = _preprocess_go_body(body, auto_signature)
    if indented_body:
        indented_body = '\n' + indented_body + '\n'
    else:
        indented_body = '\n'

    # 检查是否需要 unsafe 包（数组参数需要 unsafe.Pointer）
    needs_unsafe = any(is_arr for _, _, is_arr in params)

    # c-shared 必须有 main()
    code = f'''package main

import "C"
{('import "unsafe"' if needs_unsafe else '')}

//export {func_name}
func {func_name}({params_str}){ret_signature} {{{indented_body}}}

func main() {{}}
'''
    return code


# ----------------------------------------------------------------------------
# 异步执行
# ----------------------------------------------------------------------------

_executor = ThreadPoolExecutor(max_workers=4)
_executor_lock = threading.Lock()


class GoFuture:
    """
    Go 异步执行 Future

    仿 NimFuture / MojoFuture，对 ThreadPoolExecutor.Future 做薄包装。
    支持 .result() / .done() / .add_done_callback() / .cancel() / __await__。
    """

    def __init__(self, fn, *args, **kwargs):
        self._future = _executor.submit(fn, *args, **kwargs)

    def result(self, timeout=None):
        return self._future.result(timeout=timeout)

    def done(self):
        return self._future.done()

    def add_done_callback(self, fn):
        self._future.add_done_callback(fn)

    def cancel(self):
        return self._future.cancel()

    def __getattr__(self, name):
        return getattr(self._future, name)

    def __await__(self):
        """
        将 GoFuture 适配为 asyncio 可 await 对象

        内部为 concurrent.futures.Future（非原生 asyncio.Future），
        通过 asyncio.wrap_future 包装为 asyncio.Future，
        然后委托其 __await__ 协议。
        """
        return asyncio.wrap_future(self._future).__await__()


# ----------------------------------------------------------------------------
# 缓存
# ----------------------------------------------------------------------------

# 缓存：func_name -> (code, so_path) 映射
_dll_cache = {}
_cache_lock = threading.Lock()


def _get_cached_so(func_name: str, code: str, force: bool = False) -> str:
    """
    获取缓存的共享库路径，必要时重新编译

    参数：
        func_name: 函数名
        code: 完整 Go 源码
        force: 是否强制重新编译

    返回：
        共享库绝对路径
    """
    with _cache_lock:
        cached = _dll_cache.get(func_name)
        if not force and cached and cached[0] == code and os.path.exists(cached[1]):
            return cached[1]
        so_path = _compile_go_code(code, func_name, force=force)
        _dll_cache[func_name] = (code, so_path)
        return so_path


def _remove_cached_so(func_name: str) -> None:
    """移除缓存的共享库（用于强制重编译）"""
    with _cache_lock:
        cached = _dll_cache.pop(func_name, None)
        if cached:
            so_path = cached[1]
            try:
                if os.path.exists(so_path):
                    os.remove(so_path)
            except OSError:
                pass





# ----------------------------------------------------------------------------
# 便捷入口
# ----------------------------------------------------------------------------

def compile_and_run(
    go_code: str,
    func_name: str = 'main',
    args: tuple = (),
    ret_type: str = 'C.longlong',
    cache_dir: str = None,
):
    """
    直接编译并运行一段 Go 源码（无装饰器）

    参数：
        go_code: 完整 Go 源码（已包含 package main、import "C" 与 //export 装饰器）
        func_name: 要调用的导出函数名
        args: Python 位置参数
        ret_type: 返回类型（Go 端 cgo 类型字符串）
        cache_dir: 缓存目录（可选）

    返回：
        函数调用结果
    """
    actual_cache_dir = cache_dir or _GO_CACHE_DIR
    os.makedirs(actual_cache_dir, exist_ok=True)

    # 运行时推断入参类型
    param_go_types = infer_go_argtypes(args)

    so_path = _compile_go_code(go_code, func_name, actual_cache_dir)
    return _call_go_function(so_path, func_name, args, param_go_types, ret_type)


def is_go_available() -> bool:
    """
    检查 Go 桥接是否可用（编译器或预编译库二选一）

    返回：
        bool: True 表示至少有一种使用方式可用
    """
    return go_compiler_available()


# ----------------------------------------------------------------------------
# GoBridge - Go 桥接实现（继承 LangBridge）
# ----------------------------------------------------------------------------

class GoBridge(LangBridge):
    """
    Go 语言桥接实现

    继承 LangBridge 抽象基类，实现 Go 特定的代码生成、编译和调用。
    """

    name = 'go'
    file_ext = '.go'
    lib_ext = '.dll' if _IS_WINDOWS else ('.dylib' if _IS_MACOS else '.so')
    lang_type = LangType.COMPILED

    def __init__(self):
        super().__init__()
        _setup_go_env()

    def compiler_available(self) -> bool:
        """编译器是否可用"""
        return go_compiler_available()

    def generate_code(self, spec: FunctionSpec) -> str:
        """
        生成 Go 代码

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

        return self._wrap_full_source('\n'.join(parts), spec.name)

    def _wrap_full_source(self, funcs_code: str, main_func: str) -> str:
        """包装完整的 Go 源码（package main, import, main 函数）"""
        # 检测是否需要 unsafe 包（检查是否使用了 unsafe.Pointer）
        needs_unsafe = 'unsafe.Pointer' in funcs_code
        return f'''package main

import "C"
{('import "unsafe"' if needs_unsafe else '')}

{funcs_code}

func main() {{}}
'''

    def _generate_function(self, spec: FunctionSpec) -> str:
        """生成单个函数的 Go 代码"""
        arg_names = []
        go_argtypes = []
        is_arrays = []

        for name, ann in spec.annotations.items():
            if name == 'return':
                continue
            arg_names.append(name)
            if ann is None or ann is inspect.Parameter.empty:
                go_t = 'C.longlong'
            else:
                go_t = get_go_type(ann)
            go_argtypes.append(go_t)
            is_arrays.append(is_array_type(go_t))

        ret_type = 'C.longlong'
        if 'return' in spec.annotations:
            ann = spec.annotations['return']
            if ann is type(None) or str(ann).lower() == 'none':
                ret_type = 'C.void'
            else:
                ret_type = get_go_type(ann)

        # 构造参数列表：数组参数拆为 (ptr, n) 两项
        c_params = []
        for i, (name, go_t, is_arr) in enumerate(zip(arg_names, go_argtypes, is_arrays)):
            if is_arr:
                c_params.append(f'{name} unsafe.Pointer')
                c_params.append(f'{name}_n C.longlong')
            else:
                c_params.append(f'{name} {go_t}')

        params_str = ', '.join(c_params) if c_params else ''

        # 返回值签名
        if ret_type == 'C.void':
            ret_signature = ''
        else:
            ret_signature = f' {ret_type}'

        # 缩进函数体
        indented_body = ''
        for line in spec.body.split('\n'):
            if line.strip():
                indented_body += '    ' + line + '\n'
            else:
                indented_body += '\n'

        if indented_body:
            indented_body = '\n' + indented_body + '\n'
        else:
            indented_body = '\n'

        return f'''//export {spec.name}
func {spec.name}({params_str}){ret_signature} {{{indented_body}}}'''

    def compile_code(self, code: str, func_name: str, cache_dir: str = None) -> str:
        """编译 Go 代码"""
        return _compile_go_code(code, func_name, cache_dir)

    def compile_project(self, project_dir: str, entry: str, output_dir: str = None) -> str:
        """
        编译 Go 项目

        扫描 project_dir 下所有 .go 文件，调用 go 编译器编译。
        entry='main' 时生成可执行文件，否则生成 c-shared 共享库。

        参数：
            project_dir: 项目目录路径
            entry: 入口函数名（'main' 表示生成可执行文件，其他表示生成共享库并导出该函数）
            output_dir: 输出目录

        返回：
            产物路径（exe 或 dll/so/dylib）

        异常：
            RuntimeError: 编译失败
        """
        output_dir = output_dir or _GO_CACHE_DIR
        os.makedirs(output_dir, exist_ok=True)

        go_files = []
        for root, dirs, files in os.walk(project_dir):
            for f in files:
                if f.endswith('.go'):
                    go_files.append(os.path.join(root, f))

        if not go_files:
            raise RuntimeError(f'No .go files found in project directory: {project_dir}')

        go_files.sort()

        project_name = os.path.basename(os.path.abspath(project_dir))

        if entry == 'main':
            if _IS_WINDOWS:
                output_path = os.path.join(output_dir, f'{project_name}.exe')
            else:
                output_path = os.path.join(output_dir, project_name)
            compile_cmd = [_GO_PATH, 'build', '-o', output_path, './...']
        else:
            ext = _shared_lib_ext()
            output_path = os.path.join(output_dir, f'{project_name}{ext}')
            compile_cmd = [_GO_PATH, 'build', '-buildmode=c-shared', '-o', output_path, './...']

        result = subprocess.run(
            compile_cmd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
            cwd=project_dir,
            env=_build_env_with_cc(),
        )

        if result.returncode != 0 or not os.path.exists(output_path):
            raise RuntimeError(
                f'Go project compilation failed:\n'
                f'stderr:\n{result.stderr}\n'
                f'stdout:\n{result.stdout}\n'
                f'files: {go_files}'
            )

        return output_path

    def call_func(self, lib_path: str, func_name: str,
                  args: tuple, ret_type=None) -> Any:
        """调用 Go 编译的函数"""
        param_go_types = []
        for arg in args:
            if isinstance(arg, bool):
                param_go_types.append('C.bool')
            elif isinstance(arg, int):
                param_go_types.append('C.longlong')
            elif isinstance(arg, float):
                param_go_types.append('C.double')
            elif isinstance(arg, str):
                param_go_types.append('*C.char')
            elif isinstance(arg, (bytes, bytearray, list, tuple)):
                param_go_types.append('unsafe.Pointer')
            else:
                param_go_types.append('C.longlong')

        # 将 Python 类型注解转换为 Go 类型字符串
        go_ret_type = _resolve_go_ret_type(ret_type)
        if go_ret_type == 'C.void':
            go_ret_type = 'C.longlong'
        return _call_go_function(
            lib_path, func_name, args, param_go_types, go_ret_type
        )


# 全局 GoBridge 实例
_go_bridge = GoBridge()

go = _go_bridge.decorator
