# -*- coding: utf-8 -*-
"""阶段1：resolver 接入 CLI 的回归（ACTUS_REFACTOR_PLAN §3.1）。

此前 `cli.py run` 直接把参数当 action_id 传给 execute，`resolver.py` 写完
从未被任何模块调用 ⇒ 六种 target 形态与七种入参形态全部不生效。
本组用隔离仓库（ACTUS_REPO_ROOT）经 CLI 实跑 id / name / path 三形态。
"""
import json
import os
import subprocess
import sys
import pytest

# 第 22 轮：真实动作执行（模块总耗时 >3s）
pytestmark = pytest.mark.slow

PY = sys.executable

ECHO_ACTION = """---
id: myapp.echo
name: EchoRunner
version: 1.0.0
trust: sandbox
kind: exec
entry: main
platform: desktop
description: 回显动作（端到端验收用）
---

# Echo

```python #!run tag=main
print("echo-ran")
```
"""


def _make_repo(tmp_path):
    root = tmp_path / "repo"
    (root / "actions").mkdir(parents=True)
    with open(root / "actions" / "echo.actus.schema.md", "w", encoding="utf-8") as fh:
        fh.write(ECHO_ACTION)
    return root


def _run_cli(root, *args):
    env = dict(os.environ)
    env["ACTUS_REPO_ROOT"] = str(root)
    proc = subprocess.run([PY, "-m", "vools.actus.cli", *args],
                          capture_output=True, text=True, encoding="utf-8", env=env)
    out = (proc.stdout or "").strip()
    try:
        return proc.returncode, json.loads(out) if out.startswith("{") else out
    except ValueError:
        return proc.returncode, out


# --------------------------------------------------------------------------
# resolver 纯解析
# --------------------------------------------------------------------------
def test_resolve_target_id_form():
    from vools.actus.resolver import resolve_target
    r = resolve_target("actus.basics.calculator")
    assert r.source == "id"
    assert r.action_id == "actus.basics.calculator"


def test_resolve_target_name_form():
    from vools.actus.resolver import resolve_target
    r = resolve_target("Calculator")
    assert r.source in ("name", "id")
    assert r.action_id, "name 形态应解析出 action_id"


def test_resolve_target_path_form():
    """新格式 .actus.schema.md 的散落路径必须能解析（此前只认 .actus.md）。

    路径按**测试文件位置**推导，不依赖 cwd —— 此前写成相对仓库根的
    `actus/vools/...`，从 actus/ 目录跑 pytest 时该路径不存在，解析出空 id。
    """
    from vools.actus.resolver import resolve_target
    here = os.path.dirname(os.path.abspath(__file__))          # …/actus/tests
    path = os.path.join(here, os.pardir, "vools", "actus", "actions", "basics",
                        "calculator.actus.schema.md")
    r = resolve_target(path)
    assert r.source == "path", r
    assert r.action_id == "actus.basics.calculator"


def test_scattered_path_accepts_schema_md(tmp_path):
    """is_scattered_path 必须认双后缀（constants.is_action_file 单一真源）。"""
    from vools.actus.scattered import is_scattered_path
    p = tmp_path / "foo.actus.schema.md"
    p.write_text("---\nid: a.b\n---\n", encoding="utf-8")
    assert is_scattered_path(str(p)) is True
    d = tmp_path / "foo.actus"
    d.mkdir()
    assert is_scattered_path(str(d)) is True
    assert is_scattered_path(str(tmp_path / "nope.txt")) is False


# --------------------------------------------------------------------------
# CLI 端到端：三形态都必须能跑
# --------------------------------------------------------------------------
def test_cli_run_by_id(tmp_path):
    root = _make_repo(tmp_path)
    code, out = _run_cli(root, "run", "myapp.echo")
    assert code == 0, out
    assert out.get("status") == "ok", out


def test_cli_run_by_name(tmp_path):
    """name 形态：此前直接当 id 用会 action_not_found。"""
    root = _make_repo(tmp_path)
    code, out = _run_cli(root, "run", "EchoRunner")
    assert code == 0, out
    assert out.get("status") == "ok", out


def test_cli_run_by_path(tmp_path):
    """path 形态：此前会把路径当 id，报动作不存在。"""
    root = _make_repo(tmp_path)
    path = str(root / "actions" / "echo.actus.schema.md")
    code, out = _run_cli(root, "run", path)
    assert code == 0, out
    assert out.get("status") == "ok", out
