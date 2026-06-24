"""
vools.sql.sqlite - SQLite 方言包

提供 SQLite 数据库方言的完整实现，包括方言类、连接类
以及便捷的连接函数。基于 Python 标准库 sqlite3。

用法：
    from vools.sql.sqlite import connect, SqliteDialect, SqliteConnection

    # 便捷方式
    conn = connect(':memory:')
    result = conn.execute('SELECT 1')

    # 手动方式
    dialect = SqliteDialect()
    conn = dialect.create_connection(database='test.db')
    conn.connect()
"""

from .dialect import SqliteDialect
from .connection import SqliteConnection


_dialect: SqliteDialect = None


def _get_dialect() -> SqliteDialect:
    """
    获取全局 SQLite 方言实例

    返回：
        SqliteDialect 单例实例
    """
    global _dialect
    if _dialect is None:
        _dialect = SqliteDialect()
    return _dialect


def is_available() -> bool:
    """
    检查 SQLite 驱动是否可用

    sqlite3 是 Python 标准库，总是返回 True。

    返回：
        True
    """
    return _get_dialect().is_available()


def connect(database: str = ':memory:', **kwargs) -> SqliteConnection:
    """
    创建并连接 SQLite 数据库

    便捷函数，创建 SqliteConnection 并自动建立连接。

    参数：
        database: 数据库文件路径，默认为 ':memory:' 表示内存数据库
        **kwargs: 额外的连接参数，传递给 sqlite3.connect()

    返回：
        已连接的 SqliteConnection 实例

    用法：
        conn = connect(':memory:')
        result = conn.execute('SELECT 1')
        conn.close()
    """
    conn = SqliteConnection(database=database, **kwargs)
    conn.connect()
    return conn


__all__ = [
    'SqliteDialect',
    'SqliteConnection',
    'connect',
    'is_available',
]
