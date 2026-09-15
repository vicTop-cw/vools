"""tests/actus/test_sandbox.py — 沙箱环境测试"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from vools.actus.sandbox import sandbox_env, prepare, cleanup


class TestSandboxEnv:
    """sandbox_env 环境变量注入测试"""

    def test_returns_dict(self):
        env = sandbox_env('/tmp/sandbox')
        assert isinstance(env, dict)

    def test_contains_required_keys(self):
        env = sandbox_env('/tmp/sandbox')
        assert 'ACTUS_SANDBOX' in env
        assert 'ACTUS_SANDBOX_ROOT' in env
        assert 'TMPDIR' in env
        assert 'TEMP' in env
        assert 'TMP' in env

    def test_sandbox_root_value(self):
        root = '/custom/sandbox/path'
        env = sandbox_env(root)
        assert env['ACTUS_SANDBOX_ROOT'] == root
        assert env['TMPDIR'] == root

    def test_sandbox_flag_set(self):
        env = sandbox_env('/tmp')
        assert env['ACTUS_SANDBOX'] == '1'


class TestPrepareCleanup:
    """prepare / cleanup 生命周期测试"""

    def test_prepare_returns_path(self):
        result = prepare('/tmp', 'test_exec_123')
        assert isinstance(result, str)
        assert 'test_exec_123' in result

    def test_cleanup_returns_none(self):
        result = cleanup('/tmp', 'test_exec_123')
        assert result is None

    def test_prepare_and_cleanup_roundtrip(self):
        prepare('/tmp', 'test_exec_456')
        cleanup('/tmp', 'test_exec_456')
        assert True  # 无异常即通过
