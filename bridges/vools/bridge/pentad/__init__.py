"""
vools.bridge.pentad - Pentad 语言桥接模块

Pentad 是一门多范式语言，编译器为 `p5c`（Rust 实现，含 run/jit/dump/check 等子命令）。
本模块提供：

- @pentad 装饰器：将 Python 函数转换为 Pentad 代码（函数体即 Pentad 代码）
- compile_and_run：直接运行一段 Pentad 源码
- PentadBridge：继承 LangBridge 的桥接实现

使用示例::

    from vools.bridge.pentad import pentad, pentad_compiler_available

    if pentad_compiler_available():
        @pentad
        def add(x: int, y: int) -> int:
            return "print(x + y)"

        print(add(3, 5))   # -> 8

前置条件：
- p5c 可执行文件（位置由 vools.bridge.configs 统一解析：用户 JSON /
  VOOLS_PROJECTS_ROOT / VOOLS_PENTAD_ROOT / PATH）
"""

from .compiler import (
    PentadBridge,
    pentad,
    _pentad_bridge,
    compile_and_run,
    pentad_compiler_available,
    get_pentad_version,
    get_pentad_type,
)

pentad_bridge = _pentad_bridge

__all__ = [
    'PentadBridge',
    'pentad',
    'pentad_bridge',
    'compile_and_run',
    'pentad_compiler_available',
    'get_pentad_version',
    'get_pentad_type',
]