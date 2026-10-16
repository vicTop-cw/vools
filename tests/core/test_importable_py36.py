# -*- coding: utf-8 -*-
"""tests/core/test_importable_py36.py — 核心包每个模块都必须【真的能 import】（双版本）

补 test_py36_compat.py 的盲区：那把守卫是 compile()，只管【语法】——管不到
`from typing import Literal`（py3.8 才有）这类**语法合法但加载期 ImportError** 的
硬依赖，也管不到循环导入（BUG-56 就是 import vools.data 在 py3.11 直接炸，语法
一点错没有）。本守卫用真办法：在当前解释器里逐个 import 核心树的全部模块。

口径要点（为什么这样设计才不误报也不漏报）：
1. 扫描面按【文件系统】枚举 vools/**/*.py，不用 pkgutil.walk_packages —— 后者在某
   个包 import 失败时会停止递归进去，不同解释器看到的模块数会不一样（实测
   py3.11 与 py3.6 若用 walk 口径会漂移），文件系统枚举保证两版本扫同一批模块。
2. 允许失败的【唯一】理由：该模块因缺少某个 **pyproject 里声明过的可选依赖**
   （extras：typer/fire/cryptography/msgpack/…）而 ModuleNotFoundError。这类是
   "环境没装 extra"，不是代码回归（例：vools.api* 需要 cli extra 的 typer，
   没装就导不进来，属设计如此）。豁免名单从 pyproject 动态解析，不写死模块清单，
   免得守卫自己烂掉。
3. 除上面这一类外的任何失败都算违规：
   - `ImportError: cannot import name 'Literal'`（py3.6 加载期撞 py3.8 名字）
   - 循环导入（BUG-56 族）
   - 加载期硬 import 可选兄弟分发（BUG-57 族；本仓另有静态闸双保险）
   - 导入期抛任何异常（副作用/环境假设）
4. 反向守卫：扫到的模块数必须 >150，防目录被挪走后空过；且要求"豁免确有生效"
   ——若当前环境把可选依赖都装齐了，允许集为空也照样通过（不误报）。

诚实边界：只测【导入成功】这件事，不测导入后的行为正确性；被测模块在导入期可能
有轻量副作用（核心包基本是纯定义 + 惰性初始化，实测全树 import 秒级完成）。
"""

import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CORE = os.path.join(REPO_ROOT, 'vools')
PYPROJECT = os.path.join(REPO_ROOT, 'pyproject.toml')

_SKIP_DIRS = {'__pycache__', '_python32', 'site-packages', 'node_modules',
              'compiler', 'templates', 'examples', 'static'}


def _iter_core_module_names():
    """按文件系统枚举核心树模块名（版本无关，两解释器同一批）。"""
    names = set()
    for dirpath, dirnames, filenames in os.walk(CORE):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fn in filenames:
            if not fn.endswith('.py') or fn == '__main__.py':
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), REPO_ROOT)[:-3]
            rel = rel.replace(os.sep, '/')
            if rel.endswith('/__init__'):
                rel = rel[: -len('/__init__')]
            names.add(rel.replace('/', '.'))
    return sorted(names)


def _optional_dep_import_roots():
    """从 pyproject 的 optional-dependencies 解析出【可选依赖】对应的 import 根名。

    发行名 → import 名的映射按惯例做归一（小写、`-`→`_`），例如
    `typing-extensions` → `typing_extensions`、`typer` → `typer`。
    只认 extras 段的包名：核心 dependencies 缺席属于环境坏了，不该被豁免。
    """
    try:
        text = open(PYPROJECT, 'r', encoding='utf-8').read()
    except OSError:
        return set()
    m = re.search(r'\[project\.optional-dependencies\](.*?)(?:\n\[|\Z)', text, re.S)
    if not m:
        return set()
    names = set()
    for dist in re.findall(r'["\']([A-Za-z0-9_.\-]+)\s*(?:[<>=!~;\[])', m.group(1)):
        low = dist.strip().lower().replace('-', '_')
        names.add(low)
        # vools-bridges 这类兄弟分发包提供的是 vools.<x>，不该豁免 vools 根；
        # 因此只额外登记去前缀后的裸名（bridge → 供 `import bridge`），
        # 绝不登记 'vools'。
        if low.startswith('vools_'):
            names.add(low[len('vools_'):])
    return names


def _missing_root_of(exc):
    """ModuleNotFoundError 时取缺失的顶层 import 名，否则 None。"""
    if isinstance(exc, ModuleNotFoundError):
        name = getattr(exc, 'name', None) or ''
        return name.split('.')[0] if name else None
    return None


def test_all_core_modules_importable():
    """核心树每个模块在当前解释器下必须可 import（缺已声明的可选依赖除外）。"""
    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)

    import importlib

    allowed_roots = _optional_dep_import_roots()
    mods = _iter_core_module_names()
    assert len(mods) > 150, '核心树仅枚举到 %d 个模块，守卫口径可能失效' % len(mods)

    violations = []
    excused = []
    for mod in mods:
        if mod in sys.modules:
            continue                       # 已被同会话其它测试导入，视为通过
        try:
            importlib.import_module(mod)
        except Exception as e:
            missing = _missing_root_of(e)
            if missing and missing in allowed_roots:
                excused.append((mod, missing))
                continue
            violations.append('%s :: %s %s' % (mod, type(e).__name__, str(e)[:120]))
    # 说明：不做 sys.modules 回滚 —— 半路卸载已导入包会让后续依赖它的测试拿到
    # 二次初始化的副本（类身份断裂，同 _ai_local_bootstrap 记过的坑）。核心树模块
    # 本就会被正常测试导入，留着是更安全的选择。
    if violations:
        raise AssertionError(
            '以下核心模块在当前解释器 %s 下无法 import（缺已声明可选依赖之外的失败）：'
            '\n  %s' % ('.'.join(map(str, sys.version_info[:3])),
                        '\n  '.join(violations[:25])))
