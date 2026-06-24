"""
vools.sql.postgres.dialect - PostgreSQL 方言实现

提供 PostgreSQL 数据库的方言实现，包括类型映射、连接创建、
标识符引用、SQL 构建器等功能。
"""

import uuid
import json
from typing import Optional

from ..core.dialect import Dialect
from ..core.config import DialectConfig
from ..core.types import SqlTypeMapper
from ..core.builder import BaseSqlBuilder


class PostgresDialect(Dialect):
    """
    PostgreSQL 方言实现

    提供 PostgreSQL 数据库特有的方言配置和功能，
    支持 psycopg2 和 psycopg 两种驱动。

    用法：
        dialect = PostgresDialect()
        conn = dialect.create_connection(host='localhost', user='postgres')
        result = conn.execute('SELECT 1')
    """

    _config: Optional[DialectConfig] = None
    _type_mapper: Optional[SqlTypeMapper] = None

    def get_config(self) -> DialectConfig:
        """
        获取 PostgreSQL 方言配置

        返回：
            DialectConfig 实例
        """
        if self._config is None:
            self._config = DialectConfig(
                name='postgres',
                driver='psycopg2',
                default_port=5432,
                default_host='localhost',
                default_user='postgres',
                default_database='postgres',
                paramstyle='pyformat',
                identifier_quote='"',
                string_quote="'",
            )
        return self._config

    def get_type_mapper(self) -> SqlTypeMapper:
        """
        获取 PostgreSQL 类型映射器

        基于基础 SqlTypeMapper，注册 PostgreSQL 特有的类型。

        返回：
            SqlTypeMapper 实例
        """
        if self._type_mapper is None:
            mapper = SqlTypeMapper()

            mapper.register_type(uuid.UUID, 'UUID')
            mapper.register_type(bytes, 'BYTEA')

            mapper._sql_to_py['SERIAL'] = int
            mapper._sql_to_py['BIGSERIAL'] = int
            mapper._sql_to_py['UUID'] = uuid.UUID
            mapper._sql_to_py['JSONB'] = dict
            mapper._sql_to_py['JSON'] = dict
            mapper._sql_to_py['BYTEA'] = bytes
            mapper._sql_to_py['TIMESTAMPTZ'] = __import__('datetime').datetime
            mapper._sql_to_py['TIMESTAMP WITH TIME ZONE'] = __import__('datetime').datetime
            mapper._sql_to_py['ARRAY'] = list

            self._type_mapper = mapper

        return self._type_mapper

    def create_connection(self, **kwargs) -> 'PostgresConnection':
        """
        创建 PostgreSQL 连接

        参数：
            **kwargs: 连接参数，如 host, port, user, password, database 等

        返回：
            PostgresConnection 实例
        """
        from .connection import PostgresConnection
        return PostgresConnection(**kwargs)

    def quote_identifier(self, identifier: str) -> str:
        """
        用双引号引用标识符

        PostgreSQL 对标识符大小写敏感，使用双引号引用时保留大小写。

        参数：
            identifier: 标识符名称

        返回：
            引用后的标识符
        """
        quote = self.get_config().identifier_quote
        escaped = identifier.replace(quote, quote + quote)
        return f"{quote}{escaped}{quote}"

    def quote_string(self, value: str) -> str:
        """
        用单引号引用字符串

        转义内部单引号，防止 SQL 注入。

        参数：
            value: 字符串值

        返回：
            引用后的字符串
        """
        quote = self.get_config().string_quote
        escaped = value.replace(quote, quote + quote)
        return f"{quote}{escaped}{quote}"

    def get_builder_class(self) -> type:
        """
        获取 SQL 构建器类

        返回：
            BaseSqlBuilder 类
        """
        return BaseSqlBuilder

    def get_paramstyle(self) -> str:
        """
        获取参数占位符风格

        PostgreSQL 使用 pyformat 风格（%s 占位符）。

        返回：
            'pyformat'
        """
        return self.get_config().paramstyle

    def is_available(self) -> bool:
        """
        检查 PostgreSQL 驱动是否可用

        优先检查 psycopg2，如果不可用则检查 psycopg。

        返回：
            驱动是否可用
        """
        try:
            import psycopg2
            return True
        except ImportError:
            pass

        try:
            import psycopg
            return True
        except ImportError:
            pass

        return False
