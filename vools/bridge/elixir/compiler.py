"""
vools.bridge.elixir.compiler - Elixir 语言桥接编译器实现

提供 Elixir 动态编译与跨语言桥接能力，对齐 vools.bridge.go 的 API 形态。

实现策略：
- Elixir 通过 elixirc 编译模块为 .beam，然后通过 elixir 执行
- 使用临时模块和输出解析返回结果
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
from ..manager import get_helper, _find_executable

# ----------------------------------------------------------------------------
# 平台判断
# ----------------------------------------------------------------------------
_IS_WINDOWS = platform.system() == 'Windows'
_IS_LINUX = platform.system() == 'Linux'
_IS_MACOS = platform.system() == 'Darwin'

# 使用 manager 的编译器辅助
_elixir_helper = get_helper('elixir')


def _setup_elixir_env() -> str:
    """设置 Elixir 运行环境（PATH）；返回 elixirc 可执行路径"""
    _elixir_helper.setup_env()
    return _elixir_helper.get_compiler_path() or 'elixirc'


def _get_elixirc_path() -> str:
    """获取 elixirc 编译器路径"""
    return _elixir_helper.get_compiler_path() or 'elixirc'


def _get_elixir_path() -> str:
    """获取 elixir 运行时可执行路径"""
    # 在 PATH 和已配置路径中查找 elixir（支持 .bat/.cmd）
    return _find_executable('elixir') or 'elixir'


# 初始化环境
_ELIXIRC_PATH = _setup_elixir_env()
_ELIXIR_PATH = _get_elixir_path()


def elixir_compiler_available() -> bool:
    """检查 Elixir 编译器是否可用"""
    return _elixir_helper.is_available()


# ----------------------------------------------------------------------------
# 编译缓存目录
# ----------------------------------------------------------------------------
_ELIXIR_CACHE_DIR = os.path.join(tempfile.gettempdir(), 'vools_elixir_cache')


# ----------------------------------------------------------------------------
# Python ↔ Elixir 类型映射
# ----------------------------------------------------------------------------

# Python 类型 → Elixir 类型字符串
PY_TO_ELIXIR_TYPE = {
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

_ELIXIR_TYPE_ALIASES = {
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


def get_elixir_type(py_type):
    """根据 Python 类型获取 Elixir 类型字符串"""
    if py_type is None or py_type is type(None):
        return 'none'
    if py_type in PY_TO_ELIXIR_TYPE:
        return PY_TO_ELIXIR_TYPE[py_type]
    if isinstance(py_type, str):
        normalized = py_type.strip().lower()
        if normalized.startswith('list[') or normalized.startswith('array['):
            return 'list'
        if normalized in _ELIXIR_TYPE_ALIASES:
            return _ELIXIR_TYPE_ALIASES[normalized]
        short = normalized.split('.')[-1]
        if short in _ELIXIR_TYPE_ALIASES:
            return _ELIXIR_TYPE_ALIASES[short]
        return 'integer'
    return 'integer'


def infer_elixir_argtypes(args):
    """根据运行时值推断 Elixir 入参类型"""
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


def is_array_type(elixir_type: str) -> bool:
    """判断 Elixir 入参类型是否为数组/列表"""
    return elixir_type == 'list'


# Elixir 类型 → ctypes 类型
ELIXIR_TO_CTYPES = {
    'integer': ctypes.c_int64,
    'float': ctypes.c_double,
    'boolean': ctypes.c_bool,
    'binary': ctypes.c_char_p,
    'list': ctypes.c_void_p,
    'tuple': ctypes.c_void_p,
    'none': None,
}


def get_ctype_for(elixir_type: str):
    """根据 Elixir 类型获取 ctypes 类型"""
    return ELIXIR_TO_CTYPES.get(elixir_type, ctypes.c_int64)


# ----------------------------------------------------------------------------
# 编译与执行
# ----------------------------------------------------------------------------

def _compile_elixir_code(code: str, func_name: str, cache_dir: str = None,
                         force: bool = False) -> str:
    """
    编译 Elixir 代码并返回模块路径

    参数：
        code: 完整 Elixir 模块源码
        func_name: 函数名（用于生成文件名）
        cache_dir: 缓存目录
        force: 强制重新编译

    返回：
        .beam 文件绝对路径
    """
    if cache_dir is None:
        cache_dir = _ELIXIR_CACHE_DIR

    os.makedirs(cache_dir, exist_ok=True)

    code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
    module_name = f'VoolsElixir{func_name.title()}_{code_hash}'
    # Elixir 模块名必须是有效的 atom，只能使用字母数字和下划线
    module_name = re.sub(r'[^a-zA-Z0-9_]', '_', module_name)

    src_path = os.path.join(cache_dir, f'{module_name}.ex')
    beam_path = os.path.join(cache_dir, f'Elixir.{module_name}.beam')

    if not force and os.path.exists(beam_path):
        return beam_path

    # 将模块名替换进代码
    final_code = code.replace('%%MODULE_NAME%%', module_name)

    with open(src_path, 'w', encoding='utf-8') as f:
        f.write(final_code)

    compile_cmd = [_ELIXIRC_PATH, '--ignore-module-conflict', '-o', cache_dir, src_path]
    result = subprocess.run(
        compile_cmd,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=60,
    )

    stderr = result.stderr.decode('utf-8', errors='replace') if result.stderr else ''
    stdout = result.stdout.decode('utf-8', errors='replace') if result.stdout else ''

    if result.returncode != 0 or not os.path.exists(beam_path):
        raise RuntimeError(
            f'Elixir 编译失败:\n'
            f'stderr:\n{stderr}\n'
            f'stdout:\n{stdout}\n'
            f'代码:\n{final_code}'
        )

    return beam_path


def _call_elixir_function(beam_path: str, func_name: str, args: tuple,
                          param_elixir_types: List, ret_elixir_type: str):
    """
    调用 Elixir 编译的函数

    通过 elixir 执行调用并解析输出
    """
    cache_dir = os.path.dirname(beam_path)
    # beam 文件名: Elixir.ModuleName.beam
    base_name = os.path.splitext(os.path.basename(beam_path))[0]
    if base_name.startswith('Elixir.'):
        module_name = base_name[7:]
    else:
        module_name = base_name

    # 构建 Elixir 调用表达式
    ex_args = []
    for i, (arg, ex_t) in enumerate(zip(args, param_elixir_types)):
        if ex_t == 'integer':
            ex_args.append(str(int(arg)))
        elif ex_t == 'float':
            ex_args.append(str(float(arg)))
        elif ex_t == 'boolean':
            ex_args.append('true' if arg else 'false')
        elif ex_t == 'binary':
            ex_args.append(f'"{str(arg)}"')
        elif ex_t == 'list':
            if arg and isinstance(arg[0], int):
                items = ','.join(str(x) for x in arg)
                ex_args.append(f'[{items}]')
            elif arg and isinstance(arg[0], float):
                items = ','.join(str(x) for x in arg)
                ex_args.append(f'[{items}]')
            elif arg and isinstance(arg[0], str):
                items = ','.join(f'"{x}"' for x in arg)
                ex_args.append(f'[{items}]')
            else:
                ex_args.append('[]')
        else:
            ex_args.append(str(arg))

    call_expr = f'{module_name}.{func_name}({", ".join(ex_args)})'

    # 构建 elixir 脚本：直接输出可解析的 ~p 格式
    script_code = f'''
Code.append_path("{cache_dir.replace("\\", "/")}")
result = {call_expr}
:io.format("~p~n", [result])
'''

    script_path = os.path.join(cache_dir, f'run_{uuid.uuid4().hex[:8]}.exs')
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(script_code)

    cmd = [_ELIXIR_PATH, script_path]
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=30,
    )

    stderr = result.stderr.decode('utf-8', errors='replace') if result.stderr else ''
    stdout = result.stdout.decode('utf-8', errors='replace') if result.stdout else ''

    # 清理临时脚本
    try:
        if os.path.exists(script_path):
            os.remove(script_path)
    except OSError:
        pass

    if result.returncode != 0:
        raise RuntimeError(
            f'Elixir 执行失败:\n'
            f'stderr:\n{stderr}\n'
            f'stdout:\n{stdout}'
        )

    output = stdout.strip()
    if not output:
        return None

    lines = [l.strip() for l in stdout.split('\n') if l.strip()]
    if lines:
        return _parse_elixir_output(lines[-1], ret_elixir_type)
    return None


def _parse_elixir_output(output: str, ret_type: str):
    """解析 Elixir 输出为 Python 类型"""
    output = output.strip()
    lines = [l.strip() for l in output.split('\n') if l.strip()]
    if not lines:
        return None
    value = lines[-1]

    if ret_type == 'boolean':
        return value == 'true'

    if ret_type == 'binary':
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
        if value.startswith('[') and value.endswith(']'):
            inner = value[1:-1].strip()
            if not inner:
                return []
            return [_parse_elixir_value(x) for x in _split_elixir_list(inner)]
        return value

    return _parse_elixir_value(value)


def _split_elixir_list(s: str) -> List[str]:
    """简单分割 Elixir 列表元素"""
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


def _parse_elixir_value(value: str):
    """自动解析 Elixir 值"""
    value = value.strip()

    if value == 'true':
        return True
    if value == 'false':
        return False
    if value == 'nil':
        return None
    if value == 'ok':
        return None

    if value.startswith('[') and value.endswith(']'):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_elixir_value(x) for x in _split_elixir_list(inner)]

    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]

    if value.startswith('{') and value.endswith('}'):
        inner = value[1:-1].strip()
        items = _split_elixir_list(inner)
        return tuple(_parse_elixir_value(x) for x in items)

    try:
        if '.' in value:
            return float(value)
        return int(value)
    except ValueError:
        pass

    return value


# ----------------------------------------------------------------------------
# Elixir 代码生成
# ----------------------------------------------------------------------------

def _preprocess_elixir_body(body: str, auto_signature: bool) -> str:
    """预处理 Elixir 函数体"""
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
            ex_t = get_elixir_type(param.annotation)
        else:
            ex_t = 'integer'
        is_arr = is_array_type(ex_t)
        params.append((pname, ex_t, is_arr))
    return params


def _generate_elixir_source(
    func_name: str,
    params: List[Tuple[str, str, bool]],
    ret_elixir_type: str,
    body: str,
    module_code: str = '',
    dependencies: List[FunctionSpec] = None,
    auto_signature: bool = True,
) -> str:
    """生成完整 Elixir 模块源码"""
    ex_params = []
    for name, ex_t, is_arr in params:
        ex_params.append(name)

    params_str = ', '.join(ex_params) if ex_params else ''

    indented_body = _preprocess_elixir_body(body, auto_signature)
    if indented_body:
        indented_body = '\n' + indented_body + '\n'
    else:
        indented_body = '\n'

    # 依赖函数
    dep_code = ''
    if dependencies:
        dep_parts = []
        for dep in dependencies:
            dep_params = [name for name in dep.annotations if name != 'return']
            dep_params_str = ', '.join(dep_params) if dep_params else ''
            dep_body = _preprocess_elixir_body(dep.body, True)
            dep_parts.append(
                f'  def {dep.name}({dep_params_str}) do\n{dep_body}\n  end'
            )
        dep_code = '\n\n' + '\n\n'.join(dep_parts) + '\n'

    module_code_section = ''
    if module_code:
        module_code_section = '\n  ' + module_code.replace('\n', '\n  ') + '\n'

    code = f'''defmodule %%MODULE_NAME%% do
{module_code_section}{dep_code}  def {func_name}({params_str}) do{indented_body}  end
end
'''
    return code


# ----------------------------------------------------------------------------
# 异步执行
# ----------------------------------------------------------------------------

_executor = ThreadPoolExecutor(max_workers=4)


class ElixirFuture:
    """Elixir 异步执行 Future"""

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
        beam_path = _compile_elixir_code(code, func_name, _ELIXIR_CACHE_DIR, force=force)
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
                src_path = beam_path.replace('Elixir.', '').replace('.beam', '.ex')
                if os.path.exists(src_path):
                    os.remove(src_path)
            except OSError:
                pass


# ----------------------------------------------------------------------------
# 便捷入口
# ----------------------------------------------------------------------------

def compile_and_run(
    elixir_code: str,
    func_name: str = 'main',
    args: tuple = (),
    ret_type: str = 'integer',
    cache_dir: str = None,
):
    """直接编译并运行一段 Elixir 源码（无装饰器）"""
    actual_cache_dir = cache_dir or _ELIXIR_CACHE_DIR
    os.makedirs(actual_cache_dir, exist_ok=True)

    param_elixir_types = infer_elixir_argtypes(args)
    beam_path = _compile_elixir_code(elixir_code, func_name, actual_cache_dir)
    return _call_elixir_function(beam_path, func_name, args, param_elixir_types, ret_type)


def is_elixir_available() -> bool:
    """检查 Elixir 桥接是否可用"""
    return elixir_compiler_available()


# ----------------------------------------------------------------------------
# ElixirBridge - 继承 LangBridge
# ----------------------------------------------------------------------------

class ElixirBridge(LangBridge):
    """Elixir 语言桥接实现"""

    name = 'elixir'
    file_ext = '.ex'
    lib_ext = '.beam'

    def compiler_available(self) -> bool:
        """编译器是否可用"""
        return elixir_compiler_available()

    def generate_code(self, spec: FunctionSpec) -> str:
        """根据函数规格生成 Elixir 代码"""
        params = []
        for name, ann in spec.annotations.items():
            if name == 'return':
                continue
            ex_t = get_elixir_type(ann) if ann is not None else 'integer'
            is_arr = is_array_type(ex_t)
            params.append((name, ex_t, is_arr))

        ret_type = 'integer'
        if 'return' in spec.annotations and spec.annotations['return'] is not None:
            ret_type = get_elixir_type(spec.annotations['return'])

        return _generate_elixir_source(
            func_name=spec.name,
            params=params,
            ret_elixir_type=ret_type,
            body=spec.body,
            module_code=spec.module_code,
            dependencies=spec.dependencies,
        )

    def get_cache_key(self, code: str, func_name: str) -> str:
        """生成与 Elixir 模块名一致的缓存键（使用 code 前 12 位 MD5）"""
        code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
        return f'VoolsElixir{func_name.title()}_{code_hash}'

    def get_lib_filename(self, cache_key: str) -> str:
        """缓存文件名即 Elixir 模块 beam 文件名"""
        return f'Elixir.{cache_key}.beam'

    def compile_code(self, code: str, func_name: str, cache_dir: str = None) -> str:
        """编译 Elixir 代码"""
        return _compile_elixir_code(code, func_name, cache_dir)

    def compile_project(self, project_dir: str, entry: str, output_dir: str = None) -> str:
        """编译 Elixir 项目"""
        raise NotImplementedError("Elixir project compilation not yet implemented")

    def call_func(self, lib_path: str, func_name: str,
                  args: tuple, ret_type=None) -> Any:
        """调用 Elixir 编译的函数"""
        param_elixir_types = []
        for arg in args:
            if isinstance(arg, bool):
                param_elixir_types.append('boolean')
            elif isinstance(arg, int):
                param_elixir_types.append('integer')
            elif isinstance(arg, float):
                param_elixir_types.append('float')
            elif isinstance(arg, str):
                param_elixir_types.append('binary')
            elif isinstance(arg, (bytes, bytearray, list, tuple)):
                param_elixir_types.append('list')
            else:
                param_elixir_types.append('binary')

        ex_ret_type = get_elixir_type(ret_type) if ret_type else 'integer'
        return _call_elixir_function(lib_path, func_name, args, param_elixir_types, ex_ret_type)


# 全局实例
_elixir_bridge = ElixirBridge()
elixir = _elixir_bridge.decorator
