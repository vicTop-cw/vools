# -*- coding: utf-8 -*-
"""回归测试：占位符 DSL 的 dunder 守卫不可被"拼接 + getattr"绕过（BUG-363）。

BUG-208 给 `vools.functional.placeholder` 加了 AST 级 dunder 检查
（属性名/裸名/字符串常量中的 `__\w+`）。但受限 builtins 里**保留了 getattr**
（DSL 属性链需要），于是运行时拼接字符串即可拼出 dunder 名字绕过检查：

    _IndexHolder(
      "lambda x,*_,**__: getattr(getattr(getattr(x, '_'+'_class_'+'_'), "
      "'_'+'_base_'+'_'), '_'+'_subclasses_'+'_')()"
    ).call(1)
    # -> [<class 'type'>, <class 'async_generator'>, ...]  （全部已加载类）

即完整 RCE 链（与 BUG-288/361/362 同族）。修复：
- `getattr`/`setattr`/`delattr`/`hasattr` 的属性名必须是**字符串字面量**
  （字面量中的 dunder 已被既有检查拦下）；
- `operator.attrgetter` / `methodcaller` / `itemgetter` 等动态取属性工具整体禁止。

正常 DSL（属性方法链、math、字面量 getattr）不受影响。
"""

import pytest

from vools.functional.placeholder import _IndexHolder, _, _1, _2


def _call(expr, *args):
    return _IndexHolder(expr).call(*args)


class TestNormalDslUnchanged:
    def test_identity(self):
        assert _call('lambda x,*_,**__: x', 5) == 5

    def test_arithmetic(self):
        assert _call('lambda x,*_,**__: x + 1', 5) == 6

    def test_method_chain(self):
        assert _call('lambda x,*_,**__: x.upper()', 'ab') == 'AB'

    def test_math_module(self):
        assert _call('lambda x,*_,**__: math.sqrt(x)', 16) == 4.0

    def test_literal_getattr(self):
        assert _call("lambda x,*_,**__: getattr(x, 'upper')()", 'ab') == 'AB'


class TestDslAttributeChainsStillWork:
    """DSL 编译产物是 getattr(x0, <env 随机名>)，必须继续可用（BUG-208 契约）。"""

    def test_placeholder_attribute_chain(self):
        assert _.upper('hello')() == 'HELLO'

    def test_placeholder_arithmetic(self):
        assert (_ + 1)(2) == 3

    def test_indexed_placeholders(self):
        assert (_1 + _2)(1, 2) == 3


class TestBypassBlocked:
    @pytest.mark.parametrize('expr', [
        # 拼接出 '__class__'
        "lambda x,*_,**__: getattr(x, '_'+'_class_'+'_')",
        # 双层拼接
        "lambda x,*_,**__: getattr(getattr(x, '_'+'_class_'+'_'), '_'+'_base_'+'_')",
        # 完整逃逸：拼出 __subclasses__ 并调用
        ("lambda x,*_,**__: getattr(getattr(getattr(x, '_'+'_class_'+'_'), "
         "'_'+'_base_'+'_'), '_'+'_subclasses_'+'_')()"),
        # f-string 动态拼名
        "lambda x,*_,**__: getattr(x, f'__{1}__')",
        # 直接 dunder（既有检查）
        'lambda x,*_,**__: x.__class__',
        'lambda x,*_,**__: x.__class__.__subclasses__()',
    ])
    def test_dynamic_attr_names_rejected(self, expr):
        # 守卫在 .call 求值前触发
        with pytest.raises(NameError):
            _IndexHolder(expr).call(1)

    def test_attrgetter_rejected(self):
        with pytest.raises(NameError):
            _IndexHolder(
                "lambda x,*_,**__: operator.attrgetter('_'*2+'class'+'_'*2)(x)").call(1)

    def test_methodcaller_rejected(self):
        with pytest.raises(NameError):
            _IndexHolder("lambda x,*_,**__: operator.methodcaller('__init__')(x)").call(1)