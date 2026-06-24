"""
vools.sys.dll - DLL 函数装饰器模块

提供 ``@dll`` 装饰器，将 Python 函数映射为 DLL/共享库函数调用。
根据函数类型注解自动映射 ctypes 类型，自动处理字符串编码解码，
支持同步/异步模式和 fallback 回退机制。

典型用法::

    @dll("mylib.dll::add")
    def add(a: int, b: int) -> int:
        pass

    result = add(3, 5)
"""

import os
import ast
import ctypes
import functools
import inspect
import textwrap
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional, Any


_executor = None


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=4)
    return _executor


_PY_TO_CTYPES = {
    int: ctypes.c_int,
    float: ctypes.c_double,
    str: ctypes.c_char_p,
    bytes: ctypes.c_char_p,
    bool: ctypes.c_bool,
}
"""Python 类型到 ctypes 类型的默认映射表。"""


def _map_py_to_ctype(py_type: Optional[type]) -> Any:
    """将 Python 类型映射为对应的 ctypes 类型。

    未注册的类型或 None 默认映射为 ``c_int``。

    Args:
        py_type: Python 类型，可为 None（表示无类型注解）。

    Returns:
        Any: 对应的 ctypes 类型对象。
    """
    if py_type is None:
        return ctypes.c_int
    return _PY_TO_CTYPES.get(py_type, ctypes.c_int)


def _convert_arg(arg: Any, c_type: Any) -> Any:
    """转换函数参数为 ctypes 兼容的类型。

    当前仅处理 str → bytes 的自动编码（UTF-8）。

    Args:
        arg: 原始参数值。
        c_type: 目标 ctypes 类型。

    Returns:
        Any: 转换后的参数值。
    """
    if c_type is ctypes.c_char_p:
        if isinstance(arg, str):
            return arg.encode('utf-8')
    return arg


def _convert_result(result: Any, ret_ctype: Any, ret_py_type: Optional[type]) -> Any:
    """转换 DLL 函数返回值为 Python 类型。

    当前仅处理 bytes → str 的自动解码（UTF-8）。

    Args:
        result: DLL 函数返回的原始结果。
        ret_ctype: 返回值的 ctypes 类型。
        ret_py_type: 期望的 Python 返回类型，可为 None。

    Returns:
        Any: 转换后的返回值。
    """
    if ret_py_type is str and isinstance(result, bytes):
        return result.decode('utf-8')
    return result


def _parse_dll_spec(spec: str) -> tuple:
    """解析 DLL 规格字符串，分离 DLL 路径和函数名。

    支持两种格式：
        - ``"path/to/dll::func_name"``：指定路径和函数名
        - ``"path/to/dll"``：仅指定路径，函数名后续从被装饰函数名推断

    Args:
        spec: DLL 规格字符串。

    Returns:
        tuple: 二元组 ``(dll_path, func_name)``，func_name 可能为 None。
    """
    if '::' in spec:
        dll_path, func_name = spec.rsplit('::', 1)
    else:
        dll_path = spec
        func_name = None
    return dll_path, func_name


def _extract_annotations(func: Callable) -> tuple:
    """从函数签名中提取类型注解。

    Args:
        func: 待解析的函数对象。

    Returns:
        tuple: 三元组 ``(arg_py_types, ret_py_type, params)``。
            - arg_py_types: 参数类型列表，无注解的位置为 None
            - ret_py_type: 返回值类型，无注解时为 None
            - params: inspect.Parameter 对象列表
    """
    sig = inspect.signature(func)
    params = list(sig.parameters.values())

    arg_py_types = []
    for param in params:
        if param.annotation is inspect.Parameter.empty:
            arg_py_types.append(None)
        else:
            arg_py_types.append(param.annotation)

    ret_py_type = None
    if sig.return_annotation is not inspect.Parameter.empty:
        ret_py_type = sig.return_annotation

    return arg_py_types, ret_py_type, params


def _load_dll(dll_path: str) -> ctypes.CDLL:
    """加载 DLL/共享库。

    Args:
        dll_path: DLL 文件路径。

    Returns:
        ctypes.CDLL: 加载后的库对象。
    """
    return ctypes.CDLL(dll_path)


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


def _setup_function(
    lib: ctypes.CDLL,
    func_name: str,
    arg_ctypes: list,
    ret_ctype: Any,
) -> Callable:
    """设置 DLL 函数的参数类型和返回类型。

    从库中获取指定函数，并设置其 argtypes 和 restype。

    Args:
        lib: 已加载的 DLL 库对象。
        func_name: 函数名称。
        arg_ctypes: 参数类型列表（ctypes 类型）。
        ret_ctype: 返回值类型（ctypes 类型）。

    Returns:
        Callable: 设置好类型签名的函数对象。
    """
    func = getattr(lib, func_name)
    func.argtypes = arg_ctypes
    func.restype = ret_ctype
    return func


def dll(
    dll_spec: str,
    *,
    async_mode: bool = False,
    fallback: Optional[Callable] = None,
):
    """装饰器工厂，将 Python 函数映射为 DLL/共享库函数调用。

    根据函数的类型注解自动映射 ctypes 类型：
        - ``int`` → ``c_int``
        - ``float`` → ``c_double``
        - ``str`` → ``c_char_p``（自动编码/解码 UTF-8）
        - ``bytes`` → ``c_char_p``
        - ``bool`` → ``c_bool``
        - 无注解 → 默认 ``c_int``

    DLL 规格格式：
        - ``"path/to/dll::func_name"``：指定路径和函数名
        - ``"path/to/dll"``：仅指定路径，函数名从被装饰函数名推断

    Fallback 优先级：
        1. 显式 ``fallback`` 参数（最高）
        2. 函数体实现（函数体非 ``pass`` 时）
        3. 无 fallback，失败抛出异常

    Args:
        dll_spec: DLL 规格字符串，格式为 ``"path/to/dll::func_name"``。
            只传路径时函数名从被装饰函数名推断。
        async_mode: 是否启用异步模式。启用后返回异步函数，在线程池中执行。
        fallback: 显式回退函数。DLL 不存在或调用失败时调用，优先级高于函数体 fallback。

    Returns:
        Callable: 装饰器函数，接收被装饰函数并返回包装后的函数。

    Examples:
        简单数值函数::

            @dll("mathlib.dll::add")
            def add(a: int, b: int) -> int:
                pass

            result = add(3, 5)

        字符串自动编码解码::

            @dll("greet.dll::hello")
            def hello(name: str) -> str:
                pass

            result = hello("World")

        函数体 fallback::

            @dll("nonexistent.dll::add")
            def add(a: int, b: int) -> int:
                return a + b  # DLL 不存在时用 Python 兜底

        异步模式::

            @dll("heavy.dll::compute", async_mode=True)
            async def compute(n: int) -> int:
                pass

            result = await compute(1000000)
    """
    def decorator(f: Callable) -> Callable:
        dll_path, func_name = _parse_dll_spec(dll_spec)
        if func_name is None:
            func_name = f.__name__

        arg_py_types, ret_py_type, params = _extract_annotations(f)

        arg_ctypes = [_map_py_to_ctype(t) for t in arg_py_types]
        ret_ctype = _map_py_to_ctype(ret_py_type)

        actual_fallback = fallback
        if actual_fallback is None and not _function_body_is_pass(f):
            actual_fallback = f

        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            return _run_sync(
                f, dll_path, func_name, args, kwargs,
                arg_ctypes, ret_ctype, ret_py_type, params, actual_fallback
            )

        @functools.wraps(f)
        async def async_wrapper(*args, **kwargs):
            return await _run_async(
                f, dll_path, func_name, args, kwargs,
                arg_ctypes, ret_ctype, ret_py_type, params, actual_fallback
            )

        if async_mode:
            return async_wrapper
        return wrapper

    return decorator


def _run_sync(
    func: Callable,
    dll_path: str,
    func_name: str,
    args: tuple,
    kwargs: dict,
    arg_ctypes: list,
    ret_ctype: Any,
    ret_py_type: Optional[type],
    params: list,
    fallback: Optional[Callable],
) -> Any:
    """同步调用 DLL 函数。

    优先调用 DLL 函数，若 DLL 不存在或调用失败且有 fallback，则调用 fallback。

    Args:
        func: 被装饰的函数对象。
        dll_path: DLL 文件路径。
        func_name: 要调用的函数名称。
        args: 调用时的位置参数。
        kwargs: 调用时的关键字参数。
        arg_ctypes: 参数类型列表（ctypes 类型）。
        ret_ctype: 返回值类型（ctypes 类型）。
        ret_py_type: 期望的 Python 返回类型，可为 None。
        params: 函数参数列表（inspect.Parameter 对象）。
        fallback: 回退函数，可为 None。

    Returns:
        Any: DLL 函数的返回值（已转换为 Python 类型），或 fallback 的返回值。

    Raises:
        FileNotFoundError: DLL 文件不存在且无 fallback 时抛出。
        Exception: 调用失败且无 fallback 时抛出。
    """
    if not os.path.exists(dll_path):
        if fallback:
            return fallback(*args, **kwargs)
        raise FileNotFoundError(f"DLL not found: {dll_path}")

    try:
        lib = _load_dll(dll_path)
        c_func = _setup_function(lib, func_name, arg_ctypes, ret_ctype)

        if kwargs:
            sig = inspect.signature(func)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            args = tuple(bound.arguments.values())

        converted_args = [
            _convert_arg(arg, c_type)
            for arg, c_type in zip(args, arg_ctypes)
        ]

        result = c_func(*converted_args)
        return _convert_result(result, ret_ctype, ret_py_type)

    except Exception:
        if fallback:
            return fallback(*args, **kwargs)
        raise


async def _run_async(
    func: Callable,
    dll_path: str,
    func_name: str,
    args: tuple,
    kwargs: dict,
    arg_ctypes: list,
    ret_ctype: Any,
    ret_py_type: Optional[type],
    params: list,
    fallback: Optional[Callable],
) -> Any:
    """异步调用 DLL 函数。

    在线程池中同步执行调用，避免阻塞事件循环。

    Args:
        func: 被装饰的函数对象。
        dll_path: DLL 文件路径。
        func_name: 要调用的函数名称。
        args: 调用时的位置参数。
        kwargs: 调用时的关键字参数。
        arg_ctypes: 参数类型列表（ctypes 类型）。
        ret_ctype: 返回值类型（ctypes 类型）。
        ret_py_type: 期望的 Python 返回类型，可为 None。
        params: 函数参数列表（inspect.Parameter 对象）。
        fallback: 回退函数，可为 None。

    Returns:
        Any: DLL 函数的返回值（已转换为 Python 类型），或 fallback 的返回值。
    """
    executor = _get_executor()
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        executor,
        lambda: _run_sync(
            func, dll_path, func_name, args, kwargs,
            arg_ctypes, ret_ctype, ret_py_type, params, fallback
        ),
    )
