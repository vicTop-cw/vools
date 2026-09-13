"""
vools.bridge.cypy.compiler - Cypy 语言桥接实现（单文件）

Cypy 是一门 Python-like 语言，编译器 cypyc 将其转译为 Cython（.pyx）再编译为高性能 C 扩展。
本模块提供：
    - CypyBridge 类：继承 LangBridge，实现 Cypy 代码生成与转译
    - cypy 装饰器：将 Python 函数转换为 Cypy 代码（函数体即 Cypy 代码）
    - compile_and_run：直接转译一段 Cypy 源码
    - cypy_compiler_available：探测 cypyc 工具链

设计要点：
    - 转译型语言：核心能力是 Cypy → Cython 转译（cypyc transpile file.cypy -> .pyx）
    - 执行链路（可选）：cypyc run 完整链路（转译 + Cython 编译 .pyd + 运行）；
      依赖完整 Python（含 Python.h）+ MSVC 编译器，环境不支持时降级返回转译产物
    - 参数传递：Python 参数以 arg0/arg1 占位符文本替换注入（Cypy 语法贴近 Python）

典型用法::

    from vools.bridge.cypy import cypy

    @cypy
    def hello() -> str:
        return '''
        print(1 + 2)
        '''

    # 环境支持时直接运行；否则返回转译的 .pyx 路径（可配 fallback）
"""

import os
import sys
import platform
import hashlib
import tempfile
import shutil
import subprocess
import threading
from typing import Any, Optional, List

from .._base import LangBridge, FunctionSpec
from ..core.types import LangType

# ----------------------------------------------------------------------------
# 平台判断
# ----------------------------------------------------------------------------
_IS_WINDOWS = platform.system() == 'Windows'


def _find_cypyc() -> Optional[str]:
    """在 PATH 与当前 Python Scripts 目录中查找 cypyc 可执行文件。"""
    found = shutil.which('cypyc')
    if found:
        return found
    scripts = os.path.join(os.path.dirname(sys.executable), 'Scripts')
    for name in ('cypyc.exe', 'cypyc'):
        cand = os.path.join(scripts, name)
        if os.path.isfile(cand):
            return cand
    return None


def _python_h_available() -> bool:
    """检查当前 Python 是否有 C API 头文件（编译 Cython 扩展需要 Python.h）。"""
    import sysconfig
    inc = sysconfig.get_paths().get('include', '')
    if inc and os.path.isfile(os.path.join(inc, 'Python.h')):
        return True
    # 常见回退：解释器目录下的 include
    base = os.path.dirname(sys.executable)
    for cand in (os.path.join(base, 'include'), os.path.join(os.path.dirname(base), 'include')):
        if os.path.isfile(os.path.join(cand, 'Python.h')):
            return True
    return False


_CYPYC = _find_cypyc()
_PYTHON_H_OK = _python_h_available()
_CYPY_CACHE_DIR = os.path.join(tempfile.gettempdir(), 'vools_cypy_cache')
_cypy_exec_lock = threading.Lock()


def cypy_compiler_available() -> bool:
    """探测 cypyc 工具链（转译能力）是否可用。"""
    if _CYPYC is None:
        # 兜底：cypyc 可能以 Python 包形式安装
        try:
            import cypyc  # noqa: F401
            return True
        except Exception:
            return False
    return True


def cypy_run_available() -> bool:
    """探测完整执行链路（转译 + Cython 编译运行）是否可用。"""
    if not cypy_compiler_available():
        return False
    # 需要 Python.h（编译 Cython 扩展）
    if not _PYTHON_H_OK:
        return False
    # 需要 C 编译器（Windows 上 MSVC cl 或 gcc）
    cl = shutil.which('cl')
    gcc = shutil.which('gcc')
    if cl is None and gcc is None:
        # MSVC 常见路径
        import glob
        msvc = glob.glob(r'D:\VisualStudioBuildTools\VC\Tools\MSVC\*\bin\Host*\x64\cl.exe')
        if not msvc:
            return False
    return True


def get_cypy_version() -> str:
    """获取 cypyc 版本号（尽力而为）。"""
    try:
        import cypyc
        return getattr(cypyc, '__version__', '') or ''
    except Exception:
        return ''


# ----------------------------------------------------------------------------
# Python ↔ Cypy 类型映射
# ----------------------------------------------------------------------------

_CYPY_TYPE_ALIASES = {
    'int': 'int',
    'integer': 'int',
    'int64': 'int',
    'float': 'float',
    'double': 'float',
    'float64': 'float',
    'str': 'str',
    'string': 'str',
    'bool': 'bool',
    'boolean': 'bool',
    'list': 'list',
    'array': 'list',
    'dict': 'dict',
    'none': 'None',
    'nonetype': 'None',
}


def get_cypy_type(py_type) -> str:
    """根据 Python 类型获取 Cypy 端类型字符串。"""
    if py_type is int:
        return 'int'
    if py_type is float:
        return 'float'
    if py_type is str:
        return 'str'
    if py_type is bool:
        return 'bool'
    if py_type in (list, tuple):
        return 'list'
    if py_type is dict:
        return 'dict'
    if py_type is type(None):
        return 'None'
    if isinstance(py_type, str):
        normalized = py_type.strip().lower()
        if normalized in _CYPY_TYPE_ALIASES:
            return _CYPY_TYPE_ALIASES[normalized]
        short = normalized.split('.')[-1]
        if short in _CYPY_TYPE_ALIASES:
            return _CYPY_TYPE_ALIASES[short]
    return 'object'


def _literal_to_cypy(value: Any) -> str:
    """把 Python 值转成 Cypy 字面量（文本替换注入用）。"""
    if value is None:
        return 'None'
    if isinstance(value, bool):
        return 'True' if value else 'False'
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return repr(value)
    if isinstance(value, (list, tuple)):
        return '[' + ', '.join(_literal_to_cypy(v) for v in value) + ']'
    if isinstance(value, dict):
        return '{' + ', '.join(
            '{}: {}'.format(_literal_to_cypy(k), _literal_to_cypy(v))
            for k, v in value.items()
        ) + '}'
    return repr(str(value))


def _inject_args(body: str, arg_values: tuple) -> str:
    """把 arg0/arg1/... 占位符替换为字面量（参数注入）。"""
    code = body
    for i, value in enumerate(arg_values):
        code = code.replace('arg{}'.format(i), _literal_to_cypy(value))
    return code


# ----------------------------------------------------------------------------
# 转译与执行
# ----------------------------------------------------------------------------

def _transpile_cypy(src_path: str, out_dir: Optional[str] = None,
                    timeout: int = 120) -> str:
    """调用 cypyc transpile 转译 .cypy 为 Cython 源（.pyx）。

    Args:
        src_path: .cypy 源文件路径。
        out_dir: 输出目录（默认源文件同目录）。
        timeout: 超时秒数。

    Returns:
        生成的 .pyx 文件路径。

    Raises:
        RuntimeError: 转译失败时抛出。
    """
    if _CYPYC is None:
        raise RuntimeError('cypyc 工具链不可用')
    if out_dir is None:
        out_dir = os.path.dirname(src_path)
    os.makedirs(out_dir, exist_ok=True)

    result = subprocess.run(
        [_CYPYC, 'transpile', src_path, '-o', out_dir],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding='utf-8', errors='replace', timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(
            'Cypy 转译失败 (exit {}):\nstderr:\n{}\nstdout:\n{}'.format(
                result.returncode, result.stderr, result.stdout
            )
        )
    base = os.path.splitext(os.path.basename(src_path))[0]
    pyx_path = os.path.join(out_dir, base + '.pyx')
    if not os.path.exists(pyx_path):
        # 兜底：在 out_dir 下递归查找同名 .pyx
        for root, _dirs, files in os.walk(out_dir):
            if (base + '.pyx') in files:
                return os.path.join(root, base + '.pyx')
        raise RuntimeError('Cypy 转译未生成 .pyx 产物')
    return pyx_path


def _execute_cypy_code(code: str, func_name: str,
                       cache_dir: Optional[str] = None,
                       timeout: int = 180) -> Any:
    """转译并（环境支持时）运行 Cypy 代码。

    Args:
        code: 完整 Cypy 源码。
        func_name: 函数名（文件名用）。
        cache_dir: 缓存目录。
        timeout: 超时秒数。

    Returns:
        环境支持完整执行时返回 stdout 输出；否则返回 .pyx 转译产物路径。

    Raises:
        RuntimeError: 转译失败时抛出。
    """
    if cache_dir is None:
        cache_dir = _CYPY_CACHE_DIR
    os.makedirs(cache_dir, exist_ok=True)

    code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
    src_path = os.path.join(cache_dir, 'cypy_{}_{}.cypy'.format(func_name, code_hash))
    with open(src_path, 'w', encoding='utf-8') as f:
        f.write(code)

    if not cypy_run_available():
        # 降级：仅转译，返回 .pyx 路径
        return _transpile_cypy(src_path, cache_dir, timeout)

    # 完整链路：cypyc run
    result = subprocess.run(
        [_CYPYC, 'run', src_path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding='utf-8', errors='replace', timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(
            'Cypy 执行失败 (exit {}):\nstderr:\n{}\nstdout:\n{}'.format(
                result.returncode, result.stderr, result.stdout
            )
        )
    return result.stdout.strip()


# ----------------------------------------------------------------------------
# CypyBridge - Cypy 桥接实现（继承 LangBridge）
# ----------------------------------------------------------------------------

class CypyBridge(LangBridge):
    """Cypy 语言桥接实现。

    核心能力为 Cypy → Cython 转译；完整执行链路（编译 .pyd 运行）依赖
    完整 Python（含 Python.h）+ C 编译器，环境不支持时降级返回 .pyx 路径。
    """

    name = 'cypy'
    is_compiled = False
    lang_type = LangType.INTERPRETED
    file_ext = '.cypy'
    lib_ext = '.pyx'

    def __init__(self) -> None:
        """初始化 Cypy 桥接器。"""
        super().__init__()

    def compiler_available(self) -> bool:
        """cypyc 工具链是否可用。"""
        return cypy_compiler_available()

    def generate_code(self, spec: FunctionSpec) -> str:
        """生成 Cypy 代码（module_code + 主体）。"""
        parts = []
        if spec.module_code:
            parts.append(spec.module_code)
        parts.append(spec.body)
        return '\n\n'.join(p for p in parts if p)

    def compile_code(self, code: str, func_name: str,
                     cache_dir: Optional[str] = None) -> str:
        """转译 Cypy 源码为 .pyx（核心能力）。

        Args:
            code: Cypy 源代码。
            func_name: 函数名。
            cache_dir: 缓存目录。

        Returns:
            .pyx 文件路径。

        Raises:
            RuntimeError: 转译失败时抛出。
        """
        if cache_dir is None:
            cache_dir = _CYPY_CACHE_DIR
        os.makedirs(cache_dir, exist_ok=True)

        code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
        src_path = os.path.join(cache_dir, 'cypy_{}_{}.cypy'.format(func_name, code_hash))
        with open(src_path, 'w', encoding='utf-8') as f:
            f.write(code)
        return _transpile_cypy(src_path, cache_dir)

    def compile_project(self, project_dir: str, entry: str,
                        output_dir: Optional[str] = None) -> str:
        """转译 Cypy 项目（扫描 .cypy 文件，逐个转译为 .pyx）。

        Args:
            project_dir: 项目目录。
            entry: 入口文件或 'main'。
            output_dir: 输出目录。

        Returns:
            入口 .pyx 路径。

        Raises:
            RuntimeError: 无 .cypy 文件时抛出。
        """
        output_dir = output_dir or _CYPY_CACHE_DIR
        os.makedirs(output_dir, exist_ok=True)

        cypy_files = []
        for root, _dirs, files in os.walk(project_dir):
            for f in files:
                if f.endswith('.cypy'):
                    cypy_files.append(os.path.join(root, f))
        cypy_files.sort()
        if not cypy_files:
            raise RuntimeError('No .cypy files found in project directory: {}'.format(project_dir))

        if entry == 'main':
            entry_file = os.path.join(project_dir, 'main.cypy')
            if not os.path.exists(entry_file):
                entry_file = cypy_files[0]
            return _transpile_cypy(entry_file, output_dir)

        for cypy_file in cypy_files:
            if os.path.basename(cypy_file) == entry or \
                    os.path.splitext(os.path.basename(cypy_file))[0] == entry:
                return _transpile_cypy(cypy_file, output_dir)
        return _transpile_cypy(cypy_files[0], output_dir)

    def _execute_code(self, package_path: str, func_name: str,
                      args: tuple, ret_type: Optional[type] = None) -> Any:
        """解包 zip 产物并转译执行 Cypy 源码。"""
        import zipfile
        import tempfile
        import shutil

        tmpdir = tempfile.mkdtemp()
        try:
            with zipfile.ZipFile(package_path, 'r') as zf:
                zf.extractall(tmpdir)
            source_file = os.path.join(tmpdir, self.get_source_filename(func_name))
            return self.call_func(source_file, func_name, args, ret_type)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def _package_code(self, code: str, func_name: str,
                      cache_dir: Optional[str] = None) -> str:
        """打包 Cypy 源码为 zip（内容哈希命名）。"""
        import zipfile
        if cache_dir is None:
            cache_dir = _CYPY_CACHE_DIR
        cache_dir = self.get_cache_dir(cache_dir)

        code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
        package_path = os.path.join(
            cache_dir, '{}_{}_package.zip'.format(func_name, code_hash)
        )
        if os.path.exists(package_path):
            return package_path

        fd, tmp_path = tempfile.mkstemp(dir=cache_dir, suffix='.zip')
        try:
            os.close(fd)
            with self._package_lock:
                if os.path.exists(package_path):
                    return package_path
                with zipfile.ZipFile(tmp_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                    zf.writestr(self.get_source_filename(func_name), code)
                try:
                    os.replace(tmp_path, package_path)
                except (PermissionError, OSError):
                    if os.path.exists(package_path):
                        return package_path
                    raise
        except Exception:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            raise
        return package_path

    def call_func(self, src_path: str, func_name: str,
                  args: tuple, ret_type: Optional[type] = None) -> Any:
        """调用 Cypy 代码：注入参数（文本替换）→ 转译（环境支持时编译运行）。

        Args:
            src_path: .cypy 源文件路径。
            func_name: 函数名。
            args: 参数元组。
            ret_type: 返回类型（当前忽略，Cypy 输出为 stdout 文本）。

        Returns:
            环境支持时返回 stdout 输出；否则返回 .pyx 路径。
        """
        with open(src_path, 'r', encoding='utf-8') as f:
            code = f.read()

        full_code = _inject_args(code, args)
        return _execute_cypy_code(full_code, func_name)

    def run_project(self, project_dir: str, entry: str = 'main',
                    args: tuple = (), cache_dir: Optional[str] = None) -> Any:
        """运行 Cypy 项目：转译入口文件，环境支持时编译运行。"""
        entry_file = self.compile_project(project_dir, entry, cache_dir)
        if not cypy_run_available():
            return (entry_file, '', '')
        result = subprocess.run(
            [_CYPYC, 'run', entry_file],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding='utf-8', errors='replace', timeout=180,
        )
        return (result.returncode, result.stdout, result.stderr)


# 全局 CypyBridge 实例
_cypy_bridge = CypyBridge()
cypy = _cypy_bridge.decorator


# ----------------------------------------------------------------------------
# 便捷入口
# ----------------------------------------------------------------------------

def compile_and_run(cypy_code: str, func_name: str = 'main',
                    args: tuple = (), cache_dir: Optional[str] = None) -> Any:
    """直接转译并（环境支持时）运行一段 Cypy 源码（无装饰器）。

    Args:
        cypy_code: 完整 Cypy 源码。
        func_name: 函数名（文件名用）。
        args: Python 位置参数（以 arg0/arg1 文本替换注入）。
        cache_dir: 缓存目录（可选）。

    Returns:
        环境支持时返回执行输出；否则返回 .pyx 转译产物路径。

    Example:
        >>> compile_and_run("print(1 + 2)")
        3  # 或 .pyx 路径（环境不支持编译时）
    """
    full_code = _inject_args(cypy_code, args)
    return _execute_cypy_code(full_code, func_name, cache_dir)


__all__ = [
    'CypyBridge',
    'cypy',
    '_cypy_bridge',
    'cypy_bridge',
    'compile_and_run',
    'cypy_compiler_available',
    'cypy_run_available',
    'get_cypy_version',
    'get_cypy_type',
]

# 别名：与其它语言模块保持一致
cypy_bridge = _cypy_bridge
