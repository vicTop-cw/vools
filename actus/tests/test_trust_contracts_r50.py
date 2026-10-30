"""trust.py 契约测试 — trust 判定与权限检查。

覆盖目标：
- decide() 全部分支：trusted/sandbox/audit/非法值
- check_permissions() 全部路径：已声明/未声明/未知权限
"""
import pytest

from vools.actus.errors import ActionError
from vools.actus.trust import decide, check_permissions


class TestDecide:
    """decide() 测试。"""

    def test_trusted_returns_auto(self):
        assert decide('trusted') == 'auto'

    def test_sandbox_returns_sandbox(self):
        assert decide('sandbox') == 'sandbox'

    def test_audit_unconfirmed_returns_need_confirm(self):
        assert decide('audit') == 'need_confirm'

    def test_audit_confirmed_returns_auto(self):
        assert decide('audit', confirmed=True) == 'auto'

    def test_audit_unconfirmed_explicit_false(self):
        assert decide('audit', confirmed=False) == 'need_confirm'

    def test_illegal_trust_raises(self):
        with pytest.raises(ActionError) as exc_info:
            decide('bogus')
        assert exc_info.value.code == 'trust_rejected'

    def test_illegal_trust_none_raises(self):
        with pytest.raises(ActionError) as exc_info:
            decide(None)
        assert exc_info.value.code == 'trust_rejected'

    def test_illegal_trust_empty_string_raises(self):
        with pytest.raises(ActionError) as exc_info:
            decide('')
        assert exc_info.value.code == 'trust_rejected'

    def test_trusted_with_confirmed_ignored(self):
        """trusted 不管 confirmed 如何都返回 auto。"""
        assert decide('trusted', confirmed=True) == 'auto'
        assert decide('trusted', confirmed=False) == 'auto'

    def test_sandbox_with_confirmed_ignored(self):
        """sandbox 不管 confirmed 如何都返回 sandbox。"""
        assert decide('sandbox', confirmed=True) == 'sandbox'
        assert decide('sandbox', confirmed=False) == 'sandbox'


class TestCheckPermissions:
    """check_permissions() 测试。"""

    def test_declared_permission_passes(self):
        """已声明权限不抛错。"""
        check_permissions(['files:read', 'net:connect'], 'files:read')

    def test_multiple_declared_permissions(self):
        """多个已声明权限不抛错。"""
        check_permissions(['files:read', 'net:connect', 'process:spawn'], 'net:connect')

    def test_undeclared_permission_raises(self):
        """未声明权限抛错。"""
        with pytest.raises(ActionError) as exc_info:
            check_permissions(['files:read'], 'net:connect')
        assert exc_info.value.code == 'permission_denied'

    def test_empty_declared_raises(self):
        """空列表声明，任何权限都抛错。"""
        with pytest.raises(ActionError) as exc_info:
            check_permissions([], 'files:read')
        assert exc_info.value.code == 'permission_denied'

    def test_none_declared_raises(self):
        """None 声明，任何权限都抛错。"""
        with pytest.raises(ActionError) as exc_info:
            check_permissions(None, 'files:read')
        assert exc_info.value.code == 'permission_denied'

    def test_unknown_permission_raises(self):
        """未知权限（不在合法权限表中）抛错。"""
        with pytest.raises(ActionError) as exc_info:
            check_permissions(['files:read'], 'bogus_perm')
        assert exc_info.value.code == 'permission_denied'

    def test_unknown_permission_with_declared(self):
        """即使声明了，未知权限仍抛错。"""
        with pytest.raises(ActionError) as exc_info:
            check_permissions(['bogus_perm'], 'bogus_perm')
        assert exc_info.value.code == 'permission_denied'

    def test_error_has_context(self):
        """越权错误应携带上下文信息。"""
        with pytest.raises(ActionError) as exc_info:
            check_permissions(['files:read'], 'net:connect')
        err = exc_info.value
        assert 'net:connect' in err.message
        assert 'files:read' in str(err.details)

    def test_all_valid_permissions_listed(self):
        """所有合法权限应能通过检查（防止权限表遗漏）。"""
        from vools.actus.constants import PERMISSIONS
        for perm in PERMISSIONS:
            check_permissions([perm], perm)
