"""
数据处理工具测试
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from vools import data


class TestDataModule(unittest.TestCase):
    """数据处理模块测试"""

    def test_data_available(self):
        """测试数据模块是否可用"""
        from vools import DATA_AVAILABLE
        self.assertTrue(DATA_AVAILABLE)

    def test_tabulate_import(self):
        """测试 tabulate 导入"""
        try:
            from vools.data.tabulate import tabulate
            self.assertIsNotNone(tabulate)
        except ImportError:
            self.skipTest("tabulate not available")

    def test_tabulate_basic(self):
        """测试 tabulate 基本功能"""
        try:
            from vools.data.tabulate import tabulate
            table = [["Alice", 24], ["Bob", 19]]
            headers = ["Name", "Age"]
            result = tabulate(table, headers=headers)
            self.assertIn("Alice", result)
            self.assertIn("Bob", result)
        except ImportError:
            self.skipTest("tabulate not available")

    def test_transform_import(self):
        """测试 transform 导入"""
        try:
            from vools.data.transform import to_spark_df
            self.assertIsNotNone(to_spark_df)
        except ImportError:
            self.skipTest("transform not available (requires pandas/pyspark)")

    def test_excel_import(self):
        """测试 excel 导入"""
        try:
            from vools.data.excel import write_excel, delete_obsolete_files
            self.assertIsNotNone(write_excel)
            self.assertIsNotNone(delete_obsolete_files)
        except ImportError:
            self.skipTest("excel not available (requires pandas/openpyxl)")


if __name__ == '__main__':
    unittest.main()
