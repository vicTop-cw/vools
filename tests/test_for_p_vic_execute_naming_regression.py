# -*- coding: utf-8 -*-
"""回归测试：for_p 别名语义 + vic_execute 包装器命名（BUG-441/442）。

**BUG-442**：``for_p = for_(print)`` 得到的是 vic_execute 的 map 包装器——
只接受单个 iterable、返回结果列表，与"直接打印结果"的文档承诺不符；
``for_p(1, 2)`` 抛 ``print() takes 1 positional argument but 2 were given``
（因为 @wraps 把包装器改名成了 print）。现 ``for_p = print``。

**BUG-441**：``@wraps(func)`` 把 builtins 的名字复制到包装器上，参数错误被
归因到 print；对 builtins 改用中性名称 ``vic_execute_wrapper``（Python 函数仍
保留原名）。
"""

import builtins

import pytest

from vools.decorators.trd import vic_execute
from vools.functional.funcs import for_p


class TestForPAlias:
    def test_is_builtin_print(self):
        assert for_p is builtins.print

    def test_multiple_args(self, capsys):
        for_p(1, 2)
        assert capsys.readouterr().out.strip() == "1 2"

    def test_kwargs(self, capsys):
        for_p(1, 2, sep="-")
        assert capsys.readouterr().out.strip() == "1-2"

    def test_returns_none(self):
        assert for_p("x") is None


class TestVicExecuteNaming:
    def test_builtin_error_not_attributed_to_print(self):
        """BUG-441：参数错误应指向包装器，而不是 print。"""
        wrapped = vic_execute()(print)
        with pytest.raises(TypeError) as ei:
            wrapped(1, 2)
        assert "print()" not in str(ei.value)
        assert "vic_execute_wrapper" in str(ei.value)

    def test_kwargs_error(self):
        wrapped = vic_execute()(print)
        with pytest.raises(TypeError) as ei:
            wrapped(1, 2, sep="-")
        assert "vic_execute_wrapper" in str(ei.value)

    def test_python_function_keeps_name(self):
        @vic_execute(max_workers=1)
        def double(x):
            return x * 2

        assert double.__name__ == "double"
        assert double([1, 2]) == [2, 4]

    def test_string_treated_as_single_value(self):
        """BUG-359 语义保持：字符串不逐字符展开。"""

        @vic_execute(max_workers=1)
        def up(s):
            return s.upper()

        assert up("abc") == ["ABC"]

    def test_map_semantics(self):
        @vic_execute(max_workers=2)
        def double(x):
            return x * 2

        assert double([1, 2, 3]) == [2, 4, 6]
