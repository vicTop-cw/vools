"""tests/concurrent/test_spawns.py — 进程/线程生成测试"""
import pytest
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from vools.concurrent.spawns import (
    SpawnHandle, spawn, spawn_many, restart_on_exit,
    SpawnManager,
)


class TestSpawnHandle:
    """SpawnHandle 生成句柄测试"""

    def test_creation(self):
        p = spawn(lambda: None)
        assert isinstance(p, SpawnHandle)
        p.join(timeout=1.0)

    def test_start_and_join(self):
        p = spawn(lambda: None)
        p.start()
        p.join(timeout=5.0)
        assert p.is_alive() is False

    def test_terminate(self):
        p = spawn(lambda: time.sleep(10))
        p.start()
        p.terminate()
        p.join(timeout=2.0)
        assert p.is_alive() is False

    def test_kill(self):
        p = spawn(lambda: time.sleep(10))
        p.start()
        p.kill()
        p.join(timeout=2.0)
        assert p.is_alive() is False

    def test_pid(self):
        p = spawn(lambda: time.sleep(0.1))
        p.start()
        assert p.pid is not None
        p.join(timeout=2.0)

    def test_exitcode(self):
        p = spawn(lambda: None)
        p.start()
        p.join(timeout=5.0)
        assert p.exitcode is not None

    def test_is_alive(self):
        p = spawn(lambda: time.sleep(0.1))
        p.start()
        # 运行中可能短暂为 True
        p.join(timeout=2.0)
        assert p.is_alive() is False

    def test_is_started(self):
        p = spawn(lambda: None)
        p.start()
        assert p.is_started is True
        p.join(timeout=2.0)

    def test_name(self):
        p = spawn(lambda: None, name='test_worker')
        assert p.name == 'test_worker'
        p.start()
        p.join(timeout=2.0)

    def test_process(self):
        p = spawn(lambda: None)
        p.start()
        assert p.process is not None
        p.join(timeout=2.0)

    def test_context_manager(self):
        with spawn(lambda: None) as p:
            p.join(timeout=2.0)
        assert True  # 无异常即通过


class TestSpawnFunction:
    """spawn 函数测试"""

    def test_spawn_returns_handle(self):
        p = spawn(lambda: None)
        assert isinstance(p, SpawnHandle)
        p.join(timeout=2.0)

    def test_spawn_with_name(self):
        p = spawn(lambda: None, name='worker')
        assert p.name == 'worker'
        p.join(timeout=2.0)


class TestSpawnMany:
    """spawn_many 批量生成测试"""

    def test_spawn_many(self):
        handles = spawn_many(lambda x: None, 3)
        assert len(handles) == 3
        for h in handles:
            h.join(timeout=2.0)


class TestRestartOnExit:
    """restart_on_exit 重启控制器测试"""

    def test_decorator(self):
        @restart_on_exit(max_restarts=2)
        def unstable():
            return 42

        assert unstable() == 42


class TestSpawnManager:
    """SpawnManager 生成管理器测试"""

    def test_creation(self):
        m = SpawnManager()
        assert m is not None

    def test_register_unregister(self):
        m = SpawnManager()
        m.register('task1', lambda: None)
        assert 'task1' in m.names
        m.unregister('task1')
        assert 'task1' not in m.names

    def test_start_stop(self):
        m = SpawnManager()
        m.register('quick', lambda: None)
        m.start('quick')
        m.stop('quick')
        assert True  # 无异常即通过

    def test_start_all_stop_all(self):
        m = SpawnManager()
        m.register('a', lambda: None)
        m.register('b', lambda: None)
        m.start_all()
        m.stop_all()
        assert True  # 无异常即通过

    def test_restart(self):
        m = SpawnManager()
        m.register('task', lambda: None)
        m.restart('task')
        assert True  # 无异常即通过

    def test_get(self):
        m = SpawnManager()
        m.register('task', lambda: None)
        handle = m.get('task')
        assert handle is not None

    def test_names(self):
        m = SpawnManager()
        m.register('a', lambda: None)
        m.register('b', lambda: None)
        assert 'a' in m.names
        assert 'b' in m.names

    def test_is_alive(self):
        m = SpawnManager()
        m.register('task', lambda: time.sleep(0.1))
        m.start('task')
        m.stop('task')
        assert True  # 无异常即通过

    def test_status(self):
        m = SpawnManager()
        status = m.status()
        assert isinstance(status, dict)

    def test_monitor(self):
        m = SpawnManager()
        results = []
        m.monitor(lambda s: results.append(s))
        assert True  # 无异常即通过

    def test_len(self):
        m = SpawnManager()
        m.register('a', lambda: None)
        m.register('b', lambda: None)
        assert len(m) == 2

    def test_contains(self):
        m = SpawnManager()
        m.register('task', lambda: None)
        assert 'task' in m
