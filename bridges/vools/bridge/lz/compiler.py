"""
vools.bridge.lz.compiler - LZ (Lang-Zone) 语言桥接实现（单文件）

LZ 是面向系统编程的静态类型语言，编译器为 lang-zone（LZ → Rust，IR 中间表示路线）。
本模块提供：
    - LzBridge 类：继承 LangBridge，实现 LZ 代码生成与 LZ→Rust 转译
    - lz 装饰器：将 Python 函数转换为 LZ 代码（函数体即 LZ 代码）
    - compile_and_run：直接转译一段 LZ 源码
    - lz_compiler_available：探测 lang-zone 工具链

设计要点：
    - 转译型语言：核心能力是 LZ → Rust 代码生成（lang-zone.exe file.lz -> file.rs）
    - 执行链路：生成的 .rs 需 rustc + lz_builtins crate 编译；rustc 不可用时
      返回 .rs 路径（only-code 降级），配合 fallback 参数回退 Python 实现
    - 参数传递：Python 参数以 LZ 字面量生成 let 绑定注入源码顶部
    - 编码注意：LZ 解析器不识别 BOM，文件写入必须 UTF-8 无 BOM

典型用法::

    from vools.bridge.lz import lz

    @lz
    def hello(x: int) -> int:
        return '''
        def main():
            let v = arg0 + 1
            print(v)
        '''

    # rustc 可用时直接运行；否则返回生成的 .rs 路径（可配 fallback）
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

# lang-zone 已知产物候选
_LZ_PROJECT_CANDIDATES = (
    r'E:\IDEProjects\AI\lang-zone\target\debug\lang-zone.exe',
    r'E:\IDEProjects\AI\lang-zone\target\release\lang-zone.exe',
)


def _find_lz_exe() -> Optional[str]:
    """在已知路径与 PATH 中查找 lang-zone 可执行文件。"""
    for cand in _LZ_PROJECT_CANDIDATES:
        if os.path.isfile(cand):
            return cand
    return shutil.which('lang-zone') or shutil.which('lz') or shutil.which('lzc')


def _rustc_available() -> bool:
    """检查 rustc 是否可用（执行 rustc --version）。"""
    try:
        result = subprocess.run(
            ['rustc', '--version'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, errors='replace', timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return False


_LZ_EXE = _find_lz_exe()
_LZ_CACHE_DIR = os.path.join(tempfile.gettempdir(), 'vools_lz_cache')
_lz_exec_lock = threading.Lock()


def lz_compiler_available() -> bool:
    """检查 lang-zone 工具链是否可用。"""
    return _LZ_EXE is not None


def get_lz_version() -> str:
    """获取 lang-zone 版本信息（尽力而为）。"""
    if not _LZ_EXE:
        return ''
    return os.path.basename(os.path.dirname(os.path.dirname(_LZ_EXE)))


# ----------------------------------------------------------------------------
# Python ↔ LZ 类型映射
# ----------------------------------------------------------------------------

_LZ_TYPE_ALIASES = {
    'int': 'i64',
    'integer': 'i64',
    'i64': 'i64',
    'int64': 'i64',
    'float': 'f64',
    'double': 'f64',
    'f64': 'f64',
    'float64': 'f64',
    'str': 'String',
    'string': 'String',
    'bool': 'bool',
    'boolean': 'bool',
    'list': 'Vec',
    'array': 'Vec',
    'vec': 'Vec',
    'none': '()',
    'nonetype': '()',
}


def get_lz_type(py_type) -> str:
    """根据 Python 类型获取 LZ 端类型字符串。"""
    if py_type is int:
        return 'i64'
    if py_type is float:
        return 'f64'
    if py_type is str:
        return 'String'
    if py_type is bool:
        return 'bool'
    if py_type in (list, tuple):
        return 'Vec'
    if py_type is type(None):
        return '()'
    if isinstance(py_type, str):
        normalized = py_type.strip().lower()
        if normalized in _LZ_TYPE_ALIASES:
            return _LZ_TYPE_ALIASES[normalized]
        short = normalized.split('.')[-1]
        if short in _LZ_TYPE_ALIASES:
            return _LZ_TYPE_ALIASES[short]
    return 'i64'


def _literal_to_lz(value: Any) -> str:
    """把 Python 值转成 LZ 字面量（嵌入生成源码用）。"""
    if value is None:
        return '()'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (list, tuple)):
        return 'vec![' + ', '.join(_literal_to_lz(v) for v in value) + ']'
    if isinstance(value, dict):
        items = ', '.join(
            '({}, {})'.format(_literal_to_lz(k), _literal_to_lz(v))
            for k, v in value.items()
        )
        return 'vec![' + items + ']'
    return json.dumps(str(value), ensure_ascii=False)


# ----------------------------------------------------------------------------
# 代码生成
# ----------------------------------------------------------------------------

def _generate_lz_source(
    func_name: str,
    arg_names: List[str],
    arg_values: tuple,
    body: str,
    module_code: str = '',
) -> str:
    """生成完整的 LZ 源码。

    参数以 let 绑定注入源码顶部；body 为用户提供的 LZ 代码。
    文件必须无 BOM（LZ 解析器不识别 BOM）。

    Args:
        func_name: 函数名（注释标记）。
        arg_names: 参数名列表。
        arg_values: Python 参数值。
        body: 用户 LZ 代码。
        module_code: 模块级代码（可选）。

    Returns:
        完整 .lz 源码字符串。
    """
    parts = []
    parts.append('// vools.lz bridge: {}'.format(func_name))
    parts.append('')

    if module_code:
        parts.append(module_code)
        parts.append('')

    for name, value in zip(arg_names, arg_values):
        parts.append('let {} = {}'.format(name, _literal_to_lz(value)))
    if arg_names:
        parts.append('')

    parts.append(body)

    return '\n'.join(parts)


def _write_no_bom(path: str, text: str) -> None:
    """UTF-8 无 BOM 写文件（LZ 解析器不识别 BOM）。"""
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)


# ----------------------------------------------------------------------------
# 转译执行
# ----------------------------------------------------------------------------

def _transpile_lz(src_path: str, timeout: int = 60) -> str:
    """调用 lang-zone 转译 .lz 为 .rs。

    Args:
        src_path: .lz 源文件路径。
        timeout: 超时秒数。

    Returns:
        生成的 .rs 文件路径。

    Raises:
        RuntimeError: 转译失败时抛出。
    """
    result = subprocess.run(
        [_LZ_EXE, src_path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding='utf-8', errors='replace', timeout=timeout,
    )
    rs_path = os.path.splitext(src_path)[0] + '.rs'
    if result.returncode != 0 or not os.path.exists(rs_path):
        raise RuntimeError(
            'LZ 转译失败 (exit {}):\nstderr:\n{}\nstdout:\n{}'.format(
                result.returncode, result.stderr, result.stdout
            )
        )
    return rs_path


def _compile_rs_to_exe(rs_path: str, timeout: int = 120) -> str:
    """用 rustc 把 .rs 编译为可执行文件（需要 lz_builtins crate 可见）。

    Args:
        rs_path: .rs 文件路径。
        timeout: 超时秒数。

    Returns:
        可执行文件路径。

    Raises:
        RuntimeError: rustc 不可用或编译失败时抛出。
    """
    if not _rustc_available():
        raise RuntimeError('rustc 不可用：已生成 .rs 源码 {}，请安装 Rust 工具链后 '
                           '手动 rustc 编译（需 lz_builtins crate）'.format(rs_path))
    exe_path = os.path.splitext(rs_path)[0] + '.exe' if os.name == 'nt' else \
        os.path.splitext(rs_path)[0]
    result = subprocess.run(
        ['rustc', rs_path, '-o', exe_path, '--edition', '2021'],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding='utf-8', errors='replace', timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(
            'rustc 编译失败 (exit {}):\n{}'.format(result.returncode, result.stderr)
        )
    return exe_path


def _execute_lz_code(code: str, func_name: str,
                     cache_dir: Optional[str] = None,
                     timeout: int = 60) -> Any:
    """转译并执行 LZ 代码。

    Args:
        code: 完整 LZ 源码。
        func_name: 函数名（文件名用）。
        cache_dir: 缓存目录。
        timeout: 执行超时。

    Returns:
        执行结果：rustc 可用时返回 stdout 输出，否则返回 .rs 路径。

    Raises:
        RuntimeError: 转译失败时抛出。
    """
    if cache_dir is None:
        cache_dir = _LZ_CACHE_DIR
    os.makedirs(cache_dir, exist_ok=True)

    code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
    src_path = os.path.join(cache_dir, 'lz_{}_{}.lz'.format(func_name, code_hash))

    with _lz_exec_lock:
        _write_no_bom(src_path, code)
        rs_path = _transpile_lz(src_path, timeout)

    if not _rustc_available():
        return rs_path  # 降级：返回 .rs 源码路径

    exe_path = _compile_rs_to_exe(rs_path, timeout)
    result = subprocess.run(
        [exe_path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding='utf-8', errors='replace', timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(
            'LZ 执行失败 (exit {}):\n{}'.format(result.returncode, result.stderr)
        )
    return result.stdout.strip()


# ----------------------------------------------------------------------------
# LzBridge - LZ 桥接实现（继承 LangBridge）
# ----------------------------------------------------------------------------

class LzBridge(LangBridge):
    """LZ 语言桥接实现。

    核心能力为 LZ → Rust 转译；执行链路依赖 rustc + lz_builtins crate，
    rustc 不可用时降级返回 .rs 源码路径（可配 fallback 回退）。
    """

    name = 'lz'
    is_compiled = False
    lang_type = LangType.INTERPRETED
    file_ext = '.lz'
    lib_ext = '.rs'

    def __init__(self) -> None:
        """初始化 LZ 桥接器。"""
        super().__init__()

    def compiler_available(self) -> bool:
        """lang-zone 工具链是否可用。"""
        return lz_compiler_available()

    def generate_code(self, spec: FunctionSpec) -> str:
        """生成 LZ 代码（module_code + 主体）。"""
        parts = []
        if spec.module_code:
            parts.append(spec.module_code)
        parts.append(spec.body)
        return '\n\n'.join(p for p in parts if p)

    def compile_code(self, code: str, func_name: str,
                     cache_dir: Optional[str] = None) -> str:
        """转译 LZ 源码为 .rs（核心能力）。

        Args:
            code: LZ 源代码。
            func_name: 函数名。
            cache_dir: 缓存目录。

        Returns:
            .rs 文件路径。

        Raises:
            RuntimeError: 转译失败时抛出。
        """
        if cache_dir is None:
            cache_dir = _LZ_CACHE_DIR
        os.makedirs(cache_dir, exist_ok=True)

        code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
        src_path = os.path.join(cache_dir, 'lz_{}_{}.lz'.format(func_name, code_hash))
        _write_no_bom(src_path, code)
        return _transpile_lz(src_path)

    def compile_project(self, project_dir: str, entry: str,
                        output_dir: Optional[str] = None) -> str:
        """转译 LZ 项目（扫描 .lz 文件，逐个转译为 .rs）。

        Args:
            project_dir: 项目目录。
            entry: 入口文件或 'main'。
            output_dir: 输出目录。

        Returns:
            转译产物目录或入口 .rs 路径。

        Raises:
            RuntimeError: 无 .lz 文件时抛出。
        """
        output_dir = output_dir or _LZ_CACHE_DIR
        os.makedirs(output_dir, exist_ok=True)

        lz_files = []
        for root, _dirs, files in os.walk(project_dir):
            for f in files:
                if f.endswith('.lz'):
                    lz_files.append(os.path.join(root, f))
        lz_files.sort()
        if not lz_files:
            raise RuntimeError('No .lz files found in project directory: {}'.format(project_dir))

        if entry == 'main':
            entry_file = os.path.join(project_dir, 'main.lz')
            if not os.path.exists(entry_file):
                entry_file = lz_files[0]
            return _transpile_lz(entry_file)

        # 全部转译，返回入口 .rs
        rs_path = None
        for lz_file in lz_files:
            rs = _transpile_lz(lz_file)
            if os.path.basename(lz_file) == entry:
                rs_path = rs
        return rs_path or _transpile_lz(entry + '.lz' if not entry.endswith('.lz') else entry)

    def _execute_code(self, package_path: str, func_name: str,
                      args: tuple, ret_type: Optional[type] = None) -> Any:
        """解包 zip 产物并转译执行 LZ 源码。"""
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
        """打包 LZ 源码为 zip（内容哈希命名，避免同名函数缓存失效）。"""
        import zipfile
        if cache_dir is None:
            cache_dir = _LZ_CACHE_DIR
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
        """调用 LZ 代码：注入参数绑定 → 转译 → （rustc 可用时）编译运行。

        Args:
            src_path: .lz 源文件路径。
            func_name: 函数名。
            args: 参数元组。
            ret_type: 返回类型（当前忽略，LZ 输出为 stdout 文本）。

        Returns:
            rustc 可用时返回 stdout 文本；否则返回 .rs 路径。
        """
        with open(src_path, 'r', encoding='utf-8') as f:
            code = f.read()

        arg_names = ['arg{}'.format(i) for i in range(len(args))]
        full_code = _generate_lz_source(
            func_name=func_name,
            arg_names=arg_names,
            arg_values=args,
            body=code,
        )
        return _execute_lz_code(full_code, func_name)

    def run_project(self, project_dir: str, entry: str = 'main',
                    args: tuple = (), cache_dir: Optional[str] = None) -> Any:
        """运行 LZ 项目：转译入口文件，rustc 可用时编译执行。"""
        if entry == 'main':
            rs_path = self.compile_project(project_dir, 'main', cache_dir)
            if not _rustc_available():
                return (rs_path, '', '')
            exe_path = _compile_rs_to_exe(rs_path)
            result = subprocess.run(
                [exe_path] + list(args),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding='utf-8', errors='replace', timeout=60,
            )
            return (result.returncode, result.stdout, result.stderr)
        artifact_path = self.compile_project(project_dir, entry, cache_dir)
        return self.call_func(artifact_path, entry, args)


# 全局 LzBridge 实例
_lz_bridge = LzBridge()
lz = _lz_bridge.decorator


# ----------------------------------------------------------------------------
# 便捷入口
# ----------------------------------------------------------------------------

def compile_and_run(lz_code: str, func_name: str = 'main',
                    args: tuple = (), cache_dir: Optional[str] = None) -> Any:
    """直接转译并（可选）执行一段 LZ 源码（无装饰器）。

    Args:
        lz_code: 完整 LZ 源码。
        func_name: 函数名（文件名用）。
        args: Python 位置参数（以 let 绑定注入）。
        cache_dir: 缓存目录（可选）。

    Returns:
        rustc 可用时返回执行输出，否则返回 .rs 路径。

    Example:
        >>> compile_and_run("def main():\\n    print(1 + 2)")
        3  # 或 .rs 路径（rustc 不可用时）
    """
    arg_names = ['arg{}'.format(i) for i in range(len(args))]
    source = _generate_lz_source(
        func_name=func_name,
        arg_names=arg_names,
        arg_values=args,
        body=lz_code,
    )
    return _execute_lz_code(source, func_name, cache_dir)


__all__ = [
    'LzBridge',
    'lz',
    '_lz_bridge',
    'lz_bridge',
    'compile_and_run',
    'lz_compiler_available',
    'get_lz_version',
    'get_lz_type',
    'rustc_available',
]

# 别名：与其它语言模块保持一致
lz_bridge = _lz_bridge
rustc_available = _rustc_available
