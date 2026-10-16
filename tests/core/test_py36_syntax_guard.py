# -*- coding: utf-8 -*-
"""tests/core/test_py36_syntax_guard.py — py3.6 语法合规守卫（钉住 BUG-59 族回归）

（原名 tests/core/test_py36_compat.py；与既有 tests/data/test_py36_compat.py 撞
pytest 有效模块名，导致 `pytest tests` 整条 import file mismatch 中止，故改名 ——
账本 BUG-74，永久防撞守卫见 tests/test_collection_hygiene.py。）

背景：本项目的验收口径要求双版本可跑（py3.11 + `E:\\Python36`），而 py3.6 对
py3.7+ 才有的语法会直接 SyntaxError——例如 BUG-59：`tests_concurrent/` 里残留一行
`from __future__ import annotations`（该 future 要求 py3.7+），整目录在 py3.6
收集即炸；再如 f-string `=`、walrus `:=`、`async` 关键词别名等。这类问题散落地
新增时【没有任何测试会挡住】——它只在"恰好有人用 py3.6 跑了那个文件"时才暴露。

本守卫就是那道人不用在场也能亮灯的闸：把发布包树与被收集/独立跑的测试树里每个
.py 都过一遍 `compile()`。在 py3.6 解释器下跑时，任何 py3.7+ 语法都会被抓出来；
在 py3.11 下跑时是同一条断言的真实通过（不是跳过、不是放宽——两版本都真跑真断言）。

口径边界（诚实声明）：这是【语法级】守卫。import py3.8 才有的标准库名字（如
`typing.Literal`，BUG-56 旁边那类）、或 py3.7+ 才有的函数参数（capture_output）
不在 compile() 的可见范围内，那类由"真在 py3.6 上 import/运行"的测试负责。

扫描面刻意【不含】tests/archive 与 tests/other：前者是 pyproject 显式 --ignore
的归档区（内有刻意保留的 py3.8+ 试验残留），后者依赖本机 GUI/Tcl 环境；把它们
拉进来只会制造与口径无关的红灯。
"""

import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 发布包树（含各 namespace 子包的 vools/ 容器）
_SHIPPED = ['vools',
            os.path.join('rx', 'vools'),
            os.path.join('bridges', 'vools'),
            os.path.join('xl', 'vools'),
            os.path.join('actus', 'vools'),
            os.path.join('pyk', 'vools'),
            os.path.join('dll32', 'vools')]

# 测试树：被 pytest 收集、或按项目验证协议会用 py3.6 跑的目录
_TEST_TREES = ['tests', 'tests_concurrent',
               os.path.join('bridges', 'tests'),
               os.path.join('rx', 'tests'),
               os.path.join('actus', 'tests'),
               os.path.join('xl', 'tests'),
               os.path.join('pyk', 'tests'),
               os.path.join('dll32', 'tests')]

# 与 pyproject addopts 的 ignore 名单保持一致
_EXCLUDED_TOP = {'monitoring', 'benchmarks', 'archive', 'other',
                 '__rust__', '__persist__', '__pycache__'}

# 整段跳过的目录名（vendored 第三方 / 内嵌独立解释器自带库，不归本项目管）
_SKIP_DIRS = {'__pycache__', '_python32', 'site-packages', 'node_modules',
              '.venv', 'Gen_Prompts', 'compiler'}


def _iter_py_files():
    """产出扫描范围内的 (绝对路径, 相对路径)。"""
    trees = _SHIPPED + _TEST_TREES
    for rel_base in trees:
        base = os.path.join(REPO_ROOT, rel_base)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            # 就地裁剪：不进入 vendored 目录
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            # 根 tests/ 下的显式 ignore 名单
            if os.path.abspath(dirpath) == os.path.abspath(base):
                dirnames[:] = [d for d in dirnames
                               if not (rel_base == 'tests' and d in _EXCLUDED_TOP)]
            for f in filenames:
                if f.endswith('.py'):
                    p = os.path.join(dirpath, f)
                    yield p, os.path.relpath(p, REPO_ROOT)


def _collect_offenders():
    """返回 (offenders, scanned)：offenders 是 (relpath, 报错一行) 列表。"""
    offenders = []
    scanned = 0
    for path, rel in _iter_py_files():
        scanned += 1
        try:
            with open(path, 'rb') as fh:
                raw = fh.read()
        except OSError as e:
            offenders.append((rel, 'read error: %s' % e))
            continue
        try:
            src = raw.decode('utf-8')  # 仓库约定：.py 一律 UTF-8
        except UnicodeDecodeError as e:
            offenders.append((rel, 'not valid UTF-8: %s' % e))
            continue
        try:
            # 用当前解释器编译本文件；py3.6 下任何 py3.7+ 语法在此抛 SyntaxError。
            # dont_inherit=True：不继承本模块的 __future__ 语句，逐文件独立判定。
            compile(src, path, 'exec', dont_inherit=True)
        except SyntaxError as e:
            offenders.append((rel, 'line %s: %s' % (e.lineno, e.msg)))
        except ValueError:
            # 含 NUL 字节等"非源码"内容，同样视为坏文件
            offenders.append((rel, 'ValueError (not a valid source file)'))
    return offenders, scanned


def test_py36_syntax_guard():
    """发布包与测试树里每个 .py 都必须能被【当前】解释器编译。

    在 E:\\Python36 下运行本测试即钉住"py3.6 可解析"这条口径（BUG-59 族）；
    在 py3.11 下运行是同一条断言的真实通过。两版本都是真跑真断言，无 skip、
    无放宽、无按版本分支放行。
    """
    offenders, scanned = _collect_offenders()
    # 反向守卫：扫描面塌缩成空集 = 本测试失去意义（防路径重构悄悄让它 0 文件空过）
    assert scanned > 500, '扫描文件数 %d 异常（树被挪走？口径失效）' % scanned
    if offenders:
        detail = '\n'.join('  %s :: %s' % (r, m) for r, m in offenders[:20])
        pytest.fail('当前解释器 %s 无法编译以下 %d/%d 个文件：\n%s'
                    % ('.'.join(map(str, sys.version_info[:3])),
                       len(offenders), scanned, detail))
