# -*- coding: utf-8 -*-
"""阶段3 kind 家族的端到端验收（走 CLI `actus run` 真实链路）。

此前的用例都是单元级（直接调 executor 的 helper）；本组在**隔离的临时仓库**
里造各类 kind 动作，用 CLI 实跑，验证 resolver → indexer → 门禁 → kind 分派
整条链路。

隔离方式：ACTUS_REPO_ROOT 指向临时目录，indexer._repo_root() 尊重该环境变量。
"""
import json
import os
import subprocess
import sys

PY = sys.executable

EXEC_ACTION = """---
id: myapp.target
name: Target
version: 1.0.0
trust: sandbox
kind: exec
entry: main
platform: desktop
description: 端到端验收用的目标动作
---

# Target

```python #!run tag=main
print("target-ran")
```
"""

LINK_ACTION = """---
id: myapp.link
name: Link
version: 1.0.0
trust: sandbox
kind: link
target: myapp.target
platform: desktop
description: 转发到 target 的 link
---

# Link
"""

ALIAS_ACTION = """---
id: myapp.alias
name: Alias
version: 1.0.0
trust: sandbox
kind: alias
target: myapp.target
platform: desktop
description: 转发到 target 的别名
---

# Alias
"""

BUNDLE_ACTION = """---
id: myapp.bundle
name: Bundle
version: 1.0.0
trust: sandbox
kind: bundle
members: [myapp.target, myapp.link]
platform: desktop
description: 动作集
---

# Bundle
"""

DOC_ACTION = """---
id: myapp.doc
name: Doc
version: 1.0.0
trust: sandbox
kind: doc
platform: desktop
description: 纯文档动作
---

# Doc

这是正文，不应被执行。
"""

DEMO_ACTION = """---
id: myapp.demo
name: Demo
version: 1.0.0
trust: sandbox
kind: demo
entry: main
platform: desktop
description: 演示动作
---

# Demo

```python #!run tag=main
print("demo-ran")
```
"""


def _make_repo(tmp_path):
    root = tmp_path / "repo"
    (root / "actions").mkdir(parents=True)
    files = {
        "target.actus.schema.md": EXEC_ACTION,
        "link.actus.schema.md": LINK_ACTION,
        "alias.actus.schema.md": ALIAS_ACTION,
        "bundle.actus.schema.md": BUNDLE_ACTION,
        "doc.actus.schema.md": DOC_ACTION,
        "demo.actus.schema.md": DEMO_ACTION,
    }
    for name, text in files.items():
        with open(root / "actions" / name, "w", encoding="utf-8") as fh:
            fh.write(text)
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


def test_e2e_link_forwards_to_target(tmp_path):
    root = _make_repo(tmp_path)
    code, out = _run_cli(root, "run", "myapp.link")
    assert code == 0, out
    assert isinstance(out, dict), out
    assert out.get("status") == "ok", out


def test_e2e_alias_forwards_to_target(tmp_path):
    root = _make_repo(tmp_path)
    code, out = _run_cli(root, "run", "myapp.alias")
    assert code == 0, out
    assert out.get("status") == "ok", out


def test_e2e_bundle_lists_members(tmp_path):
    root = _make_repo(tmp_path)
    code, out = _run_cli(root, "run", "myapp.bundle")
    assert code == 0, out
    data = out.get("data") or {}
    assert data.get("count") == 2, out
    assert "myapp.target" in data.get("members", [])


def test_e2e_doc_renders_without_executing(tmp_path):
    root = _make_repo(tmp_path)
    code, out = _run_cli(root, "run", "myapp.doc")
    assert code == 0, out
    data = out.get("data") or {}
    assert data.get("rendered") is True, out


def test_e2e_demo_expands_source(tmp_path):
    root = _make_repo(tmp_path)
    code, out = _run_cli(root, "run", "myapp.demo")
    assert code == 0, out
    data = out.get("data") or {}
    demo = data.get("demo") or {}
    assert demo.get("block_count", 0) >= 1, out
    assert demo.get("expanded")[0].get("only_code") is True


def test_e2e_unknown_action_reports_readably(tmp_path):
    root = _make_repo(tmp_path)
    code, out = _run_cli(root, "run", "myapp.does-not-exist")
    assert code != 0 or (isinstance(out, dict) and out.get("status") == "failed")
