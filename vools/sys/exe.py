"""
vools.sys.exe - 可执行文件装饰器模块

提供 ``@exe`` 装饰器，将 Python 函数映射为外部可执行文件调用。
通过函数参数命名约定自动构建命令行参数，支持同步/异步模式和 fallback 回退机制。

典型用法::

    @exe("echo")
    def echo(msg: str):
        pass

    returncode, stdout, stderr = echo("hello")
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
from typing import Callable, Optional, Tuple, Any


_executor = None


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=4)
    return _executor


def _build_command(exe_path: str, func: Callable, args: tuple, kwargs: dict) -> list:
    """根据函数签名和调用参数构建命令行参数列表。

    参数映射规则：
        - 单下划线前缀 ``_f`` → 短选项 ``-f value``（值为 None 时只有 ``-f``）
        - 双下划线前缀 ``__path`` → 长选项 ``--path value``（值为 None 时只有 ``--path``）
        - 无特殊前缀的参数 → 按顺序追加到命令末尾作为位置参数
        - ``*args`` 可变位置参数 → 按顺序追加到命令末尾

    Args:
        exe_path: 可执行文件路径。
        func: 被装饰的函数对象，用于获取参数签名。
        args: 调用时的位置参数元组。
        kwargs: 调用时的关键字参数字典。

    Returns:
        list: 构建好的命令行参数列表，第一个元素为可执行文件路径。
    """
    sig = inspect.signature(func)
    params = list(sig.parameters.values())

    cmd = [exe_path]
    positional_args = []

    bound_args = {}
    var_positional_name = None
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
                    positional_args.append(v)
            else:
                positional_args.append(value)
            continue

        if name.startswith('__'):
            option_name = name[2:]
            option = f'--{option_name}'
            if value is None:
                cmd.append(option)
            else:
                cmd.append(option)
                cmd.append(str(value))
        elif name.startswith('_'):
            option_name = name[1:]
            option = f'-{option_name}'
            if value is None:
                cmd.append(option)
            else:
                cmd.append(option)
                cmd.append(str(value))
        else:
            positional_args.append(value)

    for arg in positional_args:
        cmd.append(str(arg))

    return cmd


def _run_command(cmd: list) -> Tuple[int, str, str]:
    """执行命令行命令并捕获输出。

    Args:
        cmd: 命令行参数列表，第一个元素为可执行文件路径。

    Returns:
        Tuple[int, str, str]: 三元组 ``(returncode, stdout, stderr)``。
            - returncode: 进程退出码，0 表示成功。
            - stdout: 标准输出字符串。
            - stderr: 标准错误字符串。

    Raises:
        FileNotFoundError: 可执行文件未找到时抛出。
    """
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
        )
        return (result.returncode, result.stdout, result.stderr)
    except FileNotFoundError:
        raise
    except Exception as e:
        return (1, '', str(e))


def _function_body_is_pass(func: Callable) -> bool:
    """检测函数体是否为空（只有 pass 或 None 表达式）。

    通过 AST 解析判断函数体是否为"空"，用于决定函数体是否作为 fallback。
    判定为空的情况：空函数体、仅含 ``pass`` 语句、仅含 ``None`` 常量表达式。

    Args:
        func: 待检测的函数对象。

    Returns:
        bool: 函数体为空返回 True，否则返回 False。
    """
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


def exe(
    exe_path: str,
    *,
    async_mode: bool = False,
    fallback: Optional[Callable] = None,
):
    """装饰器工厂，将 Python 函数映射为外部可执行文件调用。

    通过函数参数命名约定自动构建命令行参数：
        - 单下划线前缀 ``_f`` → 短选项 ``-f value``（值为 None 时只有标志 ``-f``）
        - 双下划线前缀 ``__path`` → 长选项 ``--path value``（值为 None 时只有标志 ``--path``）
        - 无特殊前缀的参数 → 按定义顺序追加到命令末尾作为位置参数

    Fallback 优先级：
        1. 显式 ``fallback`` 参数（最高）
        2. 函数体实现（函数体非 ``pass`` 时）
        3. 无 fallback，失败抛出异常

    Args:
        exe_path: 可执行文件路径，支持绝对路径或 PATH 中的命令名。
        async_mode: 是否启用异步模式。启用后返回异步函数，在线程池中执行。
        fallback: 显式回退函数。exe 不存在或执行失败时调用，优先级高于函数体 fallback。

    Returns:
        Callable: 装饰器函数，接收被装饰函数并返回包装后的函数。

    Examples:
        简单命令调用::

            @exe("echo")
            def echo(msg: str):
                pass

            returncode, stdout, stderr = echo("hello")

        带选项参数::

            @exe("python")
            def python_cmd(_c=None, _O=None, __verbose=None):
                pass

            result = python_cmd(_c="print(123)", _O=None)

        异步模式::

            @exe("ping", async_mode=True)
            async def ping(host: str, count: int = 4):
                pass

            result = await ping("127.0.0.1")

        函数体 fallback::

            @exe("/path/to/may_not_exist.exe")
            def compute(x: int, y: int):
                return (0, str(x + y), "")
    """
    def decorator(f: Callable) -> Callable:
        actual_fallback = fallback
        if actual_fallback is None and not _function_body_is_pass(f):
            actual_fallback = f

        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            return _run_sync(f, exe_path, args, kwargs, actual_fallback)

        @functools.wraps(f)
        async def async_wrapper(*args, **kwargs):
            return await _run_async(f, exe_path, args, kwargs, actual_fallback)

        if async_mode:
            return async_wrapper
        return wrapper

    return decorator


def _run_sync(
    func: Callable,
    exe_path: str,
    args: tuple,
    kwargs: dict,
    fallback: Optional[Callable],
) -> Tuple[int, str, str]:
    """同步执行外部可执行文件。

    优先调用外部可执行文件，若文件不存在或调用失败且有 fallback，则调用 fallback。

    Args:
        func: 被装饰的函数对象。
        exe_path: 可执行文件路径。
        args: 调用时的位置参数。
        kwargs: 调用时的关键字参数。
        fallback: 回退函数，可为 None。

    Returns:
        Tuple[int, str, str]: 三元组 ``(returncode, stdout, stderr)``。

    Raises:
        FileNotFoundError: 可执行文件不存在且无 fallback 时抛出。
        Exception: 调用失败且无 fallback 时抛出。
    """
    if not os.path.exists(exe_path):
        if fallback:
            return fallback(*args, **kwargs)
        raise FileNotFoundError(f"Executable not found: {exe_path}")

    try:
        cmd = _build_command(exe_path, func, args, kwargs)
        return _run_command(cmd)
    except FileNotFoundError:
        if fallback:
            return fallback(*args, **kwargs)
        raise
    except Exception:
        if fallback:
            return fallback(*args, **kwargs)
        raise


async def _run_async(
    func: Callable,
    exe_path: str,
    args: tuple,
    kwargs: dict,
    fallback: Optional[Callable],
) -> Tuple[int, str, str]:
    """异步执行外部可执行文件。

    在线程池中同步执行调用，避免阻塞事件循环。

    Args:
        func: 被装饰的函数对象。
        exe_path: 可执行文件路径。
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
        lambda: _run_sync(func, exe_path, args, kwargs, fallback),
    )
