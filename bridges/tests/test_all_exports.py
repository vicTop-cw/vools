# -*- coding: utf-8 -*-
"""bridges/tests/test_all_exports.py — bridge 包每个模块的 __all__ 必须【可兑现】（钉幻影名回归）。

同族缺陷（一次寻虫抓到 54 处，全在 bridge/）：

各语言子包的 compiler.py / types.py / api/*.py / loader.py 把「类方法名」写进
`__all__`，而这些名字在模块级根本不存在。例如：

  bridge.vbnet.api.filesystem.__all__ 列了
  ['FileSystemModule', 'CreateDirectory', 'DeleteDirectory', ...]，
  但 CreateDirectory 只是 FileSystemModule 的一个方法，不是模块级函数 ——
  `from bridge.vbnet.api.filesystem import CreateDirectory` 实测 AttributeError；
  star import 时 Python 会静默跳过不存在的名字，所以这个 bug 一直"看着能用"。

根因：某次批量补 `__all__` 时，把类里的方法名一起抄进了列表，没有校验
"这个名字是不是模块级名字"。

本锁按"__all__ 里的每个名字必须在模块命名空间里能 getattr 到"的通用形状断言，
而不是逐个点名 —— 将来再加语言子包时漏写也会亮。

测试不挑环境：只做静态的 __all__ 兑现性检查。对 import 失败（可能因依赖未装）的
模块，跳过并收集到 skipped 列表，避免把"缺依赖"误报为"__all__ 有幻影名"。
py3.6 兼容：无 walrus / f-string 之外的新语法依赖。
"""

import importlib
import os
import sys

import pytest

_BRIDGES_VOOLS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'vools'
)
if _BRIDGES_VOOLS not in sys.path:
    sys.path.insert(0, _BRIDGES_VOOLS)

# 他人正在开发的新子包目录（git status 显示 ?? 未提交），本锁不扫，避免冲突。
SKIP_DIR_PARTS = {'bat', 'md', 'rich', '__pycache__'}


def _walk_modules():
    """遍历 bridge/ 下所有非 __init__ 的 .py 模块（跳过未提交的 WIP 目录）。"""
    for dirpath, _dirnames, filenames in os.walk(_BRIDGES_VOOLS):
        parts = os.path.relpath(dirpath, _BRIDGES_VOOLS).split(os.sep)
        if any(p in SKIP_DIR_PARTS for p in parts):
            continue
        if '__init__.py' not in filenames:
            continue
        rel = os.path.relpath(dirpath, _BRIDGES_VOOLS).replace(os.sep, '.')
        pkg = rel if rel != '.' else os.path.basename(_BRIDGES_VOOLS)
        for fn in filenames:
            if fn.endswith('.py') and fn != '__init__.py':
                yield pkg + '.' + fn[:-3]


def test_all_exports_have_no_phantom_names():
    """__all__ 里的每个名字必须是模块级真实名字，不得是类方法名或幻影名。

    修复前 54 个模块把 CreateDirectory/FindWindow/compile_code 等方法名写进
    __all__，而它们只作为类方法存在，模块级根本没有。
    """
    skipped = []
    bad = []
    checked = 0
    for fq in _walk_modules():
        try:
            mod = importlib.import_module(fq)
        except Exception as exc:
            skipped.append((fq, type(exc).__name__))
            continue
        all_list = getattr(mod, '__all__', None)
        if all_list is None:
            continue
        checked += 1
        names = set(dir(mod))
        phantom = [n for n in all_list if n not in names]
        if phantom:
            bad.append((fq, phantom))
    # skipped 只作报告，不作失败 —— 缺依赖不是 __all__ 的锅。
    print('checked=%d, skipped=%d (依赖未装): %s' % (
        checked, len(skipped), [s[0] for s in skipped]))
    assert not bad, (
        '%d 个模块 __all__ 含模块级不存在的名字：%s'
        % (len(bad), '; '.join('%s -> %s' % (f, p) for f, p in bad[:5]))
    )