"""
vicDate 工具类的单元测试
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from datetime import datetime, date, timedelta
from vools.datetime import vicDate, VDate


class TestVicDateBasic:
    """测试 vicDate 基本功能"""

    def test_vicdate_init_default(self):
        """测试默认初始化（使用当前日期）"""
        vd = vicDate()
        today = datetime.now().date()