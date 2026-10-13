"""锁定各分发包声明的 Python 地板与其【真实】源码语法一致。

背景：vools-actus 曾声明 requires-python>=3.6，实际 sigma.py 早已用 3.7 的
`from __future__ import annotations`，py3.6 装上即 SyntaxError（2026-10-13
修复为 >=3.7）。光靠肉眼 grep 会把正则字符类 `[:=]` 误判成海象、把 docstring
里的 `|` 误判成 PEP604。这里用 AST 精确计算每个子项目 vools/ 源码树的语法地板，
再与该子包 pyproject 的 requires-python 比对，声明不得【低于】真实地板
（声明更高是允许的，例如保守）。

判据（语法层面）：
  - 出现 `from __future__ import annotations`  -> >= 3.7（PEP 563）
  - 海象 NamedExpr / match 语句                -> >= 3.8 / 3.10
  - 求值位置的 PEP604 `X | Y` 注解             -> >= 3.10
    （被 future annotations 延迟不求值时不算，3.7 即可）
注：标准库 dataclasses 等 3.7 模块不在 AST 可见范围，各包统一走
core.compat.dataclass_compat 垫片在 3.6 回退，不在此测试判定内。
"""

import ast
import os
import re

import pytest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 分发包 -> (pyproject.toml 相对路径, 源码树相对路径)
# 核心包源码直接在仓库根 vools/，子项目在 <pkg>/vools。
_PKGS = {
    "core": ("pyproject.toml", "vools"),
    "actus": ("actus/pyproject.toml", "actus/vools"),
    "bridges": ("bridges/pyproject.toml", "bridges/vools"),
    "rx": ("rx/pyproject.toml", "rx/vools"),
    "pyk": ("pyk/pyproject.toml", "pyk/vools"),
    "xl": ("xl/pyproject.toml", "xl/vools"),
    "dll32": ("dll32/pyproject.toml", "dll32/vools"),
}

_REQ_RE = re.compile(r'requires-python\s*=\s*">=\s*3\.(\d+)"')


def _declared_floor(pyproject_path):
    txt = open(pyproject_path, "r", encoding="utf-8").read()
    m = _REQ_RE.search(txt)
    return (3, int(m.group(1))) if m else None


class _FloorFinder(ast.NodeVisitor):
    def __init__(self, future_annot):
        self.future_annot = future_annot
        self.walrus = False
        self.match = False
        self.bitor_runtime = False

    def visit_NamedExpr(self, n):
        self.walrus = True
        self.generic_visit(n)

    def visit_Match(self, n):
        self.match = True
        self.generic_visit(n)

    def visit_FunctionDef(self, n):
        self._ann(n.returns)
        for a in (list(n.args.args) + list(n.args.kwonlyargs)
                  + list(getattr(n.args, "posonlyargs", []))):
            self._ann(a.annotation)
        self.generic_visit(n)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_AnnAssign(self, n):
        self._ann(n.annotation)
        self.generic_visit(n)

    def _ann(self, ann):
        if self.future_annot or ann is None:
            return
        for x in ast.walk(ann):
            if isinstance(x, ast.BinOp) and isinstance(x.op, ast.BitOr):
                self.bitor_runtime = True


# 扫描时跳过的目录：vendored 的第三方代码 / 内嵌解释器运行时 / 缓存。
# 这些不是本项目要负责兼容的自有源码（dll32 内嵌了一整套 _python32 运行时）。
_SCAN_SKIP_DIRS = {"__pycache__", "_python32", "site-packages", ".venv",
                   "node_modules", "Lib"}


def _syntax_floor(pkg_dir):
    floor = (3, 6)
    future = walrus = match = bitor = False
    for dp, dirs, fns in os.walk(pkg_dir):
        dirs[:] = [d for d in dirs if d not in _SCAN_SKIP_DIRS]
        for fn in fns:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(dp, fn)
            src = open(path, "rb").read()
            tree = ast.parse(src, filename=path)
            # 用 AST 判定真实的 future 导入，不能用子串匹配——注释/docstring
            # 里出现这行字（包括本文件自己的说明）会造成误报。
            has_future = any(
                isinstance(n, ast.ImportFrom)
                and n.module == "__future__"
                and any(a.name == "annotations" for a in n.names)
                for n in ast.walk(tree)
            )
            f = _FloorFinder(has_future)
            f.visit(tree)
            future |= has_future
            walrus |= f.walrus
            match |= f.match
            bitor |= f.bitor_runtime
    if walrus:
        floor = max(floor, (3, 8))
    if match or bitor:
        floor = max(floor, (3, 10))
    if future:
        floor = max(floor, (3, 7))
    return floor


@pytest.mark.parametrize("pkg", sorted(_PKGS))
def test_declared_python_floor_covers_real_syntax(pkg):
    rel_proj, rel_src = _PKGS[pkg]
    pyproject = os.path.join(_REPO, rel_proj)
    assert os.path.isfile(pyproject), pyproject
    declared = _declared_floor(pyproject)
    assert declared is not None, "缺少 requires-python 声明"

    pkg_src = os.path.join(_REPO, rel_src)
    if not os.path.isdir(pkg_src):
        pytest.skip("%s 源码树不存在" % pkg_src)
    real = _syntax_floor(pkg_src)
    # 声明的地板必须 >= 真实语法地板；低于它意味着旧解释器装上即 SyntaxError
    assert declared >= real, (
        "%s 声明 requires-python>=%d.%d，但源码已用到 %d.%d 语法"
        % (pkg, declared[0], declared[1], real[0], real[1])
    )
