"""tests/concurrent/test_spawns.py — 进程/线程生成测试

**为什么用模块级函数而不是 lambda**：``vools.concurrent.spawns`` 基于
``multiprocessing.Process``，Windows 下用 spawn 启动方式，target 必须**可 pickle**。
lambda 定义在函数体内部，pickle 无法按名引用（``Can't pickle local object
'TestSpawnHandle.test_creation.<locals>.<lambda>'``），所以旧版整文件 24 个用例全挂。

这里把回调提成模块级函数（可 pickle），并按真实签名对齐：
``SpawnHandle.pid/exitcode/name/process/is_started`` 是 **property**（不是方法）、
``SpawnManager.names()`` 是**方法**、``SpawnManager.is_alive(name)`` 需要参数、
``spawn_many(func, args_list)`` 第二参是**参数列表的列表**、``restart_on_exit``
装饰器调用后返回的是 ``SpawnHandle``（不是被装饰函数的返回值）。
"""
import pytest
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from vools.concurrent.spawns import (
    SpawnHandle, spawn, spawn_many, restart_on_exit,
    SpawnManager,
)


# --- 模块级回调（必须可 pickle，见文件头说明） ---------------------------

def _noop():
    return None


def _sleep_short():
    time.sleep(0.1)


def _sleep_long():
    time.sleep(30)


def _append_to(results, value):
    results.append(value)


def _unstable():
    """restart_on_exit 测试用回调——必须是模块级才能被 pickle。"""
    return 42


class TestSpawnHandle:
    """SpawnHandle 生成句柄测试"""

    def test_creation(self):
        p = spawn(_noop)
        assert isinstance(p, SpawnHandle)
        p.join(timeout=30.0)

    def test_start_and_join(self):
        p = spawn(_noop)
        p.join(timeout=30.0)
        assert p.is_alive() is False

    def test_terminate(self):
        p = spawn(_sleep_long)
        p.terminate()
        p.join(timeout=30.0)
        assert p.is_alive() is False

    def test_kill(self):
        p = spawn(_sleep_long)
        p.kill()
        p.join(timeout=30.0)
        assert p.is_alive() is False

    def test_pid(self):
        p = spawn(_sleep_short)
        # pid 是 property
        assert p.pid is not None
        p.join(timeout=30.0)

    def test_exitcode(self):
        p = spawn(_noop)
        p.join(timeout=30.0)
        assert p.exitcode is not None

    def test_is_alive(self):
        p = spawn(_sleep_short)
        p.join(timeout=30.0)
        assert p.is_alive() is False

    def test_is_started(self):
        p = spawn(_noop)
        # is_started 是 property
        assert p.is_started is True
        p.join(timeout=30.0)

    def test_name(self):
        p = spawn(_noop, name='test_worker')
        assert p.name == 'test_worker'
        p.join(timeout=30.0)

    def test_process(self):
        p = spawn(_noop)
        # process 是 property
        assert p.process is not None
        p.join(timeout=30.0)

    def test_context_manager(self):
        with spawn(_noop) as p:
            p.join(timeout=30.0)
        assert True  # 无异常即通过

    def test_args_and_kwargs(self):
        p = spawn(_append_to, args=([], 'x'))
        p.join(timeout=30.0)
        assert p.exitcode == 0


class TestSpawnFunction:
    """spawn 函数测试"""

    def test_spawn_returns_handle(self):
        p = spawn(_noop)
        assert isinstance(p, SpawnHandle)
        p.join(timeout=30.0)

    def test_spawn_with_name(self):
        p = spawn(_noop, name='worker')
        assert p.name == 'worker'
        p.join(timeout=30.0)

    def test_spawn_autostart_false(self):
        p = spawn(_noop, autostart=False)
        assert p.is_started is False
        p.start()
        assert p.is_started is True
        p.join(timeout=30.0)


class TestSpawnMany:
    """spawn_many 批量生成测试"""

    def test_spawn_many(self):
        # 真实签名：spawn_many(func, args_list) —— 第二参是「每个进程的位置参数」列表
        handles = spawn_many(_noop, [(), (), ()])
        assert len(handles) == 3
        for h in handles:
            h.join(timeout=30.0)
        assert all(h.exitcode == 0 for h in handles)

    def test_spawn_many_length_mismatch(self):
        with pytest.raises(ValueError):
            spawn_many(_noop, [(), ()], kwargs_list=[{}])


class TestRestartOnExit:
    """restart_on_exit 重启控制器测试

    装饰器用法下，调用被装饰函数返回的是 **SpawnHandle**（控制器启动并监控进程），
    不是原函数的返回值。
    """

    def test_decorator_returns_handle(self):
        # 被装饰的函数也必须是**模块级**的：restart_on_exit 会把它交给
        # multiprocessing，嵌套定义无法 pickle。
        decorated = restart_on_exit(max_restarts=2, delay=0.1)(_unstable)
        handle = decorated()
        assert isinstance(handle, SpawnHandle)
        handle.join(timeout=30.0)


class TestSpawnManager:
    """SpawnManager 生成管理器测试"""

    def test_creation(self):
        m = SpawnManager()
        assert m is not None

    def test_register_unregister(self):
        m = SpawnManager()
        m.register('task1', _noop)
        assert 'task1' in m.names()
        m.unregister('task1')
        assert 'task1' not in m.names()

    def test_start_stop(self):
        m = SpawnManager()
        m.register('quick', _sleep_short)
        m.start('quick')
        m.stop('quick')
        assert m.is_alive('quick') is False

    def test_start_all_stop_all(self):
        m = SpawnManager()
        m.register('a', _sleep_short)
        m.register('b', _sleep_short)
        m.start_all()
        m.stop_all()
        assert m.is_alive('a') is False
        assert m.is_alive('b') is False

    def test_restart(self):
        m = SpawnManager()
        m.register('task', _sleep_short)
        m.start('task')
        m.restart('task')
        assert m.get('task') is not None
        m.stop('task')

    def test_get(self):
        m = SpawnManager()
        m.register('task', _noop)
        handle = m.get('task')
        assert handle is not None

    def test_names(self):
        m = SpawnManager()
        m.register('a', _noop)
        m.register('b', _noop)
        assert 'a' in m.names()
        assert 'b' in m.names()

    def test_is_alive(self):
        m = SpawnManager()
        m.register('task', _sleep_short)
        m.start('task')
        m.stop('task')
        assert m.is_alive('task') is False

    def test_status(self):
        m = SpawnManager()
        status = m.status()
        assert isinstance(status, dict)

    def test_monitor(self):
        m = SpawnManager()
        m.register('quick', _noop)
        m.start_all()
        # monitor(timeout) 阻塞等待全部结束，返回是否全部结束
        assert m.monitor(timeout=10.0) is True

    def test_len(self):
        m = SpawnManager()
        m.register('a', _noop)
        m.register('b', _noop)
        assert len(m) == 2

    def test_contains(self):
        m = SpawnManager()
        m.register('task', _noop)
        assert 'task' in m

    def test_duplicate_register_raises(self):
        m = SpawnManager()
        m.register('task', _noop)
        with pytest.raises(ValueError):
            m.register('task', _noop)

    def test_unregister_alive_raises(self):
        m = SpawnManager()
        m.register('task', _sleep_long)
        m.start('task')
        try:
            with pytest.raises(RuntimeError):
                m.unregister('task')
        finally:
            m.stop('task')
