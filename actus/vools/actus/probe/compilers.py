"""probe/compilers.py — 编译器探测。

复用 vools.sys.compile_cmd 和 vools.task.core.cli_exec。
"""


__all__ = [
    "CompilersProber",
    "probe",
]

import shutil
import subprocess
import sys

from .base import Prober, ProbeItem

# 编译器检测表：(name, cmd, version_args)
COMPILER_TABLE = [
    ("gcc", "gcc", ["--version"]),
    ("g++", "g++", ["--version"]),
    ("clang", "clang", ["--version"]),
    ("cl", "cl", ["??"]),  # MSVC cl.exe
    ("rustc", "rustc", ["--version"]),
    ("cargo", "cargo", ["--version"]),
    ("nim", "nim", ["--version"]),
    ("zig", "zig", ["version"]),
    ("go", "go", ["version"]),
    ("javac", "javac", ["-version"]),
    ("java", "java", ["-version"]),
]


def _detect_compiler(cmd: str, version_args: list, timeout: int = 5) -> dict:
    """检测单个编译器。"""
    path = shutil.which(cmd)
    if not path:
        return {"name": cmd, "available": False, "error": "not found"}

    version = ""
    try:
        r = subprocess.run(
            [path] + version_args, capture_output=True, text=True, errors='replace', timeout=timeout
        )
        output = (r.stdout or r.stderr or "").strip()
        if output:
            version = output.split("\n")[0][:200]
    except Exception:
        pass

    return {"name": cmd, "available": True, "path": path, "version": version}


class CompilersProber(Prober):
    """编译器探测器。"""

    def probe(self) -> list:
        results = []
        for name, cmd, version_args in COMPILER_TABLE:
            info = _detect_compiler(cmd, version_args)
            results.append(ProbeItem(
                name=info["name"],
                category="compilers",
                available=info["available"],
                path=info.get("path"),
                version=info.get("version"),
                error=info.get("error"),
            ))
        return results
