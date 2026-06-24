"""
vools.sql.sqlite.connection - SQLite 数据库连接实现

提供 SQLite 数据库连接的具体实现，基于 Python 标准库 sqlite3，
封装了连接管理、SQL 执行、事务控制等功能。
"""

import sqlite3
from typing import Any, Optional, Sequence, List, Tuple

from ..core.connection import Connection
from ..core.result import ResultSet, Row


class SqliteConnection(Connection):
    """
    SQLite 数据库连接实现类

    基于 Python 标准库 sqlite3 实现的数据库连接，
    提供统一的连接管理、SQL 执行、事务控制接口。

    用法：
        conn = SqliteConnection(database=':memory:')
        conn.connect()
        result = conn.execute('SELECT 1')
        conn.close()

    上下文管理器用法：
        with SqliteConnection(database='test.db') as conn:
            conn.execute('CREATE TABLE users (id INTEGER, name TEXT)')
    """

    _database: str
    _conn_kwargs: dict

    def __init__(self, database: str = ':memory:', **kwargs):
        """
        初始化 SQLite 连接

        参数：
            database: 数据库文件路径，默认为 ':memory:' 表示内存数据库
            **kwargs: 额外的连接参数，将传递给 sqlite3.connect()
        """
        self._database = database
        self._conn_kwargs = kwargs
        self._connected = False
        self._conn = None

    def connect(self, **kwargs: Any) -> None:
        """
        建立 SQLite 数据库连接

        如果已有连接，先关闭再重新连接。
        连接成功后将 _connected 标记为 True。

        参数：
            **kwargs: 额外的连接参数，会覆盖初始化时的参数
        """
        if self._connected:
            self.close()

        connect_kwargs = dict(self._conn_kwargs)
        connect_kwargs.update(kwargs)

        if 'database' in connect_kwargs:
            self._database = connect_kwargs.pop('database')

        self._conn = sqlite3.connect(self._database, **connect_kwargs)
        self._connected = True

    def close(self) -> None:
        """
        关闭 SQLite 数据库连接

        关闭当前数据库连接，释放相关资源。
        关闭后将 _connected 标记为 False。
        若连接已关闭，则不执行任何操作。
        """
        if not self._connected:
            return

        try:
            if self._conn is not None:
                self._conn.close()
        finally:
            self._conn = None
            self._connected = False

    def execute(self, sql: str, params: Optional[Sequence] = None) -> ResultSet:
        """
        执行 SQL 查询

        执行单条 SQL 语句，返回查询结果集。
        对于 SELECT 查询，返回包含所有行的 ResultSet；
        对于 INSERT/UPDATE/DELETE 等 DML 语句，返回设置了 rowcount 的 ResultSet。

        参数：
            sql: 要执行的 SQL 语句
            params: SQL 参数序列，用于替换 SQL 中的 ? 占位符

        返回：
            ResultSet 查询结果集对象

        异常：
            RuntimeError: 连接未建立
        """
        if not self._connected or self._conn is None:
            raise RuntimeError('Database connection is not established')

        cursor = self._conn.cursor()

        if params is None:
            cursor.execute(sql)
        else:
            cursor.execute(sql, params)

        sql_upper = sql.strip().upper()

        if sql_upper.startswith(('SELECT', 'WITH', 'PRAGMA', 'EXPLAIN')):
            columns = []
            if cursor.description is not None:
                columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            result = ResultSet(
                columns=columns,
                rows=rows,
                rowcount=len(rows),
            )
        else:
            result = ResultSet(
                columns=[],
                rows=[],
                rowcount=cursor.rowcount,
            )

        cursor.close()
        return result

    def executemany(self, sql: str, seq_of_params: Sequence[Sequence]) -> int:
        """
        批量执行 SQL 语句

        使用多组参数重复执行同一条 SQL 语句，
        常用于批量插入或批量更新操作。

        参数：
            sql: 要执行的 SQL 语句
            seq_of_params: 参数序列的序列，每组参数对应一次执行

        返回：
            受影响的总行数
        """
        cursor = self._conn.cursor()
        cursor.executemany(sql, seq_of_params)
        rowcount = cursor.rowcount
        cursor.close()
        return rowcount if rowcount >= 0 else len(seq_of_params)

    def commit(self) -> None:
        """
        提交事务

        将当前事务中的所有修改提交到数据库。
        若连接未建立，则不执行任何操作。
        """
        if self._connected and self._conn is not None:
            self._conn.commit()

    def rollback(self) -> None:
        """
        回滚事务

        撤销当前事务中的所有修改，回滚到事务开始前的状态。
        若连接未建立，则不执行任何操作。
        """
        if self._connected and self._conn is not None:
            self._conn.rollback()

    def cursor(self) -> object:
        """
        获取底层 sqlite3 游标对象

        返回底层 sqlite3 驱动的游标对象，
        用于执行更底层的数据库操作。

        返回：
            sqlite3.Cursor 游标对象

        异常：
            RuntimeError: 连接未建立
        """
        if not self._connected or self._conn is None:
            raise RuntimeError('Database connection is not established')
        return self._conn.cursor()

    @property
    def database(self) -> str:
        """
        获取数据库路径

        返回：
            数据库文件路径或 ':memory:'
        """
        return self._database

    def __repr__(self) -> str:
        """
        返回字符串表示

        返回：
            SqliteConnection 的字符串表示
        """
        status = 'connected' if self._connected else 'closed'
        return f"SqliteConnection(database={self._database!r}, status={status})"
