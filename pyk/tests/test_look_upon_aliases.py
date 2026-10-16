# -*- coding: utf-8 -*-
"""pyk/tests/test_look_upon_aliases.py — look_upon 模块级 register_do/builtin_do 别名（钉 BUG-71）

2026-10-17 寻虫实测：`from vools.pyk.look_upon import *` 抛 AttributeError
（__all__ 列了 register_do/builtin_do，实现却是 LookUpon 上的 @classmethod，
模块层没有同名绑定）。修复是加两行模块级别名。

本锁用【静态 AST】判定而不是运行时 import：look_upon 在干净环境（无 pyspark/
无 psycopg2）里 import 路径本身带条件降级，运行锁容易变成"环境不对就 skip"的
假绿形状（本仓红线：不用 skip 掩盖）。静态断言任何环境都能真跑真断。
"""

import ast
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)                       # pyk/
_MONOREPO_ROOT = os.path.dirname(_ROOT)
_TARGET = os.path.join(_ROOT, 'vools', 'pyk', 'look_upon.py')
if not os.path.isfile(_TARGET):
    _TARGET = os.path.join(_MONOREPO_ROOT, 'pyk', 'vools', 'pyk', 'look_upon.py')


def _module_level_bindings(src):
    """模块层可达绑定：进入顶层 try/if 的分支体（DagValidationError 在
    try/except ImportError 两侧各 import 一次），并认 AnnAssign
    （LANGUAGE_DEFAULT_CMD: Dict[...] = {...}）。函数/类体不进——那是局部名。"""
    tree = ast.parse(src)
    names = set()

    def collect(body):
        for st in body:
            if isinstance(st, ast.Assign):
                for t in st.targets:
                    if isinstance(t, ast.Name):
                        names.add(t.id)
            elif isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name):
                names.add(st.target.id)
            elif isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(st.name)
            elif isinstance(st, ast.Import):
                names.update((a.asname or a.name).split('.')[0] for a in st.names)
            elif isinstance(st, ast.ImportFrom):
                names.update((a.asname or a.name) for a in st.names)
            elif isinstance(st, ast.Try):
                for sub in (st.body, st.orelse, st.finalbody):
                    collect(sub)
                for h in st.handlers:
                    collect(h.body)
            elif isinstance(st, (ast.If, ast.For, ast.While)):
                collect(st.body)
                collect(st.orelse)
    collect(tree.body)
    return names


def _str_elts(node):
    """取字面量列表里的字符串元素，兼容 py3.6/3.7 的 ast.Str 与 3.8+ 的 ast.Constant。

    （本锁自己就踩过这个坑：只判 ast.Constant 时 py3.6 下 __all__ 被抽成空，
    双版本对拍才亮灯 —— 守卫也要过双版本门。）
    """
    out = []
    for e in getattr(node, 'elts', []):
        # py3.8+ 是 ast.Constant(.value)；py3.6/3.7 是 ast.Str(.s)
        v = getattr(e, 'value', None)
        if v is None:
            v = getattr(e, 's', None)
        if isinstance(v, str):
            out.append(v)
    return out


def test_all_names_bound_at_module_level():
    src = open(_TARGET, 'rb').read().decode('utf-8')
    tree = ast.parse(src)
    declared = None
    for st in tree.body:
        if isinstance(st, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == '__all__' for t in st.targets):
            declared = _str_elts(st.value)
    assert declared, 'look_upon 未定义 __all__ 字面量（口径漂移，或字面量抽取器与当前解释器 AST 形状不符）'
    bound = _module_level_bindings(src)
    missing = [n for n in declared if n not in bound]
    # 允许 _LAZY/条件分支里定义的兼容名字静态看不到？—— 本文件没有这种形状：
    # 若将来出现，请改用运行时核验并保持"真 import 真断言"。当前必须零缺失。
    assert not missing, '__all__ 空头名（star import 会 AttributeError）: %s' % missing


def test_register_do_and_builtin_do_aliases_exist():
    src = open(_TARGET, 'rb').read().decode('utf-8')
    tree = ast.parse(src)
    aliased = {}
    for st in tree.body:
        if isinstance(st, ast.Assign) and isinstance(st.value, ast.Attribute):
            for t in st.targets:
                if isinstance(t, ast.Name) and t.id in ('register_do', 'builtin_do'):
                    aliased[t.id] = ast.unparse(st.value) if hasattr(ast, 'unparse') else '%s.%s' % (
                        getattr(st.value.value, 'id', '?'), st.value.attr)
    assert 'register_do' in aliased and 'builtin_do' in aliased, \
        '模块级别名缺失：__all__ 列了 register_do/builtin_do 但没有同名绑定（BUG-71 复发）'
