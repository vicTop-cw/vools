"""vools.bridge.bat.compiler - Windows 批处理（bat/cmd/batch）语言桥接实现

提供 BatBridge 类，继承 LangBridge 抽象基类，实现批处理脚本的打包与执行。

- 语言标记：bat（主名）；cmd / batch 通过模块级 BRIDGE_ALIASES 声明别名，
  get_bridge 的约定式自动发现会把同一实例挂到别名名下。
- 执行后端：Windows 下用系统自带 cmd.exe（``cmd /d /s /c <script>``）；
  非 Windows 平台显式报不可用（returncode 非 0）。
- 编码约定：脚本按 UTF-8（无 BOM）写入，执行前置 ``chcp 65001 >nul``，
  保证含中文内容的批处理在默认 OEM 代码页（GBK）下不乱码。

任意语言即入口的约定（源头机制）：
    在 ``vools/bridge/<lang>/compiler.py`` 提供模块级 bridge 实例
    （``_<lang>_bridge`` 或 ``bridge``），并可选声明 ``BRIDGE_ALIASES``
    元组，即可零改代码成为 md runner 的语言入口。
"""


__all__ = [
    "bat_compiler_available",
    "BatBridge",
    "compile_and_run",
    "compiler_available",
    "generate_code",
    "compile_code",
    "compile_project",
    "call_func",
    "BRIDGE_ALIASES",
]

import os
import shutil
import tempfile
import hashlib
import platform
import subprocess
import zipfile
from typing import Any, Optional

from .._base import LangBridge, FunctionSpec
from ..core.types import LangType

_IS_WINDOWS = platform.system() == 'Windows'

_BAT_CACHE_DIR = os.path.join(tempfile.gettempdir(), 'vools_bat_cache')


def bat_compiler_available() -> bool:
    """cmd.exe 是 Windows 系统组件：Windows 上必然可用，其它平台不可用。"""
    if not _IS_WINDOWS:
        return False
    if shutil.which('cmd.exe'):
        return True
    system_root = os.environ.get('SystemRoot', r'C:\Windows')
    return os.path.exists(os.path.join(system_root, 'System32', 'cmd.exe'))


def _write_bat(path: str, code: str) -> None:
    """写入 UTF-8（无 BOM）批处理脚本，前置 chcp 65001 避免中文乱码。"""
    header = '@echo off\r\nchcp 65001 >nul\r\n'
    with open(path, 'w', encoding='utf-8', newline='\r\n') as f:
        f.write(header)
        f.write(code)
        if not code.endswith(('\n', '\r')):
            f.write('\r\n')


def _run_bat_script(script_path: str, args: tuple = (), timeout: int = 60) -> Optional[str]:
    """用 cmd.exe 执行 .bat 脚本，返回 stdout 文本；失败返回 None。"""
    if not _IS_WINDOWS:
        raise RuntimeError("bat/cmd 仅支持 Windows 平台")

    cmd = ['cmd.exe', '/d', '/s', '/c', script_path]
    cmd.extend(str(a) for a in args)

    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError):
        return None

    # chcp 65001 后输出为 UTF-8；兜底 errors='replace' 保证不炸
    out = proc.stdout.decode('utf-8', errors='replace')
    err = proc.stderr.decode('utf-8', errors='replace')
    if proc.returncode != 0 and err:
        out = (out + '\n' if out else '') + err
    return out


class BatBridge(LangBridge):
    """Windows 批处理语言桥接（bat / cmd / batch）。"""

    name = 'bat'
    is_compiled = False
    lang_type = LangType.INTERPRETED
    file_ext = '.bat'
    lib_ext = '.bat'

    def __init__(self):
        super().__init__()
        try:
            os.makedirs(_BAT_CACHE_DIR, exist_ok=True)
        except OSError:
            pass

    def compiler_available(self) -> bool:
        return bat_compiler_available()

    def generate_code(self, spec: FunctionSpec) -> str:
        """根据函数规格生成批处理源码。"""
        body = (spec.body or '').strip()
        lines = ['@echo off', 'setlocal']
        if body:
            lines.append(body)
        lines.append('endlocal')
        return '\r\n'.join(lines)

    def compile_code(self, code: str, func_name: str, cache_dir: str = None) -> str:
        """批处理为解释型语言：“编译产物”即写入的 .bat 源文件路径。"""
        if cache_dir is None:
            cache_dir = _BAT_CACHE_DIR
        os.makedirs(cache_dir, exist_ok=True)

        code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
        src_path = os.path.join(cache_dir, f'bat_{func_name}_{code_hash}.bat')
        if os.path.exists(src_path):
            return src_path
        _write_bat(src_path, code)
        return src_path

    def compile_project(self, project_dir: str, entry: str,
                        output_dir: str = None) -> str:
        """收集项目下全部 .bat 文件，按 entry 拼接为单个可执行批处理。"""
        output_dir = output_dir or _BAT_CACHE_DIR
        os.makedirs(output_dir, exist_ok=True)

        bat_files = []
        for root, _dirs, files in os.walk(project_dir):
            for f in files:
                if f.lower().endswith('.bat'):
                    bat_files.append(os.path.join(root, f))
        if not bat_files:
            raise RuntimeError(f'No .bat files found in project directory: {project_dir}')
        bat_files.sort()

        project_name = os.path.basename(os.path.abspath(project_dir))

        if entry == 'main':
            main_bat = os.path.join(project_dir, 'main.bat')
            if os.path.exists(main_bat):
                return main_bat
            return bat_files[0]

        project_hash = hashlib.md5(
            os.path.abspath(project_dir).encode('utf-8')).hexdigest()[:12]
        output_path = os.path.join(
            output_dir, f'bat_proj_{project_name}_{entry}_{project_hash}.bat')
        if os.path.exists(output_path):
            return output_path

        lines = ['@echo off', 'setlocal',
                 f'REM Auto-generated from project: {project_name}']
        for bat_file in bat_files:
            rel_path = os.path.relpath(bat_file, project_dir)
            lines.append(f'REM --- {rel_path} ---')
            with open(bat_file, 'r', encoding='utf-8') as f:
                lines.append(f.read())
        lines.append(f'call :{entry} %*')
        lines.append('endlocal')

        _write_bat(output_path, '\r\n'.join(lines))
        return output_path

    def call_func(self, src_path: str, func_name: str,
                  args: tuple, ret_type=None) -> Any:
        output = _run_bat_script(src_path, args)
        if output is None:
            raise RuntimeError(f"bat execution failed for '{func_name}'")
        return output

    def _execute_code(self, package_path, func_name, args, ret_type=None):
        """解包 zip 并通过 cmd.exe 执行批处理脚本。"""
        if not _IS_WINDOWS:
            raise RuntimeError("bat/cmd 仅支持 Windows 平台")

        tmpdir = tempfile.mkdtemp(prefix='vools_bat_')
        try:
            with zipfile.ZipFile(package_path, 'r') as zf:
                zf.extractall(tmpdir)

            source_file = os.path.join(tmpdir, self.get_source_filename(func_name))
            with open(source_file, 'r', encoding='utf-8') as f:
                code = f.read()

            script_path = os.path.join(tmpdir, 'run.bat')
            _write_bat(script_path, code)

            output = _run_bat_script(script_path, args)
            if output is None:
                raise RuntimeError(f"bat execution failed for '{func_name}'")
            return output
        finally:
            try:
                import shutil as _shutil
                _shutil.rmtree(tmpdir, ignore_errors=True)
            except Exception:
                pass


_bat_bridge = BatBridge()
bridge = _bat_bridge

#: 声明别名：约定式自动发现会把同一实例挂到 cmd / batch 名下
BRIDGE_ALIASES = ('cmd', 'batch')


def compile_and_run(code: str, func_name: str = 'main',
                    args: tuple = (), ret_type=None,
                    cache_dir: str = None) -> Any:
    bridge = _bat_bridge
    src_path = bridge.compile_code(code, func_name, cache_dir)
    return bridge.call_func(src_path, func_name, args, ret_type)


bat = _bat_bridge.decorator

