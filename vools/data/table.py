"""
二维表格数据结构

提供轻量级的二维表格数据结构，与 pandas DataFrame 互补。

设计理念:
1. 轻量简洁，无外部依赖
2. 链式操作风格 (继承 Seq 设计理念)
3. 与 vools.xl 模块深度集成
4. 与 pandas DataFrame 互转便捷
5. 借鉴 QAX 数据集 API 设计，提供 60+ 便捷方法

使用场景:
- 小型数据分析 (<100万行)
- Excel 数据处理
- 数据管道构建

QAX 风格 API:
- 创建: new(), from_array(), from_file(), from_range()
- 访问: get_cell(), set_cell(), get_row(), get_col()
- 修改: add_row(), add_col(), del_row(), del_col(), update()
- 转换: to_array(), to_file(), to_dataframe()
- 数据操作: where(), select(), order_by(), group_by(), join(), merge()
- 聚合: sum(), avg(), count(), min(), max()
"""

from typing import List, Dict, Any, Callable, Optional, Iterator, Tuple, Union, TYPE_CHECKING
from collections import OrderedDict
from copy import copy
import os
import re
import csv
from datetime import datetime

from .seq import Seq
from ..decorators import rself

__all__ = ['Table', 'Row', 'Column']


@rself
class Row(Seq):
    """Table 的一行对象 (用于行级操作)
    
    示例::
    
        table = Table([...])
        row = table.get_row(0)
        print(row['name'])  # 访问单元格
        row['age'] = 26    # 修改单元格
        row['new_col'] = 'value'  # 添加新列
        
        # Seq 风格操作
        row.map(str).filter(lambda x: x)
    """
    
    def __init__(self, *args, **kwargs):
        self._table = None
        self._row_index = 0
        self._data = []
        
        def _is_table(obj):
            return hasattr(obj, '_columns') and hasattr(obj, '_data')
        
        if len(args) == 2 and _is_table(args[0]):
            self._table = args[0]
            self._row_index = args[1]
            if self._table and self._row_index < len(self._table._data):
                self._data = self._table._data[self._row_index]
        elif len(args) == 1 and isinstance(args[0], (list, tuple, Iterator, Seq)) and not _is_table(args[0]):
            self._data = list(args[0])
            self._table = kwargs.get('table')
            self._row_index = kwargs.get('row_index', 0)
        else:
            self._table = kwargs.get('table')
            self._row_index = kwargs.get('row_index', 0)
            if self._table and self._row_index < len(self._table._data):
                self._data = self._table._data[self._row_index]
        
        super().__init__(self._data)
        self._rself_kwargs = {'table': self._table, 'row_index': self._row_index}
    
    @classmethod
    def __from_parent__(cls, parent_val, **kwargs):
        """从父类（Seq）实例创建 Row 实例
        
        Args:
            parent_val: 父类实例（序列数据）
            **kwargs: 包含 table 和 row_index
            
        Returns:
            Row 实例
        """
        table = kwargs.get('table')
        row_index = kwargs.get('row_index', 0)
        row_data = list(parent_val)
        return cls(row_data, table=table, row_index=row_index)
    
    def __getitem__(self, key):
        if isinstance(key, slice):
            return Row(self._data[key], table=self._table, row_index=self._row_index)
        if isinstance(key, int):
            return self._data[key]
        return self._table.at(self._row_index, key)
    
    def __setitem__(self, key, value):
        if isinstance(key, int):
            self._data[key] = value
            if self._table and self._row_index < len(self._table._data):
                self._table._data[self._row_index][key] = value
        else:
            self._table.set_cell(self._row_index, key, value)
    
    def __len__(self):
        return len(self._data)
    
    def __iter__(self):
        return iter(self._data)
    
    def __repr__(self):
        return f'Row({self._row_index})'
    
    def to_dict(self) -> Dict[str, Any]:
        """转为字典"""
        if self._table:
            return self._table.row(self._row_index)
        return dict(zip(['col_%d' % i for i in range(len(self._data))], self._data))
    
    def index(self) -> int:
        """行索引"""
        return self._row_index
    
    def table(self) -> 'Table':
        """所属表格"""
        return self._table
    
    def map(self, func=None):
        """映射操作（立即求值，返回新 Row）"""
        if func is None:
            for v in self._data:
                print(v)
            return None
        result = [func(v) for v in self._data]
        return Row(result, table=self._table, row_index=self._row_index)
    
    def filter(self, func=bool):
        """过滤操作（立即求值，返回新 Row）"""
        result = [v for v in self._data if func(v)]
        return Row(result, table=self._table, row_index=self._row_index)
    
    def where(self, func):
        """LINQ 风格过滤（filter 的别名）"""
        return self.filter(func)
    
    def filterfalse(self, func=bool):
        """反向过滤操作（立即求值，返回新 Row）"""
        result = [v for v in self._data if not func(v)]
        return Row(result, table=self._table, row_index=self._row_index)
    
    def wherenot(self, func):
        """LINQ 风格反向过滤"""
        return self.filterfalse(func)
    
    def select(self, func):
        """LINQ 风格映射（map 的别名）"""
        return self.map(func)
    
    def take(self, n):
        """取前 n 个元素"""
        result = self._data[:n]
        return Row(result, table=self._table, row_index=self._row_index)
    
    def skip(self, n):
        """跳过前 n 个元素"""
        result = self._data[n:]
        return Row(result, table=self._table, row_index=self._row_index)
    
    def reverse(self):
        """反转元素顺序"""
        result = self._data[::-1]
        return Row(result, table=self._table, row_index=self._row_index)
    
    def collect(self):
        """物化为列表"""
        return list(self._data)
    
    def to_list(self):
        """转为列表"""
        return list(self._data)


@rself
class Column(Seq):
    """Table 的一列对象 (用于列级操作)
    
    示例::
    
        table = Table([...])
        col = table.get_col('age')
        print(col[0])       # 访问第0行的单元格
        col[0] = 26        # 修改第0行的单元格
        print(col.sum())    # 求和
        print(col.name())   # 列名
        
        # Seq 风格操作
        col.map(str).filter(lambda x: x)
    """
    
    def __init__(self, *args, **kwargs):
        self._table = None
        self._col_index = 0
        self._col_name = ''
        self._data = []
        
        def _is_table(obj):
            return hasattr(obj, '_columns') and hasattr(obj, '_data')
        
        if len(args) == 2 and _is_table(args[0]):
            self._table = args[0]
            col = args[1]
            self._col_index = self._table._get_col_index(col)
            self._col_name = self._table._columns[self._col_index]
            self._data = [row[self._col_index] for row in self._table._data]
        elif len(args) == 1 and isinstance(args[0], (list, tuple, Iterator, Seq)) and not _is_table(args[0]):
            self._data = list(args[0])
            self._table = kwargs.get('table')
            self._col_index = kwargs.get('col_index', 0)
            self._col_name = kwargs.get('col_name', '')
        else:
            self._table = kwargs.get('table')
            self._col_index = kwargs.get('col_index', 0)
            self._col_name = kwargs.get('col_name', '')
            if self._table:
                self._col_index = self._table._get_col_index(self._col_index)
                self._col_name = self._table._columns[self._col_index]
                self._data = [row[self._col_index] for row in self._table._data]
        
        super().__init__(self._data)
        self._rself_kwargs = {'table': self._table, 'col_index': self._col_index, 'col_name': self._col_name}
    
    @classmethod
    def __from_parent__(cls, parent_val, **kwargs):
        """从父类（Seq）实例创建 Column 实例
        
        Args:
            parent_val: 父类实例（序列数据）
            **kwargs: 包含 table、col_index、col_name
            
        Returns:
            Column 实例
        """
        table = kwargs.get('table')
        col_index = kwargs.get('col_index', 0)
        col_name = kwargs.get('col_name', '')
        col_data = list(parent_val)
        return cls(col_data, table=table, col_index=col_index, col_name=col_name)
    
    def __getitem__(self, key):
        if isinstance(key, slice):
            return Column([self._data[i] for i in range(*key.indices(len(self._data)))],
                          table=self._table, col_index=self._col_index, col_name=self._col_name)
        if isinstance(key, int):
            return self._data[key]
        return self._table.at(key, self._col_index) if self._table else None
    
    def __setitem__(self, key, value):
        if isinstance(key, int):
            self._data[key] = value
            if self._table and key < len(self._table._data):
                self._table._data[key][self._col_index] = value
        elif self._table:
            self._table.set_cell(key, self._col_index, value)
    
    def __len__(self):
        return len(self._data)
    
    def __iter__(self):
        return iter(self._data)
    
    def __repr__(self):
        return f'Column({self._col_name})'
    
    def name(self) -> str:
        """列名"""
        return self._col_name
    
    def index(self) -> int:
        """列索引"""
        return self._col_index
    
    def table(self) -> 'Table':
        """所属表格"""
        return self._table
    
    def to_list(self) -> List[Any]:
        """转为列表"""
        return list(self._data)
    
    def sum(self) -> Union[int, float]:
        """求和 (仅数字)"""
        vals = [v for v in self._data if isinstance(v, (int, float))]
        return sum(vals)
    
    def avg(self) -> Union[int, float]:
        """平均值 (仅数字)"""
        vals = [v for v in self._data if isinstance(v, (int, float))]
        return sum(vals) / len(vals) if vals else 0
    
    def min(self) -> Any:
        """最小值"""
        vals = [v for v in self._data if v is not None]
        return min(vals) if vals else None
    
    def max(self) -> Any:
        """最大值"""
        vals = [v for v in self._data if v is not None]
        return max(vals) if vals else None
    
    def count(self) -> int:
        """非空值数量"""
        vals = [v for v in self._data if v is not None]
        return len(vals)
    
    def distinct(self) -> List[Any]:
        """去重后的列表"""
        seen = []
        for v in self._data:
            if v not in seen:
                seen.append(v)
        return seen
    
    def map(self, func=None):
        """映射操作（立即求值，返回新 Column）"""
        if func is None:
            for v in self._data:
                print(v)
            return None
        result = [func(v) for v in self._data]
        return Column(result, table=self._table, col_index=self._col_index, col_name=self._col_name)
    
    def filter(self, func=bool):
        """过滤操作（立即求值，返回新 Column）"""
        result = [v for v in self._data if func(v)]
        return Column(result, table=self._table, col_index=self._col_index, col_name=self._col_name)
    
    def where(self, func):
        """LINQ 风格过滤（filter 的别名）"""
        return self.filter(func)
    
    def filterfalse(self, func=bool):
        """反向过滤操作（立即求值，返回新 Column）"""
        result = [v for v in self._data if not func(v)]
        return Column(result, table=self._table, col_index=self._col_index, col_name=self._col_name)
    
    def wherenot(self, func):
        """LINQ 风格反向过滤"""
        return self.filterfalse(func)
    
    def select(self, func):
        """LINQ 风格映射（map 的别名）"""
        return self.map(func)
    
    def take(self, n):
        """取前 n 个元素"""
        result = self._data[:n]
        return Column(result, table=self._table, col_index=self._col_index, col_name=self._col_name)
    
    def skip(self, n):
        """跳过前 n 个元素"""
        result = self._data[n:]
        return Column(result, table=self._table, col_index=self._col_index, col_name=self._col_name)
    
    def reverse(self):
        """反转元素顺序"""
        result = self._data[::-1]
        return Column(result, table=self._table, col_index=self._col_index, col_name=self._col_name)
    
    def collect(self):
        """物化为列表"""
        return list(self._data)


@rself
class Table(Seq):
    """二维表格数据结构

    示例::

        from vools.data import Table

        # 创建表格
        table = Table([
            ['Alice', 25, 'New York'],
            ['Bob', 30, 'Los Angeles'],
            ['Charlie', 35, 'Chicago'],
        ], columns=['name', 'age', 'city'])

        # 访问数据
        print(table.rows())      # 3
        print(table.cols())     # 3
        print(table.at(0, 0))   # 'Alice'
        print(table.column('name'))  # ['Alice', 'Bob', 'Charlie']

        # 链式操作
        table.filter(lambda r: r['age'] > 25) \
             .select('name', 'city') \
             .foreach(print)

        # Excel 读写
        table.write_excel('output.xlsx')
        table2 = Table.read_excel('input.xlsx')

        # 与 pandas 互转
        df = table.to_dataframe()
        table3 = Table.from_dataframe(df)
    """

    def __init__(self, data: List[List[Any]] = None,
                 columns: List[str] = None, name: str = None):
        """创建表格

        Args:
            data: 二维列表数据
            columns: 列名列表
            name: 表格名称
        """
        super().__init__()
        data = data or []
        self._collection = list(data)
        self._last = len(self._collection) - 1
        self._current = -1
        self._origin = iter([])
        self._ops = []
        self._active_op = lambda x: x
        
        self._columns = columns or [f'col_{i}' for i in range(len(self._collection[0]) if self._collection else 0)]
        self._row_index = {}
        self._name = name or ''
        self._rself_kwargs = {'columns': list(self._columns), 'name': self._name}
    
    @property
    def _data(self):
        return self._collection
    
    @_data.setter
    def _data(self, value):
        self._collection = list(value)
        self._last = len(self._collection) - 1
        self._current = -1
        self._origin = iter([])
        self._ops = []
        self._active_op = lambda x: x
    
    @classmethod
    def __from_parent__(cls, parent_val, **kwargs):
        """从父类（Seq）实例创建 Table 实例
        
        Args:
            parent_val: 父类实例（序列数据）
            **kwargs: 包含 columns 和 name
            
        Returns:
            Table 实例
        """
        columns = kwargs.get('columns', None)
        name = kwargs.get('name', '')
        data = list(parent_val)
        
        if data and isinstance(data[0], dict):
            if columns is None:
                columns = list(data[0].keys())
            data = [[row.get(c) for c in columns] for row in data]
        
        return cls(data, columns=columns, name=name)
    
    # ==================== QAX 风格创建方法 ====================
    
    @classmethod
    def new(cls, name: str = None) -> 'Table':
        """创建空表格 (对应 QAX())
        
        Returns:
            空 Table
        """
        return cls(name=name)
    
    @classmethod
    def from_array(cls, arr, fields_name=None, data_type=None) -> 'Table':
        """从数组创建 (对应 ArrayToQax)
        
        Args:
            arr: 二维数组或一维数组
            fields_name: 列名列表
            data_type: 列类型 (暂未实现)
        
        Returns:
            Table 实例
        """
        if not arr:
            return cls(name=fields_name)
        
        # 展平一维数组
        if not isinstance(arr[0], (list, tuple)):
            arr = [[v] for v in arr]
        
        columns = list(fields_name) if fields_name else None
        return cls(arr, columns=columns, name=fields_name if isinstance(fields_name, str) else None)
    
    @classmethod
    def from_file(cls, filepath: str, delimiter: str = ',', 
                  encoding: str = 'utf-8', rows: int = None,
                  cols=None, types=None, name: str = None) -> 'Table':
        """从 CSV/TXT 文件创建 (对应 FileToQax)
        
        Args:
            filepath: 文件路径
            delimiter: 列分隔符
            encoding: 文件编码
            rows: 最大行数
            cols: 要读取的列索引
            types: 列类型 (暂未实现)
            name: 表格名称
        
        Returns:
            Table 实例
        """
        data = []
        columns = None
        
        with open(filepath, 'r', encoding=encoding) as f:
            reader = csv.reader(f, delimiter=delimiter)
            for i, row in enumerate(reader):
                if rows and i >= rows:
                    break
                if i == 0:
                    columns = [str(c) if c else f'col_{j}' for j, c in enumerate(row)]
                    if cols:
                        row = [row[j] if j < len(row) else '' for j in cols]
                    else:
                        row = row
                else:
                    if cols:
                        row = [row[j] if j < len(row) else '' for j in cols]
                    else:
                        row = row
                data.append(row)
        
        # 处理列
        if columns and cols:
            columns = [columns[j] if j < len(columns) else f'col_{j}' for j in cols]
        
        return cls(data, columns=columns, name=name)
    
    @classmethod
    def from_dicts(cls, dicts: List[Dict[str, Any]],
                   columns: List[str] = None, name: str = None) -> 'Table':
        """从字典列表创建 (增强版)
        
        Args:
            dicts: 字典列表
            columns: 列名列表 (可选)
            name: 表格名称
        
        Returns:
            Table 实例
        """
        if not dicts:
            return cls(name=name)
        
        if columns is None:
            columns = list(dicts[0].keys())
        
        data = [
            [d.get(c) for c in columns]
            for d in dicts
        ]
        return cls(data, columns=columns, name=name)
    
    @classmethod
    def from_dataframe(cls, df, name: str = None) -> 'Table':
        """从 pandas DataFrame 创建
        
        Args:
            df: pandas DataFrame
            name: 表格名称
        
        Returns:
            Table 实例
        """
        columns = list(df.columns)
        data = df.values.tolist()
        return cls(data, columns=columns, name=name)

    # ==================== 属性 ====================

    def rows(self) -> int:
        """行数 (对应 QAXRows)"""
        return len(self._data)
    
    def cols(self) -> int:
        """列数 (对应 QAXCols)"""
        return len(self._columns)
    
    def columns(self) -> List[str]:
        """列名列表 (对应 QAXColNames)"""
        return list(self._columns)
    
    def name(self) -> str:
        """表格名称 (对应 QAXName)"""
        return self._name
    
    def set_name(self, name: str) -> 'Table':
        """设置表格名称 (对应 SetQaxName)
        
        Returns:
            self (支持链式)
        """
        self._name = name
        return self
    
    def is_empty(self) -> bool:
        """是否为空"""
        return len(self._data) == 0

    # ==================== 数据访问 (QAX 风格) ====================

    def at(self, row: int, col: Union[int, str]) -> Any:
        """按行列访问单个元素

        Args:
            row: 行索引 (从0开始)
            col: 列索引或列名

        Returns:
            元素值
        """
        row_data = self._data[row]
        col_idx = self._get_col_index(col)
        return row_data[col_idx]
    
    def get_cell(self, row_index: int, col_index: int, 
                 default_value=None, null_value=None) -> Any:
        """获取单元格值 (对应 GetCell)
        
        Args:
            row_index: 行索引 (从0开始)
            col_index: 列索引
            default_value: 默认值 (当值为空时返回)
            null_value: 空值 (当值为 null_value 时返回默认值)
        
        Returns:
            单元格值
        """
        if row_index < 0 or row_index >= len(self._data):
            return default_value
        
        row = self._data[row_index]
        if col_index < 0 or col_index >= len(row):
            return default_value
        
        value = row[col_index]
        if value is None or value == null_value:
            return default_value
        return value
    
    def get_cell2(self, row_index: int, col_name: str,
                  default_value=None, null_value=None) -> Any:
        """获取单元格值 (按列名) (对应 GetCell2)
        
        Args:
            row_index: 行索引 (从0开始)
            col_name: 列名
            default_value: 默认值
            null_value: 空值
        
        Returns:
            单元格值
        """
        col_index = self._columns.index(col_name) if col_name in self._columns else -1
        if col_index < 0:
            return default_value
        return self.get_cell(row_index, col_index, default_value, null_value)
    
    def set_cell(self, row_index: int, col_index: Union[int, str], value: Any) -> 'Table':
        """设置单元格值 (对应 SetCell)
        
        Args:
            row_index: 行索引 (从0开始)
            col_index: 列索引或列名
            value: 要设置的值
        
        Returns:
            self (支持链式)
        """
        # 确保有足够的行
        while len(self._data) <= row_index:
            self._data.append([None] * len(self._columns))
        
        # 确保有足够的列
        if isinstance(col_index, str):
            col_idx = self._columns.index(col_index) if col_index in self._columns else -1
            if col_idx < 0:
                # 添加新列
                col_idx = len(self._columns)
                self._columns.append(col_index)
                for row in self._data:
                    row.append(None)
        else:
            col_idx = col_index
            while len(self._data[row_index]) <= col_idx:
                self._data[row_index].append(None)
        
        self._data[row_index][col_idx] = value
        return self
    
    def set_cell2(self, row_index: int, col_name: str, value: Any) -> 'Table':
        """设置单元格值 (按列名) (对应 SetCell2)
        
        Returns:
            self (支持链式)
        """
        return self.set_cell(row_index, col_name, value)

    def row(self, i: int) -> Dict[str, Any]:
        """获取一行数据

        Args:
            i: 行索引 (从0开始)

        Returns:
            字典形式的一行数据
        """
        row_data = self._data[i]
        return dict(zip(self._columns, row_data))
    
    def get_row(self, rownum: int) -> Row:
        """获取一行对象 (对应 GetRow，返回 Row 对象)
        
        Args:
            rownum: 行索引 (从0开始)
        
        Returns:
            Row 对象
        """
        return Row(self, rownum)
    
    def del_row(self, rownum: int) -> 'Table':
        """删除行 (对应 DelRow)
        
        Args:
            rownum: 行索引
        
        Returns:
            self (支持链式)
        """
        if 0 <= rownum < len(self._data):
            self._data.pop(rownum)
        return self
    
    def new_row(self) -> Row:
        """创建新行 (对应 NewRow)
        
        Returns:
            Row 对象
        """
        self._data.append([None] * len(self._columns))
        return Row(self, len(self._data) - 1)

    def column(self, name: Union[str, int]) -> List[Any]:
        """获取一列数据

        Args:
            name: 列名或列索引

        Returns:
            列表形式的一列数据
        """
        col_idx = self._get_col_index(name)
        return [row[col_idx] for row in self._data]
    
    def get_col(self, col) -> 'Column':
        """获取一列对象 (对应 GetCol)
        
        Args:
            col: 列名或列索引
        
        Returns:
            Column 对象
        """
        return Column(self, col)
    
    def get_cols(self, distinct: bool = False, col_names: List[str] = None) -> 'Table':
        """获取多列数据 (对应 GetCols)
        
        Args:
            distinct: 是否去重
            col_names: 要获取的列名列表
        
        Returns:
            新的 Table
        """
        if col_names is None:
            col_names = list(self._columns)
        
        result = self.select(*col_names)
        if distinct:
            result = result.distinct()
        return result
    
    def del_col(self, col) -> 'Table':
        """删除列 (对应 DelCol)
        
        Args:
            col: 列名或列索引
        
        Returns:
            self (支持链式)
        """
        col_idx = self._get_col_index(col)
        col_name = self._columns[col_idx]
        
        # 删除列名
        self._columns.pop(col_idx)
        
        # 删除数据
        for row in self._data:
            if col_idx < len(row):
                row.pop(col_idx)
        
        # 清除索引缓存
        self._row_index.clear()
        
        return self
    
    def add_col(self, col_name: str, default_value: Any = None) -> 'Table':
        """添加新列 (对应 NewCol)
        
        Args:
            col_name: 列名
            default_value: 默认值
        
        Returns:
            self (支持链式)
        """
        self._columns.append(col_name)
        for row in self._data:
            row.append(default_value)
        return self
    
    def set_col_name(self, col_num: int, new_col_name: str) -> 'Table':
        """修改列名 (对应 SetColName)
        
        Args:
            col_num: 列索引 (从0开始)
            new_col_name: 新列名
        
        Returns:
            self (支持链式)
        """
        if 0 <= col_num < len(self._columns):
            self._columns[col_num] = new_col_name
            self._row_index.clear()
        return self
    
    def set_ordinal(self, col_name: str, ordinal: int) -> 'Table':
        """修改列位置 (对应 SetOrdinal)
        
        Args:
            col_name: 列名
            ordinal: 新位置 (从0开始)
        
        Returns:
            self (支持链式)
        """
        if col_name not in self._columns:
            return self
        
        old_idx = self._columns.index(col_name)
        new_idx = max(0, min(ordinal, len(self._columns) - 1))
        
        if old_idx == new_idx:
            return self
        
        # 移动列名
        self._columns.pop(old_idx)
        self._columns.insert(new_idx, col_name)
        
        # 移动数据
        for row in self._data:
            if old_idx < len(row):
                val = row.pop(old_idx)
                row.insert(new_idx, val)
        
        self._row_index.clear()
        return self

    def rowslice(self, start: int, end: int = None) -> 'Table':
        """行切片

        Args:
            start: 起始行 (包含)
            end: 结束行 (不包含)，None 表示到末尾

        Returns:
            新的 Table
        """
        end = end if end is not None else len(self._data)
        return Table(
            [row[:] for row in self._data[start:end]],
            columns=list(self._columns),
            name=self._name
        )
    
    # ==================== 列类型转换 (QAX 风格) ====================
    
    def to_date(self, col: Union[str, int]) -> 'Table':
        """列转日期类型 (对应 QAXColToDate)
        
        Args:
            col: 列名或列索引
        
        Returns:
            self (修改自身)
        """
        col_idx = self._get_col_index(col)
        for row in self._data:
            if col_idx < len(row) and row[col_idx]:
                try:
                    if isinstance(row[col_idx], str):
                        # 尝试解析日期字符串
                        for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%Y-%m-%d %H:%M:%S', '%Y/%m/%d %H:%M:%S']:
                            try:
                                row[col_idx] = datetime.strptime(row[col_idx], fmt)
                                break
                            except ValueError:
                                continue
                except (ValueError, TypeError):
                    pass
        return self
    
    def to_num(self, col: Union[str, int]) -> 'Table':
        """列转数字类型 (对应 QAXColToNum)
        
        Args:
            col: 列名或列索引
        
        Returns:
            self (修改自身)
        """
        col_idx = self._get_col_index(col)
        for row in self._data:
            if col_idx < len(row) and row[col_idx] is not None:
                try:
                    val = row[col_idx]
                    if isinstance(val, str):
                        # 移除千分位逗号
                        val = val.replace(',', '')
                        row[col_idx] = float(val) if '.' in val else int(val)
                    elif isinstance(val, (int, float)):
                        pass  # 已经是数字
                    else:
                        row[col_idx] = None
                except (ValueError, TypeError):
                    row[col_idx] = None
        return self
    
    def to_str(self, col: Union[str, int]) -> 'Table':
        """列转字符串类型 (对应 QAXColToStr)
        
        Args:
            col: 列名或列索引
        
        Returns:
            self (修改自身)
        """
        col_idx = self._get_col_index(col)
        for row in self._data:
            if col_idx < len(row) and row[col_idx] is not None:
                row[col_idx] = str(row[col_idx])
        return self

    def _get_col_index(self, col) -> int:
        """获取列索引"""
        if isinstance(col, int):
            return col
        if col in self._row_index:
            return self._row_index[col]
        # 构建索引
        for i, name in enumerate(self._columns):
            self._row_index[name] = i
        return self._row_index[col]

    # ==================== 迭代器 ====================

    def iter_rows(self) -> Iterator['Row']:
        """行迭代器 - 返回 Row 对象
        
        遍历所有行，每行返回一个 Row 对象
        数量 = rows()
        """
        for i in range(len(self._data)):
            yield self.get_row(i)

    def iter_cols(self) -> Iterator['Column']:
        """列迭代器 - 返回 Column 对象
        
        遍历所有列，每列返回一个 Column 对象
        数量 = cols()
        """
        for i in range(len(self._columns)):
            yield self.get_col(i)

    def iter_cells_row_major(self) -> Iterator[Any]:
        """先行后列的单元格值迭代器
        
        先遍历第一行所有列，再第二行...
        总数量 = rows() * cols()
        """
        for row in self._data:
            for cell in row:
                yield cell

    def iter_cells_col_major(self) -> Iterator[Any]:
        """先列后行的单元格值迭代器
        
        先遍历第一列所有行，再第二列...
        总数量 = rows() * cols()
        """
        num_rows = len(self._data)
        num_cols = len(self._columns)
        for j in range(num_cols):
            for i in range(num_rows):
                yield self._data[i][j]

    def iter_values(self) -> Iterator[List[Any]]:
        """值迭代器"""
        for row in self._data:
            yield list(row)

    def iter_columns(self) -> Iterator[Tuple[str, List[Any]]]:
        """列迭代器"""
        for i, col_name in enumerate(self._columns):
            yield col_name, [row[i] for row in self._data]

    # ==================== 链式操作 ====================

    def select(self, *cols: str) -> 'Table':
        """选择列

        Args:
            *cols: 要选择的列名

        Returns:
            新的 Table

        示例::

            table.select('name', 'age')
        """
        col_indices = [self._columns.index(c) for c in cols]
        new_data = [
            [row[i] for i in col_indices]
            for row in self._data
        ]
        return Table(new_data, columns=list(cols))

    def filter(self, predicate: Callable[[Dict], bool]) -> 'Table':
        """过滤行

        Args:
            predicate: 谓词函数，接收一整行数据 (字典)

        Returns:
            新的 Table

        示例::

            table.filter(lambda r: r['age'] > 25)
        """
        new_data = [
            row[:] for row, i in zip(self._data, range(len(self._data)))
            if predicate(self.row(i))
        ]
        return Table(new_data, columns=list(self._columns))

    def map(self, func: Callable[[Dict], Dict]) -> 'Table':
        """映射每一行

        Args:
            func: 映射函数，接收行数据，返回新行数据

        Returns:
            新的 Table
        """
        new_data = [func(row) if isinstance(row, dict) else func(self.row(i))
                   for i, row in enumerate(self._data)]
        # 如果返回的是字典，需要转换回列表
        if new_data and isinstance(new_data[0], dict):
            first_dict = new_data[0]
            new_columns = list(first_dict.keys())
            new_data = [
                [row.get(c) for c in new_columns]
                for row in new_data
            ]
            return Table(new_data, columns=new_columns)
        return Table(new_data, columns=list(self._columns))

    def sort(self, by: str, reverse: bool = False) -> 'Table':
        """排序

        Args:
            by: 排序列名
            reverse: 是否降序

        Returns:
            新的 Table
        """
        col_idx = self._columns.index(by)
        sorted_data = sorted(self._data, key=lambda x: x[col_idx], reverse=reverse)
        return Table([row[:] for row in sorted_data], columns=list(self._columns))

    def distinct(self) -> 'Table':
        """去重

        Returns:
            新的 Table
        """
        seen = set()
        new_data = []
        for row in self._data:
            row_tuple = tuple(row)
            if row_tuple not in seen:
                seen.add(row_tuple)
                new_data.append(row[:])
        return Table(new_data, columns=list(self._columns))

    def limit(self, n: int, offset: int = 0) -> 'Table':
        """限制行数

        Args:
            n: 返回行数
            offset: 偏移量

        Returns:
            新的 Table
        """
        end = min(offset + n, len(self._data))
        return Table(
            [row[:] for row in self._data[offset:end]],
            columns=list(self._columns)
        )

    def foreach(self, func: Callable[[Dict], None]) -> 'Table':
        """遍历每一行

        Args:
            func: 处理函数，接收行数据

        Returns:
            self (支持链式)
        """
        for i in range(len(self._data)):
            func(self.row(i))
        return self

    # ==================== SQL 风格方法 ====================

    def where(self, expr) -> 'Table':
        """SQL 风格条件过滤 (WHERE)

        Args:
            expr: 字符串表达式 (如 'age > 25') 或 谓词函数 (如 lambda r: r['age'] > 25)

        Returns:
            新的 Table

        示例::

            table.where('age > 25')
            table.where(lambda r: r['age'] > 25 and r['city'] == 'NYC')
        """
        if callable(expr):
            predicate = expr
        elif isinstance(expr, str):
            predicate = self._parse_where_expr(expr)
        else:
            raise TypeError('where() expr must be string or callable')

        return self.filter(predicate)

    def _parse_where_expr(self, expr: str) -> Callable[[Dict], bool]:
        """解析简单的 SQL where 表达式

        支持: <, >, <=, >=, ==, !=, and, or, in
        """
        import re

        def safe_eval(row):
            # 替换列名为行属性访问
            safe = expr
            for col in self._columns:
                # 单词边界匹配，避免部分匹配
                safe = re.sub(r'\b' + re.escape(col) + r'\b',
                             repr(row.get(col)), safe)
            try:
                return bool(eval(safe))
            except Exception:
                return False

        return safe_eval

    def order_by(self, col: str, desc: bool = False) -> 'Table':
        """SQL 风格排序 (ORDER BY)

        Args:
            col: 排序列名
            desc: 是否降序

        Returns:
            新的 Table

        示例::

            table.order_by('age', desc=True)
        """
        return self.sort(col, reverse=desc)

    def having(self, predicate: Callable[[Dict], bool]) -> 'Table':
        """分组后过滤 (HAVING)

        注意: 通常在 group_by 后使用，对分组后的 Table 进行过滤

        Args:
            predicate: 谓词函数

        Returns:
            新的 Table

        示例::

            groups = table.group_by('city')
            # 筛选行数 >= 2 的分组
            big_groups = [g for k, g in groups.items() if g.rows() >= 2]
        """
        return self.filter(predicate)

    def agg(self, funcs: Dict[str, Union[str, Callable]]) -> 'Table':
        """SQL 风格聚合 (AGG)

        Args:
            funcs: 列名 -> 聚合方法映射
                - 字符串: 'sum'/'mean'/'avg'/'min'/'max'/'count'/'std'/'var'
                - 函数: 自定义聚合函数

        Returns:
            新的 Table (1 行，包含聚合结果)

        示例::

            table.agg({'age': 'mean', 'salary': 'sum'})
            table.agg({'age': lambda vals: sum(vals) / len(vals)})
        """
        result = {}
        for col, func in funcs.items():
            values = [v for v in self.column(col) if v is not None]
            nums = [v for v in values if isinstance(v, (int, float))]

            if callable(func):
                result[col] = func(values)
            elif func == 'sum':
                result[col] = sum(nums)
            elif func in ('mean', 'avg'):
                result[col] = sum(nums) / len(nums) if nums else 0
            elif func == 'min':
                result[col] = min(values) if values else None
            elif func == 'max':
                result[col] = max(values) if values else None
            elif func == 'count':
                result[col] = len(values)
            elif func == 'std':
                if len(nums) > 1:
                    mean = sum(nums) / len(nums)
                    var = sum((x - mean) ** 2 for x in nums) / (len(nums) - 1)
                    result[col] = var ** 0.5
                else:
                    result[col] = 0
            elif func == 'var':
                if len(nums) > 1:
                    mean = sum(nums) / len(nums)
                    result[col] = sum((x - mean) ** 2 for x in nums) / (len(nums) - 1)
                else:
                    result[col] = 0
            else:
                raise ValueError(f'Unknown agg func: {func}')

        return Table([[result[c] for c in funcs.keys()]],
                    columns=list(funcs.keys()))

    def query(self, sql_like: str = None, **kwargs) -> 'Table':
        """SQL 风格链式查询

        Args:
            sql_like: SQL 风格参数字符串
                如 "where=age>25&order_by=age&limit=5"
            **kwargs: 查询参数
                - where: 条件
                - order_by: 排序列
                - desc: 是否降序
                - limit: 限制行数
                - offset: 偏移量
                - select: 要选择的列

        Returns:
            新的 Table

        示例::

            table.query(where='age > 25', order_by='age', desc=True, limit=5)
        """
        result = self
        if 'select' in kwargs:
            cols = kwargs['select']
            if isinstance(cols, str):
                cols = [c.strip() for c in cols.split(',')]
            result = result.select(*cols)
        if 'where' in kwargs:
            result = result.where(kwargs['where'])
        if 'order_by' in kwargs:
            result = result.order_by(kwargs['order_by'], desc=kwargs.get('desc', False))
        if 'offset' in kwargs:
            result = result.limit(kwargs.get('limit', 10),
                                 offset=kwargs['offset'])
        elif 'limit' in kwargs:
            result = result.limit(kwargs['limit'])
        return result

    # ==================== 聚合操作 ====================

    def group_by(self, col: str) -> Dict[Any, 'Table']:
        """分组

        Args:
            col: 分组列名

        Returns:
            分组后的字典 {分组值: Table}

        示例::

            groups = table.group_by('city')
            for city, group in groups.items():
                print(city, group.rows())
        """
        col_idx = self._columns.index(col)
        groups = {}
        for row in self._data:
            key = row[col_idx]
            if key not in groups:
                groups[key] = []
            groups[key].append(row[:])
        return {
            k: Table(v, columns=list(self._columns), name=self._name)
            for k, v in groups.items()
        }
    
    # ==================== 数据操作 (QAX 风格) ====================
    
    def join(self, other: 'Table', select_fields: List[str] = None,
             on_str: str = None, join_type: str = 'inner',
             first: bool = False, fld_type: int = 0) -> 'Table':
        """两表连接 (对应 QaxJoin)
        
        Args:
            other: 连接的另一个表
            select_fields: 要选择的字段 ['table1.col1', 'table2.col2']
            on_str: 连接条件 'table1.id = table2.id'
            join_type: 连接类型 'inner', 'left', 'right', 'outer'
            first: 是否只返回第一个匹配
            fld_type: 字段类型 (暂未使用)
        
        Returns:
            连接后的新 Table
        """
        if on_str is None:
            # 自动查找同名列作为连接键
            common_cols = set(self._columns) & set(other._columns)
            if not common_cols:
                raise ValueError('No common columns found for join')
            on_col = list(common_cols)[0]
        else:
            # 解析 on_str: 'table1.id = table2.id'
            match = re.match(r'(\w+)\.(\w+)\s*=\s*(\w+)\.(\w+)', on_str)
            if match:
                on_col = match.group(2)  # 使用右边的列名
            else:
                on_col = on_str
        
        # 确定字段前缀
        self_prefix = 't1_'
        other_prefix = 't2_'
        
        # 确定要选择的字段
        if select_fields:
            self_cols = [f.replace('self.', '').replace('t1.', '') for f in select_fields if f.startswith(('self.', 't1.'))]
            other_cols = [f.replace('other.', '').replace('t2.', '') for f in select_fields if f.startswith(('other.', 't2.'))]
            if not self_cols:
                self_cols = list(self._columns)
            if not other_cols:
                other_cols = list(other._columns)
        else:
            self_cols = list(self._columns)
            other_cols = list(other._columns)
        
        # 构建结果
        result_data = []
        result_columns = (
            [self_prefix + c for c in self_cols] + 
            [other_prefix + c for c in other_cols if c != on_col or join_type != 'inner']
        )
        
        # 创建其他表的索引
        other_index = {}
        for i, row in enumerate(other._data):
            key = row[other._columns.index(on_col)] if on_col in other._columns else None
            if key not in other_index:
                other_index[key] = []
            other_index[key].append(row)
        
        # 执行连接
        for s_row in self._data:
            key = s_row[self._columns.index(on_col)] if on_col in self._columns else None
            s_vals = [s_row[self._columns.index(c)] if c in self._columns else None for c in self_cols]
            
            if key in other_index:
                for o_row in other_index[key]:
                    o_vals = [o_row[other._columns.index(c)] if c in other._columns else None for c in other_cols]
                    if join_type == 'inner':
                        result_data.append(s_vals + [v for c, v in zip(other_cols, o_vals) if c != on_col])
                    else:
                        result_data.append(s_vals + [v for c, v in zip(other_cols, o_vals)])
            elif join_type in ('left', 'outer'):
                result_data.append(s_vals + [None] * (len(other_cols) - (1 if on_col in other_cols else 0)))
            
            if first and key in other_index:
                break
        
        return Table(result_data, columns=result_columns, name=self._name)
    
    def merge(self, other: 'Table', vertical: bool = True) -> 'Table':
        """合并两个表 (对应 QAXMerge)
        
        Args:
            other: 要合并的另一个表
            vertical: True-纵向追加行，False-横向追加列
        
        Returns:
            合并后的新 Table
        """
        if vertical:
            # 纵向合并（追加行）- 要求列结构相同
            if self._columns != other._columns:
                # 尝试对齐列
                new_columns = list(self._columns)
                for col in other._columns:
                    if col not in new_columns:
                        new_columns.append(col)
                
                # 补齐两表的列
                data1 = []
                for row in self._data:
                    new_row = row[:] + [None] * (len(new_columns) - len(row))
                    data1.append(new_row)
                
                data2 = []
                for row in other._data:
                    new_row = [None] * len(self._columns) + row[:]
                    # 重新按 new_columns 排列
                    aligned_row = []
                    for col in new_columns:
                        if col in self._columns:
                            idx = self._columns.index(col)
                            aligned_row.append(row[idx] if idx < len(row) else None)
                        elif col in other._columns:
                            idx = other._columns.index(col)
                            aligned_row.append(row[idx] if idx < len(row) else None)
                        else:
                            aligned_row.append(None)
                    data2.append(aligned_row)
                
                return Table(data1 + data2, columns=new_columns, name=self._name)
            else:
                return Table(self._data + other._data[:], columns=list(self._columns), name=self._name)
        else:
            # 横向合并（追加列）- 要求行数相同
            if len(self._data) != len(other._data):
                raise ValueError('Tables must have same row count for horizontal merge')
            
            new_columns = list(self._columns) + list(other._columns)
            result_data = []
            for i in range(len(self._data)):
                result_data.append(self._data[i][:] + other._data[i][:])
            
            return Table(result_data, columns=new_columns, name=self._name)
    
    def replace(self, col_num: int, replace_before: Any, replace_after: Any) -> 'Table':
        """替换列中的值 (对应 QAXReplace)
        
        Args:
            col_num: 列索引
            replace_before: 要替换的值
            replace_after: 替换后的值
        
        Returns:
            self (支持链式)
        """
        for row in self._data:
            if col_num < len(row) and row[col_num] == replace_before:
                row[col_num] = replace_after
        return self
    
    def clear(self) -> 'Table':
        """清空数据 (对应 QAXClear)
        
        Returns:
            self (支持链式)
        """
        self._data = []
        return self
    
    def compute(self, expression: str, filter_expr: str = None, default_value: Any = None) -> Any:
        """计算聚合表达式 (对应 QAXCompute)
        
        Args:
            expression: 聚合表达式，如 'SUM(price * quantity)'
            filter_expr: 过滤条件，如 'quantity > 0'
            default_value: 默认值
        
        Returns:
            计算结果
        """
        table = self
        if filter_expr:
            table = table.where(filter_expr)
        
        # 简单解析表达式
        expr_lower = expression.upper().strip()
        
        # 提取列名和操作
        if expr_lower.startswith('SUM(') and expr_lower.endswith(')'):
            col_name = expression[4:-1]
            values = table.column(col_name)
            nums = [v for v in values if isinstance(v, (int, float))]
            return sum(nums) if nums else default_value
        elif expr_lower.startswith('AVG(') and expr_lower.endswith(')'):
            col_name = expression[4:-1]
            values = table.column(col_name)
            nums = [v for v in values if isinstance(v, (int, float))]
            return sum(nums) / len(nums) if nums else default_value
        elif expr_lower.startswith('COUNT(') and expr_lower.endswith(')'):
            col_name = expression[6:-1]
            values = table.column(col_name)
            return len([v for v in values if v is not None])
        elif expr_lower.startswith('MAX(') and expr_lower.endswith(')'):
            col_name = expression[4:-1]
            values = table.column(col_name)
            nums = [v for v in values if isinstance(v, (int, float))]
            return max(nums) if nums else default_value
        elif expr_lower.startswith('MIN(') and expr_lower.endswith(')'):
            col_name = expression[4:-1]
            values = table.column(col_name)
            nums = [v for v in values if isinstance(v, (int, float))]
            return min(nums) if nums else default_value
        
        return default_value

    def aggregate(self, col: str, agg_func: Callable[[List], Any]) -> Dict[Any, Any]:
        """聚合

        Args:
            col: 聚合列名
            agg_func: 聚合函数

        Returns:
            聚合结果字典
        """
        values = self.column(col)
        return {col: agg_func(values)}
    
    # ==================== 字符串处理 (QAX 风格) ====================
    
    def substr(self, to_field_name: str, trunc_field_name: str,
               start_pos: int = 1, end_pos: int = None,
               filter_str: str = None) -> 'Table':
        """字符串截取 (对应 QAXSubstr)
        
        Args:
            to_field_name: 目标列名（存放截取结果）
            trunc_field_name: 源列名
            start_pos: 起始位置 (从1开始)
            end_pos: 结束位置
            filter_str: 过滤条件
        
        Returns:
            self (修改自身)
        """
        table = self
        if filter_str:
            table = Table([r[:] for r in self._data], columns=list(self._columns), name=self._name)
        
        col_idx = table._columns.index(trunc_field_name) if trunc_field_name in table._columns else -1
        if col_idx < 0:
            return self
        
        # 添加目标列
        if to_field_name not in table._columns:
            table._columns.append(to_field_name)
            for row in table._data:
                row.append(None)
        
        to_idx = table._columns.index(to_field_name)
        
        for row in table._data:
            if col_idx < len(row) and row[col_idx]:
                val = str(row[col_idx])
                # Python 索引从0开始，所以 start_pos-1
                start = max(0, start_pos - 1)
                if end_pos:
                    row[to_idx] = val[start:end_pos]
                else:
                    row[to_idx] = val[start:]
        
        return self
    
    def split(self, split_field_name: str, separator: str,
              to_fields_arr: List[str]) -> 'Table':
        """字符串分割 (对应 QAXSplit)
        
        Args:
            split_field_name: 要分割的列名
            separator: 分隔符
            to_fields_arr: 目标列名列表
        
        Returns:
            self (修改自身)
        """
        col_idx = self._columns.index(split_field_name) if split_field_name in self._columns else -1
        if col_idx < 0:
            return self
        
        # 确保目标列存在
        for field in to_fields_arr:
            if field not in self._columns:
                self._columns.append(field)
                for row in self._data:
                    row.append(None)
        
        field_indices = [self._columns.index(f) for f in to_fields_arr]
        
        for row in self._data:
            if col_idx < len(row) and row[col_idx]:
                parts = str(row[col_idx]).split(separator)
                for i, idx in enumerate(field_indices):
                    if i < len(parts):
                        row[idx] = parts[i]
                    else:
                        row[idx] = None
        
        return self
    
    def concat(self, to_field: str, concat_array: List[str],
               filter_str: str = None) -> 'Table':
        """字符串拼接 (对应 QAXConcat)
        
        Args:
            to_field: 目标列名
            concat_array: 要拼接的列名列表
            filter_str: 过滤条件
        
        Returns:
            self (修改自身)
        """
        table = self
        if filter_str:
            table = Table([r[:] for r in self._data], columns=list(self._columns), name=self._name)
        
        # 确保目标列存在
        if to_field not in table._columns:
            table._columns.append(to_field)
            for row in table._data:
                row.append(None)
        
        to_idx = table._columns.index(to_field)
        
        for row in table._data:
            parts = []
            for col_name in concat_array:
                if col_name in table._columns:
                    col_idx = table._columns.index(col_name)
                    if col_idx < len(row) and row[col_idx]:
                        parts.append(str(row[col_idx]))
            row[to_idx] = ''.join(parts)
        
        return self

    def count(self) -> int:
        """行数"""
        return self.rows()

    def sum(self, col: str) -> Union[int, float]:
        """求和"""
        values = self.column(col)
        return sum(v for v in values if isinstance(v, (int, float)))

    def avg(self, col: str) -> float:
        """平均值"""
        values = self.column(col)
        nums = [v for v in values if isinstance(v, (int, float))]
        return sum(nums) / len(nums) if nums else 0

    def min(self, col: str) -> Any:
        """最小值"""
        values = self.column(col)
        nums = [v for v in values if isinstance(v, (int, float))]
        return min(nums) if nums else None

    def max(self, col: str) -> Any:
        """最大值"""
        values = self.column(col)
        nums = [v for v in values if isinstance(v, (int, float))]
        return max(nums) if nums else None

    # ==================== 转换 ====================

    def to_dicts(self) -> List[Dict[str, Any]]:
        """转为字典列表"""
        return [self.row(i) for i in range(len(self._data))]
    
    def to_list(self) -> List[List[Any]]:
        """转为二维列表 (对应 QAXToArray)"""
        return [row[:] for row in self._data]
    
    def to_array(self, include_fields: bool = True) -> List[List[Any]]:
        """转为二维数组 (对应 QAXToArray)
        
        Args:
            include_fields: 是否包含字段名行
        
        Returns:
            二维列表
        """
        if include_fields:
            return [list(self._columns)] + [row[:] for row in self._data]
        return [row[:] for row in self._data]

    def to_dataframe(self):
        """转为 pandas DataFrame

        需要安装 pandas::

            pip install pandas
        """
        try:
            import pandas as pd
            import math

            # 处理 NaN
            def convert_value(v):
                if v is None:
                    return None
                if isinstance(v, float) and math.isnan(v):
                    return None
                return v

            data = [[convert_value(v) for v in row] for row in self._data]
            return pd.DataFrame(data, columns=self._columns)
        except ImportError:
            raise ImportError('pandas is required. Install: pip install pandas')
    
    def to_file(self, filepath: str, delimiter: str = ',',
                encoding: str = 'utf-8') -> bool:
        """导出到文件 (对应 QAXToFile)
        
        Args:
            filepath: 文件路径
            delimiter: 列分隔符
            encoding: 文件编码
        
        Returns:
            True-成功
        """
        try:
            with open(filepath, 'w', encoding=encoding, newline='') as f:
                writer = csv.writer(f, delimiter=delimiter)
                # 写入表头
                writer.writerow(self._columns)
                # 写入数据
                for row in self._data:
                    writer.writerow(row)
            return True
        except Exception:
            return False
    
    def show(self, max_rows: int = 10) -> 'Table':
        """显示表格内容 (对应 showQax)
        
        Args:
            max_rows: 最大显示行数
        
        Returns:
            self (支持链式)
        """
        print(self._repr_html(max_rows))
        return self
    
    def _repr_html(self, max_rows: int = 10) -> str:
        """HTML 格式的表格表示"""
        lines = []
        lines.append(f'<strong>Table: {self._name or "unnamed"} ({self.rows()} rows x {self.cols()} cols)</strong>')
        lines.append('<table border="1">')
        
        # 表头
        lines.append('<tr>')
        for col in self._columns[:10]:
            lines.append(f'<th>{col}</th>')
        if len(self._columns) > 10:
            lines.append('<th>...</th>')
        lines.append('</tr>')
        
        # 数据
        for i, row in enumerate(self._data[:max_rows]):
            lines.append('<tr>')
            for val in row[:10]:
                val_str = str(val) if val is not None else ''
                lines.append(f'<td>{val_str}</td>')
            if len(row) > 10:
                lines.append('<td>...</td>')
            lines.append('</tr>')
        
        lines.append('</table>')
        
        if self.rows() > max_rows:
            lines.append(f'<em>... and {self.rows() - max_rows} more rows</em>')
        
        return '\n'.join(lines)

    @classmethod
    def from_dicts(cls, dicts: List[Dict[str, Any]],
                   columns: List[str] = None) -> 'Table':
        """从字典列表创建

        Args:
            dicts: 字典列表
            columns: 列名列表 (可选)

        Returns:
            Table 实例
        """
        if not dicts:
            return cls()

        if columns is None:
            columns = list(dicts[0].keys())

        data = [
            [d.get(c) for c in columns]
            for d in dicts
        ]
        return cls(data, columns=columns)

    @classmethod
    def from_dataframe(cls, df) -> 'Table':
        """从 pandas DataFrame 创建

        Args:
            df: pandas DataFrame

        Returns:
            Table 实例
        """
        columns = list(df.columns)
        data = df.values.tolist()
        return cls(data, columns=columns)

    # ==================== Excel IO ====================

    @classmethod
    def read_excel(cls, filename: str, sheet_index: int = 0,
                   header: bool = True) -> 'Table':
        """从 Excel 读取

        Args:
            filename: 文件路径
            sheet_index: 工作表索引 (从0开始)
            header: 是否将首行作为表头

        Returns:
            Table 实例

        示例::

            table = Table.read_excel('data.xlsx')
        """
        from ..xl import Book

        if not os.path.exists(filename):
            raise FileNotFoundError(f'File not found: {filename}')

        with Book() as book:
            if not book.load(filename):
                raise RuntimeError(f'Failed to load: {book.error_message}')

            sheet = book.get_sheet(sheet_index)

            # 扫描实际数据范围
            first_row = sheet.first_row
            last_row = sheet.last_row
            first_col = sheet.first_col
            last_col = sheet.last_col

            # trial 版本占用第0行，从第1行开始读取
            if first_row == 0:
                first_row = 1

            # 自动检测有效列数（从表头行检测）
            if header:
                header_row = first_row
                # 扫描前50列确定列数
                last_col = first_col
                for col in range(first_col, min(first_col + 50, sheet.last_col + 1)):
                    ct = sheet.cell_type(header_row, col)
                    if ct == 2:  # STRING
                        val = sheet.read_str(header_row, col)
                        if val and str(val).strip() != '':
                            last_col = col
                # 确保至少读取 first_col 到 last_col

            # 读取数据
            rows = last_row - first_row + 1
            cols = last_col - first_col + 1

            if rows <= 0 or cols <= 0:
                return cls()

            matrix = sheet.read_matrix(rows, cols, first_row, first_col)

            if not matrix:
                return cls()

            # 分离表头和数据
            if header:
                columns = [str(c) if c is not None and c != '' else f'col_{i}'
                          for i, c in enumerate(matrix[0])]
                data = matrix[1:] if len(matrix) > 1 else []
            else:
                columns = [f'col_{i}' for i in range(cols)]
                data = matrix

            # 过滤空行
            data = [row for row in data if any(v is not None and v != '' for v in row)]

            return cls(data, columns=columns)

    def write_excel(self, filename: str, sheet_name: str = 'Sheet1') -> bool:
        """写入 Excel

        Args:
            filename: 文件路径
            sheet_name: 工作表名称

        Returns:
            True-成功

        示例::

            table.write_excel('output.xlsx')
        """
        from ..xl import Book

        with Book() as book:
            sheet = book.add_sheet(sheet_name)
            # 写入表头
            sheet.write_matrix([self._columns], start_row=1, start_col=0)
            # 写入数据
            if self._data:
                sheet.write_matrix(self._data, start_row=2, start_col=0)
            return book.save(filename)

    # ==================== 特殊方法 ====================

    def __len__(self) -> int:
        return self.rows()

    def __iter__(self) -> Iterator[Dict[str, Any]]:
        for i in range(len(self._data)):
            yield self.row(i)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self.row(key)
        elif isinstance(key, str):
            return self.column(key)
        elif isinstance(key, tuple):
            row, col = key
            return self.at(row, col)
        raise TypeError(f'Invalid key type: {type(key)}')

    def __repr__(self):
        if self.is_empty():
            return 'Table(empty)'
        max_rows = 5
        header = f'Table({self.rows()} rows x {self.cols()} cols)'
        rows = []
        for i, row in enumerate(self._data[:max_rows]):
            row_str = ', '.join(
                str(v) if v is not None else ''
                for v in row[:5]
            )
            if len(self._columns) > 5:
                row_str += '...'
            rows.append(f'  [{row_str}]')
        if len(self._data) > max_rows:
            rows.append(f'  ... ({len(self._data) - max_rows} more rows)')
        return header + '\n' + '\n'.join(rows)

    def __str__(self):
        return self.__repr__()
    
    def _with_attrs(self, result):
        """将当前表的属性（列名、表名等）复制到结果表中
        
        Args:
            result: 结果 Table 实例
            
        Returns:
            复制属性后的 result
        """
        if isinstance(result, Table) and result is not self:
            result._columns = list(self._columns)
            result._name = self._name
            result._row_index = {}
            result._rself_kwargs = {'columns': list(self._columns), 'name': self._name}
        return result


# 批量包装 Seq 中返回新实例的方法，使其保留 Table 属性
_seq_methods_to_wrap = [
    'take', 'skip', 'reverse', 'sort_by',
    'prepend', 'extend', 'add', 'add_reversed',
    'take_while', 'drop_while',
    'enumerate', 'zip', 'zip_longest',
    'flatten', 'flatmap', 'flatmap_ex', 'flatmap_ex1',
    'grouper', 'accum', 'distinct', 'group_by',
]

for _method_name in _seq_methods_to_wrap:
    if hasattr(Seq, _method_name) and _method_name not in Table.__dict__:
        _original_method = getattr(Seq, _method_name)
        
        def _make_wrapper(mname, mfunc):
            def _wrapper(self, *args, **kwargs):
                result = mfunc(self, *args, **kwargs)
                return self._with_attrs(result)
            _wrapper.__name__ = mname
            return _wrapper
        
        setattr(Table, _method_name, _make_wrapper(_method_name, _original_method))


# 便捷函数
def read_excel(filename: str, sheet_index: int = 0) -> Table:
    """从 Excel 读取为 Table

    Args:
        filename: 文件路径
        sheet_index: 工作表索引

    Returns:
        Table 实例
    """
    return Table.read_excel(filename, sheet_index)


def write_excel(filename: str, table: Table,
                sheet_name: str = 'Sheet1') -> bool:
    """将 Table 写入 Excel

    Args:
        filename: 文件路径
        table: Table 实例
        sheet_name: 工作表名称

    Returns:
        True-成功
    """
    return table.write_excel(filename, sheet_name)
