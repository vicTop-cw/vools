"""
vools.dll32 - 32位 DLL 专用桥接包

提供通过嵌入式 Python 3.6 32位进程调用 32 位 DLL 的功能。

主要功能:
    1. @dll32 装饰器 - 通过 ctypes 调用标准 DLL
    2. COM 支持 - 通过 win32com 调用 COM 组件 (包括 RC6)
    3. .NET 支持 - 通过 pythonnet 调用 .NET 程序集
    4. 函数签名注册表 - 统一管理 DLL 函数签名

用法:
    # 1. 使用 dll32 装饰器调用标准 DLL (VB6Plus.dll, VB6OpenSSL.dll, VB6MQTT.dll)
    from vools.dll32 import dll32

    @dll32('VB6Plus.dll::Base64Encode_UTF8')
    def base64_encode(input_str: str) -> str:
        pass

    result = base64_encode('Hello')

    # 2. 使用 VB6Plus 包装类
    from vools.dll32 import vb6plus

    result = vb6plus.base64_encode_utf8('Hello')
    result = vb6plus.md5_32_utf8('test')

    # 3. 使用 RC6Plus (VBRichClient5) - 通过 COM
    from vools.dll32 import get_rc6

    rc6 = get_rc6()
    result = rc6.crypt.base64_encode('Hello')
    result = rc6.md5('test')
    result = rc6.fso.read_text('test.txt')

    # 4. 使用 .NET 程序集
    from vools.dll32._lib.clr import CLRAssembly

    CLRAssembly.load_assembly('System.Data')

支持的标准 DLL:
    - VB6Plus.dll: Base64, MD5, URL, HTML, AES, INI, SQLite 等
    - VB6OpenSSL.dll: HTTPS GET/POST 请求
    - VB6MQTT.dll: MQTT 客户端

支持的 COM 组件:
    - RC6 (VBRichClient5): 加密、文件、集合、网络、数据库等
"""

from .dll import dll32

# 导出包装模块
from .vb6plus import VB6Plus, vb6plus
from .openssl import OpenSSL, openssl
from .mqtt import MQTT, mqtt

# 导出 COM/CLR 相关
from ._lib import COMObject, create_com_object
from ._lib.com import RC6Plus, get_rc6, DirectCOM

# 导出签名注册表
from ._signatures import SIGNATURES, get_signature, list_dlls, list_functions

__all__ = [
    # 核心装饰器
    'dll32',
    # 包装类 (标准 DLL)
    'VB6Plus',
    'OpenSSL',
    'MQTT',
    # 全局实例 (标准 DLL)
    'vb6plus',
    'openssl',
    'mqtt',
    # COM/CLR
    'COMObject',
    'create_com_object',
    'RC6Plus',
    'get_rc6',
    'DirectCOM',
    # 签名注册表
    'SIGNATURES',
    'get_signature',
    'list_dlls',
    'list_functions',
]
