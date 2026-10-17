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
_api_loading = False


def _load_api():
    """延迟加载 api 子模块

    不能用 `from . import api`（2026-10-17 寻虫 BUG-77 同族）：本模块有模块级
    __getattr__，`from . import api` 会走 _handle_fromlist 对父包 hasattr，
    而 hasattr 又触发 __getattr__ → 再调 _load_api，一次属性访问自递归几十层
    （实测 entries=50）。importlib.import_module 不查父包属性，天然无此环；
    _api_loading 再兜一层防重入。
    """
    global _api_loaded, _api_error, _api_loading
    if _api_loaded:
        return True
    if _api_loading:
        return False                       # 重入直接判失败，绝不递归
    _api_loading = True
    try:
        import importlib
        mod = importlib.import_module('.api', __name__)
        globals()['api'] = mod
        _api_loaded = True
    except Exception as e:
        _api_error = e
        _api_loaded = False
    finally:
        _api_loading = False
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


# Python 3.6 兼容：模块级 __getattr__ 是 PEP 562（3.7+ 才生效），3.6 下是死函数。
# 实测 py3.6：`from vools.bridge.vbnet import api` 能成（importlib 的 from-import
# 会退回直接导入子模块），但 `vools.bridge.vbnet.api` 属性访问拿到 MISSING ——
# 同一个包两种写法两种结果（2026-10-17 寻虫 BUG-78 同族；vools-bridges
# requires-python = ">=3.6"，属承诺范围内必须可用）。按同仓 vools/__init__.py、
# vools/datetime、vools/decorators、vools/sql、vools/pyk 的 <3.7 分支做法主动绑上；
# 绑不上（缺 pywin32 等真实依赖）时保持缺席，与 3.7+ 下 __getattr__ 抛
# AttributeError 的行为一致。
import sys as _sys

if _sys.version_info < (3, 7) and 'api' not in globals():
    _load_api()


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
