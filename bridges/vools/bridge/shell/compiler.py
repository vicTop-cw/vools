"""
vools.bridge.shell.compiler - Shell/Bash 语言桥接编译器实现

提供 ShellBridge 类，继承 LangBridge 抽象基类，实现 Shell/Bash 特定的代码生成、
解释执行和调用逻辑。
"""

import os
import sys
import tempfile
import hashlib
import platform
import inspect
import json
import shutil
import subprocess
import threading
import textwrap
from typing import Any, Optional

from .._base import LangBridge, FunctionSpec
from ..core.types import LangType
from .types import get_shell_type

_IS_WINDOWS = platform.system() == 'Windows'
_IS_LINUX = platform.system() == 'Linux'
_IS_MACOS = platform.system() == 'Darwin'

_SHELL_COMPILER = 'bash'

_SHELL_SEARCH_PATHS_WINDOWS = [
    r"C:\Windows\System32",
    r"C:\Program Files\Git\bin",
    r"C:\Program Files\Git\usr\bin",
    os.path.expanduser("~/AppData/Local/Programs/Git/bin"),
]

_SHELL_SEARCH_PATHS_UNIX = [
    "/bin",
    "/usr/bin",
    "/usr/local/bin",
    "/opt/homebrew/bin",
]


def _setup_shell_env() -> str:
    search_paths = _SHELL_SEARCH_PATHS_WINDOWS if _IS_WINDOWS else _SHELL_SEARCH_PATHS_UNIX
    env_paths = os.environ.get('PATH', '').split(os.pathsep)

    for p in search_paths:
        if os.path.exists(p) and p not in env_paths:
            os.environ['PATH'] = p + os.pathsep + os.environ.get('PATH', '')

    return _get_shell_path()


def _get_shell_path() -> str:
    found = shutil.which(_SHELL_COMPILER)
    if found:
        return found

    search_paths = _SHELL_SEARCH_PATHS_WINDOWS if _IS_WINDOWS else _SHELL_SEARCH_PATHS_UNIX
    exe_suffix = '.exe' if _IS_WINDOWS else ''
    for p in search_paths:
        candidate = os.path.join(p, _SHELL_COMPILER + exe_suffix)
        if os.path.exists(candidate):
            return candidate
    return _SHELL_COMPILER


def _wsl_available() -> bool:
    try:
        result = subprocess.run(
            ['wsl', '--version'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, OSError):
        return False
    except Exception:
        return False


_SHELL_PATH = _setup_shell_env()
_WSL_AVAILABLE = _IS_WINDOWS and _wsl_available()


def shell_compiler_available() -> bool:
    if not _IS_WINDOWS:
        try:
            result = subprocess.run(
                [_SHELL_PATH, '--version'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                universal_newlines=True, timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, OSError):
            return False
        except Exception:
            return False
    else:
        if shutil.which(_SHELL_COMPILER):
            try:
                result = subprocess.run(
                    [_SHELL_PATH, '--version'],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    universal_newlines=True, timeout=5,
                )
                return result.returncode == 0
            except Exception:
                pass
        return _WSL_AVAILABLE


def bash_compiler_available() -> bool:
    return shell_compiler_available()


_SHELL_CACHE_DIR = os.path.join(tempfile.gettempdir(), 'vools_shell_cache')


def infer_shell_argtypes(args):
    result = []
    for arg in args:
        if isinstance(arg, bool):
            result.append('bool')
        elif isinstance(arg, int):
            result.append('int')
        elif isinstance(arg, float):
            result.append('float')
        elif isinstance(arg, str):
            result.append('string')
        elif isinstance(arg, (bytes, bytearray)):
            result.append('string')
        elif isinstance(arg, (list, tuple)):
            result.append('array')
        elif isinstance(arg, dict):
            result.append('assoc_array')
        else:
            result.append('string')
    return result


def _preprocess_shell_body(body: str) -> str:
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


def _generate_shell_source(
    func_name: str,
    arg_names: list,
    arg_shell_types: list,
    ret_shell_type: str,
    body: str,
    auto_signature: bool = True,
    args_json: str = None,
) -> str:
    indented_body = _preprocess_shell_body(body)
    if indented_body:
        indented_body = '\n' + indented_body + '\n'
    else:
        indented_body = '\n'

    if auto_signature:
        assign_lines = []
        for i, arg in enumerate(arg_names):
            assign_lines.append(f'    local {arg}="${arg_values[i]}"')

        assign_code = '\n'.join(assign_lines) if assign_lines else ''

        code = f'''#!/usr/bin/env bash
set -euo pipefail

ARGS_JSON='{args_json}'

parse_args() {{
    local json="$1"
    local count=$(echo "$json" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo 0)
    for i in $(seq 0 $((count - 1))); do
        eval "ARG_$i=$(echo "$json" | python3 -c "import sys,json; print(json.load(sys.stdin)[$i])" 2>/dev/null || echo '')"
    done
}}

{func_name}() {{{indented_body}}}

parse_args "$ARGS_JSON"

RESULT=$({func_name} $(for i in $(seq 0 $(( {len(arg_names)} - 1 ))); do echo -n "\"$ARG_$i\" "; done))

echo "$RESULT"
'''
    else:
        code = f'''#!/usr/bin/env bash
set -euo pipefail

ARGS_JSON='{args_json}'

{body}
'''
    return code


def _generate_shell_source_simple(
    func_name: str,
    arg_names: list,
    body: str,
) -> str:
    indented_body = _preprocess_shell_body(body)
    if indented_body:
        indented_body = '\n' + indented_body + '\n'
    else:
        indented_body = '\n'

    code = f'''#!/usr/bin/env bash
set -euo pipefail

{func_name}() {{{indented_body}}}

{func_name} "$@"
'''
    return code


def _execute_shell_code(code: str, func_name: str, cache_dir: str = None,
                        force: bool = False) -> str:
    if cache_dir is None:
        cache_dir = _SHELL_CACHE_DIR

    os.makedirs(cache_dir, exist_ok=True)

    code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
    base_name = f'shell_{func_name}_{code_hash}'
    src_path = os.path.join(cache_dir, f'{base_name}.sh')

    if not force and os.path.exists(src_path):
        output = _run_shell_script(src_path, [])
        if output is not None:
            return output.strip()

    with open(src_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(code)

    if not _IS_WINDOWS:
        try:
            os.chmod(src_path, 0o755)
        except Exception:
            pass

    output = _run_shell_script(src_path, [])
    if output is None:
        raise RuntimeError(
            f'Shell 执行失败\n'
            f'代码:\n{code}'
        )

    return output.strip()


def _run_shell_script(script_path: str, args: list) -> Optional[str]:
    try:
        if _IS_WINDOWS:
            # Convert Windows path to WSL path for bash.exe (WSL launcher)
            wsl_path = script_path.replace(chr(92), '/')
            wsl_path = '/mnt/' + wsl_path[0].lower() + wsl_path[2:]
            cmd = ['wsl', 'bash', wsl_path] + args
        else:
            cmd = [_SHELL_PATH, script_path] + args

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=60,
        )
        if result.returncode == 0:
            return result.stdout
        else:
            raise RuntimeError(
                f'Shell 脚本执行失败 (exit code {result.returncode}):\n'
                f'stderr:\n{result.stderr}\n'
                f'stdout:\n{result.stdout}'
            )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f'Shell 脚本执行超时: {script_path}')
    except Exception as e:
        raise RuntimeError(f'Shell 脚本执行出错: {e}')


def _parse_shell_output(output: str, ret_type: str):
    if output == '' or output.lower() == 'null' or output.lower() == 'none':
        return None

    if ret_type == 'int':
        try:
            return int(output)
        except ValueError:
            return output
    elif ret_type == 'float':
        try:
            return float(output)
        except ValueError:
            return output
    elif ret_type == 'bool':
        if output.lower() in ('true', '1', 'yes'):
            return True
        elif output.lower() in ('false', '0', 'no'):
            return False
        return output
    elif ret_type in ('array', 'list'):
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return output
    elif ret_type in ('assoc_array', 'dict', 'hash'):
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return output
    elif ret_type == 'string' or ret_type == 'str':
        return output
    elif ret_type == 'void':
        return None

    try:
        return json.loads(output)
    except json.JSONDecodeError:
        try:
            return int(output)
        except ValueError:
            try:
                return float(output)
            except ValueError:
                return output


_code_cache = {}
_cache_lock = threading.Lock()


def _get_cached_code(func_name: str, code: str, force: bool = False) -> str:
    with _cache_lock:
        cached = _code_cache.get(func_name)
        if not force and cached and cached[0] == code and os.path.exists(cached[1]):
            return cached[1]
        code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
        base_name = f'shell_{func_name}_{code_hash}'
        src_path = os.path.join(_SHELL_CACHE_DIR, f'{base_name}.sh')
        os.makedirs(_SHELL_CACHE_DIR, exist_ok=True)
        with open(src_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(code)
        if not _IS_WINDOWS:
            try:
                os.chmod(src_path, 0o755)
            except Exception:
                pass
        _code_cache[func_name] = (code, src_path)
        return src_path


from concurrent.futures import ThreadPoolExecutor


class ShellFuture:
    def __init__(self, future):
        self._future = future

    def result(self, timeout=None):
        return self._future.result(timeout=timeout)


def _run_async(code: str, func_name: str, args: tuple,
               ret_type: Optional[type] = None, cache_dir: str = None) -> ShellFuture:
    executor = ThreadPoolExecutor(max_workers=1)

    def _execute():
        shell_ret_type = get_shell_type(ret_type) if ret_type else 'auto'
        full_code = _generate_callable_shell_code(code, func_name, args)
        output = _execute_shell_code(full_code, func_name, cache_dir)
        return _parse_shell_output(output, shell_ret_type)

    future = executor.submit(_execute)
    executor.shutdown(wait=False)
    return ShellFuture(future)


def _generate_callable_shell_code(body: str, func_name: str, args: tuple) -> str:
    arg_names = [f'arg{i}' for i in range(len(args))]
    return _generate_shell_source_simple(func_name, arg_names, body)


class ShellBridge(LangBridge):
    """
    Shell/Bash 语言桥接实现

    继承 LangBridge 抽象基类，实现 Shell/Bash 特定的代码生成、
    解释执行和调用逻辑。
    """

    name = 'shell'
    is_compiled = False
    lang_type = LangType.INTERPRETED
    file_ext = '.sh'
    lib_ext = '.sh'

    def __init__(self):
        super().__init__()
        _setup_shell_env()

    def compiler_available(self) -> bool:
        return shell_compiler_available()

    def _execute_code(self, package_path, func_name, args, ret_type=None):
        """解包并执行代码。"""
        import zipfile, tempfile, shutil

        shell_ret_type = get_shell_type(ret_type) if ret_type else 'auto'

        tmpdir = tempfile.mkdtemp()
        try:
            with zipfile.ZipFile(package_path, 'r') as zf:
                zf.extractall(tmpdir)

            source_file = os.path.join(tmpdir, self.get_source_filename(func_name))

            # Read the generated code
            with open(source_file, 'r', encoding='utf-8') as f:
                code = f.read()

            # Build wrapper that calls the function with arguments
            full_code = '#!/usr/bin/env bash\nset -euo pipefail\n\n' + code + '\n' + func_name + ' "$@"\n'

            wrapper_path = os.path.join(tmpdir, 'wrapper.sh')
            with open(wrapper_path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(full_code)

            arg_list = [str(a) for a in args]
            output = _run_shell_script(wrapper_path, arg_list)
            if output is None:
                raise RuntimeError(
                    "Shell execution failed for '{}'".format(func_name)
                )
            return _parse_shell_output(output.strip(), shell_ret_type)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def generate_code(self, spec: FunctionSpec) -> str:
        parts = []

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

        return '\n'.join(parts)

    def _generate_function(self, spec: FunctionSpec) -> str:
        arg_names = []

        for name, ann in spec.annotations.items():
            if name == 'return':
                continue
            arg_names.append(name)

        body = spec.body
        if body:
            body = textwrap.dedent(body).strip()

        indented_body = _preprocess_shell_body(body)
        if indented_body:
            indented_body = '\n' + indented_body + '\n'
        else:
            indented_body = '\n'

        return f'{spec.name}() {{{indented_body}}}'

    def compile_code(self, code: str, func_name: str, cache_dir: str = None) -> str:
        if cache_dir is None:
            cache_dir = _SHELL_CACHE_DIR

        os.makedirs(cache_dir, exist_ok=True)

        code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
        base_name = f'shell_{func_name}_{code_hash}'
        src_path = os.path.join(cache_dir, f'{base_name}.sh')

        with open(src_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(code)

        if not _IS_WINDOWS:
            try:
                os.chmod(src_path, 0o755)
            except Exception:
                pass

        return src_path

    def compile_project(self, project_dir: str, entry: str, output_dir: str = None) -> str:
        output_dir = output_dir or _SHELL_CACHE_DIR
        os.makedirs(output_dir, exist_ok=True)

        sh_files = []
        for root, dirs, files in os.walk(project_dir):
            for f in files:
                if f.endswith('.sh'):
                    sh_files.append(os.path.join(root, f))

        if not sh_files:
            raise RuntimeError(f'No .sh files found in project directory: {project_dir}')

        sh_files.sort()

        project_name = os.path.basename(os.path.abspath(project_dir))

        if entry == 'main':
            main_sh = os.path.join(project_dir, 'main.sh')
            if not os.path.exists(main_sh):
                main_sh = sh_files[0]
            return main_sh
        else:
            project_hash = self._get_project_hash(project_dir)[:12]
            output_path = os.path.join(output_dir, f'shell_proj_{project_name}_{entry}_{project_hash}.sh')

            if os.path.exists(output_path):
                return output_path

            all_code = []
            all_code.append('#!/usr/bin/env bash')
            all_code.append(f'# Auto-generated from project: {project_name}')
            all_code.append('set -euo pipefail')
            all_code.append('')

            for sh_file in sh_files:
                rel_path = os.path.relpath(sh_file, project_dir)
                all_code.append(f'# --- {rel_path} ---')
                with open(sh_file, 'r', encoding='utf-8') as f:
                    all_code.append(f.read())
                all_code.append('')

            all_code.append('# Entry point call')
            all_code.append(f'{entry} "$@"')

            final_code = '\n'.join(all_code)

            with open(output_path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(final_code)

            if not _IS_WINDOWS:
                try:
                    os.chmod(output_path, 0o755)
                except Exception:
                    pass

            return output_path

    def call_func(self, src_path: str, func_name: str,
                  args: tuple, ret_type=None) -> Any:
        shell_ret_type = get_shell_type(ret_type) if ret_type else 'auto'

        with open(src_path, 'r', encoding='utf-8') as f:
            code = f.read()

        arg_list = [str(a) for a in args]

        full_code = f'''#!/usr/bin/env bash
set -euo pipefail

{code}

{func_name} "$@"
'''

        code_hash = hashlib.md5(full_code.encode('utf-8')).hexdigest()[:12]
        base_name = f'shell_call_{func_name}_{code_hash}'
        cache_dir = _SHELL_CACHE_DIR
        os.makedirs(cache_dir, exist_ok=True)
        call_path = os.path.join(cache_dir, f'{base_name}.sh')

        with open(call_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(full_code)

        if not _IS_WINDOWS:
            try:
                os.chmod(call_path, 0o755)
            except Exception:
                pass

        output = _run_shell_script(call_path, arg_list)
        return _parse_shell_output(output.strip(), shell_ret_type)


_shell_bridge = ShellBridge()


def compile_and_run(code: str, func_name: str = 'main',
                    args: tuple = (), ret_type=None,
                    cache_dir: str = None) -> Any:
    bridge = _shell_bridge
    src_path = bridge.compile_code(code, func_name, cache_dir)
    return bridge.call_func(src_path, func_name, args, ret_type)


shell = _shell_bridge.decorator
sh = shell
bash = shell
