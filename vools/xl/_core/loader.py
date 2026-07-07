"""LibXL DLL 加载器"""
import os
import ctypes
from typing import Optional

from .._dlls import get_dll_path

_libxl_dll = None
_libxl_dll_path = None


class LibXLLoader:
    """LibXL DLL 加载器

    单例模式，确保 DLL 只加载一次。
    """

    _instance = None
    _dll = None

    def __new__(cls, dll_path: Optional[str] = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_dll(dll_path)
        return cls._instance

    def _load_dll(self, dll_path: Optional[str] = None):
        """加载 DLL

        Args:
            dll_path: DLL 路径，为 None 则使用内置 DLL
        """
        global _libxl_dll, _libxl_dll_path

        if dll_path is None:
            dll_path = get_dll_path('libxl.dll')

        if not os.path.exists(dll_path):
            raise FileNotFoundError(f"LibXL DLL not found: {dll_path}")

        self._dll = ctypes.CDLL(dll_path)
        _libxl_dll = self._dll
        _libxl_dll_path = dll_path

    @property
    def dll(self) -> ctypes.CDLL:
        """获取 DLL 实例"""
        return self._dll

    @property
    def dll_path(self) -> str:
        """获取 DLL 路径"""
        return _libxl_dll_path


def get_libxl_dll(dll_path: Optional[str] = None) -> ctypes.CDLL:
    """获取 LibXL DLL 实例

    Args:
        dll_path: DLL 路径，为 None 则使用内置 DLL

    Returns:
        ctypes.CDLL 实例
    """
    global _libxl_dll
    if _libxl_dll is None:
        loader = LibXLLoader(dll_path)
        _libxl_dll = loader.dll
    return _libxl_dll


__all__ = [
    'LibXLLoader',
    'get_libxl_dll',
]
