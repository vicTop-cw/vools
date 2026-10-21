"""v2 签名器测试：signer.py（FileHashSigner + NPUSigner）。"""

import pytest

from vools.rhop.signer import FileHashSigner, NPUSigner


class TestFileHashSigner:
    def test_sign_and_verify(self):
        s = FileHashSigner()
        sig = s.sign("job-001", {"stdout": "ok"})
        assert sig.startswith("sha256:")
        assert s.verify("job-001", {"stdout": "ok"}, sig)

    def test_verify_wrong_result_fails(self):
        s = FileHashSigner()
        sig = s.sign("job-001", {"stdout": "ok"})
        assert not s.verify("job-001", {"stdout": "NO"}, sig)

    def test_verify_wrong_task_id_fails(self):
        s = FileHashSigner()
        sig = s.sign("job-001", {"stdout": "ok"})
        assert not s.verify("job-002", {"stdout": "ok"}, sig)

    def test_deterministic(self):
        s = FileHashSigner()
        sig1 = s.sign("t", {"a": 1})
        sig2 = s.sign("t", {"a": 1})
        assert sig1 == sig2


class TestNPUSigner:
    def test_sign_returns_none_without_npu_smi(self, monkeypatch):
        """npu-smi 不可用时 sign 返回 None。"""
        def raise_fn(*a, **kw):
            raise FileNotFoundError("npu-smi not found")
        monkeypatch.setattr("subprocess.check_output", raise_fn)
        s = NPUSigner()
        assert s.sign("job-001", {"stdout": "ok"}) is None

    def test_verify_returns_false_when_sign_fails(self, monkeypatch):
        def raise_fn(*a, **kw):
            raise FileNotFoundError
        monkeypatch.setattr("subprocess.check_output", raise_fn)
        s = NPUSigner()
        assert not s.verify("job-001", {"stdout": "ok"}, "anything")

    def test_sign_with_mocked_npu_smi(self, monkeypatch):
        """mock npu-smi 输出，验证签名格式。"""
        def fake_output(*a, **kw):
            return b"Serial : ABC123\nOther: xyz"
        monkeypatch.setattr("subprocess.check_output", fake_output)
        s = NPUSigner(marker="NPU_MARKER")
        sig = s.sign("job-001", {"stdout": "ok"})
        assert sig is not None
        assert sig.startswith("NPU_MARKER:ABC123:")
        # 验证
        assert s.verify("job-001", {"stdout": "ok"}, sig)
        assert not s.verify("job-001", {"stdout": "NO"}, sig)
