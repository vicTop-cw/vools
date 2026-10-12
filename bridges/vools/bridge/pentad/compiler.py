"""
vools.bridge.pentad.compiler - Pentad 语言桥接实现（单文件）

Pentad 是一门多范式语言，编译器为 `p5c`（Rust 实现，含 run/jit/dump/check 等子命令）。
本模块提供：
    - PentadBridge 类：继承 LangBridge，实现 Pentad 代码生成与 `p5c run` 执行
    - pentad 装饰器：将 Python 函数转换为 Pentad 代码执行（函数体即 Pentad 代码）
    - compile_and_run：直接执行一段 Pentad 源码（无装饰器）
    - pentad_compiler_available：探测 p5c 工具链

设计要点：
    - 执行型语言：lang_type = INTERPRETED，产物为 .p5 源文件
    - 执行链路：p5c run -q <file.p5>，-q 抑制诊断行，只输出程序自身 stdout
    - 工具链位置统一由 vools.bridge.configs 解析（用户 JSON / VOOLS_PROJECTS_ROOT /
      环境变量可覆盖），不硬编码用户机器绝对路径
    - 编码注意：p5c 输出为 UTF-8，必须按 UTF-8 解码（Windows 本地编码是 GBK）

典型用法::

    from vools.bridge.pentad import pentad

    @pentad
    def add(x: int, y: int) -> int:
        return "print(x + y)"

    print(add(3, 5))   # -> 8
"""

import os
import sys
import json
import platform
import hashlib
import tempfile
import subprocess
import threading
from typing import Any, Optional, List

from .._base import LangBridge, FunctionSpec, FunctionParser
from ..core.types import LangType

# ----------------------------------------------------------------------------
# 平台判断
# ----------------------------------------------------------------------------
_IS_WINDOWS = platform.system() == 'Windows'

# ----------------------------------------------------------------------------
# Pentad 工具链探测（位置由 configs 统一解析）
# ----------------------------------------------------------------------------

def _find_p5c() -> Optional[str]:
    """按 configs 声明位置与 PATH 查找 p5c 可执行文件。"""
    try:
        from ..configs import resolve_compiler
        resolved = resolve_compiler('pentad')
        if resolved and os.path.exists(resolved):
            return resolved
    except Exception:
        pass
    import shutil
    return shutil.which('p5c')


def _resolve_pentad_command() -> tuple:
    """解析可用的 p5c 命令，返回 (cmd_prefix, path_converter, use_wsl)。

    探测顺序：configs 解析结果 → PATH → WSL 中的 p5c。
    """
    local = _find_p5c()
    if local:
        return ([local], lambda p: p, False)
    from ..core.wsl import resolve_command
    return resolve_command('p5c')


_P5C_CMD, _PATH_CONVERTER, _USE_WSL = _resolve_pentad_command()
_P5C_OK = bool(_P5C_CMD)
_PENTAD_CACHE_DIR = os.path.join(tempfile.gettempdir(), 'vools_pentad_cache')
_pentad_exec_lock = threading.Lock()


def pentad_compiler_available() -> bool:
    """p5c 工具链是否可用。"""
    return _P5C_OK


def get_pentad_version() -> str:
    """获取 p5c 版本号（尽力而为）。"""
    if not _P5C_OK:
        return ''
    try:
        result = subprocess.run(
            _P5C_CMD + ['--version'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=10,
        )
        out = (result.stdout or b'') + (result.stderr or b'')
        text = out.decode('utf-8', errors='replace')
        return text.strip()
    except Exception:
        return ''


def get_pentad_type() -> str:
    """获取 Pentad 类型标识（与其它桥接保持一致）。"""
    return 'pentad'


# ----------------------------------------------------------------------------
# 代码执行
# ----------------------------------------------------------------------------

def _execute_pentad_code(code: str, func_name: str,
                         cache_dir: Optional[str] = None,
                         timeout: int = 60) -> str:
    """把 Pentad 源码写入缓存并执行，返回 stdout。

    Args:
        code: 完整 Pentad 源码。
        func_name: 函数名（文件名用）。
        cache_dir: 缓存目录。
        timeout: 执行超时。

    Returns:
        stdout 文本（UTF-8 解码）。

    Raises:
        RuntimeError: 执行失败时抛出。
    """
    if not _P5C_OK:
        raise RuntimeError('p5c 工具链不可用：请设置 VOOLS_PENTAD_ROOT 或把 p5c 加入 PATH')
    if cache_dir is None:
        cache_dir = _PENTAD_CACHE_DIR
    os.makedirs(cache_dir, exist_ok=True)

    code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
    src_path = os.path.join(cache_dir, 'pentad_{}_{}.p5'.format(func_name, code_hash))

    with _pentad_exec_lock:
        with open(src_path, 'w', encoding='utf-8') as f:
            f.write(code)
        # -q 抑制词法/语法/执行诊断，只保留程序自身 stdout
        result = subprocess.run(
            _P5C_CMD + ['run', '-q', _PATH_CONVERTER(src_path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=timeout,
        )

    stdout_text = result.stdout.decode('utf-8', errors='replace') if result.stdout else ''
    stderr_text = result.stderr.decode('utf-8', errors='replace') if result.stderr else ''

    if result.returncode != 0:
        raise RuntimeError(
            'Pentad 执行失败 (exit {}):\n'
            'stderr:\n{}\nstdout:\n{}\n代码:\n{}'.format(
                result.returncode, stderr_text, stdout_text, code
            )
        )
    return stdout_text.strip()


# ----------------------------------------------------------------------------
# PentadBridge - Pentad 桥接实现（继承 LangBridge）
# ----------------------------------------------------------------------------

class PentadBridge(LangBridge):
    """Pentad 语言桥接实现。

    继承 LangBridge 抽象基类，实现 Pentad 特定的代码生成、执行和调用逻辑。
    Pentad 为执行型语言，产物为 .p5 源文件，执行方式为 `p5c run -q`。
    """

    name = 'pentad'
    is_compiled = False
    lang_type = LangType.INTERPRETED
    file_ext = '.p5'
    lib_ext = '.p5'

    def __init__(self) -> None:
        """初始化 Pentad 桥接器。"""
        super().__init__()

    def compiler_available(self) -> bool:
        """p5c 工具链是否可用。"""
        return pentad_compiler_available()

    def generate_code(self, spec: FunctionSpec) -> str:
        """生成 Pentad 代码（module_code + 主体）。"""
        parts = []
        if spec.module_code:
            parts.append(spec.module_code)
        parts.append(spec.body)
        return '\n'.join(p for p in parts if p)

    def compile_code(self, code: str, func_name: str,
                     cache_dir: Optional[str] = None) -> str:
        """保存 Pentad 源码到缓存目录（直通型语言的'编译'）。

        Args:
            code: Pentad 源代码。
            func_name: 函数名。
            cache_dir: 缓存目录。

        Returns:
            源文件路径。
        """
        if cache_dir is None:
            cache_dir = _PENTAD_CACHE_DIR
        os.makedirs(cache_dir, exist_ok=True)

        code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
        src_path = os.path.join(cache_dir, 'pentad_{}_{}.p5'.format(func_name, code_hash))
        with open(src_path, 'w', encoding='utf-8') as f:
            f.write(code)
        return src_path

    def compile_project(self, project_dir: str, entry: str,
                        output_dir: Optional[str] = None) -> str:
        """处理 Pentad 项目：返回入口 .p5 文件路径。"""
        p5_files = []
        for root, _dirs, files in os.walk(project_dir):
            for f in files:
                if f.endswith('.p5'):
                    p5_files.append(os.path.join(root, f))
        p5_files.sort()
        if not p5_files:
            raise RuntimeError(
                'No .p5 files found in project directory: {}'.format(project_dir)
            )

        if entry == 'main':
            entry_file = os.path.join(project_dir, 'main.p5')
            if os.path.exists(entry_file):
                return entry_file
            return p5_files[0]

        for p5_file in p5_files:
            if os.path.basename(p5_file) == entry or \
                    os.path.splitext(os.path.basename(p5_file))[0] == entry:
                return p5_file
        return p5_files[0]

    def call_func(self, src_path: str, func_name: str,
                  args: tuple, ret_type: Optional[type] = None) -> Any:
        """调用 Pentad 代码：注入 `let` 参数绑定后执行。

        Args:
            src_path: .p5 源文件路径。
            func_name: 函数名。
            args: 参数元组（以 `let argN = <literal>;` 绑定注入源码顶部）。
            ret_type: 返回类型（当前忽略，Pentad 输出为 stdout 文本）。

        Returns:
            执行输出（stdout 文本）。
        """
        with open(src_path, 'r', encoding='utf-8') as f:
            code = f.read()
        if args:
            bindings = '\n'.join(
                'let arg{} = {}'.format(i, _pentad_literal(v))
                for i, v in enumerate(args)
            )
            code = bindings + '\n' + code
        return _execute_pentad_code(code, func_name)

    def _execute_code(self, package_path, func_name, args, ret_type=None):
        """解包 zip 产物并执行 Pentad 源码（LangBridge 解释型入口）。

        Args:
            package_path: 打包 zip 路径（内含 .p5 源文件）。
            func_name: 函数名。
            args: 参数元组。
            ret_type: 返回值类型（当前忽略）。

        Returns:
            执行输出（stdout 文本）。
        """
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

    def run_project(self, project_dir: str, entry: str = 'main',
                    args: tuple = (), cache_dir: Optional[str] = None) -> Any:
        """运行 Pentad 项目：找到入口 .p5 并执行，返回 (returncode, stdout, stderr)。"""
        entry_file = self.compile_project(project_dir, entry, cache_dir)
        result = subprocess.run(
            _P5C_CMD + ['run', '-q', _PATH_CONVERTER(entry_file)] + list(args),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=120,
        )
        out = result.stdout.decode('utf-8', errors='replace') if result.stdout else ''
        err = result.stderr.decode('utf-8', errors='replace') if result.stderr else ''
        return (result.returncode, out, err)


# 全局 PentadBridge 实例
_pentad_bridge = PentadBridge()
pentad = _pentad_bridge.decorator


# ----------------------------------------------------------------------------
# 便捷入口
# ----------------------------------------------------------------------------

def compile_and_run(pentad_code: str, func_name: str = 'main',
                    args: tuple = (), ret_type: Any = None,
                    cache_dir: Optional[str] = None,
                    names: Optional[List[str]] = None) -> Any:
    """直接执行一段 Pentad 源码（无装饰器）。

    Args:
        pentad_code: 完整 Pentad 源码。
        func_name: 函数名（用于文件名）。
        args: 参数（以字面量嵌入；当前直接拼到源码前部）。
        ret_type: 返回类型（可选）。
        cache_dir: 缓存目录（可选）。
        names: 自定义参数名列表（可选）。

    Returns:
        执行结果（最后一行 stdout）。

    Example:
        >>> compile_and_run("print(1 + 2)")
        '3'
        >>> compile_and_run("print(x + y)", args=(3, 5), names=('x', 'y'))
        '8'
    """
    source = pentad_code
    if args:
        if names is None:
            names = ['arg{}'.format(i) for i in range(len(args))]
        bindings = []
        for name, val in zip(names, args):
            bindings.append('let {} = {}'.format(name, _pentad_literal(val)))
        source = '\n'.join(bindings) + '\n' + pentad_code
    output = _execute_pentad_code(source, func_name, cache_dir)
    return _parse_pentad_output(output, ret_type)


def _pentad_literal(val: Any) -> str:
    """把 Python 值转为 Pentad 字面量（尽力而为）。"""
    if isinstance(val, bool):
        return 'True' if val else 'False'
    if isinstance(val, int):
        return str(val)
    if isinstance(val, float):
        return repr(val)
    if isinstance(val, str):
        escaped = val.replace('\\', '\\\\').replace('"', '\\"')
        return '"{}"'.format(escaped)
    return repr(val)


def _parse_pentad_output(output: str, ret_type: Any = None) -> Any:
    """解析 Pentad 执行输出为 Python 值（标量字符串化，尽力而为）。"""
    text = output.strip()
    if not text:
        return ''
    # 取最后一行作为结果
    line = text.split('\n')[-1].strip()
    return line


__all__ = [
    'PentadBridge',
    'pentad',
    '_pentad_bridge',
    'pentad_bridge',
    'compile_and_run',
    'pentad_compiler_available',
    'get_pentad_version',
    'get_pentad_type',
]

# 别名：与其它语言模块保持一致
pentad_bridge = _pentad_bridge