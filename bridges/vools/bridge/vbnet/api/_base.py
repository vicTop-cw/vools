"""
vools.bridge.vbnet.api._base - API.tlb 桥接核心模块

提供 COM 对象缓存、异常类和可用性检测功能。
"""

import platform
from typing import Any, Callable, Dict, Optional, Tuple


class APIBridgeError(Exception):
    """API 桥接异常基类

    所有 API.tlb 桥接相关的异常都从此类派生。
    """

    def __init__(self, message: str = "", cause: Optional[Exception] = None):
        super().__init__(message)
        self.cause = cause

    def __str__(self) -> str:
        if self.cause:
            return f"{super().__str__()} (原因: {self.cause})"
        return super().__str__()


_IS_WINDOWS = platform.system() == 'Windows'

_win32com_client = None
_win32com_import_error = None


def _get_win32com_client():
    """延迟导入 win32com.client 模块

    Returns:
        win32com.client 模块

    Raises:
        APIBridgeError: pywin32 未安装或非 Windows 平台
    """
    global _win32com_client, _win32com_import_error

    if not _IS_WINDOWS:
        raise APIBridgeError("API.tlb 桥接仅支持 Windows 平台")

    if _win32com_client is not None:
        return _win32com_client

    if _win32com_import_error is not None:
        raise APIBridgeError(
            "pywin32 未安装。请运行: pip install pywin32",
            cause=_win32com_import_error
        )

    try:
        import win32com.client.dynamic
        _win32com_client = win32com.client.dynamic
        return _win32com_client
    except ImportError as e:
        _win32com_import_error = e
        raise APIBridgeError(
            "pywin32 未安装。请运行: pip install pywin32",
            cause=e
        )


class _COMObjectCache:
    """COM 对象单例缓存

    管理 API.tlb 中的各种 COM 对象，确保每个 ProgID 只创建一次实例，
    提供延迟创建和缓存复用机制。

    支持的 ProgID:
        - API.Window
        - API.Mouse
        - API.Keyboard
        - API.Image
        - API.FileSystem
        - API.Process
        - API.Network
    """

    _SUPPORTED_PROGIDS = (
        "API.Window",
        "API.Mouse",
        "API.Keyboard",
        "API.Image",
        "API.FileSystem",
        "API.Process",
        "API.Network",
    )

    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._failed: Dict[str, Exception] = {}

    def get(self, prog_id: str) -> Any:
        """获取或创建 COM 对象实例

        Args:
            prog_id: COM 对象的 ProgID，例如 "API.Window"

        Returns:
            COM 对象实例（win32com.client.dynamic.CDispatch）

        Raises:
            APIBridgeError: COM 对象创建失败
        """
        if prog_id in self._cache:
            return self._cache[prog_id]

        if prog_id in self._failed:
            raise APIBridgeError(
                f"COM 对象 {prog_id} 之前创建失败",
                cause=self._failed[prog_id]
            )

        try:
            client = _get_win32com_client()
            obj = client.Dispatch(prog_id)
            self._cache[prog_id] = obj
            return obj
        except Exception as e:
            self._failed[prog_id] = e
            raise APIBridgeError(
                f"无法创建 COM 对象 {prog_id}。请确保 API.dll 已正确注册。",
                cause=e
            )

    def has(self, prog_id: str) -> bool:
        """检查指定 ProgID 的 COM 对象是否已成功创建并缓存

        Args:
            prog_id: COM 对象的 ProgID

        Returns:
            bool: 对象是否已缓存
        """
        return prog_id in self._cache

    def clear(self, prog_id: Optional[str] = None) -> None:
        """清除缓存

        Args:
            prog_id: 指定要清除的 ProgID，为 None 时清除全部缓存
        """
        if prog_id is None:
            self._cache.clear()
            self._failed.clear()
        else:
            self._cache.pop(prog_id, None)
            self._failed.pop(prog_id, None)

    @property
    def supported_progids(self):
        """获取支持的 ProgID 列表"""
        return self._SUPPORTED_PROGIDS


_com_object_cache = _COMObjectCache()


def is_api_available() -> bool:
    """检测 API.tlb COM 组件是否可用

    尝试创建 API.Window 对象来判断 API.dll 是否已正确注册。

    Returns:
        bool: API 组件是否可用
    """
    if not _IS_WINDOWS:
        return False

    try:
        _get_win32com_client()
    except APIBridgeError:
        return False

    try:
        _com_object_cache.get("API.Window")
        return True
    except APIBridgeError:
        return False


class _BaseModule:
    """API 模块基类

    封装通用的 COM 对象调用逻辑，包括：
    - 延迟获取 COM 对象
    - 异常转换（COM 异常 -> APIBridgeError）
    - 返回值类型转换
    """

    _prog_id: str = ""

    def __init__(self):
        self._com_obj = None

    @property
    def _obj(self):
        """延迟获取底层 COM 对象"""
        if self._com_obj is None:
            self._com_obj = _com_object_cache.get(self._prog_id)
        return self._com_obj

    def _call(self, method_name: str, *args, **kwargs) -> Any:
        """调用 COM 对象的方法

        Args:
            method_name: 方法名
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            方法返回值

        Raises:
            APIBridgeError: COM 调用异常
        """
        try:
            method = getattr(self._obj, method_name)
            return method(*args, **kwargs)
        except APIBridgeError:
            raise
        except Exception as e:
            raise APIBridgeError(
                f"调用 {self._prog_id}.{method_name} 失败",
                cause=e
            )

    def _call_bool(self, method_name: str, *args, **kwargs) -> bool:
        """调用返回布尔值的方法

        处理返回值可能为 None 的情况，None 视为 False。
        """
        result = self._call(method_name, *args, **kwargs)
        if result is None:
            return False
        return bool(result)

    def _call_int(self, method_name: str, *args, **kwargs) -> int:
        """调用返回整数的方法"""
        result = self._call(method_name, *args, **kwargs)
        return int(result) if result is not None else 0

    def _call_str(self, method_name: str, *args, **kwargs) -> str:
        """调用返回字符串的方法"""
        result = self._call(method_name, *args, **kwargs)
        return str(result) if result is not None else ""

    def _call_rect(self, method_name: str, *args, **kwargs) -> Tuple[int, int, int, int]:
        """调用返回 RECT 结构的方法，转换为 (left, top, right, bottom) 元组

        支持多种返回值格式：
        - 具有 Left/Top/Right/Bottom 属性的对象
        - 具有 left/top/right/bottom 属性的对象（小写）
        - 可索引对象（list/tuple 等）
        - 字典格式（'Left'/'Top'/'Right'/'Bottom' 或 'left'/'top'/'right'/'bottom'）
        """
        result = self._call(method_name, *args, **kwargs)
        if result is None:
            return (0, 0, 0, 0)
        try:
            return (int(result.Left), int(result.Top), int(result.Right), int(result.Bottom))
        except AttributeError:
            pass
        try:
            return (int(result.left), int(result.top), int(result.right), int(result.bottom))
        except AttributeError:
            pass
        try:
            return (int(result['Left']), int(result['Top']), int(result['Right']), int(result['Bottom']))
        except (TypeError, KeyError):
            pass
        try:
            return (int(result['left']), int(result['top']), int(result['right']), int(result['bottom']))
        except (TypeError, KeyError):
            pass
        try:
            return (int(result[0]), int(result[1]), int(result[2]), int(result[3]))
        except (TypeError, IndexError):
            pass
        return (0, 0, 0, 0)

    def _call_list(self, method_name: str, *args, **kwargs) -> list:
        """调用返回集合的方法，转换为 list

        支持多种集合类型：
        - 原生可迭代对象（list, tuple 等）
        - COM 集合（具有 Count 属性和 Item 方法）
        - .NET 集合（具有 Count 属性和索引器）
        - 单个对象（包装为单元素列表）
        """
        result = self._call(method_name, *args, **kwargs)
        if result is None:
            return []
        try:
            return list(result)
        except TypeError:
            pass
        try:
            count = result.Count
            items = []
            for i in range(count):
                try:
                    items.append(result.Item(i))
                except Exception:
                    try:
                        items.append(result(i))
                    except Exception:
                        break
            return items
        except AttributeError:
            pass
        try:
            count = len(result)
            items = []
            for i in range(count):
                items.append(result[i])
            return items
        except (TypeError, AttributeError):
            pass
        return [result]

    def _get_screen_size(self) -> Tuple[int, int]:
        """获取屏幕尺寸（宽度, 高度）

        通过获取桌面窗口的矩形区域来计算屏幕尺寸。

        Returns:
            tuple: (width, height) 屏幕宽度和高度
        """
        try:
            from .window import Window
            hwnd = Window.GetDesktopWindow()
            left, top, right, bottom = Window.GetWindowRect(hwnd)
            return (right - left, bottom - top)
        except Exception:
            try:
                import ctypes
                user32 = ctypes.windll.user32
                width = user32.GetSystemMetrics(0)
                height = user32.GetSystemMetrics(1)
                return (width, height)
            except Exception:
                return (1920, 1080)
