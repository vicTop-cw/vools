"""
vools.bridge.lua - Lua 语言桥接模块

提供 Lua 动态执行与跨语言桥接能力。

设计目标：
- 通过 subprocess 调用 Lua 解释器执行代码
- 支持 JSON 序列化进行数据交换
- 装饰器模式：@lua 将 Python 函数转换为 Lua 代码执行
- 继承 LangBridge 统一接口

使用示例::

    from vools.bridge.lua import lua, lua_compiler_available

    if lua_compiler_available():
        @lua
        def fib(n: int) -> int:
            return '''
            function fib(n)
              if n <= 1 then return 1 end
              return fib(n-1) + fib(n-2)
            end
            print(fib(args[1]))
            '''

        print(fib(10))  # -> 89

前置条件：
- 安装 Lua（>= 5.3），并将 lua 加入 PATH
- 参考: https://www.lua.org/
"""

from .compiler import (
    lua,
    luae,
    lua_compiler_available,
    compile_and_run,
    LuaFuture,
    LuaBridge,
    _lua_bridge,
)
from .types import PY_TO_LUA_TYPE, LUA_TO_CTYPES, get_lua_type, get_lua_ctype

lua_bridge = _lua_bridge

__all__ = [
    'lua',
    'luae',
    'lua_compiler_available',
    'compile_and_run',
    'LuaFuture',
    'LuaBridge',
    'lua_bridge',
    'PY_TO_LUA_TYPE',
    'LUA_TO_CTYPES',
    'get_lua_type',
    'get_lua_ctype',
]
