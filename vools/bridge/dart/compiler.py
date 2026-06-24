"""
vools.bridge.dart.compiler - Dart 语言桥接编译器实现

提供 Dart 动态编译与跨语言桥接能力，继承 LangBridge 抽象基类。

Dart 编译：
- dart compile exe: 编译为本地可执行文件
- dart run: 直接运行 Dart 脚本
- 通过 subprocess 执行，JSON 序列化传递参数
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

logger = logging.getLogger(__name__)

_IS_WINDOWS = platform.system() == 'Windows'
_IS_LINUX = platform.system() == 'Linux'
_IS_MACOS = platform.system() == 'Darwin'

_DART_CACHE_DIR = os.path.join(tempfile.gettempdir(), 'vools_dart_cache')


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


def _check_wsl_dart() -> bool:
    """检查 WSL 中是否有 dart"""
    try:
        result = subprocess.run(
            ['wsl', 'dart', '--version'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=10
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


_USE_WSL = _IS_WINDOWS and shutil.which('dart') is None and _check_wsl() and _check_wsl_dart()


def _to_wsl_path(windows_path: str) -> str:
    """将 Windows 路径转换为 WSL 路径"""
    if not os.path.isabs(windows_path):
        windows_path = os.path.abspath(windows_path)
    drive = windows_path[0].lower()
    rest = windows_path[2:].replace('\\', '/')
    return f'/mnt/{drive}{rest}'


def _find_dart() -> Optional[str]:
    """查找 dart 命令路径"""
    import shutil
    return shutil.which('dart')


def dart_compiler_available() -> bool:
    """检查 Dart 编译器是否可用"""
    if _find_dart() is not None:
        return True
    return _USE_WSL


def get_dart_version() -> Optional[str]:
    """获取 Dart 版本信息"""
    dart_path = _find_dart()
    if dart_path is None:
        return None

    try:
        result = subprocess.run(
            ['dart', '--version'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )
        return result.stdout.strip() or result.stderr.strip()
    except Exception:
        return None


def _dart_exe_ext() -> str:
    """返回当前平台下可执行文件的扩展名"""
    if _USE_WSL:
        return ''
    if _IS_WINDOWS:
        return '.exe'
    return ''


# ----------------------------------------------------------------------------
# 异步执行
# ----------------------------------------------------------------------------

_executor = ThreadPoolExecutor(max_workers=4)
_executor_lock = threading.Lock()


class DartFuture:
    """
    Dart 异步执行 Future

    仿 NimFuture / MojoFuture，对 ThreadPoolExecutor.Future 做薄包装。
    支持 .result() / .done() / .add_done_callback() / .cancel() / __await__。
    """

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
        """
        将 DartFuture 适配为 asyncio 可 await 对象
        """
        return asyncio.wrap_future(self._future).__await__()


# ----------------------------------------------------------------------------
# Dart 代码生成
# ----------------------------------------------------------------------------

def _generate_dart_source(
    func_name: str,
    params: List[tuple],
    ret_dart_type: str,
    body: str,
    module_code: str = '',
    dependencies: List[FunctionSpec] = None,
) -> str:
    """
    生成完整的 Dart 源码

    参数：
        func_name: 函数名
        params: 参数列表 [(name, dart_type), ...]
        ret_dart_type: Dart 返回类型
        body: 函数体代码
        module_code: 模块级代码
        dependencies: 依赖函数列表

    返回：
        完整 Dart 源码字符串
    """
    parts = []

    parts.append("import 'dart:convert';")
    parts.append("import 'dart:io';")
    parts.append("import 'dart:async';")
    parts.append('')

    # 模块级代码
    if module_code:
        parts.append(module_code)
        parts.append('')

    # 依赖函数
    if dependencies:
        for dep in dependencies:
            dep_params = []
            for name, ann in dep.annotations.items():
                if name == 'return':
                    continue
                dep_ret_type = 'String'
                if ann is not None:
                    dep_ret_type = ann if isinstance(ann, str) else 'String'
                dep_params.append((name, dep_ret_type))

            dep_ret = 'String'
            if 'return' in dep.annotations:
                ret_ann = dep.annotations['return']
                if ret_ann is not type(None) and ret_ann is not None:
                    dep_ret = ret_ann if isinstance(ret_ann, str) else 'String'

            dep_params_str = ', '.join([f'{t} {n}' for n, t in dep_params])
            dep_body = textwrap.dedent(dep.body).strip() if dep.body else ''
            indented_body = ''
            for line in dep_body.split('\n'):
                if line.strip():
                    indented_body += '    ' + line + '\n'
                else:
                    indented_body += '\n'

            parts.append(f'String {dep.name}({dep_params_str}) {{')
            parts.append(indented_body)
            parts.append('}')
            parts.append('')

    # 主函数
    params_str = ', '.join([f'{t} {n}' for n, t in params])

    ret_sig = '' if ret_dart_type == 'void' else f' -> {ret_dart_type}'

    body = textwrap.dedent(body).strip() if body else ''
    indented_body = ''
    for line in body.split('\n'):
        if line.strip():
            indented_body += '    ' + line + '\n'
        else:
            indented_body += '\n'

    func_def = f'String {func_name}({params_str}) {{'
    if ret_dart_type != 'void':
        func_def = f'{ret_dart_type} {func_name}({params_str}) {{'

    parts.append(func_def)
    parts.append(indented_body)
    parts.append('}')
    parts.append('')

    # main 函数 - 通过 stdin/stdout 传递参数和结果
    parts.append('void main() {')
    parts.append('    final stdin = stdinLineStream();')
    parts.append('    stdin.listen((line) {')
    parts.append('        if (line.trim().isEmpty) return;')
    parts.append('        try {')
    parts.append('            final data = jsonDecode(line);')
    parts.append('            final args = List<dynamic>.from(data[\'args\']);')
    parts.append('            final funcName = data[\'func\'] as String;')
    parts.append('')
    parts.append('            dynamic result;')
    parts.append('            switch (funcName) {')

    # 为每个函数生成 case
    if dependencies:
        for dep in dependencies:
            dep_params = []
            dep_param_names = []
            for name, ann in dep.annotations.items():
                if name == 'return':
                    continue
                dep_ret_type = 'String'
                if ann is not None:
                    dep_ret_type = ann if isinstance(ann, str) else 'String'
                dep_params.append((name, dep_ret_type))
                dep_param_names.append(name)

            dep_param_access = []
            for i, (n, t) in enumerate(dep_params):
                if t == 'int':
                    dep_param_access.append(f'args[{i}] as int')
                elif t == 'double':
                    dep_param_access.append(f'args[{i}] as double')
                elif t == 'bool':
                    dep_param_access.append(f'args[{i}] as bool')
                else:
                    dep_param_access.append(f'args[{i}].toString()')

            dep_call_args = ', '.join(dep_param_access)
            dep_ret = 'String'
            if 'return' in dep.annotations:
                ret_ann = dep.annotations['return']
                if ret_ann is not type(None) and ret_ann is not None:
                    dep_ret = ret_ann if isinstance(ret_ann, str) else 'String'

            parts.append(f"                case '{dep.name}':")
            if dep_ret == 'void':
                parts.append(f'                    {dep.name}({dep_call_args});')
                parts.append("                    result = 'OK';")
            else:
                parts.append(f'                    result = {dep.name}({dep_call_args});')
            parts.append('                    break;')

    # 主函数 case
    param_access = []
    for i, (n, t) in enumerate(params):
        if t == 'int':
            param_access.append(f'args[{i}] as int')
        elif t == 'double':
            param_access.append(f'args[{i}] as double')
        elif t == 'bool':
            param_access.append(f'args[{i}] as bool')
        else:
            param_access.append(f'args[{i}].toString()')

    call_args = ', '.join(param_access)

    parts.append(f"                case '{func_name}':")
    if ret_dart_type == 'void':
        parts.append(f'                    {func_name}({call_args});')
        parts.append("                    result = 'OK';")
    else:
        parts.append(f'                    result = {func_name}({call_args});')
    parts.append('                    break;')

    parts.append('                default:')
    parts.append("                    throw Exception('Unknown function: $funcName');")
    parts.append('            }')
    parts.append('')
    parts.append("            stdout.writeln(jsonEncode({'result': result}));")
    parts.append('        } catch (e) {')
    parts.append("            stderr.writeln('ERROR: $e');")
    parts.append('        }')
    parts.append('    });')
    parts.append('}')
    parts.append('')

    # 辅助函数：按行读取 stdin
    parts.append('Stream<String> stdinLineStream() {')
    parts.append('    final controller = StreamController<String>();')
    parts.append('    int buffer = 0;')
    parts.append('    List<int> currentLine = [];')
    parts.append('    stdin.listen((data) {')
    parts.append('        for (var byte in data) {')
    parts.append('            if (byte == 10) { // newline')
    parts.append('                controller.add(String.fromCharCodes(currentLine));')
    parts.append('                currentLine = [];')
    parts.append('            } else if (byte != 13) { // not carriage return')
    parts.append('                currentLine.add(byte);')
    parts.append('            }')
    parts.append('        }')
    parts.append('    });')
    parts.append('    return controller.stream;')
    parts.append('}')

    return '\n'.join(parts)


# ----------------------------------------------------------------------------
# 编译逻辑
# ----------------------------------------------------------------------------

def _compile_dart_code(code: str, func_name: str, cache_dir: str = None,
                       force: bool = False) -> str:
    """
    编译 Dart 代码并返回可执行文件路径

    参数：
        code: 完整 Dart 源代码
        func_name: 函数名（用于生成文件名）
        cache_dir: 缓存目录，None 则使用 _DART_CACHE_DIR
        force: 强制重新编译（忽略缓存）

    返回：
        编译后的可执行文件绝对路径

    异常：
        RuntimeError: 编译失败
    """
    if cache_dir is None:
        cache_dir = _DART_CACHE_DIR

    os.makedirs(cache_dir, exist_ok=True)

    # 生成唯一文件名（基于代码 MD5）
    code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
    base_name = f'dart_{func_name}_{code_hash}'
    src_path = os.path.join(cache_dir, f'{base_name}.dart')
    ext = _dart_exe_ext()
    exe_path = os.path.join(cache_dir, f'{base_name}{ext}')

    # 缓存命中（且非强制）
    if not force and os.path.exists(exe_path):
        return exe_path

    # 写入 .dart 源文件
    with open(src_path, 'w', encoding='utf-8') as f:
        f.write(code)

    # 编译命令：dart compile exe -o out main.dart
    if _USE_WSL:
        wsl_src = _to_wsl_path(src_path)
        wsl_exe = _to_wsl_path(exe_path)
        compile_cmd = [
            'wsl', 'dart', 'compile',
            'exe', '-o', wsl_exe,
            wsl_src,
        ]
    else:
        compile_cmd = [
            'dart', 'compile',
            'exe', '-o', exe_path,
            src_path,
        ]

    result = subprocess.run(
        compile_cmd,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=120,
    )

    stdout = result.stdout.decode('utf-8', errors='replace')
    stderr = result.stderr.decode('utf-8', errors='replace')

    if result.returncode != 0 or not os.path.exists(exe_path):
        raise RuntimeError(
            f'Dart 编译失败:\n'
            f'stderr:\n{stderr}\n'
            f'stdout:\n{stdout}\n'
            f'代码:\n{code}'
        )

    # 清理源文件
    try:
        os.remove(src_path)
    except OSError:
        pass

    return exe_path


def _call_dart_executable(exe_path: str, func_name: str, args: tuple,
                          param_types: List[str], ret_type: str):
    """
    调用 Dart 编译的可执行文件

    通过 stdin/stdout 传递 JSON 序列化的参数和结果。

    参数：
        exe_path: 可执行文件绝对路径
        func_name: 函数名
        args: 原始 Python 参数
        param_types: 参数类型列表
        ret_type: 返回类型

    返回：
        Python 端的解码结果
    """
    # 序列化参数
    json_args = []
    for arg, dart_type in zip(args, param_types):
        if dart_type == 'int':
            json_args.append(int(arg))
        elif dart_type == 'double':
            json_args.append(float(arg))
        elif dart_type == 'bool':
            json_args.append(bool(arg))
        else:
            json_args.append(str(arg))

    input_data = json.dumps({'func': func_name, 'args': json_args}) + '\n'

    try:
        if _USE_WSL:
            wsl_exe = _to_wsl_path(exe_path)
            result = subprocess.run(
                ['wsl', wsl_exe],
                input=input_data.encode('utf-8'),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=60,
            )
        else:
            result = subprocess.run(
                [exe_path],
                input=input_data.encode('utf-8'),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=60,
            )

        stdout = result.stdout.decode('utf-8', errors='replace')
        stderr = result.stderr.decode('utf-8', errors='replace')

        if result.returncode != 0:
            raise RuntimeError(
                f'Dart execution failed (code {result.returncode}):\n'
                f'stderr: {stderr}\n'
                f'stdout: {stdout}'
            )

        output = stdout.strip()
        if not output:
            return None

        # 解析 JSON 输出
        try:
            output_data = json.loads(output)
            result_val = output_data.get('result')

            # 类型转换
            if ret_type == 'int':
                return int(result_val)
            elif ret_type in ('double', 'float'):
                return float(result_val)
            elif ret_type == 'bool':
                return result_val in ('true', 'True', True)

            return result_val
        except json.JSONDecodeError:
            if output.startswith('ERROR:'):
                raise RuntimeError(f'Dart function error: {output[6:].strip()}')
            return output

    except subprocess.TimeoutExpired:
        raise RuntimeError('Dart execution timed out')


# ----------------------------------------------------------------------------
# 缓存
# ----------------------------------------------------------------------------

_dll_cache = {}
_cache_lock = threading.Lock()


def _get_cached_exe(func_name: str, code: str, force: bool = False) -> str:
    """
    获取缓存的可执行文件路径，必要时重新编译
    """
    with _cache_lock:
        cached = _dll_cache.get(func_name)
        if not force and cached and cached[0] == code and os.path.exists(cached[1]):
            return cached[1]
        exe_path = _compile_dart_code(code, func_name, force=force)
        _dll_cache[func_name] = (code, exe_path)
        return exe_path


def _remove_cached_exe(func_name: str) -> None:
    """移除缓存的可执行文件（用于强制重编译）"""
    with _cache_lock:
        cached = _dll_cache.pop(func_name, None)
        if cached:
            exe_path = cached[1]
            try:
                if os.path.exists(exe_path):
                    os.remove(exe_path)
            except OSError:
                pass


# ----------------------------------------------------------------------------
# 便捷入口
# ----------------------------------------------------------------------------

def compile_and_run(
    dart_code: str,
    func_name: str = 'main',
    args: tuple = (),
    ret_type: str = 'String',
    cache_dir: str = None,
):
    """
    直接编译并运行一段 Dart 源码（无装饰器）

    参数：
        dart_code: 完整 Dart 源码
        func_name: 要调用的导出函数名
        args: Python 位置参数
        ret_type: 返回类型
        cache_dir: 缓存目录（可选）

    返回：
        函数调用结果
    """
    actual_cache_dir = cache_dir or _DART_CACHE_DIR
    os.makedirs(actual_cache_dir, exist_ok=True)

    # 运行时推断入参类型
    param_types = []
    for arg in args:
        if isinstance(arg, bool):
            param_types.append('bool')
        elif isinstance(arg, int):
            param_types.append('int')
        elif isinstance(arg, float):
            param_types.append('double')
        elif isinstance(arg, str):
            param_types.append('String')
        else:
            param_types.append('String')

    exe_path = _compile_dart_code(dart_code, func_name, actual_cache_dir)
    return _call_dart_executable(exe_path, func_name, args, param_types, ret_type)


# ----------------------------------------------------------------------------
# DartBridge - Dart 桥接实现（继承 LangBridge）
# ----------------------------------------------------------------------------

class DartBridge(LangBridge):
    """
    Dart 语言桥接实现

    继承 LangBridge 抽象基类，实现 Dart 特定的代码生成、编译和调用。
    使用 subprocess 调用 dart 进行编译和执行。
    """

    name = 'dart'
    file_ext = '.dart'
    lib_ext = _dart_exe_ext() or '.exe'

    def __init__(self):
        super().__init__()

    def compiler_available(self) -> bool:
        """编译器是否可用"""
        return dart_compiler_available()

    def generate_code(self, spec: FunctionSpec) -> str:
        """
        生成 Dart 代码

        生成包含依赖函数和主函数的 Dart 源码，
        使用 stdin/stdout JSON 协议进行参数传递。
        """
        from .types import get_dart_type

        # 解析参数
        params = []
        for name, ann in spec.annotations.items():
            if name == 'return':
                continue
            if ann is None:
                dart_type = 'String'
            else:
                dart_type = get_dart_type(ann)
            params.append((name, dart_type))

        # 返回类型
        ret_dart_type = 'void'
        if 'return' in spec.annotations:
            ann = spec.annotations['return']
            if ann is not type(None) and ann is not None:
                ret_dart_type = get_dart_type(ann)

        # 生成依赖函数
        dependencies = spec.dependencies if spec.dependencies else []

        # module_code 处理
        module_code = spec.module_code if spec.module_code else ''

        return _generate_dart_source(
            func_name=spec.name,
            params=params,
            ret_dart_type=ret_dart_type,
            body=spec.body,
            module_code=module_code,
            dependencies=dependencies,
        )

    def compile_code(self, code: str, func_name: str, cache_dir: str = None) -> str:
        """
        编译 Dart 代码，返回可执行文件路径

        使用 dart compile exe 编译为本地可执行文件。
        """
        if cache_dir is None:
            cache_dir = _DART_CACHE_DIR

        return _compile_dart_code(code, func_name, cache_dir)

    def compile_project(self, project_dir: str, entry: str, output_dir: str = None) -> str:
        """
        编译 Dart 项目

        扫描 project_dir 下所有 .dart 文件，调用 dart 编译器编译。
        entry='main' 时生成可执行文件。

        参数：
            project_dir: 项目目录路径
            entry: 入口函数名，'main' 表示编译为可执行文件
            output_dir: 输出目录

        返回：
            产物路径（可执行文件）

        异常：
            RuntimeError: 编译失败
        """
        output_dir = output_dir or _DART_CACHE_DIR
        os.makedirs(output_dir, exist_ok=True)

        dart_files = []
        for root, dirs, files in os.walk(project_dir):
            for f in files:
                if f.endswith('.dart'):
                    dart_files.append(os.path.join(root, f))

        if not dart_files:
            raise RuntimeError(f'No .dart files found in project directory: {project_dir}')

        dart_files.sort()

        project_name = os.path.basename(os.path.abspath(project_dir))

        if entry == 'main':
            ext = _dart_exe_ext()
            output_path = os.path.join(output_dir, f'{project_name}{ext}')
            compile_cmd = ['dart', 'compile', 'exe', '-o', output_path]
            compile_cmd.extend(dart_files)
        else:
            raise RuntimeError('Dart project compilation only supports entry="main" for now')

        result = subprocess.run(
            compile_cmd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
            cwd=project_dir,
            timeout=180,
        )

        if result.returncode != 0 or not os.path.exists(output_path):
            raise RuntimeError(
                f'Dart project compilation failed:\n'
                f'stderr:\n{result.stderr}\n'
                f'stdout:\n{result.stdout}\n'
                f'files: {dart_files}'
            )

        return output_path

    def call_func(self, lib_path: str, func_name: str,
                  args: tuple, ret_type=None) -> Any:
        """
        调用 Dart 编译的函数

        通过 subprocess 调用 dart 执行的可执行文件，
        使用 JSON 序列化通过 stdin/stdout 传递参数和结果。
        """
        from .types import get_dart_type

        # 推断参数类型
        param_types = []
        for arg in args:
            if isinstance(arg, bool):
                param_types.append('bool')
            elif isinstance(arg, int):
                param_types.append('int')
            elif isinstance(arg, float):
                param_types.append('double')
            elif isinstance(arg, str):
                param_types.append('String')
            else:
                param_types.append('String')

        # 推断返回类型
        ret_dart_type = 'String'
        if ret_type is not None:
            ret_dart_type = get_dart_type(ret_type)

        return _call_dart_executable(lib_path, func_name, args, param_types, ret_dart_type)


# 全局 DartBridge 实例
_dart_bridge = DartBridge()


# 统一装饰器接口（使用 LangBridge 标准装饰器）
dart = _dart_bridge.decorator

# 别名
dartexe = dart
