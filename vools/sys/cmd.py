"""
vools.sys.cmd - 命令行装饰器模块

提供 ``@cmd`` 装饰器，将 Python 函数映射为 shell 命令调用。
通过函数参数命名约定自动构建命令行参数，支持选择不同的 shell（bash/cmd/powershell），
以及同步/异步模式和 fallback 回退机制。

典型用法::

    @cmd("ls")
    def ls(_l=None):
        pass

    returncode, stdout, stderr = ls()

    @cmd("echo", shell="powershell")
    def ps_echo(msg: str):
        pass

    result = ps_echo("hello world")
"""

import os
import sys
import ast
import subprocess
import functools
import inspect
import textwrap
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional, Tuple, Any, Literal


_executor = None


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=4)
    return _executor


def _build_command(cmd_str: str, func: Callable, args: tuple, kwargs: dict) -> str:
    """根据函数签名和调用参数构建完整命令字符串。

    参数映射规则：
        - 单下划线前缀 ``_f`` → 短选项 ``-f value``（值为 None 时只有 ``-f``）
        - 双下划线前缀 ``__path`` → 长选项 ``--path value``（值为 None 时只有 ``--path``）
        - 无特殊前缀的参数 → 按顺序追加到命令末尾作为位置参数
        - ``*args`` 可变位置参数 → 按顺序追加到命令末尾

    Args:
        cmd_str: 基础命令字符串。
        func: 被装饰的函数对象，用于获取参数签名。
        args: 调用时的位置参数元组。
        kwargs: 调用时的关键字参数字典。

    Returns:
        str: 构建好的完整命令字符串。
    """
    sig = inspect.signature(func)
    params = list(sig.parameters.values())

    cmd_parts = [cmd_str]
    positional_args = []

    bound_args = {}
    try:
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()
        for name, value in bound.arguments.items():
            bound_args[name] = value
    except TypeError:
        param_names = [p.name for p in params]
        for i, arg in enumerate(args):
            if i < len(param_names):
                bound_args[param_names[i]] = arg
        bound_args.update(kwargs)

    for param in params:
        name = param.name
        if name not in bound_args:
            continue

        value = bound_args[name]

        if param.kind == inspect.Parameter.VAR_POSITIONAL:
            if isinstance(value, (tuple, list)):
                for v in value:
                    positional_args.append(str(v))
            else:
                positional_args.append(str(value))
            continue

        if name.startswith('__'):
            option_name = name[2:]
            option = f'--{option_name}'
            if value is None:
                cmd_parts.append(option)
            else:
                cmd_parts.append(option)
                cmd_parts.append(str(value))
        elif name.startswith('_'):
            option_name = name[1:]
            option = f'-{option_name}'
            if value is None:
                cmd_parts.append(option)
            else:
                cmd_parts.append(option)
                cmd_parts.append(str(value))
        else:
            positional_args.append(str(value))

    cmd_parts.extend(positional_args)
    return ' '.join(cmd_parts)


def _snake_to_pascal(name: str) -> str:
    """将 snake_case 转换为 PascalCase（PowerShell 命令风格）。

    保留连续大写字母的正确转换，例如：
        get_childitem -> Get-ChildItem
        get_process -> Get-Process
        write_output -> Write-Output

    Args:
        name: snake_case 格式的名称。

    Returns:
        str: PascalCase 格式的名称，单词间用连字符分隔。
    """
    words = name.split('_')
    capitalized = [word.capitalize() for word in words if word]
    if len(capitalized) >= 2:
        return capitalized[0] + '-' + ''.join(capitalized[1:])
    return ''.join(capitalized)


def _get_shell_args(shell: str) -> Tuple[str, list]:
    """获取指定 shell 的执行参数。

    Args:
        shell: shell 类型，支持 "cmd", "powershell", "bash", "sh"。

    Returns:
        Tuple[str, list]: (shell_executable, arguments_list)
    """
    shell = shell.lower()
    if shell == 'cmd':
        return ('cmd.exe', ['/c'])
    elif shell == 'powershell' or shell == 'ps':
        return ('powershell.exe', ['-Command'])
    elif shell == 'bash':
        return ('bash', ['-c'])
    elif shell == 'sh':
        return ('sh', ['-c'])
    elif shell == 'wsl':
        return ('wsl', ['bash', '-c'])
    elif shell == 'pwsh':
        return ('pwsh', ['-Command'])
    else:
        raise ValueError(f"Unsupported shell: {shell}. Supported: cmd, powershell/ps, bash, sh, wsl, pwsh")


def _run_command(cmd_str: str, shell: str) -> Tuple[int, str, str]:
    """执行 shell 命令并捕获输出。

    Args:
        cmd_str: 命令字符串。
        shell: shell 类型。

    Returns:
        Tuple[int, str, str]: 三元组 ``(returncode, stdout, stderr)``。
            - returncode: 进程退出码，0 表示成功。
            - stdout: 标准输出字符串。
            - stderr: 标准错误字符串。
    """
    try:
        shell_exe, shell_args = _get_shell_args(shell)

        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'

        if shell.lower() == 'cmd':
            cmd_str = 'chcp 65001 >nul && ' + cmd_str

        full_cmd = [shell_exe] + shell_args + [cmd_str]

        result = subprocess.run(
            full_cmd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
            env=env,
        )
        return (result.returncode, result.stdout, result.stderr)
    except FileNotFoundError as e:
        return (1, '', f"Shell not found: {shell_exe}. Error: {e}")
    except Exception as e:
        return (1, '', str(e))


def _function_body_is_pass(func: Callable) -> bool:
    """检测函数体是否为空（只有 pass 或 None 表达式）。"""
    try:
        source = inspect.getsource(func)
        source = textwrap.dedent(source)
        tree = ast.parse(source)
        func_def = tree.body[0]
        if not isinstance(func_def, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return False
        body = func_def.body
        if len(body) == 0:
            return True
        if len(body) == 1 and isinstance(body[0], ast.Pass):
            return True
        if len(body) == 1 and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and body[0].value.value is None:
            return True
        return False
    except Exception:
        return False


def cmd(
    cmd_str: Optional[Any] = None,
    *,
    shell: Literal['cmd', 'powershell', 'ps', 'bash', 'sh', 'wsl', 'pwsh'] = 'powershell',
    async_mode: bool = False,
    fallback: Optional[Callable] = None,
):
    """装饰器工厂，将 Python 函数映射为 shell 命令调用。

    通过函数参数命名约定自动构建命令行参数：
        - 单下划线前缀 ``_f`` → 短选项 ``-f value``（值为 None 时只有标志 ``-f``）
        - 双下划线前缀 ``__path`` → 长选项 ``--path value``（值为 None 时只有标志 ``--path``）
        - 无特殊前缀的参数 → 按定义顺序追加到命令末尾作为位置参数

    Args:
        cmd_str: 基础命令字符串（如 "ls", "dir", "echo"）。
            当为 None 或省略时，自动使用被装饰函数的名称作为命令。
            当传入可调用对象时（如 `@cmd` 不带括号），直接作为被装饰函数处理。
        shell: 使用的 shell 类型，支持：
            - "cmd": Windows cmd.exe
            - "powershell"/"ps": Windows PowerShell
            - "bash": Bash shell
            - "sh": POSIX shell
            - "wsl": WSL bash
            - "pwsh": PowerShell Core
            默认值为 "powershell"。
        async_mode: 是否启用异步模式。启用后返回异步函数，在线程池中执行。
        fallback: 显式回退函数。命令执行失败时调用，优先级高于函数体 fallback。

    Returns:
        Callable: 装饰器函数或装饰后的函数。

    Examples:
        使用函数名作为命令（无括号）::

            @cmd
            def echo(msg: str):
                pass

            returncode, stdout, stderr = echo("hello")

        使用函数名作为命令（带括号）::

            @cmd(None)
            def echo(msg: str):
                pass

            result = echo("hello")

        显式指定命令::

            @cmd("echo")
            def echo_func(msg: str):
                pass

            result = echo_func("hello")

        指定 shell::

            @cmd("dir", shell="cmd")
            def dir_cmd():
                pass

            result = dir_cmd()

        带参数的命令::

            @cmd("echo")
            def echo(msg: str):
                pass

            returncode, stdout, stderr = echo("hello world")

        异步模式::

            @cmd("ping", shell="cmd", async_mode=True)
            async def ping(host: str, _n: int = 4):
                pass

            result = await ping("127.0.0.1")

        函数体 fallback::

            @cmd("/path/to/may_not_exist")
            def custom_cmd(arg1: str):
                return (0, f"fallback result: {arg1}", "")
    """
    if callable(cmd_str):
        f = cmd_str
        cmd_str = None
        actual_fallback = fallback
        if actual_fallback is None and not _function_body_is_pass(f):
            actual_fallback = f
        actual_cmd = f.__name__
        if shell.lower() in ('powershell', 'ps', 'pwsh'):
            actual_cmd = _snake_to_pascal(actual_cmd)

        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            return _run_sync(f, actual_cmd, shell, args, kwargs, actual_fallback)

        @functools.wraps(f)
        async def async_wrapper(*args, **kwargs):
            return await _run_async(f, actual_cmd, shell, args, kwargs, actual_fallback)

        if async_mode:
            return async_wrapper
        return wrapper

    def decorator(f: Callable) -> Callable:
        actual_fallback = fallback
        if actual_fallback is None and not _function_body_is_pass(f):
            actual_fallback = f

        actual_cmd = cmd_str if cmd_str is not None else f.__name__
        if cmd_str is None and shell.lower() in ('powershell', 'ps', 'pwsh'):
            actual_cmd = _snake_to_pascal(actual_cmd)

        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            return _run_sync(f, actual_cmd, shell, args, kwargs, actual_fallback)

        @functools.wraps(f)
        async def async_wrapper(*args, **kwargs):
            return await _run_async(f, actual_cmd, shell, args, kwargs, actual_fallback)

        if async_mode:
            return async_wrapper
        return wrapper

    return decorator


def _run_sync(
    func: Callable,
    cmd_str: str,
    shell: str,
    args: tuple,
    kwargs: dict,
    fallback: Optional[Callable],
) -> Tuple[int, str, str]:
    """同步执行 shell 命令。

    Args:
        func: 被装饰的函数对象。
        cmd_str: 基础命令字符串。
        shell: shell 类型。
        args: 调用时的位置参数。
        kwargs: 调用时的关键字参数。
        fallback: 回退函数，可为 None。

    Returns:
        Tuple[int, str, str]: 三元组 ``(returncode, stdout, stderr)``。
    """
    try:
        full_cmd = _build_command(cmd_str, func, args, kwargs)
        return _run_command(full_cmd, shell)
    except Exception:
        if fallback:
            return fallback(*args, **kwargs)
        raise


async def _run_async(
    func: Callable,
    cmd_str: str,
    shell: str,
    args: tuple,
    kwargs: dict,
    fallback: Optional[Callable],
) -> Tuple[int, str, str]:
    """异步执行 shell 命令。

    Args:
        func: 被装饰的函数对象。
        cmd_str: 基础命令字符串。
        shell: shell 类型。
        args: 调用时的位置参数。
        kwargs: 调用时的关键字参数。
        fallback: 回退函数，可为 None。

    Returns:
        Tuple[int, str, str]: 三元组 ``(returncode, stdout, stderr)``。
    """
    executor = _get_executor()
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        executor,
        lambda: _run_sync(func, cmd_str, shell, args, kwargs, fallback),
    )