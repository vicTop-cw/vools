"""
vools.bridge.freebasic.transport - 免序列化 Transport 抽象

把"如何把 Python 对象变成 ctypes 参数"封装为可替换的 Transport。
当前默认实现为 CtypesTransport（纯 ctypes，零外部依赖）。
未来 zinc 可用时可通过 set_transport(ZincTransport()) 注入更底层的 zero-copy 实现。

设计动机：
- nim bridge 的 seq_*.dll 走 CSV 序列化：list → str → bytes → C → str → list
  每次调用都要做三次往返，对大数据/高频调用成本明显
- 本模块让 list 直接以 POINTER(c_long) 形式传入，跳过 CSV 中转
"""

from typing import Any, Tuple, Protocol

import ctypes

from .types import FB_TO_CTYPES, is_array_type


class Transport(object):
    """
    Transport 抽象协议

    实现该协议可注入自定义序列化策略（如 zinc zero-copy）。
    """

    def prepare_arg(self, arg: Any, fb_type: str) -> Tuple[Any, Any]:
        """
        把 Python 值转成 (ctypes 值, ctypes 类型)

        参数：
            arg: Python 参数值
            fb_type: 对应的 FB 类型字符串

        返回：
            (ctypes-ready value, ctypes type) 元组
        """
        ...

    def prepare_ret(self, fb_type: str) -> Any:
        """
        返回 ctypes restype

        参数：
            fb_type: FB 返回类型字符串

        返回：
            ctypes 类型
        """
        ...

    def decode_result(self, value: Any, fb_type: str) -> Any:
        """
        把 ctypes 返回值解码回 Python 对象

        参数：
            value: ctypes 函数返回值
            fb_type: FB 返回类型字符串

        返回：
            Python 对象
        """
        ...


class CtypesTransport(Transport):
    """
    纯 ctypes 实现的 Transport

    规则：
    - int → (c_long(value), c_long)
    - float → (c_double(value), c_double)
    - bool → (c_bool(value), c_bool)
    - str → (value.encode('utf-8'), c_char_p)
    - bytes → (value, c_char_p)
    - list[int] → ((c_long * n)(*v), POINTER(c_long))，长度由调用方追加
    - list[float] → ((c_double * n)(*v), POINTER(c_double))，长度由调用方追加
    - 其他 → (c_void_p(value), c_void_p)
    """

    def prepare_arg(self, arg: Any, fb_type: str) -> Tuple[Any, Any]:
        if fb_type == 'Void' or fb_type is None:
            return (None, None)

        if fb_type == 'Long':
            if isinstance(arg, int):
                # 边界：超过 32 位走 longlong
                if -2**31 <= arg < 2**31:
                    return (ctypes.c_long(arg), ctypes.c_long)
                return (ctypes.c_longlong(arg), ctypes.c_longlong)
            return (ctypes.c_long(int(arg) if arg is not None else 0), ctypes.c_long)

        if fb_type == 'Double':
            return (ctypes.c_double(float(arg)), ctypes.c_double)

        if fb_type == 'Boolean':
            return (ctypes.c_bool(bool(arg)), ctypes.c_bool)

        if fb_type == 'ZString Ptr':
            if isinstance(arg, str):
                return (arg.encode('utf-8'), ctypes.c_char_p)
            if isinstance(arg, bytes):
                return (arg, ctypes.c_char_p)
            return (str(arg).encode('utf-8'), ctypes.c_char_p)

        if fb_type == 'Long Ptr':
            # list[int] → c_long array
            values = list(arg) if arg else []
            arr = (ctypes.c_long * len(values))(*values)
            return (arr, ctypes.POINTER(ctypes.c_long))

        if fb_type == 'Double Ptr':
            values = list(arg) if arg else []
            arr = (ctypes.c_double * len(values))(*values)
            return (arr, ctypes.POINTER(ctypes.c_double))

        # Any Ptr / 其他
        if arg is None:
            return (ctypes.c_void_p(0), ctypes.c_void_p)
        if isinstance(arg, int):
            return (ctypes.c_void_p(arg), ctypes.c_void_p)
        return (ctypes.c_void_p(0), ctypes.c_void_p)

    def prepare_ret(self, fb_type: str) -> Any:
        return FB_TO_CTYPES.get(fb_type)

    def decode_result(self, value: Any, fb_type: str) -> Any:
        if value is None:
            return None
        if fb_type == 'ZString Ptr':
            if isinstance(value, bytes):
                return value.decode('utf-8')
            return value
        if fb_type == 'Boolean':
            return bool(value)
        return value


class ZincTransport(Transport):
    """
    ZincTransport 占位实现

    当用户安装 `zinc` PyPI 包（Rust 编译的 Python 库，提供 zero-copy 跨语言交互）后，
    可在本类中实现基于 zinc 的真正零拷贝路径。
    本次实现仅保留入口与文档。

    启用方法：
        from vools.bridge.freebasic import set_transport
        set_transport(ZincTransport())  # 需要先 pip install zinc
    """

    def __init__(self):
        try:
            import zinc  # noqa: F401
            self._zinc = zinc
        except ImportError as e:
            raise NotImplementedError(
                "zinc not installed; install with `pip install zinc` to use "
                "ZincTransport for zero-copy FreeBASIC bridging."
            ) from e

    def prepare_arg(self, arg, fb_type):
        # TODO: 用户实现 zinc.Transport.prepare_arg
        raise NotImplementedError("ZincTransport.prepare_arg not yet implemented")

    def prepare_ret(self, fb_type):
        raise NotImplementedError("ZincTransport.prepare_ret not yet implemented")

    def decode_result(self, value, fb_type):
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
        from vools.bridge.freebasic import CtypesTransport, set_transport
        set_transport(MyCustomTransport())
    """
    global _default_transport
    _default_transport = transport
