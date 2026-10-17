# -*- coding: utf-8 -*-
"""tests/sql/test_lazy_dialect_attrs.py — vools.sql 惰性方言必须【可用且不自递归】（钉 BUG-77/79）

三个形状（同一次寻虫抓到，都在 vools/sql/__init__.py）：

1. `__getattr__`  ↔  `from . import X` 互递归（BUG-77）
   模块级 __getattr__ 存在时，`from . import mysql` 会走 importlib 的
   _handle_fromlist，它对父包做 hasattr(pkg, 'mysql') —— hasattr 又触发本模块
   __getattr__ → 再调 _load_mysql → 又 from . import mysql。实测一次属性访问
   自递归 50~105 层，最终只靠 `except Exception` 吞掉 RecursionError 才"看着能用"；
   `from vools.sql import *` 实测卡死 >120s。修法：改 importlib.import_module
   （不查父包属性）+ _LOADING/_DIALECT_FAILED 两个集合把三态分开。

2. __all__ 空头名（BUG-79，BUG-70 同族）
   'mysql' / 'oracle' / 'mssql' 三个名字对应的子模块目录在本分发里【不存在】
   （ls 实测只有 core/postgres/spark/sqlite + manager.py），空头名让 star import
   逐名 getattr 时失败。另 'manager' 在 __all__ 里出现两次，已去重。

3. py3.6 下惰性名整体不可解析（BUG-78，见 test_pep562_py36_convention.py）

本锁按"必须可用"的形状断言，而不是逐个点名，防止再加一个方言时漏测。
"""

import os
import sys
import time

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import vools.sql as S  # noqa: E402

# 本分发实际存在的方言子模块（目录名实测）
PRESENT_DIALECTS = ['postgres', 'sqlite', 'spark']


def test_present_dialects_resolve_by_attribute():
    """存在的方言子模块必须能【属性访问】拿到（不能只靠 from-import 兜住）。"""
    for name in PRESENT_DIALECTS:
        mod = getattr(S, name, None)
        assert mod is not None, 'vools.sql.%s 拿不到（惰性解析失效）' % name
        assert getattr(mod, '__name__', '') == 'vools.sql.' + name


def test_no_self_recursion_on_lazy_resolve():
    """解析一个方言名：3.7+ 时 __getattr__ 只应进入一次（修复前实测 50~105 次）。

    两版本都真断言，不留 skip：
      py3.7+ —— 名字被 pop 后走惰性路径，期望 entries == 1（>1 即与
        `from . import X` 互递归）；
      py3.6  —— 模块级 __getattr__ 是 PEP 562（3.7+）特性，在这版【根本不会被调用】，
        名字由 <3.7 主动绑定分支提供，所以期望 entries == 0 且仍能拿到模块
        （若哪天有人在 3.6 上靠 __getattr__ 兜，这里就会亮）。
    pop 出的绑定在 finally 里原样放回，不给后续测试留脏状态。
    """
    name = 'sqlite'
    real = S.__getattr__
    calls = []

    def counting(n, _c=calls, _r=real, _k=name):
        if n == _k:
            _c.append(1)
            if len(_c) > 20:
                raise RecursionError('probe cap: 自递归')
        return _r(n)

    S.__getattr__ = counting
    saved = None
    try:
        sys.setrecursionlimit(1000)
        if sys.version_info >= (3, 7):
            saved = S.__dict__.pop(name, None)     # 逼它走惰性路径
            got = getattr(S, name, None)
            assert got is not None, '%s.%s 解析不出来' % (S.__name__, name)
            assert len(calls) == 1, \
                '解析 %s 自递归 %d 次（应为 1；修复前实测 50~105）' % (name, len(calls))
        else:
            # 3.6 上 pop 会让名字彻底解析不出来（__getattr__ 是死函数 = BUG-78 本身），
            # 所以这里不 pop，只验证：名字靠 eager 分支可得，且 __getattr__ 一次都没被调。
            got = getattr(S, name, None)
            assert got is not None, \
                'py3.6 下 vools.sql.%s 应由 <3.7 主动绑定分支提供（BUG-78）' % name
            assert len(calls) == 0, \
                'py3.6 下模块级 __getattr__ 不该被调用（PEP 562 是 3.7+），实际 %d 次' % len(calls)
    finally:
        S.__getattr__ = real
        if saved is not None:
            S.__dict__[name] = saved


def test_star_import_completes_quickly():
    """`from vools.sql import *` 必须秒级完成（未修 recursion+空头名时实测 >120s）。"""
    t0 = time.time()
    ns = {}
    exec('from vools.sql import *', ns)
    el = time.time() - t0
    assert el < 10, 'star import 耗时 %.1fs（疑似又出现自递归）' % el
    assert any(hasattr(S, n) for n in PRESENT_DIALECTS)


def test_all_names_resolvable():
    """__all__ 不得有空头名（BUG-70 同族形状，通用断言）。"""
    missing = [n for n in S.__all__ if not hasattr(S, n)]
    assert not missing, '__all__ 空头名: %s' % missing


def test_no_duplicate_entries_in_all():
    """__all__ 不应重复列同一个名字（'manager' 从前被列了两次）。"""
    seen = set()
    dup = []
    for n in S.__all__:
        if n in seen:
            dup.append(n)
        seen.add(n)
    assert not dup, '__all__ 重复名: %s' % dup


def test_absent_dialects_are_not_declared():
    """不存在的方言【不能】出现在 __all__ 里（本分发没有 mysql/oracle/mssql）。"""
    for name in ('mysql', 'oracle', 'mssql'):
        assert name not in S.__all__, \
            '%s 子模块在本分发不存在，却仍挂在 __all__ 上（空头名会让 star import 失败）' % name
        with pytest.raises(AttributeError):
            getattr(S, name)
