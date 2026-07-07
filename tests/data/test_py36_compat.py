# -*- coding: utf-8 -*-
"""Python 3.6 兼容性测试脚本 - 测试 data 模块核心功能"""
import sys


def test_row():
    from vools.data.table import Table, Row
    from vools.data.seq import Seq
    
    data = [
        ['Alice', 25, 'New York'],
        ['Bob', 30, 'Los Angeles'],
    ]
    t = Table(data, columns=['name', 'age', 'city'])
    row = t.get_row(0)
    
    assert isinstance(row, Seq), "Row 应该继承 Seq"
    assert isinstance(row, Row), "Row 应该是 Row 类型"
    assert row['name'] == 'Alice', "按列名访问失败"
    assert row[0] == 'Alice', "按索引访问失败"
    assert len(row) == 3, "长度错误"
    assert list(row) == ['Alice', 25, 'New York'], "迭代失败"
    
    mapped = row.map(str)
    assert isinstance(mapped, Row), "map 应该返回 Row"
    assert mapped[1] == '25', "map 结果错误"
    
    filtered = row.filter(lambda x: isinstance(x, str))
    assert isinstance(filtered, Row), "filter 应该返回 Row"
    assert len(filtered) == 2, "filter 结果长度错误"
    
    print("Row 测试通过")

def test_column():
    from vools.data.table import Table, Column
    from vools.data.seq import Seq
    
    data = [
        ['Alice', 25, 'New York'],
        ['Bob', 30, 'Los Angeles'],
    ]
    t = Table(data, columns=['name', 'age', 'city'])
    col = t.get_col('age')
    
    assert isinstance(col, Seq), "Column 应该继承 Seq"
    assert isinstance(col, Column), "Column 应该是 Column 类型"
    assert col[0] == 25, "按索引访问失败"
    assert len(col) == 2, "长度错误"
    assert list(col) == [25, 30], "迭代失败"
    assert col.sum() == 55, "sum 错误"
    assert col.avg() == 27.5, "avg 错误"
    
    mapped = col.map(lambda x: x * 2)
    assert isinstance(mapped, Column), "map 应该返回 Column"
    assert list(mapped) == [50, 60], "map 结果错误"
    
    print("Column 测试通过")

def test_table():
    from vools.data.table import Table
    from vools.data.seq import Seq
    
    data = [
        ['Alice', 25, 'New York'],
        ['Bob', 30, 'Los Angeles'],
        ['Charlie', 35, 'Chicago'],
    ]
    t = Table(data, columns=['name', 'age', 'city'])
    
    assert isinstance(t, Seq), "Table 应该继承 Seq"
    assert isinstance(t, Table), "Table 应该是 Table 类型"
    assert t.rows() == 3, "行数错误"
    assert t.cols() == 3, "列数错误"
    assert t.at(0, 0) == 'Alice', "at 错误"
    
    filtered = t.filter(lambda r: r['age'] > 25)
    assert isinstance(filtered, Table), "filter 应该返回 Table"
    assert filtered.rows() == 2, "filter 结果行数错误"
    
    print("Table 测试通过")

def test_iterators():
    from vools.data.table import Table, Row, Column
    
    data = [
        ['Alice', 25],
        ['Bob', 30],
    ]
    t = Table(data, columns=['name', 'age'])
    
    rows = list(t.iter_rows())
    assert len(rows) == 2, "iter_rows 数量错误"
    assert isinstance(rows[0], Row), "iter_rows 应该返回 Row"
    
    cols = list(t.iter_cols())
    assert len(cols) == 2, "iter_cols 数量错误"
    assert isinstance(cols[0], Column), "iter_cols 应该返回 Column"
    
    cells_row = list(t.iter_cells_row_major())
    assert cells_row == ['Alice', 25, 'Bob', 30], "先行后列错误"
    
    cells_col = list(t.iter_cells_col_major())
    assert cells_col == ['Alice', 'Bob', 25, 30], "先列后行错误"
    
    print("迭代器测试通过")

def test_qax():
    from vools.data.qax import Qax
    from vools.data.table import Table
    
    data = [
        ['Alice', 25, 'New York'],
        ['Bob', 30, 'Los Angeles'],
    ]
    q = Qax(data, columns=['name', 'age', 'city'])
    
    assert isinstance(q, Table), "Qax 应该继承 Table"
    assert isinstance(q, Qax), "Qax 应该是 Qax 类型"
    assert q.QAXRows() == 2, "QAXRows 错误"
    assert q.QAXCols() == 3, "QAXCols 错误"
    assert q.GetCell(1, 1) == 'Alice', "GetCell 错误（1基索引）"
    assert q.GetCell2('name', 1) == 'Alice', "GetCell2 错误"
    
    q2 = q.QAXSelect('name', 'age')
    assert isinstance(q2, Qax), "QAXSelect 应该返回 Qax"
    assert q2.QAXCols() == 2, "QAXSelect 列数错误"
    
    q3 = q.QAXSort('age')
    assert isinstance(q3, Qax), "QAXSort 应该返回 Qax"
    
    assert q.QAXSum('age') == 55, "QAXSum 错误"
    assert q.QAXAvg('age') == 27.5, "QAXAvg 错误"
    
    print("Qax 测试通过")

if __name__ == '__main__':
    print("Python 版本:", sys.version)
    print()
    
    test_row()
    test_column()
    test_table()
    test_iterators()
    test_qax()
    
    print()
    print("=" * 50)
    print("所有 Python 3.6 兼容性测试通过！")
    print("=" * 50)
