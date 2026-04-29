"""
数据处理工具测试
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from vools.data import collect,Seq,NONE


class TestDataModule(unittest.TestCase):
    """数据处理模块测试"""

    def test_data_available(self):
        """测试数据模块是否可用"""
        from vools import DATA_AVAILABLE
        self.assertTrue(DATA_AVAILABLE)

    def test_collect(self):
        """测试 collect 函数"""
        result = collect(Seq(range(10)),lambda x: x if x % 2 == 0 else NONE ,list)
        self.assertEqual(result, list(range(0,10,2)))

    

if __name__ == '__main__':
    unittest.main()
