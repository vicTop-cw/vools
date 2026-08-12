"""
RC6 COM 组件包装

RC6 是 vbRichClient5 的一部分，是一个功能丰富的 COM 组件库，
提供了文件操作、编码转换、正则表达式、加密、HTTP 等功能。

ProgID: RC6.cRC6

用法:
    from vools.dll32._lib.com import RC6

    # 创建 RC6 实例
    rc6 = RC6.create()

    # 使用各种子对象
    encoding = rc6.Encoding
    crypto = rc6.Crypto
    http = rc6.Http
"""
from typing import Optional
from ._base import COMObject


class RC6(COMObject):
    """RC6 COM 组件包装类

    RC6 是 vbRichClient5 的核心组件，提供了：
    - cDataPath: 路径处理
    - cFile: 文件操作
    - cDir: 目录操作
    - cEncoding: 编码转换
    - cCrypto: 加密解密
    - cHash: 哈希
    - cHttp: HTTP 请求
    - cRegExp: 正则表达式
    - cRegistry: 注册表
    - cTimer: 计时器
    - cCollectionEx: 集合扩展
    - 等等
    """

    # RC6 的 ProgID
    PROG_ID = 'RC6.cRC6'

    def __init__(self, obj=None):
        super().__init__(obj)
        self._sub_objects = {}

    @classmethod
    def create(cls) -> 'RC6':
        """创建 RC6 实例

        Returns:
            RC6 实例
        """
        return cls.create(cls.PROG_ID)

    @classmethod
    def get_active(cls) -> Optional['RC6']:
        """获取已运行的 RC6 实例

        Returns:
            RC6 实例，如果未运行返回 None
        """
        return cls.get_active(cls.PROG_ID)

    @property
    def Encoding(self):
        """编码转换对象 (cEncoding)

        提供 Base64、URL、HTML、Unicode 等编码转换。
        """
        if 'Encoding' not in self._sub_objects:
            self._sub_objects['Encoding'] = EncodingWrapper(self._obj.Encoding)
        return self._sub_objects['Encoding']

    @property
    def Crypto(self):
        """加密对象 (cCrypto)

        提供 AES、DES、RC4 等加密功能。
        """
        if 'Crypto' not in self._sub_objects:
            self._sub_objects['Crypto'] = CryptoWrapper(self._obj.Crypto)
        return self._sub_objects['Crypto']

    @property
    def Http(self):
        """HTTP 请求对象 (cHttp)

        提供 HTTP GET/POST 请求功能。
        """
        if 'Http' not in self._sub_objects:
            self._sub_objects['Http'] = HttpWrapper(self._obj.Http)
        return self._sub_objects['Http']

    @property
    def File(self):
        """文件操作对象 (cFile)"""
        if 'File' not in self._sub_objects:
            self._sub_objects['File'] = COMObject(self._obj.File)
        return self._sub_objects['File']

    @property
    def Dir(self):
        """目录操作对象 (cDir)"""
        if 'Dir' not in self._sub_objects:
            self._sub_objects['Dir'] = COMObject(self._obj.Dir)
        return self._sub_objects['Dir']

    @property
    def RegExp(self):
        """正则表达式对象 (cRegExp)"""
        if 'RegExp' not in self._sub_objects:
            self._sub_objects['RegExp'] = COMObject(self._obj.RegExp)
        return self._sub_objects['RegExp']

    @property
    def Registry(self):
        """注册表操作对象 (cRegistry)"""
        if 'Registry' not in self._sub_objects:
            self._sub_objects['Registry'] = COMObject(self._obj.Registry)
        return self._sub_objects['Registry']

    @property
    def DataPath(self):
        """路径处理对象 (cDataPath)"""
        if 'DataPath' not in self._sub_objects:
            self._sub_objects['DataPath'] = COMObject(self._obj.DataPath)
        return self._sub_objects['DataPath']

    @property
    def CollectionEx(self):
        """集合扩展对象 (cCollectionEx)"""
        if 'CollectionEx' not in self._sub_objects:
            self._sub_objects['CollectionEx'] = COMObject(self._obj.CollectionEx)
        return self._sub_objects['CollectionEx']


class EncodingWrapper(COMObject):
    """RC6 Encoding 对象包装"""

    def Base64Encode(self, text: str) -> str:
        """Base64 编码"""
        return self._obj.Base64Encode(text)

    def Base64Decode(self, text: str) -> str:
        """Base64 解码"""
        return self._obj.Base64Decode(text)

    def URLEncode(self, text: str) -> str:
        """URL 编码"""
        return self._obj.URLEncode(text)

    def URLDecode(self, text: str) -> str:
        """URL 解码"""
        return self._obj.URLDecode(text)

    def HTMLEncode(self, text: str) -> str:
        """HTML 编码"""
        return self._obj.HTMLEncode(text)

    def HTMLDecode(self, text: str) -> str:
        """HTML 解码"""
        return self._obj.HTMLDecode(text)


class CryptoWrapper(COMObject):
    """RC6 Crypto 对象包装"""

    def AESEncrypt(self, text: str, password: str = '',
                   mode: int = 0, padding: int = 0) -> str:
        """AES 加密

        Args:
            text: 待加密文本
            password: 密码
            mode: 模式 (0-ECB, 1-CBC)
            padding: 填充方式

        Returns:
            加密后的 Base64 字符串
        """
        return self._obj.AESEncrypt(text, password, mode, padding)

    def AESDecrypt(self, encrypted: str, password: str = '',
                   mode: int = 0, padding: int = 0) -> str:
        """AES 解密

        Args:
            encrypted: 加密文本 (Base64)
            password: 密码
            mode: 模式 (0-ECB, 1-CBC)
            padding: 填充方式

        Returns:
            解密后的原文
        """
        return self._obj.AESDecrypt(encrypted, password, mode, padding)


class HttpWrapper(COMObject):
    """RC6 Http 对象包装"""

    def Get(self, url: str, timeout: int = 30) -> str:
        """HTTP GET 请求

        Args:
            url: 请求 URL
            timeout: 超时时间（秒）

        Returns:
            响应内容
        """
        return self._obj.Get(url, timeout)

    def Post(self, url: str, data: str = '', timeout: int = 30) -> str:
        """HTTP POST 请求

        Args:
            url: 请求 URL
            data: POST 数据
            timeout: 超时时间（秒）

        Returns:
            响应内容
        """
        return self._obj.Post(url, data, timeout)
