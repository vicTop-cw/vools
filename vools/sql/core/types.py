"""
vools.sql.core.types - Python ↔ SQL 类型映射系统

提供 Python 类型与 SQL 类型之间的自动转换和推断能力，
简化 SQL 语句构建和结果处理时的类型声明工作。
"""

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

    @staticmethod
    def register_type(py_type, sql_type):
        """
        注册自定义类型映射

        参数：
            py_type: Python 类型
            sql_type: 对应的 SQL 类型字符串
        """
        SqlTypeMapper._py_to_sql[py_type] = sql_type
        SqlTypeMapper._sql_to_py[sql_type.upper()] = py_type

    @staticmethod
    def get_sql_type(py_type):
        """
        获取 Python 类型对应的 SQL 类型

        参数：
            py_type: Python 类型

        返回：
            SQL 类型字符串，如果未注册则返回 None
        """
        return SqlTypeMapper._py_to_sql.get(py_type)

    @staticmethod
    def get_py_type(sql_type):
        """
        获取 SQL 类型对应的 Python 类型

        参数：
            sql_type: SQL 类型字符串（不区分大小写）

        返回：
            Python 类型，如果未注册则返回 None
        """
        return SqlTypeMapper._sql_to_py.get(sql_type.upper())

    @staticmethod
    def infer_arg_types(args):
        """
        根据参数值推断 SQL 参数类型列表

        遍历参数列表，根据每个参数的 Python 类型推断对应的 SQL 类型。
        对于未注册的类型，默认使用 'VARCHAR'。

        参数：
            args: 参数值列表

        返回：
            SQL 类型字符串列表
        """
        result = []
        for arg in args:
            py_type = type(arg)
            sql_type = SqlTypeMapper._py_to_sql.get(py_type)
            if sql_type is None:
                sql_type = 'VARCHAR'
            result.append(sql_type)
        return result

    @staticmethod
    def infer_ret_type(ret_type):
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
        if isinstance(ret_type, type):
            sql_type = SqlTypeMapper._py_to_sql.get(ret_type)
            if sql_type is not None:
                return sql_type
        return 'INTEGER'

    @staticmethod
    def convert_args(args, sql_types):
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

    @staticmethod
    def convert_result(result, py_type):
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
