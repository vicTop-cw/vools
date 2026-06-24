"""
vools.sql.postgres - PostgreSQL 方言包

提供 PostgreSQL 数据库的方言实现，包括方言配置、连接管理、
类型映射等功能。

用法：
    from vools.sql.postgres import PostgresDialect, PostgresConnection, connect, is_available

    # 检查驱动是否可用
    if is_available():
        # 创建并连接
        conn = connect(host='localhost', user='postgres', password='pass')
        result = conn.execute('SELECT 1')
        conn.close()
"""

from .dialect import PostgresDialect
from .connection import PostgresConnection

__all__ = [
    'PostgresDialect',
    'PostgresConnection',
    'connect',
    'is_available',
    'dialect',
]

_dialect_instance = None


def _get_dialect():
    """
    获取全局 PostgreSQL 方言实例

    返回：
        PostgresDialect 实例
    """
    global _dialect_instance
    if _dialect_instance is None:
        _dialect_instance = PostgresDialect()
    return _dialect_instance


class _DialectProxy:
    """
    方言代理类，用于延迟初始化

    首次访问时才创建 PostgresDialect 实例。
    """

    def __getattr__(self, name):
        return getattr(_get_dialect(), name)

    def __dir__(self):
        return dir(_get_dialect())


dialect = _DialectProxy()


def connect(**kwargs):
    """
    创建并建立 PostgreSQL 连接

    便捷函数，创建 PostgresConnection 实例并调用 connect()。

    参数：
        **kwargs: 连接参数，如 host, port, user, password, database 等

    返回：
        已连接的 PostgresConnection 实例
    """
    conn = PostgresConnection(**kwargs)
    conn.connect()
    return conn


def is_available():
    """
    检查 PostgreSQL 驱动是否可用

    优先检查 psycopg2，如果不可用则检查 psycopg。

    返回：
        驱动是否可用
    """
    return _get_dialect().is_available()
