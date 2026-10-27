# -*- coding: utf-8 -*-
"""回归测试：SpawnManager 的 register(name)/monitor/stop/stop_all 参数校验（BUG-349）。

修复前：

    mgr.register(None, fn)     # 静默接受，None 原样作为字典键
    mgr.register("", fn)       # 同上
    mgr.names()                # -> [None, '']    （非字符串名字泄漏到公共查询面）
    mgr.monitor(timeout="x")   # TypeError: unsupported operand type(s) for +: 'float' and 'str'
    mgr.stop_all(timeout="x")  # 静默返回 None（stop 内部 join 的 TypeError 被
                               #   `except Exception: pass` 吞掉 → 非法超时退化为直接 kill）

修复：register 要求 name 非空字符串；monitor/stop/stop_all 用既有的
_validate_positive_number 校验 timeout（None 仅 monitor 允许）。
"""

import pytest

from vools.vconcurrent.spawns import SpawnManager


def _noop():
    return None


class TestRegisterNameValidation:
    @pytest.mark.parametrize("bad", [None, 123, 1.5, ["a"]])
    def test_non_str_name(self, bad):
        mgr = SpawnManager()
        with pytest.raises(TypeError) as ei:
            mgr.register(bad, _noop)
        assert "name" in str(ei.value)

    @pytest.mark.parametrize("bad", ["", "   "])
    def test_blank_name(self, bad):
        mgr = SpawnManager()
        with pytest.raises(ValueError) as ei:
            mgr.register(bad, _noop)
        assert "name" in str(ei.value)

    def test_duplicate_name_still_rejected(self):
        mgr = SpawnManager()
        mgr.register("dup", _noop)
        with pytest.raises(ValueError):
            mgr.register("dup", _noop)


class TestTimeoutValidation:
    @pytest.mark.parametrize("bad", ["x", [1]])
    def test_monitor_type(self, bad):
        mgr = SpawnManager()
        with pytest.raises(TypeError) as ei:
            mgr.monitor(timeout=bad)
        assert "timeout" in str(ei.value)

    @pytest.mark.parametrize("bad", [0, -1])
    def test_monitor_non_positive(self, bad):
        mgr = SpawnManager()
        with pytest.raises(ValueError):
            mgr.monitor(timeout=bad)

    @pytest.mark.parametrize("bad", ["x", None, 0, -1])
    def test_stop_timeout(self, bad):
        mgr = SpawnManager()
        with pytest.raises((TypeError, ValueError)):
            mgr.stop("whatever", timeout=bad)

    @pytest.mark.parametrize("bad", ["x", None, 0, -1])
    def test_stop_all_timeout(self, bad):
        mgr = SpawnManager()
        with pytest.raises((TypeError, ValueError)):
            mgr.stop_all(timeout=bad)


class TestBehaviourUnchanged:
    def test_names_only_strings(self):
        mgr = SpawnManager()
        mgr.register("a", _noop)
        mgr.register("b", _noop)
        names = mgr.names()
        assert sorted(names) == ["a", "b"]
        assert all(isinstance(n, str) for n in names)

    def test_monitor_timeout_and_infinite(self):
        mgr = SpawnManager()
        mgr.register("a", _noop)
        assert mgr.monitor(timeout=0.1) is True
        assert mgr.monitor() is True

    def test_status_and_unregister(self):
        mgr = SpawnManager()
        mgr.register("a", _noop)
        status = mgr.status()
        assert "a" in status
        assert mgr.unregister("a") is not None
        assert mgr.names() == []

    def test_stop_all_default(self):
        mgr = SpawnManager()
        mgr.register("a", _noop)
        assert mgr.stop_all() is None
