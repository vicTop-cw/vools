"""_format_table / show_table 文本表格格式化回归。

锁定 2026-10-14 修复：
1. has_header 参数此前【全程失效】——_format_table 无条件在首行后插分隔线，
   show_table 也没把 has_header 传下去；show_table(data, has_header=False)
   仍输出带分隔线的表头样式。修复后 has_header=True 才插分隔线。
2. 死代码清理：旧 _format_table 分配了从未使用的 rows 列表（O(行×列) 白耗）。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from vools.xl._utils import (
    _format_table,
    _normalize_data,
    dataframe_to_2d_list,
)


def test_empty_table_returns_blank():
    assert _format_table([]) == ''
    assert _format_table([[]]) == ''


def test_has_header_inserts_separator():
    out = _format_table([['name', 'age'], ['bob', '30']], has_header=True)
    lines = out.splitlines()
    assert len(lines) == 3
    assert set(lines[1]) <= set('-+')   # 分隔线行
    assert lines[0].startswith('name')


def test_no_header_does_not_insert_separator():
    """回归核心：has_header=False 绝不能出现分隔线（旧版无条件插入）。"""
    out = _format_table([['a', 'b'], ['c', 'd']], has_header=False)
    lines = out.splitlines()
    assert len(lines) == 2
    assert '-+-' not in out


def test_single_row_never_gets_separator():
    assert _format_table([['only', 'header']], has_header=True) == 'only | header'


def test_ragged_rows_pad_and_align():
    # has_header=False 聚焦参差行的补空与对齐
    out = _format_table([['x', 'yy', 'zzz'], ['1']], has_header=False)
    lines = out.splitlines()
    assert lines[0] == 'x | yy | zzz'
    assert lines[1] == '1 |    |    '
    assert len(lines[0]) == len(lines[1])


def test_show_table_passes_has_header(capsys):
    from vools.xl._utils import show_table
    show_table([['a', 'b'], ['c', 'd']], title=None, has_header=False)
    out = capsys.readouterr().out
    assert '-+-' not in out
    show_table([['a', 'b'], ['c', 'd']], title=None, has_header=True)
    out = capsys.readouterr().out
    assert '-+-' in out


def test_dataframe_to_2d_list_none_becomes_empty_string():
    pd = pytest.importorskip('pandas')
    df = pd.DataFrame({'x': [1, None], 'y': ['a', 'b']})
    rows = dataframe_to_2d_list(df, show_index=False)
    assert rows[0] == ['x', 'y']            # 表头
    assert rows[2][0] == ''                  # None -> ''


def test_normalize_data_rejects_unsupported_type():
    with pytest.raises(TypeError):
        _normalize_data(12345)


def test_normalize_list_passthrough():
    res = _normalize_data([['a'], ['b']])
    assert res['type'] == 'list'
    assert res['data'] == [['a'], ['b']]
