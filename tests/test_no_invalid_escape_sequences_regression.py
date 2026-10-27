# -*- coding: utf-8 -*-
"""回归测试：全库不得存在"无效转义序列"（BUG-343）。

## 缺陷

``vools/data/vtext.py`` 的 ``_strip_sql_comments`` docstring 里写了正则
``/\\*.*?\\*/``，但字符串**不是 raw**，于是 ``\\*`` 成了"无效转义序列"：

* Python 3.11 → ``DeprecationWarning: invalid escape sequence '\\*'``
* Python 3.12+ → ``SyntaxWarning: invalid escape sequence '\\*'``

后果：每个 import 该模块的用户都会在 stderr 看到这条警告（3.12+ 尤其显眼），
且在 ``-W error`` 环境下直接 import 失败。根因是文档里画正则时忘了 raw 前缀。

修复：该 docstring 改为 ``r\"\"\"...\"\"\"``（仍保留 ``/\\*.*?\\*/`` 的字面形态）。

## 本测试

对 ``vools`` 全库逐文件 ``compile()``，捕获"无效转义"类
DeprecationWarning/SyntaxWarning，确保 0 处——避免同类问题再次混入。
"""

import io
import os
import warnings

import pytest

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vools")


def _iter_py_files():
    for root, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in files:
            if name.endswith(".py"):
                yield os.path.join(root, name)


def _invalid_escape_warnings(path):
    src = io.open(path, encoding="utf-8", errors="replace").read()
    found = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            compile(src, path, "exec")
        except SyntaxError as exc:            # 语法错误另算（不该出现）
            return [(getattr(exc, "lineno", 0), "SyntaxError: " + str(exc)[:120])]
    for w in caught:
        if issubclass(w.category, (DeprecationWarning, SyntaxWarning)) and "escape" in str(w.message):
            found.append((w.lineno, f"{w.category.__name__}: {w.message}"))
    return found


class TestNoInvalidEscapeSequences:
    def test_vtext_docstring_is_raw(self):
        """直接钉住出问题的那个 docstring：正则示例必须原样呈现。"""
        from vools.data.vtext import _strip_sql_comments

        doc = _strip_sql_comments.__doc__ or ""
        assert r"/\*.*?\*/" in doc

    def test_whole_package_compiles_without_invalid_escape(self):
        offenders = []
        for path in _iter_py_files():
            bad = _invalid_escape_warnings(path)
            if bad:
                rel = os.path.relpath(path, os.path.dirname(ROOT)).replace("\\", "/")
                for lineno, msg in bad:
                    offenders.append(f"{rel}:L{lineno} {msg}")
        assert offenders == [], "存在无效转义序列（改用 raw 字符串）：\n" + "\n".join(offenders)

    def test_scanner_actually_detects_a_known_bad_snippet(self, tmp_path):
        """反向自检：扫描器必须能发现故意写坏的样例，否则上面的 0 命中不可信。"""
        bad = tmp_path / "bad_escape.py"
        bad.write_text('DOC = """正则 /\\*x\\*/ 未加 raw 前缀"""\n', encoding="utf-8")
        found = _invalid_escape_warnings(str(bad))
        assert any("escape" in msg for _, msg in found), found
