"""Windows 窗口样式辅助 — GUI 类动作共用（toast / dialog 家族）。

round_corners(hwnd): 给指定窗口开系统圆角。
优先 DWM 系统圆角（Win11 22000+，系统级抗锯齿，观感最佳）；
不可用回退 SetWindowRgn 圆角矩形区域（Win10 可用，边缘无抗锯齿）；
均不可用返回 "none"（窗口保持方角，调用方出参如实标注）。

纯展示性增强：任何失败都不抛异常、不阻断动作，只降级。
"""

__all__ = ["round_corners"]

_DWMWA_WINDOW_CORNER_PREFERENCE = 33  # Win11 22000+
_DWMWCP_ROUND = 2


def round_corners(hwnd: int, radius: int = 24) -> str:
    """给窗口加四角圆角。返回 "dwm" | "region" | "none"。

    hwnd 非法（<=0）或 radius 非法（<=0）时直接 "none"（便于测试与降级路径）。
    """
    if not hwnd or hwnd <= 0 or radius <= 0:
        return "none"
    try:
        import ctypes
        from ctypes import wintypes

        dwm = ctypes.windll.dwmapi
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        dwm.DwmSetWindowAttribute.argtypes = (
            wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD)
        dwm.DwmSetWindowAttribute.restype = ctypes.c_long  # HRESULT
        user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
        user32.GetWindowRect.restype = wintypes.BOOL
        user32.SetWindowRgn.argtypes = (wintypes.HWND, wintypes.HANDLE, wintypes.BOOL)
        user32.SetWindowRgn.restype = wintypes.BOOL
        gdi32.CreateRoundRectRgn.argtypes = (
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.c_int, ctypes.c_int)
        gdi32.CreateRoundRectRgn.restype = wintypes.HANDLE

        hwnd_arg = wintypes.HWND(hwnd)

        # 1) Win11：DWM 系统圆角（系统抗锯齿，与窗口动画/阴影协调）
        pref = ctypes.c_int(_DWMWCP_ROUND)
        if dwm.DwmSetWindowAttribute(
                hwnd_arg, wintypes.DWORD(_DWMWA_WINDOW_CORNER_PREFERENCE),
                ctypes.byref(pref), ctypes.c_uint(4)) == 0:
            return "dwm"

        # 2) Win10 回退：SetWindowRgn 圆角矩形区域（边缘无抗锯齿）
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd_arg, ctypes.byref(rect)):
            return "none"
        w, h = rect.right - rect.left, rect.bottom - rect.top
        if w <= 0 or h <= 0:
            return "none"
        hrgn = gdi32.CreateRoundRectRgn(0, 0, w + 1, h + 1, radius, radius)
        if not hrgn:
            return "none"
        if user32.SetWindowRgn(hwnd_arg, hrgn, True):
            # 区域所有权已移交系统，按 Win32 契约不再 DeleteObject
            return "region"
        return "none"
    except Exception:
        return "none"
