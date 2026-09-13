"""
vools.bridge.zi - 兹（Zi）语言桥接模块

兹是一门以中文为主、编译到 BEAM 字节码（Elixir/Erlang）的编程语言，
编译器为 Python 包 zhi。本模块提供：

- @zi 装饰器：将 Python 函数转换为兹代码（函数体即兹代码）
- compile_and_run：直接运行一段兹源码
- ZiBridge：继承 LangBridge 的桥接实现

使用示例::

    from vools.bridge.zi import zi, zi_compiler_available

    if zi_compiler_available():
        @zi
        def hello() -> str:
            return '''
            坊 示例

            策 主
                言 "你好，兹"
            '''

        print(hello())   # -> 你好，兹

前置条件：
- zhi 编译器（E:\\IDEProjects\\AI\\兹\\zhi\\src）可导入
- Elixir 运行时（zhi 编译到 BEAM 需要）
"""

from .compiler import (
    ZiBridge,
    zi,
    _zi_bridge,
    compile_and_run,
    zi_compiler_available,
    get_zi_version,
    get_zi_type,
)

zi_bridge = _zi_bridge

__all__ = [
    'ZiBridge',
    'zi',
    'zi_bridge',
    'compile_and_run',
    'zi_compiler_available',
    'get_zi_version',
    'get_zi_type',
]
