"""
vools.sys - 外部系统资源轻量桥接子包

提供外部可执行文件（exe）和动态链接库（dll/so）的轻量桥接能力，
以及系统集成 CLI 工具。通过装饰器模式，用 Python 函数签名定义接口，
框架自动完成参数映射、类型转换、同步/异步调用和回退机制。

子模块：
    exe: @exe 装饰器，调用外部可执行文件
    dll: @dll 装饰器，调用外部 DLL/共享库
    dll_cmd: DLL 管理 CLI 子命令
    compile_cmd: 编译 CLI 子命令
    run_cmd: 运行 CLI 子命令
    env_cmd: 环境探测 CLI 子命令
    env: get_env 系统环境变量读取（PowerShell/Shell 加速）
    fire_app: 基于 Python Fire 的 CLI 入口

用法：
    from vools.sys import exe, dll, SysCLI, get_env

    # @exe 装饰器
    @exe("echo")
    def echo(msg: str):
        pass
    returncode, stdout, stderr = echo("hello")

    # @dll 装饰器
    @dll("mylib.dll::add")
    def add(a: int, b: int) -> int:
        pass
    result = add(3, 5)

    # get_env 系统环境变量读取
    path = get_env("PATH")
"""

from .fire_app import SysCLI
from .exe import exe
from .dll import dll
from .env import get_env, get_env_with_default

__all__ = ['SysCLI', 'exe', 'dll', 'get_env', 'get_env_with_default']
