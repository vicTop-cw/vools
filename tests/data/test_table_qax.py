"""
vools.data.Table QAX 风格 API 测试

测试 Table 类新增的 QAX 风格方法。
"""

import unittest
import tempfile
import os
from vools.data import Table, Row, Column


class TestTableBasic(unittest.TestCase):
    """基本功能测试"""
    
    def setUp(self):
        self.table = Table([
            ['Alice', 25, 'New York'],
            ['Bob', 30, 'Los Angeles'],
            ['Charlie', 35, 'Chicago'],
        ], columns=['name', 'age', 'city'], name='users')
    
    def test_creation(self):
        """测试创建"""
        self.assertEqual(self.table.rows(), 3)
        self.assertEqual(self.table.cols(), 3)
        self.assertEqual(self.table.name(), 'users')
        self.assertEqual(self.table.columns(), ['name', 'age', 'city'])
    
    def test_at(self):
        """测试 at 访问"""
        self.assertEqual(self.table.at(0, 0), 'Alice')
        self.assertEqual(self.table.at(1, 'age'), 30)
        self.assertEqual(self.table.at(2, 'city'), 'Chicago')
    
    def test_row(self):
        """测试 row 方法"""
        row = self.table.row(0)
        self.assertEqual(row['name'], 'Alice')
        self.assertEqual(row['age'], 25)


class TestTableQAX(unittest.TestCase):
    """QAX 风格 API 测试"""
    
    def setUp(self):
        self.table = Table([
            ['Alice', 25, 'New York'],
            ['Bob', 30, 'Los Angeles'],
            ['Charlie', 35, 'Chicago'],
        ], columns=['name', 'age', 'city'], name='users')
    
    def test_get_cell(self):
        """测试 get_cell"""
        self.assertEqual(self.table.get_cell(0, 0), 'Alice')
        self.assertEqual(self.table.get_cell(0, 0, 'N/A'), 'Alice')
        self.assertEqual(self.table.get_cell(10, 0, 'N/A'), 'N/A')  # 越界返回默认值
    
    def test_get_cell2(self):
        """测试 get_cell2 (按列名)"""
        self.assertEqual(self.table.get_cell2(0, 'name'), 'Alice')
        self.assertEqual(self.table.get_cell2(1, 'age'), 30)
    
    def test_set_cell(self):
        """测试 set_cell"""
        self.table.set_cell(0, 1, 26)
        self.assertEqual(self.table.at(0, 1), 26)
    
    def test_set_cell2(self):
        """测试 set_cell2 (按列名)"""
        self.table.set_cell2(0, 'name', 'Alicia')
        self.assertEqual(self.table.at(0, 0), 'Alicia')
    
    def test_get_row(self):
        """测试 get_row 返回 Row 对象"""
        row = self.table.get_row(1)
        self.assertIsInstance(row, Row)
        self.assertEqual(row['name'], 'Bob')
        self.assertEqual(row['age'], 30)
    
    def test_row_object_setitem(self):
        """测试 Row 对象赋值"""
        row = self.table.get_row(0)
        row['age'] = 26
        self.assertEqual(self.table.at(0, 1), 26)
    
    def test_del_row(self):
        """测试 del_row"""
        self.table.del_row(0)
        self.assertEqual(self.table.rows(), 2)
        self.assertEqual(self.table.at(0, 0), 'Bob')  # 现在第一行是 Bob
    
    def test_new_row(self):
        """测试 new_row"""
        row = self.table.new_row()
        row['name'] = 'David'
        row['age'] = 40
        row['city'] = 'Houston'
        self.assertEqual(self.table.rows(), 4)
        self.assertEqual(self.table.at(3, 0), 'David')
    
    def test_add_col(self):
        """测试 add_col"""
        self.table.add_col('score', 100)
        self.assertEqual(self.table.cols(), 4)
        self.assertEqual(self.table.column('score'), [100, 100, 100])
    
    def test_del_col(self):
        """测试 del_col"""
        self.table.del_col('age')
        self.assertEqual(self.table.cols(), 2)
        self.assertEqual(self.table.columns(), ['name', 'city'])
    
    def test_get_cols(self):
        """测试 get_cols"""
        result = self.table.get_cols(col_names=['name', 'age'])
        self.assertEqual(result.cols(), 2)
        self.assertEqual(result.rows(), 3)
    
    def test_set_col_name(self):
        """测试 set_col_name"""
        self.table.set_col_name(1, 'age2')
        self.assertEqual(self.table.columns()[1], 'age2')
    
    def test_set_ordinal(self):
        """测试 set_ordinal"""
        self.table.set_ordinal('city', 0)
        self.assertEqual(self.table.columns()[0], 'city')
    
    def test_name(self):
        """测试名称属性"""
        self.assertEqual(self.table.name(), 'users')
        self.table.set_name('people')
        self.assertEqual(self.table.name(), 'people')
    
    def test_to_array(self):
        """测试 to_array"""
        arr = self.table.to_array(include_fields=True)
        self.assertEqual(len(arr), 4)  # 1 header + 3 rows
        self.assertEqual(arr[0], ['name', 'age', 'city'])
        
        arr2 = self.table.to_array(include_fields=False)
        self.assertEqual(len(arr2), 3)
        self.assertEqual(arr2[0], ['Alice', 25, 'New York'])


class TestTableChain(unittest.TestCase):
    """链式操作测试"""
    
    def setUp(self):
        self.table = Table([
            ['Alice', 25, 'New York'],
            ['Bob', 30, 'Los Angeles'],
            ['Charlie', 35, 'Chicago'],
            ['David', 30, 'Houston'],
        ], columns=['name', 'age', 'city'])
    
    def test_where(self):
        """测试 where"""
        result = self.table.where('age > 25')
        self.assertEqual(result.rows(), 3)
    
    def test_select(self):
        """测试 select"""
        result = self.table.select('name', 'age')
        self.assertEqual(result.cols(), 2)
        self.assertEqual(result.columns(), ['name', 'age'])
    
    def test_sort(self):
        """测试 sort"""
        result = self.table.sort('age', reverse=True)
        self.assertEqual(result.at(0, 'name'), 'Charlie')  # 35岁最高
    
    def test_distinct(self):
        """测试 distinct"""
        result = self.table.select('age').distinct()
        self.assertEqual(result.rows(), 3)  # 有 25, 30, 35 三个不同值


class TestTableMerge(unittest.TestCase):
    """合并操作测试"""
    
    def test_merge_vertical(self):
        """测试纵向合并"""
        t1 = Table([[1], [2]], columns=['a'])
        t2 = Table([[3], [4]], columns=['a'])
        result = t1.merge(t2, vertical=True)
        self.assertEqual(result.rows(), 4)
    
    def test_merge_horizontal(self):
        """测试横向合并"""
        t1 = Table([[1, 2]], columns=['a', 'b'])
        t2 = Table([[3, 4]], columns=['c', 'd'])
        result = t1.merge(t2, vertical=False)
        self.assertEqual(result.cols(), 4)


class TestTableStringOps(unittest.TestCase):
    """字符串操作测试"""
    
    def test_substr(self):
        """测试 substr"""
        table = Table([
            ['hello world', 100],
            ['foo bar', 200],
        ], columns=['text', 'value'])
        table.substr('sub', 'text', 1, 5)  # 1-5 是 exclusive，即取索引 0-4
        self.assertEqual(table.column('sub'), ['hello', 'foo b'])
    
    def test_concat(self):
        """测试 concat"""
        table = Table([
            ['A', 'B', 1],
            ['C', 'D', 2],
        ], columns=['first', 'second', 'num'])
        table.concat('combined', ['first', 'second'])
        self.assertEqual(table.column('combined'), ['AB', 'CD'])


class TestTableColumn(unittest.TestCase):
    """Column 对象测试"""
    
    def setUp(self):
        self.table = Table([
            ['Alice', 25, 'New York'],
            ['Bob', 30, 'Los Angeles'],
            ['Charlie', 35, 'Chicago'],
        ], columns=['name', 'age', 'city'])
    
    def test_get_col_returns_column(self):
        """测试 get_col 返回 Column 对象"""
        col = self.table.get_col('age')
        self.assertIsInstance(col, Column)
    
    def test_get_col_by_index(self):
        """测试按索引获取列"""
        col = self.table.get_col(1)
        self.assertEqual(col.name(), 'age')
    
    def test_col_getitem(self):
        """测试 Column.__getitem__"""
        col = self.table.get_col('age')
        self.assertEqual(col[0], 25)
        self.assertEqual(col[1], 30)
        self.assertEqual(col[2], 35)
    
    def test_col_setitem(self):
        """测试 Column.__setitem__"""
        col = self.table.get_col('age')
        col[0] = 26
        self.assertEqual(self.table.at(0, 1), 26)
    
    def test_col_len(self):
        """测试 Column.__len__"""
        col = self.table.get_col('age')
        self.assertEqual(len(col), 3)
    
    def test_col_iter(self):
        """测试 Column.__iter__"""
        col = self.table.get_col('age')
        values = list(col)
        self.assertEqual(values, [25, 30, 35])
    
    def test_col_name(self):
        """测试 Column.name()"""
        col = self.table.get_col('name')
        self.assertEqual(col.name(), 'name')
    
    def test_col_index(self):
        """测试 Column.index()"""
        col = self.table.get_col('city')
        self.assertEqual(col.index(), 2)
    
    def test_col_to_list(self):
        """测试 Column.to_list()"""
        col = self.table.get_col('name')
        self.assertEqual(col.to_list(), ['Alice', 'Bob', 'Charlie'])
    
    def test_col_sum(self):
        """测试 Column.sum()"""
        col = self.table.get_col('age')
        self.assertEqual(col.sum(), 90)  # 25+30+35
    
    def test_col_avg(self):
        """测试 Column.avg()"""
        col = self.table.get_col('age')
        self.assertAlmostEqual(col.avg(), 30.0)
    
    def test_col_min(self):
        """测试 Column.min()"""
        col = self.table.get_col('age')
        self.assertEqual(col.min(), 25)
    
    def test_col_max(self):
        """测试 Column.max()"""
        col = self.table.get_col('age')
        self.assertEqual(col.max(), 35)
    
    def test_col_count(self):
        """测试 Column.count()"""
        col = self.table.get_col('age')
        self.assertEqual(col.count(), 3)
    
    def test_col_distinct(self):
        """测试 Column.distinct()"""
        col = self.table.get_col('age')
        self.assertEqual(col.distinct(), [25, 30, 35])


class TestTableIO(unittest.TestCase):
    """IO 操作测试"""
    
    def test_to_file(self):
        """测试 to_file"""
        table = Table([
            ['Alice', 25],
            ['Bob', 30],
        ], columns=['name', 'age'])
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
            filepath = f.name
        
        try:
            result = table.to_file(filepath)
            self.assertTrue(result)
            
            # 读取验证
            with open(filepath, 'r') as f:
                content = f.read()
            self.assertIn('name,age', content)
            self.assertIn('Alice,25', content)
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)


if __name__ == '__main__':
    unittest.main(verbosity=2)
