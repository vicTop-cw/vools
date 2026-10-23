# -*- coding: utf-8 -*-
"""回归测试：lazy 延迟表达式阻断沙箱逃逸（BUG-361）。

`vools.decorators.lazy` 用 `eval(expr, safe_globals)` 求值 `->` / `=>` 表达式，
其中 `safe_globals` 只把 `__builtins__` 换成白名单（SAFE_BUILTINS）。文档称其为
"安全的内置函数白名单"——但 **eval + 受限 builtins 不是沙箱**：

    lazy("-> ().__class__.__base__.__subclasses__()")()
    # -> 375 个子类，含 Popen / BuiltinImporter / _wrap_close

即 `__import__`、`open` 虽被拦，仍可经 `__class__`/`__subclasses__`/`__globals__`
MRO 链拿到任意类（与 BUG-288 的 `str.format` 逃逸同族）。

修复：表达式路径在求值前做 AST 校验，拒绝
- 下划线开头的属性（`__class__`、`__subclasses__`、`__globals__`…）
- 下划线开头的名称（`__builtins__`…）
- `.format` / `.format_map`（BUG-288 逃逸面）
- `import` 语句

正常表达式（算术、白名单 builtin、调用者变量/模块属性、lambda、推导式）不受影响；
`def ...` 多行路径是**显式代码块**（非沙箱），保持可用。
"""

import math

import pytest

from vools.decorators.lazy import LazySecurityError, lazy


class TestNormalExpressionsUnchanged:
    def test_constant(self):
        assert lazy(5)() == 5

    def test_arrow_expression(self):
        assert lazy('=> 2 ** 8')() == 256

    def test_pow_builtin(self):
        # 文档示例：pow 不在 SAFE_BUILTINS 白名单但历史上可用，保持可用
        assert lazy('-> pow(2, 10)')() == 1024

    def test_parameters(self):
        assert lazy('a, b -> a + b')(3, 5) == 8

    def test_module_attribute_from_caller_scope(self):
        # math 在调用者 globals 中 —— 调用者作用域语义保持不变
        assert lazy('-> math.sqrt(16)')() == 4.0

    def test_callable_passthrough(self):
        assert lazy(lambda: 42)() == 42

    def test_list_comprehension(self):
        assert lazy('-> [x * 2 for x in range(3)]')() == [0, 2, 4]

    def test_lambda_expression(self):
        assert lazy('=> (lambda a: a + 1)(5)')() == 6

    def test_caller_local_variable(self):
        def scope():
            secret = 'LOCAL'
            return lazy('-> secret')()

        assert scope() == 'LOCAL'

    def test_multiline_def_still_works(self):
        fn = lazy('def f(x):\n    return x * 2')()
        assert fn(10) == 20


class TestEscapeVectorsBlocked:
    @pytest.mark.parametrize('expr', [
        '-> ().__class__.__base__.__subclasses__()',
        '-> (1).__class__',
        '-> pow.__globals__',
        '-> ().__class__.__bases__',
        '-> __builtins__',
    ])
    def test_dunder_access_blocked(self, expr):
        # 修复前：__subclasses__ 可达 375 个含 Popen 的类
        with pytest.raises(LazySecurityError):
            lazy(expr)

    @pytest.mark.parametrize('expr', [
        "-> '{0.__class__}'.format(1)",
        "-> '{a}'.format_map({'a': 1})",
    ])
    def test_format_escape_blocked(self, expr):
        with pytest.raises(LazySecurityError):
            lazy(expr)

    def test_import_statement_blocked(self):
        with pytest.raises(LazySecurityError):
            lazy('-> __import__("os")')

    def test_syntax_error_reports_clearly(self):
        with pytest.raises(LazySecurityError) as ei:
            lazy('-> 2 **')
        assert '无效的延迟表达式' in str(ei.value)


class TestDefPathIsExplicitCode:
    def test_def_not_sandboxed(self):
        # def 路径是显式代码块（文档语义），不做 AST 限制
        fn = lazy('def g(x):\n    return x + 1')()
        assert fn(1) == 2