"""
dll32 核心模块

提供 32 位 Python 进程管理和跨进程通信功能。
"""
from ._spawn32 import Python32Process, get_process
from ._pipe_comm import call_dll, ping

__all__ = [
    'Python32Process',
    'get_process',
    'call_dll',
    'ping',
]
