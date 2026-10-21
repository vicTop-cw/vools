"""
回归测试：get_week / VDate.get_week 的 num 方向语义（BUG-242）。

文档口径：正数=未来，负数=过去。
原实现 `w0 - timedelta(days=num*7)` 使正数指向过去、负数指向未来，与文档相反。
"""

import pytest
from vools.datetime import get_week, VDate


class TestGetWeekDirection:
    """BUG-242: get_week num 正数应返回未来周"""

    def test_num_zero_returns_current_week(self):
        """num=0 返回当前周起始日"""
        assert get_week('20240101', num=0) == '20240101'
        assert get_week('2024-01-01', num=0) == '2024-01-01'

    def test_num_positive_returns_future(self):
        """正数 num 应返回未来周（下周）"""
        # 2024-01-01 是周一，下周一是 2024-01-08
        assert get_week('20240101', num=1) == '20240108'
        assert get_week('2024-01-01', num=1) == '2024-01-08'

    def test_num_negative_returns_past(self):
        """负数 num 应返回过去周（上周）"""
        # 2024-01-01 是周一，上周一 2023-12-25
        assert get_week('20240101', num=-1) == '20231225'
        assert get_week('2024-01-01', num=-1) == '2023-12-25'

    def test_num_positive_multiple_weeks(self):
        """正数多周偏移"""
        assert get_week('20240101', num=2) == '20240115'
        assert get_week('20240101', num=52) == '20241230'

    def test_num_negative_multiple_weeks(self):
        """负数多周偏移"""
        assert get_week('20240101', num=-2) == '20231218'
        assert get_week('20240101', num=-52) == '20230102'

    def test_monday_boundary(self):
        """周一作为起始日的语义"""
        # 2024-01-03 是周三，本周一是 2024-01-01
        assert get_week('20240103', num=0) == '20240101'
        # 下周一
        assert get_week('20240103', num=1) == '20240108'

    def test_weekday_param(self):
        """weekday 参数指定一周起始"""
        # 2024-01-01 是周一，若周日(weekday=7)为起始，本周日是 2024-01-07
        assert get_week('20240101', num=0, weekday=7) == '20240107'
        # 上周日
        assert get_week('20240101', num=-1, weekday=7) == '20231231'

    def test_weekday_out_of_range(self):
        """weekday 越界抛出 ValueError"""
        with pytest.raises(ValueError, match=r"weekday 必须在 1-7 之间"):
            get_week('20240101', weekday=0)
        with pytest.raises(ValueError, match=r"weekday 必须在 1-7 之间"):
            get_week('20240101', weekday=8)

    def test_invalid_length(self):
        """长度不合法的字符串抛出 ValueError"""
        with pytest.raises(ValueError, match=r"日期字符串长度必须为 8 或 10"):
            get_week('')
        with pytest.raises(ValueError, match=r"日期字符串长度必须为 8 或 10"):
            get_week('2024010')
        with pytest.raises(ValueError, match=r"日期字符串长度必须为 8 或 10"):
            get_week('202401011')

    def test_none_input_returns_none(self):
        """None 输入返回 None"""
        assert get_week(None) is None


class TestVDateGetWeekDirection:
    """BUG-242: VDate.get_week 正数应返回未来周"""

    def test_vdate_num_zero(self):
        v = VDate('2024-01-01')
        assert v.get_week(num=0) == '2024-01-01'

    def test_vdate_num_positive_returns_future(self):
        v = VDate('2024-01-01')
        assert v.get_week(num=1) == '2024-01-08'

    def test_vdate_num_negative_returns_past(self):
        v = VDate('2024-01-01')
        assert v.get_week(num=-1) == '2023-12-25'

    def test_vdate_preserves_fmt(self):
        """get_week 结果沿用 self.fmt"""
        v = VDate('20240101')
        assert v.get_week(num=1) == '20240108'

    def test_vdate_weekday_validation(self):
        """weekday 越界抛出 ValueError"""
        v = VDate('2024-01-01')
        with pytest.raises(ValueError):
            v.get_week(num=0, weekday=0)
        with pytest.raises(ValueError):
            v.get_week(num=0, weekday=8)
