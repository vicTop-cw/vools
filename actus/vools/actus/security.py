"""security.py — 安全加固模块 (Phase O-P)。

提供 Actus 运行时的安全增强功能：
- 动作权限验证（基于 trust level + scope）
- 沙箱隔离增强（文件系统/网络/进程限制）
- 敏感信息检测与脱敏
- 审计日志记录
- 输入验证与注入防护
"""

import os
import re
import json
import time
import logging
import hashlib
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class SecurityLevel(Enum):
    """安全级别。"""
    STRICT = "strict"      # 最严格：只读 + 无网络 + 无子进程
    STANDARD = "standard"  # 标准：限制写范围 + 网络白名单
    RELAXED = "relaxed"    # 宽松：基本检查


@dataclass
class SecurityPolicy:
    """安全策略配置。"""
    level: SecurityLevel = SecurityLevel.STANDARD
    allowed_paths: List[str] = field(default_factory=list)      # 允许写入的路径
    blocked_paths: List[str] = field(default_factory=list)     # 禁止访问的路径
    allowed_hosts: List[str] = field(default_factory=list)     # 网络白名单
    allow_subprocess: bool = True                              # 是否允许子进程
    allow_network: bool = True                                 # 是否允许网络
    max_file_size_mb: int = 100                                # 最大文件大小
    sensitive_patterns: List[str] = field(default_factory=list) # 敏感信息模式


@dataclass
class AuditEvent:
    """审计事件。"""
    timestamp: float
    action_id: str
    event_type: str          # run / file_access / network / subprocess / violation
    details: Dict
    success: bool


# ── 默认安全策略 ──────────────────────────────────────────────────────────

DEFAULT_POLICY = SecurityPolicy(
    level=SecurityLevel.STANDARD,
    allowed_paths=[],          # 空 = 不限制（仅记录）
    blocked_paths=[
        "/etc", "/sys", "/proc", "/dev",
        "C:\\Windows", "C:\\Program Files",
        ".git", ".ssh", ".aws", ".azure",
    ],
    allowed_hosts=[],
    allow_subprocess=True,
    allow_network=True,
    max_file_size_mb=100,
    sensitive_patterns=[
        r"api[_-]?key\s*[:=]\s*\S+",
        r"secret\s*[:=]\s*\S+",
        r"password\s*[:=]\s*\S+",
        r"token\s*[:=]\s*\S+",
        r"BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY",
        r"sk-[a-zA-Z0-9]{20,}",           # API key 格式
        r"ghp_[a-zA-Z0-9]{36}",          # GitHub PAT
        r"AKIA[0-9A-Z]{16}",              # AWS Access Key
    ],
)


# ── 审计日志 ──────────────────────────────────────────────────────────────

class AuditLogger:
    """审计日志记录器。"""

    def __init__(self, log_dir: str = None):
        if log_dir is None:
            log_dir = os.path.join(os.getcwd(), "_meta", "audit")
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._events: List[AuditEvent] = []

    def log(self, action_id: str, event_type: str, details: Dict, success: bool = True):
        """记录审计事件。"""
        event = AuditEvent(
            timestamp=time.time(),
            action_id=action_id,
            event_type=event_type,
            details=details,
            success=success,
        )
        self._events.append(event)
        self._write_event(event)

    def _write_event(self, event: AuditEvent):
        """写入审计日志文件。"""
        log_file = self.log_dir / f"audit_{time.strftime('%Y%m%d')}.jsonl"
        entry = {
            "timestamp": event.timestamp,
            "action_id": event.action_id,
            "event_type": event.event_type,
            "details": event.details,
            "success": event.success,
        }
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def get_events(self, action_id: str = None, event_type: str = None,
                   since: float = None) -> List[AuditEvent]:
        """查询审计事件。"""
        events = self._events
        if action_id:
            events = [e for e in events if e.action_id == action_id]
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        if since:
            events = [e for e in events if e.timestamp >= since]
        return events

    def summary(self) -> Dict:
        """审计摘要。"""
        total = len(self._events)
        violations = len([e for e in self._events if not e.success])
        by_type: Dict[str, int] = {}
        for e in self._events:
            by_type[e.event_type] = by_type.get(e.event_type, 0) + 1
        return {
            "total_events": total,
            "violations": violations,
            "by_type": by_type,
        }


# ── 敏感信息检测 ──────────────────────────────────────────────────────────

class SensitiveInfoDetector:
    """敏感信息检测器。"""

    def __init__(self, patterns: List[str] = None):
        self.patterns = patterns or DEFAULT_POLICY.sensitive_patterns
        self._compiled = [re.compile(p, re.IGNORECASE) for p in self.patterns]

    def scan(self, text: str) -> List[Dict]:
        """扫描文本中的敏感信息。"""
        findings = []
        for i, pattern in enumerate(self._compiled):
            for match in pattern.finditer(text):
                findings.append({
                    "pattern_index": i,
                    "pattern": self.patterns[i],
                    "match": match.group(),
                    "start": match.start(),
                    "end": match.end(),
                    "line": text[:match.start()].count("\n") + 1,
                })
        return findings

    def scan_file(self, file_path: str) -> List[Dict]:
        """扫描文件中的敏感信息。"""
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            return self.scan(content)
        except Exception as e:
            logger.warning(f"扫描文件失败 {file_path}: {e}")
            return []

    def redact(self, text: str, replacement: str = "***REDACTED***") -> str:
        """脱敏处理。"""
        result = text
        for pattern in self._compiled:
            result = pattern.sub(replacement, result)
        return result

    def redact_file(self, file_path: str, output_path: str = None) -> str:
        """脱敏文件内容。"""
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            redacted = self.redact(content)
            if output_path:
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(redacted)
            return redacted
        except Exception as e:
            logger.warning(f"脱敏文件失败 {file_path}: {e}")
            return ""


# ── 输入验证与注入防护 ────────────────────────────────────────────────────

class InputValidator:
    """输入验证器。"""

    # 危险命令模式
    DANGEROUS_PATTERNS = [
        r"rm\s+-rf\s+/",
        r"del\s+/f\s+/s",
        r"format\s+[a-z]:",
        r"mkfs\.",
        r"dd\s+if=.*of=/dev/",
        r">\s*/dev/sd",
        r":\(\)\s*\{\s*:\s*\|:\s*&\s*\}\s*;",  # fork bomb
        r"curl.*\|\s*(ba)?sh",                  # pipe to shell
        r"wget.*\|\s*(ba)?sh",
        r"eval\s*\(",
        r"exec\s*\(",
        r"os\.system\s*\(",
        r"subprocess\..*shell\s*=\s*True",
    ]

    # 路径遍历模式
    PATH_TRAVERSAL = [
        r"\.\./",
        r"\.\.\\",
        r"%2e%2e%2f",
        r"%2e%2e/",
        r"\.\.%2f",
    ]

    def __init__(self):
        self._dangerous = [re.compile(p, re.IGNORECASE) for p in self.DANGEROUS_PATTERNS]
        self._traversal = [re.compile(p, re.IGNORECASE) for p in self.PATH_TRAVERSAL]

    def check_command(self, command: str) -> Tuple[bool, List[str]]:
        """检查命令是否安全。"""
        issues = []
        for pattern in self._dangerous:
            if pattern.search(command):
                issues.append(f"危险命令模式: {pattern.pattern}")
        return len(issues) == 0, issues

    def check_path(self, path: str, base_dir: str = None) -> Tuple[bool, List[str]]:
        """检查路径是否安全。"""
        issues = []
        for pattern in self._traversal:
            if pattern.search(path):
                issues.append(f"路径遍历: {pattern.pattern}")

        if base_dir:
            try:
                resolved = Path(path).resolve()
                base = Path(base_dir).resolve()
                if not str(resolved).startswith(str(base)):
                    issues.append(f"路径越界: {path} 不在 {base_dir} 内")
            except Exception:
                issues.append(f"无法解析路径: {path}")

        return len(issues) == 0, issues

    def sanitize_filename(self, filename: str) -> str:
        """清理文件名。"""
        # 移除路径分隔符和危险字符
        sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", filename)
        # 移除前导空格和点
        sanitized = sanitized.lstrip(" .")
        # 限制长度
        if len(sanitized) > 255:
            sanitized = sanitized[:255]
        return sanitized or "unnamed"


# ── 沙箱增强 ──────────────────────────────────────────────────────────────

class SandboxEnhancer:
    """沙箱增强器。"""

    def __init__(self, policy: SecurityPolicy = None):
        self.policy = policy or DEFAULT_POLICY

    def validate_action(self, action_id: str, action_meta: Dict) -> Tuple[bool, List[str]]:
        """验证动作是否符合安全策略。"""
        issues = []

        # 检查 trust level
        trust = action_meta.get("trust", "audit")
        if trust == "sandbox":
            # sandbox 级别动作需要额外限制
            if not self.policy.allow_subprocess:
                issues.append("sandbox 动作不允许子进程")

        # 检查 permissions
        permissions = action_meta.get("permissions", [])
        for perm in permissions:
            if perm.startswith("network:") and not self.policy.allow_network:
                issues.append(f"网络权限被拒绝: {perm}")
            if perm.startswith("subprocess:") and not self.policy.allow_subprocess:
                issues.append(f"子进程权限被拒绝: {perm}")

        return len(issues) == 0, issues

    def check_file_access(self, path: str, mode: str = "read") -> Tuple[bool, List[str]]:
        """检查文件访问是否允许。"""
        issues = []
        # 使用 normpath 而非 resolve，避免 Windows 上路径解析问题
        resolved = os.path.normpath(os.path.abspath(path))

        # 检查禁止路径
        for blocked in self.policy.blocked_paths:
            blocked_norm = os.path.normpath(os.path.abspath(blocked))
            if resolved.startswith(blocked_norm) or resolved.startswith(blocked):
                issues.append(f"访问被禁止的路径: {blocked}")

        # 检查允许路径（写操作）
        if mode in ("write", "append", "delete") and self.policy.allowed_paths:
            allowed = False
            for p in self.policy.allowed_paths:
                p_norm = os.path.normpath(os.path.abspath(p))
                if resolved.startswith(p_norm) or resolved.startswith(p):
                    allowed = True
                    break
            if not allowed:
                issues.append(f"写入路径不在白名单: {path}")

        return len(issues) == 0, issues

    def check_network_access(self, host: str) -> Tuple[bool, List[str]]:
        """检查网络访问是否允许。"""
        issues = []
        if not self.policy.allow_network:
            issues.append("网络访问被策略禁止")
        elif self.policy.allowed_hosts:
            if host not in self.policy.allowed_hosts:
                issues.append(f"主机不在白名单: {host}")
        return len(issues) == 0, issues

    def apply_process_limits(self):
        """应用进程级限制。"""
        try:
            import resource
            # 限制内存 (512MB)
            resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
            # 限制 CPU 时间 (60s)
            resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
            # 限制文件数
            resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
            # 限制子进程数
            resource.setrlimit(resource.RLIMIT_NPROC, (16, 16))
        except (ImportError, ValueError):
            pass  # Windows 或不支持


# ── 安全扫描器（组合入口） ────────────────────────────────────────────────

class SecurityScanner:
    """安全扫描器 — 组合所有安全功能。"""

    def __init__(self, policy: SecurityPolicy = None):
        self.policy = policy or DEFAULT_POLICY
        self.audit = AuditLogger()
        self.detector = SensitiveInfoDetector(self.policy.sensitive_patterns)
        self.validator = InputValidator()
        self.sandbox = SandboxEnhancer(self.policy)

    def scan_action(self, action_id: str, action_meta: Dict,
                     code: str = None) -> Dict:
        """全面扫描动作安全性。"""
        result = {
            "action_id": action_id,
            "safe": True,
            "issues": [],
            "warnings": [],
            "sensitive_findings": [],
        }

        # 1. 权限验证
        ok, issues = self.sandbox.validate_action(action_id, action_meta)
        if not ok:
            result["safe"] = False
            result["issues"].extend(issues)

        # 2. 代码扫描
        if code:
            # 敏感信息
            findings = self.detector.scan(code)
            if findings:
                result["sensitive_findings"] = findings
                result["warnings"].append(f"发现 {len(findings)} 处敏感信息")

            # 危险命令
            ok, issues = self.validator.check_command(code)
            if not ok:
                result["safe"] = False
                result["issues"].extend(issues)

        # 3. 记录审计
        self.audit.log(action_id, "security_scan", {
            "safe": result["safe"],
            "issues": result["issues"],
            "warnings": result["warnings"],
        }, result["safe"])

        return result

    def scan_text_output(self, text: str, action_id: str = "") -> Dict:
        """扫描输出文本中的敏感信息。"""
        findings = self.detector.scan(text)
        if findings:
            self.audit.log(action_id, "sensitive_output", {
                "count": len(findings),
                "patterns": [f["pattern"] for f in findings],
            }, False)
        return {
            "has_sensitive": len(findings) > 0,
            "findings": findings,
            "redacted": self.detector.redact(text) if findings else text,
        }

    def summary(self) -> Dict:
        """安全扫描摘要。"""
        return {
            "audit": self.audit.summary(),
            "policy_level": self.policy.level.value,
        }


# ── 单例 ──────────────────────────────────────────────────────────────────

_scanner: Optional[SecurityScanner] = None


def get_security_scanner() -> SecurityScanner:
    """获取安全扫描器单例。"""
    global _scanner
    if _scanner is None:
        _scanner = SecurityScanner()
    return _scanner


def scan_action(action_id: str, action_meta: Dict, code: str = None) -> Dict:
    """便捷函数：扫描动作安全性。"""
    return get_security_scanner().scan_action(action_id, action_meta, code)


def scan_output(text: str, action_id: str = "") -> Dict:
    """便捷函数：扫描输出文本。"""
    return get_security_scanner().scan_text_output(text, action_id)


__all__ = [
    'AuditEvent',
    'AuditLogger',
    'DEFAULT_POLICY',
    'InputValidator',
    'SandboxEnhancer',
    'SecurityLevel',
    'SecurityPolicy',
    'SecurityScanner',
    'SensitiveInfoDetector',
    'get_security_scanner',
    'logger',
    'scan_action',
    'scan_output'
]
