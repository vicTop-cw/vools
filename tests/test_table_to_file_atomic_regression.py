# -*- coding: utf-8 -*-
"""回归测试：Table.to_file 原子写 + 失败可见（BUG-355）。

原实现：

    try:
        with open(filepath, 'w', encoding=encoding, newline='') as f:
            ...  # 先写表头，再逐行写数据
        return True
    except Exception:
        return False

两个问题：
1. **失败原因全部丢失**——目录不存在 / 权限 / 编码不支持都只得到 `False`，
   无从判断；
2. **编码失败会残留半写文件**：文件已创建且表头已写入，写数据行时才抛
   UnicodeEncodeError → 目标路径留下一个只有表头的坏文件，而函数返回 False。

修复：同目录临时文件 + `os.replace` 原子替换；失败时清理临时文件并
`warnings.warn`（返回值契约仍为 True/False）。

往返语义（含逗号/引号/换行的字段、GBK、tab 分隔、空表）不变。
"""

import glob
import os
import warnings

import pytest

from vools.data.table import Table


@pytest.fixture()
def workdir(tmp_path):
    return tmp_path


class TestAtomicWrite:
    def test_success(self, workdir):
        p = workdir / 'ok.csv'
        t = Table([['1', 'a']], columns=['id', 'name'])
        assert t.to_file(str(p)) is True
        assert Table.from_file(str(p))._data == [['1', 'a']]

    def test_no_temp_files_left(self, workdir):
        p = workdir / 'ok.csv'
        Table([['1']], columns=['a']).to_file(str(p))
        assert glob.glob(str(workdir / '.vools_tbl_*')) == []

    def test_overwrite_existing(self, workdir):
        p = workdir / 'over.csv'
        p.write_text('old,data\n9,9\n', encoding='utf-8')
        Table([['1', 'a']], columns=['id', 'name']).to_file(str(p))
        assert Table.from_file(str(p))._data == [['1', 'a']]

    def test_encoding_failure_cleans_up(self, workdir):
        p = workdir / 'bad.csv'
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            ok = Table([['中文']], columns=['a']).to_file(str(p), encoding='ascii')
        assert ok is False
        # 修复前：文件存在且只有表头
        assert not p.exists()
        assert glob.glob(str(workdir / '.vools_tbl_*')) == []
        assert any(issubclass(w.category, RuntimeWarning) for w in caught)

    def test_missing_directory_warns(self, workdir):
        target = str(workdir / 'no_such_dir' / 'x.csv')
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            assert Table([['1']], columns=['a']).to_file(target) is False
        assert caught, '失败应当有可见告警'
        assert not os.path.exists(target)


class TestRoundTripUnchanged:
    def test_special_characters(self, workdir):
        p = workdir / 'sp.csv'
        t = Table([['a,b', 'say "hi"'], ['line1\nline2', 'x']],
                  columns=['c1', 'c2'])
        t.to_file(str(p))
        assert Table.from_file(str(p))._data == t._data

    def test_gbk_and_tab(self, workdir):
        p = workdir / 'gbk.csv'
        t = Table([['中文', 'x']], columns=['名称', 'c'])
        t.to_file(str(p), delimiter='\t', encoding='gbk')
        back = Table.from_file(str(p), delimiter='\t', encoding='gbk')
        assert (back._columns, back._data) == (['名称', 'c'], [['中文', 'x']])

    def test_empty_table(self, workdir):
        p = workdir / 'empty.csv'
        Table([], columns=['a', 'b']).to_file(str(p))
        back = Table.from_file(str(p))
        assert (back._columns, back._data) == (['a', 'b'], [])