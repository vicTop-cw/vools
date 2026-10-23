# -*- coding: utf-8 -*-
"""回归测试：join 的 on_str 严格解析、支持异名键列（BUG-328）。

原实现：
    match = re.match(r'(\\w+)\\.(\\w+)\\s*=\\s*(\\w+)\\.(\\w+)', on_str)
    if match: on_col = match.group(2)      # 只取左侧列名，两侧共用
    else:     on_col = on_str              # 解析失败整串当列名

两个后果（都会让 key 恒为 None → 走 other_index[None] 全匹配分支）：

A. `on_str='id = id'`（不符合模板）→ **静默笛卡尔积**（2×2=4 行）；
B. `on_str='t1.id = t2.bid'`（两表键列不同名——显式写 on_str 的典型理由）
   → 取 'id' 当两侧共用键，右表无 'id' → key None → 同样静默笛卡尔积；
   若右表恰好也有同名但不相关的 'id' 列 → 用错列连接，静默错配。

修复：`re.fullmatch` 解析出 (左别名,左列,右别名,右列)，按别名（t1/t2/table1/
table2/表 name）或列归属判定两侧键列，**分别**用于左/右键；解析失败、别名无法
判定、键列不存在均显式报错（ValueError/KeyError）。
"""

import pytest

from vools.data.table import Table


@pytest.fixture()
def a():
    return Table([[1, 'x', 'A'], [2, 'y', 'B']],
                 columns=['id', 'name', 'aval'], name='t1')


@pytest.fixture()
def b():
    return Table([[1, 'x', 'P'], [3, 'z', 'Q']],
                 columns=['id', 'name', 'bval'], name='t2')


@pytest.fixture()
def c():
    # 键列名与 a 不同（bid 对应 a.id）
    return Table([[1, 'P'], [3, 'Q']], columns=['bid', 'bval'], name='t2')


class TestStrictParsing:
    @pytest.mark.parametrize('bad', [
        'id = id',                 # 缺别名
        't1.id == t2.id',          # 双等号
        '',                        # 空串
        't1.id = t2.id and 1=1',   # 多余条件
        'nope',                    # 不存在的列名
    ])
    def test_malformed_on_str_raises(self, a, b, bad):
        # 修复前：退化为笛卡尔积（a.rows * b.rows 行）。
        # 简化格式下非法串按"列名"处理 -> KeyError；带别名格式 -> ValueError。
        with pytest.raises((ValueError, KeyError)):
            a.join(b, on_str=bad)

    def test_missing_key_column_raises(self, a, b):
        with pytest.raises(KeyError):
            a.join(b, on_str='t1.nope = t2.id')

    def test_simplified_single_column_format(self, a, b):
        # 简化格式（并发扩展）：裸列名，两表都必须有该列
        out = a.join(b, on_str='id')
        assert out.rows() == 1
        assert out._columns[0] == 't1_id'

    def test_simplified_missing_column_raises(self, a, b):
        with pytest.raises(KeyError):
            a.join(b, on_str='nope')


class TestSameNameJoin:
    @pytest.mark.parametrize('on_str', [
        't1.id = t2.id',
        'table1.id = table2.id',
        't2.id = t1.id',          # 反序书写
    ])
    def test_alias_variants(self, a, b, on_str):
        out = a.join(b, on_str=on_str)
        assert out._columns == ['t1_id', 't1_name', 't1_aval',
                                't2_name', 't2_bval']
        assert out.rows() == 1

    def test_alias_by_table_name(self, a, b):
        out = a.join(b, on_str='t1.id = t2.id')
        assert out._data == [[1, 'x', 'A', 'x', 'P']]


class TestDifferentKeyColumnNames:
    """核心场景：显式 on_str 的常用理由是两表键列不同名。"""

    def test_inner(self, a, c):
        out = a.join(c, on_str='t1.id = t2.bid')
        assert out._columns == ['t1_id', 't1_name', 't1_aval', 't2_bval']
        assert out._data == [[1, 'x', 'A', 'P']]

    def test_inner_reversed(self, a, c):
        out = a.join(c, on_str='t2.bid = t1.id')
        assert out._data == [[1, 'x', 'A', 'P']]

    def test_left(self, a, c):
        out = a.join(c, on_str='t1.id = t2.bid', join_type='left')
        assert out.rows() == 2
        assert out._data[1] == [2, 'y', 'B', None, None]

    def test_outer(self, a, c):
        out = a.join(c, on_str='t1.id = t2.bid', join_type='outer')
        assert out.rows() == 3
        assert out._data[-1] == [None, None, None, 3, 'Q']

    def test_no_silent_cross_join(self, a, c):
        # 修复前：返回 len(a)*len(c) = 4 行
        out = a.join(c, on_str='t1.id = t2.bid')
        assert out.rows() == 1


class TestOtherPathsUnchanged:
    def test_auto_common_column(self, a, b):
        out = a.join(b)
        assert out.rows() == 1

    def test_first_true(self, a, b):
        out = a.join(b, on_str='t1.id = t2.id', first=True)
        assert out.rows() == 1

    def test_select_fields(self, a, b):
        out = a.join(b, select_fields=['t1.id', 't2.bval'],
                     on_str='t1.id = t2.id')
        assert out._columns == ['t1_id', 't2_bval']
        assert out._data == [[1, 'P']]