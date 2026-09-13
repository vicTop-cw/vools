"""
vools.bridge.tnr - Tnr 语言桥接模块

Tnr 是面向 AI 的张量数学语言（公式即代码，Rust 实现）。
本模块提供 Tnr 动态执行与跨语言桥接能力：

- @tnr 装饰器：将 Python 函数转换为 Tnr 代码执行（函数体即 Tnr 代码）
- compile_and_run：直接执行 Tnr 源码
- run_tnr_file：直接运行 .tnr 文件
- TnrBridge：继承 LangBridge 的桥接实现

使用示例::

    from vools.bridge.tnr import tnr, tnr_compiler_available

    if tnr_compiler_available():
        @tnr
        def add(x: int, y: int) -> int:
            return "print(x + y);"

        print(add(3, 5))   # -> 8

前置条件：
- Tnr 工具链可用（本机 E:\\IDEProjects\\AI\\Tnr\\target\\release\\tnr.exe 或 PATH/WSL 中的 tnr）
"""

from .compiler import (
    TnrBridge,
    tnr,
    _tnr_bridge,
    compile_and_run,
    run_tnr_file,
    tnr_compiler_available,
    get_tnr_version,
    get_tnr_type,
    _parse_tnr_output,
)

tnr_bridge = _tnr_bridge

__all__ = [
    'TnrBridge',
    'tnr',
    'tnr_bridge',
    'compile_and_run',
    'run_tnr_file',
    'tnr_compiler_available',
    'get_tnr_version',
    'get_tnr_type',
    '_parse_tnr_output',
]
