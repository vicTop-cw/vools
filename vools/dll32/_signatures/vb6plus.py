"""
VB6Plus.dll 函数签名

根据 E:\\vb\\vb6例子\\Module\\mVB6Plus.bas 中的声明定义。
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


# VB6Plus.dll 函数签名注册表
# 类型说明:
#   'str' - ByVal 字符串 (c_char_p)
#   'ref_str' - ByRef 字符串 (指针的指针, byref(c_char_p))
#   'int' - 整数 (c_int)
#   'long' - 长整数 (c_long)
#   'ref_long' - ByRef 长整数 (byref(c_long))
#   'double' - 双精度浮点数 (c_double)
#   'bool' - 布尔值 (c_bool)
VB6PLUS_SIGNATURES: Dict[str, FuncSignature] = {
    # ===== 字符串操作 =====
    'StrCompare': {
        'argtypes': ['ref_str', 'ref_str'],
        'restype': 'double',
        'doc': '字符串相似度比较',
    },
    'Permutation': {
        'argtypes': ['ref_str', 'ref_str', 'ref_long'],
        'restype': 'str',
        'doc': '字符串全排列',
    },
    'ExplodeData': {
        'argtypes': ['ref_str', 'ref_str', 'ref_str'],
        'restype': 'str',
        'doc': '字符串分割提取',
    },
    'Combination': {
        'argtypes': ['ref_str', 'ref_str', 'ref_long'],
        'restype': 'str',
        'doc': '字符串组合',
    },
    'StrToHex_GB': {
        'argtypes': ['ref_str', 'int'],
        'restype': 'str',
        'doc': '字符串转十六进制 (GB 编码)',
    },
    'StrToHex_UTF8': {
        'argtypes': ['ref_str', 'int'],
        'restype': 'str',
        'doc': '字符串转十六进制 (UTF-8 编码)',
    },
    'HexToStr_GB': {
        'argtypes': ['ref_str'],
        'restype': 'str',
        'doc': '十六进制转字符串 (GB 编码)',
    },
    'HexToStr_UTF8': {
        'argtypes': ['ref_str'],
        'restype': 'str',
        'doc': '十六进制转字符串 (UTF-8 编码)',
    },
    'Regex_Replace': {
        'argtypes': ['ref_str', 'ref_str', 'ref_str'],
        'restype': 'str',
        'doc': '正则表达式替换',
    },

    # ===== INI 文件操作 =====
    'ReadINIValue': {
        'argtypes': ['ref_str', 'ref_str', 'ref_str', 'ref_str'],
        'restype': 'str',
        'doc': '读取 INI 文件值',
    },
    'WriteINIValue': {
        'argtypes': ['ref_str', 'ref_str', 'ref_str', 'ref_str'],
        'restype': 'bool',
        'doc': '写入 INI 文件值',
    },

    # ===== HTML 编解码 =====
    'NoHTML': {
        'argtypes': ['str', 'int'],
        'restype': 'str',
        'doc': '去除 HTML 标签',
    },
    'HTMLEncode': {
        'argtypes': ['str'],
        'restype': 'str',
        'doc': 'HTML 编码',
    },
    'HTMLDecode': {
        'argtypes': ['str'],
        'restype': 'str',
        'doc': 'HTML 解码',
    },

    # ===== URL 编解码 =====
    'UrlEncode_GB': {
        'argtypes': ['str'],
        'restype': 'str',
        'doc': 'URL 编码 (GB 编码)',
    },
    'UrlDecode_GB': {
        'argtypes': ['str'],
        'restype': 'str',
        'doc': 'URL 解码 (GB 编码)',
    },
    'UrlEncode_UTF8': {
        'argtypes': ['str'],
        'restype': 'str',
        'doc': 'URL 编码 (UTF-8 编码)',
    },
    'UrlDecode_UTF8': {
        'argtypes': ['str'],
        'restype': 'str',
        'doc': 'URL 解码 (UTF-8 编码)',
    },

    # ===== Unicode 编解码 =====
    'UnicodeEncode': {
        'argtypes': ['str'],
        'restype': 'str',
        'doc': 'Unicode 编码 (\\uXXXX 格式)',
    },
    'UnicodeDecode': {
        'argtypes': ['str'],
        'restype': 'str',
        'doc': 'Unicode 解码',
    },

    # ===== Base64 编解码 =====
    'Base64Encode_GB': {
        'argtypes': ['str'],
        'restype': 'str',
        'doc': 'Base64 编码 (GB 编码)',
    },
    'Base64Decode_GB': {
        'argtypes': ['str'],
        'restype': 'str',
        'doc': 'Base64 解码 (GB 编码)',
    },
    'Base64Encode_UTF8': {
        'argtypes': ['str'],
        'restype': 'str',
        'doc': 'Base64 编码 (UTF-8 编码)',
    },
    'Base64Decode_UTF8': {
        'argtypes': ['str'],
        'restype': 'str',
        'doc': 'Base64 解码 (UTF-8 编码)',
    },

    # ===== MD5 =====
    'MD516_GB': {
        'argtypes': ['str'],
        'restype': 'str',
        'doc': 'MD5 16位 (GB 编码)',
    },
    'MD532_GB': {
        'argtypes': ['str'],
        'restype': 'str',
        'doc': 'MD5 32位 (GB 编码)',
    },
    'MD516_UTF8': {
        'argtypes': ['str'],
        'restype': 'str',
        'doc': 'MD5 16位 (UTF-8 编码)',
    },
    'MD532_UTF8': {
        'argtypes': ['str'],
        'restype': 'str',
        'doc': 'MD5 32位 (UTF-8 编码)',
    },

    # ===== AES 加密 =====
    'AESEncrypt_GB': {
        'argtypes': ['str', 'str', 'str', 'int', 'int', 'int'],
        'restype': 'str',
        'doc': 'AES 加密 (GB 编码)',
    },
    'AESDecrypt_GB': {
        'argtypes': ['str', 'str', 'str', 'int', 'int', 'int'],
        'restype': 'str',
        'doc': 'AES 解密 (GB 编码)',
    },
    'AESEncrypt_UTF8': {
        'argtypes': ['str', 'str', 'str', 'int', 'int', 'int'],
        'restype': 'str',
        'doc': 'AES 加密 (UTF-8 编码)',
    },
    'AESDecrypt_UTF8': {
        'argtypes': ['str', 'str', 'str', 'int', 'int', 'int'],
        'restype': 'str',
        'doc': 'AES 解密 (UTF-8 编码)',
    },
    'AESEncryptTxtFile_GB': {
        'argtypes': ['str', 'str', 'str', 'str', 'int'],
        'restype': 'str',
        'doc': 'AES 加密文本文件 (GB 编码)',
    },
    'AESDecryptTxtFile_GB': {
        'argtypes': ['str', 'str', 'str', 'str', 'int'],
        'restype': 'str',
        'doc': 'AES 解密文本文件 (GB 编码)',
    },

    # ===== HTTP 请求 =====
    'XMLHTTP_Get': {
        'argtypes': ['ref_str', 'ref_str', 'ref_str', 'int', 'int'],
        'restype': 'str',
        'doc': 'XMLHTTP GET 请求',
    },
    'XMLHTTP_Post': {
        'argtypes': ['ref_str', 'ref_str', 'ref_str', 'ref_str', 'int', 'int'],
        'restype': 'str',
        'doc': 'XMLHTTP POST 请求',
    },

    # ===== Windows 工具 =====
    'Win_CopyFileToClipBoard': {
        'argtypes': ['str'],
        'restype': 'long',
        'doc': '复制文件到剪贴板',
    },
    'RunVBScript': {
        'argtypes': ['ref_str', 'ref_str'],
        'restype': 'long',
        'doc': '执行 VBScript',
    },

    # ===== 对话框 =====
    'ShowOpenFile': {
        'argtypes': ['long', 'ref_str', 'ref_str', 'ref_str', 'ref_str', 'int'],
        'restype': 'str',
        'doc': '显示打开文件对话框',
    },
    'ShowSaveFile': {
        'argtypes': ['long', 'ref_str', 'ref_str', 'ref_str', 'ref_str'],
        'restype': 'str',
        'doc': '显示保存文件对话框',
    },
    'ShowBrowserFolder': {
        'argtypes': ['long', 'ref_str', 'ref_str'],
        'restype': 'str',
        'doc': '显示浏览文件夹对话框',
    },

    # ===== 二维码 =====
    'MakeQRCode': {
        'argtypes': ['ref_str', 'ref_str', 'int', 'int', 'int'],
        'restype': 'str',
        'doc': '生成二维码图片',
    },
    'ScanQRImage': {
        'argtypes': ['ref_str', 'bool', 'ref_str', 'int'],
        'restype': 'str',
        'doc': '扫描二维码图片',
    },

    # ===== 图片转换 =====
    'ImageToJPG': {
        'argtypes': ['ref_str', 'ref_str', 'int'],
        'restype': 'str',
        'doc': '图片转 JPG',
    },
    'ImageToBMP': {
        'argtypes': ['ref_str', 'ref_str'],
        'restype': 'str',
        'doc': '图片转 BMP',
    },

    # ===== SQLite =====
    'SQLite_Open': {
        'argtypes': ['ref_long', 'ref_str', 'ref_str'],
        'restype': 'long',
        'doc': '打开 SQLite 数据库',
    },
    'SQLite_Close': {
        'argtypes': ['ref_long'],
        'restype': 'long',
        'doc': '关闭 SQLite 数据库',
    },
    'SQLite_Execute': {
        'argtypes': ['ref_long', 'ref_str', 'ref_str'],
        'restype': 'long',
        'doc': '执行 SQL 语句',
    },
}

# 兼容性别名
__all__ = ['VB6PLUS_SIGNATURES']
