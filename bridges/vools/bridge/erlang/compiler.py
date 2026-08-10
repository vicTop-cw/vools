"""
vools.bridge.erlang.compiler - Erlang 语言桥接编译器实现

提供 Erlang 动态编译与跨语言桥接能力，对齐 vools.bridge.go 的 API 形态。

实现策略：
- Erlang 通过 erlc 编译模块为 .beam，然后通过 erl 执行
- 使用临时模块和输出解析返回结果
- 对于需要共享库的场景，生成 ERL_NIF C 代码并编译为 .dll/.so
"""

import os
import sys
import re
import tempfile
import hashlib
import platform
import asyncio
import inspect
import functools
import threading
import ctypes
import shutil
import subprocess
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, List, Tuple

from .._base import LangBridge, FunctionSpec
from ..core.types import LangType
from ..manager import get_helper, _find_executable

# ----------------------------------------------------------------------------
# 平台判断
# ----------------------------------------------------------------------------
_IS_WINDOWS = platform.system() == 'Windows'
_IS_LINUX = platform.system() == 'Linux'
_IS_MACOS = platform.system() == 'Darwin'

# 使用 manager 的编译器辅助
_erlang_helper = get_helper('erlang')


def _setup_erlang_env() -> str:
    """设置 Erlang 运行环境（PATH）；返回 erl 可执行路径"""
    _erlang_helper.setup_env()
    return _erlang_helper.get_compiler_path() or 'erlc'


def _get_erlc_path() -> str:
    """获取 erlc 编译器路径"""
    return _erlang_helper.get_compiler_path() or 'erlc'


def _get_erl_path() -> str:
    """获取 erl 运行时可执行路径"""
    # 在 PATH 和已配置路径中查找 erl（支持 .bat/.cmd）
    return _find_executable('erl') or 'erl'


# 初始化环境
_ERLC_PATH = _setup_erlang_env()
_ERL_PATH = _get_erl_path()


def erlang_compiler_available() -> bool:
    """检查 Erlang 编译器是否可用"""
    return _erlang_helper.is_available()


# ----------------------------------------------------------------------------
# 编译缓存目录
# ----------------------------------------------------------------------------
_ERLANG_CACHE_DIR = os.path.join(tempfile.gettempdir(), 'vools_erlang_cache')


def _shared_lib_ext() -> str:
    """返回当前平台下共享库的扩展名"""
    if _IS_WINDOWS:
        return '.dll'
    if _IS_MACOS:
        return '.dylib'
    return '.so'


# ----------------------------------------------------------------------------
# Python ↔ Erlang 类型映射
# ----------------------------------------------------------------------------

# Python 类型 → Erlang 类型字符串
PY_TO_ERLANG_TYPE = {
    int: 'integer',
    float: 'float',
    bool: 'boolean',
    str: 'binary',
    bytes: 'binary',
    bytearray: 'binary',
    list: 'list',
    tuple: 'tuple',
    type(None): 'none',
}

_ERLANG_TYPE_ALIASES = {
    'int': 'integer',
    'integer': 'integer',
    'float': 'float',
    'double': 'float',
    'bool': 'boolean',
    'boolean': 'boolean',
    'str': 'binary',
    'string': 'binary',
    'binary': 'binary',
    'bytes': 'binary',
    'list': 'list',
    'tuple': 'tuple',
    'array': 'list',
    'none': 'none',
    'void': 'none',
}


def get_erlang_type(py_type):
    """根据 Python 类型获取 Erlang 类型字符串"""
    if py_type is None or py_type is type(None):
        return 'none'
    if py_type in PY_TO_ERLANG_TYPE:
        return PY_TO_ERLANG_TYPE[py_type]
    if isinstance(py_type, str):
        normalized = py_type.strip().lower()
        if normalized.startswith('list[') or normalized.startswith('array['):
            return 'list'
        if normalized in _ERLANG_TYPE_ALIASES:
            return _ERLANG_TYPE_ALIASES[normalized]
        short = normalized.split('.')[-1]
        if short in _ERLANG_TYPE_ALIASES:
            return _ERLANG_TYPE_ALIASES[short]
        return 'integer'
    return 'integer'


def infer_erlang_argtypes(args):
    """根据运行时值推断 Erlang 入参类型"""
    result = []
    for arg in args:
        if isinstance(arg, bool):
            result.append('boolean')
        elif isinstance(arg, int):
            result.append('integer')
        elif isinstance(arg, float):
            result.append('float')
        elif isinstance(arg, str):
            result.append('binary')
        elif isinstance(arg, (bytes, bytearray)):
            result.append('binary')
        elif isinstance(arg, (list, tuple)):
            result.append('list')
        else:
            result.append('binary')
    return result


def is_array_type(erlang_type: str) -> bool:
    """判断 Erlang 入参类型是否为数组/列表"""
    return erlang_type == 'list'


# Erlang 类型 → ctypes 类型（用于 NIF 场景）
ERLANG_TO_CTYPES = {
    'integer': ctypes.c_int64,
    'float': ctypes.c_double,
    'boolean': ctypes.c_bool,
    'binary': ctypes.c_char_p,
    'list': ctypes.c_void_p,
    'tuple': ctypes.c_void_p,
    'none': None,
}


def get_ctype_for(erlang_type: str):
    """根据 Erlang 类型获取 ctypes 类型"""
    return ERLANG_TO_CTYPES.get(erlang_type, ctypes.c_int64)


# ----------------------------------------------------------------------------
# 编译与执行
# ----------------------------------------------------------------------------

def _compile_erlang_code(code: str, func_name: str, cache_dir: str = None,
                         force: bool = False) -> str:
    """
    编译 Erlang 代码并返回模块路径

    参数：
        code: 完整 Erlang 模块源码
        func_name: 函数名（用于生成文件名）
        cache_dir: 缓存目录
        force: 强制重新编译

    返回：
        .beam 文件绝对路径
    """
    if cache_dir is None:
        cache_dir = _ERLANG_CACHE_DIR

    os.makedirs(cache_dir, exist_ok=True)

    code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
    module_name = f'vools_erlang_{func_name}_{code_hash}'
    # Erlang 模块名必须是 atom，只能使用字母数字和下划线，且首字母小写
    module_name = re.sub(r'[^a-zA-Z0-9_]', '_', module_name)
    module_name = module_name[0].lower() + module_name[1:]

    src_path = os.path.join(cache_dir, f'{module_name}.erl')
    beam_path = os.path.join(cache_dir, f'{module_name}.beam')

    if not force and os.path.exists(beam_path):
        return beam_path

    # 将模块名替换进代码
    final_code = code.replace('%%MODULE_NAME%%', module_name)

    with open(src_path, 'w', encoding='utf-8') as f:
        f.write(final_code)

    compile_cmd = [_ERLC_PATH, '-o', cache_dir, src_path]
    result = subprocess.run(
        compile_cmd,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=60,
    )

    stderr = result.stderr.decode('utf-8', errors='replace') if result.stderr else ''
    stdout = result.stdout.decode('utf-8', errors='replace') if result.stdout else ''

    if result.returncode != 0 or not os.path.exists(beam_path):
        raise RuntimeError(
            f'Erlang 编译失败:\n'
            f'stderr:\n{stderr}\n'
            f'stdout:\n{stdout}\n'
            f'代码:\n{final_code}'
        )

    return beam_path


def _call_erlang_function(beam_path: str, func_name: str, args: tuple,
                          param_erlang_types: List, ret_erlang_type: str):
    """
    调用 Erlang 编译的函数

    通过 erl 执行调用并解析输出
    """
    cache_dir = os.path.dirname(beam_path)
    module_name = os.path.splitext(os.path.basename(beam_path))[0]

    # 构建 Erlang 调用表达式
    erl_args = []
    for i, (arg, erl_t) in enumerate(zip(args, param_erlang_types)):
        if erl_t == 'integer':
            erl_args.append(str(int(arg)))
        elif erl_t == 'float':
            erl_args.append('{:.10f}'.format(float(arg)))
        elif erl_t == 'boolean':
            erl_args.append('true' if arg else 'false')
        elif erl_t == 'binary':
            erl_args.append(f'<<"{str(arg)}">>/binary')
        elif erl_t == 'list':
            if arg and isinstance(arg[0], int):
                items = ','.join(str(x) for x in arg)
                erl_args.append(f'[{items}]')
            elif arg and isinstance(arg[0], float):
                items = ','.join(str(x) for x in arg)
                erl_args.append(f'[{items}]')
            elif arg and isinstance(arg[0], str):
                items = ','.join(f'<<"{x}">>' for x in arg)
                erl_args.append(f'[{items}]')
            else:
                erl_args.append('[]')
        else:
            erl_args.append(str(arg))

    call_expr = f'{module_name}:{func_name}({", ".join(erl_args)})'

    # 构建 erl 命令
    eval_expr = f'io:format("~p~n", [{call_expr}]), init:stop().'
    cmd = [
        _ERL_PATH,
        '-pa', cache_dir,
        '-noshell',
        '-eval', eval_expr,
    ]

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=30,
    )

    stderr = result.stderr.decode('utf-8', errors='replace') if result.stderr else ''
    stdout = result.stdout.decode('utf-8', errors='replace') if result.stdout else ''

    if result.returncode != 0:
        raise RuntimeError(
            f'Erlang 执行失败:\n'
            f'stderr:\n{stderr}\n'
            f'stdout:\n{stdout}'
        )

    output = stdout.strip()
    if not output:
        return None

    return _parse_erlang_output(output, ret_erlang_type)


def _parse_erlang_output(output: str, ret_type: str):
    """解析 Erlang 输出为 Python 类型"""
    output = output.strip()

    # 去除可能的 shell 输出前缀
    lines = [l.strip() for l in output.split('\n') if l.strip()]
    if not lines:
        return None
    value = lines[-1]

    if ret_type == 'boolean':
        return value == 'true'

    if ret_type == 'binary':
        # 处理 <<"...">> 或 "..."
        if value.startswith('<<"') and value.endswith('">>'):
            return value[3:-3]
        if value.startswith('"') and value.endswith('"'):
            return value[1:-1]
        return value

    if ret_type == 'float':
        try:
            return float(value)
        except ValueError:
            return value

    if ret_type == 'integer':
        try:
            return int(value)
        except ValueError:
            return value

    if ret_type == 'list':
        # 简单解析 Erlang 列表 [1,2,3]
        if value.startswith('[') and value.endswith(']'):
            inner = value[1:-1].strip()
            if not inner:
                return []
            items = []
            for item in _split_erlang_list(inner):
                items.append(_parse_erlang_value(item))
            return items
        return value

    # 自动推断
    return _parse_erlang_value(value)


def _split_erlang_list(s: str) -> List[str]:
    """简单分割 Erlang 列表元素"""
    items = []
    depth = 0
    current = ''
    for char in s:
        if char in '[{(':
            depth += 1
            current += char
        elif char in ']})':
            depth -= 1
            current += char
        elif char == ',' and depth == 0:
            if current.strip():
                items.append(current.strip())
            current = ''
        else:
            current += char
    if current.strip():
        items.append(current.strip())
    return items


def _parse_erlang_value(value: str):
    """自动解析 Erlang 值"""
    value = value.strip()

    if value == 'true':
        return True
    if value == 'false':
        return False
    if value == 'ok':
        return None
    if value == 'undefined':
        return None

    # 列表
    if value.startswith('[') and value.endswith(']'):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_erlang_value(x) for x in _split_erlang_list(inner)]

    # binary
    if value.startswith('<<"') and value.endswith('">>'):
        return value[3:-3]

    # 字符串
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]

    # 元组
    if value.startswith('{') and value.endswith('}'):
        inner = value[1:-1].strip()
        items = _split_erlang_list(inner)
        return tuple(_parse_erlang_value(x) for x in items)

    # 数字
    try:
        if '.' in value:
            return float(value)
        return int(value)
    except ValueError:
        pass

    return value


# ----------------------------------------------------------------------------
# Erlang 代码生成
# ----------------------------------------------------------------------------

def _preprocess_erlang_body(body: str, auto_signature: bool) -> str:
    """预处理 Erlang 函数体"""
    if not auto_signature:
        return body

    indented_lines = []
    for raw_line in body.split('\n'):
        line = raw_line.rstrip()
        if not line:
            indented_lines.append('')
            continue
        indented_lines.append('    ' + line)

    while indented_lines and not indented_lines[0]:
        indented_lines.pop(0)
    while indented_lines and not indented_lines[-1]:
        indented_lines.pop()

    return '\n'.join(indented_lines)


def _resolve_params_from_sig(sig: inspect.Signature) -> List[Tuple[str, str, bool]]:
    """从函数签名解析形参列表"""
    params = []
    for pname, param in sig.parameters.items():
        if param.annotation is not inspect.Parameter.empty:
            erl_t = get_erlang_type(param.annotation)
        else:
            erl_t = 'integer'
        is_arr = is_array_type(erl_t)
        params.append((pname, erl_t, is_arr))
    return params


def _generate_erlang_source(
    func_name: str,
    params: List[Tuple[str, str, bool]],
    ret_erlang_type: str,
    body: str,
    module_code: str = '',
    dependencies: List[FunctionSpec] = None,
    auto_signature: bool = True,
) -> str:
    """
    生成完整 Erlang 模块源码

    参数：
        func_name: 函数名
        params: 形参列表 [(name, erlang_type, is_array), ...]
        ret_erlang_type: 返回类型
        body: 函数体代码
        module_code: 模块级代码
        dependencies: 依赖函数规格列表
        auto_signature: 是否自动缩进函数体

    返回：
        完整 Erlang 模块源码字符串
    """
    # 参数名（Erlang 变量首字母大写）
    erl_params = []
    for name, erl_t, is_arr in params:
        var_name = name[0].upper() + name[1:] if name else 'Arg'
        erl_params.append(var_name)

    params_str = ', '.join(erl_params) if erl_params else ''
    arity = len(erl_params)

    # 缩进函数体，并去掉末尾可能存在的 '.'
    indented_body = _preprocess_erlang_body(body, auto_signature)
    if indented_body:
        indented_body = '\n' + indented_body.rstrip('.').rstrip() + '\n'
    else:
        indented_body = '\n'

    # 依赖函数
    dep_code = ''
    dep_exports = []
    if dependencies:
        dep_parts = []
        for dep in dependencies:
            dep_params = []
            for name in dep.annotations:
                if name == 'return':
                    continue
                var_name = name[0].upper() + name[1:] if name else 'Arg'
                dep_params.append(var_name)
            dep_params_str = ', '.join(dep_params) if dep_params else ''
            dep_arity = len(dep_params)
            dep_body = _preprocess_erlang_body(dep.body, True).rstrip('.').rstrip()
            dep_parts.append(
                f'{dep.name}({dep_params_str}) ->\n{dep_body}.'
            )
            dep_exports.append(f'{dep.name}/{dep_arity}')
        dep_code = '\n\n' + '\n\n'.join(dep_parts) + '\n'

    exports = [f'{func_name}/{arity}'] + dep_exports
    export_line = '-export([' + ', '.join(exports) + ']).'

    # 模块级代码
    module_code_section = ''
    if module_code:
        module_code_section = '\n' + module_code + '\n'

    code = f'''-module(%%MODULE_NAME%%).
{export_line}

{func_name}({params_str}) ->{indented_body}.
{dep_code}{module_code_section}
'''
    return code


# ----------------------------------------------------------------------------
# 异步执行
# ----------------------------------------------------------------------------

_executor = ThreadPoolExecutor(max_workers=4)


class ErlangFuture:
    """Erlang 异步执行 Future"""

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
        return asyncio.wrap_future(self._future).__await__()


# ----------------------------------------------------------------------------
# 缓存
# ----------------------------------------------------------------------------

_beam_cache = {}
_cache_lock = threading.Lock()


def _get_cached_beam(func_name: str, code: str, force: bool = False) -> str:
    """获取缓存的 beam 路径，必要时重新编译"""
    with _cache_lock:
        cached = _beam_cache.get(func_name)
        if not force and cached and cached[0] == code and os.path.exists(cached[1]):
            return cached[1]
        beam_path = _compile_erlang_code(code, func_name, _ERLANG_CACHE_DIR, force=force)
        _beam_cache[func_name] = (code, beam_path)
        return beam_path


def _remove_cached_beam(func_name: str) -> None:
    """移除缓存的 beam"""
    with _cache_lock:
        cached = _beam_cache.pop(func_name, None)
        if cached:
            beam_path = cached[1]
            try:
                if os.path.exists(beam_path):
                    os.remove(beam_path)
                src_path = beam_path[:-5] + '.erl'
                if os.path.exists(src_path):
                    os.remove(src_path)
            except OSError:
                pass


# ----------------------------------------------------------------------------
# 便捷入口
# ----------------------------------------------------------------------------

def compile_and_run(
    erlang_code: str,
    func_name: str = 'main',
    args: tuple = (),
    ret_type: str = 'integer',
    cache_dir: str = None,
):
    """直接编译并运行一段 Erlang 源码（无装饰器）"""
    actual_cache_dir = cache_dir or _ERLANG_CACHE_DIR
    os.makedirs(actual_cache_dir, exist_ok=True)

    param_erlang_types = infer_erlang_argtypes(args)
    beam_path = _compile_erlang_code(erlang_code, func_name, actual_cache_dir)
    return _call_erlang_function(beam_path, func_name, args, param_erlang_types, ret_type)


def is_erlang_available() -> bool:
    """检查 Erlang 桥接是否可用"""
    return erlang_compiler_available()


# ----------------------------------------------------------------------------
# ErlangBridge - 继承 LangBridge
# ----------------------------------------------------------------------------

class ErlangBridge(LangBridge):
    """Erlang 语言桥接实现"""

    name = 'erlang'
    file_ext = '.erl'
    lib_ext = '.beam'
    lang_type = LangType.BEAM

    def compiler_available(self) -> bool:
        """编译器是否可用"""
        return erlang_compiler_available()

    def generate_code(self, spec: FunctionSpec) -> str:
        """根据函数规格生成 Erlang 代码"""
        params = []
        for name, ann in spec.annotations.items():
            if name == 'return':
                continue
            erl_t = get_erlang_type(ann) if ann is not None else 'integer'
            is_arr = is_array_type(erl_t)
            params.append((name, erl_t, is_arr))

        ret_type = 'integer'
        if 'return' in spec.annotations and spec.annotations['return'] is not None:
            ret_type = get_erlang_type(spec.annotations['return'])

        return _generate_erlang_source(
            func_name=spec.name,
            params=params,
            ret_erlang_type=ret_type,
            body=spec.body,
            module_code=spec.module_code,
            dependencies=spec.dependencies,
        )

    def get_cache_key(self, code: str, func_name: str) -> str:
        """生成与 Erlang 模块名一致的缓存键（使用 code 前 12 位 MD5）"""
        code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
        return f'vools_erlang_{func_name}_{code_hash}'

    def get_lib_filename(self, cache_key: str) -> str:
        """缓存文件名即 Erlang 模块 beam 文件名"""
        return f'{cache_key}.beam'

    def compile_code(self, code: str, func_name: str, cache_dir: str = None) -> str:
        """编译 Erlang 代码"""
        return _compile_erlang_code(code, func_name, cache_dir)

    def compile_project(self, project_dir: str, entry: str, output_dir: str = None) -> str:
        """编译 Erlang 项目"""
        raise NotImplementedError("Erlang project compilation not yet implemented")

    def call_func(self, lib_path: str, func_name: str,
                  args: tuple, ret_type=None) -> Any:
        """调用 Erlang 编译的函数"""
        param_erlang_types = []
        for arg in args:
            if isinstance(arg, bool):
                param_erlang_types.append('boolean')
            elif isinstance(arg, int):
                param_erlang_types.append('integer')
            elif isinstance(arg, float):
                param_erlang_types.append('float')
            elif isinstance(arg, str):
                param_erlang_types.append('binary')
            elif isinstance(arg, (bytes, bytearray, list, tuple)):
                param_erlang_types.append('list')
            else:
                param_erlang_types.append('binary')

        erl_ret_type = get_erlang_type(ret_type) if ret_type else 'integer'
        return _call_erlang_function(lib_path, func_name, args, param_erlang_types, erl_ret_type)


# 全局实例
_erlang_bridge = ErlangBridge()
erlang = _erlang_bridge.decorator
