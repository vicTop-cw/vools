"""
vools.bridge.zi.compiler - 兹（Zi）语言桥接实现（单文件）

兹是一门以中文为主、编译到 BEAM 字节码（Elixir/Erlang）的编程语言，
编译器为 Python 包 zhi（词法/语法/语义/Elixir 代码生成全链路）。
本模块提供：
    - ZiBridge 类：继承 LangBridge，实现兹代码生成与直通运行
    - zi 装饰器：将 Python 函数转换为兹代码（函数体即兹代码）
    - compile_and_run：直接运行一段兹源码
    - zi_compiler_available：探测 zhi 编译器与 Elixir 运行时

设计要点：
    - 解释/直通型语言：核心执行链路 `zhi compile <file.玆> --run`
      （即时编译到内存并运行 `策 主`，复用 OTP 并发/容错）
    - 参数传递：Python 参数以文本替换方式注入（arg0/arg1 -> 字面量），
      避免 zhi 顶层赋作用域限制
    - 工具链：zhi Python 包（E:\\IDEProjects\\AI\\兹\\zhi\\src）+ Elixir 可执行
    - 编码：.玆 文件 UTF-8 无 BOM 写入

典型用法::

    from vools.bridge.zi import zi

    @zi
    def hello() -> str:
        return '''
        坊 示例

        策 主
            言 "你好，兹"
        '''

    print(hello())   # -> 你好，兹
"""

import os
import sys
import json
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

# zhi Python 包源码目录（非标准安装，src 布局）
_ZHI_SRC = r'E:\IDEProjects\AI\兹\zhi\src'


def _zhi_available() -> bool:
    """探测 zhi 编译器是否可导入。"""
    if not os.path.isdir(os.path.join(_ZHI_SRC, 'zhi')):
        return False
    try:
        sys.path.insert(0, _ZHI_SRC)
        import zhi  # noqa: F401
        return True
    except Exception:
        return False


def _elixir_available() -> bool:
    """探测 Elixir 运行时是否可用（zhi 编译到 BEAM 需要）。"""
    try:
        return shutil.which('elixir') is not None
    except Exception:
        return False


_ZHI_OK = _zhi_available()
_ELIXIR_OK = _elixir_available()
_ZI_CACHE_DIR = os.path.join(tempfile.gettempdir(), 'vools_zi_cache')
_zi_exec_lock = threading.Lock()


def zi_compiler_available() -> bool:
    """zhi 编译器 + Elixir 运行时是否都可用。"""
    return _ZHI_OK and _ELIXIR_OK


def get_zi_version() -> str:
    """获取 zhi 编译器版本信息（尽力而为）。"""
    if not _ZHI_OK:
        return ''
    try:
        sys.path.insert(0, _ZHI_SRC)
        import zhi
        return getattr(zhi, '__version__', '') or 'zhi@src'
    except Exception:
        return ''


# ----------------------------------------------------------------------------
# Python ↔ 兹 类型映射
# ----------------------------------------------------------------------------

_ZI_TYPE_ALIASES = {
    'int': '数',
    'integer': '数',
    'float': '数',
    'number': '数',
    'str': '字',
    'string': '字',
    'bool': '真',
    'boolean': '真',
    'list': '列',
    'array': '列',
    'none': '空',
    'nonetype': '空',
}


def get_zi_type(py_type) -> str:
    """根据 Python 类型获取兹端类型名称（尽力映射）。"""
    if py_type in (int, float):
        return '数'
    if py_type is str:
        return '字'
    if py_type is bool:
        return '真'
    if py_type in (list, tuple):
        return '列'
    if py_type is type(None):
        return '空'
    if isinstance(py_type, str):
        normalized = py_type.strip().lower()
        if normalized in _ZI_TYPE_ALIASES:
            return _ZI_TYPE_ALIASES[normalized]
        short = normalized.split('.')[-1]
        if short in _ZI_TYPE_ALIASES:
            return _ZI_TYPE_ALIASES[short]
    return '字'


def _literal_to_zi(value: Any) -> str:
    """把 Python 值转成兹字面量（文本替换注入用）。"""
    if value is None:
        return '空'
    if isinstance(value, bool):
        return '真' if value else '假'
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (list, tuple)):
        return '[' + ', '.join(_literal_to_zi(v) for v in value) + ']'
    return json.dumps(str(value), ensure_ascii=False)


def _inject_args(body: str, arg_values: tuple) -> str:
    """把 arg0/arg1/... 占位符替换为字面量（参数注入）。"""
    code = body
    for i, value in enumerate(arg_values):
        code = code.replace('arg{}'.format(i), _literal_to_zi(value))
    return code


# ----------------------------------------------------------------------------
# 执行逻辑
# ----------------------------------------------------------------------------

def _execute_zi_code(code: str, func_name: str,
                     cache_dir: Optional[str] = None,
                     timeout: int = 120) -> str:
    """执行兹代码并返回 stdout 输出（zhi compile --run 直通运行）。

    Args:
        code: 完整兹源码。
        func_name: 函数名（文件名用）。
        cache_dir: 缓存目录。
        timeout: 执行超时秒数。

    Returns:
        stdout 输出（strip 后，不含 Elixir 编译警告）。

    Raises:
        RuntimeError: 编译或执行失败时抛出。
    """
    if cache_dir is None:
        cache_dir = _ZI_CACHE_DIR
    os.makedirs(cache_dir, exist_ok=True)

    code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
    src_path = os.path.join(cache_dir, 'zi_{}_{}.玆'.format(func_name, code_hash))

    with _zi_exec_lock:
        with open(src_path, 'w', encoding='utf-8') as f:
            f.write(code)

        env = dict(os.environ)
        env['PYTHONPATH'] = _ZHI_SRC + os.pathsep + env.get('PYTHONPATH', '')

        result = subprocess.run(
            [sys.executable, '-m', 'zhi.cli', 'compile', src_path, '--run'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding='utf-8', errors='replace',
            env=env, timeout=timeout,
        )

    if result.returncode != 0:
        raise RuntimeError(
            '兹编译/执行失败 (exit {}):\nstderr:\n{}\nstdout:\n{}\n代码:\n{}'.format(
                result.returncode, result.stderr, result.stdout, code
            )
        )
    return result.stdout.strip()


# ----------------------------------------------------------------------------
# ZiBridge - 兹桥接实现（继承 LangBridge）
# ----------------------------------------------------------------------------

class ZiBridge(LangBridge):
    """兹语言桥接实现。

    核心链路为 `zhi compile <file.玆> --run`（即时编译到内存并运行 `策 主`）。
    参数通过文本替换 arg0/arg1 注入。
    """

    name = 'zi'
    is_compiled = False
    lang_type = LangType.INTERPRETED
    file_ext = '.玆'
    lib_ext = '.玆'

    def __init__(self) -> None:
        """初始化兹桥接器。"""
        super().__init__()

    def compiler_available(self) -> bool:
        """zhi 编译器 + Elixir 运行时是否可用。"""
        return zi_compiler_available()

    def generate_code(self, spec: FunctionSpec) -> str:
        """生成兹代码（module_code + 主体）。"""
        parts = []
        if spec.module_code:
            parts.append(spec.module_code)
        parts.append(spec.body)
        return '\n\n'.join(p for p in parts if p)

    def compile_code(self, code: str, func_name: str,
                     cache_dir: Optional[str] = None) -> str:
        """保存兹源码到缓存目录（直通型语言的'编译'）。

        Args:
            code: 兹源代码。
            func_name: 函数名。
            cache_dir: 缓存目录。

        Returns:
            源文件路径。
        """
        if cache_dir is None:
            cache_dir = _ZI_CACHE_DIR
        os.makedirs(cache_dir, exist_ok=True)

        code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
        src_path = os.path.join(cache_dir, 'zi_{}_{}.玆'.format(func_name, code_hash))
        with open(src_path, 'w', encoding='utf-8') as f:
            f.write(code)
        return src_path

    def compile_project(self, project_dir: str, entry: str,
                        output_dir: Optional[str] = None) -> str:
        """处理兹项目：返回入口 .玆 文件路径。

        Args:
            project_dir: 项目目录。
            entry: 入口（'main' 或文件名）。
            output_dir: 输出目录。

        Returns:
            入口 .玆 文件路径。

        Raises:
            RuntimeError: 无 .玆 文件时抛出。
        """
        zi_files = []
        for root, _dirs, files in os.walk(project_dir):
            for f in files:
                if f.endswith('.玆'):
                    zi_files.append(os.path.join(root, f))
        zi_files.sort()
        if not zi_files:
            raise RuntimeError('No .玆 files found in project directory: {}'.format(project_dir))

        if entry == 'main':
            entry_file = os.path.join(project_dir, 'main.玆')
            if os.path.exists(entry_file):
                return entry_file
            return zi_files[0]

        for zi_file in zi_files:
            if os.path.basename(zi_file) == entry or os.path.splitext(os.path.basename(zi_file))[0] == entry:
                return zi_file
        return zi_files[0]

    def _execute_code(self, package_path: str, func_name: str,
                      args: tuple, ret_type: Optional[type] = None) -> Any:
        """解包 zip 产物并执行兹源码。"""
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
        """打包兹源码为 zip（内容哈希命名）。"""
        import zipfile
        if cache_dir is None:
            cache_dir = _ZI_CACHE_DIR
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
        """调用兹代码：注入参数（文本替换）→ zhi compile --run 执行。

        Args:
            src_path: .玆 源文件路径。
            func_name: 函数名。
            args: 参数元组。
            ret_type: 返回类型（当前忽略，兹输出为 stdout 文本）。

        Returns:
            执行输出（stdout 文本）。
        """
        with open(src_path, 'r', encoding='utf-8') as f:
            code = f.read()

        full_code = _inject_args(code, args)
        return _execute_zi_code(full_code, func_name)

    def run_project(self, project_dir: str, entry: str = 'main',
                    args: tuple = (), cache_dir: Optional[str] = None) -> Any:
        """运行兹项目：找到入口 .玆 并执行，返回 (returncode, stdout, stderr)。"""
        entry_file = self.compile_project(project_dir, entry, cache_dir)
        env = dict(os.environ)
        env['PYTHONPATH'] = _ZHI_SRC + os.pathsep + env.get('PYTHONPATH', '')
        result = subprocess.run(
            [sys.executable, '-m', 'zhi.cli', 'compile', entry_file, '--run'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding='utf-8', errors='replace',
            env=env, timeout=120,
        )
        return (result.returncode, result.stdout, result.stderr)


# 全局 ZiBridge 实例
_zi_bridge = ZiBridge()
zi = _zi_bridge.decorator


# ----------------------------------------------------------------------------
# 便捷入口
# ----------------------------------------------------------------------------

def compile_and_run(zi_code: str, func_name: str = 'main',
                    args: tuple = (), cache_dir: Optional[str] = None) -> str:
    """直接运行一段兹源码（无装饰器）。

    Args:
        zi_code: 完整兹源码（含 `策 主` 入口）。
        func_name: 函数名（文件名用）。
        args: Python 位置参数（以 arg0/arg1 文本替换注入）。
        cache_dir: 缓存目录（可选）。

    Returns:
        执行输出（stdout 文本）。

    Example:
        >>> compile_and_run("坊 示例\\n\\n策 主\\n    言 \\"你好兹\\"")
        '你好兹'
    """
    full_code = _inject_args(zi_code, args)
    return _execute_zi_code(full_code, func_name, cache_dir)


__all__ = [
    'ZiBridge',
    'zi',
    '_zi_bridge',
    'zi_bridge',
    'compile_and_run',
    'zi_compiler_available',
    'get_zi_version',
    'get_zi_type',
]

# 别名：与其它语言模块保持一致
zi_bridge = _zi_bridge
