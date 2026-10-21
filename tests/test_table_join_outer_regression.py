# -*- coding: utf-8 -*-
"""回归测试：Table.join 的 right/outer 语义与 first 参数（BUG-277）。

① join_type 声明支持 'inner','left','right','outer'，但原实现连接主循环
   **从不补右表未匹配行**——right 实际等同 inner、outer 实际等同 left，
   静默丢失右表独有数据。
② 附带修复：`first=True`（只返回第一个匹配）原实现在处理完该 self 行的
   全部匹配后才跳出，多个匹配仍返回多行。

修复：记录命中过的 other key，right/outer 循环后补齐未命中右表行
（self 侧 None + 全部 other_cols）；first=True 在首个匹配后立即跳出
（right/outer 不做补齐）。
"""

from vools.data.table import Table


def _a():
    return Table([[1, 'x'], [2, 'y']], columns=['id', 'val'])


def _b():
    return Table([[1, 'A'], [3, 'C']], columns=['id', 'other'])


class TestJoinTypes:
    def test_inner(self):
        r = _a().join(_b(), on_str='id', join_type='inner')
        assert r.rows() == 1
        assert r._data[0] == [1, 'x', 'A']

    def test_left(self):
        r = _a().join(_b(), on_str='id', join_type='left')
        assert r.rows() == 2
        assert r._data[1] == [2, 'y', None, None]

    def test_right_includes_right_only_row(self):
        # 修复前：rows=1（等同 inner）
        r = _a().join(_b(), on_str='id', join_type='right')
        assert r.rows() == 2
        assert [None, None, 3, 'C'] in r._data

    def test_outer_includes_both_sides(self):
        # 修复前：rows=2（等同 left）
        r = _a().join(_b(), on_str='id', join_type='outer')
        assert r.rows() == 3
        assert [2, 'y', None, None] in r._data
        assert [None, None, 3, 'C'] in r._data

    def test_row_width_matches_header(self):
        for how in ('inner', 'left', 'right', 'outer'):
            r = _a().join(_b(), on_str='id', join_type=how)
            assert all(len(row) == len(r.columns()) for row in r._data), how

    def test_right_join_empty_left(self):
        empty = Table([], columns=['id', 'val'])
        r = empty.join(_b(), on_str='id', join_type='right')
        assert r.rows() == 2


class TestFirstParam:
    def test_first_returns_single_match(self):
        t1 = Table([[1, 'x']], columns=['id', 'val'])
        t2 = Table([[1, 'A'], [1, 'B']], columns=['id', 'other'])
        r = t1.join(t2, on_str='id', join_type='left', first=True)
        # 修复前：返回 2 行（该 self 行的全部匹配）
        assert r.rows() == 1

    def test_first_across_self_rows(self):
        t1 = Table([[1, 'x'], [2, 'y']], columns=['id', 'val'])
        t2 = Table([[1, 'A'], [2, 'B']], columns=['id', 'other'])
        assert t1.join(t2, on_str='id', join_type='inner', first=True).rows() == 1
        assert t1.join(t2, on_str='id', join_type='inner').rows() == 2

    def test_first_right_no_padding(self):
        t1 = Table([[1, 'x']], columns=['id', 'val'])
        t2 = Table([[1, 'A'], [3, 'C']], columns=['id', 'other'])
        assert t1.join(t2, on_str='id', join_type='right', first=True).rows() == 1