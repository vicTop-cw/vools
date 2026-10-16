# -*- coding: utf-8 -*-
"""tests/test_collection_hygiene.py — 同一次收集里不得有两个测试文件解析成同一模块名（钉 BUG-74）

pytest 默认 prepend 导入模式下，测试文件的模块名由【最近的没有 __init__.py 的祖先
目录】当 basedir、相对它算点分名：
    tests/core/test_x.py（core 无 __init__.py）        -> 'test_x'
    tests/test_y.py（tests 有 __init__.py、仓库根没有）  -> 'tests.test_y'
    tests/md/test_utils.py（md 有 __init__.py）         -> 'tests.md.test_utils'
两个文件若落到同一个模块名，`pytest <两者>` 直接：
    "import file mismatch: imported module 'test_x' has this __file__ attribute ...
     which is not the same as the test file we want to collect"
    → Interrupted: 1 error during collection，整条退出码 2。

本仓真踩过（BUG-74）：我加的 tests/core/test_py36_compat.py 与既有
tests/data/test_py36_compat.py 同名，分目录各自跑全绿、合起来跑整条断，还把两个
py3.6 真失败一起藏了 5 天。

判定口径（为什么按【收集根分组】而不是全仓一把抓）：
  - 冲突只有在【同一次收集】里才致命。本仓默认 testpaths=["tests"]（根组），各命名
    空间是 `cd rx && pytest tests` 这样各自的根跑，两组永不同场。
  - 实测过：`pytest tests/core/test_import.py actus/tests/test_import.py` 同跑确实
    ERROR（跨根同名不是无害），所以跨根重复【单列一格】如实报出来（当前已知 1 组：
    test_import），并断言不再新增 —— 既不假装不存在，也不为历史遗留去改别人的文件。
  - 反向守卫：每组必须扫到测试文件（根组实测 122 个，阈值取 >90），防 glob 口径
    塌缩成空集假绿。
"""

import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 与 pyproject [tool.pytest.ini_options] addopts 的 --ignore 一致 + vendored/归档
IGNORED_DIR_NAMES = {
    'monitoring', 'benchmarks', 'archive', 'other',
    '__rust__', '__persist__', '__pycache__', 'node_modules',
    '_python32', 'site-packages', 'templates', 'Gen_Prompts', 'compiler',
}

# 收集根分组：每组 = 一种实际跑法（同组文件会被同一次收集装进同一个 sys.modules 空间）
GROUPS = [
    ('root', ['tests', 'tests_concurrent']),
    ('rx', ['rx/tests']),
    ('bridges', ['bridges/tests']),
    ('xl', ['xl/tests']),
    ('pyk', ['pyk/tests']),
    ('dll32', ['dll32/tests']),
    ('actus', ['actus/tests']),
]

# 跨收集根撞【有效模块名】：分根跑法碰不到，但同跑必炸 —— 历史已知 1 组
# （10-13 的 9bec243 起存在），只允许这些，新增即红。不替别人改名，但不许继续加。
KNOWN_CROSS_ROOT = {
    'test_import': frozenset(['tests/core/test_import.py', 'actus/tests/test_import.py']),
}


def _is_ignored_path(rel):
    return any(seg in IGNORED_DIR_NAMES for seg in rel.replace('\\', '/').split('/'))


def _effective_module_name(path):
    """按 pytest 规则算有效模块名（沿 __init__.py 链向上收包名）。"""
    parts = [os.path.splitext(os.path.basename(path))[0]]
    cur = os.path.dirname(path)
    while os.path.isfile(os.path.join(cur, '__init__.py')):
        parent = os.path.dirname(cur)
        if parent == cur:                      # 到文件系统根
            break
        parts.append(os.path.basename(cur))
        cur = parent
    return '.'.join(reversed(parts))


def _collect_groups():
    """返回 {组名: [(relpath, 有效模块名), ...]}。"""
    out = {}
    for gname, rel_dirs in GROUPS:
        rows = []
        for rd in rel_dirs:
            base = os.path.join(REPO_ROOT, rd.replace('/', os.sep))
            if not os.path.isdir(base):
                continue
            for dirpath, dirnames, filenames in os.walk(base):
                dirnames[:] = [d for d in dirnames if d not in IGNORED_DIR_NAMES]
                for fn in filenames:
                    if not (fn.startswith('test_') and fn.endswith('.py')):
                        continue
                    p = os.path.join(dirpath, fn)
                    rel = os.path.relpath(p, REPO_ROOT).replace(os.sep, '/')
                    if _is_ignored_path(rel):
                        continue
                    rows.append((rel, _effective_module_name(p)))
        out[gname] = rows
    return out


def test_no_duplicate_module_names_within_a_collection_root():
    """同一次收集内不得撞名（这才是会把套件整条打停的形状）。"""
    groups = _collect_groups()
    offenders = []
    for gname, rows in groups.items():
        assert rows, '收集根 %s 一个测试文件都没扫到，守卫口径已塌缩' % gname
        if gname == 'root':
            # 实测当前根组 122 个测试文件（tests + tests_concurrent，排除 --ignore
            # 目录后）。阈值取 90 留新增余量，又能抓住"目录被挪走/口径塌缩"。
            assert len(rows) > 90, '根组仅 %d 个文件，口径可能失效' % len(rows)
        seen = {}
        for rel, mod in rows:
            if mod in seen:
                offenders.append('%s: %s  <- %s / %s' % (gname, mod, seen[mod], rel))
            else:
                seen[mod] = rel
    if offenders:
        raise AssertionError(
            '同一次收集里这些文件解析成同一模块名，会让整条 `pytest` 因 import file '
            'mismatch 中止（exit=2）并顺带藏掉真实失败。改文件名，或给该目录加 '
            '__init__.py：\n  ' + '\n  '.join(offenders))


def test_no_new_cross_root_duplicates():
    """跨收集根撞【有效模块名】：分根跑没事，同跑必 collection ERROR —— 历史 1 组已备案，不许新增。

    判据是 pytest 的有效模块名而不是文件名：tests/core/test_utils.py('test_utils')
    与 tests/md/test_utils.py('tests.md.test_utils') 永不相撞，不该被报。
    """
    groups = _collect_groups()
    by_mod = {}
    for gname, rows in groups.items():
        for rel, mod in rows:
            by_mod.setdefault(mod, []).append((gname, rel))
    new = []
    for mod, hits in sorted(by_mod.items()):
        files = [rel for _g, rel in hits]
        if len(files) < 2:
            continue
        known = KNOWN_CROSS_ROOT.get(mod)
        if known is not None and set(files) <= set(known):
            continue
        # 同根内部重复由上一格负责报，这里只管跨根
        if len({g for g, _r in hits}) > 1:
            new.append('%s  <- %s' % (mod, ' / '.join(files)))
    if new:
        raise AssertionError(
            '出现新的跨收集根同名模块（把两种根放同一次 pytest 里会因 import file '
            'mismatch 整条中止）：\n  ' + '\n  '.join(new) +
            '\n请改名；若确属有意，把它加进 KNOWN_CROSS_ROOT 并说明为什么安全。')
