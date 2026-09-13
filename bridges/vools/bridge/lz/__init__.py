"""
vools.bridge.lz - LZ (Lang-Zone) 语言桥接模块

LZ 是面向系统编程的静态类型语言（LZ → Rust，IR 中间表示路线）。
本模块提供 LZ 转译与跨语言桥接能力：

- @lz 装饰器：将 Python 函数转换为 LZ 代码（函数体即 LZ 代码）
- compile_and_run：直接转译一段 LZ 源码
- LzBridge：继承 LangBridge 的桥接实现

使用示例::

    from vools.bridge.lz import lz, lz_compiler_available

    if lz_compiler_available():
        @lz
        def hello(x: int) -> int:
            return '''
            def main():
                let v = arg0 + 1
                print(v)
            '''

        # rustc 可用时返回执行输出；否则返回生成的 .rs 路径
        print(hello(1))

前置条件：
- lang-zone 工具链（E:\\IDEProjects\\AI\\lang-zone\\target\\debug\\lang-zone.exe 或 PATH）
- rustc + lz_builtins crate（可选，用于转译后编译执行）
"""

from .compiler import (
    LzBridge,
    lz,
    _lz_bridge,
    compile_and_run,
    lz_compiler_available,
    get_lz_version,
    get_lz_type,
    rustc_available,
)

lz_bridge = _lz_bridge

__all__ = [
    'LzBridge',
    'lz',
    'lz_bridge',
    'compile_and_run',
    'lz_compiler_available',
    'get_lz_version',
    'get_lz_type',
    'rustc_available',
]
