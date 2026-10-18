"""
BUG-107b: 非 Priority 模式下 AllowSyncName 无法注册不同名函数。
原实现：_validate_mode 强制 AllowSyncName 必须配合 Priority；
       _register_function 非 Priority 分支硬检查同名。
修复：AllowSyncName 可与任意模式组合，_register_function 支持。

BUG-107（文档）：overload 模块头文档示例使用默认模式却展示
"add(1,2) # 3" / "add('a','b') # 'ab'"——主函数无类型注解时与
有注解重载同时匹配，默认模式不含 Ambiguous 会抛"模糊调用"。
已修正文档示例，明确说明需显式开启 Ambiguous。
"""
import pytest
from vools.decorators.overload import (
    overload, reset_registry, Strict, Ambiguous, AllowSyncName, Priority,
    ParentMode,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_registry()


def test_allow_sync_name_with_strict_no_priority():
    """BUG-107b: Strict|Ambiguous|AllowSyncName（不含 Priority）可注册不同名函数"""
    @overload(mode=Strict | Ambiguous | AllowSyncName)
    def typed(x: object):
        return f"object:{type(x).__name__}"

    @typed.register
    def typed_str(x: str):
        return f"str:{x}"

    @typed.register
    def typed_int(x: int):
        return f"int:{x}"

    # Ambiguous 取第一个匹配（主函数先注册，object 注解兜底）
    assert typed(10) == "object:int"
    assert typed("hi") == "object:str"
    # float 只匹配 object
    assert typed(1.5) == "object:float"


def test_allow_sync_name_only():
    """BUG-107b: 仅 AllowSyncName（不带 Priority）也合法"""
    @overload(mode=AllowSyncName | Strict | Ambiguous)
    def calc(x):
        return "untyped"

    @calc.register
    def calc_str(x: str):
        return f"str:{x}"

    # 主函数先注册，Ambiguous 取第一个
    assert calc("hi") == "untyped"
    assert calc(42) == "untyped"


def test_validate_mode_no_longer_blocks():
    """BUG-107b: _validate_mode 不再拒绝 AllowSyncName 不带 Priority 的组合"""
    @overload(mode=AllowSyncName | Strict)
    def fn(x):
        return x

    @fn.register
    def fn_int(x: int):
        return x

    # 无 Ambiguous：主函数无注解 + 有注解重载同时匹配 → 抛"模糊调用"
    with pytest.raises(TypeError):
        fn(1)


def test_default_mode_still_raises_ambiguous():
    """默认模式（Priority|Strict|AllowSyncName 不含 Ambiguous）仍抛模糊调用"""
    @overload
    def add(a, b):
        return "untyped"

    @add.register(export_mode=ParentMode)
    def add_int(a: int, b: int):
        return a + b

    with pytest.raises(TypeError, match="模糊调用"):
        add(1, 2)