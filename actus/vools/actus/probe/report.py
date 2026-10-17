"""probe/report.py — ProbeReport 组装与摘要渲染。

对应 PROBE_PLAN.md §3.1 架构里的「vools.actus.probe.report — ProbeReport 组装」层：
把各探测器产出的 ProbeItem 列表 + 四个维度 dict 汇总成一份可序列化报告，
并提供人类可读摘要。__init__.py 的 probe() 负责采集，本模块负责组装/呈现。
"""


__all__ = [
    "ProbeReport",
    "format_summary",
    "to_dict",
    "add_item",
    "add_items",
    "build_summary",
]

__all__ = ['ProbeReport', 'format_summary']

import time
from typing import Any, Dict

from .base import ProbeItem


class ProbeReport:
    """探针完整报告。"""

    def __init__(self, timestamp: float = None, elapsed_ms: float = 0,
                 platform_info: dict = None, permissions_info: dict = None,
                 environment_info: dict = None, resources_info: dict = None,
                 items: list = None, summary: dict = None):
        self.timestamp = timestamp or time.time()
        self.elapsed_ms = elapsed_ms
        self.platform_info = platform_info or {}
        self.permissions_info = permissions_info or {}
        self.environment_info = environment_info or {}
        self.resources_info = resources_info or {}
        self.items = items or []
        self.summary = summary or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "elapsed_ms": round(self.elapsed_ms, 1),
            "platform": self.platform_info,
            "permissions": self.permissions_info,
            "environment": self.environment_info,
            "resources": self.resources_info,
            "items": [item.to_dict() for item in self.items],
            "summary": self.summary,
        }

    def add_item(self, item: ProbeItem):
        self.items.append(item)

    def add_items(self, items: list):
        self.items.extend(items)

    def build_summary(self):
        """构建汇总信息。"""
        available_count = sum(1 for i in self.items if i.available)
        total_count = len(self.items)
        by_category = {}
        for item in self.items:
            cat = item.category or "unknown"
            if cat not in by_category:
                by_category[cat] = {"total": 0, "available": 0}
            by_category[cat]["total"] += 1
            if item.available:
                by_category[cat]["available"] += 1

        # 提取关键工具状态
        key_tools = {}
        for item in self.items:
            if item.category in ("system_tools", "compilers", "runtimes") and item.available:
                key_tools[item.name] = {"version": item.version, "path": item.path}

        self.summary = {
            "total_items": total_count,
            "available_items": available_count,
            "unavailable_items": total_count - available_count,
            "by_category": by_category,
            "key_tools": key_tools,
        }
        return self.summary


def format_summary(report: ProbeReport) -> str:
    """格式化输出摘要。"""
    lines = []
    lines.append("=" * 60)
    lines.append("vools probe report")
    lines.append("=" * 60)
    lines.append("Timestamp: %.0f" % report.timestamp)
    lines.append("Elapsed: %.1fms" % report.elapsed_ms)
    lines.append("")

    # 平台信息
    p = report.platform_info
    if p:
        lines.append("[Platform]")
        lines.append("  OS: %s %s (%s)" % (p.get('os'), p.get('os_release'), p.get('arch')))
        lines.append("  Python: %s @ %s" % (p.get('python_version'), p.get('python_executable')))
        if p.get("linux_distro"):
            d = p["linux_distro"]
            lines.append("  Distro: %s %s" % (d.get('name', d.get('id', '?')), d.get('version', '')))
        if p.get("windows_version"):
            lines.append("  Windows: %s" % p['windows_version'])
        lines.append("")

    # 权限信息
    perm = report.permissions_info
    if perm:
        lines.append("[Permissions]")
        lines.append("  User: %s (uid=%s)" % (perm['user'].get('name', '?'), perm['user'].get('uid', '?')))
        lines.append("  Admin: %s" % perm['is_admin'])
        lines.append("  Can install: %s" % perm['can_install_system_wide'])
        lines.append("")

    # 资源信息
    res = report.resources_info
    if res:
        lines.append("[Resources]")
        cpu = res.get("cpu", {})
        mem = res.get("memory", {})
        if cpu:
            lines.append("  CPU: %s cores (%s)" % (cpu.get('count_logical', '?'), cpu.get('model', cpu.get('platform', ''))))
        if mem:
            lines.append("  Memory: %sMB total, %sMB available (%s%% used)" % (
                mem.get('total_mb', '?'), mem.get('available_mb', '?'), mem.get('used_percent', '?')))
        lines.append("")

    # 环境信息
    env = report.environment_info
    if env:
        lines.append("[Environment]")
        lines.append("  PATH dirs: %s" % env.get('path_count', '?'))
        venv = env.get("virtual_env", {})
        if venv.get("active"):
            lines.append("  Virtual Env: %s" % venv.get('path', ''))
        conda = env.get("conda_env", {})
        if conda.get("active"):
            lines.append("  Conda Env: %s" % conda.get('name', ''))
        secrets = env.get("secret_keys_found", {})
        if secrets:
            lines.append("  Secret keys found: %s" % ', '.join(secrets.keys()))
        lines.append("")

    # 汇总
    s = report.summary
    if s:
        lines.append("[Summary]")
        lines.append("  Total items: %s" % s['total_items'])
        lines.append("  Available: %s" % s['available_items'])
        lines.append("  Unavailable: %s" % s['unavailable_items'])
        lines.append("")

        # 按分类显示
        lines.append("[By Category]")
        for cat, counts in s.get("by_category", {}).items():
            lines.append("  %s: %s/%s" % (cat, counts['available'], counts['total']))
        lines.append("")

        # 关键工具
        lines.append("[Key Tools]")
        for name, info in sorted(s.get("key_tools", {}).items()):
            ver = info.get("version", "")
            lines.append("  [x] %s: %s" % (name, ver))

    lines.append("=" * 60)
    return "\n".join(lines)

