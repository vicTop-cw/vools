# -*- coding: utf-8 -*-
"""回归测试：overload.register 的 export_mode 契约（BUG-245 修正版）。

契约由 tests/oop/test_overload_new.py 锁定，并在本文件同口径复验：
- `export_mode=None`（默认）→ **返回原函数、不改变原函数**；
- `ExportAsFunction` 是 None 的具名别名，行为同默认；
- `ParentMode` / `ExportAsManager` → 返回 OverloadManager（管理器）；
- 因此注册应使用**异名**（模块头示例 `add_int` 风格）；同名注册会把名字
  重绑成新函数、管理器丢失（BUG-245 已在 register docstring 注明该陷阱）。

历史：BUG-227/228 曾把默认返回值改成管理器，导致
`tests/oop/test_overload_new.py::TestExportModes::test_export_none_original_function`
失败；BUG-245 回滚该行为并把模块头/overload() 的误导性表述改为与本契约一致。
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


class TestDefaultReturnsOriginalFunction:
    """默认 export_mode=None：返回原函数（测试锁定契约）。"""

    def test_default_returns_function(self):
        @overload
        def f(x):
            return "base"

        def impl(x):
            return "impl"

        assert f.register(impl) is impl          # 不是管理器

    def test_export_as_function_alias(self):
        # ExportAsFunction 就是 None 的别名（同一哨兵）
        assert ExportAsFunction is None

        @overload
        def f(x):
            return "base"

        def impl(x):
            return "impl"

        assert f.register(impl, export_mode=ExportAsFunction) is impl

    def test_different_name_registration_dispatches(self):
        # 模块头示例风格：异名注册 + 含 Ambiguous 模式（默认模式无
        # Ambiguous，主函数与重载同匹配会按文档抛"模糊调用"）
        from vools.decorators.overload import (
            AllowSyncName, Ambiguous, Priority, Strict)

        @overload(mode=Priority | AllowSyncName | Strict | Ambiguous)
        def add(a, b):
            return a + b

        @add.register
        def add_int(a: int, b: int):
            return a + b

        assert isinstance(add, OverloadManager)
        assert add(1, 2) == 3
        assert add("a", "b") == "ab"


class TestManagerModes:
    """ParentMode / ExportAsManager：返回管理器。"""

    def test_parent_mode(self):
        @overload
        def f(x):
            return "base"

        m = f.register(lambda x: "impl", export_mode=ParentMode)
        assert isinstance(m, OverloadManager)

    def test_export_as_manager(self):
        @overload
        def f(x):
            return "base"

        m = f.register(lambda x: "impl", export_mode=ExportAsManager)
        assert isinstance(m, OverloadManager)

    def test_sentinels_distinct(self):
        assert ParentMode != ExportAsManager
        assert ExportAsFunction is None


class TestSameNameTrapDocumented:
    """同名注册的已知陷阱（行为断言，防文档漂移）。"""

    def test_same_name_rebinds_to_function(self):
        @overload
        def g():
            return "noarg"

        @g.register
        def g(a):
            return f"one:{a}"

        # 默认返回原函数 → 名字 g 已重绑为刚注册的函数（管理器丢失）
        assert not isinstance(g, OverloadManager)
        assert g(7) == "one:7"

    def test_register_docstring_mentions_trap(self):
        doc = OverloadManager.register.__doc__ or ""
        assert "同名注册" in doc
        assert "异名" in doc