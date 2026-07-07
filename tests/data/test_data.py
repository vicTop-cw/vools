"""
数据处理工具测试
"""
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

    def test_NONE(self):
        """测试 NONE 常量"""
        self.assertEqual(NONE, NONE)
        self.assertIsNot(NONE, None)
        
        for i in NONE:
            print(i)

if __name__ == '__main__':
    # print(NONE.sdsf().s())
    unittest.main()
    
