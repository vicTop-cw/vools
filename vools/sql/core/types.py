"""
vools.sql.core.types - Python ↔ SQL 类型映射系统

提供 Python 类型与 SQL 类型之间的自动转换和推断能力，
简化 SQL 语句构建和结果处理时的类型声明工作。
"""

import functools
import datetime
import decimal


PY_TO_SQL = {
    int: 'INTEGER',
    float: 'DOUBLE',
    bool: 'BOOLEAN',
    str: 'VARCHAR',
    bytes: 'BLOB',
    datetime.date: 'DATE',
    datetime.datetime: 'DATETIME',
    decimal.Decimal: 'DECIMAL',
    dict: 'JSON',
    list: 'JSON',
    type(None): 'NULL',
}


SQL_TO_PY = {
    'INTEGER': int,
    'INT': int,
    'BIGINT': int,
    'SMALLINT': int,
    'TINYINT': int,
    'FLOAT': float,
    'DOUBLE': float,
    'REAL': float,
    'BOOLEAN': bool,
    'BOOL': bool,
    'VARCHAR': str,
    'CHAR': str,
    'TEXT': str,
    'STRING': str,
    'CLOB': str,
    'BLOB': bytes,
    'BINARY': bytes,
    'VARBINARY': bytes,
    'DATE': datetime.date,
    'DATETIME': datetime.datetime,
    'TIMESTAMP': datetime.datetime,
    'DECIMAL': decimal.Decimal,
    'NUMERIC': decimal.Decimal,
    'JSON': dict,
}


class _DualMapperMethod:
    """BUG-353: 让映射方法同时支持两种调用方式。

    - `SqlTypeMapper.get_sql_type(x)`：类调用，使用**类级默认映射**（向后兼容）；
    - `mapper.get_sql_type(x)`：实例调用，使用**实例自己的映射副本**。

    原实现全是 staticmethod 且写类级字典 —— 任何方言实例初始化时
    `register_type(...)`（sqlite: str->TEXT/float->REAL；postgres: str->STRING/
    list->ARRAY）都会**污染全局映射**，结果随方言实例创建顺序而变。
    """

    def __init__(self, fn):
        self.fn = fn
        functools.update_wrapper(self, fn)

    def __get__(self, obj, objtype=None):
        # obj is None -> 类访问：self 传 None 表示"使用类级字典"
        return functools.partial(self.fn, obj)


def _mapper_maps(obj):
    """取映射字典：obj 为实例时用实例副本，为 None（类访问）时用类级默认。"""
    if obj is None:
        return SqlTypeMapper._py_to_sql, SqlTypeMapper._sql_to_py
    return obj._py_to_sql, obj._sql_to_py


class SqlTypeMapper:
    """
    SQL 类型映射器

    提供 Python 类型与 SQL 类型之间的转换和推断功能，
    支持根据参数值自动推断类型，以及自动转换参数格式。

    用法：
        sql_types = SqlTypeMapper.infer_arg_types([1, 2.0, "hello"])
        converted = SqlTypeMapper.convert_args([1, "hello"], sql_types)
    """

    _py_to_sql = dict(PY_TO_SQL)
    _sql_to_py = dict(SQL_TO_PY)

    def __init__(self):
        # BUG-353: 实例持有映射副本，方言注册不再改类级全局映射
        self._py_to_sql = dict(type(self)._py_to_sql)
        self._sql_to_py = dict(type(self)._sql_to_py)

    @_DualMapperMethod
    def register_type(self, py_type, sql_type):
        """
        注册自定义类型映射

        参数：
            py_type: Python 类型
            sql_type: 对应的 SQL 类型字符串
        """
        # BUG-457: 原实现零校验——``register_type(123, 456)`` 抛
        # ``AttributeError: 'int' object has no attribute 'upper'``（看不出哪个参数
        # 错），而 ``register_type(int, '')`` 会**静默注册空类型**：此后
        # ``get_sql_type(int)`` 返回 ''，映射被污染且无任何提示。
        if not isinstance(py_type, type):
            raise TypeError(
                f"register_type() 的 py_type 必须是类型，收到 "
                f"{type(py_type).__name__}: {py_type!r}")
        if not isinstance(sql_type, str) or not sql_type.strip():
            raise ValueError(
                f"register_type() 的 sql_type 必须是非空字符串，收到 "
                f"{type(sql_type).__name__}: {sql_type!r}")
        _py_map, _sql_map = _mapper_maps(self)
        _py_map[py_type] = sql_type
        _sql_map[sql_type.upper()] = py_type

    @_DualMapperMethod
    def get_sql_type(self, py_type):
        """
        获取 Python 类型对应的 SQL 类型

        参数：
            py_type: Python 类型

        返回：
            SQL 类型字符串，如果未注册则返回 None
        """
        _py_map, _ = _mapper_maps(self)
        return _py_map.get(py_type)

    @_DualMapperMethod
    def get_py_type(self, sql_type):
        """
        获取 SQL 类型对应的 Python 类型

        参数：
            sql_type: SQL 类型字符串（不区分大小写）

        返回：
            Python 类型，如果未注册则返回 None
        """
        # BUG-457: 非字符串会抛 cryptic 的 'int' object has no attribute 'upper'。
        if not isinstance(sql_type, str):
            raise TypeError(
                f"get_py_type() 的 sql_type 必须是字符串，收到 "
                f"{type(sql_type).__name__}: {sql_type!r}")
        _, _sql_map = _mapper_maps(self)
        return _sql_map.get(sql_type.upper())

    @_DualMapperMethod
    def infer_arg_types(self, args):
        """
        根据参数值推断 SQL 参数类型列表

        遍历参数列表，根据每个参数的 Python 类型推断对应的 SQL 类型。
        对于未注册的类型，默认使用 'VARCHAR'。

        参数：
            args: 参数值列表

        返回：
            SQL 类型字符串列表
        """
        _py_map, _ = _mapper_maps(self)
        result = []
        for arg in args:
            py_type = type(arg)
            sql_type = _py_map.get(py_type)
            if sql_type is None:
                sql_type = 'VARCHAR'
            result.append(sql_type)
        return result

    @_DualMapperMethod
    def infer_ret_type(self, ret_type):
        """
        根据返回类型注解推断 SQL 返回类型

        参数：
            ret_type: Python 返回类型注解（如 int、str 等），
                     可以是 None 表示无返回值

        返回：
            对应的 SQL 类型字符串，如果无法推断则返回 'INTEGER'
        """
        if ret_type is None or ret_type is type(None):
            return None
        # BUG-352: Optional[X] 解包后再推断
        _origin_o = getattr(ret_type, '__origin__', None)
        if _origin_o is not None and getattr(_origin_o, '__name__', '') == 'Union':
            _inner = [a for a in (getattr(ret_type, '__args__', ()) or ())
                      if a is not type(None)]
            if len(_inner) == 1:
                ret_type = _inner[0]
        _py_map, _ = _mapper_maps(self)
        if isinstance(ret_type, type):
            sql_type = _py_map.get(ret_type)
            if sql_type is not None:
                return sql_type
        # BUG-352: List[int]/Dict[str, int] 等泛型按 origin 映射（list/dict -> JSON），
        # 原实现落到最后 fallback 'INTEGER'，与 PY_TO_SQL 的声明不一致。
        _origin = getattr(ret_type, '__origin__', None)
        if _origin is not None:
            sql_type = _py_map.get(_origin)
            if sql_type is not None:
                return sql_type
        return 'INTEGER'

    @_DualMapperMethod
    def convert_args(self, args, sql_types):
        """
        转换参数值为 SQL 兼容格式

        目前为简单原样返回，后续方言扩展时将添加具体转换逻辑。

        参数：
            args: 原始参数值列表
            sql_types: SQL 参数类型列表

        返回：
            转换后的参数列表
        """
        return list(args)

    @_DualMapperMethod
    def convert_result(self, result, py_type):
        """
        转换 SQL 结果值为 Python 类型

        目前为简单原样返回，后续方言扩展时将添加具体转换逻辑。

        参数：
            result: SQL 结果值
            py_type: 目标 Python 类型

        返回：
            转换后的 Python 值
        """
        return result


def infer_arg_types(args):
    """
    根据参数值推断 SQL 参数类型列表（便捷函数）

    参数：
        args: 参数值列表

    返回：
        SQL 类型字符串列表
    """
    return SqlTypeMapper.infer_arg_types(args)


def infer_ret_type(ret_type):
    """
    根据返回类型注解推断 SQL 返回类型（便捷函数）

    参数：
        ret_type: Python 返回类型注解

    返回：
        对应的 SQL 类型字符串
    """
    return SqlTypeMapper.infer_ret_type(ret_type)


def convert_args(args, sql_types):
    """
    转换参数值为 SQL 兼容格式（便捷函数）

    参数：
        args: 原始参数值列表
        sql_types: SQL 参数类型列表

    返回：
        转换后的参数列表
    """
    return SqlTypeMapper.convert_args(args, sql_types)


def convert_result(result, py_type):
    """
    转换 SQL 结果值为 Python 类型（便捷函数）

    参数：
        result: SQL 结果值
        py_type: 目标 Python 类型

    返回：
        转换后的 Python 值
    """
    return SqlTypeMapper.convert_result(result, py_type)


__all__ = [
    'PY_TO_SQL',
    'SQL_TO_PY',
    'SqlTypeMapper',
    'convert_args',
    'convert_result',
    'infer_arg_types',
    'infer_ret_type'
]
