# -*- coding: utf-8 -*-
"""回归测试：spawn / watchdog / restart_on_exit 参数校验（BUG-407）。

`vconcurrent.spawns` 的三个入口原先都零校验，非法参数要到**子进程或后台
线程**里才炸，父进程拿到正常句柄却永远等不到结果：

    spawn('not-callable')            # 子进程: TypeError: 'str' object is not callable
    spawn(worker, 'abc')             # str 被逐字符展开 → 子进程参数个数错误
    spawn(worker, (1,), name=123)    # 子进程: AssertionError: name must be a string
    watchdog(object(), timeout=1)    # 看门狗线程: AttributeError ...
    watchdog(h, timeout=-1)          # 接受；interval 计算得到负值语义不明
    restart_on_exit(max_restarts=-1) # 接受（负次数）
    restart_on_exit(delay=-1)        # 接受（负延迟）

修复：func/target 必须可调用；args 必须是非 str 序列（否则会被逐字符展开）；
kwargs 映射或 None；name 字符串或 None；watchdog 的 handle 必须是 SpawnHandle、
timeout > 0、max_restarts 非负整数、on_dead 可调用或 None；restart_on_exit 的
max_restarts 非负整数、delay >= 0、backoff > 0。正常派生/监控/重启控制器
行为不变。
"""

import time

import pytest

from vools.vconcurrent.spawns import (
    SpawnHandle,
    restart_on_exit,
    spawn,
    watchdog,
)


def _worker(x):
    return x * 2


class TestSpawnValidation:
    @pytest.mark.parametrize('bad', ['not-callable', 123, None])
    def test_non_callable_target(self, bad):
        with pytest.raises(TypeError) as ei:
            spawn(bad)
        assert 'callable' in str(ei.value) or '可调用' in str(ei.value)

    @pytest.mark.parametrize('bad', ['abc', b'ab', bytearray(b'ab')])
    def test_str_args_rejected(self, bad):
        # str 会被当作序列逐字符展开成多个位置参数
        with pytest.raises(TypeError):
            spawn(_worker, bad)

    def test_non_sequence_args(self):
        with pytest.raises(TypeError):
            spawn(_worker, 123)

    def test_bad_kwargs(self):
        with pytest.raises(TypeError):
            spawn(_worker, (1,), kwargs='x')

    def test_non_str_name(self):
        with pytest.raises(TypeError):
            spawn(_worker, (1,), name=123)


class TestWatchdogValidation:
    @pytest.fixture()
    def handle(self):
        h = spawn(_worker, (1,), name='wd-fixture')
        h.join(timeout=30)
        return h

    def test_bad_handle(self):
        with pytest.raises(TypeError) as ei:
            watchdog(object(), timeout=1.0)
        assert 'SpawnHandle' in str(ei.value)

    @pytest.mark.parametrize('timeout', [-1, 0])
    def test_non_positive_timeout(self, handle, timeout):
        with pytest.raises(ValueError):
            watchdog(handle, timeout=timeout)

    @pytest.mark.parametrize('timeout', ['x', None, True])
    def test_bad_timeout_type(self, handle, timeout):
        with pytest.raises(TypeError):
            watchdog(handle, timeout=timeout)

    def test_bad_on_dead(self, handle):
        with pytest.raises(TypeError):
            watchdog(handle, timeout=1.0, on_dead='x')

    def test_negative_max_restarts(self, handle):
        with pytest.raises(ValueError):
            watchdog(handle, timeout=1.0, max_restarts=-1)


class TestRestartOnExitValidation:
    @pytest.mark.parametrize('bad', [-1, -(10 ** 6)])
    def test_negative_max_restarts(self, bad):
        with pytest.raises(ValueError):
            restart_on_exit(_worker, max_restarts=bad)

    def test_negative_delay(self):
        with pytest.raises(ValueError):
            restart_on_exit(_worker, delay=-1)

    def test_bad_backoff(self):
        with pytest.raises(ValueError):
            restart_on_exit(_worker, backoff=0)

    def test_non_callable_func(self):
        with pytest.raises(TypeError):
            restart_on_exit('x')

    def test_decorator_mode_still_works(self):
        ctrl = restart_on_exit(max_restarts=1, delay=0.01)
        assert ctrl is not None


class TestNormalUsageUnchanged:
    def test_spawn_and_join(self):
        h = spawn(_worker, (5,), name='normal')
        assert isinstance(h, SpawnHandle)
        assert h.is_started is True
        h.join(timeout=30)
        assert h.exitcode == 0

    def test_watchdog_lifecycle(self):
        h = spawn(_worker, (2,), name='wd-normal')
        wd = watchdog(h, timeout=1.0)
        try:
            wd.heartbeat()
            wd.start()
            time.sleep(0.1)
        finally:
            wd.stop()
            h.join(timeout=30)
        assert h.exitcode == 0

    def test_restart_controller_created(self):
        ctrl = restart_on_exit(_worker, args=(3,), max_restarts=1, delay=0.01)
        assert type(ctrl).__name__ == '_RestartController'