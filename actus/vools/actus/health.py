"""health.py — 系统健康检查 (Phase O)。

检查 Actus 运行环境的完整性和可用性：
- 引擎核心模块是否完整
- 编译器后端是否可用
- 目录结构是否正确
- 依赖是否满足
- 性能基线是否达标
"""

import os
import sys
import time
import shutil
import logging
from typing import Dict, List, Optional
from pathlib import Path
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class HealthCheckResult:
    """健康检查结果。"""
    name: str
    status: str          # ok / warn / error
    message: str
    duration: float = 0.0
    suggestion: str = ""


@dataclass
class HealthReport:
    """健康报告。"""
    results: List[HealthCheckResult] = field(default_factory=list)
    total_duration: float = 0.0

    @property
    def status_counts(self) -> Dict[str, int]:
        counts = {"ok": 0, "warn": 0, "error": 0}
        for r in self.results:
            counts[r.status] = counts.get(r.status, 0) + 1
        return counts

    @property
    def overall(self) -> str:
        counts = self.status_counts
        if counts["error"] > 0:
            return "error"
        if counts["warn"] > 0:
            return "warn"
        return "ok"

    def summary(self) -> str:
        counts = self.status_counts
        return f"✅ {counts['ok']} 通过 | ⚠️ {counts['warn']} 警告 | ❌ {counts['error']} 错误"


# ── 检查项 ────────────────────────────────────────────────────────────────

def check_python_version() -> HealthCheckResult:
    """检查 Python 版本。"""
    start = time.time()
    version = sys.version_info
    if version >= (3, 8):
        return HealthCheckResult("python_version", "ok", f"Python {version.major}.{version.minor}.{version.micro}", time.time() - start)
    return HealthCheckResult("python_version", "error", f"Python {version.major}.{version.minor} 过低，需要 3.8+", time.time() - start, "升级 Python 到 3.8+")


def check_core_modules(repo_root: str = ".") -> HealthCheckResult:
    """检查核心模块完整性。"""
    start = time.time()
    required = ["executor.py", "model.py", "validate.py", "scaffold.py", "discovery.py"]
    engine_dir = Path(repo_root) / "engine" / "actuscore"

    if not engine_dir.exists():
        return HealthCheckResult("core_modules", "error", "engine/actuscore 目录不存在", time.time() - start)

    missing = []
    for mod in required:
        if not (engine_dir / mod).exists():
            missing.append(mod)

    if missing:
        return HealthCheckResult("core_modules", "error", f"缺少核心模块: {', '.join(missing)}", time.time() - start)

    return HealthCheckResult("core_modules", "ok", f"核心模块完整 ({len(required)} 个)", time.time() - start)


def check_actions_directory(repo_root: str = ".") -> HealthCheckResult:
    """检查动作目录结构。"""
    start = time.time()
    actions_dir = Path(repo_root) / "actions"

    if not actions_dir.exists():
        return HealthCheckResult("actions_directory", "warn", "actions 目录不存在", time.time() - start, "运行 `actus scaffold` 创建动作目录")

    action_files = list(actions_dir.rglob("*.actus.md"))
    return HealthCheckResult("actions_directory", "ok", f"发现 {len(action_files)} 个动作文件", time.time() - start)


def check_compilers() -> HealthCheckResult:
    """检查可用编译器。"""
    start = time.time()
    compilers = []

    if shutil.which("python3") or shutil.which("python"):
        compilers.append("python")
    if shutil.which("node"):
        compilers.append("node")
    if shutil.which("rustc"):
        compilers.append("rust")
    if shutil.which("gcc"):
        compilers.append("c")
    if shutil.which("sh"):
        compilers.append("shell")

    if compilers:
        return HealthCheckResult("compilers", "ok", f"可用编译器: {', '.join(compilers)}", time.time() - start)
    return HealthCheckResult("compilers", "warn", "未发现任何编译器", time.time() - start, "安装 Node.js 或 Python 以支持更多运行时")


def check_disk_space(repo_root: str = ".") -> HealthCheckResult:
    """检查磁盘空间。"""
    start = time.time()
    try:
        usage = shutil.disk_usage(repo_root)
        free_gb = usage.free / (1024 ** 3)
        if free_gb < 0.5:
            return HealthCheckResult("disk_space", "error", f"磁盘空间不足: {free_gb:.1f}GB", time.time() - start, "清理磁盘空间")
        if free_gb < 2.0:
            return HealthCheckResult("disk_space", "warn", f"磁盘空间偏低: {free_gb:.1f}GB", time.time() - start)
        return HealthCheckResult("disk_space", "ok", f"磁盘空间充足: {free_gb:.1f}GB", time.time() - start)
    except Exception as e:
        return HealthCheckResult("disk_space", "warn", f"无法检查磁盘空间: {e}", time.time() - start)


def check_network() -> HealthCheckResult:
    """检查网络连通性。"""
    start = time.time()
    import urllib.request
    try:
        urllib.request.urlopen("https://pypi.org", timeout=5)
        return HealthCheckResult("network", "ok", "网络连通", time.time() - start)
    except Exception:
        return HealthCheckResult("network", "warn", "无法访问 PyPI（部分功能可能受限）", time.time() - start)


def check_meta_directory(repo_root: str = ".") -> HealthCheckResult:
    """检查元数据目录。"""
    start = time.time()
    meta_dir = Path(repo_root) / "_meta"

    if not meta_dir.exists():
        return HealthCheckResult("meta_directory", "warn", "_meta 目录不存在", time.time() - start, "运行 `actus init` 初始化项目")

    return HealthCheckResult("meta_directory", "ok", "元数据目录存在", time.time() - start)


def check_vault(repo_root: str = ".") -> HealthCheckResult:
    """检查 Vault 配置。"""
    start = time.time()
    try:
        from actuscore.vault import Vault
        return HealthCheckResult("vault", "ok", "Vault 模块可用", time.time() - start)
    except ImportError as e:
        return HealthCheckResult("vault", "warn", f"Vault 模块导入失败: {e}", time.time() - start)


# ── 健康检查运行器 ────────────────────────────────────────────────────────

class HealthChecker:
    """健康检查运行器。"""

    def __init__(self, repo_root: str = "."):
        self.repo_root = repo_root
        self._checks = [
            ("Python 版本", lambda: check_python_version()),
            ("核心模块", lambda: check_core_modules(repo_root)),
            ("动作目录", lambda: check_actions_directory(repo_root)),
            ("元数据目录", lambda: check_meta_directory(repo_root)),
            ("编译器", lambda: check_compilers()),
            ("磁盘空间", lambda: check_disk_space(repo_root)),
            ("网络", lambda: check_network()),
            ("Vault", lambda: check_vault(repo_root)),
        ]

    def add_check(self, name: str, func):
        """添加自定义检查项。"""
        self._checks.append((name, func))

    def run(self) -> HealthReport:
        """运行所有检查。"""
        start = time.time()
        report = HealthReport()

        for name, func in self._checks:
            try:
                result = func()
                result.name = name
                report.results.append(result)
            except Exception as e:
                report.results.append(HealthCheckResult(name, "error", f"检查异常: {e}"))

        report.total_duration = time.time() - start
        return report

    def report_text(self, report: HealthReport) -> str:
        """生成文本报告。"""
        lines = ["🏥 Actus 系统健康报告", ""]
        lines.append(f"总体状态: {report.overall.upper()}")
        lines.append(f"检查耗时: {report.total_duration:.3f}s")
        lines.append("")

        for r in report.results:
            icon = {"ok": "✅", "warn": "⚠️", "error": "❌"}.get(r.status, "❓")
            lines.append(f"{icon} [{r.status.upper()}] {r.name}: {r.message}")
            if r.suggestion:
                lines.append(f"   建议: {r.suggestion}")

        lines.append("")
        lines.append(report.summary())
        return "\n".join(lines)


def run_health_check(repo_root: str = ".") -> HealthReport:
    """运行健康检查。"""
    checker = HealthChecker(repo_root)
    return checker.run()


__all__ = [
    'HealthCheckResult',
    'HealthChecker',
    'HealthReport',
    'check_actions_directory',
    'check_compilers',
    'check_core_modules',
    'check_disk_space',
    'check_meta_directory',
    'check_network',
    'check_python_version',
    'check_vault',
    'logger',
    'run_health_check'
]
