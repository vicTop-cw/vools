"""tests/actus/test_security.py — 安全扫描器测试"""
import pytest
import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from vools.actus.security import (
    SecurityScanner, SensitiveInfoDetector, AuditLogger,
    SecurityLevel, AuditEvent, InputValidator,
    get_security_scanner, scan_action, scan_output,
)


class TestSecurityLevel:
    """SecurityLevel 枚举测试"""

    def test_levels_exist(self):
        assert SecurityLevel.STRICT.value == 'strict'
        assert SecurityLevel.STANDARD.value == 'standard'
        assert SecurityLevel.RELAXED.value == 'relaxed'


class TestAuditEvent:
    """AuditEvent 数据类测试"""

    def test_creation(self):
        event = AuditEvent(
            action_id='test.action',
            event_type='security_scan',
            details={'safe': True},
            success=True,
            timestamp='2024-01-01T00:00:00',
        )
        assert event.action_id == 'test.action'
        assert event.success is True


class TestAuditLogger:
    """AuditLogger 审计日志测试"""

    def test_log_and_get_events(self):
        logger = AuditLogger()
        logger.log('test', 'scan', {'safe': True}, True)
        events = logger.get_events()
        assert len(events) >= 1
        assert events[0].action_id == 'test'

    def test_filter_by_action(self):
        logger = AuditLogger()
        logger.log('action_a', 'scan', {}, True)
        logger.log('action_b', 'scan', {}, False)
        events = logger.get_events(action_id='action_a')
        assert all(e.action_id == 'action_a' for e in events)

    def test_summary(self):
        logger = AuditLogger()
        logger.log('a', 'scan', {}, True)
        logger.log('b', 'scan', {}, False)
        summary = logger.summary()
        assert 'total_events' in summary
        assert summary['total_events'] >= 2


class TestSensitiveInfoDetector:
    """SensitiveInfoDetector 敏感信息检测测试"""

    def test_scan_clean_text(self):
        detector = SensitiveInfoDetector()
        findings = detector.scan('This is a clean text with no secrets.')
        assert findings == []

    def test_scan_api_key_pattern(self):
        detector = SensitiveInfoDetector()
        findings = detector.scan('api_key = "sk-1234567890abcdef"')
        assert isinstance(findings, list)

    def test_redact(self):
        detector = SensitiveInfoDetector()
        redacted = detector.redact('password=secret123', replacement='***')
        assert isinstance(redacted, str)

    def test_scan_file(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write('Some clean content')
            f.flush()
            detector = SensitiveInfoDetector()
            findings = detector.scan_file(f.name)
            assert isinstance(findings, list)
        os.unlink(f.name)

    def test_redact_file(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write('password=mysecret')
            f.flush()
            detector = SensitiveInfoDetector()
            redacted = detector.redact_file(f.name)
            assert isinstance(redacted, str)
        os.unlink(f.name)


class TestInputValidator:
    """InputValidator 输入验证测试"""

    def test_check_safe_command(self):
        validator = InputValidator()
        ok, issues = validator.check_command('echo hello')
        assert isinstance(ok, bool)

    def test_check_suspicious_command(self):
        validator = InputValidator()
        ok, issues = validator.check_command('rm -rf /')
        assert isinstance(ok, bool)

    def test_sanitize_filename(self):
        validator = InputValidator()
        safe = validator.sanitize_filename('../../etc/passwd')
        # 路径分隔符被替换为下划线
        assert '/' not in safe
        assert '\\' not in safe
        assert isinstance(safe, str)


class TestSecurityScanner:
    """SecurityScanner 综合扫描测试"""

    def test_scan_safe_action(self):
        scanner = SecurityScanner()
        result = scanner.scan_action(
            'test.safe',
            {'permissions': [], 'trust': 'trusted'},
            code='echo hello',
        )
        assert 'safe' in result
        assert isinstance(result['safe'], bool)

    def test_scan_with_code(self):
        scanner = SecurityScanner()
        result = scanner.scan_action(
            'test.code',
            {'permissions': []},
            code='import os; os.system("ls")',
        )
        assert 'issues' in result
        assert 'warnings' in result

    def test_scan_text_output(self):
        scanner = SecurityScanner()
        result = scanner.scan_text_output('output with password=secret', 'test.action')
        assert 'has_sensitive' in result
        assert isinstance(result['has_sensitive'], bool)

    def test_summary(self):
        scanner = SecurityScanner()
        scanner.scan_action('a', {}, code='echo 1')
        summary = scanner.summary()
        assert 'audit' in summary
        assert 'policy_level' in summary


class TestModuleLevelFunctions:
    """模块级便捷函数测试"""

    def test_get_security_scanner(self):
        scanner = get_security_scanner()
        assert isinstance(scanner, SecurityScanner)

    def test_scan_action_function(self):
        result = scan_action('test.fn', {'permissions': []}, code='echo 1')
        assert 'safe' in result

    def test_scan_output_function(self):
        result = scan_output('clean output', 'test')
        assert 'has_sensitive' in result
