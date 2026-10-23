# -*- coding: utf-8 -*-
"""link/alias 转发的「深链」与「成环」必须区分（第 22 轮）。

原实现只数转发深度（≥5 就拒），把所有情况都报成
`param_invalid`「疑似环」——但直线链 a1→a8 **不是环**，诊断信息误导。
现在加了访问链追踪：
  - 目标已在链上 / 指向自己 → `action_ref_cycle`（附完整链路）
  - 链上无重复但层级超限   → `param_invalid`（明确写「深度超限而非成环」）
"""
import json
import os
import subprocess
import sys

import pytest

FENCE = "`" * 3
ACTUS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LINK_TPL = """---
id: {aid}
name: N
version: 1.0.0
trust: sandbox
kind: link
target: {target}
platform: desktop
description: link {aid}
---

# N
"""

EXEC_TPL = """---
id: {aid}
name: N
version: 1.0.0
trust: sandbox
kind: exec
entry: main
platform: desktop
description: leaf
---

# N

{fence}python #!run tag=main
print("leaf-ran")
{fence}
"""


def _write(actions, name, text):
    with open(os.path.join(actions, name), "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def _make_chain_repo(tmp_path, hops):
    """造 hops 条 link 的直线链，末端接一个 exec 叶子。"""
    root = tmp_path / "repo"
    actions = root / "actions"
    actions.mkdir(parents=True)
    for i in range(1, hops + 1):
        target = "myapp.a%d" % (i + 1) if i < hops else "myapp.leaf"
        _write(actions, "a%d.actus.schema.md" % i,
               LINK_TPL.format(aid="myapp.a%d" % i, target=target))
    _write(actions, "leaf.actus.schema.md", EXEC_TPL.format(aid="myapp.leaf", fence=FENCE))
    return root


def _make_cycle_repo(tmp_path):
    root = tmp_path / "repo"
    actions = root / "actions"
    actions.mkdir(parents=True)
    _write(actions, "c1.actus.schema.md",
           LINK_TPL.format(aid="myapp.c1", target="myapp.c2"))
    _write(actions, "c2.actus.schema.md",
           LINK_TPL.format(aid="myapp.c2", target="myapp.c1"))
    return root


def _run(root, aid):
    env = dict(os.environ)
    env["ACTUS_REPO_ROOT"] = str(root)
    proc = subprocess.run([sys.executable, "-m", "vools.actus.cli", "run", aid],
                          capture_output=True, text=True, encoding="utf-8",
                          env=env, cwd=ACTUS, timeout=300)
    out = (proc.stdout or "").strip()
    assert out.startswith("{"), "CLI 输出非 JSON: %s | %s" % (out[:200], proc.stderr[:200])
    return json.loads(out)


def test_short_link_chain_works(tmp_path):
    """3 跳链应正常跑到叶子。"""
    root = _make_chain_repo(tmp_path, hops=3)
    result = _run(root, "myapp.a1")
    assert result["status"] == "ok", result
    assert "leaf-ran" in json.dumps(result.get("data") or {}, ensure_ascii=False)


def test_deep_chain_reports_depth_not_cycle(tmp_path):
    """8 跳直线链：报 param_invalid 且明确是「深度超限」，不能谎称成环。"""
    root = _make_chain_repo(tmp_path, hops=8)
    result = _run(root, "myapp.a1")
    assert result["status"] == "failed"
    err = result.get("error") or {}
    assert err.get("code") == "param_invalid", err
    msg = str(err.get("message") or "")
    assert "深度超限" in msg, "应说明是深度超限: %r" % msg
    assert "成环" in msg and "而非成环" in msg


def test_true_cycle_reports_cycle_code(tmp_path):
    """c1↔c2 真环：报 action_ref_cycle，并给出完整链路。"""
    root = _make_cycle_repo(tmp_path)
    result = _run(root, "myapp.c1")
    assert result["status"] == "failed"
    err = result.get("error") or {}
    assert err.get("code") == "action_ref_cycle", err
    chain = (err.get("details") or {}).get("chain") or []
    assert chain[:2] == ["myapp.c1", "myapp.c2"], chain
    assert chain[-1] == "myapp.c1", "链路应回到起点"


def test_self_link_is_cycle(tmp_path):
    """自环必须立刻判成环，不进深度循环。"""
    root = tmp_path / "repo"
    actions = root / "actions"
    actions.mkdir(parents=True)
    _write(actions, "self.actus.schema.md",
           LINK_TPL.format(aid="myapp.self", target="myapp.self"))
    result = _run(root, "myapp.self")
    assert result["status"] == "failed"
    assert (result.get("error") or {}).get("code") == "action_ref_cycle"
