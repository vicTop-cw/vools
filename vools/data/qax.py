"""
Qax - SqlCel QAX 风格的表格数据结构

继承自 Table，提供 PascalCase 命名的 QAX 风格 API，60+ 便捷方法。

设计理念:
1. 完全兼容 SqlCel QAX 命名风格
2. 底层复用 Table 实现
3. 行列索引从 1 开始（QAX 风格）
4. 支持链式调用（@rself）
5. Python 3.6 兼容

使用场景:
- 从 SqlCel/VB 迁移的代码
- 习惯 QAX 风格 API 的开发者
"""

from typing import List, Dict, Any, Callable, Optional, Union
from copy import copy

from .table import Table
from ..decorators import rself

__all__ = ['Qax']


@rself
class Qax(Table):
    """SqlCel QAX 风格的表格数据结构

    提供 PascalCase 命名的 API，行列索引从 1 开始。

    示例::

        from vools.data import Qax

        # 创建表格
        qax = Qax([
            ['Alice', 25, 'New York'],
            ['Bob', 30, 'Los Angeles'],
        ], columns=['name', 'age', 'city'], name='users')

        # QAX 风格访问（索引从1开始）
        print(qax.GetCell(1, 1))   # 'Alice'
        print(qax.GetCell2('name', 2))  # 'Bob'

        # 链式操作
        qax.QAXFilter(lambda r: r['age'] > 25) \\
            .QAXSelect('name', 'city') \\
            .showQax()
    """

    def __init__(self, data=None, columns=None, name=None):
        """创建 Qax 表格（对应 QAX()）

        Args:
            data: 二维列表数据
            columns: 列名列表
            name: 表格名称
        """
        super(Qax, self).__init__(data, columns=columns, name=name)
        self._rself_kwargs = {'columns': list(self._columns), 'name': self._name}

    @classmethod
    def __from_parent__(cls, parent_val, **kwargs):
        """从父类（Table/Seq）实例创建 Qax 实例

        Args:
            parent_val: 父类实例（序列数据）
            **kwargs: 包含 columns 和 name

        Returns:
            Qax 实例
        """
        if hasattr(parent_val, '_columns') and hasattr(parent_val, '_data'):
            columns = list(parent_val._columns)
            name = getattr(parent_val, '_name', '')
            data = [row[:] for row in parent_val._data]
            return cls(data, columns=columns, name=name)

        columns = kwargs.get('columns', None)
        name = kwargs.get('name', '')
        data = list(parent_val)

        if data and isinstance(data[0], dict):
            if columns is None:
                columns = list(data[0].keys())
            data = [[row.get(c) for c in columns] for row in data]

        return cls(data, columns=columns, name=name)

    # ==================== 创建类 ====================

    @classmethod
    def ArrayToQax(cls, data, columns=None, name=None):
        """从二维数组创建 Qax（对应 ArrayToQax）

        Args:
            data: 二维数组或一维数组
            columns: 列名列表
            name: 表格名称

        Returns:
            Qax 实例
        """
        result = cls.from_array(data, fields_name=columns)
        if name:
            result._name = name
            result._rself_kwargs['name'] = name
        return result

    @classmethod
    def FileToQax(cls, path, delimiter=',', encoding='utf-8',
                  rows=None, cols=None, name=None):
        """从文件读取（对应 FileToQax）

        Args:
            path: 文件路径
            delimiter: 列分隔符
            encoding: 文件编码
            rows: 最大行数
            cols: 要读取的列索引
            name: 表格名称

        Returns:
            Qax 实例
        """
        return cls.from_file(path, delimiter=delimiter, encoding=encoding,
                             rows=rows, cols=cols, name=name)

    @classmethod
    def ExcelToQAX(cls, path, sheet=0, header=True):
        """从 Excel 读取（对应 ExcelToQAX）

        Args:
            path: Excel 文件路径
            sheet: 工作表索引或名称
            header: 是否将首行作为表头

        Returns:
            Qax 实例
        """
        if isinstance(sheet, str):
            from ..xl import Book
            with Book() as book:
                if not book.load(path):
                    raise RuntimeError('Failed to load Excel')
                sheet_idx = 0
                for i in range(book.sheet_count):
                    s = book.get_sheet(i)
                    if s.name == sheet:
                        sheet_idx = i
                        break
                result = cls.read_excel(path, sheet_index=sheet_idx, header=header)
        else:
            result = cls.read_excel(path, sheet_index=sheet, header=header)
        return result

    # ==================== 信息类 ====================

    def QAXRows(self):
        """行数（对应 QAXRows）

        Returns:
            行数
        """
        return self.rows()

    def QAXCols(self):
        """列数（对应 QAXCols）

        Returns:
            列数
        """
        return self.cols()

    def QAXColNames(self):
        """列名列表（对应 QAXColNames）

        Returns:
            列名列表
        """
        return self.columns()

    def QAXName(self):
        """表名（对应 QAXName）

        Returns:
            表名
        """
        return self.name()

    def SetQaxName(self, name):
        """设置表名（对应 SetQaxName）

        Args:
            name: 新表名

        Returns:
            self（支持链式）
        """
        return self.set_name(name)

    def QAXColIndex(self, colName):
        """获取列索引（从1开始）（对应 QAXColIndex）

        Args:
            colName: 列名

        Returns:
            列索引（从1开始），未找到返回 -1
        """
        try:
            return self._columns.index(colName) + 1
        except ValueError:
            return -1

    # ==================== 访问类 ====================

    def GetCell(self, row, col):
        """获取单元格（行列索引从1开始，QAX风格）（对应 GetCell）

        Args:
            row: 行号（从1开始）
            col: 列号（从1开始）

        Returns:
            单元格值
        """
        return self.get_cell(row - 1, col - 1)

    def GetCell2(self, colName, row):
        """获取单元格（列名+行号）（对应 GetCell2）

        Args:
            colName: 列名
            row: 行号（从1开始）

        Returns:
            单元格值
        """
        return self.get_cell2(row - 1, colName)

    def GetRow(self, row):
        """获取某行（对应 GetRow）

        Args:
            row: 行号（从1开始）

        Returns:
            行数据字典
        """
        return self.row(row - 1)

    def GetCol(self, col):
        """获取某列（对应 GetCol）

        Args:
            col: 列名或列号（从1开始）

        Returns:
            列数据列表
        """
        if isinstance(col, int):
            col = col - 1
        return self.column(col)

    def GetCols(self, cols):
        """获取多列（对应 GetCols）

        Args:
            cols: 列名列表

        Returns:
            新的 Qax
        """
        return self.get_cols(col_names=cols)

    # ==================== 修改类 ====================

    def SetCell(self, row, col, value):
        """设置单元格（对应 SetCell）

        Args:
            row: 行号（从1开始）
            col: 列号（从1开始）
            value: 值

        Returns:
            self（支持链式）
        """
        return self.set_cell(row - 1, col - 1, value)

    def SetCell2(self, colName, row, value):
        """设置单元格（列名+行号）（对应 SetCell2）

        Args:
            colName: 列名
            row: 行号（从1开始）
            value: 值

        Returns:
            self（支持链式）
        """
        return self.set_cell2(row - 1, colName, value)

    def DelRow(self, row):
        """删除行（对应 DelRow）

        Args:
            row: 行号（从1开始）

        Returns:
            self（支持链式）
        """
        return self.del_row(row - 1)

    def DelCol(self, col):
        """删除列（对应 DelCol）

        Args:
            col: 列名或列号（从1开始）

        Returns:
            self（支持链式）
        """
        if isinstance(col, int):
            col = col - 1
        return self.del_col(col)

    def NewRow(self, data=None):
        """新增行（对应 NewRow）

        Args:
            data: 行数据（列表或字典）

        Returns:
            self（支持链式）
        """
        if data is not None:
            if isinstance(data, dict):
                row_data = [data.get(c) for c in self._columns]
            else:
                row_data = list(data)
                while len(row_data) < len(self._columns):
                    row_data.append(None)
            self._data.append(row_data)
            return self
        else:
            self.new_row()
            return self

    def AddCol(self, colName, default=None):
        """新增列（对应 AddCol）

        Args:
            colName: 列名
            default: 默认值

        Returns:
            self（支持链式）
        """
        return self.add_col(colName, default_value=default)

    def InsertRow(self, row, data=None):
        """插入行（对应 InsertRow）

        Args:
            row: 插入位置（从1开始）
            data: 行数据

        Returns:
            self（支持链式）
        """
        if isinstance(data, dict):
            row_data = [data.get(c) for c in self._columns]
        elif data is not None:
            row_data = list(data)
            while len(row_data) < len(self._columns):
                row_data.append(None)
        else:
            row_data = [None] * len(self._columns)
        self._data.insert(row - 1, row_data)
        return self

    def InsertCol(self, col, colName, default=None):
        """插入列（对应 InsertCol）

        Args:
            col: 插入位置（从1开始）
            colName: 列名
            default: 默认值

        Returns:
            self（支持链式）
        """
        col_idx = col - 1
        self._columns.insert(col_idx, colName)
        for row in self._data:
            row.insert(col_idx, default)
        self._row_index.clear()
        return self

    # ==================== 数据操作 ====================

    def QAXSelect(self, *cols):
        """选择列（对应 QAXSelect）

        Args:
            *cols: 要选择的列名

        Returns:
            新的 Qax
        """
        return self.select(*cols)

    def QAXSort(self, col, asc=True):
        """排序（对应 QAXSort）

        Args:
            col: 排序列名
            asc: 是否升序

        Returns:
            新的 Qax
        """
        return self.order_by(col, desc=not asc)

    def QAXDistinct(self):
        """去重（对应 QAXDistinct）

        Returns:
            新的 Qax
        """
        return self.distinct()

    def QAXFilter(self, condition):
        """过滤（对应 QAXFilter）

        Args:
            condition: 过滤条件（字符串表达式或谓词函数）

        Returns:
            新的 Qax
        """
        return self.where(condition)

    def QAXTop(self, n):
        """取前n行（对应 QAXTop）

        Args:
            n: 行数

        Returns:
            新的 Qax
        """
        return self.limit(n)

    # ==================== 聚合类 ====================

    def QAXSum(self, col):
        """求和（对应 QAXSum）

        Args:
            col: 列名

        Returns:
            求和结果
        """
        return self.sum(col)

    def QAXAvg(self, col):
        """平均值（对应 QAXAvg）

        Args:
            col: 列名

        Returns:
            平均值
        """
        return self.avg(col)

    def QAXCount(self, col=None):
        """计数（对应 QAXCount）

        Args:
            col: 列名（可选），为 None 时计数行数

        Returns:
            计数结果
        """
        if col is None:
            return self.rows()
        values = self.column(col)
        return len([v for v in values if v is not None])

    def QAXMax(self, col):
        """最大值（对应 QAXMax）

        Args:
            col: 列名

        Returns:
            最大值
        """
        return self.max(col)

    def QAXMin(self, col):
        """最小值（对应 QAXMin）

        Args:
            col: 列名

        Returns:
            最小值
        """
        return self.min(col)

    def QaxGroup(self, group_cols, agg_spec=None):
        """分组聚合（对应 QaxGroup）

        Args:
            group_cols: 分组列名或列名列表
            agg_spec: 聚合规格字典 {列名: 聚合方法}

        Returns:
            分组后的 Qax
        """
        if isinstance(group_cols, str):
            group_cols = [group_cols]

        groups = self.group_by(group_cols[0])

        result_data = []
        result_columns = list(group_cols)

        if agg_spec:
            for col in agg_spec:
                result_columns.append(col)

            for key, group_table in groups.items():
                row = [key]
                for col, func in agg_spec.items():
                    if callable(func):
                        values = group_table.column(col)
                        row.append(func(values))
                    elif func == 'sum':
                        row.append(group_table.sum(col))
                    elif func in ('avg', 'mean'):
                        row.append(group_table.avg(col))
                    elif func == 'count':
                        values = group_table.column(col)
                        row.append(len([v for v in values if v is not None]))
                    elif func == 'min':
                        row.append(group_table.min(col))
                    elif func == 'max':
                        row.append(group_table.max(col))
                    else:
                        row.append(None)
                result_data.append(row)
        else:
            for key, group_table in groups.items():
                result_data.append([key])

        return Qax(result_data, columns=result_columns, name=self._name)

    def QAXCompute(self, col, func=None):
        """计算（对应 QAXCompute）

        Args:
            col: 列名或表达式
            func: 聚合函数或表达式字符串

        Returns:
            计算结果
        """
        if func is None:
            return self.compute(col)
        if callable(func):
            values = self.column(col)
            return func(values)
        return self.compute(func + '(' + col + ')')

    # ==================== 连接合并 ====================

    def QaxJoin(self, other, on=None, how='inner'):
        """连接（对应 QaxJoin）

        Args:
            other: 另一个 Qax/Table
            on: 连接列名
            how: 连接类型 'inner', 'left', 'right', 'outer'

        Returns:
            连接后的 Qax
        """
        return self.join(other, on_str=on, join_type=how)

    def QAXMerge(self, other):
        """合并（对应 QAXMerge）

        Args:
            other: 另一个 Qax/Table

        Returns:
            合并后的 Qax
        """
        return self.merge(other, vertical=True)

    # ==================== 更新类 ====================

    def QAXUpdate(self, condition, values):
        """条件更新（对应 QAXUpdate）

        Args:
            condition: 条件表达式或谓词函数
            values: 更新值字典 {列名: 新值}

        Returns:
            self（支持链式）
        """
        if callable(condition):
            predicate = condition
        else:
            predicate = self._parse_where_expr(condition)

        for i in range(len(self._data)):
            row_dict = self.row(i)
            if predicate(row_dict):
                for col, val in values.items():
                    col_idx = self._get_col_index(col)
                    if col_idx < len(self._data[i]):
                        self._data[i][col_idx] = val
        return self

    def QAXReplace(self, old, new, col=None):
        """替换（对应 QAXReplace）

        Args:
            old: 旧值
            new: 新值
            col: 列名或列号（从1开始），None 表示所有列

        Returns:
            self（支持链式）
        """
        if col is not None:
            if isinstance(col, int):
                col_idx = col - 1
            else:
                col_idx = self._get_col_index(col)
            return self.replace(col_idx, old, new)
        else:
            for row in self._data:
                for i in range(len(row)):
                    if row[i] == old:
                        row[i] = new
            return self

    def QAXClear(self):
        """清空数据（对应 QAXClear）

        Returns:
            self（支持链式）
        """
        return self.clear()

    # ==================== 字符串类 ====================

    def QAXSubstr(self, col, start, length=None, new_col=None):
        """字符串截取（对应 QAXSubstr）

        Args:
            col: 源列名
            start: 起始位置（从1开始）
            length: 截取长度（可选）
            new_col: 目标列名（可选，默认同 col）

        Returns:
            self（支持链式）
        """
        to_field = new_col or col
        end_pos = start + length - 1 if length else None
        return self.substr(to_field, col, start_pos=start, end_pos=end_pos)

    def QAXSplit(self, col, sep, new_cols):
        """字符串分割（对应 QAXSplit）

        Args:
            col: 要分割的列名
            sep: 分隔符
            new_cols: 目标列名列表

        Returns:
            self（支持链式）
        """
        return self.split(col, sep, new_cols)

    def QAXConcat(self, cols, new_col, sep=''):
        """字符串拼接（对应 QAXConcat）

        Args:
            cols: 要拼接的列名列表
            new_col: 目标列名
            sep: 分隔符

        Returns:
            self（支持链式）
        """
        if sep:
            temp_cols = []
            for i, c in enumerate(cols):
                temp_col = '__concat_temp_' + str(i)
                self.add_col(temp_col, '')
                temp_cols.append(temp_col)
                col_idx = self._get_col_index(c)
                temp_idx = self._get_col_index(temp_col)
                for row in self._data:
                    row[temp_idx] = str(row[col_idx]) if row[col_idx] is not None else ''

            result_col = new_col
            if result_col not in self._columns:
                self._columns.append(result_col)
                for row in self._data:
                    row.append('')

            result_idx = self._get_col_index(result_col)
            for row in self._data:
                parts = []
                for i, c in enumerate(cols):
                    col_idx = self._get_col_index(c)
                    val = row[col_idx]
                    if val is not None and val != '':
                        parts.append(str(val))
                row[result_idx] = sep.join(parts)

            for temp_col in temp_cols:
                self.del_col(temp_col)

            return self
        else:
            return self.concat(new_col, cols)

    # ==================== 转换类 ====================

    def QAXToArray(self, include_fields=True):
        """转为二维数组（对应 QAXToArray）

        Args:
            include_fields: 是否包含字段名行

        Returns:
            二维列表
        """
        return self.to_array(include_fields=include_fields)

    def QAXToFile(self, path, delimiter=',', encoding='utf-8'):
        """写入文件（对应 QAXToFile）

        Args:
            path: 文件路径
            delimiter: 列分隔符
            encoding: 文件编码

        Returns:
            True-成功
        """
        return self.to_file(path, delimiter=delimiter, encoding=encoding)

    def showQax(self, max_rows=10):
        """显示（对应 showQax）

        Args:
            max_rows: 最大显示行数

        Returns:
            self（支持链式）
        """
        return self.show(max_rows=max_rows)

    def QAXToDictList(self):
        """转为字典列表（对应 QAXToDictList）

        Returns:
            字典列表
        """
        return self.to_dicts()

    # ==================== 列操作 ====================

    def QAXColToDate(self, col, fmt=None):
        """列转日期（对应 QAXColToDate）

        Args:
            col: 列名或列号（从1开始）
            fmt: 日期格式（暂未使用，自动尝试多种格式）

        Returns:
            self（支持链式）
        """
        if isinstance(col, int):
            col = col - 1
        return self.to_date(col)

    def QAXColToNum(self, col):
        """列转数字（对应 QAXColToNum）

        Args:
            col: 列名或列号（从1开始）

        Returns:
            self（支持链式）
        """
        if isinstance(col, int):
            col = col - 1
        return self.to_num(col)

    def QAXColToStr(self, col):
        """列转字符串（对应 QAXColToStr）

        Args:
            col: 列名或列号（从1开始）

        Returns:
            self（支持链式）
        """
        if isinstance(col, int):
            col = col - 1
        return self.to_str(col)

    def SetColName(self, oldName, newName):
        """修改列名（对应 SetColName）

        Args:
            oldName: 旧列名或列号（从1开始）
            newName: 新列名

        Returns:
            self（支持链式）
        """
        if isinstance(oldName, int):
            col_num = oldName - 1
        else:
            try:
                col_num = self._columns.index(oldName)
            except ValueError:
                return self
        return self.set_col_name(col_num, newName)

    def SetOrdinal(self, col, new_index):
        """调整列顺序（对应 SetOrdinal）

        Args:
            col: 列名或列号（从1开始）
            new_index: 新位置（从1开始）

        Returns:
            self（支持链式）
        """
        if isinstance(col, int):
            col = self._columns[col - 1]
        return self.set_ordinal(col, new_index - 1)
