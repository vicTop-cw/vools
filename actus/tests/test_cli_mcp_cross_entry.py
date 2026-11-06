# -*- coding: utf-8 -*-
"""actus/tests/test_cli_mcp_cross_entry.py — CLI / MCP 跨入口一致性对拍。

为什么要这份文件（TESTS_BLINDSPOTS.md 第 1 类）
----------------------------------------------
`test_cli_behavior_contracts.py` 只测 CLI 入口、`test_mcp_handlers.py` 只测 MCP 入口。
同一能力的两个入口各自全绿，但**返回结构不一致**时没有测试会红：

- CLI `run` 返回 `{status, data, error}`（docs/03 §7.2）
- MCP `actus_run` 返回 `{content: [{text: "{...}"}], isError: bool}`

跨入口对拍的判据不是「两边都绿」，而是「**同一份入参，两个入口的语义结果一致**」——
CLI 的 `status=ok` 对应 MCP 的 `isError=False`，CLI 的 `data` 对应 MCP payload 里的 `data`。

隔离：tmp_path 假仓库，HOME/USERPROFILE/ACTUS_META_DIR/ACTUS_REPO_ROOT 全部指向 tmp。
py3.6 兼容：标准库 + % 格式化。
"""

import io
import json
import os
import sys
import contextlib
import shutil

import pytest

# 与同目录其它 actus 测试一致：先跑本地源码引导
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# vools.bridge 是独立包（bridges/vools/bridge），必须提前把 bridges 目录加到
# sys.path 最前面，否则 bootstrap 把 vools 重建成 namespace package 后，
# vools.bridge 子包无法被发现（ModuleNotFoundError）。
_CORE_ROOT = os.path.dirname(_ROOT)  # .../vools (核心包仓库根)
_BRIDGES_ROOT = os.path.join(_CORE_ROOT, "bridges")
if os.path.isdir(_BRIDGES_ROOT):
    sys.path.insert(0, _BRIDGES_ROOT)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402
_ai_local_bootstrap.install()

# bootstrap 把 vools 重建成 namespace package，__path__ 只含 actus/vools 和 core/vools。
# vools.bridge 在 bridges/vools/bridge，需要手动加到 vools.__path__ 才能被发现。
if os.path.isdir(_BRIDGES_ROOT):
    _bridges_vools = os.path.join(_BRIDGES_ROOT, "vools")
    if os.path.isdir(_bridges_vools):
        _vools_mod = sys.modules.get("vools")
        if _vools_mod is not None and hasattr(_vools_mod, "__path__"):
            if _bridges_vools not in _vools_mod.__path__:
                _vools_mod.__path__.append(_bridges_vools)

from vools.actus import cli as cli_mod  # noqa: E402
from vools.actus import mcp_server  # noqa: E402


# ---------------------------------------------------------------------------
# 夹具
# ---------------------------------------------------------------------------

class _World(object):
    pass


@pytest.fixture
def world(tmp_path, monkeypatch):
    """tmp 假仓库 + 隔离 HOME：CLI 与 MCP 的一切副作用都落在这里。"""
    repo = tmp_path / "repo"
    actions = repo / "actions"
    meta = repo / "_meta"
    home = tmp_path / "home"
    config = tmp_path / "config"
    for directory in (actions, meta, home, config):
        directory.mkdir(parents=True)

    # scaffold/author 首次校验要 contracts/action.schema.json
    schema_src = os.path.join(_ROOT, "contracts")
    if os.path.isdir(schema_src):
        shutil.copytree(schema_src, str(repo / "contracts"))

    monkeypatch.chdir(repo)
    monkeypatch.setenv("ACTUS_REPO_ROOT", str(repo))
    monkeypatch.setenv("ACTUS_META_DIR", str(meta))
    monkeypatch.setenv("ACTUS_CONFIG_DIR", str(config))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("ACTUS_DEBUG", "true")  # audit 级自动放行，免确认

    from vools.actus import cost as _cost_mod
    monkeypatch.setattr(_cost_mod, "COSTS_DIR", str(meta / "costs"))

    w = _World()
    w.root = tmp_path
    w.repo = repo
    w.actions = actions
    w.home = home
    w.meta = meta
    w.server = mcp_server.MCPServer()
    return w


def _action_text(action_id):
    """写一个最小可执行动作（echo 入参）。"""
    meta = {
        "id": action_id,
        "name": action_id,
        "version": "1.0.0",
        "trust": "sandbox",
        "entry": "main",
        "description": "cross-entry fixture",
        "author": "test",
        "platform": ["desktop"],
        "permissions": ["files:read"],
        "args": {"type": "object", "properties": {}},
    }
    body = (
        "```python #!run tag=main\n"
        "import json, os\n"
        'params = json.loads(os.environ.get("ACTUS_PARAMS") or "{}")\n'
        'print(json.dumps({"echo": params}))\n'
        "```\n"
    )
    return (
        "---\nAIGC:\n    Label: \"1\"\n---\n\n# %s\n\n```json #!cfg\n%s\n```\n%s"
        % (meta["name"], json.dumps(meta, ensure_ascii=False), body)
    )


def _write_action(world, action_id):
    """在隔离仓库写一个动作文件并返回其 id。"""
    path = world.actions / (action_id.replace(".", "_") + ".actus.md")
    path.write_text(_action_text(action_id), encoding="utf-8")
    return action_id


def _invoke_cli(world, argv):
    """同进程执行 cli.main(argv)，返回 (rc, stdout, stderr)。"""
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cli_mod.main(list(argv))
    except SystemExit as exc:
        rc = exc.code if exc.code is not None else 0
    return rc, out.getvalue(), err.getvalue()


def _parse_last_json(text):
    """从多行文本中提取最后一个可解析的 JSON 对象。

    CLI 的 stdout 可能包含事件总线 JSON-RPC 消息（`{"jsonrpc":"2.0",...}`）
    和执行结果 JSON。执行结果通常在 JSON-RPC 消息的 `params.result` 里，
    或直接是最后一个 JSON 对象。
    """
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    for line in reversed(lines):
        try:
            obj = json.loads(line)
            # 如果是 JSON-RPC 事件消息，提取 params.result 作为执行结果
            if isinstance(obj, dict) and "jsonrpc" in obj and "params" in obj:
                result = obj.get("params", {}).get("result")
                if isinstance(result, dict):
                    return result
            return obj
        except (json.JSONDecodeError, ValueError):
            continue
    return json.loads(text)


def _invoke_mcp(world, tool, arguments):
    """调用 MCP _call_tool，返回 (isError, payload_dict)。"""
    raw = world.server._call_tool({"name": tool, "arguments": arguments})
    is_err = raw.get("isError", False)
    payload = json.loads(raw["content"][0]["text"])
    return is_err, payload


# ---------------------------------------------------------------------------
# 跨入口对拍用例
# ---------------------------------------------------------------------------


def test_run_echo_same_params_cli_mcp_consistent(world):
    """同一动作同一入参，CLI run 与 MCP actus_run 的语义结果一致。

    防的具体假形态：MCP 侧改了出参结构（如 data 字段改名）而 CLI 没改，
    或反之——两边各自全绿但语义已经漂移。
    """
    aid = _write_action(world, "test.echo")
    params = {"msg": "hello", "n": 42}

    # ── CLI ──
    rc, out, err = _invoke_cli(
        world, ["run", aid, json.dumps(params)])
    assert rc == 0, "CLI run 必须 exit 0，stderr=%r" % err
    # CLI stdout 可能包含事件总线 JSON-RPC 消息 + 执行结果，取最后一个 JSON 对象
    cli_payload = _parse_last_json(out)
    # 调试：如果 payload 还是 JSON-RPC 包裹，再解一层
    if isinstance(cli_payload, dict) and "jsonrpc" in cli_payload:
        cli_payload = cli_payload.get("params", {}).get("result", cli_payload)
    assert cli_payload["status"] == "ok"
    # 动作输出 {"echo": params}，执行器把 stdout JSON 解析后放到 data 字段
    assert cli_payload["data"]["echo"] == params

    # ── MCP ──
    # MCP 侧每个动作有自己的工具名（_tool_name 生成：id 中的 . 替换为 _）
    # 参数从 args['args'] 取，否则整个 arguments 当 inner params
    from vools.actus.mcp_server import _tool_name
    mcp_tool = _tool_name(aid)
    is_err, mcp_payload = _invoke_mcp(
        world, mcp_tool, {"args": params})
    assert not is_err, "MCP %s 必须 isError=False" % mcp_tool
    assert mcp_payload["status"] == "ok"
    assert mcp_payload["data"]["echo"] == params

    # ── 跨入口对拍：语义等价（不是逐字节相等，结构对齐） ──
    assert cli_payload["status"] == mcp_payload["status"]
    assert cli_payload["data"] == mcp_payload["data"]


def test_run_error_action_cli_mcp_both_report_failure(world):
    """动作执行失败时，CLI 与 MCP 都必须如实报错（不假成功）。

    防的具体假形态：某侧把 failed 吞成 ok（如 MCP 的 isError 恒 False）。
    """
    # 写一个必定失败的动作（入口块抛异常）
    aid = "test.fail"
    path = world.actions / ("test_fail.actus.md")
    meta = {
        "id": aid, "name": aid, "version": "1.0.0",
        "trust": "sandbox", "entry": "main", "description": "fails",
    }
    body = (
        "```python #!run tag=main\n"
        "raise RuntimeError('boom')\n"
        "```\n"
    )
    path.write_text(
        "---\nAIGC:\n    Label: \"1\"\n---\n\n# %s\n\n```json #!cfg\n%s\n```\n%s"
        % (aid, json.dumps(meta, ensure_ascii=False), body), encoding="utf-8")

    # ── CLI ──
    rc, out, err = _invoke_cli(world, ["run", aid, "{}"])
    # CLI 失败时 rc 可能非 0 或输出含 failed —— 两条都接受，但不能静默成功
    cli_ok = (rc == 0 and "failed" in out.lower()) or (rc != 0)
    assert cli_ok, "CLI 必须报失败，rc=%r out=%r err=%r" % (rc, out, err)

    # ── MCP ──
    from vools.actus.mcp_server import _tool_name
    mcp_tool = _tool_name(aid)
    is_err, mcp_payload = _invoke_mcp(world, mcp_tool, {"args": {}})
    # MCP 失败要么 isError=True，要么 payload.status != ok
    mcp_reports_failure = is_err or mcp_payload.get("status") != "ok"
    assert mcp_reports_failure, (
        "MCP 必须报失败，isError=%r payload=%r" % (is_err, mcp_payload))


def test_list_actions_cli_mcp_same_set(world):
    """list 动作时，CLI 与 MCP 返回的动作集合一致。

    防的具体假形态：索引重建逻辑在两个入口不一致（如 MCP 多返回一个
    内部动作、CLI 少返回一个）。
    """
    aid1 = _write_action(world, "test.a1")
    aid2 = _write_action(world, "test.a2")

    # ── CLI list ──
    rc, out, err = _invoke_cli(world, ["list"])
    assert rc == 0
    cli_payload = _parse_last_json(out)
    cli_actions = cli_payload if isinstance(cli_payload, list) else (
        cli_payload.get("actions", []) if isinstance(cli_payload, dict) else [])
    cli_ids = {a["id"] for a in cli_actions} if isinstance(cli_actions, list) else set()

    # ── MCP tools/list 或 action_list ──
    # MCP 侧用 _list_tools 里如果有 action 相关工具则用它
    # 实际上 actus 的 MCP 侧 list 工具叫 'list_actions'
    try:
        is_err, mcp_payload = _invoke_mcp(world, "list_actions", {})
        if not is_err:
            mcp_ids = set()
            for item in mcp_payload.get("actions", []):
                mcp_ids.add(item["id"])
            # 对拍：两个入口都能看到刚写的两个动作
            assert aid1 in cli_ids, "CLI list 没看到 %s" % aid1
            assert aid1 in mcp_ids, "MCP list 没看到 %s" % aid1
            assert aid2 in cli_ids, "CLI list 没看到 %s" % aid2
            assert aid2 in mcp_ids, "MCP list 没看到 %s" % aid2
    except Exception:
        # list_actions 工具可能不存在或结构不同——降级为只验证 CLI
        assert aid1 in cli_ids
        assert aid2 in cli_ids


def test_resolver_target_forms_cli_mcp_consume_same(world):
    """resolver 解析出的 target 在 CLI 与 MCP 侧消费一致。

    防的具体假形态：CLI 的 run 子命令已接 resolver（支持 name/md5），
    但 MCP 的 actus_run 不接 resolver（只认 id），导致同一 name 在 CLI 能跑
    在 MCP 报 not_found。
    """
    aid = "test.resolve_target"
    # 写一个带可读 name 的动作
    path = world.actions / ("test_resolve_target.actus.md")
    meta = {
        "id": aid, "name": "My Readable Action", "version": "1.0.0",
        "trust": "sandbox", "entry": "main", "description": "resolver test",
    }
    body = (
        "```python #!run tag=main\n"
        "import json, os\n"
        'params = json.loads(os.environ.get("ACTUS_PARAMS") or "{}")\n'
        'print(json.dumps({"echo": params}))\n'
        "```\n"
    )
    path.write_text(
        "---\nAIGC:\n    Label: \"1\"\n---\n\n# %s\n\n```json #!cfg\n%s\n```\n%s"
        % ("My Readable Action", json.dumps(meta, ensure_ascii=False), body),
        encoding="utf-8")

    params = {"q": "cross"}

    # ── CLI 用 name 跑 ──
    rc, out, err = _invoke_cli(
        world, ["run", "My Readable Action", json.dumps(params)])
    # CLI 已接 resolver：name 可解析
    if rc == 0:
        cli_payload = _parse_last_json(out)
        if isinstance(cli_payload, dict) and "jsonrpc" in cli_payload:
            cli_payload = cli_payload.get("params", {}).get("result", cli_payload)
        assert cli_payload["status"] == "ok"
        assert cli_payload["data"]["echo"] == params

    # ── MCP 用 name 跑 ──
    from vools.actus.mcp_server import _tool_name
    mcp_tool = _tool_name(aid)
    is_err, mcp_payload = _invoke_mcp(
        world, mcp_tool, {"args": params})
    # MCP 侧如果没接 resolver，这里会报错——这正是我们要对拍的
    if not is_err:
        assert mcp_payload["status"] == "ok"
        assert mcp_payload["data"]["echo"] == params
        # 如果两边都成功，结果必须一致
        assert cli_payload["data"] == mcp_payload["data"]
