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

        Raises:
            IndexError: row 或 col 越界（BUG-248）
        """
        row = self._check_1based(row, len(self._data), '行')
        col = self._check_1based(col, len(self._columns), '列')
        return self.get_cell(row - 1, col - 1)

    def GetCell2(self, colName, row):
        """获取单元格（列名+行号）（对应 GetCell2）

        Args:
            colName: 列名
            row: 行号（从1开始）

        Returns:
            单元格值

        Raises:
            IndexError: row 越界（BUG-248）
        """
        row = self._check_1based(row, len(self._data), '行')
        return self.get_cell2(row - 1, colName)

    def GetRow(self, row):
        """获取某行（对应 GetRow）

        Args:
            row: 行号（从1开始）

        Returns:
            行数据字典

        Raises:
            IndexError: 行号越界（BUG-248）
        """
        row = self._check_1based(row, len(self._data), '行')
        return self.row(row - 1)

    def GetCol(self, col):
        """获取某列（对应 GetCol）

        Args:
            col: 列名或列号（从1开始）

        Returns:
            列数据列表

        Raises:
            IndexError: 列号越界（BUG-248）
        """
        if isinstance(col, int):
            col = self._check_1based(col, len(self._columns), '列') - 1
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

        Raises:
            IndexError: row 或 col 越界（BUG-248）
        """
        row = self._check_1based(row, len(self._data), '行')
        col = self._check_1based(col, len(self._columns), '列')
        return self.set_cell(row - 1, col - 1, value)

    def SetCell2(self, colName, row, value):
        """设置单元格（列名+行号）（对应 SetCell2）

        Args:
            colName: 列名
            row: 行号（从1开始）
            value: 值

        Returns:
            self（支持链式）

        Raises:
            IndexError: row 越界（BUG-248）
        """
        row = self._check_1based(row, len(self._data), '行')
        return self.set_cell2(row - 1, colName, value)

    def DelRow(self, row):
        """删除行（对应 DelRow）

        Args:
            row: 行号（从1开始）

        Returns:
            self（支持链式）

        Raises:
            IndexError: 行号不在 1..行数 范围内（BUG-246）
        """
        row = self._check_1based(row, len(self._data), '行')
        return self.del_row(row - 1)

    def DelCol(self, col):
        """删除列（对应 DelCol）

        Args:
            col: 列名或列号（从1开始）

        Returns:
            self（支持链式）

        Raises:
            IndexError: 列号不在 1..列数 范围内（BUG-246）
        """
        if isinstance(col, int):
            col = self._check_1based(col, len(self._columns), '列') - 1
        return self.del_col(col)

    def _check_1based(self, pos, limit, what):
        """校验 1-based 索引落在 1..limit 内（BUG-246）。

        原实现直接把 1-based 位置减 1 交给 Python 列表操作：0/负数会被
        负索引语义静默解释为「从末尾数」，造成插入到错误位置或删错列，
        而不是报错。
        """
        if not isinstance(pos, int) or isinstance(pos, bool):
            raise TypeError(f"{what}号必须是整数（从1开始），收到 {type(pos).__name__}: {pos!r}")
        if pos < 1 or pos > limit:
            raise IndexError(
                f"{what}号必须在 1..{limit} 范围内（从1开始），收到 {pos!r}")
        return pos

    def _fit_row_data(self, data):
        """把列表行数据对齐到列数（BUG-246）。"""
        row_data = list(data)
        n_cols = len(self._columns)
        if len(row_data) > n_cols:
            raise ValueError(
                f"行数据有 {len(row_data)} 个字段，超过列数 {n_cols}；"
                f"多出的字段会破坏表格矩形性，请先 AddCol 或截断数据")
        while len(row_data) < n_cols:
            row_data.append(None)
        return row_data

    def NewRow(self, data=None):
        """新增行（对应 NewRow）

        Args:
            data: 行数据（列表或字典）

        Returns:
            self（支持链式）

        Raises:
            ValueError: 列表行数据字段数超过列数（BUG-246）
        """
        if data is not None:
            if isinstance(data, dict):
                row_data = [data.get(c) for c in self._columns]
            else:
                row_data = self._fit_row_data(data)
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
            row: 插入位置（从1开始，允许 1..行数+1）
            data: 行数据

        Returns:
            self（支持链式）

        Raises:
            IndexError: 插入位置超出 1..行数+1（BUG-246）
            ValueError: 列表行数据字段数超过列数（BUG-246）
        """
        row = self._check_1based(row, len(self._data) + 1, '行')
        if isinstance(data, dict):
            row_data = [data.get(c) for c in self._columns]
        elif data is not None:
            row_data = self._fit_row_data(data)
        else:
            row_data = [None] * len(self._columns)
        self._data.insert(row - 1, row_data)
        return self

    def InsertCol(self, col, colName, default=None):
        """插入列（对应 InsertCol）

        Args:
            col: 插入位置（从1开始，允许 1..列数+1）
            colName: 列名
            default: 默认值

        Returns:
            self（支持链式）

        Raises:
            IndexError: 插入位置超出 1..列数+1（BUG-246）
        """
        col = self._check_1based(col, len(self._columns) + 1, '列')
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

        result_columns = list(group_cols)

        # BUG-177: 原 `groups = self.group_by(group_cols[0])` 只取第一列分组，
        # 多列时静默丢弃其余分组维度，且 result_columns 声明了多列但数据行只有单键，
        # 列数与数据不对齐。多列按 (g1,g2,...) 组合键分组，单列仍走 group_by 路径。
        if len(group_cols) == 1:
            col_idx_list = [self._get_col_index(group_cols[0])]
        else:
            col_idx_list = [self._get_col_index(c) for c in group_cols]

        if agg_spec:
            for col in agg_spec:
                result_columns.append(col)

        buckets: Dict[Any, List[List[Any]]] = {}
        for row in self._data:
            key = tuple(row[i] for i in col_idx_list)
            buckets.setdefault(key, []).append(row[:])

        result_data = []
        for key, rows in buckets.items():
            # BUG-177: 多列分组键 (g1,g2,...) 应展开为独立单元格（QAX 行列对齐），
            # 而非把整组键塞成单个单元格值。
            row = list(key) if len(key) > 1 else [key[0]]
            if not agg_spec:
                result_data.append(row)
                continue
            group_table = Qax(rows, columns=list(self._columns), name=self._name)
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
        # BUG-178: QAX 风格列号从 1 开始，col 可为 int。原 `func + '(' + col + ')'`
        # 在 col 为 int 时 str+int 拼接 TypeError；先转列名。
        # BUG-251: 原 `col - 1` 无校验——col=0/-1 经负索引对最后一列计算/静默失败。
        if isinstance(col, int):
            col = self._columns[self._check_1based(
                col, len(self._columns), '列') - 1]
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

        Raises:
            IndexError: col 为整数且不在 1..列数 范围内（BUG-247）
        """
        if col is not None:
            if isinstance(col, int):
                # BUG-247: 原 `col - 1` 无校验，col=0/-1 经负索引静默写到最后
                # 一列，col>列数 静默 no-op。
                col_idx = self._check_1based(col, len(self._columns), '列') - 1
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
            length: 截取长度（可选；0 表示空串，None 表示取到末尾）
            new_col: 目标列名（可选，默认同 col）

        Returns:
            self（支持链式）
        """
        to_field = new_col or col
        # BUG-249: 原 `if length else None` 是假值陷阱——length=0 被当成
        # 「不限制」返回整条尾部字符串；改用 is not None 区分。
        end_pos = start + length - 1 if length is not None else None
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
            sep: 分隔符（空字段保留占位，None 视为空串）

        Returns:
            self（支持链式）
        """
        if sep:
            result_col = new_col
            if result_col not in self._columns:
                self._columns.append(result_col)
                for row in self._data:
                    row.append('')

            result_idx = self._get_col_index(result_col)
            indices = [self._get_col_index(c) for c in cols]
            for row in self._data:
                # BUG-249: 原实现过滤空字符串字段导致分隔符错位
                # （('a','','c') + '-' -> 'a-c' 而非 'a--c'）；本实现逐列
                # 保留占位，None 渲染为空串。同时删除原「临时列」死代码
                # （建列→拷贝→最终循环又从原列读→del_col，临时值从未使用）。
                parts = [('' if row[idx] is None else str(row[idx]))
                         for idx in indices]
                row[result_idx] = sep.join(parts)
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

        Raises:
            IndexError: 列号越界（BUG-250）
        """
        if isinstance(col, int):
            col = self._check_1based(col, len(self._columns), '列') - 1
        return self.to_date(col)

    def QAXColToNum(self, col):
        """列转数字（对应 QAXColToNum）

        Args:
            col: 列名或列号（从1开始）

        Returns:
            self（支持链式）

        Raises:
            IndexError: 列号越界（BUG-250）
        """
        if isinstance(col, int):
            col = self._check_1based(col, len(self._columns), '列') - 1
        return self.to_num(col)

    def QAXColToStr(self, col):
        """列转字符串（对应 QAXColToStr）

        Args:
            col: 列名或列号（从1开始）

        Returns:
            self（支持链式）

        Raises:
            IndexError: 列号越界（BUG-250）
        """
        if isinstance(col, int):
            col = self._check_1based(col, len(self._columns), '列') - 1
        return self.to_str(col)

    def SetColName(self, oldName, newName):
        """修改列名（对应 SetColName）

        Args:
            oldName: 旧列名或列号（从1开始）
            newName: 新列名

        Returns:
            self（支持链式）

        Raises:
            IndexError: oldName 为整数且越界（BUG-251）
        """
        if isinstance(oldName, int):
            # BUG-251: 原 `oldName - 1` 无校验，越界静默 no-op。
            col_num = self._check_1based(
                oldName, len(self._columns), '列') - 1
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
            new_index: 新位置（从1开始，1..列数）

        Returns:
            self（支持链式）

        Raises:
            IndexError: col 或 new_index 越界（BUG-251）
        """
        if isinstance(col, int):
            # BUG-251: 原 `col - 1` 无校验，SetOrdinal(0, 2) 实际移动最后一列。
            col = self._columns[self._check_1based(
                col, len(self._columns), '列') - 1]
        # BUG-251: new_index 原样 -1 交给 base，0/-1 经负索引静默移到最前。
        new_index = self._check_1based(
            new_index, len(self._columns), '新位置')
        return self.set_ordinal(col, new_index - 1)
