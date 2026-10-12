"""tests/data/test_vic_inherit.py — pyk vic* 类与核心 V* 类的继承/能力对齐回归。

锁住两件事：
1. 继承关系：vicText/vicSql 必须是 VText 的子类（而不是裸 str 兄弟类）。
   vools/__init__.py 里 vicText 就是 VText 的别名，pyk 子类必须与之一致。
2. 能力面：legacy vools.py 大文件里 vicText/vicList 的通用方法，
   在核心 VText/VList 上可用（pyspark 相关的 toDF 除外，它留在 pyk）。
"""

import pytest

from vools.data.vtext import VText
from vools.data.vlist import VList
from vools.datetime.vdate_class import VDate


def _pyk_text():
    """导入 vools.pyk.text；pyspark/pandas 缺失时跳过该用例。

    vools.pyk 是 pyspark 可选子包（pyk.df 需要 pandas/pyspark），
    环境未装时是环境约束而非代码缺陷，故 skip 而非 fail。
    """
    try:
        from vools.pyk import text as _m
        return _m
    except ImportError as e:
        pytest.skip('vools.pyk.text 需要 pyspark/pandas: %s' % e)


def _pyk_postgre():
    try:
        from vools.pyk import postgre as _m
        return _m
    except ImportError as e:
        pytest.skip('vools.pyk.postgre 需要 pyspark/pandas: %s' % e)


# ============================================================
# 1. 核心库别名约定
# ============================================================

def test_core_vic_aliases_are_core_classes():
    import vools
    assert vools.vicText is VText
    assert vools.vicList is VList
    assert vools.vicDate is VDate


# ============================================================
# 2. pyk vic* 的继承关系
# ============================================================

def test_pyk_victext_inherits_vtext():
    vicText = _pyk_text().vicText
    assert issubclass(vicText, VText)
    assert 'VText' in [c.__name__ for c in vicText.__mro__]


def test_pyk_vicquery_inherits_victext_and_vtext():
    m = _pyk_text()
    assert issubclass(m.vicQuery, m.vicText)
    assert issubclass(m.vicQuery, VText)


def test_pyk_vicsql_inherits_vtext():
    vicSql = _pyk_postgre().vicSql
    assert issubclass(vicSql, VText)


def test_pyk_victext_instance_is_vtext():
    vicText = _pyk_text().vicText
    assert isinstance(vicText("select 1"), VText)


def test_pyk_vicsql_instance_is_vtext():
    vicSql = _pyk_postgre().vicSql
    assert isinstance(vicSql("select 1"), VText)


def test_pyk_victext_keeps_subclass_on_str_ops():
    """核心 VText 覆写了 __add__ 等，子类运算后应保持 vicText 类型。"""
    vicText = _pyk_text().vicText
    assert type(vicText("a") + "b") is vicText
    assert type(vicText("abc")[0]) is vicText


# ============================================================
# 3. pyk vicText 继承到的核心能力（legacy 能力面）
# ============================================================

LEGACY_VICTEXT_CAPS = [
    'toZipB64', 'unZipB64', 'encrypt', 'decrypt', 'strip_margin',
    'get_content_fromfile', 'regexp_split', 'formatEx', 'text', 'do',
    'trim', 'regexp_findall', 'regexp_replace', 'regexp_like',
    'regexp_substr', 'regexp_count', 'regexp_instr', 'splitEx', 'like',
    'build', 'discard_comments', 'move_trailing_commas', 'run', 'result',
    'replace_run_date', 'write',
]


@pytest.mark.parametrize('name', LEGACY_VICTEXT_CAPS)
def test_pyk_victext_has_core_capability(name):
    vicText = _pyk_text().vicText
    assert hasattr(vicText, name), 'vicText 缺少继承自 VText 的能力: %s' % name


def test_pyk_victext_pyspark_methods_still_present():
    """pyk 专属的 pyspark 方法不能因为改成继承而丢失。"""
    assert hasattr(_pyk_text().vicText, 'toDF')
    assert hasattr(_pyk_postgre().vicSql, 'toDF')


# ============================================================
# 4. VText 新增能力的行为
# ============================================================

def test_vtext_trim():
    assert str(VText('  hi  ').trim()) == 'hi'
    assert str(VText('xxhixx').trim('x')) == 'hi'


def test_vtext_regexp_family():
    t = VText('a1b2')
    assert t.regexp_findall(r'\d') == ['1', '2']
    assert str(t.regexp_replace(r'\d', '#')) == 'a#b#'
    assert t.regexp_like(r'^a.c$') is False
    assert VText('abc').regexp_like(r'^a.c$') is True
    assert t.regexp_count(r'\d') == 2
    assert t.regexp_substr(r'\d') == '1'
    assert t.regexp_instr(r'\d') == 1


def test_vtext_split_ex():
    assert VText('a,b,c').splitEx(',') == ['a', 'b', 'c']


def test_vtext_like():
    assert VText('Hello').like('he*') is True
    assert VText('Hello').like('he*', ignorecase=False) is False


def test_vtext_discard_comments():
    assert str(VText('select 1 -- c\nfrom t').discard_comments()) == 'select 1 \nfrom t'


def test_vtext_move_trailing_commas():
    assert str(VText('a,\nb,\nc').move_trailing_commas()) == 'a\n,b\n,c'


def test_vtext_build():
    assert str(VText('{item}').build(lst=['a', 'b'])) == 'a\n ,b'


def test_vtext_run_and_result():
    t = VText('1+1')
    out = t.run('eval')
    assert out == 2
    assert t.result == 2


def test_vtext_result_is_readonly():
    t = VText('x')
    with pytest.raises(ValueError):
        t.result = 'nope'


def test_vtext_operators_keep_type():
    assert type(VText('a') + 'b') is VText
    assert type('x' + VText('y')) is VText
    assert type(VText('a') * 2) is VText
    assert type(VText('abc')[0]) is VText
    assert str(VText('a') + 'b') == 'ab'
    assert str('x' + VText('y')) == 'xy'


def test_vtext_sub_removes_substring():
    assert str(VText('a1b2') - '1') == 'ab2'


def test_vtext_call():
    assert VText('hi')(lambda s: s.upper()) == 'HI'


# ============================================================
# 5. VList 新增能力的行为
# ============================================================

def test_vlist_no_recursion_on_non_list_return():
    """回归锁：ListLikeMeta.__instancecheck__ 曾无限递归（size/is_empty 必崩）。"""
    assert VList([1, 2, 3]).size == 3
    assert VList([]).is_empty is True
    assert VList([1]).is_empty is False
    assert VList([1, 2, 3]).quantify(lambda x: x > 1) == 2


def test_vlist_isinstance_semantics():
    assert isinstance(VList([1]), VList) is True
    assert isinstance([1], VList) is True
    assert isinstance(5, VList) is False


def test_vlist_dotproduct_not_shadowed_by_map_method():
    """回归锁：类体内 map=map 默认值会被 VList.map 方法遮蔽。"""
    assert VList.dotproduct([1, 2, 3], [4, 5, 6]) == 32


def test_vlist_itertools_helpers():
    assert VList([1, 2, 3, 4]).rotate(1).collect() == [4, 1, 2, 3]
    assert VList([1, 2]).ncycles(2).collect() == [1, 2, 1, 2]
    assert VList([[1, 2], [3]]).flatten().collect() == [1, 2, 3]
    assert VList([1, 2, 3]).tee().collect() == [(1, 2), (2, 3)]
    assert VList(list('ABCDEFG')).grouper(3, 'x').collect() == [
        ('A', 'B', 'C'), ('D', 'E', 'F'), ('G', 'x', 'x')]
    assert VList.roundrobin('ABC', 'D', 'EF').collect() == ['A', 'D', 'E', 'B', 'F', 'C']
    assert len(VList([1, 2]).powerset().collect()) == 4
    assert VList([1, 1, 2, 2, 1]).unique_justseen().collect() == [1, 2, 1]
    assert VList([1, 1, 2, 2, 1]).unique_everseen().collect() == [1, 2]
    assert VList([0, 0, 3]).first_true() == 3
    assert VList([1, 2, 3, 1]).dropwhile(lambda x: x < 3).collect() == [3, 1]
    assert VList([1, 2, 3, 1]).takewhile(lambda x: x < 3).collect() == [1, 2]
    assert VList.repeatfunc(lambda x: x * 2, 3, 5).collect() == [10, 10, 10]


def test_vlist_padnone_is_lazy():
    """回归锁：padnone 是无限序列，必须保持惰性（曾误物化成 VList 而挂死）。"""
    import itertools
    got = list(itertools.islice(VList([1, 2]).padnone(), 4))
    assert got == [1, 2, None, None]


def test_vlist_partition():
    parts = VList(range(5)).partition(lambda x: x % 2 == 0).collect()
    assert [p.collect() for p in parts] == [[1, 3], [0, 2, 4]]


def test_vlist_folds():
    assert VList([1, 2, 3]).foldLeft(0, mutable=True)(lambda a, b: a + b) == 6
    assert VList([1, 2, 3]).foldRight(0, mutable=True)(lambda a, b: a + b) == 6


def test_vlist_swap_and_mul():
    assert VList([1, 2, 3]).swap(0, 2).collect() == [3, 2, 1]
    assert (VList([1, 2]) * 2).collect() == [1, 2, 1, 2]


def test_vlist_accummap():
    assert VList([1, 2, 3]).accummap(lambda ix, acc: sum(acc)).collect() == [1, 3, 6]


def test_vlist_join_returns_vtext():
    joined = VList([1, 2, 3]).join('-')
    assert isinstance(joined, VText)
    assert str(joined) == '1-2-3'


def test_vlist_sample():
    assert len(VList([1, 2, 3, 4, 5]).sample(2).collect()) == 2
