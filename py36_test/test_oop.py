"""
OOP 工具测试
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from vools import oop


class TestOOPModule(unittest.TestCase):
    """OOP 模块测试"""

    def test_oop_available(self):
        """测试 OOP 模块是否可用"""
        from vools import OOP_AVAILABLE
        self.assertTrue(OOP_AVAILABLE)

    def test_extend_import(self):
        """测试 extend 导入"""
        try:
            from vools.oop.extend import clone, g, arrow_func
            self.assertIsNotNone(clone)
            self.assertIsNotNone(g)
            self.assertIsNotNone(arrow_func)
        except ImportError as e:
            self.skipTest(f"extend not available: {e}")

    def test_selector_import(self):
        """测试 selector 导入"""
        try:
            from vools.oop.selector import Selector, overloads
            self.assertIsNotNone(Selector)
            self.assertIsNotNone(overloads)
        except ImportError as e:
            self.skipTest(f"selector not available: {e}")

    def test_calltype_import(self):
        """测试 calltype 导入"""
        try:
            from vools.oop.calltype import get_callable_type, create_fake
            self.assertIsNotNone(get_callable_type)
            self.assertIsNotNone(create_fake)
        except ImportError as e:
            self.skipTest(f"calltype not available: {e}")


if __name__ == '__main__':
    unittest.main()
