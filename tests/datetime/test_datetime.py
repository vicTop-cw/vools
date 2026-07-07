"""
日期时间工具测试
"""
import unittest
from vools import datetime


class TestDatetimeModule(unittest.TestCase):
    """日期时间模块测试"""

    def test_datetime_available(self):
        """测试日期时间模块是否可用"""
        from vools import DATETIME_AVAILABLE
        self.assertTrue(DATETIME_AVAILABLE)

    def test_range_import(self):
        """测试 range 导入"""
        try:
            from vools.datetime.utils import get_date_range, parse_date_string
            self.assertIsNotNone(get_date_range)
            self.assertIsNotNone(parse_date_string)
        except ImportError as e:
            self.skipTest(f"range not available: {e}")

    def test_utils_import(self):
        """测试 utils 导入"""
        try:
            from vools.datetime.utils import get_recently_months, get_recently_weeks, get_recently_days
            self.assertIsNotNone(get_recently_months)
            self.assertIsNotNone(get_recently_weeks)
            self.assertIsNotNone(get_recently_days)
        except ImportError as e:
            self.skipTest(f"utils not available: {e}")

    def test_get_recently_months(self):
        """测试 get_recently_months 功能"""
        try:
            from vools.datetime.utils import get_recently_months
            result = get_recently_months("2024-01-15", 3)
            self.assertIsInstance(result, list)
            self.assertGreater(len(result), 0)
        except ImportError as e:
            self.skipTest(f"get_recently_months not available: {e}")


def test_vicDate():
    """测试 vicDate 类"""
    from vools.datetime import vDate
    date = vDate()
    result = date.__dir__()
    assert result is not None, "vicDate __dir__() should not return None"
    assert isinstance(result, list), "vicDate __dir__() should return a list"
    assert len(result) > 0, "vicDate __dir__() should return non-empty list"
    print("vicDate __dir__() 返回了", len(result), "个属性")

if __name__ == '__main__':
    test_vicDate()
    unittest.main()
