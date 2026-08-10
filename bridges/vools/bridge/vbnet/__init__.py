"""
vools.bridge.vbnet - VB.NET 语言桥接模块

提供 VB.NET 代码的动态编译和 DLL 调用能力，
以及 API.tlb COM 组件的 Python 封装。

前置条件：
- 安装 .NET SDK (dotnet) 并添加到 PATH
- 或提供预编译的 VB.NET DLL
- API.tlb 功能需要 Windows 平台 + API.dll 注册 + pywin32

用法：
    from vools.bridge.vbnet import vbnet, compile_and_run

    @vbnet
    def add(a: int, b: int) -> int:
        return "Return a + b"

    result = add(1, 2)  # 自动编译并调用

    # 异步执行
    @vbnet(async_mode=True)
    async def compute(x: int) -> int:
        return "Return x * x"

    result = await compute(5)

    # 直接运行代码
    result = compile_and_run("Return 42", args=())

    # API.tlb Windows 自动化
    from vools.bridge.vbnet import api
    if api.is_api_available():
        hwnd = api.Window.FindWindow("Notepad", None)
        api.Mouse.LeftClick()
"""

from .compiler import (
    vbnet,
    vb,
    vbnet_compiler_available,
    compile_and_run,
    VBNetFuture,
    VBNetBridge,
    _vbnet_bridge,
)
from .types import (
    PY_TO_VB_TYPE,
    VB_TO_CTYPES,
    get_vb_type,
    get_vb_ctype,
)

vbnet_bridge = _vbnet_bridge

_api_loaded = False
_api_error = None


def _load_api():
    """延迟加载 api 子模块"""
    global _api_loaded, _api_error
    if not _api_loaded:
        try:
            from . import api
            globals()['api'] = api
            _api_loaded = True
        except Exception as e:
            _api_error = e
            _api_loaded = False
    return _api_loaded


def __getattr__(name):
    """延迟加载属性"""
    if name == 'api':
        if _load_api():
            return globals().get('api')
        raise AttributeError(
            "module 'vools.bridge.vbnet' has no attribute 'api' "
            "(API 模块加载失败: %s)" % _api_error
        )
    raise AttributeError("module 'vools.bridge.vbnet' has no attribute '%s'" % name)


def __dir__():
    """返回所有可用的导出名称"""
    names = set(globals().keys()) | set(__all__)
    if _api_loaded or _load_api():
        names.add('api')
    return sorted(names)


__all__ = [
    'vbnet',
    'vb',
    'vbnet_compiler_available',
    'compile_and_run',
    'VBNetFuture',
    'VBNetBridge',
    'vbnet_bridge',
    'PY_TO_VB_TYPE',
    'VB_TO_CTYPES',
    'get_vb_type',
    'get_vb_ctype',
    'api',
]
