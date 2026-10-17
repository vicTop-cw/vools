"""
DirectCOM 免注册 COM 加载支持

提供免注册方式加载 COM 组件的功能，主要用于加载 VBRichClient5 (RC6)。

两种加载路径：

1. 注册表路径（传统）：ProgID 已在注册表中注册，win32com EnsureDispatch
   直接解析 CLSID -> InprocServer32 即可。
2. 免注册 SxS 路径（自包含，推荐）：调用 CreateActCtxW 激活 _dlls 目录下的
   SxS manifest（声明 <comClass clsid=... progid=...>），之后
   CoCreateInstance 会优先从 manifest 声明的同目录 DLL 解析 in-proc 服务器，
   完全不依赖注册表。这样 dll32 只靠 `_dlls` 就能运行。

关键前提（实测踩过的坑）：
    vbRichClient5.dll 依赖 **vb_cairo_sqlite.dll**（约 2.8MB），而 RC6.dll
    依赖 **cairo_sqlite.dll**（另一份，约 3.9MB）。两者不是同一个文件。
    _dlls 若只放 cairo_sqlite.dll，vbRichClient5.dll 会因
    WinError 126（找不到指定的模块）而加载失败——表现和"注册表指向外部
    目录"很像，容易误判为注册问题。_dlls 必须两份都放。

用法:
    from vools.dll32._lib.com.directcom import DirectCOM

    dc = DirectCOM()
    obj = dc.create("vbRichClient5.cConstructor")
"""

__all__ = [
    "DirectCOM",
    "create_object",
    "enable_regfree",
    "create",
    "create_with_pythoncom",
]

import os
import sys
import ctypes
from typing import Optional, Any

# SxS manifest 文件名（放在 _dlls 目录）
SXS_MANIFEST_NAME = 'vbRichClient5.sxs.manifest'

# vbRichClient5 的 COM 类声明（与 vbRichClient5.manifest 一致）
_VBRC5_CLSID = '{CAECC935-9C70-4176-8BED-C39B2E33B31F}'
_VBRC5_PROGID = 'vbRichClient5.cConstructor'

# CreateActCtxW / ActivateActCtx
_ACTCTX_FLAG_ASSEMBLY_DIRECTORY_VALID = 0x4


class _ACTCTX(ctypes.Structure):
    """Win32 ACTCTX（用于 CreateActCtxW）。"""
    _fields_ = [
        ('cbSize', ctypes.c_ulong),
        ('dwFlags', ctypes.c_ulong),
        ('lpSource', ctypes.c_wchar_p),
        ('wProcessorArchitecture', ctypes.c_ushort),
        ('wLangId', ctypes.c_ushort),
        ('lpAssemblyDirectory', ctypes.c_wchar_p),
        ('lpResourceName', ctypes.c_wchar_p),
        ('lpApplicationName', ctypes.c_wchar_p),
        ('hModule', ctypes.c_void_p),
    ]


def _write_sxs_manifest(dll_dir: str) -> Optional[str]:
    """确保 _dlls 下存在可用的 SxS manifest，返回其路径。

    免注册 COM 需要 manifest 显式声明 comClass（clsid/progid/threadingModel）
    以及依赖 DLL 作为同级 file 项。
    """
    path = os.path.join(dll_dir, SXS_MANIFEST_NAME)
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">\n'
        '  <file name="vbRichClient5.dll">\n'
        '    <comClass clsid="{}" threadingModel="Apartment" progid="{}" />\n'
        '  </file>\n'
        '  <file name="vb_cairo_sqlite.dll" />\n'
        '  <file name="RC6.dll" />\n'
        '  <file name="cairo_sqlite.dll" />\n'
        '</assembly>\n'
    ).format(_VBRC5_CLSID, _VBRC5_PROGID)
    try:
        # 已存在且内容一致就不重写
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                if f.read() == xml:
                    return path
        with open(path, 'w', encoding='utf-8') as f:
            f.write(xml)
        return path
    except OSError:
        return None


class DirectCOM:
    """DirectCOM 免注册 COM 加载器

    优先走免注册 SxS activation context（_dlls 自包含）；失败时回退到
    注册表路径（win32com EnsureDispatch）。

    用法:
        dc = DirectCOM()
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
        self._actctx_handle = None
        self._actctx_cookie = None

        # 确保 DLL 在搜索路径中
        if self._dll_dir not in os.environ.get('PATH', ''):
            os.environ['PATH'] = self._dll_dir + os.pathsep + os.environ.get('PATH', '')

    def enable_regfree(self) -> bool:
        """激活 _dlls 下的 SxS manifest，启用免注册 COM（幂等）。

        CreateActCtxW 激活后，本进程后续 CoCreateInstance 会优先按 manifest
        声明的 <comClass clsid/progid> 从同目录 DLL 解析 in-proc 服务器，
        不再依赖注册表里的 ProgID -> InprocServer32。

        Returns:
            True 表示 activation context 已激活（或之前已激活）。
        """
        if self._actctx_handle:
            return True
        if not sys.platform == 'win32' and os.name != 'nt':
            return False
        manifest = _write_sxs_manifest(self._dll_dir)
        if not manifest or not os.path.exists(manifest):
            return False
        try:
            kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        except OSError:
            return False

        act = _ACTCTX()
        act.cbSize = ctypes.sizeof(_ACTCTX)
        act.dwFlags = _ACTCTX_FLAG_ASSEMBLY_DIRECTORY_VALID
        act.lpSource = manifest
        act.lpAssemblyDirectory = self._dll_dir
        act.wProcessorArchitecture = 0  # 当前进程架构
        act.wLangId = 0
        act.hModule = None

        handle = kernel32.CreateActCtxW(ctypes.byref(act))
        if not handle or handle == ctypes.c_void_p(-1).value:
            return False
        cookie = ctypes.c_ulong(0)
        if not kernel32.ActivateActCtx(handle, ctypes.byref(cookie)):
            kernel32.ReleaseActCtx(handle)
            return False
        self._actctx_handle = handle
        self._actctx_cookie = cookie.value
        return True

    def _ensure_pythoncom(self):
        """确保 pythoncom 已加载"""
        if self._pythoncom is None:
            try:
                import pythoncom
                from win32com.client.gencache import EnsureDispatch
                self._pythoncom = pythoncom
                self._Dispatch = EnsureDispatch
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

        注意:
            使用 win32com 的 EnsureDispatch（makepy 生成的强类型包装）。
            对 vbRichClient5 等带 TypeLib 的 VB6 COM 组件，makepy 是必需的：
            - 否则 AESEncrypt/ArcFour 等接受 SAFEARRAY(VT_UI1) 的方法会因
              win32com 无法把 bytes/array 转成 VB6 Byte Array 而报 "Type mismatch"。
            - comtypes 对 vbRichClient5 的 TypeLib 解析失败
              （GetRefTypeInfo failed, E:Cannot load DLL），不适用。
        """
        _, Dispatch = self._ensure_pythoncom()

        # 优先启用免注册 SxS：_dlls 自包含时无需注册表（可脱离外部目录运行）
        regfree = self.enable_regfree()

        try:
            # 使用 win32com 创建 COM 对象
            obj = Dispatch(prog_id)
            return obj
        except Exception as e:
            if regfree:
                # 免注册上下文已激活仍失败：多为依赖 DLL 缺失/不配对
                # （vbRichClient5.dll 需要 vb_cairo_sqlite.dll，不是 cairo_sqlite.dll）
                missing = os.path.join(self._dll_dir, 'vb_cairo_sqlite.dll')
                hint = ''
                if not os.path.exists(missing):
                    hint = ('\n提示: 缺少 {}（vbRichClient5.dll 的配对依赖，'
                            '与 RC6.dll 用的 cairo_sqlite.dll 不是同一个文件）').format(missing)
                raise RuntimeError(
                    f"无法创建 COM 对象 {prog_id}（免注册 SxS 已启用）: {e}{hint}"
                )
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

