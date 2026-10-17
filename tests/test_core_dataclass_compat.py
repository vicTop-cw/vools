# -*- coding: utf-8 -*-
"""测试 vools.core.dataclass_compat（3.13 走标准库分支）。"""

from dataclasses import FrozenInstanceError as _StdFIE
from vools.core.dataclass_compat import (
    dataclass, field, asdict, is_dataclass, MISSING,
    FrozenInstanceError, _HAS_DATACLASSES
)

__all__ = ["TestDataclass", "TestField", "TestAsdict", "TestIsDataclass",
           "TestMISSING", "TestFrozen", "TestFlag", "TestImport"]


@dataclass
class Point:
    x: int
    y: int


@dataclass(frozen=True)
class Frozen:
    a: int


class TestDataclass:
    """dataclass 装饰器测试。"""

    def test_basic(self):
        p = Point(1, 2)
        assert p.x == 1
        assert p.y == 2

    def test_bare_decorator(self):
        @dataclass
        class P2:
            x: int
        assert P2(3).x == 3

    def test_no_parens_callable(self):
        # dataclass(Point) 无参数用法
        @dataclass()
        class P3:
            x: int
        assert P3(5).x == 5

    def test_frozen(self):
        f = Frozen(1)
        assert f.a == 1
        with __import__("pytest").raises(_StdFIE):
            f.a = 2


class TestField:
    """field 测试。"""

    def test_field_default(self):
        @dataclass
        class F1:
            x: int = field(default=10)
        assert F1().x == 10

    def test_field_factory(self):
        @dataclass
        class F2:
            x: list = field(default_factory=list)
        assert F2().x == []


class TestAsdict:
    """asdict 测试。"""

    def test_basic(self):
        d = asdict(Point(1, 2))
        assert d == {"x": 1, "y": 2}


class TestIsDataclass:
    """is_dataclass 测试。"""

    def test_true(self):
        assert is_dataclass(Point(1, 2)) is True
        assert is_dataclass(Point) is True

    def test_false(self):
        assert is_dataclass(42) is False


class TestMISSING:
    """MISSING 测试。"""

    def test_identity(self):
        from dataclasses import MISSING as std_missing
        assert MISSING is std_missing


class TestFrozen:
    """FrozenInstanceError 测试。"""

    def test_basic(self):
        assert FrozenInstanceError is _StdFIE


class TestFlag:
    """版本标志测试。"""

    def test_flag(self):
        assert _HAS_DATACLASSES is True


class TestImport:
    """__all__ 测试。"""

    def test_all(self):
        from vools.core.dataclass_compat import __all__
        for n in ["dataclass", "field", "asdict", "is_dataclass", "MISSING",
                  "FrozenInstanceError"]:
            assert n in __all__
