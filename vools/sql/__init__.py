"""
vools.sql - SQL 方言框架

提供统一的 SQL 方言抽象与构建能力，支持多种数据库的 SQL 生成与适配。

子模块：
- core: 核心基础设施（类型映射、构建器抽象、连接抽象、结果集抽象、装饰器、方言基类）
- manager: SQL 方言管理器与注册表
- mysql: MySQL 方言实现
- postgres: PostgreSQL 方言实现
- sqlite: SQLite 方言实现
- spark: Spark SQL 方言实现
- oracle: Oracle 方言实现
- mssql: SQL Server 方言实现
"""

from .core.types import SqlTypeMapper, PY_TO_SQL, SQL_TO_PY, infer_arg_types, infer_ret_type, convert_args, convert_result
from .core.builder import SqlBuilder, BaseSqlBuilder
from .core.connection import Connection
from .core.result import ResultSet, Row
from .core.decorators import sql_function, sql_module, sql_func_name
from .core.dialect import Dialect, register_dialect as _core_register_dialect, get_dialect as _core_get_dialect, list_dialects as _core_list_dialects, has_dialect
from .core.config import DialectConfig

from .manager import (
    manager,
    DialectManager,
    register_dialect,
    get_dialect,
    create_dialect,
    is_available,
    list_dialects,
    list_available,
    get_config,
    set_config,
    save_config,
    load_config,
)

__all__ = [
    # core.types
    'SqlTypeMapper',
    'PY_TO_SQL',
    'SQL_TO_PY',
    'infer_arg_types',
    'infer_ret_type',
    'convert_args',
    'convert_result',

    # core.builder
    'SqlBuilder',
    'BaseSqlBuilder',

    # core.connection
    'Connection',

    # core.result
    'ResultSet',
    'Row',

    # core.decorators
    'sql_function',
    'sql_module',
    'sql_func_name',

    # core.dialect
    'Dialect',
    'has_dialect',

    # core.config
    'DialectConfig',

    # manager
    'manager',
    'DialectManager',
    'register_dialect',
    'get_dialect',
    'create_dialect',
    'is_available',
    'list_dialects',
    'list_available',
    'get_config',
    'set_config',
    'save_config',
    'load_config',
    'get_config_file_path',
    'clear_instance_cache',

    # 方言模块
    'mysql',
    'postgres',
    'sqlite',
    'spark',
    'oracle',
    'mssql',

    # 子模块
    'core',
    'manager',
]

# 延迟导入方言模块，避免导入失败影响整体
_mysql_loaded = False
_postgres_loaded = False
_sqlite_loaded = False
_spark_loaded = False
_oracle_loaded = False
_mssql_loaded = False


def _load_mysql():
    """延迟加载 MySQL 模块"""
    global _mysql_loaded
    if not _mysql_loaded:
        try:
            from . import mysql
            globals()['mysql'] = mysql
            _mysql_loaded = True
        except Exception:
            _mysql_loaded = False
    return _mysql_loaded


def _load_postgres():
    """延迟加载 PostgreSQL 模块"""
    global _postgres_loaded
    if not _postgres_loaded:
        try:
            from . import postgres
            globals()['postgres'] = postgres
            _postgres_loaded = True
        except Exception:
            _postgres_loaded = False
    return _postgres_loaded


def _load_sqlite():
    """延迟加载 SQLite 模块"""
    global _sqlite_loaded
    if not _sqlite_loaded:
        try:
            from . import sqlite
            globals()['sqlite'] = sqlite
            _sqlite_loaded = True
        except Exception:
            _sqlite_loaded = False
    return _sqlite_loaded


def _load_spark():
    """延迟加载 Spark SQL 模块"""
    global _spark_loaded
    if not _spark_loaded:
        try:
            from . import spark
            globals()['spark'] = spark
            _spark_loaded = True
        except Exception:
            _spark_loaded = False
    return _spark_loaded


def _load_oracle():
    """延迟加载 Oracle 模块"""
    global _oracle_loaded
    if not _oracle_loaded:
        try:
            from . import oracle
            globals()['oracle'] = oracle
            _oracle_loaded = True
        except Exception:
            _oracle_loaded = False
    return _oracle_loaded


def _load_mssql():
    """延迟加载 SQL Server 模块"""
    global _mssql_loaded
    if not _mssql_loaded:
        try:
            from . import mssql
            globals()['mssql'] = mssql
            _mssql_loaded = True
        except Exception:
            _mssql_loaded = False
    return _mssql_loaded


def __getattr__(name):
    """延迟加载属性"""
    if name == 'mysql':
        if _load_mysql():
            return globals().get(name)
        raise AttributeError("module 'vools.sql' has no attribute '%s'" % name)

    if name == 'postgres':
        if _load_postgres():
            return globals().get(name)
        raise AttributeError("module 'vools.sql' has no attribute '%s'" % name)

    if name == 'sqlite':
        if _load_sqlite():
            return globals().get(name)
        raise AttributeError("module 'vools.sql' has no attribute '%s'" % name)

    if name == 'spark':
        if _load_spark():
            return globals().get(name)
        raise AttributeError("module 'vools.sql' has no attribute '%s'" % name)

    if name == 'oracle':
        if _load_oracle():
            return globals().get(name)
        raise AttributeError("module 'vools.sql' has no attribute '%s'" % name)

    if name == 'mssql':
        if _load_mssql():
            return globals().get(name)
        raise AttributeError("module 'vools.sql' has no attribute '%s'" % name)

    # manager 额外函数
    manager_funcs = (
        'get_config_file_path',
        'clear_instance_cache',
    )
    if name in manager_funcs:
        return getattr(globals()['manager'], name)

    raise AttributeError("module 'vools.sql' has no attribute '%s'" % name)


def __dir__():
    """返回所有可用的导出名称"""
    return sorted(set(globals().keys()) | set(__all__))
