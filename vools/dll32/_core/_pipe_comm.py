"""
管道通信模块

提供与 32 位 Python 进程的 JSON-RPC 通信。
"""
from ._spawn32 import get_process


def call_dll(dll_path, func_name, args):
    """调用 32 位 DLL 函数"""
    proc = get_process()
    return proc.call('call_dll', [dll_path, func_name, args])


def ping():
    """Ping 检查"""
    proc = get_process()
    return proc.call('ping')