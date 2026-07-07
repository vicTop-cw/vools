"""
VBRichClient5 (RC6) COM 组件包装模块

VBRichClient5 是一个功能丰富的 VB6 扩展库，提供了：
- 加密解密 (Crypt)
- 文件系统 (FSO)
- 集合和字典
- 网络通信
- JSON 处理
- 定时器
- 等等...

用法:
    # 方式1: 使用全局实例
    from vools.dll32 import get_rc6

    rc6 = get_rc6()
    result = rc6.base64_encode('Hello')
    result = rc6.md5('test')

    # 方式2: 使用类
    from vools.dll32._lib.com.rc6plus import RC6Plus

    rc6 = RC6Plus()
    result = rc6.crypt.aes_encrypt('data', 'password')

    # 方式3: 使用 DirectCOM
    from vools.dll32._lib.com.directcom import DirectCOM

    dc = DirectCOM()
    constructor = dc.create("vbRichClient5.cConstructor")
"""
from typing import Optional, Any, Dict, Tuple

from .directcom import DirectCOM


def _unwrap_result(result: Any) -> Any:
    """解包 RC6 返回值

    RC6 的方法通常返回 (result, extra_info) 元组，
    我们只需要 result 部分。
    """
    if isinstance(result, tuple) and len(result) >= 1:
        return result[0]
    return result


class RC6Plus:
    """VBRichClient5 (RC6) 包装类

    提供便捷访问 RC6 常用功能的接口。

    常用子对象:
        - constructor: cConstructor 对象
        - crypt: 加密解密 (cCrypt)
        - fso: 文件系统 (cFSO)
        - collection: 集合 (cCollection)
        - timer: 定时器 (cTimer)
        - json: JSON 处理
        - tcp_client: TCP 客户端 (cTCPClient)
        - tcp_server: TCP 服务器 (cTCPServer)
        - memdb: 内存数据库 (cMemDB)
    """

    # VBRichClient5 ProgID
    PROG_ID = "vbRichClient5.cConstructor"

    def __init__(self, dll_dir: Optional[str] = None):
        """初始化 RC6 包装

        Args:
            dll_dir: DLL 目录路径
        """
        self._dll_dir = dll_dir
        self._constructor: Optional[Any] = None
        self._sub_objects: Dict[str, Any] = {}

        # 自动初始化
        self._init()

    def _init(self) -> None:
        """初始化 RC6 连接"""
        dc = DirectCOM(self._dll_dir)
        self._constructor = dc.create(self.PROG_ID)

    @property
    def constructor(self) -> Any:
        """获取 cConstructor 对象"""
        return self._constructor

    @property
    def crypt(self) -> Any:
        """加密解密对象 (cCrypt)

        提供:
            - base64_encode/decode: Base64 编解码
            - md5, sha1, sha256, sha384, sha512: 哈希
            - aes_encrypt/decrypt: AES 加解密
            - rc4_encrypt/decrypt: RC4 加解密
            - hex_encode/decode: 十六进制编解码
            - compress/decompress: 压缩解压
            - ...
        """
        if 'crypt' not in self._sub_objects:
            result = self._constructor.Crypt()
            self._sub_objects['crypt'] = _unwrap_result(result)
        return self._sub_objects['crypt']

    @property
    def fso(self) -> Any:
        """文件系统对象 (cFSO)

        提供:
            - read_text/write_text: 读写文本文件
            - read_bytes/write_bytes: 读写二进制文件
            - file_exists, dir_exists: 检查存在性
            - copy_file, move_file, delete_file: 文件操作
            - get_special_folder: 获取特殊文件夹
            - show_open_dialog, show_save_dialog: 对话框
            - ...
        """
        if 'fso' not in self._sub_objects:
            result = self._constructor.FSO()
            self._sub_objects['fso'] = _unwrap_result(result)
        return self._sub_objects['fso']

    @property
    def collection(self) -> Any:
        """集合对象 (cCollection)

        提供比 VB6 原生 Collection 更强大的集合功能。
        """
        if 'collection' not in self._sub_objects:
            result = self._constructor.Collection()
            self._sub_objects['collection'] = _unwrap_result(result)
        return self._sub_objects['collection']

    @property
    def sorted_dict(self) -> Any:
        """有序字典对象 (cSortedDictionary)"""
        if 'sorted_dict' not in self._sub_objects:
            result = self._constructor.SortedDictionary()
            self._sub_objects['sorted_dict'] = _unwrap_result(result)
        return self._sub_objects['sorted_dict']

    @property
    def json(self) -> Any:
        """JSON 处理对象"""
        if 'json' not in self._sub_objects:
            self._sub_objects['json'] = self._constructor.cJSON()
        return self._sub_objects['json']

    @property
    def stream(self) -> Any:
        """数据流对象 (cStream)"""
        if 'stream' not in self._sub_objects:
            result = self._constructor.Stream()
            self._sub_objects['stream'] = _unwrap_result(result)
        return self._sub_objects['stream']

    @property
    def timer(self) -> Any:
        """定时器对象 (cTimer)

        提供定时器功能，不需要窗体。
        """
        if 'timer' not in self._sub_objects:
            result = self._constructor.Timer()
            self._sub_objects['timer'] = _unwrap_result(result)
        return self._sub_objects['timer']

    @property
    def tcp_client(self) -> Any:
        """TCP 客户端对象 (cTCPClient)"""
        if 'tcp_client' not in self._sub_objects:
            result = self._constructor.TCPClient()
            self._sub_objects['tcp_client'] = _unwrap_result(result)
        return self._sub_objects['tcp_client']

    @property
    def tcp_server(self) -> Any:
        """TCP 服务器对象 (cTCPServer)"""
        if 'tcp_server' not in self._sub_objects:
            result = self._constructor.TCPServer()
            self._sub_objects['tcp_server'] = _unwrap_result(result)
        return self._sub_objects['tcp_server']

    @property
    def memdb(self) -> Any:
        """内存数据库对象 (cMemDB)

        基于 SQLite 的内存数据库。
        """
        if 'memdb' not in self._sub_objects:
            result = self._constructor.MemDB()
            self._sub_objects['memdb'] = _unwrap_result(result)
        return self._sub_objects['memdb']

    @property
    def simple_dom(self) -> Any:
        """简单 DOM 对象 (cSimpleDOM)

        用于解析 XML/HTML 文档。
        """
        if 'simple_dom' not in self._sub_objects:
            result = self._constructor.SimpleDOM()
            self._sub_objects['simple_dom'] = _unwrap_result(result)
        return self._sub_objects['simple_dom']

    @property
    def formula(self) -> Any:
        """公式计算对象 (cFormula)

        对包含计算公式的字符串求值。
        """
        if 'formula' not in self._sub_objects:
            result = self._constructor.Formula()
            self._sub_objects['formula'] = _unwrap_result(result)
        return self._sub_objects['formula']

    # ===== 便捷方法 =====

    def base64_encode(self, text: str) -> str:
        """Base64 编码

        Args:
            text: 待编码文本

        Returns:
            Base64 编码结果
        """
        result = self.crypt.Base64Enc(text)
        return _unwrap_result(result)

    def base64_decode(self, text: str) -> str:
        """Base64 解码

        Args:
            text: Base64 编码文本

        Returns:
            解码结果
        """
        result = self.crypt.Base64Dec(text)
        return _unwrap_result(result)

    def md5(self, text: str) -> str:
        """MD5 哈希

        Args:
            text: 待哈希文本

        Returns:
            32位 MD5 哈希值
        """
        result = self.crypt.MD5(text)
        return _unwrap_result(result)

    def sha256(self, text: str) -> str:
        """SHA256 哈希

        Args:
            text: 待哈希文本

        Returns:
            SHA256 哈希值
        """
        result = self.crypt.SHA256(text)
        return _unwrap_result(result)

    def aes_encrypt(self, data: str, password: str = '',
                    mode: int = 0, padding: int = 0) -> str:
        """AES 加密

        Args:
            data: 待加密数据
            password: 密码
            mode: 模式 (0-ECB, 1-CBC)
            padding: 填充方式

        Returns:
            加密后的 Base64 字符串
        """
        result = self.crypt.AESEncrypt(data, password, mode, padding)
        return _unwrap_result(result)

    def aes_decrypt(self, encrypted: str, password: str = '',
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
        result = self.crypt.AESDecrypt(encrypted, password, mode, padding)
        return _unwrap_result(result)

    def read_text(self, file_path: str, encoding: str = 'utf-8') -> str:
        """读取文本文件

        Args:
            file_path: 文件路径
            encoding: 编码 (utf-8, gbk, etc.)

        Returns:
            文件内容
        """
        result = self.fso.ReadTextContent(file_path, encoding)
        return _unwrap_result(result)

    def write_text(self, file_path: str, content: str, encoding: str = 'utf-8') -> None:
        """写入文本文件

        Args:
            file_path: 文件路径
            content: 文件内容
            encoding: 编码 (utf-8, gbk, etc.)
        """
        self.fso.SaveTextContent(content, file_path, encoding)

    def __repr__(self) -> str:
        return f"<RC6Plus>"


# 全局实例 (延迟初始化)
_rc6_plus: Optional[RC6Plus] = None


def get_rc6() -> RC6Plus:
    """获取全局 RC6Plus 实例

    Returns:
        RC6Plus 实例
    """
    global _rc6_plus
    if _rc6_plus is None:
        _rc6_plus = RC6Plus()
    return _rc6_plus
