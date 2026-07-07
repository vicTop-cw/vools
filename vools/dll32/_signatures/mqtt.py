"""
VB6MQTT.dll 函数签名

根据 E:\\vb\\vb6例子\\Module\\VB6MQTT.bas 中的声明定义。
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


# VB6MQTT.dll 函数签名注册表
# 注意：所有函数的第一个参数都是 ByRef MQTTClient As Long（输出句柄）
VB6MQTT_SIGNATURES: Dict[str, FuncSignature] = {
    'MQTT_Open': {
        'argtypes': ['ref_long', 'ref_str', 'ref_str', 'ref_str', 'ref_str', 'ref_str', 'int', 'ref_str'],
        'restype': 'long',
        'doc': '打开 MQTT 连接',
    },
    'MQTT_Close': {
        'argtypes': ['ref_long', 'ref_str'],
        'restype': 'long',
        'doc': '关闭 MQTT 连接',
    },
    'MQTT_GetNewMsg': {
        'argtypes': ['ref_long'],
        'restype': 'str',
        'doc': '获取新消息',
    },
    'MQTT_PubMessage': {
        'argtypes': ['ref_long', 'ref_str', 'int', 'long', 'ref_str'],
        'restype': 'long',
        'doc': '发布消息',
    },
}

# 兼容性别名
MQTT_SIGNATURES = VB6MQTT_SIGNATURES
__all__ = ['MQTT_SIGNATURES']
