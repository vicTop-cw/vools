# -*- coding: utf-8 -*-
"""回归测试：placeholder 表达式求值不得任意代码执行（BUG-208）。

原 `_IndexHolder.__init__` 默认 env 塞完整 builtins 模块且无 `__builtins__`
键（Python 自动注入真实 builtins），`call`/`__expr__` 对用户表达式 eval/exec
→ `__import__('os').getcwd()`、`math.__loader__.load_module('sys')`、
`().__class__.__bases__[0].__subclasses__()`、`operator.attrgetter('__class__')`
等对象图逃逸链全部可走通。

修复（双层）：
- 受限 `__builtins__`（safe_builtins + getattr/hasattr，DSL 属性链编译代码
  需要）注入默认 env 与 `__expr__` 的 exec namespace；
- `_check_expr_dangerous` AST 级拒绝 dunder 属性访问 / '__*' 字符串常量 /
  dunder 裸名，斩断逃逸链（与 vools/security/safe_eval 的安全口径一致但
  不误伤默认表达式 `lambda x,*_,**__` 的参数名）。
"""

import pytest

from vools.functional.placeholder import _IndexHolder, _1, _2, _


class TestEvalBlocked:
    """`.call` 入口必须拒绝一切逃逸链（BUG-208）。"""

    @pytest.mark.parametrize("expr", [
        "__import__('os').getcwd()",
        "builtins.__import__('os').getcwd()",
        "getattr(builtins, '__import__')('os').system('echo x')",
        "math.__loader__.load_module('sys')",
        "().__class__.__bases__[0].__subclasses__()",
        "operator.attrgetter('__class__')(1)",
        "builtins.__loader__",
        "open('nope.txt')",
        "eval('1+1')",
    ])
    def test_call_blocks_escape_chain(self, expr):
        with pytest.raises(NameError):
            _IndexHolder(expr).call

    def test_expr_def_path_blocks(self):
        h = _IndexHolder()
        with pytest.raises(NameError):
            h.__expr__("().__class__", mode='single', func_type='def')


class TestLegitStillWorks:
    """合法 DSL 不受影响（防修复过度）。"""

    def test_placeholder_arith(self):
        assert (_1 + 1)(5) == 6
        assert (_2 * 2)(5) == 10

    def test_math_operator(self):
        assert _IndexHolder("math.sqrt(4)").call == 2.0
        assert _IndexHolder("operator.add(1, 2)").call == 3

    def test_restricted_builtins_view(self):
        assert _IndexHolder("builtins.len([1,2,3])").call == 3
        assert _IndexHolder("builtins.sum([1,2,3])").call == 6

    def test_lambda_expr(self):
        assert _IndexHolder("lambda x: x * 2").call(5) == 10

    def test_default_holder(self):
        assert _IndexHolder().call("abc") == "abc"

    def test_attr_chain_uses_getattr(self):
        # DSL 属性链编译为 getattr(x,'upper')——受限 __builtins__ 必须含 getattr
        assert _.upper("hello")() == "HELLO"
        assert (_ + 1)(2) == 3
        assert (_1 + _2)(1, 2) == 3


class TestEnvRestricted:
    """默认 env 必须自带受限 __builtins__（无自动注入真实 builtins）。"""

    def test_env_has_restricted_builtins(self):
        env = _IndexHolder("x").env
        assert '__builtins__' in env
        assert '__import__' not in env['__builtins__']
        assert 'open' not in env['__builtins__']
        assert 'eval' not in env['__builtins__']

    def test_builtins_key_no_import(self):
        env = _IndexHolder("x").env
        assert not hasattr(env['builtins'], '__import__')