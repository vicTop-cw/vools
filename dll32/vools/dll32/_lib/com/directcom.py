"""
DirectCOM 免注册 COM 加载支持

提供免注册方式加载 COM 组件的功能，主要用于加载 VBRichClient5 (RC6)。

注意: 当前实现主要依赖 pythoncom 的 Dispatch 方式，
如果 RC6 已注册则可以直接使用。

用法:
    from vools.dll32._lib.com.directcom import DirectCom

    # 方式1: 直接使用 pythoncom (需要 RC6 已注册)
    obj = DirectCom.create("vbRichClient5.cConstructor")

    # 方式2: 通过 DirectCOM (待完善)
    # 需要进一步研究 DirectCOM 的调用方式
"""
import os
import sys
import ctypes
from typing import Optional, Any


class DirectCOM:
    """DirectCOM 免注册 COM 加载器

    当前实现:
        - 主要使用 pythoncom 的 Dispatch 方式 (需要 RC6 注册)
        - 尝试使用 DirectCOM.dll 的免注册功能 (待完善)

    用法:
        dc = DirectCom()
        obj = dc.create("vbRichClient5.cConstructor")
    """

    def __init__(self, dll_dir: Optional[str] = None):
        """初始化 DirectCOM

        Args:
            dll_dir: DLL 文件目录
        """
        if dll_dir is None:
            dll_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                '_dlls'
            )
        self._dll_dir = dll_dir
        self._pythoncom = None
        self._win32com_client = None

        # 确保 DLL 在搜索路径中
        if self._dll_dir not in os.environ.get('PATH', ''):
            os.environ['PATH'] = self._dll_dir + os.pathsep + os.environ.get('PATH', '')

    def _ensure_pythoncom(self):
        """确保 pythoncom 已加载"""
        if self._pythoncom is None:
            try:
                import pythoncom
                from win32com.client import Dispatch
                self._pythoncom = pythoncom
                self._Dispatch = Dispatch
            except ImportError as e:
                raise ImportError(
                    "pythoncom 未安装。请确保 Python 32 位环境中已安装 pywin32:\n"
                    "在 32 位 Python 环境中运行: pip install pywin32"
                )
        return self._pythoncom, self._Dispatch

    def create(self, prog_id: str) -> Any:
        """创建 COM 对象

        Args:
            prog_id: ProgID，例如 "vbRichClient5.cConstructor"

        Returns:
            COM 对象
        """
        _, Dispatch = self._ensure_pythoncom()

        try:
            # 使用 win32com 创建 COM 对象
            obj = Dispatch(prog_id)
            return obj
        except Exception as e:
            raise RuntimeError(f"无法创建 COM 对象 {prog_id}: {e}")

    def create_with_pythoncom(self, prog_id: str) -> Any:
        """使用 pythoncom 创建对象 (显式方式)

        Args:
            prog_id: ProgID

        Returns:
            COM 对象
        """
        return self.create(prog_id)

    def __repr__(self) -> str:
        return f"<DirectCOM dll_dir={self._dll_dir}>"


# 创建简化的 create_object 别名
def create_object(prog_id: str, dll_dir: Optional[str] = None) -> Any:
    """创建 COM 对象的便捷函数

    Args:
        prog_id: ProgID
        dll_dir: DLL 目录

    Returns:
        COM 对象
    """
    dc = DirectCOM(dll_dir)
    return dc.create(prog_id)
