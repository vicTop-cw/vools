"""
测试新的 overload 模块（OverloadMode 模式标志系统）

覆盖：
1. 默认模式 @overload（无参数）
2. Priority + AllowSyncName + Strict + Ambiguous
3. export_mode=None（默认不修改原函数）
4. export_mode=ParentMode（返回管理器）
5. 非同名函数注册（AllowSyncName）
6. 严格类型匹配 vs 数量匹配
7. Ambiguous 模糊匹配
8. 无 Ambiguous 时的模糊报错
9. 类方法绑定
10. 链式注册
"""

import pytest
from vools.decorators.overload import (
    overload, OverloadManager, OverloadMode,
    Priority, AllowSyncName, Strict, Ambiguous,
    ParentMode, reset_registry,
)


def setup_function():
    reset_registry()


class TestOverloadDefault:
    """测试默认模式 @overload"""

    def test_basic_overload(self):
        @overload
        def process():
            return "无参数"

        @process.register(export_mode=ParentMode)
        def process_one(x):
            return f"一个参数: {x}"

        @process.register(export_mode=ParentMode)
        def process_two(x, y):
            return f"两个参数: {x}, {y}"

        assert process() == "无参数"
        assert process(10) == "一个参数: 10"
        assert process(20, 30) == "两个参数: 20, 30"

    def test_class_method(self):
        class TestCls:
            def __init__(self, a, b):
                self.a = a
                self.b = b

            @overload
            def process(self):
                return f"一个参数: {self.a}, {self.b}"

            @process.register(export_mode=ParentMode)
            def process_one(self, x):
                return f"两个参数: {self.a}, {self.b}, {x}"

            @process.register(export_mode=ParentMode)
            def process_two(self, x, y):
                return f"三个参数: {self.a}, {self.b}, {x}, {y}"

        obj = TestCls(1, 2)
        assert obj.process() == "一个参数: 1, 2"
        assert obj.process(3) == "两个参数: 1, 2, 3"
        assert obj.process(4, 5) == "三个参数: 1, 2, 4, 5"


class TestOverloadModeFlags:
    """测试各种模式组合"""

    def test_strict_mode(self):
        @overload(mode=Strict | Ambiguous)
        def process(a: int, b: int):
            return a + b

        @process.register(export_mode=ParentMode)
        def process(a: str, b: str):  # 同名函数
            return a + b

        assert process(1, 2) == 3
        assert process("a", "b") == "ab"

        with pytest.raises(TypeError):
            process(1, "b")

    def test_priority_mode(self):
        @overload(mode=Priority | AllowSyncName | Strict | Ambiguous)
        def process():
            return "主函数"

        @process.register(priority=1, export_mode=ParentMode)
        def process_one(arg):
            return f"优先级1: {arg}"

        @process.register(priority=10, export_mode=ParentMode)
        def process_high(arg):
            return f"高优先级: {arg}"

        assert process("hello") == "高优先级: hello"

    def test_non_same_name_registration(self):
        @overload(mode=Priority | AllowSyncName | Strict | Ambiguous)
        def add(a, b):
            return a + b

        @add.register(export_mode=ParentMode)
        def add_int(a: int, b: int):
            return a + b

        @add.register(export_mode=ParentMode)
        def add_str(a: str, b: str):
            return a + b

        assert add(1, 2) == 3         # matches add_int
        assert add("x", "y") == "xy"  # matches add_str

    def test_ambiguous_allowed(self):
        @overload(mode=Priority | AllowSyncName | Strict | Ambiguous)
        def add(a, b):
            return a + b

        @add.register(export_mode=ParentMode)
        def add_int(a: int, b: int):
            return a + b

        # int + int matches both add and add_int,
        # Ambiguous allows picking the first
        assert add(1, 2) == 3

    def test_ambiguous_error(self):
        @overload(mode=Priority | AllowSyncName | Strict)
        def add(a, b):
            return a + b

        @add.register(export_mode=ParentMode)
        def add_int(a: int, b: int):
            return a + b

        # int + int matches both add and add_int,
        # no Ambiguous flag -> should raise TypeError
        with pytest.raises(TypeError, match="模糊调用"):
            add(1, 2)


class TestExportModes:
    """测试 export_mode 行为"""

    def test_export_none_original_function(self):
        """export_mode=None -> 不修改原函数"""
        @overload(mode=Priority | AllowSyncName | Strict | Ambiguous)
        def add(a, b):
            return a + b

        @add.register  # export_mode=None 是默认
        def add_int(a: int, b: int):
            return a + b

        # add_int 是原函数，不是 OverloadManager
        assert not hasattr(add_int, 'is_overload_manager')
        assert add_int(1, 2) == 3  # 直接调用原函数

    def test_export_parent_mode(self):
        """export_mode=ParentMode -> 返回管理器"""
        @overload(mode=Priority | AllowSyncName | Strict | Ambiguous)
        def add(a, b):
            return a + b

        @add.register(export_mode=ParentMode)
        def add_int(a: int, b: int):
            return a + b

        assert add_int.is_overload_manager()
        assert add_int(1, 2) == 3  # 走重载匹配

    def test_chain_register(self):
        """链式注册"""
        @overload(mode=Priority | AllowSyncName | Strict | Ambiguous)
        def add(a, b):
            return a + b

        @add.register(export_mode=ParentMode)
        def add_int(a: int, b: int):
            return a + b

        @add_int.register(export_mode=ParentMode)
        def add_str(a: str, b: str):
            return a + b

        assert add.is_overload_manager()
        assert add_int.is_overload_manager()
        assert add_str.is_overload_manager()
        assert add(1, 2) == 3
        assert add("x", "y") == "xy"


class TestStrictDecorator:
    """测试 strict 装饰器"""

    def test_strict_decorator(self):
        from vools.decorators.overload import strict

        @strict
        def multiply(a: int, b: int) -> int:
            return a * b

        assert multiply(3, 4) == 12

        with pytest.raises(TypeError):
            multiply(3, "4")


class TestRegistryIsolation:
    """测试注册表隔离"""

    def test_reset_registry(self):
        reset_registry()
        from vools.decorators.overload import _registry
        assert len(_registry) == 0

    def test_multiple_overloads_independent(self):
        reset_registry()

        @overload
        def fn1(a):
            return f"fn1: {a}"

        @overload
        def fn2(a, b):
            return f"fn2: {a}, {b}"

        assert fn1(1) == "fn1: 1"
        assert fn2(1, 2) == "fn2: 1, 2"
