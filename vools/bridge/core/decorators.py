"""
vools.bridge.core.decorators - 桥接装饰器

提供 @bridge_function 和 @bridge_module 装饰器，简化跨语言函数定义。
支持从类型注解自动推断参数类型、自动转换参数和返回值、fallback 机制等。
"""

import functools
import inspect
import ctypes

from .types import CTypeMapper


_FUNC_NAME_ATTR = '_bridge_func_name'


def _get_signature_info(func):
    """
    从函数签名中提取参数类型和返回类型信息。

    参数：
        func: 要分析的函数

    返回：
        (param_names, param_types, return_type) 元组
        param_names: 参数名称列表
        param_types: 参数类型列表（与 param_names 对应），
                     无注解的参数类型为 None
        return_type: 返回类型注解，无注解则为 None
    """
    try:
        sig = inspect.signature(func)
    except (ValueError, TypeError):
        return [], [], None

    param_names = []
    param_types = []
    for name, param in sig.parameters.items():
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue
        param_names.append(name)
        if param.annotation is not param.empty:
            param_types.append(param.annotation)
        else:
            param_types.append(None)

    return_type = None
    if sig.return_annotation is not sig.empty:
        return_type = sig.return_annotation

    return param_names, param_types, return_type


def _resolve_ctypes_types(param_types, return_type):
    """
    将 Python 类型解析为 ctypes 类型。

    参数：
        param_types: Python 参数类型列表
        return_type: Python 返回类型

    返回：
        (argtypes, restype) 元组
        argtypes: ctypes 参数类型列表
        restype: ctypes 返回类型，可能为 None
    """
    argtypes = []
    for py_type in param_types:
        if py_type is None:
            argtypes.append(None)
        else:
            c_type = CTypeMapper.get_ctype(py_type)
            if c_type is None:
                argtypes.append(ctypes.c_void_p)
            else:
                argtypes.append(c_type)

    restype = CTypeMapper.infer_ret_type(return_type)

    return argtypes, restype


def _convert_args(args, argtypes):
    """
    转换参数以匹配 ctypes 类型要求。

    目前支持的转换：
        - str -> bytes (utf-8 编码)，当对应类型为 c_char_p 时

    参数：
        args: 原始参数值列表
        argtypes: ctypes 参数类型列表

    返回：
        转换后的参数列表
    """
    return CTypeMapper.convert_args(args, argtypes)


def _convert_result(result, return_type):
    """
    转换返回值以匹配 Python 类型期望。

    目前支持的转换：
        - bytes -> str (utf-8 解码)，当返回类型注解为 str 时

    参数：
        result: 原始返回值
        return_type: Python 返回类型注解

    返回：
        转换后的返回值
    """
    if return_type is str and isinstance(result, bytes):
        return result.decode('utf-8')
    return result


def _make_bridge_wrapper(func, language, lib_name, func_name, fallback,
                         serializer, deserializer, skip_first_arg=False):
    """
    创建桥接函数包装器的内部辅助函数。

    参数：
        func: 原始函数
        language: 目标语言名称
        lib_name: 共享库名称
        func_name: 库中的函数名称
        fallback: 回退函数
        serializer: 参数序列化函数
        deserializer: 返回值反序列化函数
        skip_first_arg: 是否跳过第一个参数（用于类方法的 self）

    返回：
        包装后的函数
    """
    param_names, param_types, return_type = _get_signature_info(func)

    if skip_first_arg and param_names:
        param_names = param_names[1:]
        param_types = param_types[1:]

    argtypes, restype = _resolve_ctypes_types(param_types, return_type)

    _lib = None
    _lib_loaded = False

    def _get_lib():
        nonlocal _lib, _lib_loaded
        if _lib_loaded:
            return _lib
        from .loader import load_library

        resolved_lib_name = lib_name
        if resolved_lib_name is None:
            resolved_lib_name = func.__name__.split('_')[0]

        _lib = load_library(language, resolved_lib_name)
        _lib_loaded = True
        return _lib

    def _setup_func(lib):
        try:
            fn = getattr(lib, func_name)
        except AttributeError:
            return None

        has_defined_types = any(t is not None for t in argtypes) or restype is not None
        if has_defined_types:
            valid_argtypes = [t for t in argtypes if t is not None]
            if valid_argtypes and len(valid_argtypes) == len(argtypes):
                fn.argtypes = argtypes
            if restype is not None:
                fn.restype = restype

        return fn

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        call_args = list(args)
        if skip_first_arg:
            call_args = call_args[1:]

        lib = _get_lib()
        if lib is not None:
            try:
                fn = _setup_func(lib)
                if fn is not None:
                    if serializer:
                        call_args = list(serializer(*call_args))
                    else:
                        call_args = _convert_args(call_args, argtypes)

                    result = fn(*call_args)

                    if deserializer:
                        result = deserializer(result)
                    else:
                        result = _convert_result(result, return_type)

                    return result
            except Exception:
                pass

        if fallback is not None:
            return fallback(*args, **kwargs)
        raise RuntimeError(
            "No %s implementation available for '%s' "
            "(library: %s, function: %s)" % (
                language, func.__name__,
                lib_name or func.__name__.split('_')[0],
                func_name
            )
        )

    wrapper._bridge_info = {
        'language': language,
        'lib_name': lib_name,
        'func_name': func_name,
        'fallback': fallback,
        'argtypes': argtypes,
        'restype': restype,
        'param_names': param_names,
        'return_type': return_type,
        'skip_first_arg': skip_first_arg,
    }

    return wrapper


def bridge_function(language, fallback=None, lib_name=None, func_name=None,
                   serializer=None, deserializer=None):
    """
    桥接函数装饰器

    将一个 Python 函数标记为可以使用其他语言实现的桥接函数。
    如果对应语言的库可用，将调用底层实现；否则调用 fallback。

    支持从函数签名的类型注解自动推断参数类型和返回类型，
    使用 CTypeMapper 进行类型映射，并自动处理 str/bytes 转换。

    参数：
        language: 目标语言名称（如 "nim"）
        fallback: Python 回退实现函数，当底层库不可用时调用
        lib_name: 共享库名称（默认根据函数名自动推导）
        func_name: 库中的函数名称（默认与 Python 函数名相同）
        serializer: 参数序列化函数（可选，自定义序列化逻辑）
        deserializer: 返回值反序列化函数（可选，自定义反序列化逻辑）

    返回：
        装饰器函数

    用法：
        @bridge_function("nim", fallback=_py_md5)
        def md5(data: bytes, length: int) -> bytes:
            pass  # 实现将由底层提供

        # 带 str 类型注解会自动编码/解码
        @bridge_function("nim", lib_name="vools_crypto", func_name="md5_hash")
        def md5_hash(data: str, length: int) -> str:
            pass
    """

    def decorator(func):
        nonlocal func_name

        resolved_func_name = func_name
        if resolved_func_name is None:
            resolved_func_name = func.__name__

        return _make_bridge_wrapper(
            func, language, lib_name, resolved_func_name,
            fallback, serializer, deserializer, skip_first_arg=False
        )

    return decorator


def bridge_func_name(name):
    """
    指定桥接函数在底层库中的名称。

    用于 @bridge_module 中的方法，单独指定函数名。

    参数：
        name: 底层库中的函数名称

    返回：
        装饰器函数

    用法：
        @bridge_module("nim", lib_name="vools_crypto")
        class Crypto:
            @bridge_func_name("md5_hash")
            def md5(self, data: bytes, length: int) -> bytes:
                pass
    """
    def decorator(func):
        setattr(func, _FUNC_NAME_ATTR, name)
        return func
    return decorator


def bridge_module(language, lib_name=None, lib_names=None):
    """
    桥接模块装饰器

    将一个类标记为桥接模块，类中的所有公共方法自动使用对应语言的实现。
    支持从方法签名的类型注解自动推断参数类型和返回类型。

    方法的第一个参数（self）会被自动跳过，不会传递给底层 C 函数。

    参数：
        language: 目标语言名称（如 "nim"）
        lib_name: 单个共享库名称（与 lib_names 二选一）
        lib_names: 共享库名称列表，按顺序尝试加载（与 lib_name 二选一）

    返回：
        装饰器函数

    用法：
        @bridge_module("nim", lib_name="vools_crypto")
        class CryptoModule:
            def md5_hash(self, data: bytes, length: int) -> bytes:
                pass

            @bridge_func_name("sha1_hash")
            def sha1(self, data: bytes, length: int) -> bytes:
                pass

        # 多库支持
        @bridge_module("nim", lib_names=["vools_crypto", "vools_encoding"])
        class CombinedModule:
            def md5_hash(self, data: bytes, length: int) -> bytes:
                pass
            def base64_encode(self, data: bytes, length: int) -> bytes:
                pass
    """

    def decorator(cls):
        resolved_lib_names = []
        if lib_names is not None:
            resolved_lib_names = list(lib_names)
        elif lib_name is not None:
            resolved_lib_names = [lib_name]

        for name in dir(cls):
            if name.startswith('_'):
                continue

            attr = getattr(cls, name)
            if not callable(attr):
                continue

            if isinstance(attr, type):
                continue

            custom_func_name = getattr(attr, _FUNC_NAME_ATTR, None)

            method_lib_names = resolved_lib_names
            if not method_lib_names:
                method_lib_names = [name.split('_')[0]]

            def _make_method_wrapper(method_attr, method_name, custom_fn_name, libs):
                resolved_fn_name = custom_fn_name or method_name

                if len(libs) <= 1:
                    first_lib = libs[0] if libs else None
                    return _make_bridge_wrapper(
                        method_attr, language, first_lib,
                        resolved_fn_name, None, None, None,
                        skip_first_arg=True
                    )

                @functools.wraps(method_attr)
                def multi_lib_wrapper(*args, **kwargs):
                    from .loader import load_library

                    call_args = list(args)[1:]  # skip self

                    _, param_types, return_type = _get_signature_info(method_attr)
                    if param_types:
                        param_types = param_types[1:]
                    argtypes, restype = _resolve_ctypes_types(param_types, return_type)

                    for lib_n in libs:
                        try:
                            lib = load_library(language, lib_n)
                            if lib is None:
                                continue
                            try:
                                fn = getattr(lib, resolved_fn_name)
                            except AttributeError:
                                continue

                            has_defined_types = any(t is not None for t in argtypes) or restype is not None
                            if has_defined_types:
                                valid_argtypes = [t for t in argtypes if t is not None]
                                if valid_argtypes and len(valid_argtypes) == len(argtypes):
                                    fn.argtypes = argtypes
                                if restype is not None:
                                    fn.restype = restype

                            converted_args = _convert_args(call_args, argtypes)
                            result = fn(*converted_args)
                            result = _convert_result(result, return_type)
                            return result
                        except Exception:
                            continue

                    raise RuntimeError(
                        "No %s implementation available for '%s' "
                        "(tried libraries: %s)" % (
                            language, method_name, ', '.join(libs)
                        )
                    )

                return multi_lib_wrapper

            wrapped = _make_method_wrapper(attr, name, custom_func_name, method_lib_names)
            setattr(cls, name, wrapped)

        return cls

    return decorator
