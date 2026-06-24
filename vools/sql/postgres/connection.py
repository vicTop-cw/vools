"""
vools.sql.postgres.connection - PostgreSQL 连接实现

提供 PostgreSQL 数据库连接的具体实现，遵循 PEP 249 DB API 2.0 规范，
支持 psycopg2 和 psycopg 两种驱动。
"""

from typing import Any, Optional, Sequence, List, Tuple

from ..core.connection import Connection
from ..core.result import ResultSet, Row


class PostgresConnection(Connection):
    """
    PostgreSQL 连接实现

    封装 psycopg2 或 psycopg 驱动的连接，提供统一的接口。
    优先使用 psycopg2，如果不可用则尝试 psycopg。

    用法：
        conn = PostgresConnection(host='localhost', user='postgres')
        conn.connect(password='pass', database='test')
        result = conn.execute('SELECT * FROM users WHERE id = %s', (1,))
        conn.commit()
        conn.close()

    上下文管理器用法：
        with PostgresConnection(...) as conn:
            conn.connect(...)
            result = conn.execute(...)
    """

    def __init__(
        self,
        host: str = 'localhost',
        port: int = 5432,
        user: str = 'postgres',
        password: str = '',
        database: str = 'postgres',
        **kwargs: Any,
    ):
        """
        初始化 PostgreSQL 连接

        参数：
            host: 主机地址，默认 'localhost'
            port: 端口号，默认 5432
            user: 用户名，默认 'postgres'
            password: 密码，默认空字符串
            database: 数据库名，默认 'postgres'
            **kwargs: 额外连接参数
        """
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._database = database
        self._extra_kwargs = kwargs
        self._conn = None
        self._connected = False
        self._driver_name = None

    def connect(self, **kwargs: Any) -> None:
        """
        建立 PostgreSQL 数据库连接

        优先使用 psycopg2 驱动，如果不可用则尝试 psycopg。
        连接成功后将 _connected 标记为 True。

        参数：
            **kwargs: 额外连接参数，会覆盖初始化时的参数
        """
        if self._connected:
            return

        host = kwargs.get('host', self._host)
        port = kwargs.get('port', self._port)
        user = kwargs.get('user', self._user)
        password = kwargs.get('password', self._password)
        database = kwargs.get('database', self._database)

        extra_kwargs = dict(self._extra_kwargs)
        for key in ('host', 'port', 'user', 'password', 'database'):
            extra_kwargs.pop(key, None)
        extra_kwargs.update({k: v for k, v in kwargs.items()
                             if k not in ('host', 'port', 'user', 'password', 'database')})

        try:
            import psycopg2
            self._driver_name = 'psycopg2'
            self._conn = psycopg2.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                dbname=database,
                **extra_kwargs,
            )
            self._connected = True
            return
        except ImportError:
            pass

        try:
            import psycopg
            self._driver_name = 'psycopg'
            self._conn = psycopg.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                dbname=database,
                **extra_kwargs,
            )
            self._connected = True
            return
        except ImportError:
            pass

        raise ImportError(
            "No PostgreSQL driver available. Please install psycopg2 or psycopg."
        )

    def close(self) -> None:
        """
        关闭 PostgreSQL 数据库连接

        关闭当前连接，释放相关资源。
        关闭后将 _connected 标记为 False。
        若连接已关闭，则不执行任何操作。
        """
        if not self._connected or self._conn is None:
            return

        try:
            self._conn.close()
        finally:
            self._conn = None
            self._connected = False

    def execute(self, sql: str, params: Optional[Sequence] = None) -> ResultSet:
        """
        执行 SQL 查询

        执行单条 SQL 语句，返回查询结果集。
        对于 INSERT/UPDATE/DELETE 等语句，返回的结果集包含受影响行数。

        参数：
            sql: 要执行的 SQL 语句
            params: SQL 参数序列，用于替换 SQL 中的占位符

        返回：
            ResultSet 查询结果集对象
        """
        if not self._connected:
            raise RuntimeError("Database connection is not established")

        cursor = self._conn.cursor()

        try:
            if params is not None:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)

            columns = []
            rows = []
            rowcount = cursor.rowcount if cursor.rowcount is not None else 0

            if cursor.description is not None:
                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()

            return ResultSet(
                columns=columns,
                rows=rows,
                rowcount=rowcount,
            )
        finally:
            cursor.close()

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
        if not self._connected:
            raise RuntimeError("Database connection is not established")

        cursor = self._conn.cursor()

        try:
            cursor.executemany(sql, seq_of_params)
            return cursor.rowcount if cursor.rowcount is not None else len(seq_of_params)
        finally:
            cursor.close()

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
        获取游标对象

        返回底层数据库驱动的游标对象，
        用于执行更底层的数据库操作。

        返回：
            底层驱动的游标对象
        """
        if not self._connected:
            raise RuntimeError("Database connection is not established")

        return self._conn.cursor()

    @property
    def driver_name(self) -> Optional[str]:
        """
        获取当前使用的驱动名称

        返回：
            驱动名称（'psycopg2' 或 'psycopg'），未连接时为 None
        """
        return self._driver_name
