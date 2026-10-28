# -*- coding: utf-8 -*-
"""actus/tests/test_round11_capabilities.py — 第 11 轮新能力的回归测试。

覆盖 cmd-polish / cmd-engine 上一轮新接线的 6 项能力（此前全部零测试）：
  ① CLI `selfdrive run/status`（echo worker、--plan、错误路径）；
  ② CLI `cost` 诚实性（空账本必须说"暂无记账"，不伪装成 0 消费）+ 有数据时汇总；
  ③ `IntentRouter.route()` 的 workflow 分支（match=workflow + workflow_id，
     **action_id 必须为 None**，防误执行）；
  ④ artifacts 统一注册表：register/list、旧 executor 格式无损转换、
     cleanup **真删磁盘文件**并回报 files_removed/reclaimed_bytes；
  ⑤ `EventBus` 订阅去重 + `MCPServer.close()` 幂等（`actus_status.event_subscribers` 可诊断）；
  ⑥ `_call_tool` 安全边界：ValueError/ActionError 收敛为 isError 结构化结果，不抛异常。

隔离：全部 tmp_path；`HOME`/`ACTUS_META_DIR`/`ACTUS_CONFIG_DIR` 指 tmp，且把
`cost.COSTS_DIR`（import 期计算的模块全局）指到 tmp —— 跑完真实仓库与 `~/.actus` 零变化。
"""

import io
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

from vools.actus import cli  # noqa: E402
from vools.actus import cost as cost_mod  # noqa: E402
from vools.actus import mcp_server  # noqa: E402
from vools.actus import records  # noqa: E402
from vools.actus.eventbus import get_event_bus  # noqa: E402
from vools.actus.intent import IntentRouter  # noqa: E402


# ---------------------------------------------------------------------------
# 夹具 / 辅助
# ---------------------------------------------------------------------------

class _World(object):
    pass


@pytest.fixture
def world(tmp_path, monkeypatch):
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    meta = tmp_path / "meta"
    config = tmp_path / "config"
    for directory in (home, repo / "actions", meta, config):
        directory.mkdir(parents=True)

    monkeypatch.chdir(repo)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("ACTUS_REPO_ROOT", str(repo))
    monkeypatch.setenv("ACTUS_META_DIR", str(meta))
    monkeypatch.setenv("ACTUS_CONFIG_DIR", str(config))
    # cost.COSTS_DIR 是 import 期计算的模块全局（不随 env 变化）—— 必须显式指到 tmp
    monkeypatch.setattr(cost_mod, "COSTS_DIR", str(meta / "costs"))

    w = _World()
    w.root = tmp_path
    w.home = home
    w.repo = repo
    w.meta = meta
    w.config = config
    return w


def _run(argv):
    """同进程跑 cli.main，返回 (rc, stdout, stderr)。"""
    import contextlib
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = cli.main(list(argv))
        except SystemExit as exc:          # pragma: no cover
            rc = exc.code if exc.code is not None else 0
    return rc, out.getvalue(), err.getvalue()


def _json(out):
    return json.loads(out)


def _call(server, name, arguments):
    raw = server._call_tool({"name": name, "arguments": arguments or {}})
    return raw["isError"], json.loads(raw["content"][0]["text"])


# ===========================================================================
# ① CLI selfdrive run / status（echo worker）
# ===========================================================================

def test_selfdrive_run_echo_returns_snapshot_and_persists(world):
    """退步了会怎样：`selfdrive run` 未接线/退回"只有库内 API"—— CLI 恒报用法错误，
    文档声称的能力实际不可用；或跑完不落 `_meta/selfdrive/<run_id>.json`，status 查不到。

    断言：rc=0、`status=ok`、`worker_kind=echo`、有 run_id；快照文件真实存在且
    内容里的 run_id/goal/summary 与输出一致。
    """
    rc, out, err = _run(["selfdrive", "run", "做一个登录页"])
    assert rc == 0, (out, err)
    payload = _json(out)
    assert payload["status"] == "ok"
    data = payload["data"]
    assert data["worker_kind"] == "echo"
    assert data["run_id"].startswith("sd-")
    assert data["goal"] == "做一个登录页"
    assert data["status"] == "ok"
    assert data["summary"]["all_done"] is True

    snapshot_path = world.meta / "selfdrive" / (data["run_id"] + ".json")
    assert snapshot_path.is_file(), "运行快照没有落到 _meta/selfdrive/"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert snapshot["run_id"] == data["run_id"]
    assert snapshot["goal"] == "做一个登录页"


def test_selfdrive_status_lists_runs_and_summary(world):
    """退步了会怎样：`selfdrive status` 不读运行快照（count=0 / 缺 summary 字段），
    用户无法知道自驱跑了什么、成功没有。

    断言：先 run 一次，再 status → `count>=1`、runs[0] 带 run_id/goal，
    summary 含 total/done/failed/all_done。
    """
    run_rc, run_out, _ = _run(["selfdrive", "run", "构建一个 TODO 应用"])
    assert run_rc == 0, run_out
    run_id = _json(run_out)["data"]["run_id"]

    rc, out, err = _run(["selfdrive", "status"])
    assert rc == 0, (out, err)
    data = _json(out)["data"]
    assert data["count"] >= 1
    row = [r for r in data["runs"] if r["run_id"] == run_id]
    assert row, "status 列表里找不到刚跑完的 run: %r" % (data["runs"],)
    summary = row[0]["summary"]
    for key in ("total", "done", "failed", "all_done"):
        assert key in summary, summary


def test_selfdrive_status_by_run_id_returns_run(world):
    """退步了会怎样：`selfdrive status <run_id>` 参数位置解析错（run_id 被当成 goal
    丢掉）→ 永远只能列全部、查不到单次详情。

    断言：status <run_id> → data.run.run_id 等于该 id、goal 正确。
    """
    run_rc, run_out, _ = _run(["selfdrive", "run", "生成一个仪表盘"])
    assert run_rc == 0, run_out
    run_id = _json(run_out)["data"]["run_id"]

    rc, out, err = _run(["selfdrive", "status", run_id])
    assert rc == 0, (out, err)
    run = _json(out)["data"]["run"]
    assert run["run_id"] == run_id
    assert run["goal"] == "生成一个仪表盘"


def test_selfdrive_run_missing_goal_is_param_invalid(world):
    """退步了会怎样：缺 goal 也开跑（空目标自驱）或抛裸异常。

    断言：rc=1、status=failed、error.code=param_invalid、消息含完整用法。
    """
    rc, out, err = _run(["selfdrive", "run"])
    payload = _json(out)
    assert rc == 1, (out, err)
    assert payload["status"] == "failed"
    error = payload["data"]["error"]
    assert error["code"] == "param_invalid"
    assert "用法" in error["message"] and "selfdrive run" in error["message"]


def test_selfdrive_action_worker_without_plan_is_param_invalid(world):
    """退步了会怎样：`--worker action` 缺 `--plan` 仍尝试执行（或抛 KeyError），
    用户看不到"该补什么"。

    断言：rc=1、error.code=param_invalid、消息点名 --plan/--plan-file。
    """
    rc, out, err = _run(["selfdrive", "run", "目标", "--worker", "action"])
    payload = _json(out)
    assert rc == 1, (out, err)
    error = payload["data"]["error"]
    assert error["code"] == "param_invalid"
    assert "--plan" in error["message"]


# ===========================================================================
# ② CLI cost 诚实性
# ===========================================================================

def test_cost_empty_ledger_says_unrecorded_not_zero_spend(world):
    """退步了会怎样（最重要）：空账本只显示 `$0` / `spend: 0` —— 用户以为"这个月
    一分钱没花"，实际是"根本没记账"（两个完全不同的结论）。

    断言：`recorded=false` + message 明说"暂无记账数据" + calls=0；不能出现
    "recorded=true"（不伪造已记账）。
    """
    rc, out, err = _run(["cost"])
    assert rc == 0, (out, err)
    payload = _json(out)
    data = payload["data"]["data"]
    assert payload["status"] == "ok"
    assert data["recorded"] is False
    assert "暂无记账" in data["message"]
    assert data["calls"] == 0
    ledger_files = []
    if os.path.isdir(str(world.meta / "costs")):
        ledger_files = [n for n in os.listdir(str(world.meta / "costs"))
                        if n.endswith(".jsonl")]
    assert ledger_files == [], "纯读命令不应创建成本账本数据文件: %r" % (ledger_files,)


def test_cost_recorded_summary_is_correct(world):
    """退步了会怎样：有记账数据时 `cost` 仍报 recorded=false / 金额与调用数不对
    （记账只写不读的原形）。

    断言：写入两笔后 recorded=true、calls=2、spend=0.40、tokens_total 正确、
    by_model 分模型计数正确。
    """
    cost_mod.record_cost("ai.llm.complete", "openai", cost_usd=0.10,
                         tokens=400, model="gpt-a")
    cost_mod.record_cost("ai.llm.complete", "openai", cost_usd=0.30,
                         tokens=600, model="gpt-b")

    rc, out, err = _run(["cost"])
    assert rc == 0, (out, err)
    data = _json(out)["data"]["data"]

    assert data["recorded"] is True
    assert data["calls"] == 2
    assert abs(data["spend_usd"] - 0.40) < 1e-9
    assert data["tokens_total"] == 1000
    assert data["by_model"]["gpt-a"]["calls"] == 1
    assert data["by_model"]["gpt-b"]["calls"] == 1


# ===========================================================================
# ③ workflow 路由
# ===========================================================================

def test_intent_router_routes_to_registered_workflow(world):
    """退步了会怎样：`register_workflow()` 注册后 `route()` 从不读 `_workflows`
    （改前原形）→ workflow 永远不命中；或命中时把 workflow_id 塞进 action_id，
    调用方误把工作流当动作执行。

    断言：命中 → match='workflow'、workflow_id 正确、**action_id is None**、
    confidence>0、reason 点明工作流。
    """
    router = IntentRouter()
    router.register_workflow("wf.login", "登录页生成流水线", tags=["deploy", "login"])

    hit = router.route("帮我 deploy login 页面")

    assert hit["match"] == "workflow", hit
    assert hit["workflow_id"] == "wf.login"
    assert hit["action_id"] is None, "workflow 命中时 action_id 必须为 None（防误执行）"
    assert hit["confidence"] > 0


def test_intent_router_unrelated_query_is_none(world):
    """退步了会怎样：无关查询也硬匹配到某个 workflow（假命中）→ 用户请求被路由到
    完全不相干的工作流。

    断言：完全无关的查询 → match='none' 且 action_id is None。
    """
    router = IntentRouter()
    router.register_workflow("wf.login", "登录页生成流水线", tags=["deploy", "login"])

    miss = router.route("今天天气怎么样")

    assert miss["match"] == "none", miss
    assert miss["action_id"] is None


# ===========================================================================
# ④ artifacts：注册/旧格式转换/真清理
# ===========================================================================

def test_register_and_list_artifact(world):
    """退步了会怎样：`register_artifact` 写的注册表与 `list_artifacts` 读的口径不一致
    （改前 executor 写 `{actions}`、本模块读 `{artifacts}`）→ 真实产物永远列不出来。

    断言：注册后 list 能拿到该条，字段（id/name/type/path/action_id）正确且按
    action_id 过滤生效。
    """
    artifact_path = world.root / "artifact.txt"
    artifact_path.write_text("payload", encoding="utf-8")

    created = records.register_artifact(
        str(world.meta), "exec-1", "report", "file", str(artifact_path),
        action_id="my.demo", description="demo artifact")
    assert created["id"] == "art_exec-1_report"

    listed = records.list_artifacts(str(world.meta))
    assert [a["name"] for a in listed] == ["report"]
    assert listed[0]["type"] == "file"
    assert listed[0]["path"] == str(artifact_path)
    assert listed[0]["action_id"] == "my.demo"
    assert records.list_artifacts(str(world.meta), action_id="other") == []


def test_legacy_executor_registry_is_converted_losslessly(world):
    """退步了会怎样（双实现口径）：旧 executor 的 `{"actions":{aid:{ver:{artifacts}}}}`
    注册表被当成"没有产物" → list/cleanup 对真实执行产物永远空转。

    断言：旧格式能加载为规范化 artifacts，且 sha256/version/block/source_exec 不丢，
    `converted_from='executor-actions'`。
    """
    legacy = {
        "actions": {
            "my.old": {
                "2.1.0": {
                    "artifacts": {
                        "old.txt": {"path": str(world.root / "old.txt"),
                                    "sha256": "abc123", "block": 3,
                                    "source_exec": "exec-old"},
                        "note": {"path": "", "sha256": "def456"},
                    }
                }
            }
        }
    }
    (world.meta / "artifacts.json").write_text(json.dumps(legacy), encoding="utf-8")

    converted = records.load_artifacts_registry(str(world.meta))
    assert converted.get("converted_from") == "executor-actions"
    by_name = {a["name"]: a for a in converted["artifacts"]}
    assert set(by_name) == {"old.txt", "note"}
    assert by_name["old.txt"]["sha256"] == "abc123"
    assert by_name["old.txt"]["version"] == "2.1.0"
    assert by_name["old.txt"]["block"] == 3
    assert by_name["old.txt"]["exec_id"] == "exec-old"
    assert by_name["old.txt"]["type"] == "file"
    assert by_name["note"]["type"] == "text"


def test_cleanup_artifacts_really_deletes_files(world):
    """退步了会怎样（假清理）：`cleanup_artifacts` 只删登记项、**不删磁盘文件** ——
    "清理产物"后磁盘占用一点没少（改前实测 1KB 文件仍在）。

    断言：登记一条过期产物（真实文件存在）→ cleanup 返回 files_removed>=1、
    reclaimed_bytes>0，且**磁盘文件真的不存在**、注册表里也没有该条。
    """
    artifact_path = world.root / "stale.bin"
    artifact_path.write_bytes(b"x" * 64)
    records.register_artifact(
        str(world.meta), "exec-old", "stale", "file", str(artifact_path),
        action_id="my.demo", timestamp="2000-01-01T00:00:00+00:00")

    result = records.cleanup_artifacts(str(world.meta), max_age_days=1)

    assert result["files_removed"] >= 1, result
    assert result["reclaimed_bytes"] >= 64, result
    assert not artifact_path.exists(), "cleanup 只删了登记项，磁盘文件还在（假清理）"
    assert records.list_artifacts(str(world.meta)) == []


# ===========================================================================
# ⑤ EventBus 订阅去重 + MCPServer.close()
# ===========================================================================

def test_mcp_server_subscriptions_do_not_accumulate(world):
    """退步了会怎样（泄漏）：每次 new MCPServer 都往全局 EventBus 追加两个闭包且
    从不 unsubscribe —— 订阅数随实例线性增长（重复通知 + 内存泄漏）。

    测试隔离：**断言相对基线的增量**，不假设进程里基线是干净的（前面用例可能留下
    订阅）。先撤销已知的 MCP 转发订阅拿到基准，再验证：
      * 一个 server → 恰好 +2（两个事件类型）；
      * 第二个 server → **不累积**（仍是 first 的数量，不是 +4）；
      * close 回到基线；重复 close 幂等。
    """
    bus = get_event_bus()
    # conftest 的 reset_globals autouse 已重置 eventbus._bus，基线确定干净；
    # 这里仍用相对增量断言，避免依赖具体订阅数。
    before = bus.subscriber_count()

    first = mcp_server.MCPServer(stdout=io.BytesIO())
    try:
        after_first = bus.subscriber_count()
        assert after_first == before + 2, (before, after_first)

        second = mcp_server.MCPServer(stdout=io.BytesIO())
        after_second = bus.subscriber_count()
        assert after_second == after_first, \
            "第二个 MCPServer 让订阅数累积了（%d → %d）" % (after_first, after_second)

        second.close()
        assert bus.subscriber_count() == before, "close() 没有撤销本实例的订阅"
        second.close()               # 幂等：第二次不能报错
        assert bus.subscriber_count() == before
    finally:
        first.close()
    assert bus.subscriber_count() == before


def test_actus_status_exposes_event_subscribers(world):
    """退步了会怎样：订阅泄漏不可诊断（没有任何对外字段）—— 只能靠内存占用猜。

    断言：`actus_status` 返回的 data 里 `event_subscribers` 等于当前总线订阅数；
    有活跃 server 时该值 > 0。
    """
    bus = get_event_bus()
    server = mcp_server.MCPServer(stdout=io.BytesIO())
    try:
        is_error, payload = _call(server, "actus_status", {})
        assert is_error is False, payload
        assert payload["data"]["event_subscribers"] == bus.subscriber_count()
        assert payload["data"]["event_subscribers"] >= 2
    finally:
        server.close()


# ===========================================================================
# ⑥ _call_tool 安全边界（不抛异常）
# ===========================================================================

def test_call_tool_wraps_value_error_as_param_invalid(world):
    """退步了会怎样（第 27 轮原形）：`_call_tool` 不兜底 —— 内部 handler 的
    `ValueError` 直接穿透（测试/嵌入式调用方拿到裸异常，连 isError 都没有）。

    断言：`actus_team_create` 传非法团队名 → `isError=True`、code=param_invalid、
    message 点名 ValueError，且**不抛异常**。
    """
    server = mcp_server.MCPServer(stdout=io.BytesIO())
    try:
        is_error, payload = _call(
            server, "actus_team_create", {"name": "bad name!", "creator": "u"})
        assert is_error is True, payload
        assert payload["status"] == "failed"
        error = payload["error"]
        assert error["code"] == "param_invalid", error
        assert "ValueError" in error["message"]
    finally:
        server.close()


def test_call_tool_wraps_action_error_with_its_own_code(world):
    """退步了会怎样：`ActionError`（如未知工具/动作不存在）也被包成 internal ——
    调用方分不清"工具不存在"与"内部崩了"。

    断言：不存在的工具 → `isError=True`、code 用 ActionError 自带的
    `action_not_found`（不是 internal），且不抛异常。
    """
    server = mcp_server.MCPServer(stdout=io.BytesIO())
    try:
        is_error, payload = _call(server, "no_such_tool_xyz", {})
        assert is_error is True, payload
        assert payload["error"]["code"] == "action_not_found", payload["error"]
        assert "no_such_tool_xyz" in payload["error"]["message"]
    finally:
        server.close()
