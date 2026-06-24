"""
vools.bridge.mojo.compiler - Mojo 动态编译装饰器

使用方式：
    @mojo
    def fib(n: int) -> int:
        return \"\"\"
        if n <= 1:
            return 1
        return fib(n-1) + fib(n-2)
        \"\"\"

    @mojo
    def sum_arr(arr: 'list[int]') -> int:
        return '''
        var total = 0
        for i in range(n):
            total += arr[i]
        return total
        '''

    result = fib(10)
    result = sum_arr([1, 2, 3, 4, 5])

    # 异步模式
    @mojo(async_mode=True)
    async def heavy(data: 'list[int]') -> int:
        return '''
        var total = 0
        for i in range(n):
            total += data[i]
        return total
        '''
    result = await heavy([1, 2, 3, 4, 5])

参数：
    func: 被装饰的函数
    mode: 运行模式
        DEBUG: 强制重编译并执行
        FORCE: 强制重编译但不执行
        NORMAL: 命中缓存跳过编译；未命中则编译
        ONLY_RUN: 只在有缓存时执行；没有则报错
        ONLY_CODE: 只生成 Mojo 代码，不编译 .so
    cache_dir: 编译缓存目录，None 则使用系统临时目录
    ret_type: 返回类型（'Int64'/'Float64'/'Bool'/'None'），None 时从注解推断
    async_mode: 是否异步执行（默认 False）
    auto_signature: 是否自动根据参数类型生成签名（默认 True）

设计目标：免序列化（serialization-free）交互
- list 参数走 UnsafePointer + 长度 Int64，不走 CSV/JSON
- 通过 transport 模块可注入 zero-copy 实现（zinc / Mojo from Python）
- 运行环境：WSL Linux + Mojo 1.0b1（Modular）
"""

import os
import sys
import tempfile
import hashlib
import platform
import asyncio
import inspect
import functools
import threading
import ctypes
import shutil
from concurrent.futures import ThreadPoolExecutor
from typing import Any, List, Tuple

from .._base import LangBridge, FunctionSpec
from .types import (
    PY_TO_MOJO_TYPE,
    get_mojo_type,
    infer_mojo_argtypes,
    is_array_type,
    MOJO_TO_CTYPES,
    get_ctype_for,
)
from .transport import get_transport, Transport
from .templates import (
    generate_mojo_wrapper,
    preprocess_mojo_body,
    generate_function_signature,
)

# 平台判断
_IS_LINUX = platform.system() == 'Linux'
_IS_WINDOWS = platform.system() == 'Windows'

# Mojo 编译器名
_MOJO_COMPILER = 'mojo'

# Mojo 1.0b1 在不同平台的常见安装路径（Modular 默认）
_MOJO_SEARCH_PATHS = [
    os.path.expanduser('~/.modular/bin'),
    os.path.expanduser('~/mojo/bin'),
    os.path.expanduser('~/.local/bin'),
    '/usr/local/bin',
    '/usr/bin',
    '/opt/modular/bin',
]


def _get_mojo_path() -> str:
    """获取 mojo 编译器路径。优先 shutil.which，找不到时按 _MOJO_SEARCH_PATHS 探测。"""
    found = shutil.which(_MOJO_COMPILER)
    if found:
        return found
    exe_suffix = '.exe' if _IS_WINDOWS else ''
    for p in _MOJO_SEARCH_PATHS:
        candidate = os.path.join(p, _MOJO_COMPILER + exe_suffix)
        if os.path.exists(candidate):
            return candidate
    return _MOJO_COMPILER


def _setup_mojo_env() -> str:
    """设置 Mojo 运行环境（PATH）；返回 mojo 可执行路径"""
    mojo_path = _get_mojo_path()
    mojo_dir = os.path.dirname(mojo_path)
    if mojo_dir and os.path.isdir(mojo_dir):
        env_paths = os.environ.get('PATH', '').split(os.pathsep)
        if mojo_dir not in env_paths:
            os.environ['PATH'] = mojo_dir + os.pathsep + os.environ.get('PATH', '')
    return mojo_path


_MOJO_PATH = _setup_mojo_env()

# 延迟导入 subprocess（避免顶层硬依赖）
import subprocess


def mojo_compiler_available() -> bool:
    """检查 Mojo 编译器是否可用（执行 `mojo --version`）"""
    try:
        result = subprocess.run(
            [_MOJO_PATH, '--version'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, OSError):
        return False
    except Exception:
        return False


# 编译缓存目录
_CACHE_DIR = os.path.join(tempfile.gettempdir(), 'vools_mojo_cache')


# ----------------------------------------------------------------------------
# 编译逻辑：候选命令探测（Mojo 1.0b1 编译 .so 的命令尚未文档化）
# ----------------------------------------------------------------------------

# 候选编译命令（按优先级排列）
_MOJO_COMPILE_CANDIDATES = [
    ['build', '-o', '{out}', '{src}'],
    ['build', '--emit', 'shared', '-o', '{out}', '{src}'],
    ['build', '-shared', '-o', '{out}', '{src}'],
    ['build', '--shared', '-o', '{out}', '{src}'],
]


def _compile_mojo_source(src_path: str, out_so_path: str, force: bool = False) -> str:
    """
    编译 Mojo 源文件为 .so

    1. 命中缓存（out_so_path 存在且 not force）直接返回；
    2. 候选命令按优先级尝试，每个失败时记录 stderr 摘要；
    3. 全部失败抛 RuntimeError。
    不使用 os.chdir，统一用绝对路径。
    """
    if not force and os.path.exists(out_so_path):
        return out_so_path

    src_abs = os.path.abspath(src_path)
    out_abs = os.path.abspath(out_so_path)
    out_dir = os.path.dirname(out_abs)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    last_err = None
    for tmpl in _MOJO_COMPILE_CANDIDATES:
        cmd = [_MOJO_PATH] + [t.format(src=src_abs, out=out_abs) for t in tmpl]
        try:
            result = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60,
            )
        except FileNotFoundError as e:
            last_err = f'FileNotFoundError: {e} (cmd={cmd})'
            continue
        except subprocess.TimeoutExpired:
            last_err = f'TimeoutExpired (60s) (cmd={cmd})'
            continue
        except Exception as e:
            last_err = f'{type(e).__name__}: {e} (cmd={cmd})'
            continue

        if result.returncode == 0 and os.path.exists(out_abs):
            return out_abs

        last_err = (
            f'cmd={cmd}\n'
            f'returncode={result.returncode}\n'
            f'stdout={result.stdout[:500]}\n'
            f'stderr={result.stderr[:500]}'
        )
        continue

    raise RuntimeError(f'Mojo 编译失败: 所有候选命令均未成功\n{last_err}')


# ----------------------------------------------------------------------------
# 线程池与异步
# ----------------------------------------------------------------------------

_executor = ThreadPoolExecutor(max_workers=4)


class MojoFuture:
    """
    Mojo 异步执行 Future

    对 ThreadPoolExecutor.Future 做薄包装，支持 .result() / .done() / .cancel()。
    """
    def __init__(self, fn, *args, **kwargs):
        self._future = _executor.submit(fn, *args, **kwargs)

    def result(self, timeout=None):
        return self._future.result(timeout=timeout)

    def done(self):
        return self._future.done()

    def cancelled(self):
        return self._future.cancelled()

    def add_done_callback(self, fn):
        self._future.add_done_callback(fn)

    def cancel(self):
        return self._future.cancel()

    def __repr__(self):
        state = 'RUNNING' if not self.done() else ('DONE' if not self.cancelled() else 'CANCELLED')
        return f'<MojoFuture {id(self)} [{state}]>'

    def __getattr__(self, name):
        return getattr(self._future, name)


# ----------------------------------------------------------------------------
# Mojo 代码生成（辅助函数）
# ----------------------------------------------------------------------------

def _resolve_params(sig: inspect.Signature, args_runtime: Tuple) -> List:
    """
    解析形参列表（Mojo 端），按类型注解/运行时值推断

    返回：[(param_name, mojo_type, is_array, is_length), ...]
      is_array=True  → 该形参是 UnsafePointer[T]
      is_length=True → 该形参是数组的长度参数 Int64

    长度参数命名规则：
      仅 1 个数组参数 → 名为 'n'（与 fbc.py 习惯一致）
      多个数组参数   → 名为 '{pname}_n'
    """
    # 预扫描：统计数组参数数量
    array_param_names = []
    for pname, param in sig.parameters.items():
        if param.annotation is not param.empty:
            mt = get_mojo_type(param.annotation)
        else:
            mt = 'Int64'
        if is_array_type(mt):
            array_param_names.append(pname)
    use_short_n = (len(array_param_names) == 1)

    params = []
    arg_idx = 0
    for pname, param in sig.parameters.items():
        if param.annotation is not param.empty:
            mojo_type = get_mojo_type(param.annotation)
        else:
            if arg_idx < len(args_runtime):
                inferred = infer_mojo_argtypes([args_runtime[arg_idx]])
                mojo_type = inferred[0] if inferred else 'Int64'
            else:
                mojo_type = 'Int64'

        if is_array_type(mojo_type):
            params.append((pname, mojo_type, True, False))
            length_name = 'n' if use_short_n else f'{pname}_n'
            params.append((length_name, 'Int64', False, True))
        else:
            params.append((pname, mojo_type, False, False))
        arg_idx += 1
    return params


def _generate_mojo_source(
    func_name: str,
    body: str,
    params: List,
    ret_type: str,
    auto_signature: bool = True,
) -> str:
    """生成完整的 Mojo 源码（@export 包装 + 缩进）"""
    param_pairs = [(p[0], p[1]) for p in params]
    if auto_signature:
        body = preprocess_mojo_body(body)
    return generate_mojo_wrapper(
        func_name=func_name,
        body=body,
        params=param_pairs,
        ret_type=ret_type,
    )


def _call_mojo_function(
    so_path: str,
    func_name: str,
    args: tuple,
    params: List,
    ret_type: str,
    transport: Transport,
):
    """
    加载 .so 并调用 Mojo 函数

    参数：
        so_path: .so 文件绝对路径
        func_name: 导出函数名
        args: 原始 Python 参数
        params: _resolve_params 返回的形参列表
        ret_type: Mojo 返回类型
        transport: Transport 实例

    返回：解码后的 Python 对象
    """
    lib = ctypes.CDLL(so_path)
    fn = getattr(lib, func_name)

    # 构造 argtypes
    fn.argtypes = [get_ctype_for(p[1]) for p in params]
    fn.restype = transport.prepare_ret(ret_type)

    # 构造 ctypes 参数（数组追加长度）
    ctypes_args = []
    for value, p in zip(args, params):
        _, mojo_type, is_array, _ = p
        c_value, _ = transport.prepare_arg(value, mojo_type)
        ctypes_args.append(c_value)
        if is_array:
            length = len(value) if value is not None else 0
            ctypes_args.append(ctypes.c_longlong(length))

    raw_result = fn(*ctypes_args)
    return transport.decode_result(raw_result, ret_type)


# ----------------------------------------------------------------------------
# 核心：_execute_sync — 同步执行体（thread-safe，可被 run_in_executor 调用）
# ----------------------------------------------------------------------------

def _execute_sync(
    func,
    sig,
    func_name,
    ret_type_str,
    cache_dir,
    mode,
    auto_signature,
    args,
):
    """
    同步执行体：解析参数 → 获取源码 → 编译 → 调用 → 返回

    此函数在后台线程（_executor）或主线程均可调用，须为纯函数风格
    （不依赖外部可变状态，所有上下文通过参数传入）。

    参数：
        func: 被装饰的 Python 函数
        sig: inspect.Signature
        func_name: 函数名
        ret_type_str: Mojo 返回类型字符串
        cache_dir: 缓存目录（绝对路径）
        mode: 运行模式（DEBUG/FORCE/NORMAL/ONLY_RUN/ONLY_CODE）
        auto_signature: 是否自动生成签名
        args: 位置参数元组

    返回：Mojo 函数调用结果；ONLY_CODE 时返回源码字符串；FORCE 时返回 .so 路径
    异常：RuntimeError / TypeError / FileNotFoundError
    """
    mode_upper = mode.upper()
    transport = get_transport()

    # 1. 解析形参（基于类型注解 + 运行时值推断）
    params = _resolve_params(sig, args)

    # 2. 调用函数获取 Mojo 源码
    try:
        mojo_body = func(*[None] * len(sig.parameters))
    except Exception as e:
        raise RuntimeError(f'获取 Mojo 代码失败: {e}') from e

    if not isinstance(mojo_body, str):
        raise TypeError(
            f'@mojo 装饰的函数必须返回 Mojo 源码字符串，得到 {type(mojo_body)}'
        )

    # 3. 生成完整 Mojo 源码
    mojo_source = _generate_mojo_source(
        func_name=func_name,
        body=mojo_body,
        params=params,
        ret_type=ret_type_str,
        auto_signature=auto_signature,
    )

    # 4. ONLY_CODE 模式：直接返回源码
    if mode_upper == 'ONLY_CODE':
        return mojo_source

    # 5. 检查编译器可用性
    if not mojo_compiler_available():
        raise RuntimeError(
            f'Mojo 编译器不可用（{_MOJO_PATH}）。请在 WSL 内安装 Modular Mojo 1.0b1。'
        )

    # 6. 写 .mojo 源文件 + 编译
    code_hash = hashlib.md5(mojo_source.encode('utf-8')).hexdigest()[:12]
    src_path = os.path.join(cache_dir, f'{func_name}_{code_hash}.mojo')
    out_so_path = os.path.join(cache_dir, f'lib{func_name}_{code_hash}.so')

    with open(src_path, 'w', encoding='utf-8') as f:
        f.write(mojo_source)

    force = mode_upper in ('DEBUG', 'FORCE')
    try:
        _compile_mojo_source(src_path, out_so_path, force=force)
    except Exception as e:
        if mode_upper != 'NORMAL':
            raise
        raise RuntimeError(f'Mojo 编译失败: {e}') from e

    if mode_upper == 'FORCE':
        return out_so_path

    if mode_upper == 'ONLY_RUN' and not os.path.exists(out_so_path):
        raise FileNotFoundError(f'ONLY_RUN 模式: .so 文件不存在: {out_so_path}')

    # 7. 加载 .so 并执行
    return _call_mojo_function(
        so_path=out_so_path,
        func_name=func_name,
        args=args,
        params=params,
        ret_type=ret_type_str,
        transport=transport,
    )





# ----------------------------------------------------------------------------
# 便捷入口
# ----------------------------------------------------------------------------

def compile_and_run(
    mojo_code: str,
    func_name: str = 'main',
    args: tuple = (),
    ret_type: str = 'Int64',
    cache_dir: str = None,
):
    """
    直接编译并运行一段 Mojo 源码（无装饰器）

    参数：
        mojo_code: 完整 Mojo 源码（已包含 @export 装饰器与 def 头）
        func_name: 要调用的导出函数名
        args: Python 位置参数
        ret_type: 返回类型
        cache_dir: 缓存目录（可选）

    返回：函数调用结果
    """
    actual_cache_dir = cache_dir or _CACHE_DIR
    os.makedirs(actual_cache_dir, exist_ok=True)

    code_hash = hashlib.md5(mojo_code.encode('utf-8')).hexdigest()[:12]
    src_path = os.path.join(actual_cache_dir, f'{func_name}_{code_hash}.mojo')
    out_so_path = os.path.join(actual_cache_dir, f'lib{func_name}_{code_hash}.so')

    with open(src_path, 'w', encoding='utf-8') as f:
        f.write(mojo_code)

    _compile_mojo_source(src_path, out_so_path, force=False)

    lib = ctypes.CDLL(out_so_path)
    fn = getattr(lib, func_name)
    fn.restype = get_ctype_for(ret_type)
    raw = fn(*args)
    return get_transport().decode_result(raw, ret_type)


def is_mojo_available() -> bool:
    """
    检查 Mojo 预编译库是否可用

    约定探测库名 `libvools_mojo_demo.so`；若 vools/lib/mojo/ 下不存在则返回 False。
    """
    try:
        from vools.bridge.mojo.loader import get_mojo_lib
        return get_mojo_lib('vools_mojo_demo') is not None
    except Exception:
        return False


# ----------------------------------------------------------------------------
# MojoBridge - Mojo 桥接实现（继承 LangBridge）
# ----------------------------------------------------------------------------

class MojoBridge(LangBridge):
    """
    Mojo 语言桥接实现

    继承 LangBridge 抽象基类，实现 Mojo 特定的代码生成、编译和调用。
    """

    name = 'mojo'
    file_ext = '.mojo'
    lib_ext = '.dll' if _IS_WINDOWS else ('.dylib' if platform.system() == 'Darwin' else '.so')

    def __init__(self):
        super().__init__()
        _setup_mojo_env()

    def compiler_available(self) -> bool:
        """编译器是否可用"""
        return mojo_compiler_available()

    def generate_code(self, spec: FunctionSpec) -> str:
        """
        生成 Mojo 代码

        包含：
        1. module_code（用户提供的模块级代码）
        2. 依赖函数（从 deps 参数生成）
        3. 主函数
        """
        parts = []

        if spec.module_code:
            parts.append(spec.module_code)
            parts.append('')

        for dep in spec.dependencies:
            dep_code = self._generate_function(dep)
            if dep_code:
                parts.append(dep_code)
                parts.append('')

        main_code = self._generate_function(spec)
        parts.append(main_code)

        return '\n'.join(parts)

    def _generate_function(self, spec: FunctionSpec) -> str:
        """生成单个函数的 Mojo 代码"""
        params = []
        ret_type = 'Int64'

        for name, ann in spec.annotations.items():
            if name == 'return':
                ret_type = get_mojo_type(ann)
                continue
            mojo_type = get_mojo_type(ann) if ann else 'Int64'
            if is_array_type(mojo_type):
                params.append((name, mojo_type))
                length_name = f'{name}_n'
                params.append((length_name, 'Int64'))
            else:
                params.append((name, mojo_type))

        body = spec.body
        if body:
            body = preprocess_mojo_body(body)

        return generate_mojo_wrapper(
            func_name=spec.name,
            body=body,
            params=params,
            ret_type=ret_type,
        )

    def compile_code(self, code: str, func_name: str, cache_dir: str = None) -> str:
        """编译 Mojo 代码"""
        actual_cache_dir = cache_dir or _CACHE_DIR
        os.makedirs(actual_cache_dir, exist_ok=True)

        code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
        src_path = os.path.join(actual_cache_dir, f'{func_name}_{code_hash}.mojo')
        out_so_path = os.path.join(actual_cache_dir, self.get_lib_filename(f'{func_name}_{code_hash}'))

        with open(src_path, 'w', encoding='utf-8') as f:
            f.write(code)

        _compile_mojo_source(src_path, out_so_path, force=False)
        return out_so_path

    def compile_project(self, project_dir: str, entry: str, output_dir: str = None) -> str:
        """
        编译 Mojo 项目

        扫描 project_dir 下所有 .mojo 文件，调用 mojo build 编译。
        entry='main' 时生成可执行文件，否则生成共享库。
        """
        output_dir = output_dir or _CACHE_DIR
        os.makedirs(output_dir, exist_ok=True)

        mojo_files = []
        for root, dirs, files in os.walk(project_dir):
            for f in files:
                if f.endswith('.mojo') or f.endswith('.🔥'):
                    mojo_files.append(os.path.join(root, f))

        if not mojo_files:
            raise RuntimeError(f'No .mojo files found in project directory: {project_dir}')

        mojo_files.sort()

        project_name = os.path.basename(os.path.abspath(project_dir))

        if entry == 'main':
            if _IS_WINDOWS:
                output_path = os.path.join(output_dir, f'{project_name}.exe')
            else:
                output_path = os.path.join(output_dir, project_name)
            compile_cmd = [_MOJO_PATH, 'build', '-o', output_path] + mojo_files
        else:
            output_path = os.path.join(output_dir, self.get_lib_filename(project_name))
            compile_cmd = [_MOJO_PATH, 'build', '--shared', '-o', output_path] + mojo_files

        result = subprocess.run(
            compile_cmd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
            cwd=output_dir
        )

        if result.returncode != 0:
            raise RuntimeError(
                f'Mojo project compilation failed:\n'
                f'stderr:\n{result.stderr}\n'
                f'stdout:\n{result.stdout}\n'
                f'files: {mojo_files}'
            )

        return output_path

    def call_func(self, lib_path: str, func_name: str,
                  args: tuple, ret_type=None) -> Any:
        """调用 Mojo 编译的函数"""
        transport = get_transport()
        lib = ctypes.CDLL(lib_path)
        fn = getattr(lib, func_name)

        mojo_ret_type = get_mojo_type(ret_type) if ret_type else 'Int64'
        fn.restype = transport.prepare_ret(mojo_ret_type)

        mojo_arg_types = infer_mojo_argtypes(list(args))

        ctypes_args = []
        fn_argtypes = []
        for value, mojo_type in zip(args, mojo_arg_types):
            c_value, _ = transport.prepare_arg(value, mojo_type)
            ctypes_args.append(c_value)
            fn_argtypes.append(get_ctype_for(mojo_type))
            if is_array_type(mojo_type):
                length = len(value) if value is not None else 0
                ctypes_args.append(ctypes.c_longlong(length))
                fn_argtypes.append(ctypes.c_longlong)

        fn.argtypes = fn_argtypes
        raw_result = fn(*ctypes_args)
        return transport.decode_result(raw_result, mojo_ret_type)


# 全局 MojoBridge 实例
_mojo_bridge = MojoBridge()

# 统一装饰器接口（使用 LangBridge 标准装饰器）
mojo = _mojo_bridge.decorator
