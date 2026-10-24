"""
vools.db.postgresql — PostgreSQL 连接管理

提供 PostgreSQL 数据库的连接管理、事务执行、查询封装等功能。
通过 vools.config 获取连接参数，也支持直接传入参数覆盖。

依赖：
    psycopg2-binary（PostgreSQL 适配器）

用法：
    from vools.db.postgresql import PostgreSQLConnection

    # 方式 1：使用 config 中的默认配置
    conn = PostgreSQLConnection()
    conn.execute('SELECT 1')

    # 方式 2：直接传入参数
    conn = PostgreSQLConnection(host='localhost', port=5432, user='postgres',
                                password='secret', database='mydb')
    result = conn.query('SELECT * FROM users WHERE id = %s', [1])
    conn.close()
"""

from __future__ import absolute_import

__all__ = [
    "PostgreSQLConnection",
]

import logging
import os
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)


class PostgreSQLConnection:
    """PostgreSQL 连接管理器。

    支持上下文管理器（with 语句）自动管理连接生命周期，
    提供执行查询、批量操作、事务管理等功能。
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        database: Optional[str] = None,
        **kwargs,
    ):
        """
        初始化 PostgreSQL 连接管理器。

        参数未传入时，依次从以下来源读取：
            1. 环境变量 PG_HOST / PG_PORT / PG_USER / PG_PASSWORD / PG_DATABASE
            2. vools.config.DATABASE_CONFIG

        参数:
            host: 数据库主机地址
            port: 数据库端口
            user: 用户名
            password: 密码
            database: 数据库名称
            **kwargs: 传递给 psycopg2.connect 的额外参数
        """
        # BUG-461: 显式传入的参数原为零校验——`host=''`/`database=''` 因 `or`
        # 短路被**静默替换**成 env/config/默认值（可能连到非预期的库），
        # `port='x'`/`port=-1`/`port=70000` 也被原样存下，直到 psycopg2.connect
        # 才以晦涩错误暴露。显式给出的值必须在构造时就校验。
        self._validate_explicit(host, port, user, password, database)

        # 从 config 读取默认值（避免循环导入，延迟加载）
        try:
            from ..config import DATABASE_CONFIG
        except ImportError:
            DATABASE_CONFIG = {}

        self._host = host or os.environ.get('PG_HOST', DATABASE_CONFIG.get('host', 'localhost'))
        self._port = port or int(os.environ.get('PG_PORT', DATABASE_CONFIG.get('port', 5432)))
        self._user = user or os.environ.get('PG_USER', DATABASE_CONFIG.get('user', 'postgres'))
        self._password = password or os.environ.get('PG_PASSWORD', DATABASE_CONFIG.get('password', ''))
        self._database = database or os.environ.get('PG_DATABASE', DATABASE_CONFIG.get('database', 'postgres'))
        # 解析后的端口同样要求合法（env/config 可能写错）
        try:
            _port = int(self._port)
        except (TypeError, ValueError):
            raise ValueError(
                f"PostgreSQL 端口必须是整数，解析得到 {self._port!r}")
        if not 1 <= _port <= 65535:
            raise ValueError(f"PostgreSQL 端口必须在 1..65535，收到 {_port}")
        self._port = _port

        self._connect_kwargs = kwargs
        self._connection = None

    @staticmethod
    def _validate_explicit(host, port, user, password, database) -> None:
        """校验**显式传入**的连接参数（BUG-461）。"""
        for name, value in (("host", host), ("user", user), ("database", database)):
            if value is None:
                continue
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"PostgreSQL 的 {name} 必须是非空字符串，收到 "
                    f"{type(value).__name__}: {value!r}")
        if password is not None and not isinstance(password, str):
            raise TypeError(
                f"PostgreSQL 的 password 必须是字符串，收到 "
                f"{type(password).__name__}: {password!r}")
        if port is not None:
            if isinstance(port, bool) or not isinstance(port, int):
                raise TypeError(
                    f"PostgreSQL 的 port 必须是整数，收到 "
                    f"{type(port).__name__}: {port!r}")
            if not 1 <= port <= 65535:
                raise ValueError(
                    f"PostgreSQL 的 port 必须在 1..65535，收到 {port}")

    def _get_connection(self):
        """获取或创建数据库连接（惰性连接）。"""
        if self._connection is None or self._connection.closed:
            import psycopg2
            self._connection = psycopg2.connect(
                host=self._host,
                port=self._port,
                user=self._user,
                password=self._password,
                dbname=self._database,
                **self._connect_kwargs,
            )
            self._connection.autocommit = False
            logger.debug('已连接到 PostgreSQL %s:%s/%s', self._host, self._port, self._database)
        return self._connection

    @contextmanager
    def _transaction(self):
        """事务上下文管理器：成功提交，失败回滚。"""
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def execute(self, sql: str, params: Optional[List[Any]] = None) -> None:
        """
        执行一条 SQL 语句（无返回结果，适合 DDL / DML）。

        参数:
            sql: SQL 语句（%s 占位符）
            params: 参数列表

        示例:
            conn.execute('CREATE TABLE t (id INT, name TEXT)')
            conn.execute('INSERT INTO t VALUES (%s, %s)', [1, 'a'])
        """
        conn = None
        cur = None
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute(sql, params)
            conn.commit()
        except Exception:
            if conn is not None:
                conn.rollback()
            raise
        finally:
            if cur is not None:
                cur.close()

    def query(
        self,
        sql: str,
        params: Optional[List[Any]] = None,
        fetch: bool = True,
    ) -> Optional[List[Tuple]]:
        """
        执行查询并返回结果。

        参数:
            sql: SQL 语句
            params: 参数列表
            fetch: 是否获取结果（False 时用于 DML 且不返回行）

        返回:
            查询结果列表（每行一个 tuple），fetch=False 时返回 None

        示例:
            rows = conn.query('SELECT id, name FROM users WHERE id > %s', [10])
        """
        conn = None
        cur = None
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute(sql, params)
            if fetch:
                return cur.fetchall()
            conn.commit()
            return None
        except Exception:
            if conn is not None:
                conn.rollback()
            raise
        finally:
            if cur is not None:
                cur.close()

    def query_one(
        self,
        sql: str,
        params: Optional[List[Any]] = None,
    ) -> Optional[Tuple]:
        """
        执行查询并返回第一行。

        返回:
            单行 tuple，无结果返回 None
        """
        conn = None
        cur = None
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute(sql, params)
            return cur.fetchone()
        except Exception:
            if conn is not None:
                conn.rollback()
            raise
        finally:
            if cur is not None:
                cur.close()

    def executemany(
        self,
        sql: str,
        seq_of_params: List[List[Any]],
    ) -> int:
        """
        批量执行 SQL（如批量 INSERT）。

        参数:
            sql: SQL 语句
            seq_of_params: 参数序列

        返回:
            影响的行数
        """
        conn = None
        cur = None
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.executemany(sql, seq_of_params)
            conn.commit()
            return cur.rowcount
        except Exception:
            if conn is not None:
                conn.rollback()
            raise
        finally:
            if cur is not None:
                cur.close()

    @contextmanager
    def transaction(self):
        """
        显式事务上下文。

        示例:
            with conn.transaction() as cur:
                cur.execute('INSERT INTO t VALUES (1)')
                cur.execute('INSERT INTO t VALUES (2)')
        """
        conn = self._get_connection()
        cur = conn.cursor()
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

    def close(self) -> None:
        """关闭数据库连接。"""
        if self._connection is not None and not self._connection.closed:
            self._connection.close()
            logger.debug('PostgreSQL 连接已关闭')

    def __enter__(self):
        """支持 with 语句。"""
        self._get_connection()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出 with 语句时关闭连接。"""
        self.close()
        return False

    def __repr__(self) -> str:
        return (
            f'PostgreSQLConnection(host={self._host!r}, port={self._port}, '
            f'user={self._user!r}, database={self._database!r})'
        )