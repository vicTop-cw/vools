"""
vools.sql.core.connection - 数据库连接抽象基类

定义数据库连接的抽象基类，遵循 PEP 249 DB API 2.0 规范，
为不同数据库方言提供统一的连接管理接口。
"""

import abc
from typing import Any, Optional, Sequence


class Connection(abc.ABC):
    """
    数据库连接抽象基类

    定义了数据库连接的标准接口，包括连接管理、SQL 执行、
    事务控制等功能。具体数据库驱动的连接类需继承此类并实现
    所有抽象方法。

    用法：
        conn = ConcreteConnection(host='localhost', port=3306)
        conn.connect(user='root', password='pass', database='test')
        result = conn.execute('SELECT * FROM users WHERE id = %s', (1,))
        conn.commit()
        conn.close()

    上下文管理器用法：
        with ConcreteConnection(...) as conn:
            conn.execute(...)
    """

    _connected: bool = False
    _conn = None

    @abc.abstractmethod
    def connect(self, **kwargs: Any) -> None:
        """
        建立数据库连接

        使用指定的连接参数建立与数据库的连接，
        连接成功后将 _connected 标记为 True。

        参数：
            **kwargs: 连接参数，如 host, port, user, password, database 等，
                      具体参数由各驱动实现决定
        """
        ...

    @abc.abstractmethod
    def close(self) -> None:
        """
        关闭数据库连接

        关闭当前数据库连接，释放相关资源。
        关闭后将 _connected 标记为 False。
        若连接已关闭，则不执行任何操作。
        """
        ...

    @abc.abstractmethod
    def execute(self, sql: str, params: Optional[Sequence] = None) -> 'ResultSet':
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
        ...

    @abc.abstractmethod
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
        ...

    @abc.abstractmethod
    def commit(self) -> None:
        """
        提交事务

        将当前事务中的所有修改提交到数据库。
        若数据库不支持事务或处于自动提交模式，则此方法可能为空操作。
        """
        ...

    @abc.abstractmethod
    def rollback(self) -> None:
        """
        回滚事务

        撤销当前事务中的所有修改，回滚到事务开始前的状态。
        若数据库不支持事务，则此方法可能为空操作或抛出异常。
        """
        ...

    @abc.abstractmethod
    def cursor(self) -> object:
        """
        获取游标对象

        返回底层数据库驱动的游标对象，
        用于执行更底层的数据库操作。

        返回：
            底层驱动的游标对象
        """
        ...

    @property
    def is_connected(self) -> bool:
        """
        检查连接是否已建立

        返回：
            True 表示连接已建立，False 表示连接未建立或已关闭
        """
        return self._connected

    def __enter__(self) -> 'Connection':
        """
        上下文管理器入口

        支持 with 语句使用连接对象。
        若连接尚未建立，自动调用 connect() 建立连接。

        返回：
            Connection 实例自身
        """
        if not self._connected:
            self.connect()
        return self

    def __exit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional[object],
    ) -> bool:
        """
        上下文管理器退出

        退出 with 语句块时的清理操作：
        - 若发生异常，则回滚事务
        - 若无异常，则提交事务
        - 最后关闭连接

        参数：
            exc_type: 异常类型，无异常时为 None
            exc_val: 异常实例，无异常时为 None
            exc_tb: 异常追踪对象，无异常时为 None

        返回：
            False 表示不抑制异常，异常会继续向上传播
        """
        try:
            if exc_type is not None:
                self.rollback()
            else:
                self.commit()
        finally:
            self.close()
        return False

    def __del__(self) -> None:
        """
        析构方法

        对象被垃圾回收时自动关闭连接，
        防止资源泄漏。
        """
        try:
            if self._connected:
                self.close()
        except Exception:
            pass
