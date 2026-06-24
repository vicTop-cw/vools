"""
vools.bridge.scala.types - Python ↔ Scala/JVM 类型映射系统

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
    tuple: 'java.util.List',  # Scala Tuple 会转换为 List
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


class ScalaTypeMapper:
    """
    Scala/JVM 类型映射器

    提供 Python 类型与 JVM 类型之间的转换和推断功能，
    支持根据参数值自动推断类型，以及自动转换参数格式。

    用法：
        jvm_type = ScalaTypeMapper.get_jvm_type(int)
        py_type = ScalaTypeMapper.get_py_type('java.lang.String')
        arg_converter = ScalaTypeMapper.get_converter(int)
        result_converter = ScalaTypeMapper.get_converter('java.lang.Integer', to_py=True)

    类型转换规则：
        Python -> JVM:
            int -> java.lang.Integer
            float -> java.lang.Double
            bool -> java.lang.Boolean
            str -> java.lang.String
            bytes -> byte[]
            list -> java.util.List
            dict -> java.util.Map

        JVM -> Python:
            java.lang.Integer -> int
            java.lang.Double -> float
            java.lang.Boolean -> bool
            java.lang.String -> str
            byte[] -> bytes
            java.util.List -> list
            java.util.Map -> dict
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
    def get_jvm_class(jvm_type_name: str, gateway=None):
        """
        获取 JVM 类型名对应的 Py4J JavaClass 对象

        参数：
            jvm_type_name: JVM 类型名
            gateway: Py4J JavaGateway 实例

        返回：
            Py4J JavaClass 对象
        """
        if gateway is None:
            from .loader import get_scala_gateway
            gateway = get_scala_gateway()

        if not gateway.is_connected:
            raise RuntimeError("Gateway not connected")

        return gateway.entry_point.__getattr__(jvm_type_name)

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
            # Py4J 的 JavaList -> Python list
            if hasattr(value, '_get_object_id'):
                # 这是一个 Py4J JavaObject
                try:
                    type_name = value.getClass().getName()
                    if type_name.startswith('java.util.List') or \
                       type_name.startswith('scala.collection'):
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
            jvm_type = ScalaTypeMapper.get_jvm_type_name(py_type)
            result.append(jvm_type)
        return result

    @staticmethod
    def describe_type(value: Any) -> str:
        """
        描述值的类型信息（Python 和 JVM）

        参数：
            value: 任意值

        返回：
            类型描述字符串
        """
        py_type = type(value)
        desc = f"Python: {py_type.__name__}"

        try:
            jvm_type_name = value.getClass().getName()
            desc += f" | JVM: {jvm_type_name}"
        except Exception:
            pass

        return desc


# Python -> JVM 转换器
def _convert_int_to_jvm(value: int):
    """int -> java.lang.Integer"""
    from py4j.java_gateway import JavaObject
    if isinstance(value, JavaObject):
        return value
    # Py4J 会自动转换基本类型
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
        from .loader import get_scala_gateway
        gateway = get_scala_gateway()

    if not gateway.is_connected:
        return value

    # 创建 Java ArrayList
    ArrayList = gateway.entry_point.java.util.ArrayList
    java_list = ArrayList()
    for item in value:
        java_list.add(item)
    return java_list


def _convert_dict_to_jvm(value: dict, gateway=None):
    """dict -> java.util.Map"""
    if gateway is None:
        from .loader import get_scala_gateway
        gateway = get_scala_gateway()

    if not gateway.is_connected:
        return value

    # 创建 Java HashMap
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
    tuple: _convert_list_to_jvm,  # Tuple 作为 List 处理
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
    return ScalaTypeMapper.get_jvm_type_name(py_type)


def get_py_type(jvm_type_name: str) -> Optional[Type]:
    """获取 JVM 类型名对应的 Python 类型"""
    return ScalaTypeMapper.get_py_type(jvm_type_name)


def convert_to_jvm(value: Any, py_type: Type = None) -> Any:
    """将 Python 值转换为 JVM 值"""
    return ScalaTypeMapper.convert_to_jvm(value, py_type)


def convert_to_py(value: Any, jvm_type_name: str = None) -> Any:
    """将 JVM 值转换为 Python 值"""
    return ScalaTypeMapper.convert_to_py(value, jvm_type_name)


def infer_jvm_types(args: List[Any]) -> List[str]:
    """根据参数值推断 JVM 类型名列表"""
    return ScalaTypeMapper.infer_jvm_types(args)
