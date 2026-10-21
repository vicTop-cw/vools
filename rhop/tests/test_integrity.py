"""v2 完整性校验测试：integrity.py。"""

import pytest

from vools.rhop.core import Side, TaskStatus
from vools.rhop.envelope import Envelope
from vools.rhop.integrity import IntegrityChecker


def _make_env():
    return Envelope(
        task_id="job-001",
        status=TaskStatus.PENDING,
        payload={"cmd": "echo hi"},
        side=Side.REQUESTER,
        created_at="2026-10-21T10:00:00Z",
        updated_at="2026-10-21T10:00:00Z",
    )


class TestIntegrityChecker:
    def test_verify_ok(self):
        env = _make_env()
        raw = env.to_rhop_bytes()
        ok, err = IntegrityChecker.verify(env, raw)
        assert ok
        assert err == ""

    def test_verify_corrupted(self):
        env = _make_env()
        raw = env.to_rhop_bytes()
        corrupted = raw[:-10] + b"XXXXXXXXXX"
        ok, err = IntegrityChecker.verify(env, corrupted)
        assert not ok

    def test_verify_bytes_ok(self):
        env = _make_env()
        raw = env.to_rhop_bytes()
        ok, err = IntegrityChecker.verify_bytes(raw)
        assert ok

    def test_verify_bytes_corrupted(self):
        raw = b'{"v":1,"task_id":"x","checksum":"sha256:wrong"}'
        ok, err = IntegrityChecker.verify_bytes(raw)
        assert not ok

    def test_checksum_match(self):
        env = _make_env()
        assert IntegrityChecker.checksum_match(env)
