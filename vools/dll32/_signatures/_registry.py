"""
函数签名注册表

集中管理所有 DLL 函数的签名定义。
"""
from typing import Dict, Optional, List

# 从各个 DLL 签名模块导入
from .vb6plus import VB6PLUS_SIGNATURES
from .openssl import OPENSSL_SIGNATURES
from .mqtt import MQTT_SIGNATURES

# 统一的签名注册表
SIGNATURES: Dict[str, Dict[str, dict]] = {
    'VB6Plus.dll': VB6PLUS_SIGNATURES,
    'VB6OpenSSL.dll': OPENSSL_SIGNATURES,
    'VB6MQTT.dll': MQTT_SIGNATURES,
}


def get_signature(dll_name: str, func_name: str) -> Optional[dict]:
    """获取指定 DLL 和函数的签名

    Args:
        dll_name: DLL 名称
        func_name: 函数名称

    Returns:
        函数签名字典，如果不存在返回 None
    """
    dll_sigs = SIGNATURES.get(dll_name, {})
    return dll_sigs.get(func_name)


def list_dlls() -> List[str]:
    """列出所有已注册的 DLL"""
    return list(SIGNATURES.keys())


def list_functions(dll_name: str) -> List[str]:
    """列出指定 DLL 的所有函数

    Args:
        dll_name: DLL 名称

    Returns:
        函数名列表
    """
    dll_sigs = SIGNATURES.get(dll_name, {})
    return list(dll_sigs.keys())
