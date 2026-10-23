# -*- coding: utf-8 -*-
"""CLI 参数面与退出码契约（第 28 轮）。

缺陷：
  1. **包没有 `__version__`** —— pyproject 注释里就写着「dynamic=[version]
     但包里没有 __version__，setuptools 直接忽略 dynamic 段」。后果：
     运行期无法自报版本（排障/缺陷上报刚需）。
  2. **没有 `--version` 选项** —— 直接落进 argparse 用法错误（exit 2）。
  3. **无子命令时静默退出** —— `actus` 什么都不打印就 exit 2，用户看不到用法。
"""
import subprocess
import sys

import pytest

ACTUS = __import__("os").path.dirname(
    __import__("os").path.dirname(__import__("os").path.abspath(__file__)))


def _cli(*args):
    return subprocess.run([sys.executable, "-m", "vools.actus.cli", *args],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", cwd=ACTUS, timeout=300)


# --------------------------------------------------------------------------
# 版本
# --------------------------------------------------------------------------
def test_package_exposes_version():
    from vools.actus import __version__
    assert __version__ and __version__ != "unknown", __version__
    parts = __version__.split(".")
    assert len(parts) >= 3, __version__


def test_cli_version_flag():
    p = _cli("--version")
    assert p.returncode == 0, p.stderr[:300]
    assert "actus" in (p.stdout or "").lower()
    from vools.actus import __version__
    assert __version__ in (p.stdout or ""), p.stdout


# --------------------------------------------------------------------------
# 无子命令
# --------------------------------------------------------------------------
def test_no_subcommand_prints_help():
    """必须打印用法（此前完全静默）。"""
    p = _cli()
    text = (p.stdout or "") + (p.stderr or "")
    assert "usage" in text.lower(), "无子命令时没有任何用法输出"
    assert p.returncode == 2, p.returncode


# --------------------------------------------------------------------------
# 退出码约定
# --------------------------------------------------------------------------
@pytest.mark.parametrize("args", [
    ("nope",),                 # 未知子命令
    ("run",),                  # 缺必需参数
    ("run", "--bogus"),        # 未知选项
    ("preview",),              # 缺目标
])
def test_usage_errors_exit_2(args):
    assert _cli(*args).returncode == 2, args


def test_help_exits_0():
    assert _cli("--help").returncode == 0


def test_runtime_failure_exits_1():
    """动作不存在属运行期失败：exit 1（与用法错误 2 区分开）。"""
    assert _cli("run", "no.such.action").returncode == 1


def test_validate_exits_0():
    assert _cli("validate").returncode == 0
