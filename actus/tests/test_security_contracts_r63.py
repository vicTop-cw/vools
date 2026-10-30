# -*- coding: utf-8 -*-
"""security.py 契约测试 (Round 57)。

覆盖：SecurityLevel/SecurityPolicy/DEFAULT_POLICY、AuditLogger（默认目录/
写入 jsonl/查询过滤/summary）、SensitiveInfoDetector（scan/scan_file/redact/
redact_file）、InputValidator（check_command 全模式/sanitize_filename）、
SandboxEnhancer（validate_action/check_file_access/check_network_access/
apply_process_limits）、SecurityScanner 组合入口、单例与便捷函数。

BUG 佐证（未修）：
- BUG-S1: check_file_access 前缀匹配无路径分隔符边界 → "C:\\Windows" 会误拦
  "C:\\WindowsUpdate"；相对条目 ".git" abspath 后只拦 cwd 下的 .git。
- BUG-S2 (fail-open): allowed_paths=["C:\\data"] 时 "C:\\database" 前缀命中 →
  越界写路径被放行。
- BUG-S3: SecurityPolicy.level 完全未被 validate_action 消费 —— STRICT 级别
  （文档承诺只读+无网络+无子进程）不产生任何额外限制，纯死配置。
"""

import json
import logging

import pytest

from vools.actus import security as smod
from vools.actus.security import (
    AuditEvent,
    AuditLogger,
    DEFAULT_POLICY,
    InputValidator,
    SandboxEnhancer,
    SecurityLevel,
    SecurityPolicy,
    SecurityScanner,
    SensitiveInfoDetector,
    get_security_scanner,
    scan_action,
    scan_output,
)


@pytest.fixture
def audit_dir(tmp_path, monkeypatch):
    """把默认审计目录指向 tmp，避免污染真实 repo。"""
    import vools.actus.paths as pmod
    monkeypatch.setattr(pmod, 'meta_dir', lambda: str(tmp_path / '_meta'))
    return tmp_path / '_meta' / 'audit'


# ---------------------------------------------------------------- enums / policy

def test_security_levels_values():
    assert SecurityLevel.STRICT.value == 'strict'
    assert SecurityLevel.STANDARD.value == 'standard'
    assert SecurityLevel.RELAXED.value == 'relaxed'


def test_policy_defaults():
    p = SecurityPolicy()
    assert p.level is SecurityLevel.STANDARD
    assert p.allowed_paths == []
    assert p.blocked_paths == []
    assert p.allowed_hosts == []
    assert p.allow_subprocess is True
    assert p.allow_network is True
    assert p.max_file_size_mb == 100
    assert p.sensitive_patterns == []


def test_default_policy_shape():
    assert DEFAULT_POLICY.level is SecurityLevel.STANDARD
    assert '/etc' in DEFAULT_POLICY.blocked_paths
    assert 'C:\\Windows' in DEFAULT_POLICY.blocked_paths
    assert '.git' in DEFAULT_POLICY.blocked_paths
    assert len(DEFAULT_POLICY.sensitive_patterns) == 8


def test_audit_event_dataclass():
    e = AuditEvent(timestamp=1.0, action_id='a', event_type='run',
                   details={'k': 1}, success=True)
    assert e.success is True
    assert e.details == {'k': 1}


# ---------------------------------------------------------------- AuditLogger

class TestAuditLogger:
    def test_init_no_dir_created(self, tmp_path):
        d = tmp_path / 'audit'
        al = AuditLogger(str(d))
        assert al.log_dir == d
        assert not d.exists()  # 构造不建目录（第 16 轮审计）

    def test_default_log_dir_follows_meta_dir(self, audit_dir, tmp_path):
        al = AuditLogger()
        assert al.log_dir == audit_dir
        assert not audit_dir.exists()

    def test_log_creates_dir_and_jsonl(self, tmp_path):
        d = tmp_path / 'audit'
        al = AuditLogger(str(d))
        al.log('act.x', 'run', {'ok': 1}, True)
        files = list(d.glob('audit_*.jsonl'))
        assert len(files) == 1
        entry = json.loads(files[0].read_text(encoding='utf-8').strip())
        assert entry['action_id'] == 'act.x'
        assert entry['event_type'] == 'run'
        assert entry['details'] == {'ok': 1}
        assert entry['success'] is True
        assert entry['timestamp'] > 0

    def test_log_append_multiple(self, tmp_path):
        al = AuditLogger(str(tmp_path / 'a'))
        al.log('a', 'run', {}, True)
        al.log('b', 'violation', {}, False)
        f = next((tmp_path / 'a').glob('audit_*.jsonl'))
        lines = [json.loads(x) for x in f.read_text(encoding='utf-8').strip().splitlines()]
        assert [x['action_id'] for x in lines] == ['a', 'b']

    def test_get_events_filters(self, tmp_path):
        al = AuditLogger(str(tmp_path / 'a'))
        al.log('a', 'run', {}, True)
        al.log('b', 'violation', {}, False)
        assert [e.action_id for e in al.get_events(action_id='a')] == ['a']
        assert [e.action_id for e in al.get_events(event_type='violation')] == ['b']
        assert [e.action_id for e in al.get_events(since=0)] == ['a', 'b']
        # since 在未来 → 空
        assert al.get_events(since=9e12) == []

    def test_summary(self, tmp_path):
        al = AuditLogger(str(tmp_path / 'a'))
        al.log('a', 'run', {}, True)
        al.log('a', 'violation', {}, False)
        al.log('b', 'run', {}, True)
        s = al.summary()
        assert s['total_events'] == 3
        assert s['violations'] == 1
        assert s['by_type'] == {'run': 2, 'violation': 1}


# ---------------------------------------------------------------- SensitiveInfoDetector

class TestSensitiveInfoDetector:
    def test_default_patterns_compiled(self):
        d = SensitiveInfoDetector()
        assert len(d._compiled) == 8

    def test_custom_patterns(self):
        d = SensitiveInfoDetector([r'secret-\d+'])
        assert d.patterns == [r'secret-\d+']

    def test_scan_findings_fields(self):
        d = SensitiveInfoDetector([r'api[_-]?key\s*[:=]\s*\S+'])
        text = 'line1\napi_key = abc123\nend'
        f = d.scan(text)
        assert len(f) == 1
        assert f[0]['pattern_index'] == 0
        assert f[0]['match'] == 'api_key = abc123'
        assert f[0]['line'] == 2
        assert f[0]['start'] < f[0]['end']

    def test_scan_multiple_patterns(self):
        d = SensitiveInfoDetector()
        text = 'sk-' + 'a' * 25 + ' and ghp_' + 'b' * 36
        f = d.scan(text)
        idx = {x['pattern_index'] for x in f}
        assert idx == {5, 6}  # sk- 与 ghp_ 两条

    def test_scan_no_match(self):
        d = SensitiveInfoDetector([r'zzzzz'])
        assert d.scan('nothing here') == []

    def test_scan_file(self, tmp_path):
        p = tmp_path / 'secret.txt'
        p.write_text('token = supersecret9', encoding='utf-8')
        d = SensitiveInfoDetector()
        f = d.scan_file(str(p))
        assert len(f) >= 1

    def test_scan_file_missing_returns_empty(self, tmp_path, caplog):
        d = SensitiveInfoDetector()
        with caplog.at_level(logging.WARNING):
            assert d.scan_file(str(tmp_path / 'nope.txt')) == []
        assert '扫描文件失败' in caplog.text

    def test_redact(self):
        d = SensitiveInfoDetector([r'secret-\d+'])
        assert d.redact('x secret-42 y') == 'x ***REDACTED*** y'

    def test_redact_custom_replacement(self):
        d = SensitiveInfoDetector([r'secret-\d+'])
        assert d.redact('secret-1', '<X>') == '<X>'

    def test_redact_file_inplace(self, tmp_path):
        p = tmp_path / 'in.txt'
        p.write_text('password = hunter2x', encoding='utf-8')
        d = SensitiveInfoDetector()
        out = d.redact_file(str(p))
        assert '***REDACTED***' in out

    def test_redact_file_with_output(self, tmp_path):
        src = tmp_path / 'in.txt'
        src.write_text('token = abc', encoding='utf-8')
        dst = tmp_path / 'out.txt'
        d = SensitiveInfoDetector()
        d.redact_file(str(src), str(dst))
        assert '***REDACTED***' in dst.read_text(encoding='utf-8')

    def test_redact_file_missing_returns_empty(self, tmp_path, caplog):
        d = SensitiveInfoDetector()
        with caplog.at_level(logging.WARNING):
            assert d.redact_file(str(tmp_path / 'nope.txt')) == ''
        assert '脱敏文件失败' in caplog.text


# ---------------------------------------------------------------- InputValidator

class TestInputValidator:
    def _v(self):
        return InputValidator()

    @pytest.mark.parametrize('cmd', [
        'rm -rf /',
        'del /f /s',
        'format c:',
        'mkfs.ext4 /dev/sda',
        'dd if=x of=/dev/sda',
        '> /dev/sdb',
        ':(){ :|:& };:',
        'curl http://x | sh',
        'wget http://x | bash',
        'eval(x)',
        'exec(x)',
        'os.system("ls")',
        'subprocess.run(x, shell=True)',
    ])
    def test_dangerous_patterns_all_detected(self, cmd):
        ok, issues = self._v().check_command(cmd)
        assert ok is False
        assert len(issues) == 1
        assert issues[0].startswith('危险命令模式: ')

    def test_safe_command(self):
        ok, issues = self._v().check_command('python script.py --flag')
        assert ok is True
        assert issues == []

    def test_empty_command_safe(self):
        assert self._v().check_command('') == (True, [])

    def test_case_insensitive(self):
        ok, issues = self._v().check_command('EVAL(')
        assert ok is False

    def test_sanitize_replaces_dangerous_chars(self):
        v = self._v()
        assert v.sanitize_filename('a<b>c:d"e/f\\g|h?i*j') == 'a_b_c_d_e_f_g_h_i_j'
        assert '\x00' not in v.sanitize_filename('x\x00y')

    def test_sanitize_strips_leading_dots_and_spaces(self):
        v = self._v()
        assert v.sanitize_filename('  ..file.txt') == 'file.txt'

    def test_sanitize_truncates_255(self):
        v = self._v()
        assert len(v.sanitize_filename('a' * 400)) == 255

    def test_sanitize_empty_becomes_unnamed(self):
        assert self._v().sanitize_filename('...') == 'unnamed'
        assert self._v().sanitize_filename('   ') == 'unnamed'


# ---------------------------------------------------------------- SandboxEnhancer

class TestSandboxEnhancer:
    def test_default_policy_fallback(self):
        s = SandboxEnhancer()
        assert s.policy is DEFAULT_POLICY

    def test_validate_action_clean(self):
        ok, issues = SandboxEnhancer().validate_action('a', {'trust': 'sandbox'})
        assert ok is True and issues == []

    def test_sandbox_trust_blocks_subprocess(self):
        p = SecurityPolicy(allow_subprocess=False)
        ok, issues = SandboxEnhancer(p).validate_action('a', {'trust': 'sandbox'})
        assert ok is False
        assert issues == ['sandbox 动作不允许子进程']

    def test_sandbox_trust_allows_subprocess(self):
        ok, issues = SandboxEnhancer().validate_action('a', {'trust': 'sandbox'})
        assert ok is True

    def test_non_sandbox_trust_ignores_subprocess_flag(self):
        p = SecurityPolicy(allow_subprocess=False)
        ok, issues = SandboxEnhancer(p).validate_action('a', {'trust': 'audit'})
        assert ok is True

    @pytest.mark.parametrize('perm', ['network:http', 'net:connect'])
    def test_network_permission_rejected(self, perm):
        p = SecurityPolicy(allow_network=False)
        ok, issues = SandboxEnhancer(p).validate_action('a', {'permissions': [perm]})
        assert ok is False
        assert issues == [f'网络权限被拒绝: {perm}']

    @pytest.mark.parametrize('perm', ['subprocess:spawn', 'process:spawn'])
    def test_process_permission_rejected(self, perm):
        p = SecurityPolicy(allow_subprocess=False)
        ok, issues = SandboxEnhancer(p).validate_action('a', {'permissions': [perm]})
        assert ok is False
        assert issues == [f'子进程权限被拒绝: {perm}']

    def test_permissions_none_coerced(self):
        ok, issues = SandboxEnhancer().validate_action('a', {'permissions': None})
        assert ok is True

    def test_strict_level_ignored(self):
        # BUG-S3 佐证：level 字段完全不被消费，STRICT 不产生任何限制
        p = SecurityPolicy(level=SecurityLevel.STRICT, allow_network=True,
                           allow_subprocess=True)
        ok, issues = SandboxEnhancer(p).validate_action('a', {'permissions': ['net:connect']})
        assert ok is True and issues == []

    def test_check_file_access_blocked_absolute(self):
        ok, issues = SandboxEnhancer().check_file_access('C:\\Windows\\system32\\x')
        assert ok is False
        assert issues == ['访问被禁止的路径: C:\\Windows']

    def test_check_file_access_unblocked(self):
        ok, issues = SandboxEnhancer().check_file_access('C:\\work\\file.txt')
        assert ok is True and issues == []

    def test_check_file_access_prefix_false_positive(self):
        # BUG-S1 佐证：C:\Windows 前缀误拦 C:\WindowsUpdate
        ok, issues = SandboxEnhancer().check_file_access('C:\\WindowsUpdate\\a.txt')
        assert ok is False
        assert issues == ['访问被禁止的路径: C:\\Windows']

    def test_check_file_access_relative_blocked_entry_only_matches_cwd(self, monkeypatch, tmp_path):
        # BUG-S1 补充：'.git' 被解析为 cwd 下的 .git，其它目录里的 .git 不拦
        monkeypatch.chdir(tmp_path)
        s = SandboxEnhancer()
        ok, _ = s.check_file_access(str(tmp_path / 'repo' / '.git' / 'config'))
        assert ok is True  # 只拦 <cwd>\.git

    def test_write_outside_whitelist_rejected(self):
        p = SecurityPolicy(allowed_paths=['C:\\allowed'])
        ok, issues = SandboxEnhancer(p).check_file_access('C:\\elsewhere\\f', 'write')
        assert ok is False
        assert issues == ['写入路径不在白名单: C:\\elsewhere\\f']

    def test_write_inside_whitelist_allowed(self):
        p = SecurityPolicy(allowed_paths=['C:\\allowed'])
        ok, issues = SandboxEnhancer(p).check_file_access('C:\\allowed\\f', 'write')
        assert ok is True

    def test_write_prefix_false_accept(self):
        # BUG-S2 佐证（fail-open）：C:\data 前缀放过 C:\database
        p = SecurityPolicy(allowed_paths=['C:\\data'])
        ok, issues = SandboxEnhancer(p).check_file_access('C:\\database\\secret', 'write')
        assert ok is True  # 前缀匹配无分隔符边界 → 越界写被放行

    def test_read_ignores_whitelist(self):
        p = SecurityPolicy(allowed_paths=['C:\\allowed'])
        ok, _ = SandboxEnhancer(p).check_file_access('C:\\elsewhere\\f', 'read')
        assert ok is True

    @pytest.mark.parametrize('mode', ['write', 'append', 'delete'])
    def test_write_modes_covered(self, mode):
        p = SecurityPolicy(allowed_paths=['C:\\allowed'])
        ok, _ = SandboxEnhancer(p).check_file_access('C:\\elsewhere', mode)
        assert ok is False

    def test_network_disabled(self):
        p = SecurityPolicy(allow_network=False)
        ok, issues = SandboxEnhancer(p).check_network_access('a.com')
        assert ok is False
        assert issues == ['网络访问被策略禁止']

    def test_network_host_not_in_whitelist(self):
        p = SecurityPolicy(allowed_hosts=['a.com'])
        ok, issues = SandboxEnhancer(p).check_network_access('b.com')
        assert ok is False
        assert issues == ['主机不在白名单: b.com']

    def test_network_host_in_whitelist(self):
        p = SecurityPolicy(allowed_hosts=['a.com'])
        ok, _ = SandboxEnhancer(p).check_network_access('a.com')
        assert ok is True

    def test_network_no_whitelist_open(self):
        ok, _ = SandboxEnhancer().check_network_access('anything.example')
        assert ok is True

    def test_apply_process_limits_no_raise_on_windows(self):
        # Windows 无 resource 模块 → ImportError 被吞
        SandboxEnhancer().apply_process_limits()


# ---------------------------------------------------------------- SecurityScanner

class TestSecurityScanner:
    def test_scan_action_clean(self, tmp_path):
        s = SecurityScanner(SecurityPolicy())
        s.audit = AuditLogger(str(tmp_path / 'audit'))
        r = s.scan_action('act.a', {'trust': 'audit'}, code='print(1)')
        assert r == {'action_id': 'act.a', 'safe': True, 'issues': [],
                     'warnings': [], 'sensitive_findings': []}

    def test_scan_action_dangerous_code(self, tmp_path):
        s = SecurityScanner(SecurityPolicy())
        s.audit = AuditLogger(str(tmp_path / 'audit'))
        r = s.scan_action('act.a', {'trust': 'audit'}, code='eval(x)')
        assert r['safe'] is False
        assert len(r['issues']) == 1

    def test_scan_action_sensitive_findings(self, tmp_path):
        s = SecurityScanner(SecurityPolicy())
        s.audit = AuditLogger(str(tmp_path / 'audit'))
        code = 'KEY = "sk-' + 'a' * 25 + '"'
        r = s.scan_action('act.a', {'trust': 'audit'}, code=code)
        assert r['sensitive_findings']
        assert r['warnings'] == ['发现 1 处敏感信息']
        assert r['safe'] is True  # 敏感信息只是 warning

    def test_scan_action_permission_violation(self, tmp_path):
        p = SecurityPolicy(allow_network=False)
        s = SecurityScanner(p)
        s.audit = AuditLogger(str(tmp_path / 'audit'))
        r = s.scan_action('act.a', {'permissions': ['net:connect']})
        assert r['safe'] is False
        assert '网络权限被拒绝: net:connect' in r['issues']

    def test_scan_action_audits_result(self, tmp_path):
        al = AuditLogger(str(tmp_path / 'audit'))
        s = SecurityScanner(SecurityPolicy())
        s.audit = al
        s.scan_action('act.a', {'trust': 'audit'}, code='eval(x)')
        evs = al.get_events(event_type='security_scan')
        assert len(evs) == 1
        assert evs[0].success is False

    def test_scan_text_output_clean(self, tmp_path):
        s = SecurityScanner(SecurityPolicy())
        s.audit = AuditLogger(str(tmp_path / 'audit'))
        r = s.scan_text_output('hello world')
        assert r == {'has_sensitive': False, 'findings': [], 'redacted': 'hello world'}

    def test_scan_text_output_sensitive(self, tmp_path):
        al = AuditLogger(str(tmp_path / 'audit'))
        s = SecurityScanner(SecurityPolicy())
        s.audit = al
        text = 'token = supersecret'
        r = s.scan_text_output(text, 'act.a')
        assert r['has_sensitive'] is True
        assert r['findings']
        assert '***REDACTED***' in r['redacted']
        evs = al.get_events(event_type='sensitive_output')
        assert len(evs) == 1
        assert evs[0].success is False

    def test_summary(self, tmp_path):
        s = SecurityScanner(SecurityPolicy())
        s.audit = AuditLogger(str(tmp_path / 'audit'))
        s.scan_text_output('clean', 'act.a')
        summ = s.summary()
        assert summ['policy_level'] == 'standard'
        assert summ['audit']['total_events'] == 0  # clean 文本不记审计


# ---------------------------------------------------------------- singleton / convenience

def test_get_security_scanner_singleton(monkeypatch, tmp_path):
    import vools.actus.paths as pmod
    monkeypatch.setattr(pmod, 'meta_dir', lambda: str(tmp_path / '_meta'))
    monkeypatch.setattr(smod, '_scanner', None)
    a = get_security_scanner()
    b = get_security_scanner()
    assert a is b
    assert isinstance(a, SecurityScanner)


def test_scan_action_convenience(monkeypatch, tmp_path):
    import vools.actus.paths as pmod
    monkeypatch.setattr(pmod, 'meta_dir', lambda: str(tmp_path / '_meta'))
    monkeypatch.setattr(smod, '_scanner', None)
    r = scan_action('act.a', {'trust': 'audit'})
    assert r['action_id'] == 'act.a'
    assert r['safe'] is True


def test_scan_output_convenience(monkeypatch, tmp_path):
    import vools.actus.paths as pmod
    monkeypatch.setattr(pmod, 'meta_dir', lambda: str(tmp_path / '_meta'))
    monkeypatch.setattr(smod, '_scanner', None)
    r = scan_output('nothing sensitive here')
    assert r['has_sensitive'] is False


def test_all_exports():
    assert 'SecurityScanner' in smod.__all__
    assert 'get_security_scanner' in smod.__all__
    assert 'scan_action' in smod.__all__
    assert 'scan_output' in smod.__all__
