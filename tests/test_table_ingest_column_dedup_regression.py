# -*- coding: utf-8 -*-
"""回归测试：摄入入口的重复列名自动去重（BUG-327 / BUG-326 的入口补全）。

BUG-326 只堵了 `add_col` / `InsertCol` / `set_col_name` 三条**显式操作**路径，
但构造入口与文件读取入口仍可产生重复列名：

    Table([[1, 2]], columns=['id', 'id'])        -> ['id', 'id']（重名）
    'id,id,name\\n1,2,a\\n3,4,b' 的 CSV 读入      -> ['id', 'id', 'name']

重名后按名 API 静默命中其中一列（实测 `column('id')` 返回第二列 `['2','4']`、
`to_num('id')` 只转第二列），而用户通常不知道源文件表头重复。

修复（分层，与 BUG-326 语义一致）：
- **摄入入口**（构造函数 / from_file）：重复列名自动去重为 `id`、`id_2`、`id_3`…
  （与既有 `col_j` 空名兜底同风格，数据与列序不变）；
- **显式操作**（add_col/InsertCol/set_col_name）：保持 ValueError 拒绝。
"""

import pytest

from vools.data.qax import Qax
from vools.data.table import Table


class TestConstructorDedup:
    def test_two_duplicates(self):
        assert Table([[1, 2]], columns=['id', 'id'])._columns == ['id', 'id_2']

    def test_three_duplicates(self):
        assert Table([[1, 2, 3]], columns=['a', 'a', 'a'])._columns == \
            ['a', 'a_2', 'a_3']

    def test_suffix_collision(self):
        # 原生已有 'a_2' -> 生成的名字要避开它
        cols = Table([[1, 2, 3]], columns=['a', 'a', 'a_2'])._columns
        assert len(cols) == len(set(cols)), f'列名仍不唯一: {cols}'

    def test_qax_constructor(self):
        assert Qax([[1, 2]], columns=['id', 'id'])._columns == ['id', 'id_2']

    def test_unique_untouched(self):
        assert Table([[1, 2]], columns=['id', 'name'])._columns == ['id', 'name']

    def test_data_preserved(self):
        t = Table([[1, 2, 'x']], columns=['a', 'a', 'b'])
        assert t.to_list() == [[1, 2, 'x']]


class TestFromFileDedup:
    @pytest.fixture()
    def dup_csv(self, tmp_path):
        p = tmp_path / 'dup.csv'
        p.write_text('id,id,name\n1,2,a\n3,4,b\n', encoding='utf-8')
        return str(p)

    def test_columns_deduped(self, dup_csv):
        t = Table.from_file(dup_csv)
        assert t._columns == ['id', 'id_2', 'name']

    def test_name_lookup_unambiguous(self, dup_csv):
        t = Table.from_file(dup_csv)
        assert t.column('id') == ['1', '3']       # 第一列
        assert t.column('id_2') == ['2', '4']     # 第二列

    def test_data_intact(self, dup_csv):
        t = Table.from_file(dup_csv)
        assert t.to_list() == [['1', '2', 'a'], ['3', '4', 'b']]

    def test_to_num_targets_first_column(self, dup_csv):
        t = Table.from_file(dup_csv)
        t.to_num('id')
        assert t.to_list() == [[1, '2', 'a'], [3, '4', 'b']]


class TestExplicitOperationsStillReject:
    """BUG-326 语义不回退：显式新增/改名仍拒绝重名。"""

    def test_add_col(self):
        with pytest.raises(ValueError):
            Table([[1]], columns=['id']).add_col('id', 0)

    def test_insert_col(self):
        with pytest.raises(ValueError):
            Qax([[1]], columns=['id']).InsertCol(1, 'id')

    def test_rename(self):
        with pytest.raises(ValueError):
            Table([[1, 2]], columns=['a', 'b']).set_col_name(1, 'a')