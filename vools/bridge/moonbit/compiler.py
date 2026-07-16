"""
vools.bridge.moonbit.compiler - MoonBit 语言桥接编译器实现

提供 MoonBit 动态编译与跨语言桥接能力，继承 LangBridge 抽象基类。

MoonBit 执行：
- moon run: 运行 MoonBit 包
- 参数通过硬编码到 main 函数的方式传递（当前方案）
- 未来可改进为通过环境变量/文件传递参数
"""

import os
import sys
import json
import tempfile
import hashlib
import platform
import subprocess
import textwrap
import logging
import shutil
import threading
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, List, Any

from .._base import LangBridge, FunctionSpec
from ..core.types import LangType, CompileMode

logger = logging.getLogger(__name__)

_IS_WINDOWS = platform.system() == 'Windows'
_IS_LINUX = platform.system() == 'Linux'
_IS_MACOS = platform.system() == 'Darwin'

_MOONBIT_CACHE_DIR = os.path.join(tempfile.gettempdir(), 'vools_moonbit_cache')


def _check_moonbit() -> bool:
    """检查本地是否有 moon 命令"""
    return shutil.which('moon') is not None


def _check_wsl() -> bool:
    """检查是否可以使用 WSL"""
    if not _IS_WINDOWS:
        return False
    try:
        result = subprocess.run(
            ['wsl', '--version'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _check_wsl_moonbit() -> bool:
    """检查 WSL 中是否有 moon"""
    try:
        result = subprocess.run(
            ['wsl', 'moon', '--version'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=10
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


_USE_WSL = _IS_WINDOWS and not _check_moonbit() and _check_wsl() and _check_wsl_moonbit()


def _to_wsl_path(windows_path: str) -> str:
    """将 Windows 路径转换为 WSL 路径"""
    if not os.path.isabs(windows_path):
        windows_path = os.path.abspath(windows_path)
    drive = windows_path[0].lower()
    rest = windows_path[2:].replace('\\', '/')
    return f'/mnt/{drive}{rest}'


def _find_moonbit() -> Optional[str]:
    """查找 moon 命令路径"""
    return shutil.which('moon')


def moonbit_compiler_available() -> bool:
    """检查 MoonBit 编译器是否可用"""
    if _check_moonbit():
        return True
    return _USE_WSL


def get_moonbit_version() -> Optional[str]:
    """获取 MoonBit 版本信息"""
    moon_path = _find_moonbit()
    if moon_path is None:
        if _USE_WSL:
            try:
                result = subprocess.run(
                    ['wsl', 'moon', '--version'],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    timeout=10,
                )
                return result.stdout.decode('utf-8', errors='replace').strip()
            except Exception:
                return None
        return None

    try:
        result = subprocess.run(
            ['moon', '--version'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=10,
        )
        return result.stdout.decode('utf-8', errors='replace').strip() or result.stderr.decode('utf-8', errors='replace').strip()
    except Exception:
        return None


# ----------------------------------------------------------------------------
# 异步执行
# ----------------------------------------------------------------------------

_executor = ThreadPoolExecutor(max_workers=4)


class MoonBitFuture:
    """MoonBit 异步执行 Future"""

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
# MoonBit 代码生成
# ----------------------------------------------------------------------------

def _escape_moonbit_string(s: str) -> str:
    """转义 MoonBit 字符串字面量"""
    return s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r')


def _format_moonbit_value(value: Any, moonbit_type: str) -> str:
    """将 Python 值格式化为 MoonBit 字面量"""
    if moonbit_type == 'Int':
        return str(int(value))
    elif moonbit_type == 'Double':
        return str(float(value))
    elif moonbit_type == 'Bool':
        return 'true' if bool(value) else 'false'
    else:
        return '"' + _escape_moonbit_string(str(value)) + '"'


def _generate_func_def_code(func_name: str, params: List[tuple], ret_moonbit_type: str,
                           body: str, module_code: str = '') -> str:
    """生成函数定义部分的代码（不含 main 函数）"""
    parts = []

    if module_code:
        parts.append(module_code)
        parts.append('')

    param_str = ', '.join([f'{name} : {ptype}' for name, ptype in params])
    func_def = f'fn {func_name}({param_str}) -> {ret_moonbit_type}'
    body = textwrap.dedent(body).strip() if body else ''
    parts.append(func_def + ' {')
    for line in body.split('\n'):
        if line.strip():
            parts.append('  ' + line)
    parts.append('}')

    return '\n'.join(parts)


def _generate_full_code(func_name: str, params: List[tuple], ret_moonbit_type: str,
                        body: str, module_code: str = '', args: tuple = ()) -> str:
    """生成完整的 MoonBit 代码（包含 main 函数，参数硬编码）"""
    func_def = _generate_func_def_code(func_name, params, ret_moonbit_type, body, module_code)
    
    parts = [func_def, '']
    parts.append('fn main {')
    
    arg_names = []
    for i, (pname, ptype) in enumerate(params):
        arg_names.append(pname)
        if i < len(args):
            val_str = _format_moonbit_value(args[i], ptype)
        else:
            if ptype == 'Int':
                val_str = '0'
            elif ptype == 'Double':
                val_str = '0.0'
            elif ptype == 'Bool':
                val_str = 'false'
            else:
                val_str = '""'
        parts.append(f'  let {pname} = {val_str}')
    
    if arg_names:
        call_str = f'  let result = {func_name}({", ".join(arg_names)})'
    else:
        call_str = f'  let result = {func_name}()'
    
    parts.append(call_str)
    
    if ret_moonbit_type == 'Bool':
        parts.append('  if result { println("true") } else { println("false") }')
    else:
        parts.append('  println(result)')
    
    parts.append('}')
    
    return '\n'.join(parts)


class MoonBitBridge(LangBridge):
    """MoonBit 语言桥接实现

    使用 moon run 执行 MoonBit 代码，参数硬编码到 main 函数中。
    缓存策略：基于函数定义（不含参数值）计算缓存键，同一个函数复用同一个项目目录，
    每次调用时重写 main.mbt 更新参数值。
    """

    name = 'moonbit'
    file_ext = '.mbt'
    lib_ext = ''
    lang_type = LangType.COMPILED

    def __init__(self):
        super().__init__()

    def compiler_available(self) -> bool:
        return moonbit_compiler_available()

    def default_cache_dir(self) -> str:
        """获取默认的编译缓存目录"""
        return _MOONBIT_CACHE_DIR

    def _get_func_def_and_types(self, spec: FunctionSpec):
        """从 FunctionSpec 获取函数定义代码、参数列表和返回类型"""
        from .types import get_moonbit_type

        params = []
        for name, ann in spec.annotations.items():
            if name == 'return':
                continue
            if ann is None:
                moonbit_type = 'String'
            else:
                moonbit_type = get_moonbit_type(ann)
            params.append((name, moonbit_type))

        ret_moonbit_type = 'String'
        if 'return' in spec.annotations:
            ann = spec.annotations['return']
            if ann is not type(None) and ann is not None:
                ret_moonbit_type = get_moonbit_type(ann)

        func_def_code = _generate_func_def_code(
            func_name=spec.name,
            params=params,
            ret_moonbit_type=ret_moonbit_type,
            body=spec.body,
            module_code=spec.module_code or '',
        )

        return func_def_code, params, ret_moonbit_type

    def generate_code(self, spec: FunctionSpec) -> str:
        """生成 MoonBit 代码（完整可运行代码，用于 only_code 模式）"""
        func_def_code, params, ret_moonbit_type = self._get_func_def_and_types(spec)
        return _generate_full_code(
            func_name=spec.name,
            params=params,
            ret_moonbit_type=ret_moonbit_type,
            body=spec.body,
            module_code=spec.module_code or '',
            args=spec.args,
        )

    def _create_moonbit_project(self, code: str, project_dir: str) -> None:
        """在指定目录创建 MoonBit 项目结构"""
        os.makedirs(project_dir, exist_ok=True)

        mbt_path = os.path.join(project_dir, 'main.mbt')
        with open(mbt_path, 'w', encoding='utf-8') as f:
            f.write(code)

        pkg_content = '''options(
  "is-main": true,
)
'''
        with open(os.path.join(project_dir, 'moon.pkg'), 'w') as f:
            f.write(pkg_content)

        with open(os.path.join(project_dir, 'moon.mod'), 'w') as f:
            f.write('name = "vools/moonbit_test"\n')
            f.write('version = "0.1.0"\n')

    def _get_or_create_project_dir(self, func_def_code: str, func_name: str,
                                    cache_dir: Optional[str] = None) -> str:
        """基于函数定义代码获取或创建缓存项目目录

        缓存键只基于函数定义（不含参数值），所以同一个函数的不同参数调用
        会复用同一个项目目录。
        """
        cache_dir = self.get_cache_dir(cache_dir)

        code_hash = hashlib.md5(func_def_code.encode('utf-8')).hexdigest()
        project_name = f'moonbit_{func_name}_{code_hash}'
        project_dir = os.path.join(cache_dir, project_name)

        if not os.path.exists(project_dir):
            dummy_code = func_def_code + '\n\nfn main {\n  println("init")\n}\n'
            self._create_moonbit_project(dummy_code, project_dir)

        return project_dir

    def compile_code(self, code: str, func_name: str, cache_dir: Optional[str] = None) -> str:
        """编译 MoonBit 代码（创建缓存项目目录）

        注意：为了兼容基类接口，这里使用完整代码计算缓存键。
        推荐使用 _get_or_create_project_dir 来获得更好的缓存复用。
        """
        cache_dir = self.get_cache_dir(cache_dir)

        code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()
        project_name = f'moonbit_{func_name}_{code_hash}'
        project_dir = os.path.join(cache_dir, project_name)

        if not os.path.exists(project_dir):
            self._create_moonbit_project(code, project_dir)

        return project_dir

    def _compile_with_cache(self, code: str, func_name: str,
                            cache_dir: Optional[str] = None) -> str:
        """带缓存的编译（重写基类方法）

        MoonBit 使用项目目录而非库文件，compile_code 已自带缓存逻辑，
        直接调用即可，无需基类的文件复制缓存机制。
        """
        return self.compile_code(code, func_name, cache_dir)

    def compile_project(self, project_dir: str, entry: str = 'main', output_dir: Optional[str] = None) -> str:
        """编译 MoonBit 项目"""
        return project_dir

    def _write_main_with_args(self, project_dir: str, func_def_code: str,
                              func_name: str, params: List[tuple],
                              ret_moonbit_type: str, args: tuple) -> None:
        """向项目目录写入包含特定参数的 main.mbt"""
        parts = [func_def_code, '', 'fn main {']
        
        arg_names = []
        for i, (pname, ptype) in enumerate(params):
            arg_names.append(pname)
            if i < len(args):
                val_str = _format_moonbit_value(args[i], ptype)
            else:
                if ptype == 'Int':
                    val_str = '0'
                elif ptype == 'Double':
                    val_str = '0.0'
                elif ptype == 'Bool':
                    val_str = 'false'
                else:
                    val_str = '""'
            parts.append(f'  let {pname} = {val_str}')
        
        if arg_names:
            call_str = f'  let result = {func_name}({", ".join(arg_names)})'
        else:
            call_str = f'  let result = {func_name}()'
        
        parts.append(call_str)
        
        if ret_moonbit_type == 'Bool':
            parts.append('  if result { println("true") } else { println("false") }')
        else:
            parts.append('  println(result)')
        
        parts.append('}')
        
        full_code = '\n'.join(parts)
        mbt_path = os.path.join(project_dir, 'main.mbt')
        with open(mbt_path, 'w', encoding='utf-8') as f:
            f.write(full_code)

    def call_func(self, lib_path: str, func_name: str,
                  args: tuple, ret_type: Optional[type] = None) -> Any:
        """调用 MoonBit 函数

        直接运行项目目录中的 MoonBit 代码，从 stdout 读取返回值。
        """
        if _USE_WSL:
            result = subprocess.run(
                ['wsl', 'moon', 'run', '.'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=60,
                cwd=lib_path,
            )
        else:
            result = subprocess.run(
                ['moon', 'run', '.'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=60,
                cwd=lib_path,
            )

        stdout = result.stdout.decode('utf-8', errors='replace')
        stderr = result.stderr.decode('utf-8', errors='replace')

        if result.returncode != 0:
            raise RuntimeError(
                f'MoonBit execution failed (code {result.returncode}):\n'
                f'stderr: {stderr}\n'
                f'stdout: {stdout}'
            )

        output = stdout.strip()
        if not output:
            return None

        if ret_type is int:
            try:
                return int(float(output))
            except (ValueError, TypeError):
                return output
        elif ret_type is float:
            try:
                return float(output)
            except (ValueError, TypeError):
                return output
        elif ret_type is bool:
            if isinstance(output, str):
                return output.lower() in ('true', '1', 'yes')
            return bool(output)

        return output

    def _run_sync(self, func, args, kwargs, mode, deps, module_code,
                  fallback, cache_dir, ret_type,
                  output_file=None, write_mode='overwrite',
                  prefix='', suffix='', project_dir=None, entry='main'):
        """同步执行（重写基类方法，优化 MoonBit 缓存策略）

        缓存改进：基于函数定义（不含参数值）计算缓存键，同一个函数复用
        同一个项目目录，每次调用时重写 main.mbt 更新参数值。
        """
        if project_dir is not None:
            return self._run_project_sync(
                func, args, kwargs, project_dir, entry,
                fallback, cache_dir, ret_type, mode
            )

        if CompileMode.normalize(mode) == CompileMode.ONLY_CODE:
            return self._run_only_code(
                func, args, kwargs, deps, module_code,
                output_file, write_mode, prefix, suffix
            )

        if not self.compiler_available():
            if fallback:
                return fallback(*args, **kwargs)
            raise RuntimeError(
                f"{self.name} compiler not available "
                f"and no fallback provided for '{func.__name__}'"
            )

        try:
            from .._base import FunctionParser
            spec = FunctionParser.parse(func, *args, **kwargs)
            if module_code:
                spec.module_code = module_code

            spec = self._dep_resolver.resolve(spec, deps)

            func_def_code, params, ret_moonbit_type = self._get_func_def_and_types(spec)

            project_dir = self._get_or_create_project_dir(
                func_def_code, func.__name__, cache_dir
            )

            self._write_main_with_args(
                project_dir, func_def_code, func.__name__,
                params, ret_moonbit_type, args
            )

            return self.call_func(project_dir, func.__name__, args, ret_type)

        except Exception:
            if fallback:
                return fallback(*args, **kwargs)
            raise


_moonbit_bridge = MoonBitBridge()
moonbit = _moonbit_bridge.decorator
moonbit_bridge = _moonbit_bridge


def compile_and_run(
    code: str,
    func_name: str,
    args: tuple,
    ret_type: Optional[type] = None,
    cache_dir: Optional[str] = None,
) -> Any:
    """编译并运行 MoonBit 代码"""
    bridge = _moonbit_bridge
    project_dir = bridge.compile_code(code, func_name, cache_dir)
    return bridge.call_func(project_dir, func_name, args, ret_type)


__all__ = [
    'moonbit',
    'moonbit_compiler_available',
    'MoonBitBridge',
    'moonbit_bridge',
    '_moonbit_bridge',
    'compile_and_run',
    'MoonBitFuture',
    'get_moonbit_version',
]
