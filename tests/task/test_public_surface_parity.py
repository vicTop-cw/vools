# -*- coding: utf-8 -*-
"""tests/task/test_public_surface_parity.py — vools.task 公开面在两件事上必须正确/一致

钉两个本轮（2026-10-17 寻虫）实测确认的缺陷：

BUG-68  `from vools.task.decorators import *` 直接 AttributeError：
  vools/task/decorators/__init__.py 的 __all__ 写着 ['task','batch_execute']，
  但 import 行只取了 task —— star import 逐名 getattr，命中不存在的 batch_execute
  即抛 AttributeError: module 'vools.task.decorators' has no attribute
  'batch_execute'（py3.11 / py3.6 双版本实测同样崩）。batch_execute 明明定义在
  task_decorator.py:161、且上级 vools/task/__init__.py 也正常再导出，唯独这层
  __init__ 漏了。

BUG-69  `vools.task` 在 py3.6 与 py3.11 下类型不一致（公开名两副面孔）：
  vools/__init__.py 声明 'task' ∈ _module_names（L342，注释 L339 明确"模块名键
  直接返回模块本身"），__getattr__（L495）遵此在 py3.7+ 返回 module；但 py3.6 的
  eager 兼容块（L711-719）没查 _module_names、只要 hasattr(module,name) 就绑属性
  —— vools.task.task（同名函数）存在，于是 py3.6 把 vools.task 绑成了【函数】。
  后果实测：`import vools.task.decorators as d` 在 py3.6 抛 AttributeError
  （as 链对函数做 getattr），而 py3.11 正常。与 L96 自述意图"保证 3.6 下行为一致"
  直接相违。修后 py3.6 与 py3.11 的 24 键类型矩阵逐键一致（本轮实测对拍过）。
"""

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def test_star_import_of_task_decorators_works():
    """BUG-68：__all__ 里每个名字都必须真能被 getattr 到。"""
    import vools.task.decorators as d
    missing = [n for n in d.__all__ if not hasattr(d, n)]
    assert not missing, '__all__ 声明了但模块没有的名字: %s' % missing
    ns = {}
    exec('from vools.task.decorators import *', ns)   # 修复前 AttributeError
    assert 'batch_execute' in ns and 'task' in ns


def test_star_import_top_level_vools_consistent():
    """上级 vools.task 包同样不得有 __all__ 空头名。"""
    import vools.task as t
    if getattr(t, '__all__', None):
        missing = [n for n in t.__all__ if not hasattr(t, n)]
        assert not missing, 'vools.task.__all__ 空头名: %s' % missing
    ns = {}
    exec('from vools.task import *', ns)
    assert 'batch_execute' in ns


def test_vools_task_is_module_on_both_versions():
    """BUG-69：vools.task 是【模块名键】，两版本都必须是 module（py3.6 曾绑成函数）。"""
    import types
    import vools
    assert isinstance(vools.task, types.ModuleType), \
        'vools.task 应为模块，实际 %r（py3.6 旧行为会绑成 task 函数）' % type(vools.task)
    assert getattr(vools.task, '__name__', '') == 'vools.task'


def test_submodule_attr_import_as_chain_works():
    """BUG-69 的直接后果：`import vools.task.decorators as d` 两版本都得可用。"""
    import importlib
    d = importlib.import_module('vools.task.decorators')
    assert hasattr(d, 'task') and hasattr(d, 'batch_execute')
    # as 链语义：vools -> .task -> .decorators 逐级 getattr，
    # py3.6 旧行为把第一级 vools.task 绑成函数后这里必炸
    code = 'import vools.task.decorators as _d\n'
    ns = {}
    exec(compile(code, '<as-chain>', 'exec'), ns)
    assert hasattr(ns['_d'], 'batch_execute')


def test_module_names_keys_are_modules():
    """_module_names 声明的键（含 task）解析结果必须是模块对象本身。"""
    import types
    import vools
    for name in sorted(vools._module_names):
        try:
            v = getattr(vools, name)
        except AttributeError:
            continue          # 未安装的可选件按设计缺席，不算违例
        assert isinstance(v, types.ModuleType), \
            '模块名键 %s 解析成 %r（应为 module）——两版本口径须一致' % (name, type(v))
