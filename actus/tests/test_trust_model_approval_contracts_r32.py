"""trust_model ApprovalManager + TrustEvaluator 契约测试（第 32 批，直接由 Lead 编写）。

退步了会怎样：
- ApprovalManager 审批流程失效 → 未批准的动作被执行或已批准的动作被拒
- TrustEvaluator 信任评估错误 → 低信任动作被放行或高信任动作被误拒
"""
import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_approvals_dir(tmp_path, monkeypatch):
    """隔离：审批记录目录指向 tmp。"""
    d = tmp_path / "approvals"
    d.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    return str(d)


class TestApprovalManager:
    def test_request_approval_public(self, tmp_approvals_dir):
        """退步了会怎样：public 动作应 pending。"""
        from vools.actus.trust_model import ApprovalManager
        am = ApprovalManager(approvals_dir=tmp_approvals_dir)
        rec = am.request_approval("act.a", "https://x", ["files:read"], "abc123")
        assert rec["status"] == "pending"

    def test_request_approval_private_auto_approved(self, tmp_approvals_dir):
        """退步了会怎样：private + author 应 auto_approved。"""
        from vools.actus.trust_model import ApprovalManager
        am = ApprovalManager(approvals_dir=tmp_approvals_dir)
        rec = am.request_approval("act.a", "https://x", ["files:read"], "abc123",
                                  visibility="private", author="alice")
        assert rec["status"] == "auto_approved"

    def test_approve(self, tmp_approvals_dir):
        """退步了会怎样：approve 应把状态改为 approved。"""
        from vools.actus.trust_model import ApprovalManager
        am = ApprovalManager(approvals_dir=tmp_approvals_dir)
        am.request_approval("act.a", "https://x", [], "abc123")
        rec = am.approve("act.a")
        assert rec["status"] == "approved"

    def test_reject(self, tmp_approvals_dir):
        """退步了会怎样：reject 应把状态改为 rejected。"""
        from vools.actus.trust_model import ApprovalManager
        am = ApprovalManager(approvals_dir=tmp_approvals_dir)
        am.request_approval("act.a", "https://x", [], "abc123")
        rec = am.reject("act.a", "violation")
        assert rec["status"] == "rejected"
        assert rec["reason"] == "violation"

    def test_is_approved(self, tmp_approvals_dir):
        """退步了会怎样：is_approved 应正确判断。"""
        from vools.actus.trust_model import ApprovalManager
        am = ApprovalManager(approvals_dir=tmp_approvals_dir)
        am.request_approval("act.a", "https://x", [], "abc123")
        assert am.is_approved("act.a") is False
        am.approve("act.a")
        assert am.is_approved("act.a") is True

    def test_is_rejected(self, tmp_approvals_dir):
        """退步了会怎样：is_rejected 应正确判断。"""
        from vools.actus.trust_model import ApprovalManager
        am = ApprovalManager(approvals_dir=tmp_approvals_dir)
        am.request_approval("act.a", "https://x", [], "abc123")
        assert am.is_rejected("act.a") is False
        am.reject("act.a")
        assert am.is_rejected("act.a") is True

    def test_is_approved_nonexistent(self, tmp_approvals_dir):
        """退步了会怎样：未存在的 action 不应 approved。"""
        from vools.actus.trust_model import ApprovalManager
        am = ApprovalManager(approvals_dir=tmp_approvals_dir)
        assert am.is_approved("not.exists") is False

    def test_list_pending(self, tmp_approvals_dir):
        """退步了会怎样：list_pending 应只列 pending 记录。"""
        from vools.actus.trust_model import ApprovalManager
        am = ApprovalManager(approvals_dir=tmp_approvals_dir)
        am.request_approval("act.a", "https://x", [], "abc123")
        am.request_approval("act.b", "https://x", [], "def456")
        am.approve("act.a")
        pending = am.list_pending()
        assert len(pending) == 1
        assert pending[0]["action_id"] == "act.b"

    def test_list_pending_empty_dir(self, tmp_approvals_dir):
        """退步了会怎样：空目录应返回空列表。"""
        from vools.actus.trust_model import ApprovalManager
        am = ApprovalManager(approvals_dir=tmp_approvals_dir)
        assert am.list_pending() == []

    def test_approve_nonexistent(self, tmp_approvals_dir):
        """退步了会怎样：approve 不存在的 action 应返回 None。"""
        from vools.actus.trust_model import ApprovalManager
        am = ApprovalManager(approvals_dir=tmp_approvals_dir)
        assert am.approve("not.exists") is None

    def test_reject_nonexistent(self, tmp_approvals_dir):
        """退步了会怎样：reject 不存在的 action 应返回 None。"""
        from vools.actus.trust_model import ApprovalManager
        am = ApprovalManager(approvals_dir=tmp_approvals_dir)
        assert am.reject("not.exists") is None


class TestTrustEvaluator:
    def test_evaluate_not_installed(self):
        """退步了会怎样：未安装的 action 应报 error。"""
        from vools.actus.trust_model import TrustEvaluator
        te = TrustEvaluator()
        result = te.evaluate("not.installed")
        assert result["can_execute"] is False
        assert "not installed" in result["error"]
