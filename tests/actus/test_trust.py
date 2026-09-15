"""tests/actus/test_trust.py — trust 决策引擎测试"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from vools.actus.trust import decide, check_permissions
from vools.actus.errors import ActionError
from vools.actus.constants import TRUST_LEVELS


class TestDecide:
    """decide 信任决策测试"""

    def test_trusted_returns_auto(self):
        assert decide('trusted') == 'auto'

    def test_sandbox_returns_sandbox(self):
        assert decide('sandbox') == 'sandbox'

    def test_audit_without_confirm(self):
        assert decide('audit') == 'need_confirm'

    def test_audit_with_confirm(self):
        assert decide('audit', confirmed=True) == 'auto'

    def test_invalid_trust_raises(self):
        with pytest.raises(ActionError) as exc_info:
            decide('invalid_level')
        assert 'trust_rejected' in str(exc_info.value) or '非法' in str(exc_info.value)

    def test_all_valid_trust_levels(self):
        for level in TRUST_LEVELS:
            result = decide(level)
            assert result in ('auto', 'sandbox', 'need_confirm')


class TestCheckPermissions:
    """check_permissions 权限检查测试"""

    def test_no_declarations(self):
        with pytest.raises(ActionError):
            check_permissions([], 'file_read')

    def test_with_declarations(self):
        # 声明的权限应通过（使用合法的权限名）
        check_permissions(['files:read', 'net:connect'], 'files:read')

    def test_undeclared_raises(self):
        with pytest.raises(ActionError):
            check_permissions(['files:read'], 'net:connect')
