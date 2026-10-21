# -*- coding: utf-8 -*-
"""回归测试：overload.register 默认返回管理器 + 三哨兵互异（BUG-227/228）。

BUG-227：`register` 默认分支返回原函数 f——同名注册 `@f.register def f(...)`
（_register_function 显式允许的正统写法）把名字 f 重绑成新函数、Manager 丢失，
此后 dispatching 全部旁路（实测 g() 报 "missing 1 required positional
argument: 'a'" 而非重载系统错误）；且与模块头 L9、示例注释 L17、overload()
L500 三处「默认返回管理器支持链式」承诺直接矛盾。

BUG-228：`ExportAsFunction` 误定义成 None——与「未传 export_mode」同值，被
register 的 `export_mode is not None` 门截胡，「显式选择返回原函数」结构性
不可达（L331 分支永假）。同族哨兵 ParentMode='parent'/ExportAsManager=
'manager' 均为唯一字符串，现对齐为 'function'。
"""

import pytest

from vools.decorators.overload import (
    ExportAsFunction,
    ExportAsManager,
    OverloadManager,
    ParentMode,
    overload,
    reset_registry,
)


@pytest.fixture(autouse=True)
def _fresh_registry():
    reset_registry()
    yield
    reset_registry()


class TestDefaultReturnsManager:
    """BUG-227 核心：默认返回管理器，同名注册不打断 dispatch。"""

    def test_default_returns_manager(self):
        @overload
        def f(x):
            return "base"

        assert isinstance(f.register(lambda x: "impl"), OverloadManager)

    def test_same_name_registration_dispatches(self):
        @overload
        def g():
            return "noarg"

        @g.register
        def g(a):
            return f"one:{a}"

        assert type(g).__name__ == "OverloadManager"
        assert g() == "noarg"        # 修复前：TypeError missing 'a'（直调 g(a)）
        assert g(7) == "one:7"

    def test_same_name_method_dispatches(self):
        class K:
            @overload
            def m(self):
                return "noarg"

            @m.register
            def m(self, a):
                return f"one:{a}"

        k = K()
        assert k.m() == "noarg"
        assert k.m(7) == "one:7"

    def test_module_header_example_verbatim(self):
        from vools.decorators.overload import (
            AllowSyncName, Ambiguous, Priority, Strict)

        reset_registry()

        @overload(mode=Priority | AllowSyncName | Strict | Ambiguous)
        def add(a, b):
            return a + b

        @add.register
        def add_int(a: int, b: int):
            return a + b

        assert add(1, 2) == 3
        assert add("a", "b") == "ab"


class TestSentinelExportAsFunction:
    """BUG-228 核心：显式 ExportAsFunction 真的返回原函数。"""

    def test_sentinels_distinct(self):
        assert len({ExportAsFunction, ParentMode, ExportAsManager}) == 3

    def test_explicit_export_as_function(self):
        @overload
        def f(x):
            return "base"

        plain = lambda x: "plain"  # noqa: E731
        assert f.register(plain, export_mode=ExportAsFunction) is plain

    def test_decorator_level_export_mode(self):
        @overload(export_mode=ExportAsFunction)
        def g(x):
            return "base"

        gimpl = lambda x: "g-impl"  # noqa: E731
        assert g.register(gimpl) is gimpl

    def test_parent_mode_still_manager(self):
        @overload
        def f(x):
            return "base"

        assert isinstance(
            f.register(lambda x: "pm", export_mode=ParentMode), OverloadManager)

    def test_export_as_manager_still_manager(self):
        @overload
        def f(x):
            return "base"

        assert isinstance(
            f.register(lambda x: "em", export_mode=ExportAsManager),
            OverloadManager)