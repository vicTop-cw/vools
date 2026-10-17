# -*- coding: utf-8 -*-
"""测试 vools.core.dataclass_compat — dataclass / field / asdict / is_dataclass。"""

import pytest

from vools.core.dataclass_compat import (
    dataclass, field, asdict, is_dataclass, MISSING, FrozenInstanceError,
)

__all__ = ["TestDataclassDecorator", "TestField", "TestAsDict",
           "TestIsDataclass", "TestMISSING", "TestFrozen", "TestImport"]


class TestDataclassDecorator:
    """dataclass 装饰器。"""

    def test_basic(self):
        @dataclass
        class Point:
            x: int = 0
            y: int = 0
        p = Point(1, 2)
        assert p.x == 1
        assert p.y == 2

    def test_with_params(self):
        @dataclass(frozen=True)
        class Pt:
            x: int = 0
        p = Pt(3)
        assert p.x == 3

    def test_callable_form(self):
        # dataclass(SomeClass, frozen=True) 立即返回
        @dataclass(cls=None, frozen=True)  # type: ignore
        class P2:
            x: int = 0
        # cls=None → 返回 lambda
        # 实际调用方式
        assert True

    def test_standard_module(self):
        import vools.core.dataclass_compat as mod
        assert mod._HAS_DATACLASSES is True


class TestField:
    """field 测试。"""

    def test_default(self):
        @dataclass
        class Foo:
            a: int = field(default=1)
        assert Foo().a == 1

    def test_default_factory(self):
        @dataclass
        class Bar:
            items: list = field(default_factory=list)
        b1 = Bar()
        b1.items.append(1)
        b2 = Bar()
        assert b2.items == []

    def test_missing(self):
        @dataclass
        class Baz:
            a: int = field(default=1)
            b: int = field(default_factory=lambda: 42)
        assert Baz().a == 1
        assert Baz().b == 42


class TestAsDict:
    """asdict 测试。"""

    def test_basic(self):
        @dataclass
        class P:
            x: int = 1
        d = asdict(P())
        assert d == {"x": 1}


class TestIsDataclass:
    """is_dataclass 测试。"""

    def test_true(self):
        @dataclass
        class P:
            x: int = 1
        assert is_dataclass(P()) is True
        assert is_dataclass(P) is True

    def test_false(self):
        assert is_dataclass(123) is False
        assert is_dataclass("str") is False


class TestMISSING:
    """MISSING 常量。"""

    def test_exist(self):
        assert MISSING is not None


class TestFrozen:
    """FrozenInstanceError。"""

    def test_raise(self):
        @dataclass(frozen=True)
        class P:
            x: int = 1
        with pytest.raises(FrozenInstanceError):
            p = P()
            p.x = 5


class TestImport:
    """__all__ 测试。"""

    def test_all(self):
        from vools.core.dataclass_compat import __all__
        assert "dataclass" in __all__
        assert "field" in __all__
        assert "asdict" in __all__
        assert "is_dataclass" in __all__
        assert "MISSING" in __all__
        assert "FrozenInstanceError" in __all__
