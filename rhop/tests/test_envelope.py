"""v2 信封测试：envelope.py（.rhop 格式 + 序列化/反序列化 + checksum）。"""

import json

import pytest

from vools.rhop.core import Side, TaskStatus
from vools.rhop.envelope import Envelope


def _make_env(**over):
    defaults = dict(
        task_id="job-001",
        status=TaskStatus.PENDING,
        payload={"cmd": "echo hi"},
        side=Side.REQUESTER,
        version=1,
    )
    defaults.update(over)
    return Envelope(**defaults)


class TestEnvelopeSerialization:
    def test_roundtrip(self):
        env = _make_env()
        raw = env.to_rhop_bytes()
        restored = Envelope.from_rhop_bytes(raw)
        assert restored.task_id == env.task_id
        assert restored.status == env.status
        assert restored.payload == env.payload
        assert restored.side == env.side
        assert restored.version == env.version
        assert restored.checksum == env.checksum

    def test_to_rhop_bytes_is_valid_json(self):
        env = _make_env()
        raw = env.to_rhop_bytes()
        data = json.loads(raw.decode("utf-8"))
        assert data["v"] == 1
        assert data["task_id"] == "job-001"
        assert data["status"] == "pending"
        assert data["checksum"].startswith("sha256:")

    def test_from_rhop_bytes_detects_corruption(self):
        env = _make_env()
        raw = env.to_rhop_bytes()
        # 篡改内容
        corrupted = raw[:-5] + b"xxxxx"
        with pytest.raises(ValueError):
            Envelope.from_rhop_bytes(corrupted)

    def test_checksum_matches_on_fresh(self):
        env = _make_env()
        assert env.checksum != ""
        assert env.checksum.startswith("sha256:")

    def test_hops_seen_preserved(self):
        env = _make_env(hops_seen=["requester", "executor"])
        raw = env.to_rhop_bytes()
        restored = Envelope.from_rhop_bytes(raw)
        assert restored.hops_seen == ["requester", "executor"]

    def test_to_dict_from_dict_roundtrip(self):
        env = _make_env(result={"stdout": "ok"}, error="none")
        d = env.to_dict()
        restored = Envelope.from_dict(d)
        assert restored.task_id == env.task_id
        assert restored.result == env.result
