"""
BUG-189 回归：VDate.simplify_date_ranges 不再因无效日期崩溃。

两处缺陷：
1. _check 只校验格式不校验日期有效性，"2023-02-30" 过正则但 strptime
   抛未捕获 ValueError 使整方法崩溃。
2. 所有输入被 filter 掉后 dates 为空，dates[0] 抛未捕获 IndexError。
"""

import pytest

from vools.datetime.vdate_class import VDate


def test_valid_dates_merged():
    assert VDate.simplify_date_ranges(("2024-01-15", "2024-01-16")) == [
        ("2024-01-15", "2024-01-16")
    ]


def test_invalid_day_returns_empty_not_raise():
    """2023-02-30 过格式正则但日期无效，不应抛 ValueError（BUG-189）。"""
    assert VDate.simplify_date_ranges(("2023-02-30",)) == []


def test_invalid_month_returns_empty():
    """2023-13-01（13 月）不应抛 ValueError。"""
    assert VDate.simplify_date_ranges(("2023-13-01",)) == []


def test_all_filtered_returns_empty_not_index_error():
    """所有输入格式非法被过滤后 dates 为空，不应抛 IndexError（BUG-189）。"""
    assert VDate.simplify_date_ranges(("abc", "xyz")) == []


def test_mixed_invalid_dropped_valid_merged():
    """混合输入：无效日期被跳过，合法日期正常合并。"""
    assert VDate.simplify_date_ranges(
        ("2024-01-15", "2023-02-30", "2024-01-16")
    ) == [("2024-01-15", "2024-01-16")]


def test_empty_input():
    assert VDate.simplify_date_ranges(()) == []


def test_numeric_format():
    assert VDate.simplify_date_ranges(("20240115", "20240116")) == [
        ("2024-01-15", "2024-01-16")
    ]


def test_non_collection_raises_type_error():
    """非 tuple/list/set 输入仍按文档抛 TypeError（不回归）。"""
    with pytest.raises(TypeError):
        VDate.simplify_date_ranges("2024-01-15")