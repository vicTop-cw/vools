"""
vools.bridge.haskell.compiler - Haskell 语言桥接编译器实现

提供 Haskell 动态编译与跨语言桥接能力，对齐 vools.bridge.go 的 API 形态。

实现策略：
- 通过 GHC 将 Haskell 源码编译为可执行文件
- 主函数从 stdin 读取参数元组，使用 read 解析后调用目标函数
- 结果通过 print / show 输出，Python 端解析 stdout
"""

import os
import sys
import re
import ast
import tempfile
import hashlib
import platform
import asyncio
import inspect
import functools
import threading
import ctypes
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
_haskell_helper = get_helper('haskell')


def _setup_haskell_env() -> str:
    """设置 Haskell 运行环境（PATH）；返回 ghc 可执行路径"""
    _haskell_helper.setup_env()
    return _haskell_helper.get_compiler_path() or 'ghc'


def _get_ghc_path() -> str:
    """获取 ghc 编译器路径"""
    return _haskell_helper.get_compiler_path() or 'ghc'


def _get_runghc_path() -> str:
    """获取 runghc 可执行路径"""
    return _find_executable('runghc') or 'runghc'


# 初始化环境
_GHC_PATH = _setup_haskell_env()
_RUNGHC_PATH = _get_runghc_path()


def haskell_compiler_available() -> bool:
    """检查 Haskell 编译器是否可用"""
    return _haskell_helper.is_available()


# ----------------------------------------------------------------------------
# 编译缓存目录
# ----------------------------------------------------------------------------
_HASKELL_CACHE_DIR = os.path.join(tempfile.gettempdir(), 'vools_haskell_cache')


# ----------------------------------------------------------------------------
# Python ↔ Haskell 类型映射
# ----------------------------------------------------------------------------

# Python 类型 → Haskell 类型字符串
# 注：list / tuple 使用 [Int] / (Int, Int) 作为默认具体类型，
# 避免 GHC 在 read 时出现无法解析的类型变量。
# 需要其他元素类型时请在 Python 端使用 list[float] / list[str] 等注解。
PY_TO_HASKELL_TYPE = {
    int: 'Int',
    float: 'Double',
    bool: 'Bool',
    str: 'String',
    bytes: 'String',
    bytearray: 'String',
    list: '[Int]',
    tuple: '(Int, Int)',
    type(None): '()',
}

_HASKELL_TYPE_ALIASES = {
    'int': 'Int',
    'integer': 'Integer',
    'float': 'Double',
    'double': 'Double',
    'bool': 'Bool',
    'boolean': 'Bool',
    'str': 'String',
    'string': 'String',
    'binary': 'String',
    'bytes': 'String',
    'list': '[Int]',
    'tuple': '(Int, Int)',
    'array': '[Int]',
    'none': '()',
    'void': '()',
}


def get_haskell_type(py_type):
    """根据 Python 类型获取 Haskell 类型字符串"""
    if py_type is None or py_type is type(None):
        return '()'
    if py_type in PY_TO_HASKELL_TYPE:
        return PY_TO_HASKELL_TYPE[py_type]
    if isinstance(py_type, str):
        normalized = py_type.strip().lower()
        if normalized.startswith('list[') or normalized.startswith('array['):
            inner = normalized[5:-1].strip()
            inner_type = _HASKELL_TYPE_ALIASES.get(inner, 'a')
            return f'[{inner_type}]'
        if normalized.startswith('tuple['):
            return '(a, b)'
        if normalized in _HASKELL_TYPE_ALIASES:
            return _HASKELL_TYPE_ALIASES[normalized]
        short = normalized.split('.')[-1]
        if short in _HASKELL_TYPE_ALIASES:
            return _HASKELL_TYPE_ALIASES[short]
        return 'Int'
    return 'Int'


def _infer_list_type(arg):
    """根据列表/元组第一个元素推断 Haskell 列表类型"""
    if not arg:
        return '[String]'
    first = arg[0]
    if isinstance(first, bool):
        return '[Bool]'
    if isinstance(first, int):
        return '[Int]'
    if isinstance(first, float):
        return '[Double]'
    if isinstance(first, str):
        return '[String]'
    return '[String]'


def infer_haskell_argtypes(args):
    """根据运行时值推断 Haskell 入参类型"""
    result = []
    for arg in args:
        if isinstance(arg, bool):
            result.append('Bool')
        elif isinstance(arg, int):
            result.append('Int')
        elif isinstance(arg, float):
            result.append('Double')
        elif isinstance(arg, str):
            result.append('String')
        elif isinstance(arg, (bytes, bytearray)):
            result.append('String')
        elif isinstance(arg, list):
            result.append(_infer_list_type(arg))
        elif isinstance(arg, tuple):
            result.append(_infer_list_type(arg))
        else:
            result.append('String')
    return result


def is_array_type(haskell_type: str) -> bool:
    """判断 Haskell 入参类型是否为数组/列表"""
    return haskell_type.startswith('[')


# Haskell 类型 → ctypes 类型（预留）
HASKELL_TO_CTYPES = {
    'Int': ctypes.c_int64,
    'Integer': ctypes.c_int64,
    'Double': ctypes.c_double,
    'Bool': ctypes.c_bool,
    'String': ctypes.c_char_p,
    '[a]': ctypes.c_void_p,
    '(a, b)': ctypes.c_void_p,
    '()': None,
}


def get_ctype_for(haskell_type: str):
    """根据 Haskell 类型获取 ctypes 类型"""
    return HASKELL_TO_CTYPES.get(haskell_type, ctypes.c_int64)


# ----------------------------------------------------------------------------
# 编译与执行
# ----------------------------------------------------------------------------

_EXE_EXT = '.exe' if _IS_WINDOWS else ''


def _compile_haskell_code(code: str, func_name: str, cache_dir: str = None,
                          force: bool = False) -> str:
    """
    编译 Haskell 代码并返回可执行文件路径

    参数：
        code: 完整 Haskell 模块源码
        func_name: 函数名（用于生成文件名）
        cache_dir: 缓存目录
        force: 强制重新编译

    返回：
        可执行文件绝对路径
    """
    if cache_dir is None:
        cache_dir = _HASKELL_CACHE_DIR

    os.makedirs(cache_dir, exist_ok=True)

    code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
    module_name = f'vools_haskell_{func_name}_{code_hash}'
    # Haskell 模块名首字母必须大写，只能使用字母数字下划线
    module_name = re.sub(r'[^a-zA-Z0-9_]', '_', module_name)
    module_name = module_name[0].upper() + module_name[1:]

    src_path = os.path.join(cache_dir, f'{module_name}.hs')
    exe_path = os.path.join(cache_dir, f'{module_name}{_EXE_EXT}')

    if not force and os.path.exists(exe_path):
        return exe_path

    # 将模块名替换进代码
    final_code = code.replace('%%MODULE_NAME%%', module_name)

    with open(src_path, 'w', encoding='utf-8') as f:
        f.write(final_code)

    compile_cmd = [_GHC_PATH, '-O2', '-o', exe_path, src_path]
    result = subprocess.run(
        compile_cmd,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=120,
    )

    stderr = result.stderr.decode('utf-8', errors='replace') if result.stderr else ''
    stdout = result.stdout.decode('utf-8', errors='replace') if result.stdout else ''

    if result.returncode != 0 or not os.path.exists(exe_path):
        raise RuntimeError(
            f'Haskell 编译失败:\n'
            f'stderr:\n{stderr}\n'
            f'stdout:\n{stdout}\n'
            f'代码:\n{final_code}'
        )

    return exe_path


def _serialize_arg(arg, hs_type: str) -> str:
    """将 Python 参数序列化为 Haskell 字面量"""
    if hs_type == 'Bool':
        return 'True' if arg else 'False'
    if hs_type == 'Double':
        return repr(float(arg))
    if hs_type == 'Int' or hs_type == 'Integer':
        return str(int(arg))
    if hs_type == 'String':
        return _escape_haskell_string(str(arg))
    if hs_type.startswith('['):
        if not arg:
            return '[]'
        # 根据第一个元素推断列表元素类型
        first = arg[0]
        if isinstance(first, bool):
            elem_type = 'Bool'
        elif isinstance(first, int):
            elem_type = 'Int'
        elif isinstance(first, float):
            elem_type = 'Double'
        elif isinstance(first, str):
            elem_type = 'String'
        else:
            elem_type = 'String'
        items = [_serialize_arg(x, elem_type) for x in arg]
        return f'[{", ".join(items)}]'
    return str(arg)


def _escape_haskell_string(s: str) -> str:
    """转义 Haskell 字符串字面量"""
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t') + '"'


def _build_args_tuple(args: tuple, param_types: List[str]) -> str:
    """构建 Haskell 可 read 的参数元组字符串"""
    if len(args) == 0:
        return ''
    if len(args) == 1:
        return _serialize_arg(args[0], param_types[0])
    parts = [_serialize_arg(arg, hs_t) for arg, hs_t in zip(args, param_types)]
    return f'({", ".join(parts)})'


def _call_haskell_function(exe_path: str, func_name: str, args: tuple,
                           param_haskell_types: List, ret_haskell_type: str):
    """
    调用 Haskell 编译的函数

    通过 stdin 传递参数元组，从 stdout 解析结果
    """
    args_input = _build_args_tuple(args, param_haskell_types)

    result = subprocess.run(
        [exe_path],
        input=args_input,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=30,
        text=True,
    )

    stderr = result.stderr or ''
    stdout = result.stdout or ''

    if result.returncode != 0:
        raise RuntimeError(
            f'Haskell 执行失败:\n'
            f'stderr:\n{stderr}\n'
            f'stdout:\n{stdout}\n'
            f'输入: {args_input}'
        )

    output = stdout.strip()
    if not output:
        return None

    return _parse_haskell_output(output, ret_haskell_type)


def _parse_haskell_output(output: str, ret_type: str):
    """解析 Haskell 输出为 Python 类型"""
    output = output.strip()
    lines = [l.strip() for l in output.split('\n') if l.strip()]
    if not lines:
        return None
    value = lines[-1]

    if ret_type == 'Bool':
        return value == 'True'

    if ret_type == 'Double':
        try:
            return float(value)
        except ValueError:
            return value

    if ret_type in ('Int', 'Integer'):
        try:
            return int(value)
        except ValueError:
            return value

    if ret_type == 'String':
        if value.startswith('"') and value.endswith('"'):
            return _unescape_haskell_string(value[1:-1])
        return value

    # 自动推断
    return _parse_haskell_value(value)


def _parse_haskell_value(value: str):
    """自动解析 Haskell 值"""
    value = value.strip()

    if value == 'True':
        return True
    if value == 'False':
        return False
    if value == '()':
        return None

    # 字符串
    if value.startswith('"') and value.endswith('"'):
        return _unescape_haskell_string(value[1:-1])

    # 列表
    if value.startswith('[') and value.endswith(']'):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_haskell_value(x) for x in _split_haskell_list(inner)]

    # 元组
    if value.startswith('(') and value.endswith(')'):
        inner = value[1:-1].strip()
        items = _split_haskell_list(inner)
        return tuple(_parse_haskell_value(x) for x in items)

    # 数字
    try:
        if '.' in value or 'e' in value.lower():
            return float(value)
        return int(value)
    except ValueError:
        pass

    return value


def _split_haskell_list(s: str) -> List[str]:
    """简单分割 Haskell 列表/元组元素"""
    items = []
    depth = 0
    in_string = False
    escape = False
    current = ''
    for char in s:
        if escape:
            current += '\\' + char
            escape = False
            continue
        if char == '\\':
            escape = True
            current += char
            continue
        if char == '"':
            in_string = not in_string
            current += char
            continue
        if in_string:
            current += char
            continue
        if char in '[({':
            depth += 1
            current += char
        elif char in '])}':
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


def _unescape_haskell_string(s: str) -> str:
    """反转义 Haskell 字符串字面量"""
    result = []
    i = 0
    while i < len(s):
        if s[i] == '\\' and i + 1 < len(s):
            nxt = s[i + 1]
            if nxt == 'n':
                result.append('\n')
            elif nxt == 'r':
                result.append('\r')
            elif nxt == 't':
                result.append('\t')
            elif nxt == '\\':
                result.append('\\')
            elif nxt == '"':
                result.append('"')
            else:
                result.append(nxt)
            i += 2
        else:
            result.append(s[i])
            i += 1
    return ''.join(result)


# ----------------------------------------------------------------------------
# Haskell 代码生成
# ----------------------------------------------------------------------------

def _preprocess_haskell_body(body: str, auto_signature: bool) -> str:
    """预处理 Haskell 函数体"""
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
            hs_t = get_haskell_type(param.annotation)
        else:
            hs_t = 'Int'
        is_arr = is_array_type(hs_t)
        params.append((pname, hs_t, is_arr))
    return params


def _build_main_function(func_name: str, params: List[Tuple[str, str, bool]],
                         ret_haskell_type: str) -> str:
    """生成从 stdin 读取参数并调用目标函数的 main 函数"""
    arg_count = len(params)
    type_names = [p[1] for p in params]
    arg_names = [p[0] for p in params]

    if arg_count == 0:
        return f'''main = print ({func_name})'''

    if arg_count == 1:
        hs_type = type_names[0]
        return f'''main = do
    input <- getContents
    let arg = read input :: {hs_type}
    print ({func_name} arg)'''

    tuple_types = ', '.join(type_names)
    pattern = '(' + ', '.join(arg_names) + ')'
    args_call = ' '.join(arg_names)
    return f'''main = do
    input <- getContents
    let {pattern} = read input :: ({tuple_types})
    print ({func_name} {args_call})'''


def _generate_haskell_source(
    func_name: str,
    params: List[Tuple[str, str, bool]],
    ret_haskell_type: str,
    body: str,
    module_code: str = '',
    dependencies: List[FunctionSpec] = None,
    auto_signature: bool = True,
) -> str:
    """生成完整 Haskell 模块源码"""
    # 函数参数列表
    hs_params = []
    for name, hs_t, is_arr in params:
        hs_params.append(name)
    params_str = ' '.join(hs_params) if hs_params else ''

    indented_body = _preprocess_haskell_body(body, auto_signature)
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
            dep_params_str = ' '.join(dep_params) if dep_params else ''
            dep_body = _preprocess_haskell_body(dep.body, True)
            if dep_params_str:
                dep_parts.append(
                    f'{dep.name} {dep_params_str} =\n{dep_body}'
                )
            else:
                dep_parts.append(
                    f'{dep.name} =\n{dep_body}'
                )
        dep_code = '\n\n' + '\n\n'.join(dep_parts) + '\n'

    main_func = _build_main_function(func_name, params, ret_haskell_type)

    module_code_section = ''
    if module_code:
        module_code_section = '\n' + module_code + '\n'

    code = f'''module Main where
{module_code_section}{dep_code}{func_name} {params_str} ={indented_body}

{main_func}
'''
    return code


# ----------------------------------------------------------------------------
# 异步执行
# ----------------------------------------------------------------------------

_executor = ThreadPoolExecutor(max_workers=4)


class HaskellFuture:
    """Haskell 异步执行 Future"""

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

_exe_cache = {}
_cache_lock = threading.Lock()


def _get_cached_exe(func_name: str, code: str, force: bool = False) -> str:
    """获取缓存的可执行文件路径，必要时重新编译"""
    with _cache_lock:
        cached = _exe_cache.get(func_name)
        if not force and cached and cached[0] == code and os.path.exists(cached[1]):
            return cached[1]
        exe_path = _compile_haskell_code(code, func_name, _HASKELL_CACHE_DIR, force=force)
        _exe_cache[func_name] = (code, exe_path)
        return exe_path


def _remove_cached_exe(func_name: str) -> None:
    """移除缓存的可执行文件"""
    with _cache_lock:
        cached = _exe_cache.pop(func_name, None)
        if cached:
            exe_path = cached[1]
            try:
                if os.path.exists(exe_path):
                    os.remove(exe_path)
                src_path = exe_path[:-4] + '.hs' if _IS_WINDOWS else exe_path + '.hs'
                if os.path.exists(src_path):
                    os.remove(src_path)
                # 清理 GHC 生成的中间文件
                base = exe_path[:-4] if _IS_WINDOWS else exe_path
                for ext in ('.hi', '.o'):
                    f = base + ext
                    if os.path.exists(f):
                        os.remove(f)
            except OSError:
                pass


# ----------------------------------------------------------------------------
# 便捷入口
# ----------------------------------------------------------------------------

def compile_and_run(
    haskell_code: str,
    func_name: str = 'main',
    args: tuple = (),
    ret_type: str = 'Int',
    cache_dir: str = None,
):
    """直接编译并运行一段 Haskell 源码（无装饰器）"""
    actual_cache_dir = cache_dir or _HASKELL_CACHE_DIR
    os.makedirs(actual_cache_dir, exist_ok=True)

    param_haskell_types = infer_haskell_argtypes(args)
    exe_path = _compile_haskell_code(haskell_code, func_name, actual_cache_dir)
    return _call_haskell_function(exe_path, func_name, args, param_haskell_types, ret_type)


def is_haskell_available() -> bool:
    """检查 Haskell 桥接是否可用"""
    return haskell_compiler_available()


# ----------------------------------------------------------------------------
# HaskellBridge - 继承 LangBridge
# ----------------------------------------------------------------------------

class HaskellBridge(LangBridge):
    """Haskell 语言桥接实现"""

    name = 'haskell'
    file_ext = '.hs'
    lib_ext = _EXE_EXT or ''

    def compiler_available(self) -> bool:
        """编译器是否可用"""
        return haskell_compiler_available()

    def generate_code(self, spec: FunctionSpec) -> str:
        """根据函数规格生成 Haskell 代码"""
        params = []
        for name, ann in spec.annotations.items():
            if name == 'return':
                continue
            hs_t = get_haskell_type(ann) if ann is not None else 'Int'
            is_arr = is_array_type(hs_t)
            params.append((name, hs_t, is_arr))

        ret_type = 'Int'
        if 'return' in spec.annotations and spec.annotations['return'] is not None:
            ret_type = get_haskell_type(spec.annotations['return'])

        return _generate_haskell_source(
            func_name=spec.name,
            params=params,
            ret_haskell_type=ret_type,
            body=spec.body,
            module_code=spec.module_code,
            dependencies=spec.dependencies,
        )

    def get_cache_key(self, code: str, func_name: str) -> str:
        """生成缓存键"""
        code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
        return f'vools_haskell_{func_name}_{code_hash}'

    def get_lib_filename(self, cache_key: str) -> str:
        """缓存文件名即可执行文件名"""
        return f'{cache_key}{_EXE_EXT}'

    def compile_code(self, code: str, func_name: str, cache_dir: str = None) -> str:
        """编译 Haskell 代码"""
        return _compile_haskell_code(code, func_name, cache_dir)

    def compile_project(self, project_dir: str, entry: str, output_dir: str = None) -> str:
        """编译 Haskell 项目"""
        raise NotImplementedError("Haskell project compilation not yet implemented")

    def call_func(self, lib_path: str, func_name: str,
                  args: tuple, ret_type=None) -> Any:
        """调用 Haskell 编译的函数"""
        param_haskell_types = infer_haskell_argtypes(args)
        hs_ret_type = get_haskell_type(ret_type) if ret_type else 'Int'
        return _call_haskell_function(lib_path, func_name, args, param_haskell_types, hs_ret_type)


# 全局实例
_haskell_bridge = HaskellBridge()
haskell = _haskell_bridge.decorator
