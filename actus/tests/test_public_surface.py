# -*- coding: utf-8 -*-
"""actus/tests/test_public_surface.py — actus 模块的 __all__ 不得挂空头名（钉 BUG-72/73）

2026-10-17 寻虫实测：
  - mcp_sse.__all__ 列着从未定义的 'MCPServerSSE' → `from vools.actus.mcp_sse
    import *` 抛 AttributeError，两个真名字也拿不到；
  - panel_init（历史遗留桩，全仓零引用）__all__ 列着 'app' → 同款炸。
本锁按【通用形状】断言：所列模块 __all__ 每名字 hasattr 可取 + star import 不抛。
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _p in (_ROOT, os.path.join(_ROOT, 'actus'), os.path.join(_ROOT, 'bridges')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

MODULES = ['vools.actus.mcp_sse', 'vools.actus.panel_init']


@pytest.mark.parametrize("mod_name", MODULES)
def test_all_names_are_resolvable(mod_name):
    import importlib
    m = importlib.import_module(mod_name)
    al = getattr(m, '__all__', None) or []
    missing = [n for n in al if not hasattr(m, n)]
    assert not missing, '%s.__all__ 空头名: %s' % (mod_name, missing)


@pytest.mark.parametrize("mod_name", MODULES)
def test_star_import_does_not_raise(mod_name):
    ns = {}
    exec('from %s import *' % mod_name, ns)
