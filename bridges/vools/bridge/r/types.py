"""
vools.bridge.r.types - Python ↔ R 类型映射系统

提供 Python 类型与 R 类型之间的自动转换和推断能力，
基于 JSON 作为中间序列化格式，简化跨语言函数调用时的类型声明工作。
"""

import json
from typing import Any, List, Tuple


PY_TO_R_TYPE = {
    int: 'integer',
    float: 'numeric',
    bool: 'logical',
    str: 'character',
    bytes: 'character',
    list: 'vector',
    dict: 'list',
    tuple: 'vector',
    type(None): 'NULL',
}


_TYPE_ALIASES = {
    'int': 'integer',
    'integer': 'integer',
    'float': 'numeric',
    'double': 'numeric',
    'numeric': 'numeric',
    'bool': 'logical',
    'boolean': 'logical',
    'logical': 'logical',
    'str': 'character',
    'string': 'character',
    'character': 'character',
    'bytes': 'character',
    'list': 'vector',
    'vector': 'vector',
    'dict': 'list',
    'list_r': 'list',
    'tuple': 'vector',
    'none': 'NULL',
    'null': 'NULL',
    'void': 'NULL',
}


class RTypeMapper:
    """
    R 类型映射器

    提供 Python 类型与 R 类型之间的转换和推断功能，
    支持根据参数值自动推断类型，以及 JSON 序列化/反序列化。

    用法：
        r_type = RTypeMapper.get_r_type(int)
        arg_types = RTypeMapper.infer_r_types([1, 2.0, "hello"])
        json_str = RTypeMapper.serialize_args([1, "hi"], ["integer", "character"])
        result = RTypeMapper.deserialize_result('42', int)
    """

    _py_to_r = dict(PY_TO_R_TYPE)

    @staticmethod
    def register_type(py_type, r_type):
        """
        注册自定义类型映射

        参数：
            py_type: Python 类型
            r_type: 对应的 R 类型字符串
        """
        RTypeMapper._py_to_r[py_type] = r_type

    @staticmethod
    def get_r_type(py_type):
        """
        获取 Python 类型对应的 R 类型字符串

        参数：
            py_type: Python 类型 / 类型注解（可为字符串形式）

        返回：
            R 类型字符串，未知则返回 'integer'
        """
        if py_type is None or py_type is type(None):
            return 'NULL'

        if py_type in RTypeMapper._py_to_r:
            return RTypeMapper._py_to_r[py_type]

        if isinstance(py_type, str):
            normalized = py_type.strip().lower()
            if normalized in _TYPE_ALIASES:
                return _TYPE_ALIASES[normalized]
            short = normalized.split('.')[-1]
            if short in _TYPE_ALIASES:
                return _TYPE_ALIASES[short]
            return 'integer'

        return 'integer'

    @staticmethod
    def infer_r_types(args):
        """
        根据参数值推断 R 类型列表

        遍历参数列表，根据每个参数的 Python 类型推断对应的 R 类型。
        对于未注册的类型，默认使用 'integer'。

        参数：
            args: 参数值列表

        返回：
            R 类型字符串列表
        """
        result = []
        for arg in args:
            if isinstance(arg, bool):
                result.append('logical')
            elif isinstance(arg, int):
                result.append('integer')
            elif isinstance(arg, float):
                result.append('numeric')
            elif isinstance(arg, str):
                result.append('character')
            elif isinstance(arg, bytes):
                result.append('character')
            elif isinstance(arg, list):
                if arg and all(isinstance(x, int) and not isinstance(x, bool) for x in arg):
                    result.append('integer')
                elif arg and all(isinstance(x, float) for x in arg):
                    result.append('numeric')
                elif arg and all(isinstance(x, str) for x in arg):
                    result.append('character')
                elif arg and all(isinstance(x, bool) for x in arg):
                    result.append('logical')
                else:
                    result.append('list')
            elif isinstance(arg, tuple):
                result.append('vector')
            elif isinstance(arg, dict):
                result.append('list')
            elif arg is None:
                result.append('NULL')
            else:
                result.append('integer')
        return result

    @staticmethod
    def serialize_args(args, r_types=None):
        """
        将 Python 参数序列化为 JSON 字符串（用于传给 R）

        参数：
            args: 参数值列表
            r_types: R 类型列表（可选，用于指导序列化）

        返回：
            JSON 字符串
        """
        serializable = []
        for i, arg in enumerate(args):
            if isinstance(arg, bytes):
                serializable.append(arg.decode('utf-8'))
            else:
                serializable.append(arg)

        payload = {
            'args': serializable,
        }
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def deserialize_result(result_json, ret_type=None):
        """
        将 R 返回的 JSON 反序列化为 Python 对象

        参数：
            result_json: JSON 字符串
            ret_type: Python 返回类型注解（可选，用于指导反序列化）

        返回：
            Python 对象
        """
        if result_json is None or result_json == '':
            return None

        try:
            result = json.loads(result_json)
        except (json.JSONDecodeError, TypeError):
            return result_json

        if ret_type is None or ret_type is type(None):
            return result

        if ret_type == int and isinstance(result, (int, float)):
            return int(result)
        if ret_type == float and isinstance(result, (int, float)):
            return float(result)
        if ret_type == bool and isinstance(result, bool):
            return bool(result)
        if ret_type == str and isinstance(result, str):
            return result
        if ret_type == bytes and isinstance(result, str):
            return result.encode('utf-8')

        return result


def get_r_type(py_type):
    """获取 Python 类型对应的 R 类型"""
    return RTypeMapper.get_r_type(py_type)


def infer_r_types(args):
    """根据参数值推断 R 类型列表"""
    return RTypeMapper.infer_r_types(args)


def serialize_args(args, r_types=None):
    """将 Python 参数序列化为 JSON"""
    return RTypeMapper.serialize_args(args, r_types)


def deserialize_result(result_json, ret_type=None):
    """将 R 返回的 JSON 反序列化为 Python 对象"""
    return RTypeMapper.deserialize_result(result_json, ret_type)
