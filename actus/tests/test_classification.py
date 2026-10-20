"""tests/actus/test_classification.py —— 分类体系 v2.0 测试。

覆盖：
  - normalize_multi_field：小写归一/去重/截断/未知值分离
  - check_classification（打回级）：kind 未知值
  - classification_notices（警告级）：purpose/industry/trigger 未知值、冲突检测
  - 多值字段：跨维度（purpose: [transform, ai]）
  - validate_action 集成：kind 未知值进 errors
"""

import pytest

from vools.actus.constants import (
    KIND_LEVELS, PURPOSE_LEVELS, INDUSTRY_LEVELS, TRIGGER_DECL_LEVELS,
    is_known_kind, is_known_purpose, is_known_industry, is_known_trigger_decl,
)
from vools.actus.validate import (
    normalize_multi_field, check_classification, classification_notices,
)


class TestKnownValueHelpers:
    """已知值判定 helper 测试"""

    def test_is_known_kind(self):
        assert is_known_kind('exec') is True
        assert is_known_kind('EXEC') is True
        assert is_known_kind('bogus') is False

    def test_is_known_purpose(self):
        assert is_known_purpose('transform') is True
        assert is_known_purpose('ai') is True
        assert is_known_purpose('bogus') is False

    def test_is_known_industry(self):
        assert is_known_industry('devops') is True
        assert is_known_industry('general') is True
        assert is_known_industry('bogus') is False

    def test_is_known_trigger_decl(self):
        assert is_known_trigger_decl('manual') is True
        assert is_known_trigger_decl('webhook') is True
        assert is_known_trigger_decl('bogus') is False


class TestNormalizeMultiField:
    """多值字段标准化测试"""

    def test_single_string(self):
        valid, warns = normalize_multi_field('transform', PURPOSE_LEVELS)
        assert valid == ['transform']
        assert warns == []

    def test_multi_value_cross_dimension(self):
        valid, warns = normalize_multi_field(['transform', 'ai'], PURPOSE_LEVELS)
        assert valid == ['transform', 'ai']
        assert warns == []

    def test_case_normalization(self):
        valid, _ = normalize_multi_field(['TRANSFORM', 'AI'], PURPOSE_LEVELS)
        assert valid == ['transform', 'ai']

    def test_dedup(self):
        valid, _ = normalize_multi_field(['transform', 'TRANSFORM'], PURPOSE_LEVELS)
        assert valid == ['transform']

    def test_unknown_value_warned_not_dropped(self):
        valid, warns = normalize_multi_field(['transform', 'bogus'], PURPOSE_LEVELS)
        assert valid == ['transform']
        assert len(warns) == 1
        assert 'bogus' in warns[0]

    def test_none_returns_empty(self):
        valid, warns = normalize_multi_field(None, PURPOSE_LEVELS)
        assert valid == []
        assert warns == []

    def test_empty_list_returns_empty(self):
        valid, warns = normalize_multi_field([], PURPOSE_LEVELS)
        assert valid == []
        assert warns == []

    def test_truncation_to_max(self):
        # 7 个已知值 → 截断到 5（前 5 个保留，追加截断警告）
        values = ['source', 'sink', 'transform', 'orchestrator', 'notify',
                  'control', 'monitor']
        valid, warns = normalize_multi_field(values, PURPOSE_LEVELS, max_n=5)
        assert len(valid) == 5
        assert valid == ['source', 'sink', 'transform', 'orchestrator', 'notify']
        assert any('截断' in w for w in warns)

    def test_truncation_with_unknown_mixed(self):
        """已知+未知混合超限：已知值截断到 max_n，未知值全警告"""
        values = ['source', 'sink', 'transform', 'orchestrator', 'notify',
                  'control', 'bogus1', 'bogus2']
        valid, warns = normalize_multi_field(values, PURPOSE_LEVELS, max_n=5)
        assert valid == ['source', 'sink', 'transform', 'orchestrator', 'notify']
        assert any('bogus1' in w for w in warns)
        assert any('bogus2' in w for w in warns)
        assert any('截断' in w for w in warns)

    def test_whitespace_values_skipped(self):
        valid, _ = normalize_multi_field(['transform', '  ', ''], PURPOSE_LEVELS)
        assert valid == ['transform']


class TestCheckClassificationReject:
    """打回级验证（kind 未知值）测试"""

    def test_valid_kind(self):
        assert check_classification({'kind': 'exec'}) == []

    def test_invalid_kind_rejected(self):
        errors = check_classification({'kind': 'bogus'})
        assert len(errors) == 1
        assert 'kind 非法' in errors[0]

    def test_missing_kind_ok(self):
        """缺 kind 不打回（回填 exec 在 model 便捷读取层处理）"""
        assert check_classification({}) == []


class TestClassificationNoticesWarn:
    """警告级验证（purpose/industry/trigger 未知值）测试"""

    def test_valid_purpose_no_notice(self):
        notices = classification_notices({'purpose': ['transform', 'ai']})
        assert notices == []

    def test_unknown_purpose_warned(self):
        notices = classification_notices({'purpose': ['transform', 'bogus']})
        assert any('purpose' in n and 'bogus' in n for n in notices)

    def test_unknown_industry_warned(self):
        notices = classification_notices({'industry': ['bogus']})
        assert any('industry' in n and 'bogus' in n for n in notices)

    def test_unknown_trigger_warned(self):
        notices = classification_notices({'trigger': ['bogus']})
        assert any('trigger' in n and 'bogus' in n for n in notices)

    def test_kind_doc_purpose_conflict(self):
        notices = classification_notices({'kind': 'doc', 'purpose': ['compute']})
        assert any('语义冲突' in n for n in notices)

    def test_kind_template_orchestrator_conflict(self):
        notices = classification_notices({'kind': 'template', 'purpose': ['orchestrator']})
        assert any('语义冲突' in n for n in notices)

    def test_kind_link_transform_legal(self):
        """link 转发 transform 合法——不产生冲突警告"""
        notices = classification_notices({'kind': 'link', 'purpose': ['transform']})
        assert not any('语义冲突' in n for n in notices)

    def test_trigger_wrong_type(self):
        notices = classification_notices({'trigger': 123})
        assert any('trigger 必须是' in n for n in notices)


class TestEcosystemNotices:
    """生态层声明警告（license/pricing/declared_features/demo）测试"""

    def test_unknown_license_warned(self):
        notices = classification_notices({'license': 'bogus-license'})
        assert any('license 未知值' in n for n in notices)

    def test_custom_license_without_url(self):
        notices = classification_notices({'license': 'custom'})
        assert any('license_url' in n for n in notices)

    def test_custom_license_with_url_ok(self):
        notices = classification_notices({'license': 'custom', 'license_url': 'https://x'})
        assert not any('license_url' in n for n in notices)

    def test_paid_pricing_warned(self):
        notices = classification_notices({'pricing': 'paid'})
        assert any('gated 免费放行' in n for n in notices)

    def test_unknown_pricing_warned(self):
        notices = classification_notices({'pricing': 'bogus'})
        assert any('pricing 未知值' in n for n in notices)

    def test_declared_features_unknown(self):
        notices = classification_notices({'declared_features': ['network-access', 'bogus']})
        assert any('declared_features 未知值' in n for n in notices)

    def test_declared_features_known_ok(self):
        notices = classification_notices({'declared_features': ['network-access', 'file-write']})
        assert notices == []

    def test_demo_missing_file_warned(self):
        notices = classification_notices({'demo': '/nonexistent/demo.mp4'})
        assert any('demo 文件不存在' in n for n in notices)
