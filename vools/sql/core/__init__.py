"""
vools.sql.core - SQL 核心基础设施

包含类型映射、构建器抽象、连接抽象、结果集抽象、装饰器、方言基类等。
"""

from .types import (
    SqlTypeMapper,
    PY_TO_SQL,
    SQL_TO_PY,
    infer_arg_types,
    infer_ret_type,
    convert_args,
    convert_result,
)
from .config import DialectConfig
from .dialect import (
    Dialect,
    register_dialect,
    get_dialect,
    list_dialects,
    has_dialect,
)
from .builder import SqlBuilder, BaseSqlBuilder
from .connection import Connection
from .result import ResultSet, Row
from .decorators import sql_function, sql_module, sql_func_name

__all__ = [
    'SqlTypeMapper',
    'PY_TO_SQL',
    'SQL_TO_PY',
    'infer_arg_types',
    'infer_ret_type',
    'convert_args',
    'convert_result',
    'DialectConfig',
    'Dialect',
    'register_dialect',
    'get_dialect',
    'list_dialects',
    'has_dialect',
    'SqlBuilder',
    'BaseSqlBuilder',
    'Connection',
    'ResultSet',
    'Row',
    'sql_function',
    'sql_module',
    'sql_func_name',
]
