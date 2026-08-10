"""vools.bridge.swift.compiler - Swift 编译器与桥接实现

使用 swift 解释器直接运行 .swift 文件，通过 JSON 在 stdin/stdout 传递参数。
支持 WSL 环境（Windows 上通过 wsl 命令调用）。
"""
import os
import sys
import json
import textwrap
import tempfile
import hashlib
import subprocess
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

from .._base import LangBridge, FunctionSpec
from ..core.types import LangType
from .types import PY_TO_SWIFT_TYPE, get_swift_type

_IS_WINDOWS = os.name == 'nt'


def _check_local_swift() -> bool:
    """检查本地是否有 swift 命令"""
    try:
        result = subprocess.run(
            ['swift', '--version'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


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


_USE_WSL = _IS_WINDOWS and not _check_local_swift() and _check_wsl()


def swift_compiler_available() -> bool:
    """检查 Swift 编译器是否可用"""
    if not _IS_WINDOWS:
        return _check_local_swift()
    if _check_local_swift():
        return True
    return _USE_WSL and _check_wsl_swift()


def _check_wsl_swift() -> bool:
    """检查 WSL 中是否有 swift"""
    try:
        result = subprocess.run(
            ['wsl', 'swift', '--version'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=10
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _to_wsl_path(windows_path: str) -> str:
    """将 Windows 路径转换为 WSL 路径"""
    if not os.path.isabs(windows_path):
        windows_path = os.path.abspath(windows_path)
    drive = windows_path[0].lower()
    rest = windows_path[2:].replace('\\', '/')
    return f'/mnt/{drive}{rest}'


def _run_swift(swift_file: str, timeout: int = 60) -> subprocess.CompletedProcess:
    """运行 Swift 脚本，自动处理 WSL"""
    if _USE_WSL:
        wsl_path = _to_wsl_path(swift_file)
        return subprocess.run(
            ['wsl', 'swift', wsl_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
            timeout=timeout
        )
    else:
        return subprocess.run(
            ['swift', swift_file],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
            timeout=timeout
        )


def _compile_swift(swift_file: str, output_path: str, timeout: int = 120) -> subprocess.CompletedProcess:
    """编译 Swift 代码，自动处理 WSL"""
    if _USE_WSL:
        wsl_src = _to_wsl_path(swift_file)
        wsl_out = _to_wsl_path(output_path)
        return subprocess.run(
            ['wsl', 'swiftc', '-o', wsl_out, wsl_src],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
            timeout=timeout
        )
    else:
        return subprocess.run(
            ['swiftc', '-o', output_path, swift_file],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
            timeout=timeout
        )


class SwiftFuture:
    """Swift 异步调用结果封装"""

    def __init__(self, future):
        self._future = future

    def result(self, timeout=None):
        return self._future.result(timeout=timeout)

    def done(self):
        return self._future.done()

    def cancelled(self):
        return self._future.cancelled()

    def __await__(self):
        return asyncio.wrap_future(self._future).__await__()


class SwiftBridge(LangBridge):
    """Swift 语言桥接实现

    使用 swift 解释器直接运行 .swift 文件，通过 JSON 在 stdin/stdout 传递参数。
    Windows 上自动通过 WSL 调用。
    """

    name = 'swift'
    lang_type = LangType.COMPILED
    file_ext = '.swift'
    lib_ext = '.swift'

    def __init__(self):
        super().__init__()
        self._executor = ThreadPoolExecutor(max_workers=4)

    def compiler_available(self) -> bool:
        return swift_compiler_available()

    def generate_code(self, spec: FunctionSpec) -> str:
        """生成 Swift 代码

        生成包含依赖函数、主函数和 main 入口的完整 Swift 脚本。
        通过 stdin 读取 JSON 参数，调用目标函数，将结果以 JSON 输出到 stdout。
        """
        parts = []
        parts.append('import Foundation')
        parts.append('')

        if spec.module_code:
            parts.append(spec.module_code)
            parts.append('')

        for dep in spec.dependencies:
            dep_code = self._generate_function(dep)
            if dep_code:
                parts.append(dep_code)
                parts.append('')

        main_code = self._generate_function(spec)
        parts.append(main_code)
        parts.append('')

        main_entry = self._generate_main_entry(spec)
        parts.append(main_entry)

        return '\n'.join(parts)

    def _generate_function(self, spec: FunctionSpec) -> str:
        """生成单个函数的 Swift 代码"""
        arg_names = []
        swift_argtypes = []

        for name, ann in spec.annotations.items():
            if name == 'return':
                continue
            arg_names.append(name)
            if ann is None:
                swift_argtypes.append('Int')
            else:
                swift_argtypes.append(get_swift_type(ann))

        ret_type = 'Int'
        if 'return' in spec.annotations:
            ann = spec.annotations['return']
            if ann is type(None) or str(ann).lower() == 'none':
                ret_type = 'Void'
            else:
                ret_type = get_swift_type(ann)

        params = []
        for i, swift_t in enumerate(swift_argtypes):
            name = arg_names[i] if i < len(arg_names) else f'arg{i}'
            params.append(f'_ {name}: {swift_t}')

        params_str = ', '.join(params)

        body = spec.body
        if body.startswith('    ') or body.startswith('\t'):
            body = textwrap.dedent(body)
        body = body.strip()

        if ret_type == 'Void':
            return f'''func {spec.name}({params_str}) {{
{body}
}}'''
        else:
            return f'''func {spec.name}({params_str}) -> {ret_type} {{
{body}
}}'''

    def _generate_main_entry(self, spec: FunctionSpec) -> str:
        """生成 main 入口函数，从 stdin 读 JSON，输出结果到 stdout"""
        arg_names = []
        arg_types = []

        for name, ann in spec.annotations.items():
            if name == 'return':
                continue
            arg_names.append(name)
            if ann is None:
                arg_types.append('Int')
            else:
                arg_types.append(get_swift_type(ann))

        ret_type = 'Int'
        if 'return' in spec.annotations:
            ann = spec.annotations['return']
            if ann is type(None) or str(ann).lower() == 'none':
                ret_type = 'Void'
            else:
                ret_type = get_swift_type(ann)

        call_args = ', '.join(arg_names)

        parse_lines = []
        for i, (aname, atype) in enumerate(zip(arg_names, arg_types)):
            if atype == 'Int':
                parse_lines.append(f'    let {aname} = args[{i}] as? Int ?? 0')
            elif atype == 'Double':
                parse_lines.append(f'    let {aname} = args[{i}] as? Double ?? 0.0')
            elif atype == 'Bool':
                parse_lines.append(f'    let {aname} = args[{i}] as? Bool ?? false')
            elif atype == 'String':
                parse_lines.append(f'    let {aname} = args[{i}] as? String ?? ""')
            else:
                parse_lines.append(f'    let {aname} = args[{i}] as? String ?? ""')

        if ret_type == 'Void':
            result_line = f'    {spec.name}({call_args})'
            output_line = '    print("{\\\"ok\\\": true}")'
        else:
            result_line = f'    let result = {spec.name}({call_args})'
            if ret_type in ('Int', 'Double', 'Bool'):
                output_line = '    print(String(describing: result))'
            else:
                output_line = '    print(result)'

        return f'''
func readLineStdin() -> String? {{
    let input = FileHandle.standardInput
    let data = input.availableData
    if data.isEmpty {{ return nil }}
    return String(data: data, encoding: .utf8)
}}

if let line = readLineStdin() {{
    let data = line.data(using: .utf8)!
    if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
       let args = json["args"] as? [Any] {{
{chr(10).join("        " + l for l in parse_lines)}
        {result_line}
        {output_line}
    }}
}}
'''

    def compile_code(self, code: str, func_name: str, cache_dir: Optional[str] = None) -> str:
        """编译 Swift 代码（解释器模式下返回源码路径）

        解释器模式下，将源码写入文件并返回文件路径。
        若 swiftc 可用，也支持编译为原生可执行文件。
        """
        cache_dir = self.get_cache_dir(cache_dir)
        os.makedirs(cache_dir, exist_ok=True)

        code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
        src_path = os.path.join(cache_dir, f'swift_{func_name}_{code_hash}.swift')

        if not os.path.exists(src_path):
            with open(src_path, 'w', encoding='utf-8') as f:
                f.write(code)

        return src_path

    def compile_project(self, project_dir: str, entry: str, output_dir: Optional[str] = None) -> str:
        """编译整个 Swift 项目

        扫描 project_dir 下所有 .swift 文件，调用 swiftc 编译。
        entry='main' 时生成可执行文件。
        """
        output_dir = output_dir or self.default_cache_dir()
        os.makedirs(output_dir, exist_ok=True)

        src_files = []
        for root, dirs, files in os.walk(project_dir):
            for f in files:
                if f.endswith('.swift'):
                    src_files.append(os.path.join(root, f))

        if not src_files:
            raise RuntimeError(f'No .swift files found in project directory: {project_dir}')

        src_files.sort()
        project_name = os.path.basename(os.path.abspath(project_dir))

        if _IS_WINDOWS:
            output_path = os.path.join(output_dir, f'{project_name}.exe')
        else:
            output_path = os.path.join(output_dir, project_name)

        if os.path.exists(output_path):
            return output_path

        combined_src = os.path.join(output_dir, f'{project_name}_combined.swift')
        with open(combined_src, 'w', encoding='utf-8') as out:
            for f in src_files:
                with open(f, 'r', encoding='utf-8') as inp:
                    out.write(inp.read())
                    out.write('\n')

        result = _compile_swift(combined_src, output_path)

        if result.returncode != 0:
            raise RuntimeError(
                f'Swift project compilation failed:\n'
                f'stderr:\n{result.stderr}\n'
                f'stdout:\n{result.stdout}'
            )

        return output_path

    def call_func(self, lib_path: str, func_name: str,
                  args: tuple, ret_type: Optional[type] = None) -> Any:
        """调用 Swift 函数

        通过 subprocess 执行 swift 命令，将参数以 JSON 写入 stdin，
        从 stdout 解析返回值。
        """
        input_data = json.dumps({'func': func_name, 'args': list(args)}, ensure_ascii=False)

        try:
            if _USE_WSL:
                wsl_path = _to_wsl_path(lib_path)
                proc = subprocess.Popen(
                    ['wsl', 'swift', wsl_path],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
            else:
                proc = subprocess.Popen(
                    ['swift', lib_path],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )

            stdout, stderr = proc.communicate(input=input_data + '\n', timeout=60)

            if proc.returncode != 0:
                raise RuntimeError(
                    f'Swift execution failed (code {proc.returncode}):\n'
                    f'stderr: {stderr}\n'
                    f'stdout: {stdout}'
                )

            output = stdout.strip()
            if not output:
                return None

            try:
                parsed = json.loads(output)
                if isinstance(parsed, dict) and 'result' in parsed:
                    return parsed['result']
                return parsed
            except json.JSONDecodeError:
                if ret_type is not None:
                    if ret_type == int:
                        try:
                            return int(output)
                        except ValueError:
                            pass
                    elif ret_type == float:
                        try:
                            return float(output)
                        except ValueError:
                            pass
                    elif ret_type == bool:
                        return output.lower() in ('true', 'yes', '1')
                return output

        except subprocess.TimeoutExpired:
            raise RuntimeError('Swift execution timed out')

    def call_func_async(self, lib_path: str, func_name: str,
                        args: tuple, ret_type: Optional[type] = None) -> SwiftFuture:
        """异步调用 Swift 函数"""
        future = self._executor.submit(
            lambda: self.call_func(lib_path, func_name, args, ret_type)
        )
        return SwiftFuture(future)


_swift_bridge = SwiftBridge()
swift = _swift_bridge.decorator
swiftc = swift


def compile_and_run(swift_code: str, func_name: str = 'main',
                    args: tuple = (), ret_type: type = None,
                    cache_dir: str = None) -> Any:
    """直接编译并运行 Swift 代码"""
    bridge = _swift_bridge
    lib_path = bridge.compile_code(swift_code, func_name, cache_dir)
    return bridge.call_func(lib_path, func_name, args, ret_type)


__all__ = [
    'swift',
    'swiftc',
    'swift_compiler_available',
    'compile_and_run',
    'SwiftFuture',
    'SwiftBridge',
    '_swift_bridge',
]
