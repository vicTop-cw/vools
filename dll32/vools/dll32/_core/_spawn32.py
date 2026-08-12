"""
32 位 Python 进程管理器

负责调用 32 位 Python 来执行 DLL 函数。
"""
import os
import subprocess
import json
import time
import tempfile

# 获取 python32 路径
_PYTHON32_DIR = os.path.join(os.path.dirname(__file__), '..', '_python32')
_PYTHON32_EXE = os.path.join(_PYTHON32_DIR, 'python.exe')


class Python32Process:
    """32 位 Python 进程包装器"""

    def __init__(self):
        pass

    def start(self):
        """启动（不需要常驻进程）"""
        pass

    def call(self, method, params=None, timeout=30):
        """调用 32 位 Python 执行"""
        req_id = str(int(time.time() * 1000000))
        req_file = os.path.join(tempfile.gettempdir(), 'dll32_req_' + req_id + '.json')
        resp_file = os.path.join(tempfile.gettempdir(), 'dll32_resp_' + req_id + '.json')

        try:
            request = {'id': req_id, 'method': method, 'params': params or []}
            with open(req_file, 'w', encoding='utf-8') as f:
                json.dump(request, f)

            dll_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), '_dlls')
            dll_dir = dll_dir.replace('\\', '\\\\')

            py_code = self._build_py_code(dll_dir, req_file, resp_file)

            py_file = os.path.join(tempfile.gettempdir(), 'dll32_py_' + req_id + '.py')
            with open(py_file, 'w', encoding='utf-8') as f:
                f.write(py_code)

            env = os.environ.copy()
            env['PYTHONPATH'] = ''

            proc_result = subprocess.run(
                [_PYTHON32_EXE, py_file],
                capture_output=True,
                text=True,
                env=env,
                timeout=timeout,
            )

            if os.path.exists(resp_file):
                with open(resp_file, 'r', encoding='utf-8') as f:
                    response = json.load(f)

                if response.get('error'):
                    raise Exception(response['error'])
                return response.get('result')
            else:
                raise Exception('Response file not found. stderr: ' + proc_result.stderr)

        finally:
            for f in [req_file, resp_file, py_file]:
                if os.path.exists(f):
                    try:
                        os.remove(f)
                    except Exception:
                        pass

    def _build_py_code(self, dll_dir, req_file, resp_file):
        """构建 32 位 Python 执行代码"""
        return '''
import sys
import os
import json
import ctypes

_dll_dir = r"''' + dll_dir + '''"
os.environ['PATH'] = _dll_dir + os.pathsep + os.environ.get('PATH', '')

# 函数签名注册表
# 类型说明:
#   'str' - ByVal 字符串 (c_char_p)
#   'ref_str' - ByRef 字符串 (指针的指针, byref(c_char_p))
#   'int' - 整数 (c_int)
#   'long' - 长整数 (c_long)
#   'ref_long' - ByRef 长整数 (byref(c_long))
#   'double' - 双精度浮点数 (c_double)
#   'bool' - 布尔值 (c_bool)
FUNC_SIGNATURES = {
    'VB6Plus.dll': {
        # ===== 字符串操作 =====
        # 字符串相似度比较
        'StrCompare': {'argtypes': ['ref_str', 'ref_str'], 'restype': 'double'},
        # 全排列
        'Permutation': {'argtypes': ['ref_str', 'ref_str', 'ref_long'], 'restype': 'str'},
        # 字符串分割提取
        'ExplodeData': {'argtypes': ['ref_str', 'ref_str', 'ref_str'], 'restype': 'str'},
        # 组合
        'Combination': {'argtypes': ['ref_str', 'ref_str', 'ref_long'], 'restype': 'str'},
        # 字符串转十六进制
        'StrToHex_GB': {'argtypes': ['ref_str', 'int'], 'restype': 'str'},
        'StrToHex_UTF8': {'argtypes': ['ref_str', 'int'], 'restype': 'str'},
        # 十六进制转字符串
        'HexToStr_GB': {'argtypes': ['ref_str'], 'restype': 'str'},
        'HexToStr_UTF8': {'argtypes': ['ref_str'], 'restype': 'str'},
        # 正则替换
        'Regex_Replace': {'argtypes': ['ref_str', 'ref_str', 'ref_str'], 'restype': 'str'},
        
        # ===== INI 文件操作 =====
        'ReadINIValue': {'argtypes': ['ref_str', 'ref_str', 'ref_str', 'ref_str'], 'restype': 'str'},
        'WriteINIValue': {'argtypes': ['ref_str', 'ref_str', 'ref_str', 'ref_str'], 'restype': 'bool'},
        
        # ===== HTML 编解码 =====
        'NoHTML': {'argtypes': ['str', 'int'], 'restype': 'str'},
        'HTMLEncode': {'argtypes': ['str'], 'restype': 'str'},
        'HTMLDecode': {'argtypes': ['str'], 'restype': 'str'},
        
        # ===== URL 编解码 =====
        'UrlEncode_GB': {'argtypes': ['str'], 'restype': 'str'},
        'UrlDecode_GB': {'argtypes': ['str'], 'restype': 'str'},
        'UrlEncode_UTF8': {'argtypes': ['str'], 'restype': 'str'},
        'UrlDecode_UTF8': {'argtypes': ['str'], 'restype': 'str'},
        
        # ===== Unicode 编解码 =====
        'UnicodeEncode': {'argtypes': ['str'], 'restype': 'str'},
        'UnicodeDecode': {'argtypes': ['str'], 'restype': 'str'},
        
        # ===== Base64 编解码 =====
        'Base64Encode_GB': {'argtypes': ['str'], 'restype': 'str'},
        'Base64Decode_GB': {'argtypes': ['str'], 'restype': 'str'},
        'Base64Encode_UTF8': {'argtypes': ['str'], 'restype': 'str'},
        'Base64Decode_UTF8': {'argtypes': ['str'], 'restype': 'str'},
        
        # ===== MD5 =====
        'MD516_GB': {'argtypes': ['str'], 'restype': 'str'},
        'MD532_GB': {'argtypes': ['str'], 'restype': 'str'},
        'MD516_UTF8': {'argtypes': ['str'], 'restype': 'str'},
        'MD532_UTF8': {'argtypes': ['str'], 'restype': 'str'},
        
        # ===== AES 加密 =====
        'AESEncrypt_GB': {'argtypes': ['str', 'str', 'str', 'int', 'int', 'int'], 'restype': 'str'},
        'AESDecrypt_GB': {'argtypes': ['str', 'str', 'str', 'int', 'int', 'int'], 'restype': 'str'},
        'AESEncrypt_UTF8': {'argtypes': ['str', 'str', 'str', 'int', 'int', 'int'], 'restype': 'str'},
        'AESDecrypt_UTF8': {'argtypes': ['str', 'str', 'str', 'int', 'int', 'int'], 'restype': 'str'},
        'AESEncryptTxtFile_GB': {'argtypes': ['str', 'str', 'str', 'str', 'int'], 'restype': 'str'},
        'AESDecryptTxtFile_GB': {'argtypes': ['str', 'str', 'str', 'str', 'int'], 'restype': 'str'},
        
        # ===== HTTP 请求 =====
        'XMLHTTP_Get': {'argtypes': ['ref_str', 'ref_str', 'ref_str', 'int', 'int'], 'restype': 'str'},
        'XMLHTTP_Post': {'argtypes': ['ref_str', 'ref_str', 'ref_str', 'ref_str', 'int', 'int'], 'restype': 'str'},
        
        # ===== Windows 工具 =====
        'Win_CopyFileToClipBoard': {'argtypes': ['str'], 'restype': 'long'},
        'RunVBScript': {'argtypes': ['ref_str', 'ref_str'], 'restype': 'long'},
        
        # ===== 对话框 =====
        'ShowOpenFile': {'argtypes': ['long', 'ref_str', 'ref_str', 'ref_str', 'ref_str', 'int'], 'restype': 'str'},
        'ShowSaveFile': {'argtypes': ['long', 'ref_str', 'ref_str', 'ref_str', 'ref_str'], 'restype': 'str'},
        'ShowBrowserFolder': {'argtypes': ['long', 'ref_str', 'ref_str'], 'restype': 'str'},
        
        # ===== 二维码 =====
        'MakeQRCode': {'argtypes': ['ref_str', 'ref_str', 'int', 'int', 'int'], 'restype': 'str'},
        'ScanQRImage': {'argtypes': ['ref_str', 'bool', 'ref_str', 'int'], 'restype': 'str'},
        
        # ===== 图片转换 =====
        'ImageToJPG': {'argtypes': ['ref_str', 'ref_str', 'int'], 'restype': 'str'},
        'ImageToBMP': {'argtypes': ['ref_str', 'ref_str'], 'restype': 'str'},
        
        # ===== SQLite =====
        'SQLite_Open': {'argtypes': ['ref_long', 'ref_str', 'ref_str'], 'restype': 'long'},
        'SQLite_Close': {'argtypes': ['ref_long'], 'restype': 'long'},
        'SQLite_Execute': {'argtypes': ['ref_long', 'ref_str', 'ref_str'], 'restype': 'long'},
    },
    'VB6OpenSSL.dll': {
        'OpenSSL_Get': {'argtypes': ['ref_str', 'ref_str', 'ref_str', 'double', 'int', 'long'], 'restype': 'str'},
        'OpenSSL_Post': {'argtypes': ['ref_str', 'ref_str', 'ref_str', 'ref_str', 'double', 'int', 'long'], 'restype': 'str'},
    },
    'VB6MQTT.dll': {
        'MQTT_Open': {'argtypes': ['ref_long', 'ref_str', 'ref_str', 'ref_str', 'ref_str', 'ref_str', 'int', 'ref_str'], 'restype': 'long'},
        'MQTT_Close': {'argtypes': ['ref_long', 'ref_str'], 'restype': 'long'},
        'MQTT_GetNewMsg': {'argtypes': ['ref_long'], 'restype': 'str'},
        'MQTT_PubMessage': {'argtypes': ['ref_long', 'ref_str', 'int', 'long', 'ref_str'], 'restype': 'long'},
    },
}

def _to_ctypes_type(type_name):
    """类型名称转换为 ctypes 类型"""
    if type_name == 'str':
        return ctypes.c_char_p
    elif type_name == 'ref_str':
        return ctypes.c_void_p
    elif type_name == 'int':
        return ctypes.c_int
    elif type_name == 'long':
        return ctypes.c_long
    elif type_name == 'ref_long':
        return ctypes.c_void_p
    elif type_name == 'double':
        return ctypes.c_double
    elif type_name == 'bool':
        return ctypes.c_bool
    else:
        return ctypes.c_char_p

def _convert_arg(arg, type_name):
    """将 Python 参数转换为 ctypes 参数"""
    if type_name == 'str':
        if isinstance(arg, bytes):
            return arg
        return str(arg).encode('utf-8')
    elif type_name == 'ref_str':
        if isinstance(arg, bytes):
            return ctypes.byref(ctypes.c_char_p(arg))
        return ctypes.byref(ctypes.c_char_p(str(arg).encode('utf-8')))
    elif type_name == 'int':
        return int(arg)
    elif type_name == 'long':
        return int(arg)
    elif type_name == 'ref_long':
        return ctypes.byref(ctypes.c_long(int(arg)))
    elif type_name == 'double':
        return float(arg)
    elif type_name == 'bool':
        return bool(arg)
    else:
        return arg

def _convert_result(ret, restype):
    """将 ctypes 返回值转换为 Python 类型"""
    if restype == 'str':
        if ret is None:
            return ''
        if isinstance(ret, bytes):
            try:
                return ret.decode('utf-8')
            except UnicodeDecodeError:
                try:
                    return ret.decode('gbk')
                except UnicodeDecodeError:
                    return ret.decode('latin-1', errors='replace')
        return str(ret)
    elif restype == 'int':
        return int(ret) if ret is not None else 0
    elif restype == 'long':
        return int(ret) if ret is not None else 0
    elif restype == 'double':
        return float(ret) if ret is not None else 0.0
    elif restype == 'bool':
        return bool(ret)
    else:
        return ret

with open(r"''' + req_file + '''", 'r', encoding='utf-8') as f:
    req = json.load(f)

method = req['method']
params = req['params']

result = {'id': req['id'], 'result': None, 'error': None}

try:
    if method == 'ping':
        result['result'] = 'pong'

    elif method == 'list_dlls':
        dlls = [f for f in os.listdir(_dll_dir) if f.endswith('.dll')]
        result['result'] = dlls

    elif method == 'call_dll':
        dll_path, func_name, args = params

        if not os.path.isabs(dll_path):
            dll_full_path = os.path.join(_dll_dir, dll_path)
        else:
            dll_full_path = dll_path

        dll_name = os.path.basename(dll_path)

        dll = ctypes.WinDLL(dll_full_path)
        func = getattr(dll, func_name)

        sig = None
        if dll_name in FUNC_SIGNATURES and func_name in FUNC_SIGNATURES[dll_name]:
            sig = FUNC_SIGNATURES[dll_name][func_name]

        if sig:
            argtypes = [_to_ctypes_type(t) for t in sig['argtypes']]
            func.argtypes = argtypes
            func.restype = _to_ctypes_type(sig['restype'])

            c_args = []
            for i, arg in enumerate(args):
                type_name = sig['argtypes'][i] if i < len(sig['argtypes']) else 'str'
                c_args.append(_convert_arg(arg, type_name))

            ret = func(*c_args)
            result['result'] = _convert_result(ret, sig['restype'])
        else:
            func.argtypes = [ctypes.c_char_p] * len(args)
            func.restype = ctypes.c_char_p
            c_args = [str(a).encode('utf-8') if not isinstance(a, bytes) else a for a in args]
            ret = func(*c_args)
            if isinstance(ret, bytes):
                try:
                    result['result'] = ret.decode('utf-8')
                except UnicodeDecodeError:
                    result['result'] = ret.decode('latin-1', errors='replace')
            else:
                result['result'] = ret

    else:
        result['error'] = 'Unknown method: ' + method

except Exception as e:
    result['error'] = str(e)

with open(r"''' + resp_file + '''", 'w', encoding='utf-8') as f:
    json.dump(result, f)
'''

    def stop(self):
        """停止"""
        pass


# 全局实例
_process = None


def get_process():
    """获取全局实例"""
    global _process
    if _process is None:
        _process = Python32Process()
    return _process
