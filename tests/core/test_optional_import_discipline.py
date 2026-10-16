# -*- coding: utf-8 -*-
"""tests/core/test_optional_import_discipline.py — 核心包不得在【模块加载期】顶层 import 可选兄弟分发。

背景（BUG-57 族）：vools 的 bridge/reactive/xl/pyk/dll32/actus 都是【独立发版的可选
分发】（装主包 vools 并不等于装了它们；主包 __getattr__ 对缺席的它们按设计抛带安装
提示的 AttributeError）。可核心树里一旦有模块在【顶层】裸 `from ..bridge... import`，
标准安装（pip install vools）下 import 那个模块就直接 ModuleNotFoundError —— 正是本轮
已修的 BUG-57（vools/sys/dll_cmd.py 顶层硬 import vools.bridge，`python -m vools sys`
一进来就崩）。这类是【散落地会复发】的回归，光靠 review 挡不住。

本守卫是 AST 级、双版本真跑真断言的永久闸（与 py3.6 语法守卫 test_py36_compat.py 同一
思路：把"人不在场也能亮灯"的判定固化进测试套件）：
  - 遍历核心包树 vools/**/*.py，逐个 ast.parse；
  - 只看【模块体层级】的 import（函数/类体内的延迟 import 是正解，不算违规）；
  - 豁免包在 `try: ... except ImportError/ModuleNotFoundError` 里的顶层 import
    ——那是官方认可的"可选加速降级"姿势（同包 env_cmd.py / decorators/bridge_decorator
    的 nim 加速都这么写），照抄文档示例不会误报；
  - 被引根包 ∈ {bridge, reactive, xl, pyk, dll32, actus} 且【未被 try 保护】即违规。

自校验（防空洞）：同一份判定函数喂两段合成源码——顶层裸 import 必须被抓、try 包裹的
必须放行。否则哪天 ast 结构判定被改错、守卫会"0 违规"地假装通过，本测试会先亮。

诚实边界：只管"顶层 import 可选分发"这一类加载期硬依赖。函数体内 import 可选分发但
【不做缺席降级】的运行时崩溃不在此覆盖（那由"真在标准安装环境跑"的测试负责）。
"""

import ast
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CORE = os.path.join(REPO_ROOT, 'vools')

# 独立发版的可选兄弟分发（与 vools/__init__.py 的可选子包清单同口径）
OPTIONAL_ROOTS = {'bridge', 'reactive', 'xl', 'pyk', 'dll32', 'actus'}

_SKIP_DIRS = {'__pycache__', '_python32', 'site-packages', 'node_modules'}


def _import_resolves_optional(node):
    """该 import 语句是否指向某个可选分发的根包。返回 (bool, 名称)。"""
    if isinstance(node, ast.ImportFrom):
        if node.level and node.level > 0:
            # 相对导入从核心包内部出发，被引模块首段即目标子包名
            first = (node.module or '').split('.')[0]
            return first in OPTIONAL_ROOTS, (('.' * node.level) + (node.module or ''))
        parts = (node.module or '').split('.')
        if parts and parts[0] == 'vools' and len(parts) > 1:
            first = parts[1]
        else:
            first = parts[0] if parts else ''
        return first in OPTIONAL_ROOTS, node.module
    if isinstance(node, ast.Import):
        for a in node.names:
            parts = a.name.split('.')
            first = parts[1] if (parts and parts[0] == 'vools' and len(parts) > 1) else parts[0]
            if first in OPTIONAL_ROOTS:
                return True, a.name
    return False, ''


def _handlers_catch_import_error(node):
    """ast.Try 的某个 except 是否罩住 ImportError / ModuleNotFoundError（宽罩含在内）。"""
    for h in node.handlers:
        t = h.type
        if t is None:
            return True                       # 裸 except 也算保护
        names = set()
        if isinstance(t, ast.Name):
            names.add(t.id)
        elif isinstance(t, ast.Tuple):
            names = {e.id for e in t.elts if isinstance(e, ast.Name)}
        names.discard(None)
        # Exception 会一并捕获 ImportError，也算保护
        if names & {'ImportError', 'ModuleNotFoundError', 'Exception'}:
            return True
    return False


def _top_level_unguarded_optional_imports(tree):
    """遍历【模块体层级】（跳过函数/类体），返回未被 try(ImportError) 保护的可选分发 import。"""
    found = []

    def walk(body, guarded):
        for st in body:
            if isinstance(st, (ast.Import, ast.ImportFrom)):
                hit, name = _import_resolves_optional(st)
                if hit and not guarded:
                    found.append((getattr(st, 'lineno', 0), name))
            elif isinstance(st, ast.Try):
                guarded_here = guarded or _handlers_catch_import_error(st)
                walk(st.body, guarded_here)
                walk(st.orelse, guarded_here)
                walk(st.finalbody, guarded_here)
            elif isinstance(st, ast.If):
                walk(st.body, guarded)
                walk(st.orelse, guarded)
            # FunctionDef/AsyncFunctionDef/ClassDef/for/while：不进入 ——
            # 函数体内 import 是延迟的（加载期不执行），属正解，不算违规。

    walk(tree.body, False)
    return found


def _iter_core_py():
    for dirpath, dirnames, filenames in os.walk(CORE):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fn in filenames:
            if fn.endswith('.py'):
                yield os.path.join(dirpath, fn)


def test_no_top_level_optional_imports_in_core():
    """核心包里不得有加载期未保护的可选分发顶层 import。"""
    offenders = []
    scanned = 0
    for path in _iter_core_py():
        try:
            src = open(path, 'rb').read().decode('utf-8')
            tree = ast.parse(src, filename=path)
        except (OSError, SyntaxError, ValueError):
            continue
        scanned += 1
        for lineno, name in _top_level_unguarded_optional_imports(tree):
            rel = os.path.relpath(path, REPO_ROOT)
            offenders.append('%s:%d -> import %s' % (rel, lineno, name))
    # 反向守卫：扫描面塌缩 = 口径失效（防目录被挪走导致 0 文件空过）
    assert scanned > 150, '核心树仅扫到 %d 个文件，守卫口径可能已失效' % scanned
    if offenders:
        raise AssertionError(
            '核心包存在加载期未保护的可选分发顶层 import（BUG-57 族：标准安装下 '
            'import 该模块即 ModuleNotFoundError，应改函数级延迟 import 或包进 '
            'try/except ImportError）：\n  ' + '\n  '.join(offenders[:20]))


def test_detector_is_non_vacuous():
    """自校验：同一判定喂合成源码——裸顶层 import 必被抓，try 包裹必放行。

    没有这格，判定逻辑一旦被改错（比如误把 try 里的也算违规、或反过来全放行），
    test_no_top_level_optional_imports 会以"0 违规"假绿。这里把它的灵敏度钉死。
    """
    raw = 'from ..bridge.core.loader import _LIB_DIR\nx = 1\n'
    caught = _top_level_unguarded_optional_imports(ast.parse(raw))
    assert len(caught) == 1, '裸顶层 import 未被抓到：守卫失明'

    guarded = ('try:\n'
               '    from ..bridge.core.loader import _LIB_DIR\n'
               'except ImportError:\n'
               '    _LIB_DIR = None\n')
    assert _top_level_unguarded_optional_imports(ast.parse(guarded)) == [], \
        'try/except ImportError 保护的顶层 import 被误判为违规（会把官方降级姿势也拦掉）'

    deferred = ('def f():\n'
                '    from ..bridge.core.loader import _LIB_DIR\n'
                '    return _LIB_DIR\n')
    assert _top_level_unguarded_optional_imports(ast.parse(deferred)) == [], \
        '函数体内的延迟 import 不应算加载期违规'

    absolute = 'from vools.reactive import x\n'
    assert len(_top_level_unguarded_optional_imports(ast.parse(absolute))) == 1, \
        '绝对路径的可选分发顶层 import 应被抓到'
