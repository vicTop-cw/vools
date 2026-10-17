"""probe/system_tools.py — 系统工具探测。

通过 shutil.which + subprocess 探测已知工具表中的每个工具。
"""


__all__ = [
    "SystemToolsProber",
    "probe",
]

import os
import platform
import shutil
import subprocess
import sys
import glob as globmod

from .base import Prober, ProbeItem
from .TOOL_TABLE import TOOL_TABLE


def _find_tool(name: str, aliases: list, well_known_paths: dict) -> str:
    """查找工具可执行文件，返回路径或 None。"""
    # 1) shutil.which（PATH 搜索）
    for cmd in [name] + aliases:
        path = shutil.which(cmd)
        if path:
            return path

    # 2) 已知路径搜索
    sys_platform = sys.platform
    patterns = well_known_paths.get(sys_platform, [])
    for pattern in patterns:
        matches = globmod.glob(pattern, recursive=True)
        if matches:
            return matches[0]

    return None


def _get_version(path: str, version_args: list, timeout: int = 5) -> str:
    """获取工具版本信息。"""
    try:
        cmd = [path] + version_args
        r = subprocess.run(
            cmd, capture_output=True, text=True, errors='replace', timeout=timeout
        )
        output = (r.stdout or r.stderr or "").strip()
        if output:
            return output.split("\n")[0][:200]
    except Exception:
        pass
    return ""


class SystemToolsProber(Prober):
    """系统工具探测器。"""

    def probe(self) -> list:
        results = []
        for entry in TOOL_TABLE:
            name, aliases, version_cmd, well_known_paths, timeout = entry

            path = _find_tool(name, aliases, well_known_paths)
            if path:
                version = _get_version(path, version_cmd, timeout)
                results.append(ProbeItem(
                    name=name,
                    category="system_tools",
                    available=True,
                    path=path,
                    version=version,
                ))
            else:
                results.append(ProbeItem(
                    name=name,
                    category="system_tools",
                    available=False,
                    error="not found",
                ))
        return results
