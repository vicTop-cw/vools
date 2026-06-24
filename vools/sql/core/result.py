"""
vools.sql.core.result - 查询结果集抽象

提供 Row 和 ResultSet 类，封装数据库查询结果，
支持多种访问方式（列名、属性、索引）和便捷的结果处理方法。
"""

from typing import List, Tuple, Dict, Any, Iterator, Optional, Union

from .types import SqlTypeMapper


class Row:
    """
    表示一行数据

    支持多种访问方式：
    - 列名访问：row['column_name']
    - 属性访问：row.column_name
    - 索引访问：row[0]
    - 迭代支持：for value in row

    属性：
        _columns: 列名列表
        _values: 值元组
    """

    __slots__ = ('_columns', '_values')

    def __init__(self, columns: List[str], values: Tuple[Any, ...]):
        """
        初始化 Row 对象

        参数：
            columns: 列名列表
            values: 值元组
        """
        object.__setattr__(self, '_columns', columns)
        object.__setattr__(self, '_values', values)

    def __getitem__(self, key: Union[str, int, slice]) -> Any:
        """
        通过列名或索引访问值

        参数：
            key: 列名（字符串）、索引（整数）或切片

        返回：
            对应的值

        抛出：
            KeyError: 列名不存在
            IndexError: 索引越界
        """
        if isinstance(key, str):
            try:
                idx = self._columns.index(key)
            except ValueError:
                raise KeyError(f"Column '{key}' not found")
            return self._values[idx]
        elif isinstance(key, (int, slice)):
            return self._values[key]
        else:
            raise TypeError(f"Invalid key type: {type(key)}")

    def __getattr__(self, name: str) -> Any:
        """
        通过属性访问列值

        参数：
            name: 列名

        返回：
            对应的值

        抛出：
            AttributeError: 列名不存在
        """
        try:
            return self[name]
        except KeyError:
            raise AttributeError(f"'Row' object has no attribute '{name}'")

    def __setattr__(self, name: str, value: Any) -> None:
        """
        禁止设置属性，保持 Row 不可变

        参数：
            name: 属性名
            value: 属性值

        抛出：
            AttributeError: Row 对象不可变
        """
        raise AttributeError("Row object is immutable")

    def __iter__(self) -> Iterator[Any]:
        """
        迭代行中的值

        返回：
            值迭代器
        """
        return iter(self._values)

    def __len__(self) -> int:
        """
        返回列数

        返回：
            列的数量
        """
        return len(self._columns)

    def __contains__(self, key: str) -> bool:
        """
        检查列是否存在

        参数：
            key: 列名

        返回：
            True 表示列存在，False 表示不存在
        """
        return key in self._columns

    def __eq__(self, other: Any) -> bool:
        """
        判断两个 Row 是否相等

        参数：
            other: 另一个对象

        返回：
            True 表示相等，False 表示不相等
        """
        if not isinstance(other, Row):
            return False
        return self._columns == other._columns and self._values == other._values

    def __repr__(self) -> str:
        """
        返回友好的字符串表示

        返回：
            Row 的字符串表示
        """
        items = ", ".join(f"{k}={v!r}" for k, v in zip(self._columns, self._values))
        return f"Row({items})"

    def keys(self) -> List[str]:
        """
        返回列名列表

        返回：
            列名列表
        """
        return list(self._columns)

    def values(self) -> Tuple[Any, ...]:
        """
        返回值元组

        返回：
            值元组
        """
        return self._values

    def items(self) -> List[Tuple[str, Any]]:
        """
        返回 (key, value) 对列表

        返回：
            (列名, 值) 对列表
        """
        return list(zip(self._columns, self._values))

    def as_dict(self) -> Dict[str, Any]:
        """
        转为字典

        返回：
            列名到值的字典映射
        """
        return dict(zip(self._columns, self._values))

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取列值，不存在时返回默认值

        参数：
            key: 列名
            default: 默认值

        返回：
            列值或默认值
        """
        try:
            return self[key]
        except KeyError:
            return default


class ResultSet:
    """
    封装查询结果集

    提供类游标接口（fetchone/fetchmany/fetchall）以及
    便捷的结果处理方法（first/scalar/to_list/to_dataframe）。

    属性：
        _columns: 列名列表
        _rows: 行数据列表
        _rowcount: 受影响行数
        _cursor: 当前游标位置
        _type_mapper: 类型映射器（可选）
    """

    def __init__(
        self,
        columns: List[str],
        rows: Optional[List[Tuple[Any, ...]]] = None,
        rowcount: int = 0,
        type_mapper: Optional[SqlTypeMapper] = None,
    ):
        """
        初始化 ResultSet

        参数：
            columns: 列名列表
            rows: 行数据列表（元组列表），默认为 None
            rowcount: 受影响行数，默认为 0
            type_mapper: 类型映射器，默认为 None
        """
        self._columns = list(columns)
        self._rowcount = rowcount
        self._cursor = 0
        self._type_mapper = type_mapper

        if rows is None:
            self._rows = []
        else:
            self._rows = [Row(self._columns, tuple(row)) for row in rows]

    def __iter__(self) -> Iterator[Row]:
        """
        迭代所有行

        返回：
            行迭代器
        """
        return iter(self._rows)

    def __len__(self) -> int:
        """
        返回行数

        返回：
            行的数量
        """
        return len(self._rows)

    def __getitem__(self, index: Union[int, slice]) -> Union[Row, List[Row]]:
        """
        通过索引访问行

        参数：
            index: 索引或切片

        返回：
            行对象或行列表

        抛出：
            IndexError: 索引越界
        """
        return self._rows[index]

    def __contains__(self, row: Row) -> bool:
        """
        检查行是否在结果集中

        参数：
            row: 行对象

        返回：
            True 表示存在，False 表示不存在
        """
        return row in self._rows

    def __repr__(self) -> str:
        """
        返回字符串表示

        返回：
            ResultSet 的字符串表示
        """
        return f"ResultSet(columns={self._columns!r}, rows={len(self._rows)}, rowcount={self._rowcount})"

    @property
    def columns(self) -> List[str]:
        """
        返回列名列表

        返回：
            列名列表
        """
        return list(self._columns)

    @property
    def rowcount(self) -> int:
        """
        返回受影响行数

        对于 SELECT 语句，通常为 -1 或匹配的行数，
        对于 INSERT/UPDATE/DELETE 语句，为受影响的行数。

        返回：
            受影响行数
        """
        return self._rowcount

    def fetchone(self) -> Optional[Row]:
        """
        获取下一行

        返回：
            下一行对象，如果没有更多行则返回 None
        """
        if self._cursor >= len(self._rows):
            return None
        row = self._rows[self._cursor]
        self._cursor += 1
        return row

    def fetchmany(self, size: Optional[int] = None) -> List[Row]:
        """
        获取多行

        参数：
            size: 获取的行数，默认为 1

        返回：
            行对象列表
        """
        if size is None:
            size = 1
        if size <= 0:
            return []
        start = self._cursor
        end = min(start + size, len(self._rows))
        rows = self._rows[start:end]
        self._cursor = end
        return rows

    def fetchall(self) -> List[Row]:
        """
        获取所有剩余行

        返回：
            所有剩余行的列表
        """
        rows = self._rows[self._cursor:]
        self._cursor = len(self._rows)
        return rows

    def first(self) -> Optional[Row]:
        """
        获取第一行

        返回：
            第一行对象，如果没有行则返回 None
        """
        if not self._rows:
            return None
        return self._rows[0]

    def scalar(self) -> Any:
        """
        获取第一行第一列的值

        常用于 COUNT、SUM 等聚合查询。

        返回：
            第一行第一列的值，如果没有行则返回 None
        """
        row = self.first()
        if row is None:
            return None
        return row[0]

    def to_list(self) -> List[Dict[str, Any]]:
        """
        转为字典列表

        返回：
            字典列表，每个字典代表一行
        """
        return [row.as_dict() for row in self._rows]

    def to_dataframe(self) -> Any:
        """
        转为 pandas DataFrame

        如果 pandas 不可用，则抛出 ImportError。

        返回：
            pandas DataFrame 对象

        抛出：
            ImportError: pandas 未安装
        """
        try:
            import pandas as pd
        except ImportError:
            raise ImportError("pandas is required for to_dataframe(), please install it first")
        return pd.DataFrame(self.to_list(), columns=self._columns)

    def reset_cursor(self) -> None:
        """
        重置游标位置到开头
        """
        self._cursor = 0

    def __bool__(self) -> bool:
        """
        判断结果集是否非空

        返回：
            True 表示有行，False 表示无行
        """
        return len(self._rows) > 0
