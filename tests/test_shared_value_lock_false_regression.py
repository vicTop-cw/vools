# -*- coding: utf-8 -*-
"""回归测试：SharedValue 支持 lock=False（BUG-238）。

`lock` 是 `multiprocessing.Value` 的标准选项（False = 不加内部锁、由调用方
自行同步）。但 `multiprocessing.Value(lock=False)` 返回**裸 ctypes 对象**
（无 `get_lock`），原 `get()/set()` 无条件 `with self._value.get_lock()`
→ `lock=False` 时必抛 `AttributeError: 'c_long' object has no attribute
'get_lock'`（参数一用即废）。

修复：按底层形态分支——有 `get_lock` 才加锁，否则直接读写 `.value`
（无锁语义与 multiprocessing.Value(lock=False) 本义一致）。
"""

import pytest

from vools.vconcurrent.multiprocessing_mod import SharedValue


class TestLockTrue:
    """默认 lock=True 路径保持（防修复过度）。"""

    def test_set_get_int(self):
        sv = SharedValue('i', 0)
        sv.set(42)
        assert sv.get() == 42

    def test_negative(self):
        sv = SharedValue('i', 0)
        sv.set(-5)
        assert sv.get() == -5

    def test_initial_default(self):
        assert SharedValue('i', 7).get() == 7


class TestLockFalse:
    """BUG-238 核心：lock=False 时 get/set 仍可用。"""

    def test_set_get_int(self):
        sv = SharedValue('i', 0, lock=False)
        sv.set(7)
        assert sv.get() == 7

    def test_set_get_double(self):
        sv = SharedValue('d', 0.0, lock=False)
        sv.set(3.14)
        assert sv.get() == 3.14

    def test_no_get_lock_on_raw(self):
        # 底层确为裸 ctypes（无 get_lock）——证明测试覆盖的是真实分支
        sv = SharedValue('i', 0, lock=False)
        assert not hasattr(sv.raw, 'get_lock')

    def test_raw_value_interop(self):
        # 无锁形态下 raw.value 直读写与包装 API 互通
        sv = SharedValue('i', 0, lock=False)
        sv.raw.value = 9
        assert sv.get() == 9
        sv.set(11)
        assert sv.raw.value == 11


class TestContextManager:
    """上下文管理器两种形态均可用。"""

    @pytest.mark.parametrize("lock", [True, False])
    def test_with_block(self, lock):
        with SharedValue('i', 0, lock=lock) as sv:
            sv.set(3)
            assert sv.get() == 3