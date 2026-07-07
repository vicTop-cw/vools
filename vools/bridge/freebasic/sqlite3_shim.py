"""
vools.bridge.freebasic.sqlite3_shim - SQLite3 FreeBASIC 桥接 Python shim

提供 SQLite3 数据库操作，通过 ctypes 加载编译好的 FreeBASIC SQLite3 DLL。
如果 DLL 不可用，回退到 Python 标准库 sqlite3 实现。
"""

import ctypes
import sqlite3 as _py_sqlite3

from .loader import get_fb_lib


def _load_lib():
    """加载 SQLite3 共享库"""
    try:
        lib = get_fb_lib('sqlite3', 'database')
        if lib is None:
            return None
        lib.sqlite3_libversion.restype = ctypes.c_char_p
        return lib
    except Exception:
        return None


_lib = _load_lib()


def sqlite3_version():
    """
    获取 SQLite3 版本字符串

    Returns:
        SQLite3 版本字符串，如 "3.26.0"
    """
    if _lib is not None:
        try:
            result = _lib.sqlite3_libversion()
            if result:
                return result.decode('utf-8')
        except Exception:
            pass
    return _py_sqlite3.sqlite_version


def is_sqlite3_available():
    """检查 SQLite3 DLL 是否可用"""
    return _lib is not None


class Cursor:
    """
    SQLite3 游标对象

    封装 Python 标准库 sqlite3.Cursor，提供统一的接口。
    """

    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, sql, params=None):
        """
        执行 SQL 语句

        Args:
            sql: SQL 语句
            params: 可选参数元组或列表

        Returns:
            Cursor 对象自身
        """
        if params is None:
            self._cursor.execute(sql)
        else:
            self._cursor.execute(sql, params)
        return self

    def fetchone(self):
        """获取下一行结果"""
        return self._cursor.fetchone()

    def fetchall(self):
        """获取所有结果行"""
        return self._cursor.fetchall()

    def fetchmany(self, size=None):
        """
        获取多行结果

        Args:
            size: 要获取的行数，默认为 arraysize

        Returns:
            结果行列表
        """
        if size is None:
            return self._cursor.fetchmany()
        return self._cursor.fetchmany(size)

    def close(self):
        """关闭游标"""
        self._cursor.close()

    @property
    def description(self):
        """列描述信息"""
        return self._cursor.description

    @property
    def rowcount(self):
        """受影响的行数"""
        return self._cursor.rowcount

    def __iter__(self):
        return iter(self._cursor)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


class Connection:
    """
    SQLite3 数据库连接对象

    封装 Python 标准库 sqlite3.Connection，提供统一的接口。
    """

    def __init__(self, connection):
        self._conn = connection

    def execute(self, sql, params=None):
        """
        执行 SQL 语句

        Args:
            sql: SQL 语句
            params: 可选参数元组或列表

        Returns:
            Cursor 对象
        """
        if params is None:
            cursor = self._conn.execute(sql)
        else:
            cursor = self._conn.execute(sql, params)
        return Cursor(cursor)

    def commit(self):
        """提交事务"""
        self._conn.commit()

    def rollback(self):
        """回滚事务"""
        self._conn.rollback()

    def close(self):
        """关闭数据库连接"""
        self._conn.close()

    def cursor(self):
        """创建一个新的游标"""
        return Cursor(self._conn.cursor())

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


def connect(database):
    """
    打开 SQLite3 数据库连接

    Args:
        database: 数据库文件路径，或 ':memory:' 表示内存数据库

    Returns:
        Connection 对象
    """
    conn = _py_sqlite3.connect(database)
    return Connection(conn)
