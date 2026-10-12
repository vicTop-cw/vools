"""tests/data/test_pyk_heavy_align.py — pyk 重型类与 legacy vools.py 的能力对齐回归。

覆盖本轮已对齐的类（不需要真 Spark 即可验证的部分）：
- vicTools: legacy 42 个静态方法入口（纯 Python 部分真跑，pyspark 部分验存在性）
- vicDataFrame: 12 个真缺口 + 5 个 camelCase 别名
- vicSql: run_date/repl_dict/sql/get_run_date_replaced_sql/get_unioned_sql
- rself: property 返回 None 不再被替换成 self（BUG-17）

vicTableInfo 因本机 Spark 不可用（py4j/PythonUtils.getEncryptionEnabled
版本不匹配）未在本轮补齐，相关用例不在此文件。
"""

import pytest

from vools.data.vtext import VText


# ============================================================
# rself: property 的 None 语义（BUG-17 回归锁）
# ============================================================

def test_rself_property_none_stays_none():
    """回归锁：@rself 曾把 property 返回的 None 替换成 self。"""
    t = VText('SOMETEXT')
    assert t.result is None
    assert t.result is not t


def test_rself_property_non_none_unchanged():
    t = VText('x')
    assert t.text == 'x'
    assert isinstance(t.text, VText)


def test_rself_method_none_still_returns_self():
    """方法返回 None 仍应返回 self（链式调用兜底，不能被上述修复破坏）。"""
    t = VText('abc')

    class _Probe(VText):
        def nothing(self):
            return None

    p = _Probe('abc')
    assert p.nothing() is p


# ============================================================
# vicTools: legacy 42 个方法入口
# ============================================================

LEGACY_VICTOOLS_METHODS = [
    'transfer', 'get_index_cols', 'static_vars', 'generate_lambda', 'shift',
    'get_py_fmt', 'get_date_seq', 'transferCols', 'generate_random_field_name',
    'getAllModules', 'getAllPackagesWithVersion', 'toDF', 'toDFWithOneColumn',
    'toOrderedDict', 'build_text', 'get_df', 'get_json_keys', 'offset_date',
    'aggregate_json_keys', 'calculate_runtime', 'excel_column_to_number',
    'excel_number_to_column', 'union_ordered_collection', 'trim',
    'regexp_findall', 'regexp_replace', 'regexp_like', 'regexp_substr',
    'regexp_count', 'regexp_instr', 'get_char', 'check_no_overlap',
    'regexp_split', 'split', 'stack', 'pivot', 'pivots',
    'get_insert_sql_for_postgre', 'generate_postgres_sql', 'trans_df',
    'chunk_df', '_split',
]


@pytest.mark.parametrize('name', LEGACY_VICTOOLS_METHODS)
def test_victools_has_legacy_method(name):
    from vools.utils.tools import trim  # 纯 Python 侧永远可用
    from vools.utils.tools import _split as _s  # noqa: F401
    # vicTools 优先取 pyk.tools.vicTools；无 pyspark 时回退 utils.tools 模块。
    # 这里对两种形态都接受：类上有方法，或模块级有同名函数。
    import vools
    tools = vools.vicTools
    assert hasattr(tools, name), 'vicTools 缺少 legacy 方法: %s' % name


def test_victools_pure_python_forwarding_works():
    """纯 Python 转发真跑一遍（不依赖 pyspark）。"""
    import vools
    t = vools.vicTools
    assert t.trim('  x  ') == 'x'
    assert t.regexp_findall(r'\d+', 'a1b22') == ['1', '22']
    assert t.regexp_replace(r'\d+', 'a1b22', '#') == 'a#b#'
    assert t.get_py_fmt('yyyyMMdd') == '%Y%m%d'
    assert t.transferCols('a,b') == ['a', 'b']
    assert t.split('a,b;c', [',', ';']) == ['a', 'b', 'c']


def test_pyk_tools_victools_class_exists():
    """pyk.tools.vicTools 是 legacy vicTools 的聚合类。"""
    pytest.importorskip('pandas')
    from vools.pyk.tools import vicTools
    assert isinstance(vicTools, type)


# ============================================================
# vicSql: legacy 语义
# ============================================================

def _vicsql():
    try:
        from vools.pyk.postgre import vicSql
        return vicSql
    except ImportError as e:
        pytest.skip('vools.pyk.postgre 需要 pyspark/pandas: %s' % e)


def test_vicsql_inherits_vtext():
    vicSql = _vicsql()
    assert issubclass(vicSql, VText)
    assert isinstance(vicSql('select 1'), VText)


def test_vicsql_repl_dict_substitution():
    vicSql = _vicsql()
    s = vicSql('select * from t where ds="{ds}"', repl_dict={'ds': '20261011'})
    assert s.sql == 'select * from t where ds="20261011"'


def test_vicsql_run_date_replacement():
    vicSql = _vicsql()
    s = vicSql("select '{run_date}' as d", run_date='2026-10-11')
    assert '2026' in s.sql
    assert '{run_date}' not in s.sql


def test_vicsql_run_date_std_is_dashed():
    vicSql = _vicsql()
    s = vicSql("select '{run_date_std}' as d", run_date='2026-10-11')
    assert '2026-10-11' in s.get_run_date_replaced_sql()


def test_vicsql_sql_setter_and_str():
    vicSql = _vicsql()
    s = vicSql('old')
    s.sql = 'new'
    assert s.sql == 'new'
    assert str(vicSql('select 1')) == 'select 1'


def test_vicsql_run_date_property_falls_back():
    """未显式给 run_date 时也要能拿到可用日期（legacy 会抛 TypeError）。"""
    vicSql = _vicsql()
    rd = vicSql('x').run_date
    assert rd is not None
    assert isinstance(rd, str)


def test_vicsql_get_unioned_sql():
    vicSql = _vicsql()
    out = vicSql.get_unioned_sql('select a as x, b as y from t', ['a', 'b'],
                                 accord_indexes='01')
    assert 'union all' in out


def test_vicsql_keeps_vtext_capabilities():
    vicSql = _vicsql()
    for name in ('toZipB64', 'unZipB64', 'regexp_replace', 'trim', 'build'):
        assert hasattr(vicSql, name), 'vicSql 缺少继承自 VText 的能力: %s' % name


# ============================================================
# vicDataFrame: 12 个真缺口 + 5 个 camelCase 别名
# ============================================================

LEGACY_VICDATAFRAME_METHODS = [
    'show', 'top', 'group_by', 'order_by', 'withColumn_', 'withColumns',
    'stack', 'stackEx', 'pivots', 'compare', '__call__',
    '__radd__', '__rsub__', '__rand__', '__ror__',
    # camelCase 别名
    'showEx', 'selectEx', 'groupingSets', 'orderCols', 'toList', 'get_miss_dates',
]


@pytest.mark.parametrize('name', LEGACY_VICDATAFRAME_METHODS)
def test_vicdataframe_has_legacy_method(name):
    pytest.importorskip('pandas')
    from vools.pyk.df import vicDataFrame
    assert hasattr(vicDataFrame, name), 'vicDataFrame 缺少 legacy 方法: %s' % name


def test_vicdataframe_camel_aliases_match_snake():
    """camelCase 别名必须与 snake_case 实现是同一个函数对象。"""
    pytest.importorskip('pandas')
    from vools.pyk.df import vicDataFrame
    assert vicDataFrame.showEx is vicDataFrame.show_ex
    assert vicDataFrame.selectEx is vicDataFrame.select_ex
    assert vicDataFrame.groupingSets is vicDataFrame.grouping_sets
    assert vicDataFrame.orderCols is vicDataFrame.order_cols
    assert vicDataFrame.toList is vicDataFrame.to_list
    assert vicDataFrame.get_miss_dates is vicDataFrame.get_missing_dates


# ============================================================
# pyk 子模块注册
# ============================================================

def test_pyk_tools_registered_in_submodules():
    from vools.pyk import _SUBMODULES
    assert 'tools' in _SUBMODULES
