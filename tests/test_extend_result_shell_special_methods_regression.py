# -*- coding: utf-8 -*-
"""回归测试：result_shell 套壳保留 staticmethod/classmethod（BUG-244）。

原 `_process_result_shells` 用 `getattr(new_cls, name)` 取方法后包装体再传
`self`：staticmethod 返回裸函数、classmethod 返回已绑定 cls 的方法，多传
一个位置参数 → 实例调用 `TypeError: takes 1 positional argument but 2 were
given`；默认（无 dir_filter）会把所有非 dunder 方法都套壳，带特殊方法的类
经 result_shell 后方法集体失效。

另：`shelled_method` 内 `dir_filter` 引用外层循环变量（晚期绑定），多组
result_shell 时先前套壳的方法会用最后一轮的 filter。

修复：`inspect.getattr_static` 取原始描述符，按 staticmethod/classmethod/
普通方法分别包装与调用，并以同名描述符写回；shell_func/dir_filter 用默认
参数固化。
"""

from vools.oop.extend import clone


_SHELL = (lambda result: result, lambda m: not m.startswith('__'))


def _make_base():
    @clone(None, result_shell=_SHELL)
    class Base:
        value = 10

        def normal(self):
            return "normal-ok"

        @staticmethod
        def stat(x):
            return x * 2

        @classmethod
        def clsm(cls):
            return cls.__name__

    return Base


class TestStaticMethodPreserved:
    """BUG-244 核心：staticmethod 经套壳后仍可正常调用。"""

    def test_instance_call(self):
        B = _make_base()
        assert B().stat(5) == 10

    def test_class_call(self):
        B = _make_base()
        assert B.stat(5) == 10

    def test_result_shell_applied(self):
        # shell 生效：给 staticmethod 返回值加壳
        @clone(None, result_shell=(lambda r: f"[{r}]", lambda m: True))
        class S:
            @staticmethod
            def foo():
                return "x"
        assert S().foo() == "[x]"


class TestClassMethodPreserved:
    """classmethod 经套壳后 cls 绑定正确。"""

    def test_instance_call_returns_cls_name(self):
        B = _make_base()
        assert B().clsm() == B.__name__

    def test_class_call(self):
        B = _make_base()
        assert B.clsm() == B.__name__

    def test_result_shell_applied(self):
        @clone(None, result_shell=(lambda r: f"[{r}]", lambda m: True))
        class C:
            @classmethod
            def name(cls):
                return cls.__name__
        assert C().name() == f"[{C.__name__}]"


class TestInstanceMethodUnchanged:
    """普通方法与 "=>" 表达式 shell 保持（防修复过度）。"""

    def test_normal_method(self):
        B = _make_base()
        assert B().normal() == "normal-ok"

    def test_arrow_expression_shell(self):
        @clone(None, result_shell=(
            lambda result: "=> self" if result is None else result, None))
        class WithNone:
            def set(self, v):
                self.v = v
                return None
        w = WithNone()
        assert w.set(1) is w


class TestMultiGroupDirFilter:
    """多组 result_shell 各自 dir_filter 不串（晚期绑定修复）。"""

    def test_groups_are_isolated(self):
        @clone(None,
               result_shell=(lambda r: f"[s1]{r}", ('a',)),
               result_shell1=(lambda r: f"[s2]{r}", ('b',)))
        class Multi:
            def a(self):
                return "A"

            def b(self):
                return "B"

        m = Multi()
        assert m.a() == "[s1]A"
        assert m.b() == "[s2]B"