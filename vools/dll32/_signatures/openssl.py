"""
VB6OpenSSL.dll 函数签名

根据 E:\\vb\\vb6例子\\Module\\mVB6OpenSSL.bas 中的声明定义。
"""
from typing import Dict
try:
    from typing import TypedDict
    class FuncSignature(TypedDict, total=False):
        """函数签名类型"""
        argtypes: list  # 参数类型列表
        restype: str    # 返回值类型
        doc: str        # 文档说明
except ImportError:
    # Python 3.6 不支持 TypedDict，用普通字典代替
    FuncSignature = dict


# VB6OpenSSL.dll 函数签名注册表
VB6OPENSSL_SIGNATURES: Dict[str, FuncSignature] = {
    'OpenSSL_Get': {
        'argtypes': ['ref_str', 'ref_str', 'ref_str', 'double', 'int', 'long'],
        'restype': 'str',
        'doc': 'OpenSSL GET 请求',
    },
    'OpenSSL_Post': {
        'argtypes': ['ref_str', 'ref_str', 'ref_str', 'ref_str', 'double', 'int', 'long'],
        'restype': 'str',
        'doc': 'OpenSSL POST 请求',
    },
}

# 兼容性别名
OPENSSL_SIGNATURES = VB6OPENSSL_SIGNATURES
__all__ = ['OPENSSL_SIGNATURES']
