# -*- coding: utf-8 -*-
"""tests/core/test_pep562_py36_convention.py — 声明支持 py3.6 的树里，惰性 __getattr__ 必须有 3.6 兜底

缺陷形状（BUG-78，本轮实测三处）：模块级 `__getattr__`（PEP 562）只在
【py3.7+】生效 —— py3.6 下它是个死函数，常规属性查找失败就直接 AttributeError。
所以"用 __getattr__ 做惰性导出"的包，若同时声明 `requires-python >= 3.6`，
就必须另带一段 `if sys.version_info < (3, 7): ...` 的主动绑定，否则 py3.6 用户
`from pkg import *` 或 `pkg.lazy_name` 全都拿不到名字。

实测证据（修复前）：
  - vools.sql（>=3.6） py3.6：postgres/sqlite/spark/get_config_file_path/
    clear_instance_cache 五个 __all__ 名字全缺，`import *` 抛 AttributeError；
    而这五个子模块本身在 3.6 下【都能直接 import】—— 缺的只是属性解析层。
  - vools.pyk（>=3.6）py3.6：11 个懒加载子模块名里只有 tools 幸免（被别处先绑过）。
  - vools.bridge.vbnet（>=3.6）py3.6：`from ... import api` 能成（importlib 的
    from-import 会退回子模块导入），但属性访问 `vbnet.api` 得到 MISSING ——
    同一个包两种写法两种结果。
  - 对照组：vools / vools.datetime / vools.decorators / vools.bridge 都【有】这段
    兜底，py3.6 下 star import 正常 —— 说明这是本仓既定约定，不是新立的规矩。

判据是【数据驱动】的：某树要不要有兜底，取决于该树 pyproject 的
`requires-python` 是否把 3.6 包进契约，而不是写死包名清单。
actus 声明 `>=3.7`，因此它没有兜底【不算违规】（与本仓对 actus 的一贯口径一致）。

本守卫是静态的（不 import 被测包）：py3.6 下也能跑，且不会把 bridges/pyk 这类
重依赖拖进核心测试套件。
"""

import ast
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 发布树 -> 该树的 pyproject（相对仓库根）
TREES = {
    '': 'pyproject.toml',
    'rx': 'rx/pyproject.toml',
    'bridges': 'bridges/pyproject.toml',
    'xl': 'xl/pyproject.toml',
    'pyk': 'pyk/pyproject.toml',
    'dll32': 'dll32/pyproject.toml',
    'actus': 'actus/pyproject.toml',
}

SKIP_DIRS = {'__pycache__', '_python32', 'site-packages', 'node_modules',
             'compiler', 'templates', 'examples', 'static'}

# 已知且【量化过代价】的豁免：补兜底会引入回归，故登记不补，而不是让它无声通过。
# pyk/vools/pyk/__init__.py —— 2026-10-17 实测：
#   补 <3.7 主动绑定后 `import vools`（py3.6）0.54s -> 1.28s（vools.pyk.core 拉
#   numpy+pandas，单它一项 1.17s）；ABAB 交错各 4 次（不带 tests/sql 排除串扰）
#   显示 tests/task::test_concurrent_submissions 补后 4/4 失败、不补 4/4 通过。
#   该缺口只影响 py3.6 的【属性访问 / star import】，
#   `from vools.pyk import core` 这类 from-import 实测可用（importlib 退回子模块导入）。
# 想摘掉这条豁免，先解决"import vools 会连带拉起 pyk"这件事。
KNOWN_EXEMPTIONS = {
    'pyk/vools/pyk/__init__.py': '补兜底会拖入 numpy/pandas 并稳定打挂时序敏感用例（实测见本表注释）',
}

# `if sys.version_info < (3, 7)` 的各种等价写法。
# 先把空白归一化再匹配，否则 `(3, 7)` / `(3,7)` / `<\t=` 这类排版差异会漏判
# （漏判 = 合法写法被报成违规，正是上一轮 PyYAML 那类"守卫自己烂掉"的形状）。
_WS = re.compile(r'\s+')
_EAGER_PATTERNS = (
    re.compile(r'version_info(\[[^\]]*\])?<(?:=\(3,6\)|\(3,7\))'),   # <(3,7) / [:2]<(3,7) / <=(3,6)
    re.compile(r'version_info\.minor<7'),                              # 拆 major/minor 的写法
    re.compile(r'version_info\[[^\]]*\]<7'),                           # version_info[1] < 7
)


def _parse_requires_python(pyproject_rel):
    """返回 (spec 字符串, 是否把 py3.6 纳入契约)。解析不到时返回 (None, None)。"""
    p = os.path.join(REPO_ROOT, pyproject_rel)
    if not os.path.isfile(p):
        return None, None
    text = open(p, 'rb').read().decode('utf-8')
    m = re.search(r'requires-python\s*=\s*["\']([^"\']+)["\']', text)
    if not m:
        return None, None
    spec = m.group(1)
    low = re.search(r'>=\s*(\d+)\.(\d+)', spec)
    if not low:
        return spec, None
    major, minor = int(low.group(1)), int(low.group(2))
    return spec, (major == 3 and minor <= 6)


def _has_module_level_getattr(tree):
    return any(isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef))
               and st.name == '__getattr__' for st in tree.body)


def _has_module_all(tree):
    return any(isinstance(st, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == '__all__'
                       for t in st.targets)
               for st in tree.body)


def _lazy_export_modules():
    """[(tree, relpath, source)] —— 有模块级 __getattr__ 且有模块级 __all__ 的发布模块。"""
    rows = []
    for tree in TREES:
        base = os.path.join(REPO_ROOT, tree, 'vools') if tree \
            else os.path.join(REPO_ROOT, 'vools')
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fn in filenames:
                if not fn.endswith('.py'):
                    continue
                p = os.path.join(dirpath, fn)
                try:
                    src = open(p, 'rb').read().decode('utf-8')
                    t = ast.parse(src)
                except (OSError, SyntaxError, ValueError):
                    continue
                if _has_module_level_getattr(t) and _has_module_all(t):
                    rel = os.path.relpath(p, REPO_ROOT).replace(os.sep, '/')
                    rows.append((tree, rel, src))
    return rows


def _has_eager36(src):
    """认 <3.7 兜底分支：先剥掉全部空白再匹配，排版差异不影響判据。"""
    flat = _WS.sub('', src)
    return any(p.search(flat) for p in _EAGER_PATTERNS)


def test_lazy_getattr_modules_have_py36_fallback():
    """声明支持 3.6 的树里，每个"__getattr__ + __all__"模块都必须带 <3.7 主动绑定。"""
    offenders = []
    exempted = []
    judged = 0
    seen_trees = set()
    for tree, rel, src in _lazy_export_modules():
        spec, allows36 = _parse_requires_python(TREES[tree])
        assert spec, '%s 的 pyproject 解析不到 requires-python，守卫口径失效' % (TREES[tree])
        assert allows36 is not None, '%s 的 requires-python %r 解析不出下限' % (TREES[tree], spec)
        seen_trees.add(tree)
        judged += 1
        if allows36 and not _has_eager36(src):
            if rel in KNOWN_EXEMPTIONS:
                exempted.append(rel)
                continue
            offenders.append('[%s] %s (requires-python %s)' % (tree or 'core', rel, spec))
    # 反向守卫：确实判到东西，且覆盖多棵树（防目录被挪走导致"0 违规"假绿）
    assert judged >= 6, '只判到 %d 个惰性导出模块，守卫口径可能已塌缩' % judged
    assert len(seen_trees) >= 3, '只覆盖到 %d 棵树: %s' % (len(seen_trees), seen_trees)
    if offenders:
        raise AssertionError(
            '这些模块用模块级 __getattr__ 做惰性导出，所在包却声明支持 py3.6，而'
            'PEP 562 在 3.6 不生效 —— py3.6 下 __all__ 的名字全拿不到。请补一段 '
            '`if sys.version_info < (3, 7): ...` 主动绑定（同仓 vools/__init__.py、'
            'vools/datetime、vools/decorators、vools/sql 的做法）：\n  '
            + '\n  '.join(offenders))


def test_exemptions_are_still_needed():
    """豁免表不许腐烂成"顺手加一条就永久安静"：条目必须【仍然成立】。

    两种失效都要亮灯：
      a) 该模块后来补上了 <3.7 兜底 —— 豁免已无必要，应删掉条目；
      b) 该模块不再满足"__getattr__ + __all__"的形状 —— 同样应删掉条目。
    """
    rows = {(tree, rel): src for tree, rel, src in _lazy_export_modules()}
    stale = []
    for rel in sorted(KNOWN_EXEMPTIONS):
        src = None
        for (_tree, r), s in rows.items():
            if r == rel:
                src = s
                break
        if src is None:
            stale.append('%s: 已不是"__getattr__ + __all__"形态，豁免条目该删' % rel)
        elif _has_eager36(src):
            stale.append('%s: 已经带 <3.7 兜底了，豁免条目该删' % rel)
    assert not stale, '豁免表过期：\n  ' + '\n  '.join(stale)


def test_actus_style_37_only_trees_are_correctly_exempted():
    """反向保底：只声明 >=3.7 的树【不要求】兜底 —— 判据必须来自 pyproject，不许一刀切。"""
    spec, allows36 = _parse_requires_python(TREES['actus'])
    assert spec is not None, 'actus 的 requires-python 读不到'
    assert allows36 is False, \
        'actus 声明 %s，本用例前提（它不在 3.6 契约内）已变，请同步修守卫' % spec
    rows = [(rel, src) for t, rel, src in _lazy_export_modules() if t == 'actus']
    assert rows, 'actus 树里找不到惰性模块，本用例失去意义'


def test_detector_is_non_vacuous():
    """自校验：判据的两侧都必须有效 —— 合法写法逐个放行、缺失写法必须被抓。"""
    with_branch = (
        "import sys\n"
        "__all__ = ['x']\n"
        "def __getattr__(name):\n    raise AttributeError(name)\n"
        "if sys.version_info < (3, 7):\n    globals()['x'] = 1\n")
    without = (
        "import sys\n"
        "__all__ = ['x']\n"
        "def __getattr__(name):\n    raise AttributeError(name)\n")
    t1 = ast.parse(with_branch)
    t2 = ast.parse(without)
    assert _has_module_level_getattr(t1) and _has_module_all(t1)
    assert _has_eager36(with_branch), '带 <3.7 分支的合法写法被误判为缺失（会把正解也拦掉）'
    assert not _has_eager36(without), '没有兜底的写法没被抓到：守卫失明'

    # 等价排版/写法【逐个】断言，不用 or（or 会让"只认其中一种"也过关）
    equivalent = [
        "if sys.version_info < (3, 7):\n    pass\n",
        "if sys.version_info < (3,7):\n    pass\n",
        "if _sys.version_info < (3, 7):\n    pass\n",
        "if sys.version_info[:2] < (3, 7):\n    pass\n",
        "if sys.version_info <= (3, 6):\n    pass\n",
        "if sys.version_info.major == 3 and sys.version_info.minor < 7:\n    pass\n",
        "if sys.version_info[1] < 7:\n    pass\n",
    ]
    for s in equivalent:
        assert _has_eager36(s), '常见等价写法没被认出来（守卫会把合法代码判成违规）: %r' % s

    # 反面：只写 "3.7 以上才有的能力"判断，不是 <3.7 兜底分支，不能误放行
    not_fallback = [
        "_HAS_DATACLASSES = sys.version_info >= (3, 7)\n",
        "if sys.version_info > (3, 8):\n    pass\n",
    ]
    for s in not_fallback:
        assert not _has_eager36(s), '把 ">=3.7 能力判断" 当成兜底分支了（会放行缺兜底的代码）: %r' % s
