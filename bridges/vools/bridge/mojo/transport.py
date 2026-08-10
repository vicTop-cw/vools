"""
vools.bridge.mojo.transport - 免序列化 Transport 抽象

把"如何把 Python 对象变成 ctypes 参数"封装为可替换的 Transport。
当前默认实现为 CtypesTransport（纯 ctypes，零外部依赖）。
未来 zinc / Mojo from Python 等 zero-copy 方案可用时可通过
set_transport(...) 注入更底层的实现。

设计动机：
- nim bridge 的 seq_*.dll 走 CSV 序列化：list -> str -> bytes -> C -> str -> list
  每次调用都要做三次往返，对大数据/高频调用成本明显
- 本模块让 list 直接以 POINTER(c_longlong) 形式传入，跳过 CSV 中转
"""

from typing import Any, Tuple

import ctypes

from .types import MOJO_TO_CTYPES, is_array_type, array_length_type


class Transport(object):
    """
    Transport 抽象协议

    实现该协议可注入自定义序列化策略（如 zinc zero-copy）。
    """

    def prepare_arg(self, arg: Any, mojo_type: str) -> Tuple[Any, Any]:
        """
        把 Python 值转成 (ctypes 值, ctypes 类型)

        参数：
            arg: Python 参数值
            mojo_type: 对应的 Mojo 类型字符串

        返回：
            (ctypes-ready value, ctypes type) 元组
        """
        ...

    def prepare_ret(self, mojo_type: str) -> Any:
        """
        返回 ctypes restype

        参数：
            mojo_type: Mojo 返回类型字符串

        返回：
            ctypes 类型
        """
        ...

    def decode_result(self, value: Any, mojo_type: str) -> Any:
        """
        把 ctypes 返回值解码回 Python 对象

        参数：
            value: ctypes 函数返回值
            mojo_type: Mojo 返回类型字符串

        返回：
            Python 对象
        """
        ...


class CtypesTransport(Transport):
    """
    纯 ctypes 实现的 Transport

    规则：
    - int -> (c_longlong(value), c_longlong)
    - float -> (c_double(value), c_double)
    - bool -> (c_int(1 or 0), c_int)
    - str -> (value.encode('utf-8'), c_char_p)
    - bytes -> (value, c_char_p)
    - list[int] -> ((c_longlong * n)(*v), POINTER(c_longlong))，长度由调用方追加
    - list[float] -> ((c_double * n)(*v), POINTER(c_double))，长度由调用方追加
    - 其他 -> (c_void_p(value), c_void_p)
    """

    def prepare_arg(self, arg: Any, mojo_type: str) -> Tuple[Any, Any]:
        if mojo_type in ('None', 'void', None):
            return (None, None)

        if mojo_type == 'Int64':
            if isinstance(arg, bool):
                return (ctypes.c_longlong(1 if arg else 0), ctypes.c_longlong)
            if isinstance(arg, int):
                return (ctypes.c_longlong(arg), ctypes.c_longlong)
            return (ctypes.c_longlong(int(arg) if arg is not None else 0),
                    ctypes.c_longlong)

        if mojo_type == 'Int32':
            return (ctypes.c_int32(int(arg) if arg is not None else 0),
                    ctypes.c_int32)

        if mojo_type == 'Float64':
            return (ctypes.c_double(float(arg) if arg is not None else 0.0),
                    ctypes.c_double)

        if mojo_type == 'Float32':
            return (ctypes.c_float(float(arg) if arg is not None else 0.0),
                    ctypes.c_float)

        if mojo_type == 'Bool':
            return (ctypes.c_int(1 if bool(arg) else 0), ctypes.c_int)

        if mojo_type == 'UnsafePointer[c_char]':
            if isinstance(arg, str):
                return (arg.encode('utf-8'), ctypes.c_char_p)
            if isinstance(arg, bytes):
                return (arg, ctypes.c_char_p)
            return (str(arg).encode('utf-8'), ctypes.c_char_p)

        if mojo_type == 'UnsafePointer[Int64]':
            values = list(arg) if arg else []
            arr = (ctypes.c_longlong * len(values))(*values)
            return (arr, ctypes.POINTER(ctypes.c_longlong))

        if mojo_type == 'UnsafePointer[Float64]':
            values = list(arg) if arg else []
            arr = (ctypes.c_double * len(values))(*values)
            return (arr, ctypes.POINTER(ctypes.c_double))

        if mojo_type == 'UnsafePointer[Int32]':
            values = list(arg) if arg else []
            arr = (ctypes.c_int32 * len(values))(*values)
            return (arr, ctypes.POINTER(ctypes.c_int32))

        if mojo_type == 'UnsafePointer[Float32]':
            values = list(arg) if arg else []
            arr = (ctypes.c_float * len(values))(*values)
            return (arr, ctypes.POINTER(ctypes.c_float))

        # OpaquePointer / 其他
        if arg is None:
            return (ctypes.c_void_p(0), ctypes.c_void_p)
        if isinstance(arg, int):
            return (ctypes.c_void_p(arg), ctypes.c_void_p)
        return (ctypes.c_void_p(0), ctypes.c_void_p)

    def prepare_ret(self, mojo_type: str) -> Any:
        return MOJO_TO_CTYPES.get(mojo_type, ctypes.c_longlong)

    def decode_result(self, value: Any, mojo_type: str) -> Any:
        if value is None:
            return None
        if mojo_type == 'UnsafePointer[c_char]':
            if isinstance(value, bytes):
                return value.decode('utf-8')
            if isinstance(value, ctypes.c_char_p):
                raw = value.value
                if raw is None:
                    return None
                if isinstance(raw, bytes):
                    return raw.decode('utf-8')
                return raw
            return value
        if mojo_type == 'Bool':
            return bool(value)
        return value


class ZincTransport(Transport):
    """
    ZincTransport 占位实现

    当用户安装 `zinc` PyPI 包（Rust 编译的 Python 库，提供 zero-copy 跨语言交互）后，
    可在本类中实现基于 zinc 的真正零拷贝路径。
    本次实现仅保留入口与文档。
    """

    def __init__(self):
        try:
            import zinc  # noqa: F401
            self._zinc = zinc
        except ImportError as e:
            raise NotImplementedError(
                "zinc not installed; install with `pip install zinc` to use "
                "ZincTransport for zero-copy Mojo bridging."
            ) from e

    def prepare_arg(self, arg, mojo_type):
        raise NotImplementedError("ZincTransport.prepare_arg not yet implemented")

    def prepare_ret(self, mojo_type):
        raise NotImplementedError("ZincTransport.prepare_ret not yet implemented")

    def decode_result(self, value, mojo_type):
        raise NotImplementedError("ZincTransport.decode_result not yet implemented")


# ----------------------------------------------------------------------------
# 模块级 Transport 状态
# ----------------------------------------------------------------------------

_default_transport = CtypesTransport()


def get_transport() -> Transport:
    """获取当前 Transport 实例（默认 CtypesTransport）"""
    return _default_transport


def set_transport(transport: Transport) -> None:
    """
    全局替换 Transport

    用法：
        from vools.bridge.mojo import CtypesTransport, set_transport
        set_transport(MyCustomTransport())
    """
    global _default_transport
    _default_transport = transport
