"""
函数签名注册表

提供 VB6Plus.dll、VB6OpenSSL.dll、VB6MQTT.dll 等 DLL 的函数签名管理。
"""
from ._registry import SIGNATURES, get_signature, list_dlls, list_functions

__all__ = [
    'SIGNATURES',
    'get_signature',
    'list_dlls',
    'list_functions',
]
