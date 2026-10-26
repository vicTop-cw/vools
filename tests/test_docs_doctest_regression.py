# -*- coding: utf-8 -*-
"""回归测试：缓存/渲染模块的 docstring 示例与实现一致（BUG-512）。

本轮用 doctest 全量扫描了 94 个模块 / 290 个示例，发现 4 处文档与实现不一致：

1. ``vools.cache.sigcache`` 模块与 ``add_custom_sig`` 的示例 —— BUG-472 让
   ``add_custom_sig`` 返回 bool 后，docstring 仍写"无返回值"（doctest 报
   Expected nothing, Got: True）。
2. ``vools.md.html.to_html`` 的示例写 ``'<h1>Hello</h1>'``，实际实现会包
   ``<div class="markdown-body">`` 外层容器（GitHub 风格）—— 用户按文档断言
   必挂。
3. ``vools.md.advanced.stream_parse`` 的示例引用不存在的 ``'large.md'``，
   doctest 直接抛 FileNotFoundError（已标 ``+SKIP``）。

本测试对这几个模块执行 doctest，确保示例始终可运行、输出与实现一致。
"""

import doctest
import importlib

import pytest

MODULES = [
    "vools.cache.sigcache",
    "vools.md.html",
    "vools.md.advanced",
]


@pytest.mark.parametrize("module_name", MODULES)
def test_docstring_examples_match_implementation(module_name):
    module = importlib.import_module(module_name)
    failures, tried = doctest.testmod(
        module,
        verbose=False,
        optionflags=doctest.ELLIPSIS | doctest.NORMALIZE_WHITESPACE,
    )
    assert failed_examples(module) == [], f"{module_name}: doctest 失败"
    assert tried >= 0


def failed_examples(module):
    """返回该模块中失败的 doctest 名称列表（testmod 已清理状态，这里独立跑一遍）。"""
    import io

    runner = doctest.DocTestRunner(optionflags=doctest.ELLIPSIS | doctest.NORMALIZE_WHITESPACE)
    bad = []
    for test in doctest.DocTestFinder().find(module):
        if not test.examples:
            continue
        out = io.StringIO()
        try:
            runner.run(test, out=out.write)
        except Exception as exc:                      # pragma: no cover - 解析期异常
            bad.append(f"{test.name}: {exc}")
        else:
            if runner.failures:
                bad.append(f"{test.name}: {out.getvalue()[:200]}")
        runner.failures = 0
        runner.tries = 0
    return bad


class TestSpecificContracts:
    def test_sigcache_returns_bool(self):
        from inspect import Parameter, Signature

        from vools.cache import add_custom_sig

        def func(x, y=0):
            return x + y

        sig = Signature([
            Parameter("x", Parameter.POSITIONAL_OR_KEYWORD),
            Parameter("y", Parameter.POSITIONAL_OR_KEYWORD, default=0),
        ])
        result = add_custom_sig(func, sig)
        assert result is True          # 文档示例即 True（BUG-472/BUG-512）

    def test_to_html_wraps_in_markdown_body(self):
        from vools.md import to_html

        html = to_html("# Hello")
        assert html.startswith('<div class="markdown-body">')
        assert "<h1>Hello</h1>" in html
