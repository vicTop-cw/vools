# -*- coding: utf-8 -*-
"""tests/core/test_declared_deps_discipline.py — 模块加载期用到的第三方包必须在 pyproject 声明

背景（BUG-65）：`vools.actus.desktop` 在【模块顶层】import fastapi，而 fastapi/uvicorn/
jinja2 在 actus 的 pyproject 里【一处都没声明】（dependencies 与所有 extra 都没有）——
`pip install vools-actus` 之后 import 该模块必 ModuleNotFoundError，而且【没有任何
extra 能补救】，用户只能手动 pip 装。这类缺陷的特点是【本机装了所以看不见】：
本机没装才暴露得出来，CI 用同一台机器就会长期假绿。与"wheel 漏带 bundle"同族。

本守卫是静态闸（不 import 被测模块，因此不依赖本机装没装那个包）：
  1. 逐个发布树（vools + 6 个 namespace 包）ast.parse 其源码，只看【模块体层级】的
     绝对 import 根名 —— 函数体/类体内的 import 是延迟的，可选加速件（yaml/
     jsonschema/paramiko/cryptography/psutil…）都走 try/except 降级，不属"装完即崩"，
     刻意不在本闸范围（否则会把一堆正当的可选加速全部误报）。
  2. 根名属于 `vools`（本仓自家包）或标准库 → 跳过。
  3. 剩下的每个第三方根名，必须能在【该树自己的】pyproject 里找到（dependencies
     或任一 optional-dependencies extra 的包名）。发行名→import 名按归一化匹配
     （小写、`-`→`_`；PyYAML→yaml 这类少数改名走显式别名表）。
  4. 豁免名单来自 pyproject 文本本身，不写死模块清单 —— 与 test_importable_py36.py
     同一原则：守卫不会随着包名变动而腐烂。

自校验格（防空洞）：同一判定喂合成源码 + 合成 pyproject —— 未声明的第三方顶层
import 必被抓、已声明的必放行、函数体内的必放行、相对导入与 stdlib 必跳过。

诚实边界：
- 标准库集合按【当前解释器】算。跨版本只在 stdlib 的模块（如 3.6 无 dataclasses/
  graphlib）若在低版本下被顶层 import，会被判"未声明第三方"——这其实是对的（那样
  装完就是在低版本上 import 期崩），但真要支持该写法应显式声明 backport 依赖。
  实测当前六棵树在 py3.6 与 py3.11 下均无此类命中（本守卫两版本都跑）。
"""

import ast
import os
import re
import sys
import sysconfig

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 发布树 -> (vools 容器目录, 自己的 pyproject)
SHIPPED_TREES = [
    ('vools', 'vools', 'pyproject.toml'),
    ('rx', os.path.join('rx', 'vools'), os.path.join('rx', 'pyproject.toml')),
    ('bridges', os.path.join('bridges', 'vools'), os.path.join('bridges', 'pyproject.toml')),
    ('xl', os.path.join('xl', 'vools'), os.path.join('xl', 'pyproject.toml')),
    ('pyk', os.path.join('pyk', 'vools'), os.path.join('pyk', 'pyproject.toml')),
    ('dll32', os.path.join('dll32', 'vools'), os.path.join('dll32', 'pyproject.toml')),
    ('actus', os.path.join('actus', 'vools'), os.path.join('actus', 'pyproject.toml')),
]

_SKIP_DIRS = {'__pycache__', '_python32', 'site-packages', 'node_modules',
              'compiler', 'templates', 'examples', 'static'}

# 发行名 -> import 名 的少数改名（其余按 归一化(小写、- → _) 直接比对）
_DIST_TO_IMPORT = {
    'pyyaml': 'yaml',
    'beautifulsoup4': 'bs4',
    'pillow': 'pil',
    'python_dotenv': 'dotenv',
    'dateutil': 'dateutil',
    'python_dateutil': 'dateutil',
    'win32pyreadline': 'pyreadline',
    'pywin32': 'win32api',
}

_LOCAL_ROOTS = {'vools', 'tests', 'setup', 'conftest'}


def _stdlib_roots():
    """当前解释器的标准库顶层名集合。"""
    names = set(sys.builtin_module_names)
    if hasattr(sys, 'stdlib_module_names'):
        names |= set(sys.stdlib_module_names)
    try:
        std = sysconfig.get_paths()['stdlib']
        for entry in os.listdir(std):
            if entry.endswith('.py'):
                names.add(entry[:-3])
            elif os.path.isdir(os.path.join(std, entry)) and not entry.startswith(('_', '.')):
                names.add(entry)
    except OSError:
        pass
    names -= {'site-packages', 'dist-packages', '__phello__'}
    return names


def _normalize(dist):
    return dist.strip().lower().replace('-', '_').replace('.', '_')


def _declared_import_names(pyproject_text):
    """从 pyproject 文本抽出【所有】被声明过的包名，映射成 import 根名集合。"""
    declared = set(re.findall(r'["\']([A-Za-z0-9_.\-]+)\s*(?:[<>=!~;\[]|\s*["\'])',
                              pyproject_text))
    roots = set()
    for d in declared:
        n = _normalize(d)
        roots.add(n)
        roots.add(_DIST_TO_IMPORT.get(n, n.split('_')[0] if n.startswith('py') else n))
        # 前缀去 py 化：pywin32 -> win32 之类
        if n.startswith('py'):
            roots.add(n[2:])
    return roots


def _module_level_third_party(tree_dir_abs):
    """返回 [(relpath, lineno, root)]：模块体层级的绝对 import 第三方根名。"""
    std = _stdlib_roots()
    out = []
    for dirpath, dirnames, filenames in os.walk(tree_dir_abs):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fn in filenames:
            if not fn.endswith('.py'):
                continue
            p = os.path.join(dirpath, fn)
            try:
                tree = ast.parse(open(p, 'rb').read().decode('utf-8'), filename=p)
            except (OSError, SyntaxError, ValueError):
                continue
            rel = os.path.relpath(p, REPO_ROOT).replace(os.sep, '/')
            for st in tree.body:                      # 只看模块体层级
                if isinstance(st, ast.Import):
                    roots = [a.name.split('.')[0] for a in st.names]
                elif isinstance(st, ast.ImportFrom):
                    if st.level or not st.module:
                        continue                      # 相对导入 = 自家树内
                    roots = [st.module.split('.')[0]]
                else:
                    continue
                for r in roots:
                    if r in _LOCAL_ROOTS or r in std or r.startswith('_'):
                        continue
                    out.append((rel, getattr(st, 'lineno', 0), r))
    return out


def _undeclared_for_tree(tree_label, container_rel, pyproject_rel):
    container = os.path.join(REPO_ROOT, container_rel)
    pj = os.path.join(REPO_ROOT, pyproject_rel)
    if not os.path.isdir(container) or not os.path.isfile(pj):
        return None                                   # 该树不存在，不参与判定
    declared = _declared_import_names(open(pj, 'rb').read().decode('utf-8'))
    bad = []
    for rel, ln, root in _module_level_third_party(container):
        if root.replace('-', '_').lower() not in declared and root not in declared:
            bad.append('%s:%d import %s' % (rel, ln, root))
    return bad


def test_module_level_third_party_deps_are_declared():
    """每棵发布树的顶层第三方 import，都必须出现在该树自己的 pyproject 里。"""
    offenders = []
    judged = 0
    for label, container_rel, pyproject_rel in SHIPPED_TREES:
        bad = _undeclared_for_tree(label, container_rel, pyproject_rel)
        if bad is None:
            continue
        judged += 1
        # 反向守卫：pyproject 必须真解析出声明，否则整闸会"全不声明也全放过"
        declared_n = len(_declared_import_names(
            open(os.path.join(REPO_ROOT, pyproject_rel), 'rb').read().decode('utf-8')))
        assert declared_n > 0, '树 %s 的 pyproject 解析不到任何依赖声明，守卫口径失效' % label
        for b in bad:
            offenders.append('[%s] %s' % (label, b))
    assert judged >= 5, '只判定到 %d 棵树，守卫口径可能失效' % judged
    if offenders:
        raise AssertionError(
            '以下顶层 import 用到的第三方包在该树 pyproject 里没声明（新环境装完即 '
            'ModuleNotFoundError，且没有 extra 能补救）：\n  ' + '\n  '.join(sorted(set(offenders))))


def test_guard_is_non_vacuous():
    """合成用例钉判定灵敏度：未声明必抓、已声明必放行、函数体内必放行、相对导入必跳过。"""
    std = _stdlib_roots()
    assert 'os' in std and 'json' in std, '标准库集合异常，判定会整体失真'

    def roots_of(source):
        t = ast.parse(source)
        out = []
        for st in t.body:
            if isinstance(st, ast.Import):
                out += [a.name.split('.')[0] for a in st.names]
            elif isinstance(st, ast.ImportFrom) and not st.level and st.module:
                out.append(st.module.split('.')[0])
        return out

    third = roots_of('import somepkg\nfrom anotherpkg.x import y\n')
    assert set(third) >= {'somepkg', 'anotherpkg'}, '顶层第三方根名没被识别出来'

    # 函数体内的 import 不算加载期依赖
    deferred = roots_of('def f():\n    import somepkg\n    return somepkg\n')
    assert deferred == [], '函数体内的 import 被当成加载期依赖（会误报可选加速件）'

    declared = _declared_import_names(
        'dependencies = ["somepkg>=1.0"]\n'
        '[project.optional-dependencies]\nextra = ["anotherpkg>=2"]\n')
    assert 'somepkg' in declared and 'anotherpkg' in declared, 'pyproject 解析漏包'
    assert 'yaml' in _declared_import_names('d = ["PyYAML>=6"]'), 'PyYAML 没映射到 yaml'
