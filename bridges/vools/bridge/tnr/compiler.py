"""
vools.bridge.tnr.compiler - Tnr 语言桥接实现（单文件）

Tnr 是面向 AI 的张量数学语言（公式即代码，Rust 实现）。
本模块提供：
    - TnrBridge 类：继承 LangBridge，实现 Tnr 特定的代码生成、解释执行与调用
    - tnr 装饰器：将 Python 函数转换为 Tnr 代码执行（函数体即 Tnr 代码）
    - compile_and_run：直接执行一段 Tnr 源码（无装饰器）
    - tnr_compiler_available：探测 Tnr 工具链（本机已知路径 → PATH → WSL）

设计要点：
    - 解释型语言：lang_type = INTERPRETED，产物为 .tnr 源文件
    - 参数传递：Python 参数以 Tnr 字面量直接嵌入生成的源码（张量用 [[..],[..]] 语法）
    - 输出解析：tnr run 逐行打印，标量输出形如 Tensor<int64, []>(3)，自动解析回 Python 值
    - 工具链探测：优先 target/release 与 target/debug 已知产物，其次 PATH，再次 WSL

典型用法::

    from vools.bridge.tnr import tnr

    @tnr
    def add(x: int, y: int) -> int:
        return "print(x + y);"

    print(add(3, 5))   # -> 8
"""

import os
import sys
import json
import platform
import hashlib
import tempfile
import textwrap
import subprocess
import threading
from typing import Any, Optional, List

from .._base import LangBridge, FunctionSpec, FunctionParser
from ..core.types import LangType
from ..core.wsl import resolve_command

# ----------------------------------------------------------------------------
# 平台判断
# ----------------------------------------------------------------------------
_IS_WINDOWS = platform.system() == 'Windows'

# ----------------------------------------------------------------------------
# Tnr 工具链探测
# ----------------------------------------------------------------------------

# 本机已知的 tnr 可执行文件候选（Tnr 项目常用产物路径）
_TNR_PROJECT_CANDIDATES = (
    r'E:\IDEProjects\AI\Tnr\target\release\tnr.exe',
    r'E:\IDEProjects\AI\Tnr\target\debug\tnr.exe',
)


def _find_local_tnr() -> Optional[str]:
    """在本机已知路径与 PATH 中查找 tnr 可执行文件。"""
    for cand in _TNR_PROJECT_CANDIDATES:
        if os.path.isfile(cand):
            return cand
    import shutil
    found = shutil.which('tnr')
    return found


def _resolve_tnr_command() -> tuple:
    """解析可用的 Tnr 命令，返回 (cmd_prefix, path_converter, use_wsl)。

    探测顺序：本机已知产物 → PATH → WSL 中的 tnr。
    """
    local = _find_local_tnr()
    if local:
        return ([local], lambda p: p, False)
    cmd_prefix, path_converter, use_wsl = resolve_command('tnr')
    # 验证可用性
    try:
        result = subprocess.run(
            cmd_prefix + ['version'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, errors='replace', timeout=10,
        )
        if result.returncode == 0:
            return cmd_prefix, path_converter, use_wsl
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        pass
    except Exception:
        pass
    return cmd_prefix, path_converter, use_wsl


_TNR_CMD, _PATH_CONVERTER, _USE_WSL = _resolve_tnr_command()

# 缓存目录
_TNR_CACHE_DIR = os.path.join(tempfile.gettempdir(), 'vools_tnr_cache')

# 保护同名临时文件的并发写入
_tnr_exec_lock = threading.Lock()


def tnr_compiler_available() -> bool:
    """检查 Tnr 工具链是否可用（执行 tnr version）。"""
    try:
        result = subprocess.run(
            _TNR_CMD + ['version'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, errors='replace', timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, OSError):
        return False
    except Exception:
        return False


def get_tnr_version() -> str:
    """获取 Tnr 版本号（不可用时返回空字符串）。"""
    try:
        result = subprocess.run(
            _TNR_CMD + ['version'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, errors='replace', timeout=10,
        )
        if result.returncode == 0:
            return (result.stdout or result.stderr).strip()
    except Exception:
        pass
    return ''


# ----------------------------------------------------------------------------
# Python ↔ Tnr 类型映射
# ----------------------------------------------------------------------------

_TNR_TYPE_ALIASES = {
    'int': 'int64',
    'int64': 'int64',
    'integer': 'int64',
    'float': 'float64',
    'float64': 'float64',
    'double': 'float64',
    'number': 'float64',
    'str': 'string',
    'string': 'string',
    'bool': 'bool',
    'boolean': 'bool',
    'list': 'tensor',
    'array': 'tensor',
    'tensor': 'tensor',
    'none': 'unit',
    'nonetype': 'unit',
}


def get_tnr_type(py_type) -> str:
    """根据 Python 类型获取 Tnr 端类型字符串。"""
    if py_type is int:
        return 'int64'
    if py_type is float:
        return 'float64'
    if py_type is str:
        return 'string'
    if py_type is bool:
        return 'bool'
    if py_type in (list, tuple):
        return 'tensor'
    if py_type is type(None):
        return 'unit'
    if isinstance(py_type, str):
        normalized = py_type.strip().lower()
        if normalized in _TNR_TYPE_ALIASES:
            return _TNR_TYPE_ALIASES[normalized]
        short = normalized.split('.')[-1]
        if short in _TNR_TYPE_ALIASES:
            return _TNR_TYPE_ALIASES[short]
    return 'int64'


def _literal_to_tnr(value: Any) -> str:
    """把 Python 值转成 Tnr 字面量（嵌入生成源码用）。"""
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
        return '[' + ', '.join(_literal_to_tnr(v) for v in value) + ']'
    if isinstance(value, dict):
        items = ', '.join(
            '{}: {}'.format(_literal_to_tnr(k), _literal_to_tnr(v))
            for k, v in value.items()
        )
        return '{' + items + '}'
    return json.dumps(str(value), ensure_ascii=False)


# ----------------------------------------------------------------------------
# 输出解析
# ----------------------------------------------------------------------------

_TENSOR_RE = None


def _parse_scalar(text: str):
    """把字符串尝试解析为 int / float，失败返回原字符串。"""
    try:
        return int(text)
    except (ValueError, TypeError):
        pass
    try:
        return float(text)
    except (ValueError, TypeError):
        return text


def _parse_tensor_notation(line: str):
    """解析 Tnr 的 Tensor 输出表示。

    支持形式：
        Tensor<int64, []>(3)          -> 3
        Tensor<float64, [2]>(1.0,2.0) -> [1.0, 2.0]
        Tensor<int64, [2,2]>(...)     -> 嵌套列表
    非 Tensor 行原样返回。
    """
    text = line.strip()
    if text.startswith('Tensor<'):
        inner = text[len('Tensor<'):]
        # 拆出类型与值：type, [shape]>(value)
        brace = inner.find('>(')
        if brace > 0:
            head = inner[:brace]
            value_part = inner[brace + 2:]
            if value_part.endswith(')'):
                value_part = value_part[:-1]
            # head 形如 "int64, []" 或 "float64, [2,2]"
            decl = head
            parts = [p.strip() for p in decl.split(',')]
            shape = parts[1] if len(parts) > 1 else '[]'
            value = value_part.strip()
            if shape == '[]' or shape == '':
                # 标量：直接转数字（去掉可能的引号）
                cleaned = value.strip().strip('"\'')
                return _parse_scalar(cleaned)
            # 张量：尝试 JSON 解析（tnr 输出通常为嵌套列表）
            if value.startswith('['):
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    pass
            # 逗号分隔的扁平行（如 1,2,3）
            if ',' in value:
                try:
                    return [_parse_scalar(v.strip()) for v in value.split(',')]
                except Exception:
                    pass
            return value
    return text


def _parse_tnr_output(output: str, ret_type: Any = None) -> Any:
    """解析 tnr run 的完整输出。

    逐行解析，返回最后一行（解析后的值）；空输出返回 None。
    """
    lines = [ln for ln in output.splitlines() if ln.strip()]
    if not lines:
        return None
    last = lines[-1]
    parsed = _parse_tensor_notation(last)

    # 按期望返回类型做二次转换
    if ret_type is not None:
        try:
            if ret_type is int and not isinstance(parsed, bool):
                return int(parsed)
            if ret_type is float:
                return float(parsed)
            if ret_type is str:
                return str(parsed) if not isinstance(parsed, str) else parsed
            if ret_type is bool:
                if isinstance(parsed, str):
                    return parsed.strip().lower() in ('true', '1')
                return bool(parsed)
        except (ValueError, TypeError):
            return parsed
    return parsed


# ----------------------------------------------------------------------------
# 代码生成
# ----------------------------------------------------------------------------

def _generate_tnr_source(
    func_name: str,
    arg_names: List[str],
    arg_values: tuple,
    body: str,
    module_code: str = '',
    deps_code: str = '',
) -> str:
    """生成完整的 Tnr 源码。

    参数以字面量直接嵌入源码顶部（Tnr 张量字面量语法 [[..],[..]]），
    body 为用户提供的 Tnr 语句序列。

    Args:
        func_name: 函数名（用于注释标记）。
        arg_names: 参数名列表。
        arg_values: Python 参数值元组。
        body: 函数体 Tnr 代码。
        module_code: 模块级代码（可选）。
        deps_code: 依赖函数代码（可选）。

    Returns:
        完整的 .tnr 源码字符串。
    """
    parts = []
    parts.append('// vools.tnr bridge: {}'.format(func_name))
    parts.append('')

    if module_code:
        parts.append(module_code)
        parts.append('')

    if deps_code:
        parts.append(deps_code)
        parts.append('')

    # 参数绑定：let argN = <字面量>;
    for name, value in zip(arg_names, arg_values):
        parts.append('let {} = {};'.format(name, _literal_to_tnr(value)))
    if arg_names:
        parts.append('')

    # 主代码
    parts.append(body)

    return '\n'.join(parts)


# ----------------------------------------------------------------------------
# 执行逻辑
# ----------------------------------------------------------------------------

def _execute_tnr_code(code: str, func_name: str, cache_dir: Optional[str] = None,
                      timeout: int = 60) -> str:
    """执行 Tnr 代码并返回 stdout 输出。

    Args:
        code: 完整 Tnr 源码。
        func_name: 函数名（用于生成文件名）。
        cache_dir: 缓存目录，None 则使用默认缓存目录。
        timeout: 执行超时秒数。

    Returns:
        Tnr 执行的 stdout 输出（strip 后）。

    Raises:
        RuntimeError: 执行失败时抛出（携带 stderr 与代码）。
    """
    if cache_dir is None:
        cache_dir = _TNR_CACHE_DIR
    os.makedirs(cache_dir, exist_ok=True)

    code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
    src_path = os.path.join(cache_dir, 'tnr_{}_{}.tnr'.format(func_name, code_hash))

    with _tnr_exec_lock:
        with open(src_path, 'w', encoding='utf-8') as f:
            f.write(code)

        result = subprocess.run(
            _TNR_CMD + ['run', _PATH_CONVERTER(src_path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, errors='replace', timeout=timeout,
        )

    if result.returncode != 0:
        raise RuntimeError(
            'Tnr 执行失败 (exit {}):\n'
            'stderr:\n{}\nstdout:\n{}\n代码:\n{}'.format(
                result.returncode, result.stderr, result.stdout, code
            )
        )
    return result.stdout.strip()


# ----------------------------------------------------------------------------
# TnrBridge - Tnr 桥接实现（继承 LangBridge）
# ----------------------------------------------------------------------------

class TnrBridge(LangBridge):
    """Tnr 语言桥接实现。

    继承 LangBridge 抽象基类，实现 Tnr 特定的代码生成、解释执行和调用逻辑。
    Tnr 是解释型张量语言，产物为 .tnr 源文件，执行方式为 `tnr run`。
    """

    name = 'tnr'
    is_compiled = False
    lang_type = LangType.INTERPRETED
    file_ext = '.tnr'
    lib_ext = '.tnr'

    def __init__(self) -> None:
        """初始化 Tnr 桥接器。"""
        super().__init__()

    def compiler_available(self) -> bool:
        """Tnr 工具链是否可用。"""
        return tnr_compiler_available()

    def generate_code(self, spec: FunctionSpec) -> str:
        """生成 Tnr 代码。

        包含模块级代码、依赖函数与主函数体（函数体即 Tnr 语句序列）。

        Args:
            spec: 函数规格。

        Returns:
            Tnr 源码字符串。
        """
        parts = []

        if spec.module_code:
            parts.append(spec.module_code)

        deps_code_parts = []
        for dep in spec.dependencies:
            deps_code_parts.append(dep.body)
        if deps_code_parts:
            parts.append('\n'.join(deps_code_parts))

        parts.append(spec.body)

        return '\n\n'.join(p for p in parts if p)

    def compile_code(self, code: str, func_name: str,
                     cache_dir: Optional[str] = None) -> str:
        """保存 Tnr 源码到缓存目录（解释型语言的'编译'）。

        Args:
            code: Tnr 源代码。
            func_name: 函数名（用于生成文件名）。
            cache_dir: 缓存目录。

        Returns:
            源文件路径。
        """
        if cache_dir is None:
            cache_dir = _TNR_CACHE_DIR
        os.makedirs(cache_dir, exist_ok=True)

        code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
        src_path = os.path.join(cache_dir, 'tnr_{}_{}.tnr'.format(func_name, code_hash))

        with open(src_path, 'w', encoding='utf-8') as f:
            f.write(code)
        return src_path

    def _package_code(self, code: str, func_name: str,
                      cache_dir: Optional[str] = None) -> str:
        """打包 Tnr 源码为 zip（带内容哈希命名，避免同名函数缓存失效）。

        基类默认按函数名缓存 zip（{func_name}_package.zip），函数体变更后
        会复用旧包导致执行旧代码；这里用 函数名+代码md5 命名，内容变了
        包名即变，天然失效。

        Args:
            code: 完整 Tnr 源码。
            func_name: 函数名。
            cache_dir: 缓存目录。

        Returns:
            zip 打包产物路径。
        """
        import zipfile
        if cache_dir is None:
            cache_dir = _TNR_CACHE_DIR
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

    def compile_project(self, project_dir: str, entry: str,
                        output_dir: Optional[str] = None) -> str:
        """处理 Tnr 项目。

        Tnr 是解释型语言，项目模式含义：
        - 扫描 project_dir 下所有 .tnr 文件；
        - entry='main' 时：返回主文件路径（project_dir/main.tnr 或第一个 .tnr）；
        - entry!='main' 时：把所有 .tnr 文件合并为一个可执行文件并返回。

        Args:
            project_dir: 项目目录。
            entry: 入口（'main' 或函数名）。
            output_dir: 输出目录。

        Returns:
            产物路径。

        Raises:
            RuntimeError: 项目目录中无 .tnr 文件时抛出。
        """
        output_dir = output_dir or _TNR_CACHE_DIR
        os.makedirs(output_dir, exist_ok=True)

        tnr_files = []
        for root, _dirs, files in os.walk(project_dir):
            for f in files:
                if f.endswith('.tnr'):
                    tnr_files.append(os.path.join(root, f))
        tnr_files.sort()
        if not tnr_files:
            raise RuntimeError('No .tnr files found in project directory: {}'.format(project_dir))

        if entry == 'main':
            main_tnr = os.path.join(project_dir, 'main.tnr')
            if os.path.exists(main_tnr):
                return main_tnr
            return tnr_files[0]

        # entry != 'main'：合并所有文件，末尾调用入口（Tnr 无显式入口调用时
        # 直接拼接全部代码，保持模块级可见性）
        project_hash = self._get_project_hash(project_dir)[:12]
        project_name = os.path.basename(os.path.abspath(project_dir))
        output_path = os.path.join(
            output_dir, 'tnr_proj_{}_{}_{}.tnr'.format(project_name, entry, project_hash)
        )
        if os.path.exists(output_path):
            return output_path

        all_code = []
        all_code.append('// vools.tnr project: {} entry={}'.format(project_name, entry))
        for tnr_file in tnr_files:
            rel_path = os.path.relpath(tnr_file, project_dir)
            all_code.append('// --- {} ---'.format(rel_path))
            with open(tnr_file, 'r', encoding='utf-8') as f:
                all_code.append(f.read())
            all_code.append('')

        final_code = '\n'.join(all_code)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(final_code)
        return output_path

    def _execute_code(self, package_path: str, func_name: str,
                      args: tuple, ret_type: Optional[type] = None) -> Any:
        """解包 zip 产物并执行其中 Tnr 源码。

        LangBridge 对解释型语言默认把源码打包为 zip（_package_code），
        这里解包出 .tnr 源文件后交给 call_func 执行。

        Args:
            package_path: zip 打包产物路径。
            func_name: 函数名（对应包内源文件名）。
            args: Python 参数。
            ret_type: 期望返回类型。

        Returns:
            解析后的执行结果。
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

    def call_func(self, src_path: str, func_name: str,
                  args: tuple, ret_type: Optional[type] = None) -> Any:
        """调用 Tnr 代码（写入参数绑定并执行 `tnr run`）。

        Args:
            src_path: .tnr 源文件路径。
            func_name: 函数名。
            args: 参数元组（以字面量嵌入源码）。
            ret_type: 返回类型注解。

        Returns:
            函数执行结果。
        """
        with open(src_path, 'r', encoding='utf-8') as f:
            code = f.read()

        arg_names = ['arg{}'.format(i) for i in range(len(args))]
        full_code = _generate_tnr_source(
            func_name=func_name,
            arg_names=arg_names,
            arg_values=args,
            body=code,
        )
        output = _execute_tnr_code(full_code, func_name)
        return _parse_tnr_output(output, ret_type)

    def run_project(self, project_dir: str, entry: str = 'main',
                    args: tuple = (), cache_dir: Optional[str] = None) -> Any:
        """运行 Tnr 项目。

        Args:
            project_dir: 项目目录。
            entry: 入口（'main' 或函数名）。
            args: 参数（entry='main' 时透传给 CLI）。
            cache_dir: 缓存目录。

        Returns:
            entry='main' 时返回 (returncode, stdout, stderr)；
            否则返回函数调用结果。
        """
        if entry == 'main':
            main_tnr = self.compile_project(project_dir, 'main', cache_dir)
            result = subprocess.run(
                _TNR_CMD + ['run', _PATH_CONVERTER(main_tnr)] + list(args),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, errors='replace', timeout=60,
            )
            return (result.returncode, result.stdout, result.stderr)
        artifact_path = self.compile_project(project_dir, entry, cache_dir)
        return self.call_func(artifact_path, entry, args)


# 全局 TnrBridge 实例
_tnr_bridge = TnrBridge()
tnr = _tnr_bridge.decorator


# ----------------------------------------------------------------------------
# 便捷入口
# ----------------------------------------------------------------------------

def compile_and_run(tnr_code: str, func_name: str = 'main',
                    args: tuple = (), ret_type: Any = None,
                    cache_dir: Optional[str] = None,
                    names: Optional[List[str]] = None) -> Any:
    """直接执行一段 Tnr 源码（无装饰器）。

    参数绑定约定：默认参数名为 arg0/arg1/...，body 中直接引用；
    也可通过 names 指定自定义参数名（长度须与 args 一致）。

    Args:
        tnr_code: 完整 Tnr 源码。
        func_name: 函数名（用于文件名）。
        args: Python 位置参数（以字面量嵌入）。
        ret_type: 返回类型（可选）。
        cache_dir: 缓存目录（可选）。
        names: 自定义参数名列表（可选，默认 arg0/arg1/...）。

    Returns:
        执行结果（解析后的最后一行输出）。

    Example:
        >>> compile_and_run("print(1 + 2);")
        3
        >>> compile_and_run("print(x + y);", args=(3, 5), names=("x", "y"))
        8
    """
    if names is None:
        arg_names = ['arg{}'.format(i) for i in range(len(args))]
    else:
        if len(names) != len(args):
            raise ValueError('names 长度必须与 args 一致')
        arg_names = list(names)
    source = _generate_tnr_source(
        func_name=func_name,
        arg_names=arg_names,
        arg_values=args,
        body=tnr_code,
    )
    output = _execute_tnr_code(source, func_name, cache_dir)
    return _parse_tnr_output(output, ret_type)


def run_tnr_file(tnr_file: str, args: tuple = ()) -> tuple:
    """直接运行一个 .tnr 文件（不进缓存），返回 (returncode, stdout, stderr)。

    Args:
        tnr_file: .tnr 文件绝对路径。
        args: 透传给 CLI 的参数。

    Returns:
        (returncode, stdout, stderr) 三元组。
    """
    result = subprocess.run(
        _TNR_CMD + ['run', _PATH_CONVERTER(tnr_file)] + list(args),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, errors='replace', timeout=60,
    )
    return (result.returncode, result.stdout, result.stderr)


__all__ = [
    'TnrBridge',
    'tnr',
    '_tnr_bridge',
    'tnr_bridge',
    'compile_and_run',
    'run_tnr_file',
    'tnr_compiler_available',
    'get_tnr_version',
    'get_tnr_type',
    '_parse_tnr_output',
]

# 别名：与其它语言模块保持一致
tnr_bridge = _tnr_bridge
