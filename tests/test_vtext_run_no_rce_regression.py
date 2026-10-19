# -*- coding: utf-8 -*-
"""回归测试：VText._run 不得任意代码执行（BUG-206）。

原 `_run(self, func=exec)` 默认参数即 exec，且 exec(text)/eval(text) 裸调用无
globals/locals 隔离，任意文本内容 RCE。修复：默认 func=None（无参不执行），
exec/eval 分支使用受限命名空间 _RUN_SAFE_NAMESPACE（白名单 builtins），
__import__/open/getattr 等不可访问。
"""

import pytest

from vools.data.vtext import VText


class TestRunEvalSafe:
    """eval 分支：算术可用，RCE 被拒（BUG-206）。"""

    def test_eval_arithmetic(self):
        assert VText('1+1').run('eval') == 2

    def test_eval_multiplication(self):
        assert VText('2*3')._run('eval') == 6

    def test_eval_import_blocked(self):
        with pytest.raises(Exception):
            VText("__import__('os').getcwd()")._run('eval')

    def test_eval_open_blocked(self):
        with pytest.raises(Exception):
            VText("open('nope.txt')")._run('eval')


class TestRunExecSafe:
    """exec 分支：简单赋值可用，RCE 被拒（BUG-206）。"""

    def test_exec_simple_assign(self):
        # 不应抛异常
        VText("x = 1 + 1")._run('exec')

    def test_exec_import_blocked(self):
        with pytest.raises(Exception):
            VText("__import__('os').getcwd()")._run('exec')


class TestRunDefaultNoExec:
    """默认 func=None，无参 _run() 不执行任意代码（BUG-206）。"""

    def test_no_arg_raises(self):
        with pytest.raises(ValueError):
            VText("1+1")._run()

    def test_default_exec_callable_blocked(self):
        # 显式传 exec 也走受限命名空间
        with pytest.raises(Exception):
            VText("__import__('os').getcwd()")._run(exec)


class TestRunCustomCallable:
    """自定义可调用对象仍正常。"""

    def test_lambda(self):
        assert VText('abc')._run(lambda s: s.upper()) == 'ABC'

    def test_empty_text(self):
        assert VText('')._run() is None
        assert VText('   ')._run('eval') is None