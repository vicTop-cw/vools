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


def _should_skip(hwnd, radius) -> bool:
    """入参是否应直接降级为 "none"。

    **任何类型异常都按"非法"处理**：模块承诺「任何失败都不抛异常、只降级」，
    而 ``"abc" <= 0`` / ``[1] <= 0`` 这类不可比较值会在比较处抛 TypeError
    —— 校验本身也必须在这个 no-throw 契约内（BUG-A 收口）。
    ``None`` / 0 / ``False`` 走 falsy 分支属**正常**降级，行为保持不变。
    """
    try:
        return bool(not hwnd or hwnd <= 0 or radius <= 0)
    except TypeError:
        return True


def round_corners(hwnd: int, radius: int = 24) -> str:
    """给窗口加四角圆角。返回 "dwm" | "region" | "none"。

    hwnd 非法（<=0 / None / 非数值）或 radius 非法（<=0 / 非数值）时直接 "none"。
    """
    if _should_skip(hwnd, radius):
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
        # 失败回滚要用 DeleteObject：必须显式声明句柄类型，否则 ctypes 按 c_int
        # 传参会在 64 位句柄上溢出/截断 —— 那时"回滚"本身会失败，泄漏照旧。
        gdi32.DeleteObject.argtypes = (wintypes.HANDLE,)
        gdi32.DeleteObject.restype = wintypes.BOOL

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
            # 成功：区域所有权已移交系统，按 Win32 契约**不再** DeleteObject
            return "region"
        # 失败：SetWindowRgn 返回 0 表示系统**没有**接管该区域，必须自己释放 ——
        # 否则每次失败泄漏一个 GDI 句柄（实测 50 次失败 → GDI 对象 +50，BUG-B 收口）
        gdi32.DeleteObject(hrgn)
        return "none"
    except Exception:
        return "none"
