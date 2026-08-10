"""
vools.bridge.java.types - Python ↔ Java/JVM 类型映射系统

提供 Python 类型与 JVM 类型之间的自动转换和推断能力，
简化 Py4J 跨语言函数调用时的类型声明工作。
"""

from typing import Type, Any, Dict, List, Optional, Callable
import ctypes


# Python 类型到 JVM 类型名的映射
PY_TO_JVM_TYPE_NAME: Dict[Type, str] = {
    int: 'java.lang.Integer',
    float: 'java.lang.Double',
    bool: 'java.lang.Boolean',
    str: 'java.lang.String',
    bytes: 'byte[]',
    bytearray: 'byte[]',
    list: 'java.util.List',
    dict: 'java.util.Map',
    set: 'java.util.Set',
    tuple: 'java.util.List',  # Tuple 会转换为 List
}

# JVM 类型名到 Python 类型的映射
JVM_TO_PY_TYPE_NAME: Dict[str, Type] = {
    'java.lang.Integer': int,
    'java.lang.Long': int,
    'java.lang.Short': int,
    'java.lang.Byte': int,
    'java.lang.Double': float,
    'java.lang.Float': float,
    'java.lang.Boolean': bool,
    'java.lang.String': str,
    'java.lang.Object': object,
    'byte[]': bytes,
    'char[]': str,
    'java.util.List': list,
    'java.util.ArrayList': list,
    'java.util.Set': set,
    'java.util.HashSet': set,
    'java.util.Map': dict,
    'java.util.HashMap': dict,
}


class JavaTypeMapper:
    """
    Java/JVM 类型映射器

    提供 Python 类型与 JVM 类型之间的转换和推断功能，
    支持根据参数值自动推断类型，以及自动转换参数格式。
    """

    @staticmethod
    def get_jvm_type_name(py_type: Type) -> str:
        """
        获取 Python 类型对应的 JVM 类型名

        参数：
            py_type: Python 类型

        返回：
            JVM 类型名字符串，如 'java.lang.Integer'
            如果未注册则返回 'java.lang.Object'
        """
        if py_type is None or py_type is type(None):
            return 'void'

        return PY_TO_JVM_TYPE_NAME.get(py_type, 'java.lang.Object')

    @staticmethod
    def get_py_type(jvm_type_name: str) -> Optional[Type]:
        """
        获取 JVM 类型名对应的 Python 类型

        参数：
            jvm_type_name: JVM 类型名，如 'java.lang.String'

        返回：
            Python 类型，如果未识别则返回 None
        """
        return JVM_TO_PY_TYPE_NAME.get(jvm_type_name)

    @staticmethod
    def get_converter(py_type: Type, to_jvm: bool = True) -> Optional[Callable]:
        """
        获取类型转换器

        参数：
            py_type: Python 类型
            to_jvm: True 转换为 JVM 类型，False 转换为 Python 类型

        返回：
            转换函数，如果不需要转换则返回 None
        """
        if to_jvm:
            return _JVM_CONVERTERS.get(py_type)
        else:
            return _PY_CONVERTERS.get(py_type)

    @staticmethod
    def convert_to_jvm(value: Any, py_type: Type = None) -> Any:
        """
        将 Python 值转换为 JVM 值

        参数：
            value: Python 值
            py_type: Python 类型（可选，用于确定转换方式）

        返回：
            转换后的 JVM 值
        """
        if value is None:
            return None

        if py_type is None:
            py_type = type(value)

        converter = _JVM_CONVERTERS.get(py_type)
        if converter:
            return converter(value)
        return value

    @staticmethod
    def convert_to_py(value: Any, jvm_type_name: str = None) -> Any:
        """
        将 JVM 值转换为 Python 值

        参数：
            value: JVM 值（可能是 Py4J JavaObject）
            jvm_type_name: JVM 类型名（可选，用于确定转换方式）

        返回：
            转换后的 Python 值
        """
        if value is None:
            return None

        # 如果是 Py4J JavaObject，尝试获取其类型
        if jvm_type_name is None:
            try:
                jvm_type_name = value.getClass().getName()
            except Exception:
                pass

        converter = _PY_CONVERTERS.get(jvm_type_name)
        if converter:
            return converter(value)

        # 尝试自动转换常见的 Py4J 包装类型
        try:
            if hasattr(value, '_get_object_id'):
                try:
                    type_name = value.getClass().getName()
                    if type_name.startswith('java.util.List'):
                        return list(value)
                    elif type_name.startswith('java.util.Map'):
                        return dict(value)
                except Exception:
                    pass
        except Exception:
            pass

        return value

    @staticmethod
    def infer_jvm_types(args: List[Any]) -> List[str]:
        """
        根据参数值推断 JVM 类型名列表

        参数：
            args: 参数值列表

        返回：
            JVM 类型名列表
        """
        result = []
        for arg in args:
            py_type = type(arg)
            jvm_type = JavaTypeMapper.get_jvm_type_name(py_type)
            result.append(jvm_type)
        return result


# Python -> JVM 转换器
def _convert_int_to_jvm(value: int):
    """int -> java.lang.Integer"""
    from py4j.java_gateway import JavaObject
    if isinstance(value, JavaObject):
        return value
    return value


def _convert_float_to_jvm(value: float):
    """float -> java.lang.Double"""
    return value


def _convert_bool_to_jvm(value: bool):
    """bool -> java.lang.Boolean"""
    return value


def _convert_str_to_jvm(value: str):
    """str -> java.lang.String"""
    return value


def _convert_bytes_to_jvm(value: bytes):
    """bytes -> byte[]"""
    return value


def _convert_list_to_jvm(value: list, gateway=None):
    """list -> java.util.List"""
    if gateway is None:
        from .loader import get_java_gateway
        gateway = get_java_gateway()

    if not gateway.is_connected:
        return value

    ArrayList = gateway.entry_point.java.util.ArrayList
    java_list = ArrayList()
    for item in value:
        java_list.add(item)
    return java_list


def _convert_dict_to_jvm(value: dict, gateway=None):
    """dict -> java.util.Map"""
    if gateway is None:
        from .loader import get_java_gateway
        gateway = get_java_gateway()

    if not gateway.is_connected:
        return value

    HashMap = gateway.entry_point.java.util.HashMap
    java_map = HashMap()
    for k, v in value.items():
        java_map.put(k, v)
    return java_map


_JVM_CONVERTERS: Dict[Type, Callable] = {
    int: _convert_int_to_jvm,
    float: _convert_float_to_jvm,
    bool: _convert_bool_to_jvm,
    str: _convert_str_to_jvm,
    bytes: _convert_bytes_to_jvm,
    list: _convert_list_to_jvm,
    dict: _convert_dict_to_jvm,
    tuple: _convert_list_to_jvm,
}


# JVM -> Python 转换器
def _convert_java_integer_to_py(value):
    """java.lang.Integer -> int"""
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return value


def _convert_java_double_to_py(value):
    """java.lang.Double -> float"""
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return value


def _convert_java_boolean_to_py(value):
    """java.lang.Boolean -> bool"""
    if value is None:
        return None
    try:
        return bool(value)
    except Exception:
        return value


def _convert_java_string_to_py(value):
    """java.lang.String -> str"""
    if value is None:
        return None
    try:
        return str(value)
    except Exception:
        return value


def _convert_byte_array_to_py(value):
    """byte[] -> bytes"""
    if value is None:
        return None
    try:
        return bytes(value)
    except Exception:
        return value


def _convert_java_list_to_py(value):
    """java.util.List -> list"""
    if value is None:
        return None
    try:
        return list(value)
    except Exception:
        return value


def _convert_java_map_to_py(value):
    """java.util.Map -> dict"""
    if value is None:
        return None
    try:
        return dict(value)
    except Exception:
        return value


_PY_CONVERTERS: Dict[str, Callable] = {
    'java.lang.Integer': _convert_java_integer_to_py,
    'java.lang.Long': _convert_java_integer_to_py,
    'java.lang.Double': _convert_java_double_to_py,
    'java.lang.Float': _convert_java_double_to_py,
    'java.lang.Boolean': _convert_java_boolean_to_py,
    'java.lang.String': _convert_java_string_to_py,
    'byte[]': _convert_byte_array_to_py,
    'char[]': _convert_java_string_to_py,
    'java.util.List': _convert_java_list_to_py,
    'java.util.ArrayList': _convert_java_list_to_py,
    'java.util.Set': _convert_java_list_to_py,
    'java.util.Map': _convert_java_map_to_py,
    'java.util.HashMap': _convert_java_map_to_py,
}


# 便捷函数
def get_jvm_type(py_type: Type) -> str:
    """获取 Python 类型对应的 JVM 类型名"""
    return JavaTypeMapper.get_jvm_type_name(py_type)


def get_py_type(jvm_type_name: str) -> Optional[Type]:
    """获取 JVM 类型名对应的 Python 类型"""
    return JavaTypeMapper.get_py_type(jvm_type_name)


def convert_to_jvm(value: Any, py_type: Type = None) -> Any:
    """将 Python 值转换为 JVM 值"""
    return JavaTypeMapper.convert_to_jvm(value, py_type)


def convert_to_py(value: Any, jvm_type_name: str = None) -> Any:
    """将 JVM 值转换为 Python 值"""
    return JavaTypeMapper.convert_to_py(value, jvm_type_name)


def infer_jvm_types(args: List[Any]) -> List[str]:
    """根据参数值推断 JVM 类型名列表"""
    return JavaTypeMapper.infer_jvm_types(args)
