"""
tests/test_serialize_regression.py
BUG-253 / BUG-254 回归锁 — serialize 往返/类型保真/bridge fallback。
"""
import enum
import asyncio
import pytest
from datetime import datetime, timezone, timedelta


# ─── BUG-253: __main__ / 脚本路径下 enum 往返 ───────────────────────────────

class _MainEnum_RS(enum.IntEnum):
    ALPHA = 1
    BETA = 2

class _MainEnum_SE(enum.Enum):
    X = "x_val"
    Y = "y_val"


def test_enum_fidelity_main_module_int():
    """BUG-253: __main__ 下 IntEnum JSON 往返保真"""
    from vools.serialize import Serializer
    s = Serializer(backend='json')
    obj = {'color': _MainEnum_RS.ALPHA, 'nested': [_MainEnum_RS.BETA]}
    data = s.dumps(obj)
    result = s.loads(data)
    assert isinstance(result['color'], _MainEnum_RS)
    assert result['color'] == _MainEnum_RS.ALPHA
    assert isinstance(result['nested'][0], _MainEnum_RS)
    assert result['nested'][0] == _MainEnum_RS.BETA


def test_enum_fidelity_main_module_str():
    """BUG-253: __main__ 下 Enum JSON 往返保真"""
    from vools.serialize import Serializer
    s = Serializer(backend='json')
    obj = {'x': _MainEnum_SE.X, 'y': _MainEnum_SE.Y}
    data = s.dumps(obj)
    result = s.loads(data)
    assert isinstance(result['x'], _MainEnum_SE)
    assert result['x'] == _MainEnum_SE.X
    assert result['y'] == _MainEnum_SE.Y


def test_enum_fidelity_stdlib_still_works():
    """BUG-253: 顶层 __main__ enum 往返保真（无 <locals> 标记）"""
    from vools.serialize import Serializer
    s = Serializer(backend='json')
    obj = {'c': _MainEnum_RS.ALPHA}
    data = s.dumps(obj)
    result = s.loads(data)
    assert isinstance(result['c'], _MainEnum_RS)
    assert result['c'] == _MainEnum_RS.ALPHA


def test_enum_fidelity_local_enum_degrades():
    """BUG-255: 函数内 enum（qualname 含 <locals>）退化返回值，不崩溃"""
    import enum
    from vools.serialize import Serializer
    def make_enum():
        class StdColor(enum.IntEnum):
            RED = 10
            GREEN = 20
        return StdColor
    StdColor = make_enum()
    s = Serializer(backend='json')
    obj = {'c': StdColor.RED, 'nested': StdColor.GREEN}
    data = s.dumps(obj)
    result = s.loads(data)
    # 函数内 enum 无法通过 getattr 链找到，退化返回值（安全降级，不崩溃）
    assert result['c'] == 10
    assert result['nested'] == 20


def test_enum_fidelity_rejects_dangerous_module():
    """BUG-253/BUG-100 联动: 危险模块（os/subprocess 等）的白名单校验仍然生效"""
    from vools.serialize.type_registry import _deserialize_enum
    # 伪造恶意 state，尝试导入 os 模块
    with pytest.raises(ValueError, match="Invalid enum module"):
        _deserialize_enum({
            'type': 'os.SomeEnum',
            'module': 'os',
            'qualname': 'SomeEnum',
            'name': 'X',
            'value': 1,
        })
    with pytest.raises(ValueError, match="Invalid enum module"):
        _deserialize_enum({
            'type': 'subprocess.SomeEnum',
            'module': 'subprocess',
            'qualname': 'SomeEnum',
            'name': 'X',
            'value': 1,
        })


# ─── BUG-254: async fallback 在已有 event loop 内 ──────────────────────────

def test_async_fallback_in_active_loop():
    """BUG-254: async fallback 在已有运行中的 event loop 内不崩溃"""
    from vools.decorators import bridge_decorator as bd

    async def async_fb(obj):
        return f"async:{obj}"

    class FakeReg:
        def is_available(self, lang): return False
        def load_symbol(self, lang, sym): return None

    orig = bd._get_registry
    bd._get_registry = lambda: FakeReg()
    try:
        @bd.bridge('fake', 'mod.func', fallback=async_fb)
        def f(obj): pass

        async def call():
            return f({'k': 1})

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(call())
            assert result == "async:{'k': 1}"
        finally:
            loop.close()
    finally:
        bd._get_registry = orig


def test_async_fallback_without_active_loop():
    """BUG-254: 无运行中 loop 时 async fallback 仍正常"""
    from vools.decorators.bridge_decorator import bridge

    async def async_fb(obj):
        return f"async:{obj}"

    # 不注册 fake registry，默认走 is_available=False → fallback
    @bridge('nonexistent_lang', 'mod.func', fallback=async_fb)
    def f(obj): pass

    result = f({'k': 1})
    assert result == "async:{'k': 1}"


def test_sync_fallback_still_works():
    """BUG-254: 修复不影响同步 fallback 正常路径"""
    from vools.decorators.bridge_decorator import bridge

    def sync_fb(obj):
        return f"sync:{obj}"

    @bridge('nonexistent_lang', 'mod.func', fallback=sync_fb)
    def f(obj): pass

    result = f({'k': 1})
    assert result == "sync:{'k': 1}"


def test_bridge_exception_triggers_async_fallback():
    """BUG-254: 路径3（桥抛异常）+ async fallback 在已有 loop 内不崩溃"""
    from vools.decorators import bridge_decorator as bd

    def bad_bridge(obj):
        raise ValueError("bridge crashed")

    async def async_fb(obj):
        return f"recovered:{obj}"

    class FakeReg:
        def is_available(self, lang): return True
        def load_symbol(self, lang, sym): return bad_bridge

    orig = bd._get_registry
    bd._get_registry = lambda: FakeReg()
    try:
        @bd.bridge('fake', 'mod.func', fallback=async_fb)
        def f(obj): pass

        async def call():
            return f({'k': 1})

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(call())
            assert result == "recovered:{'k': 1}"
        finally:
            loop.close()
    finally:
        bd._get_registry = orig
