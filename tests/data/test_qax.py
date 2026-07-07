"""
Qax 类测试

验证 Qax 类的核心 API，至少 20 个方法。
"""

from vools.data import Qax


def test_create():
    """测试创建类方法"""
    print('=== 测试创建类 ===')

    # 1. 构造函数
    qax = Qax([
        ['Alice', 25, 'New York'],
        ['Bob', 30, 'Los Angeles'],
        ['Charlie', 35, 'Chicago'],
    ], columns=['name', 'age', 'city'], name='users')
    assert qax.QAXRows() == 3
    assert qax.QAXCols() == 3
    assert qax.QAXName() == 'users'
    print('  [PASS] Qax() 构造函数')

    # 2. ArrayToQax
    qax2 = Qax.ArrayToQax([
        ['Dave', 40, 'Boston'],
        ['Eve', 28, 'Seattle'],
    ], columns=['name', 'age', 'city'], name='users2')
    assert qax2.QAXRows() == 2
    assert qax2.QAXCols() == 3
    print('  [PASS] ArrayToQax()')

    print('创建类测试通过!\n')


def test_info():
    """测试信息类方法"""
    print('=== 测试信息类 ===')

    qax = Qax([
        ['Alice', 25, 'New York'],
        ['Bob', 30, 'Los Angeles'],
    ], columns=['name', 'age', 'city'], name='test')

    # 3. QAXRows
    assert qax.QAXRows() == 2
    print('  [PASS] QAXRows()')

    # 4. QAXCols
    assert qax.QAXCols() == 3
    print('  [PASS] QAXCols()')

    # 5. QAXColNames
    assert qax.QAXColNames() == ['name', 'age', 'city']
    print('  [PASS] QAXColNames()')

    # 6. QAXName
    assert qax.QAXName() == 'test'
    print('  [PASS] QAXName()')

    # 7. SetQaxName
    result = qax.SetQaxName('new_name')
    assert qax.QAXName() == 'new_name'
    assert isinstance(result, Qax)
    print('  [PASS] SetQaxName() - 链式调用返回 Qax')

    # 8. QAXColIndex
    assert qax.QAXColIndex('name') == 1
    assert qax.QAXColIndex('age') == 2
    assert qax.QAXColIndex('city') == 3
    assert qax.QAXColIndex('not_exist') == -1
    print('  [PASS] QAXColIndex() - 索引从1开始')

    print('信息类测试通过!\n')


def test_access():
    """测试访问类方法"""
    print('=== 测试访问类 ===')

    qax = Qax([
        ['Alice', 25, 'New York'],
        ['Bob', 30, 'Los Angeles'],
        ['Charlie', 35, 'Chicago'],
    ], columns=['name', 'age', 'city'])

    # 9. GetCell (索引从1开始)
    assert qax.GetCell(1, 1) == 'Alice'
    assert qax.GetCell(2, 2) == 30
    assert qax.GetCell(3, 3) == 'Chicago'
    print('  [PASS] GetCell() - 索引从1开始')

    # 10. GetCell2
    assert qax.GetCell2('name', 1) == 'Alice'
    assert qax.GetCell2('age', 2) == 30
    assert qax.GetCell2('city', 3) == 'Chicago'
    print('  [PASS] GetCell2() - 列名+行号')

    # 11. GetRow
    row1 = qax.GetRow(1)
    assert row1['name'] == 'Alice'
    assert row1['age'] == 25
    assert row1['city'] == 'New York'
    print('  [PASS] GetRow() - 返回字典')

    # 12. GetCol
    names = qax.GetCol('name')
    assert names == ['Alice', 'Bob', 'Charlie']
    ages = qax.GetCol(2)
    assert ages == [25, 30, 35]
    print('  [PASS] GetCol() - 支持列名和列号')

    # 13. GetCols
    result = qax.GetCols(['name', 'city'])
    assert isinstance(result, Qax)
    assert result.QAXCols() == 2
    assert result.QAXColNames() == ['name', 'city']
    print('  [PASS] GetCols() - 返回 Qax')

    print('访问类测试通过!\n')


def test_modify():
    """测试修改类方法"""
    print('=== 测试修改类 ===')

    qax = Qax([
        ['Alice', 25, 'New York'],
        ['Bob', 30, 'Los Angeles'],
    ], columns=['name', 'age', 'city'])

    # 14. SetCell
    result = qax.SetCell(1, 2, 26)
    assert qax.GetCell(1, 2) == 26
    assert isinstance(result, Qax)
    print('  [PASS] SetCell() - 链式调用')

    # 15. SetCell2
    qax.SetCell2('city', 1, 'Boston')
    assert qax.GetCell2('city', 1) == 'Boston'
    print('  [PASS] SetCell2()')

    # 16. NewRow
    qax.NewRow(['Dave', 40, 'Seattle'])
    assert qax.QAXRows() == 3
    assert qax.GetCell(3, 1) == 'Dave'
    print('  [PASS] NewRow() - 新增行')

    # 17. AddCol
    qax.AddCol('gender', 'unknown')
    assert qax.QAXCols() == 4
    assert qax.GetCell2('gender', 1) == 'unknown'
    print('  [PASS] AddCol() - 新增列')

    # 18. DelRow
    qax.DelRow(3)
    assert qax.QAXRows() == 2
    print('  [PASS] DelRow() - 删除行')

    # 19. DelCol
    qax.DelCol('gender')
    assert qax.QAXCols() == 3
    print('  [PASS] DelCol() - 删除列')

    # 20. InsertRow
    qax.InsertRow(2, ['Charlie', 35, 'Chicago'])
    assert qax.QAXRows() == 3
    assert qax.GetCell(2, 1) == 'Charlie'
    print('  [PASS] InsertRow() - 插入行')

    # 21. InsertCol
    qax.InsertCol(2, 'gender', 'unknown')
    assert qax.QAXCols() == 4
    assert qax.QAXColIndex('gender') == 2
    assert qax.GetCell(1, 2) == 'unknown'
    print('  [PASS] InsertCol() - 插入列')

    print('修改类测试通过!\n')


def test_data_operations():
    """测试数据操作类方法"""
    print('=== 测试数据操作类 ===')

    qax = Qax([
        ['Alice', 25, 'New York'],
        ['Bob', 30, 'Los Angeles'],
        ['Charlie', 35, 'Chicago'],
        ['Alice', 25, 'New York'],
    ], columns=['name', 'age', 'city'])

    # 22. QAXSelect
    result = qax.QAXSelect('name', 'age')
    assert isinstance(result, Qax)
    assert result.QAXCols() == 2
    assert result.QAXColNames() == ['name', 'age']
    print('  [PASS] QAXSelect() - 返回 Qax')

    # 23. QAXSort
    result = qax.QAXSort('age', asc=True)
    assert isinstance(result, Qax)
    assert result.GetCell(1, 2) == 25
    assert result.GetCell(4, 2) == 35
    print('  [PASS] QAXSort() - 升序')

    result = qax.QAXSort('age', asc=False)
    assert result.GetCell(1, 2) == 35
    print('  [PASS] QAXSort() - 降序')

    # 24. QAXDistinct
    result = qax.QAXDistinct()
    assert isinstance(result, Qax)
    assert result.QAXRows() == 3
    print('  [PASS] QAXDistinct() - 去重')

    # 25. QAXFilter (lambda)
    result = qax.QAXFilter(lambda r: r['age'] > 28)
    assert isinstance(result, Qax)
    assert result.QAXRows() == 2
    print('  [PASS] QAXFilter() - lambda 过滤')

    # 26. QAXTop
    result = qax.QAXTop(2)
    assert isinstance(result, Qax)
    assert result.QAXRows() == 2
    print('  [PASS] QAXTop() - 取前n行')

    print('数据操作类测试通过!\n')


def test_aggregate():
    """测试聚合类方法"""
    print('=== 测试聚合类 ===')

    qax = Qax([
        ['Alice', 25, 'New York'],
        ['Bob', 30, 'Los Angeles'],
        ['Charlie', 35, 'Chicago'],
        ['Dave', 40, 'Boston'],
    ], columns=['name', 'age', 'city'])

    # 27. QAXSum
    assert qax.QAXSum('age') == 25 + 30 + 35 + 40
    print('  [PASS] QAXSum()')

    # 28. QAXAvg
    assert qax.QAXAvg('age') == (25 + 30 + 35 + 40) / 4
    print('  [PASS] QAXAvg()')

    # 29. QAXCount
    assert qax.QAXCount() == 4
    assert qax.QAXCount('age') == 4
    print('  [PASS] QAXCount()')

    # 30. QAXMax
    assert qax.QAXMax('age') == 40
    print('  [PASS] QAXMax()')

    # 31. QAXMin
    assert qax.QAXMin('age') == 25
    print('  [PASS] QAXMin()')

    print('聚合类测试通过!\n')


def test_conversion():
    """测试转换类方法"""
    print('=== 测试转换类 ===')

    qax = Qax([
        ['Alice', 25, 'New York'],
        ['Bob', 30, 'Los Angeles'],
    ], columns=['name', 'age', 'city'], name='test')

    # 32. QAXToArray
    arr = qax.QAXToArray(include_fields=True)
    assert arr[0] == ['name', 'age', 'city']
    assert len(arr) == 3
    arr2 = qax.QAXToArray(include_fields=False)
    assert len(arr2) == 2
    print('  [PASS] QAXToArray()')

    # 33. QAXToDictList
    dicts = qax.QAXToDictList()
    assert len(dicts) == 2
    assert dicts[0]['name'] == 'Alice'
    assert dicts[1]['age'] == 30
    print('  [PASS] QAXToDictList()')

    # 34. showQax
    result = qax.showQax(max_rows=2)
    assert isinstance(result, Qax)
    print('  [PASS] showQax() - 链式调用')

    print('转换类测试通过!\n')


def test_column_operations():
    """测试列操作类方法"""
    print('=== 测试列操作类 ===')

    qax = Qax([
        ['Alice', '25', 'New York'],
        ['Bob', '30', 'Los Angeles'],
    ], columns=['name', 'age', 'city'])

    # 35. QAXColToNum
    result = qax.QAXColToNum('age')
    assert isinstance(result, Qax)
    assert qax.GetCell(1, 2) == 25
    assert isinstance(qax.GetCell(1, 2), int)
    print('  [PASS] QAXColToNum()')

    # 36. QAXColToStr
    qax.QAXColToStr('age')
    assert qax.GetCell(1, 2) == '25'
    print('  [PASS] QAXColToStr()')

    # 37. SetColName
    qax.SetColName('city', 'location')
    assert 'location' in qax.QAXColNames()
    assert 'city' not in qax.QAXColNames()
    print('  [PASS] SetColName()')

    # 38. SetOrdinal
    qax.SetOrdinal('location', 1)
    assert qax.QAXColIndex('location') == 1
    assert qax.QAXColIndex('name') == 2
    print('  [PASS] SetOrdinal() - 调整列顺序')

    print('列操作类测试通过!\n')


def test_string_operations():
    """测试字符串类方法"""
    print('=== 测试字符串类 ===')

    qax = Qax([
        ['Alice Smith', 'New York,USA'],
        ['Bob Johnson', 'Los Angeles,USA'],
    ], columns=['full_name', 'location'])

    # 39. QAXSubstr
    qax.QAXSubstr('full_name', 1, length=5, new_col='first_name')
    assert qax.GetCell(1, 3) == 'Alice'
    print('  [PASS] QAXSubstr()')

    # 40. QAXSplit
    qax.QAXSplit('location', ',', ['city', 'country'])
    assert qax.GetCell(1, 4) == 'New York'
    assert qax.GetCell(1, 5) == 'USA'
    print('  [PASS] QAXSplit()')

    # 41. QAXConcat
    qax2 = Qax([
        ['Alice', 'Smith'],
        ['Bob', 'Johnson'],
    ], columns=['first', 'last'])
    qax2.QAXConcat(['first', 'last'], 'full', sep=' ')
    assert qax2.GetCell(1, 3) == 'Alice Smith'
    print('  [PASS] QAXConcat() - 带分隔符')

    print('字符串类测试通过!\n')


def test_update():
    """测试更新类方法"""
    print('=== 测试更新类 ===')

    qax = Qax([
        ['Alice', 25, 'New York'],
        ['Bob', 30, 'Los Angeles'],
        ['Charlie', 35, 'Chicago'],
    ], columns=['name', 'age', 'city'])

    # 42. QAXUpdate
    result = qax.QAXUpdate(lambda r: r['age'] > 28, {'city': 'Unknown'})
    assert isinstance(result, Qax)
    assert qax.GetCell(2, 3) == 'Unknown'
    assert qax.GetCell(3, 3) == 'Unknown'
    assert qax.GetCell(1, 3) == 'New York'
    print('  [PASS] QAXUpdate() - 条件更新')

    # 43. QAXReplace
    qax.QAXReplace('Unknown', 'N/A', col='city')
    assert qax.GetCell(2, 3) == 'N/A'
    print('  [PASS] QAXReplace() - 指定列替换')

    # 44. QAXClear
    qax2 = Qax([[1, 2], [3, 4]], columns=['a', 'b'])
    result = qax2.QAXClear()
    assert isinstance(result, Qax)
    assert qax2.QAXRows() == 0
    print('  [PASS] QAXClear() - 清空数据')

    print('更新类测试通过!\n')


def test_chaining():
    """测试链式调用 - @rself 装饰器"""
    print('=== 测试链式调用 (@rself) ===')

    qax = Qax([
        ['Alice', 25, 'New York'],
        ['Bob', 30, 'Los Angeles'],
        ['Charlie', 35, 'Chicago'],
    ], columns=['name', 'age', 'city'])

    # 45. 链式操作返回 Qax 类型
    result = qax.QAXFilter(lambda r: r['age'] > 25).QAXSelect('name', 'city').QAXSort('name')
    assert isinstance(result, Qax)
    assert result.QAXRows() == 2
    assert result.QAXCols() == 2
    print('  [PASS] 链式操作返回 Qax 类型')

    # 46. 修改自身的方法也返回 Qax
    result = qax.SetQaxName('test').AddCol('test_col', 1)
    assert isinstance(result, Qax)
    print('  [PASS] 修改方法链式返回 Qax')

    # 47. Table 方法调用后也返回 Qax
    result = qax.select('name', 'age')
    assert isinstance(result, Qax)
    print('  [PASS] Table 方法调用后返回 Qax (__from_parent__)')

    print('链式调用测试通过!\n')


def test_group():
    """测试分组聚合"""
    print('=== 测试分组聚合 ===')

    qax = Qax([
        ['Alice', 25, 'New York'],
        ['Bob', 30, 'New York'],
        ['Charlie', 35, 'Chicago'],
        ['Dave', 40, 'Chicago'],
        ['Eve', 28, 'Boston'],
    ], columns=['name', 'age', 'city'])

    # 48. QaxGroup
    result = qax.QaxGroup('city', {'age': 'avg'})
    assert isinstance(result, Qax)
    assert result.QAXCols() == 2
    print('  [PASS] QaxGroup() - 分组聚合')

    print('分组聚合测试通过!\n')


def run_all_tests():
    """运行所有测试"""
    print('=' * 60)
    print('Qax 类测试开始')
    print('=' * 60)
    print()

    test_create()
    test_info()
    test_access()
    test_modify()
    test_data_operations()
    test_aggregate()
    test_conversion()
    test_column_operations()
    test_string_operations()
    test_update()
    test_chaining()
    test_group()

    print('=' * 60)
    print('所有测试通过! (48+ 个方法验证)')
    print('=' * 60)


if __name__ == '__main__':
    run_all_tests()
