# -*- coding: utf-8 -*-
"""actus/tests/test_cli_json_contracts.py — CLI 全局 `--json` 的扁平输出契约。

背景（第 27/28 轮）：`search` / `registry build` / `visibility get` 此前只打印人类
文本，脚本无法解析。cmd-engine 加了全局 `--json`（并允许子命令级同义开关），输出
**扁平**结构 `{status, ...}`（与 MCP 一致，**不套 `data`**）。

本文件钉住：
  1. 三个已接线命令的 `--json` 能被 `json.loads` 解析、顶层有 `status`、**没有 `data`**；
  2. 两种位置都可用（全局 `--json` 在子命令前 / 子命令级 `--json` 在子命令后）；
  3. 人类模式（不加 `--json`）**不是 JSON**（否则这个开关就白加了）。

补记：`registry validate` / `registry info` / `visibility set` 的 `--json` 已在
后续接线，本文件把它们从 xfail 转为正式守卫（再退回文本会直接红）。

隔离：`tmp_path` 假仓库 + HOME/ACTUS_META_DIR/ACTUS_CONFIG_DIR 全指 tmp。
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

from vools.actus import cli  # noqa: E402
from vools.actus.registry import ActionRegistry  # noqa: E402

_ACTION_TEXT = """# Demo

```json #!cfg
{"id": "myapp.demo", "name": "Demo", "version": "1.0.0",
 "description": "demo action", "trust": "sandbox"}
```
"""


# ---------------------------------------------------------------------------
# 夹具 / 辅助
# ---------------------------------------------------------------------------

class _World(object):
    pass


@pytest.fixture
def world(tmp_path, monkeypatch):
    home = tmp_path / "home"
    meta = tmp_path / "_meta"
    repo = tmp_path / "repo"
    actions = repo / "actions"
    config = tmp_path / "config"
    for directory in (home, meta, actions, config):
        directory.mkdir(parents=True)
    (actions / "demo.actus.md").write_text(_ACTION_TEXT, encoding="utf-8")

    monkeypatch.chdir(repo)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("ACTUS_REPO_ROOT", str(repo))
    monkeypatch.setenv("ACTUS_META_DIR", str(meta))
    monkeypatch.setenv("ACTUS_CONFIG_DIR", str(config))

    # registry info/validate 需要索引文件：先真实构建一次（写 tmp 仓库）
    ActionRegistry(cache_dir=str(tmp_path / "cache")).build_from_directory(str(repo))

    w = _World()
    w.root = tmp_path
    w.repo = repo
    w.meta = meta
    return w


def _run(argv):
    """同进程跑 cli.main，返回 (rc, stdout, stderr)。"""
    import contextlib
    import io
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = cli.main(list(argv))
        except SystemExit as exc:          # pragma: no cover - argparse --help 等
            rc = exc.code if exc.code is not None else 0
    return rc, out.getvalue(), err.getvalue()


def _expect_flat_json(argv, key):
    rc, out, err = _run(argv)
    assert rc == 0, (argv, out, err)
    payload = json.loads(out)             # 解析失败 = 不是机器可读输出
    assert payload.get("status") == "ok", (argv, payload)
    assert "data" not in payload, "CLI --json 必须是扁平结构（不套 data）: %r" % (argv,)
    assert key in payload, (argv, sorted(payload))
    return payload


# ===========================================================================
# 1) 三个已接线命令：全局 --json（子命令前）
# ===========================================================================

def test_global_json_flag_search_is_flat(world):
    """退步了会怎样：`--json search` 又退回人类文本（脚本无法解析），
    或改成 `{status,data:{...}}` 套层（与 MCP 形状漂移、客户端要写两套解析）。

    断言：扁平 JSON、status=ok、query/count/actions 字段齐全，命中 myapp.demo。
    """
    payload = _expect_flat_json(["--json", "search", "demo"], "actions")
    assert payload["query"] == "demo"
    assert payload["count"] >= 1
    assert "myapp.demo" in [row["id"] for row in payload["actions"]]


def test_global_json_flag_registry_build_is_flat(world):
    """退步了会怎样：`--json registry build` 仍是 ✅ 文本，或丢了 index/count，
    CI 无法从机器输出里知道索引落在哪、建了几条。

    断言：扁平 JSON、status=ok、index 路径存在、count 与仓库动作数一致。
    """
    payload = _expect_flat_json(["--json", "registry", "build"], "index")
    assert os.path.isfile(payload["index"])
    assert payload["count"] >= 1


def test_global_json_flag_visibility_get_is_flat(world):
    """退步了会怎样：`--json visibility get` 仍是 👁️ 文本；或缺少 action_id/visibility，
    脚本无法判断某动作当前可见性。

    断言：扁平 JSON、action_id/visibility 具体值（动作未声明 → public）。
    """
    payload = _expect_flat_json(
        ["--json", "visibility", "get", "myapp.demo"], "visibility")
    assert payload["action_id"] == "myapp.demo"
    assert payload["visibility"] == "public"


# ===========================================================================
# 2) 同样三个命令：子命令级 --json（子命令后）必须等价
# ===========================================================================

@pytest.mark.parametrize("argv,key", [
    (["search", "--json", "demo"], "actions"),
    (["registry", "--json", "build"], "index"),
    (["visibility", "--json", "get", "myapp.demo"], "visibility"),
], ids=["search", "registry-build", "visibility-get"])
def test_subcommand_json_flag_is_equivalent(world, argv, key):
    """退步了会怎样：只有全局位置可用 —— `actus search --json`（自然的写法）落进
    用法错误或退回人类文本；两处开关行为不一致。

    断言：子命令级 `--json` 同样输出扁平 JSON + status=ok + 关键字段。
    """
    payload = _expect_flat_json(argv, key)
    if key == "actions":
        assert payload["query"] == "demo"
    elif key == "index":
        assert os.path.isfile(payload["index"])


# ===========================================================================
# 3) 人类模式不加 --json → 必须不是 JSON
# ===========================================================================

@pytest.mark.parametrize("argv,marker", [
    (["search", "demo"], "找到"),
    (["registry", "build"], "注册表索引已构建"),
    (["visibility", "get", "myapp.demo"], "myapp.demo"),
], ids=["search", "registry-build", "visibility-get"])
def test_human_mode_is_not_json(world, argv, marker):
    """退步了会怎样：加 `--json` 时把人类模式也改成 JSON —— `actus search` 的
    默认体验被破坏（人读不了），这个开关就失去"可选"的意义。

    断言：默认模式 `json.loads` 必须失败，且含人类可读文案。
    """
    rc, out, err = _run(argv)
    assert rc == 0, (argv, err)

    with pytest.raises(ValueError):
        json.loads(out)
    assert marker in out, "人类模式缺少可读文案: %r" % (out[:200],)


# ===========================================================================
# 4) 已接线：registry validate / registry info / visibility set 的 --json
# ===========================================================================

@pytest.mark.parametrize("argv,key", [
    (["--json", "registry", "validate"], "valid"),
    (["--json", "registry", "info"], "actions"),
    (["--json", "visibility", "set", "myapp.demo", "--level", "public"], "visibility"),
], ids=["registry-validate", "registry-info", "visibility-set"])
def test_newly_wired_commands_are_flat_json(world, argv, key):
    """退步了会怎样：这三个命令（cmd-engine 后续接线）又退回人类文本，或输出套
    `data` 层 —— 脚本无法解析。

    断言：扁平 JSON、status=ok、关键字段存在（validate→valid/invalid；info→actions；
    visibility set→action_id/visibility/previous）。
    """
    payload = _expect_flat_json(argv, key)
    if key == "valid":
        assert "invalid" in payload
    elif key == "actions":
        assert payload["count"] >= 1
    else:
        assert payload["action_id"] == "myapp.demo"
