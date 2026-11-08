# -*- coding: utf-8 -*-
"""examples/ 示例冒烟测试（T0r2.3.1 r1-doc-as-impl 出口判据）。

验收目标：examples/ 下的剪贴板示例必须「可真实运行」且有测试覆盖。
本文件以子进程方式真实运行两个示例脚本，断言退出码与关键输出标记：
  - clipboard_basic.py  -> CLIP_BASIC_OK（写/读/清空全链路）
  - clipboard_watch.py  -> CLIP_WATCH_OK（监控收到写入事件）

示例会短暂改写系统剪贴板（Windows 全局剪贴板），与
test_clipboard_integration.py 的真实读写策略一致。
"""

import os
import subprocess
import sys

EXAMPLES = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples"
)
_BASIC = os.path.join(EXAMPLES, "clipboard_basic.py")
_WATCH = os.path.join(EXAMPLES, "clipboard_watch.py")


def _env():
    """继承 pytest 进程的 vools 相关 sys.path，保证子进程可导入 actus 与 rx。"""
    env = dict(os.environ)
    roots = [p for p in sys.path if "vools" in p.replace("\\", "/").lower()]
    env["PYTHONPATH"] = os.pathsep.join(roots)
    return env


def _run(script, timeout=20):
    proc = subprocess.run(
        [sys.executable, script],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=_env(),
    )
    return proc


def test_example_basic_runs():
    proc = _run(_BASIC)
    assert proc.returncode == 0, "示例退出码非 0\nstdout:\n%s\nstderr:\n%s" % (
        proc.stdout, proc.stderr)
    assert "CLIP_BASIC_OK" in proc.stdout
    assert "[write]" in proc.stdout and "[read]" in proc.stdout and "[clear]" in proc.stdout


def test_example_watch_runs():
    proc = _run(_WATCH, timeout=20)
    assert proc.returncode == 0, "示例退出码非 0\nstdout:\n%s\nstderr:\n%s" % (
        proc.stdout, proc.stderr)
    assert "CLIP_WATCH_OK" in proc.stdout
    assert "[watch]" in proc.stdout
