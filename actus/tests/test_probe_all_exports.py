# -*- coding: utf-8 -*-
"""actus/tests/test_probe_all_exports.py — probe 包每个模块的 __all__ 必须【可兑现】（钉幻影名回归）。

同一族缺陷（寻虫一次抓到 10 处，都在 probe 包里）：

1. report.py 里 `__all__` 连写两次：前一份列了 `to_dict/add_item/add_items/build_summary`，
   后一份 `['ProbeReport', 'format_summary']` 静默覆盖掉它。前 4 个名字是
   ProbeReport 的**方法**，不是模块级名字 —— `from vools.actus.probe.report import to_dict`
   实测在 py3.11 与 py3.6 上都是 ImportError。重复赋值本身也是 dead code。

2. 9 个子模块（actions/compilers/environment/permissions/platform/python_pkgs/resources/
   runtimes/system_tools）把 `probe` 写进 `__all__`，而 `probe` 在这些模块里
   **只作为类方法存在**（如 `ActionsProber.probe()`），模块级根本没有这个名字。
   同一批 `fix(actus.probe): 12 个 probe 模块补 __all__` 只做了 report.py 与这 9 处，
   所以本锁按"__all__ 里的名字必须能在模块命名空间里查到"的通用形状断言，
   而不是逐个点名 —— 将来再加探测模块漏写时这里也会亮。

测试不挑环境（不真跑探针）：只做静态的 __all__ 兑现性检查，快且确定。
py3.6 兼容：无 walrus / f-string 之外的新语法依赖。
"""

import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

from vools.actus import probe as probe_pkg  # noqa: E402

_PROBE_DIR = os.path.dirname(os.path.abspath(probe_pkg.__file__))


def _probe_submodule_names():
    """返回 probe/ 下所有非 __init__ 的 .py 模块名（不含字节码）。"""
    names = []
    for fn in sorted(os.listdir(_PROBE_DIR)):
        if fn.endswith('.py') and fn != '__init__.py':
            names.append(fn[:-3])
    return names


def test_every_probe_submodule_has_single_all():
    """probe/ 下每个子模块只能出现一次 `__all__` 赋值（report.py 修复前连写两次）。"""
    for name in _probe_submodule_names():
        path = os.path.join(_PROBE_DIR, name + '.py')
        with open(path, 'r', encoding='utf-8') as fh:
            src = fh.read()
        count = src.count('__all__ =')
        if count > 1:
            pytest.fail(
                '%s.py: __all__ 赋值出现 %d 次（应 <=1；修复前 report.py 为 2 次，'
                '后一份静默覆盖前一份）' % (name, count)
            )


def test_every_probe_submodule_all_names_are_module_level():
    """__all__ 里的每个名字必须是模块级真实名字，不得是方法名或幻影名。

    修复前 9 个子模块把 `probe` 列进 __all__，而它只是类方法（如
    ActionsProber.probe）；report.py 把 to_dict 等 4 个方法名也列了。
    """
    for name in _probe_submodule_names():
        mod = importlib.import_module('vools.actus.probe.' + name)
        all_list = getattr(mod, '__all__', None)
        if all_list is None:
            continue
        names = set(dir(mod))
        phantom = [n for n in all_list if n not in names]
        assert not phantom, \
            '%s.py: __all__ 含 %d 个模块级不存在的名字 %s（应全部可兑现）' % (
                name, len(phantom), phantom)


def test_every_probe_submodule_all_has_no_duplicates():
    """__all__ 里同一名字不得重复出现（sql 包里 'manager' 曾重复，同族问题）。"""
    for name in _probe_submodule_names():
        mod = importlib.import_module('vools.actus.probe.' + name)
        all_list = getattr(mod, '__all__', None)
        if all_list is None:
            continue
        dupes = [n for n in set(all_list) if all_list.count(n) > 1]
        assert not dupes, \
            '%s.py: __all__ 重复名字 %s' % (name, dupes)


def test_report_all_names_star_importable():
    """report.py 的 __all__ 必须能通过 `from ... import *` 兑现。

    修复前 `from vools.actus.probe.report import *` 会因 line-9 那份
    phantom __all__ 的存在而按名字逐个 getattr —— 4 个方法名全部落空。
    """
    ns = {}
    exec('from vools.actus.probe.report import *', ns)
    assert 'ProbeReport' in ns, 'star import 丢了 ProbeReport'
    assert 'format_summary' in ns, 'star import 丢了 format_summary'