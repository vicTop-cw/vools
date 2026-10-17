"""probe/actions.py — 动作依赖分析。

扫描动作目录，提取依赖信息。
"""


__all__ = [
    "ActionsProber",
    "probe",
]

import os
import sys
from .base import Prober, ProbeItem

# 动作依赖映射：动作使用的工具/库 → 依赖类型
ACTION_DEPENDENCY_MAP = {
    "screenshot": {"tools": ["scrot", "import", "PowerShell"], "packages": ["Pillow", "mss"]},
    "clipboard": {"tools": ["clip", "pbcopy", "PowerShell"], "packages": ["pyperclip", "pywin32"]},
    "convert": {"tools": [], "packages": ["Pillow", "opencv-python"]},
    "json": {"tools": ["jq", "yq"], "packages": []},
    "http": {"tools": ["curl", "wget"], "packages": ["requests", "httpx"]},
    "dialog": {"tools": [], "packages": ["pywin32", "tkinter"]},
    "git": {"tools": ["git"], "packages": ["GitPython"]},
    "sftp": {"tools": ["sftp", "scp"], "packages": ["paramiko"]},
    "checksum": {"tools": ["md5sum", "sha256sum"], "packages": []},
    "mcp": {"tools": [], "packages": ["mcp"]},
    "cron": {"tools": ["crontab", "schtasks"], "packages": ["schedule"]},
    "macro": {"tools": [], "packages": ["pyautogui", "pynput"]},
    "watch": {"tools": [], "packages": ["watchdog"]},
    "encode": {"tools": [], "packages": []},
    "form": {"tools": [], "packages": []},
    "secret": {"tools": [], "packages": []},
}


def _scan_actions_dir(actions_dir: str = None) -> dict:
    """扫描动作目录，提取依赖信息。"""
    if actions_dir is None:
        # 尝试默认位置
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        actions_dir = os.path.join(repo_root, "actions")

    if not os.path.isdir(actions_dir):
        return {"actions_dir": actions_dir, "exists": False, "actions": []}

    actions = []
    for dirpath, _dirnames, filenames in os.walk(actions_dir):
        for fn in sorted(filenames):
            if fn.endswith(".actus.md"):
                rel = os.path.relpath(os.path.join(dirpath, fn), actions_dir).replace(os.sep, "/")
                actions.append({"id": rel, "path": os.path.join(dirpath, fn)})

    return {"actions_dir": actions_dir, "exists": True, "actions": actions}


class ActionsProber(Prober):
    """动作依赖分析探测器。"""

    def probe(self) -> list:
        info = _scan_actions_dir()
        results = []

        # 添加动作列表
        results.append(ProbeItem(
            name="actions",
            category="actions",
            available=info["exists"],
            extra={
                "actions_dir": info["actions_dir"],
                "action_count": len(info["actions"]),
                "actions": info["actions"][:50],  # 限制数量
            },
        ))

        # 添加依赖映射
        results.append(ProbeItem(
            name="action_dependencies",
            category="actions",
            available=True,
            extra=ACTION_DEPENDENCY_MAP,
        ))

        return results
