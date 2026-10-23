# -*- coding: utf-8 -*-
"""回归测试：Table.join 的 join_type 校验（BUG-391）。

`join(..., join_type='bogus')` / `''` / `'LEFT'` 等非法值原先**静默退化**：
落到默认分支后行数按 inner 计算、输出列却按左连接口径（含 t2 键列），
调用方完全看不出参数无效：

    a.join(b, on_str='t1.id = t2.id', join_type='inner')  # 1 行
    a.join(b, on_str='t1.id = t2.id', join_type='')      # 1 行（应为错误）
    a.join(b, on_str='t1.id = t2.id', join_type='LEFT')  # 1 行（应等价 left=2 行）

修复：规范化大小写/空白后校验 ∈ {inner, left, right, outer}，否则 ValueError。
合法类型语义不变。
"""

import pytest

from vools.data.table import Table


@pytest.fixture()
def tables():
    a = Table([[1, 'a'], [2, 'b']], columns=['id', 'v'], name='t1')
    b = Table([[2, 'x'], [3, 'y']], columns=['id', 'w'], name='t2')
    return a, b


class TestValidJoinTypes:
    @pytest.mark.parametrize('jt,expected_rows', [
        ('inner', 1), ('left', 2), ('right', 2), ('outer', 3),
    ])
    def test_join_types(self, tables, jt, expected_rows):
        a, b = tables
        r = a.join(b, on_str='t1.id = t2.id', join_type=jt)
        assert r.rows() == expected_rows

    def test_case_insensitive(self, tables):
        a, b = tables
        # 修复前：'LEFT' 静默当作默认分支（1 行），与 left（2 行）不一致
        assert a.join(b, on_str='t1.id = t2.id', join_type='LEFT').rows() == 2

    def test_whitespace_tolerated(self, tables):
        a, b = tables
        assert a.join(b, on_str='t1.id = t2.id', join_type=' left ').rows() == 2


class TestInvalidJoinTypes:
    @pytest.mark.parametrize('jt', ['bogus', '', ' ', 'full', None, 123])
    def test_rejected(self, tables, jt):
        a, b = tables
        with pytest.raises(ValueError) as ei:
            a.join(b, on_str='t1.id = t2.id', join_type=jt)
        assert 'join_type' in str(ei.value)


class TestOtherJoinPathsUnchanged:
    def test_auto_common_column(self, tables):
        a, b = tables
        # on_str 省略 → 自动用同名列 'id'
        assert a.join(b)._columns == ['t1_id', 't1_v', 't2_w']

    def test_select_fields(self, tables):
        a, b = tables
        r = a.join(b, select_fields=['t1.id', 't2.w'], on_str='t1.id = t2.id')
        assert r._columns == ['t1_id', 't2_w']
        assert r._data == [[2, 'x']]

    def test_missing_key_column_raises(self, tables):
        a, b = tables
        with pytest.raises(KeyError):
            a.join(b, on_str='t1.nope = t2.id')