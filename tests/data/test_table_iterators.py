"""
测试 Table 类的四种迭代方式
"""
from vools.data import Table, Row, Column


def test_iter_rows():
    """测试 iter_rows() - 返回 Row 对象的迭代器"""
    table = Table([
        ['Alice', 25, 'New York'],
        ['Bob', 30, 'Los Angeles'],
        ['Charlie', 35, 'Chicago'],
    ], columns=['name', 'age', 'city'])
    
    rows = list(table.iter_rows())
    
    # 数量 = rows()
    assert len(rows) == table.rows() == 3, f"Expected 3 rows, got {len(rows)}"
    
    # 每个元素都是 Row 对象
    for i, row in enumerate(rows):
        assert isinstance(row, Row), f"Row {i} is not Row instance, got {type(row)}"
        assert row.index() == i, f"Row index mismatch: expected {i}, got {row.index()}"
    
    # 验证顺序和内容
    assert rows[0]['name'] == 'Alice'
    assert rows[0]['age'] == 25
    assert rows[1]['name'] == 'Bob'
    assert rows[2]['name'] == 'Charlie'
    
    print("✓ iter_rows() 测试通过")


def test_iter_cols():
    """测试 iter_cols() - 返回 Column 对象的迭代器"""
    table = Table([
        ['Alice', 25, 'New York'],
        ['Bob', 30, 'Los Angeles'],
        ['Charlie', 35, 'Chicago'],
    ], columns=['name', 'age', 'city'])
    
    cols = list(table.iter_cols())
    
    # 数量 = cols()
    assert len(cols) == table.cols() == 3, f"Expected 3 cols, got {len(cols)}"
    
    # 每个元素都是 Column 对象
    for i, col in enumerate(cols):
        assert isinstance(col, Column), f"Column {i} is not Column instance, got {type(col)}"
        assert col.index() == i, f"Column index mismatch: expected {i}, got {col.index()}"
    
    # 验证顺序和内容
    assert cols[0].name() == 'name'
    assert list(cols[0]) == ['Alice', 'Bob', 'Charlie']
    assert cols[1].name() == 'age'
    assert list(cols[1]) == [25, 30, 35]
    assert cols[2].name() == 'city'
    assert list(cols[2]) == ['New York', 'Los Angeles', 'Chicago']
    
    print("✓ iter_cols() 测试通过")


def test_iter_cells_row_major():
    """测试 iter_cells_row_major() - 先行后列的单元格值迭代器"""
    table = Table([
        [1, 2, 3],
        [4, 5, 6],
    ], columns=['a', 'b', 'c'])
    
    cells = list(table.iter_cells_row_major())
    
    # 总数量 = rows() * cols()
    expected_count = table.rows() * table.cols()
    assert len(cells) == expected_count, f"Expected {expected_count} cells, got {len(cells)}"
    
    # 验证顺序：先行后列
    expected = [1, 2, 3, 4, 5, 6]
    assert cells == expected, f"Expected {expected}, got {cells}"
    
    print("✓ iter_cells_row_major() 测试通过")


def test_iter_cells_col_major():
    """测试 iter_cells_col_major() - 先列后行的单元格值迭代器"""
    table = Table([
        [1, 2, 3],
        [4, 5, 6],
    ], columns=['a', 'b', 'c'])
    
    cells = list(table.iter_cells_col_major())
    
    # 总数量 = rows() * cols()
    expected_count = table.rows() * table.cols()
    assert len(cells) == expected_count, f"Expected {expected_count} cells, got {len(cells)}"
    
    # 验证顺序：先列后行
    expected = [1, 4, 2, 5, 3, 6]
    assert cells == expected, f"Expected {expected}, got {cells}"
    
    print("✓ iter_cells_col_major() 测试通过")


def test_iter_backward_compatibility():
    """测试 __iter__ 向后兼容（返回字典）"""
    table = Table([
        ['Alice', 25, 'New York'],
        ['Bob', 30, 'Los Angeles'],
    ], columns=['name', 'age', 'city'])
    
    rows = list(table)
    
    # 验证是字典
    assert isinstance(rows[0], dict), f"Expected dict, got {type(rows[0])}"
    assert rows[0]['name'] == 'Alice'
    assert rows[1]['name'] == 'Bob'
    
    print("✓ __iter__ 向后兼容测试通过")


def test_empty_table():
    """测试空表格的迭代"""
    table = Table(columns=['a', 'b', 'c'])
    
    assert len(list(table.iter_rows())) == 0
    assert len(list(table.iter_cols())) == 3
    assert len(list(table.iter_cells_row_major())) == 0
    assert len(list(table.iter_cells_col_major())) == 0
    
    print("✓ 空表格迭代测试通过")


def test_generator():
    """测试方法返回生成器/迭代器"""
    table = Table([
        [1, 2],
        [3, 4],
    ], columns=['a', 'b'])
    
    import types
    
    assert hasattr(table.iter_rows(), '__iter__')
    assert hasattr(table.iter_cols(), '__iter__')
    assert hasattr(table.iter_cells_row_major(), '__iter__')
    assert hasattr(table.iter_cells_col_major(), '__iter__')
    
    # 验证是生成器
    assert hasattr(table.iter_rows(), '__next__')
    assert hasattr(table.iter_cols(), '__next__')
    assert hasattr(table.iter_cells_row_major(), '__next__')
    assert hasattr(table.iter_cells_col_major(), '__next__')
    
    print("✓ 生成器/迭代器测试通过")


if __name__ == '__main__':
    test_iter_rows()
    test_iter_cols()
    test_iter_cells_row_major()
    test_iter_cells_col_major()
    test_iter_backward_compatibility()
    test_empty_table()
    test_generator()
    print("\n🎉 所有测试通过！")
