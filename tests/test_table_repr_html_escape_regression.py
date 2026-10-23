# -*- coding: utf-8 -*-
"""回归测试：Table._repr_html / show() 的 HTML 转义（BUG-380）。

`show()` 打印 `_repr_html()` 生成的 HTML，而原实现把**单元格值、列名、表名
直接拼接**进标签：

    Table([['<script>alert(1)</script>']], columns=['<b>col</b>'], name='<i>T</i>')
    .show()
    # <td><script>alert(1)</script></td>   ← 原样注入（Jupyter / 网页里即 XSS）

普通值也会破坏排版：`<td>a&b</td>`（应为 `a&amp;b`）。

修复：表名 / 列名 / 单元格值统一 `html.escape`；结构与普通值的渲染不变。
"""

import pytest

from vools.data.table import Table


class TestEscaping:
    def test_script_tag_escaped(self):
        t = Table([['<script>alert(1)</script>']], columns=['a'])
        html = t._repr_html()
        assert '<script>' not in html
        assert '&lt;script&gt;alert(1)&lt;/script&gt;' in html

    def test_ampersand_escaped(self):
        t = Table([['a&b']], columns=['a'])
        assert '<td>a&amp;b</td>' in t._repr_html()

    def test_column_name_escaped(self):
        t = Table([[1]], columns=['<b>col</b>'])
        assert '<th>&lt;b&gt;col&lt;/b&gt;</th>' in t._repr_html()

    def test_table_name_escaped(self):
        t = Table([[1]], columns=['a'], name='<i>T</i>')
        assert '&lt;i&gt;T&lt;/i&gt;' in t._repr_html()

    def test_less_than(self):
        t = Table([['<']], columns=['a'])
        assert '<td>&lt;</td>' in t._repr_html()

    def test_none_renders_empty_cell(self):
        t = Table([[None]], columns=['a'])
        assert '<td></td>' in t._repr_html()


class TestStructureUnchanged:
    def test_basic_structure(self):
        t = Table([[1, 'a']], columns=['id', 'name'])
        html = t._repr_html()
        assert html.startswith('<strong>Table:')
        assert '<table border="1">' in html
        assert '<th>id</th>' in html and '<th>name</th>' in html
        assert '<td>1</td>' in html and '<td>a</td>' in html
        assert html.rstrip().endswith('</table>')

    def test_row_limit_and_hint(self):
        t = Table([[i] for i in range(5)], columns=['x'])
        html = t._repr_html(max_rows=2)
        assert html.count('<tr>') == 3          # 表头 + 2 行
        assert 'and 3 more rows' in html

    def test_column_truncation(self):
        t = Table([[i for i in range(12)]], columns=[f'c{i}' for i in range(12)])
        html = t._repr_html()
        assert '<th>...</th>' in html and '<td>...</td>' in html

    def test_show_returns_self(self, capsys):
        t = Table([[1]], columns=['a'])
        assert t.show() is t
        out = capsys.readouterr().out
        assert '<table border="1">' in out

    def test_repr_is_plain_text(self):
        t = Table([['<b>x</b>']], columns=['a'])
        # repr 是纯文本，不做 HTML 转义
        assert '<b>x</b>' in repr(t)