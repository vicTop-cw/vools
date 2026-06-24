"""
vools.sql.sqlite.dialect - SQLite 方言实现

提供 SQLite 数据库方言的具体实现，包括类型映射、连接创建、
标识符引用等功能，基于 Python 标准库 sqlite3。
"""

from ..core.dialect import Dialect
from ..core.config import DialectConfig
from ..core.types import SqlTypeMapper
from ..core.builder import BaseSqlBuilder


class SqliteDialect(Dialect):
    """
    SQLite 方言实现类

    基于 Python 标准库 sqlite3 实现的 SQL 方言，
    提供 SQLite 特有的类型映射、标识符引用等功能。

    用法：
        dialect = SqliteDialect()
        conn = dialect.create_connection(database=':memory:')
        conn.connect()
    """

    _config: DialectConfig = None
    _type_mapper: SqlTypeMapper = None

    def __init__(self):
        """
        初始化 SQLite 方言
        """
        self._init_config()
        self._init_type_mapper()

    def _init_config(self) -> None:
        """
        初始化方言配置
        """
        self._config = DialectConfig(
            name='sqlite',
            driver='sqlite3',
            default_port=0,
            default_host='',
            default_user='',
            default_database=':memory:',
            paramstyle='qmark',
            identifier_quote='"',
            string_quote="'",
        )

    def _init_type_mapper(self) -> None:
        """
        初始化 SQLite 类型映射器

        基于基础 SqlTypeMapper，注册 SQLite 特有的类型。
        SQLite 的类型亲和性：INTEGER, REAL, TEXT, BLOB, NUMERIC
        """
        self._type_mapper = SqlTypeMapper

        self._type_mapper.register_type(int, 'INTEGER')
        self._type_mapper.register_type(float, 'REAL')
        self._type_mapper.register_type(str, 'TEXT')
        self._type_mapper.register_type(bytes, 'BLOB')
        self._type_mapper.register_type(bool, 'INTEGER')

        import datetime
        import decimal
        self._type_mapper.register_type(datetime.date, 'TEXT')
        self._type_mapper.register_type(datetime.datetime, 'TEXT')
        self._type_mapper.register_type(decimal.Decimal, 'NUMERIC')

    def get_config(self) -> DialectConfig:
        """
        获取 SQLite 方言配置

        返回：
            DialectConfig 实例
        """
        return self._config

    def get_type_mapper(self) -> SqlTypeMapper:
        """
        获取 SQLite 类型映射器

        返回：
            SqlTypeMapper 实例
        """
        return self._type_mapper

    def create_connection(self, **kwargs) -> 'SqliteConnection':
        """
        创建 SQLite 数据库连接

        参数：
            **kwargs: 连接参数，如 database 等

        返回：
            SqliteConnection 实例
        """
        from .connection import SqliteConnection
        return SqliteConnection(**kwargs)

    def quote_identifier(self, identifier: str) -> str:
        """
        用双引号引用标识符（表名、列名等）

        SQLite 使用双引号引用标识符，内部的双引号需要转义为两个双引号。

        参数：
            identifier: 标识符名称

        返回：
            引用后的标识符
        """
        escaped = identifier.replace('"', '""')
        return f'"{escaped}"'

    def quote_string(self, value: str) -> str:
        """
        用单引号引用字符串值

        SQLite 使用单引号引用字符串，内部的单引号需要转义为两个单引号。

        参数：
            value: 字符串值

        返回：
            引用后的字符串
        """
        escaped = value.replace("'", "''")
        return f"'{escaped}'"

    def get_builder_class(self) -> type:
        """
        获取 SQL 构建器类

        SQLite 直接使用基础构建器 BaseSqlBuilder。

        返回：
            SQL 构建器类
        """
        return BaseSqlBuilder

    def get_paramstyle(self) -> str:
        """
        获取参数占位符风格

        SQLite 使用 qmark 风格（? 占位符）。

        返回：
            'qmark'
        """
        return 'qmark'

    def is_available(self) -> bool:
        """
        检查 sqlite3 驱动是否可用

        sqlite3 是 Python 标准库，总是可用。

        返回：
            True
        """
        return True
