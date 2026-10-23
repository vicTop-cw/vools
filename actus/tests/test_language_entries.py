# -*- coding: utf-8 -*-
"""ACTUS_REFACTOR_PLAN §六.1：powershell / cmd 等语言入口必须真正可执行。

计划把「powershell/cmd 路由：runner 直接分支与 ShellRuntime 方言检测需对齐；
bat 直接 spawn 与 cmd /c 包装二选一」列为开放问题。实测七种语言入口全部
可执行（python / bash / shell / powershell / pwsh / cmd / node），本组把它
固化为回归——任一语言退化都会立刻红。
"""
import json
import os
import subprocess
import sys

import pytest

FENCE = "`" * 3
ACTUS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TPL = """---
id: myapp.{lang}
name: N
version: 1.0.0
trust: sandbox
kind: exec
entry: main
platform: desktop
description: probe {lang}
---

# N

{fence}{lang} #!run tag=main
{snippet}
{fence}
"""


def _make_repo(tmp_path, lang, snippet):
    root = tmp_path / "repo"
    (root / "actions").mkdir(parents=True)
    path = root / "actions" / "a.actus.schema.md"
    path.write_text(TPL.format(lang=lang, snippet=snippet, fence=FENCE),
                    encoding="utf-8")
    return root


def _run_cli(root, lang):
    env = dict(os.environ)
    env["ACTUS_REPO_ROOT"] = str(root)
    proc = subprocess.run(
        [sys.executable, "-m", "vools.actus.cli", "run", "myapp.%s" % lang],
        capture_output=True, text=True, encoding="utf-8", env=env, cwd=ACTUS,
        timeout=180)
    out = (proc.stdout or "").strip()
    assert out.startswith("{"), "CLI 输出非 JSON：%s | stderr=%s" % (out[:200], proc.stderr[:200])
    return json.loads(out)


# language -> (snippet, expected stdout)
CASES = [
    ("python", 'print("ok-py")', "ok-py"),
    ("bash", "echo ok-bash", "ok-bash"),
    ("shell", "echo ok-shell", "ok-shell"),
    ("powershell", 'Write-Output "ok-ps"', "ok-ps"),
    ("pwsh", 'Write-Output "ok-pwsh"', "ok-pwsh"),
    ("cmd", "echo ok-cmd", "ok-cmd"),
    ("node", 'console.log("ok-node")', "ok-node"),
]


@pytest.mark.parametrize("lang,snippet,expected", CASES,
                         ids=[c[0] for c in CASES])
def test_language_entry_executes(tmp_path, lang, snippet, expected):
    """各语言作为入口块时必须能真的跑出结果（§六.1）。"""
    root = _make_repo(tmp_path, lang, snippet)
    result = _run_cli(root, lang)
    assert result.get("status") == "ok", "语言 %s 执行失败: %s" % (lang, result)
    data = result.get("data") or {}
    output = str(data.get("output") or "")
    assert expected in output, "语言 %s 输出不含预期: %r" % (lang, output[:160])
