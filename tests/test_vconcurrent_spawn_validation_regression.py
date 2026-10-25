# -*- coding: utf-8 -*-
"""回归测试：spawn 的 daemon 校验 + spawn_many 的 args_list 校验（BUG-490）。

修复前：

    spawn(worker, daemon='yes')   # 静默接受（'yes' 仅被当真值）
    spawn(worker, daemon=1)       # 同样接受
    spawn_many(worker, 123)       # 裸 "'int' object is not iterable"（看不出参数名）
    spawn_many(worker, "abc")     # 字符串被逐字符当 args_list

修复后：`daemon` 必须是 bool；`spawn_many` 的 `args_list` 必须是 list/tuple。

注意：Windows 下 multiprocessing 用 spawn 模式，被测目标必须是**模块级函数**
（lambda/闭包不可 pickle）。
"""

import sys
import time

import pytest

from vools.vconcurrent.spawns import spawn, spawn_many


def worker():
    time.sleep(0.02)


class TestDaemonValidation:
    @pytest.mark.parametrize("bad", ["yes", 1, 0, None, 1.5])
    def test_non_bool_daemon(self, bad):
        with pytest.raises(TypeError) as ei:
            spawn(worker, daemon=bad, autostart=False)
        assert "daemon" in str(ei.value)

    @pytest.mark.parametrize("ok", [True, False])
    def test_bool_daemon_accepted(self, ok):
        h = spawn(worker, daemon=ok, autostart=False)
        assert h.is_started is False


class TestSpawnManyValidation:
    @pytest.mark.parametrize("bad", [123, "abc", None, {}])
    def test_bad_args_list(self, bad):
        with pytest.raises(TypeError) as ei:
            spawn_many(worker, bad)
        assert "args_list" in str(ei.value)

    def test_kwargs_length_mismatch(self):
        with pytest.raises(ValueError):
            spawn_many(worker, [[], []], [{}])


class TestSpawnBehaviourUnchanged:
    def test_spawn_and_join(self):
        h = spawn(worker)
        assert h.is_started is True
        assert isinstance(h.pid, int)
        h.join(5.0)
        assert h.is_alive() is False
        assert h.exitcode == 0

    def test_spawn_many(self):
        handles = spawn_many(worker, [[], [], []])
        assert len(handles) == 3
        for h in handles:
            h.join(5.0)
            assert h.exitcode == 0

    def test_spawn_many_empty(self):
        assert spawn_many(worker, []) == []

    def test_autostart_false(self):
        h = spawn(worker, autostart=False)
        assert h.is_started is False
        h.start()
        assert h.is_started is True
        h.join(5.0)


class TestExistingValidationsIntact:
    def test_func_must_be_callable(self):
        with pytest.raises(TypeError):
            spawn(123)

    def test_args_string_rejected(self):
        with pytest.raises(TypeError) as ei:
            spawn(worker, args="abc")
        assert "args" in str(ei.value)

    def test_kwargs_must_be_mapping(self):
        with pytest.raises(TypeError):
            spawn(worker, kwargs=[1])

    def test_name_type(self):
        with pytest.raises(TypeError):
            spawn(worker, name=123)
