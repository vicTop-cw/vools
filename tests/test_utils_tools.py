# -*- coding: utf-8 -*-
"""测试 vools.utils.tools — 字符串/正则/日期工具。

注：测试断言反映了现有实现的实际语义（与 pandas 等库的同类函数
并不完全等价），因此这些断言可视为对当前行为的锁定（contract test）。
"""

import datetime

__all__ = [
    "TestRegexpUtils",
    "TestStringUtils",
    "TestExcelUtils",
    "TestDateUtils",
    "TestOtherUtils",
]


class TestRegexpUtils:
    """正则工具测试（锁定现有实现语义）。"""

    def test_findall(self):
        from vools.utils.tools import regexp_findall
        assert regexp_findall(r"\d+", "a1b22c333") == ["1", "22", "333"]
        assert regexp_findall(r"x", "hello") == []

    def test_replace(self):
        from vools.utils.tools import regexp_replace
        assert regexp_replace(r"\d+", "a1b2c3", "-") == "a-b-c-"
        assert regexp_replace(r"\d+", "abc", "-") == "abc"

    def test_like(self):
        from vools.utils.tools import regexp_like
        # complete_matching=True → 整个源串必须等于唯一匹配
        assert regexp_like(r"\d+", "abc123") is False
        assert regexp_like(r"\d+", "abc") is False
        assert regexp_like(r"abc", "abc") is True
        # complete_matching=False → 只需存在匹配
        assert regexp_like(r"\d+", "abc123", complete_matching=False) is True
        assert regexp_like(r"\d+", "abc", complete_matching=False) is False

    def test_substr(self):
        from vools.utils.tools import regexp_substr
        # occurrence=0 → 第一个匹配
        assert regexp_substr(r"\d+", "a1b22c333") == "1"
        assert regexp_substr(r"\d+", "a1b22c333", occurrence=2) == "333"

    def test_count(self):
        from vools.utils.tools import regexp_count
        assert regexp_count(r"a", "banana") == 3
        assert regexp_count(r"x", "banana") == 0

    def test_instr(self):
        from vools.utils.tools import regexp_instr
        # 0-based 起始位置；无匹配返回 -1
        assert regexp_instr(r"\d+", "a1b2c3") == 1
        assert regexp_instr(r"\d+", "abc") == -1
        assert regexp_instr(r"\d+", "a1b2c3", occurrence=2) == 5

    def test_split(self):
        from vools.utils.tools import regexp_split
        # 简单分隔符
        assert regexp_split(r",", "a,b,c") == ["a", "b", "c"]
        assert regexp_split(r",", "a,b,c") == ["a", "b", "c"]


class TestStringUtils:
    """字符串工具测试。"""

    def test_trim(self):
        from vools.utils.tools import trim
        assert trim("  hello  ") == "hello"
        # left=False → 只修剪右侧
        assert trim("  hello  ", left=False) == "  hello"
        # right=False → 只修剪左侧
        assert trim("  hello  ", right=False) == "hello  "
        # 指定字符集
        assert trim("-hello-", chars="-") == "hello"
        # 都不修剪
        assert trim("  hello  ", left=False, right=False) == "  hello  "

    def test_shift(self):
        from vools.utils.tools import shift
        # 正数 num → 元素右移，fill_value 从左侧补入
        assert list(shift([1, 2, 3], 1)) == [None, 1, 2]
        assert list(shift([1, 2, 3], 1, fill_value=0)) == [0, 1, 2]
        # 负数 num → 元素左移，fill_value 从右侧补入
        assert list(shift([1, 2, 3], -1, fill_value=0)) == [2, 3, 0]
        # cycle=True → 纯轮转
        assert list(shift([1, 2, 3], 1, cycle=True)) == [2, 3, 1]
        assert list(shift([1, 2, 3], -1, cycle=True)) == [3, 1, 2]
        # num=0 → 无变化
        assert list(shift([1, 2, 3], 0)) == [1, 2, 3]

    def test_static_vars(self):
        from vools.utils.tools import static_vars

        @static_vars(count=0)
        def counter():
            counter.count += 1
            return counter.count

        assert counter() == 1
        assert counter() == 2

    def test_get_char(self):
        from vools.utils.tools import get_char
        # 现有实现：返回第一个替换后的字符串（不是 join）
        assert get_char("abc", rep="-") == "-"

    def test_union_ordered_collection(self):
        from vools.utils.tools import union_ordered_collection
        assert union_ordered_collection([1, 2, 2, 3, 1]) == [1, 2, 3]

    def test_build_text(self):
        from vools.utils.tools import build_text
        # 空 dct/lst 时返回空串
        assert build_text() == ""
        # 给定 dct 时产生文本
        result = build_text(dct={"name": "test"})
        assert isinstance(result, str)

    def test_generate_lambda(self):
        from vools.utils.tools import generate_lambda
        f = generate_lambda("x + 1")
        assert f(1) == 2
        # 多参数：param_symbols 用逗号分隔或列表
        g = generate_lambda("a + b", param_symbols=["a", "b"])
        assert g(2, 3) == 5
        h = generate_lambda("a + b", param_symbols="a,b")
        assert h(2, 3) == 5

    def test_calculate_runtime(self):
        from vools.utils.tools import calculate_runtime

        @calculate_runtime
        def identity():
            return 42

        assert identity() == 42

    def test_aggregate_json_keys(self):
        from vools.utils.tools import aggregate_json_keys
        # 返回无序 union（set 语义）
        result = aggregate_json_keys([["a", "b"], ["b", "c"]])
        assert set(result) == {"a", "b", "c"}

    def test_get_json_keys(self):
        from vools.utils.tools import get_json_keys
        keys = get_json_keys('{"a": 1, "b": {"c": 2}}')
        assert "a" in keys

    def test_transfer(self):
        from vools.utils.tools import transfer

        @transfer()
        def f():
            return 1

        assert f() == 1

    def test_transferCols(self):
        from vools.utils.tools import transferCols
        r = transferCols(["a", "b", "c"])
        assert isinstance(r, list)


class TestExcelUtils:
    """Excel 列名互转测试。"""

    def test_column_to_number(self):
        from vools.utils.tools import excel_column_to_number
        assert excel_column_to_number("A") == 1
        assert excel_column_to_number("Z") == 26
        assert excel_column_to_number("AA") == 27

    def test_number_to_column(self):
        from vools.utils.tools import excel_number_to_column
        assert excel_number_to_column(1) == "A"
        assert excel_number_to_column(26) == "Z"
        assert excel_number_to_column(27) == "AA"


class TestDateUtils:
    """日期工具测试。"""

    def test_offset_date_with_str(self):
        from vools.utils.tools import offset_date
        # 现有实现期望字符串
        r = offset_date("20240101", 1)
        assert r == "20240102"

    def test_get_date_seq(self):
        from vools.utils.tools import get_date_seq
        seq = get_date_seq(nums=3, date_type="day", fmt="%m%d")
        assert len(seq) == 3

    def test_get_py_fmt(self):
        from vools.utils.tools import get_py_fmt
        assert "%Y" in get_py_fmt("yyyy")
        assert "%m" in get_py_fmt("MM")


class TestOtherUtils:
    """其他工具测试。"""

    def test_get_index_cols_1based(self):
        from vools.utils.tools import get_index_cols
        cols = ["a", "b", "c"]
        # 现有实现是 1-based 索引
        result = get_index_cols(cols, 1, 3)
        assert result == [cols[0], cols[2]]

    def test_to_ordered_dict(self):
        from vools.utils.tools import toOrderedDict
        od = toOrderedDict([1, 2, 3])
        assert list(od.values()) == [1, 2, 3]

    def test_generate_random_field_name(self):
        from vools.utils.tools import generate_random_field_name
        name = generate_random_field_name(word_count=2, max_length=5)
        assert len(name) <= 5 * 2 + 1

    def test_check_no_overlap(self):
        from vools.utils.tools import check_no_overlap
        # 字符串列表中互不包含 → True
        assert check_no_overlap(["a", "b", "c"]) is True
        # "ab" 包含 "b" → False
        assert check_no_overlap(["ab", "b"]) is False
        # 单元素列表 → True（无对比项）
        assert check_no_overlap(["a"]) is True
