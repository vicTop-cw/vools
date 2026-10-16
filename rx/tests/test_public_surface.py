# -*- coding: utf-8 -*-
"""rx/tests/test_public_surface.py — vools.reactive 的 __all__ 必须全部可取（钉 BUG-70）

2026-10-17 寻虫：`__init__.py` 的 __all__ 里曾挂着 14 个从未实现的名字，
`from vools.reactive import *` 逐名 getattr 直接 AttributeError —— 整套 star-import
连带 210 个真名字一起拿不到（实测 py3.11/py3.6 双版本炸）。

本锁是【通用断言】而不是逐个点名：__all__ 里每一个名字都必须 hasattr 得到，
且 star import 在独立命名空间里必须不抛。以后往 __all__ 加空头名（实现没写、
或写在别的模块没 re-export）会在 rx 套件里直接亮灯。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _p in (_ROOT, os.path.join(_ROOT, 'rx')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import vools.reactive as R  # noqa: E402


def test_all_names_are_resolvable():
    missing = [n for n in R.__all__ if not hasattr(R, n)]
    assert not missing, '__all__ 有空头名（star import 会整条 AttributeError）: %s' % missing


def test_star_import_binds_everything():
    ns = {}
    exec('from vools.reactive import *', ns)   # 修复前：AttributeError
    got = [n for n in R.__all__ if n in ns]
    assert len(got) == len(R.__all__), 'star import 只绑到 %d/%d' % (len(got), len(R.__all__))
