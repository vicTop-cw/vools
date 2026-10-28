# -*- coding: utf-8 -*-
"""actus/tests/test_mcp_handlers.py — MCP `_call_tool` 高危写操作 handler 的行为契约。

为什么要这份文件（测试套件自审结论）
------------------------------------
`mcp_server.py` 有 2400+ 行 / 46 个 `_handle_*`，但此前测试只覆盖 `_tool_name`、
`resolve_action_arg`、`text_result` 和源码字符串 —— **`_call_tool` 的派发与各
handler 行为零覆盖**。审计探针实测：把 `_call_tool` / `_list_tools` / `handle` /
`serve` 全部改成抛异常，相关 60 个测试仍然全绿（最大的假绿灯）。

本文件按风险挑 12 个写操作/高危 handler，每个至少钉四件事：
  1. **正常路径** → `isError=False` + 返回体含**具体字段/值**（不是只断言 isError）；
  2. **缺参** → `isError=True` + `param_invalid` + **点名**缺哪些参数（统一校验层，
     改前会静默写空名注册表/空 id 私有动作/空团队）；
  3. **错误参数类型** → 结构化错误（不是异常穿到协议层）；
  4. **副作用落在隔离目录**（HOME / ACTUS_META_DIR / ACTUS_REPO_ROOT 全部指 tmp）。
另有一条**总括门禁**：遍历 tools/list 中所有声明了 required 的工具，空参数调用必须
统一返回 param_invalid —— 这条能防止「派发层整体坏掉但测试仍绿」。

隔离：`tmp_path` 假仓库（复制 contracts/action.schema.json 供 scaffold/author 校验），
HOME/USERPROFILE 指 tmp（visibility 引擎的 `~/.actus` 因此被圈住），跑完不碰真实仓库。

py3.6 兼容：标准库 + % 格式化。
"""

import json
import os
import shutil
import sys

import pytest

# 与同目录其它 actus 测试一致：先跑本地源码引导，让 vools.actus 命中源码树
# 而不是 site-packages 的发布 wheel（否则测的是旧包，结论是假的）。
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

from vools.actus import mcp_server  # noqa: E402
from vools.actus.errors import ActionError, is_failure_status  # noqa: E402


# ---------------------------------------------------------------------------
# 夹具与工具
# ---------------------------------------------------------------------------

class _World(object):
    pass


@pytest.fixture
def world(tmp_path, monkeypatch):
    """tmp 假仓库 + 隔离 HOME：MCP 写操作的一切副作用都必须落在这里。"""
    repo = tmp_path / "repo"
    actions = repo / "actions"
    meta = repo / "_meta"
    home = tmp_path / "home"
    config = tmp_path / "config"
    for directory in (actions, meta, home, config):
        directory.mkdir(parents=True)

    # scaffold / author 的首次校验要 contracts/action.schema.json（否则校验报缺文件）
    schema_src = os.path.join(_ROOT, "contracts")
    if os.path.isdir(schema_src):
        shutil.copytree(schema_src, str(repo / "contracts"))

    monkeypatch.chdir(repo)
    monkeypatch.setenv("ACTUS_REPO_ROOT", str(repo))
    monkeypatch.setenv("ACTUS_META_DIR", str(meta))
    monkeypatch.setenv("ACTUS_CONFIG_DIR", str(config))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))

    w = _World()
    w.root = tmp_path
    w.repo = repo
    w.actions = actions
    w.home = home
    w.meta = meta
    w.server = mcp_server.MCPServer()
    return w


def _call(world, tool, arguments):
    """调用 `_call_tool`，返回 (isError, 解析后的 payload, 原始 result)。"""
    raw = world.server._call_tool({"name": tool, "arguments": arguments})
    assert isinstance(raw, dict) and "content" in raw and "isError" in raw
    payload = json.loads(raw["content"][0]["text"])
    return raw["isError"], payload, raw


def _tools(world):
    return {tool["name"]: tool for tool in world.server._list_tools()}


def _required_of(world, tool):
    return list((_tools(world).get(tool, {}).get("inputSchema") or {}).get("required") or [])


def _snapshot(root):
    """目录内容快照：{相对路径: 大小, sha256}（用于断言副作用范围）。"""
    import hashlib
    out = {}
    for dirpath, _dirnames, filenames in os.walk(str(root)):
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, str(root)).replace(os.sep, "/")
            digest = hashlib.sha256()
            with open(full, "rb") as handle:
                for chunk in iter(lambda: handle.read(65536), b""):
                    digest.update(chunk)
            out[rel] = (os.path.getsize(full), digest.hexdigest())
    return out


def _write_action(path, action_id):
    """写一个最小可解析动作（JSON #!cfg）。"""
    meta = {"id": action_id, "name": action_id, "version": "1.0.0", "entry": "main"}
    path.write_text(
        "---\nAIGC:\n    Label: \"1\"\n---\n\n# %s\n\n```json #!cfg\n%s\n```\n"
        % (action_id, json.dumps(meta, ensure_ascii=False)), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# 1) 12 个高危 handler：缺参统一门禁（改前会静默写空 key）
# ---------------------------------------------------------------------------

_WRITE_TOOLS = [
    ("actus_registry_add", ["name", "url"]),
    ("actus_registry_remove", ["name"]),
    ("actus_private_add", ["action_id"]),
    ("actus_private_remove", ["action_id"]),
    ("actus_team_create", ["name", "creator"]),
    ("actus_team_add_member", ["team", "user_id"]),
    ("actus_team_remove_member", ["team", "user_id"]),
    ("actus_visibility_set", ["action_id", "visibility"]),
    ("actus_scaffold", ["description"]),
    ("actus_author", ["action_id", "instruction"]),
    ("actus_publish", ["action_id"]),
    ("actus_execute", ["language", "code"]),
]


@pytest.mark.parametrize("tool,missing", _WRITE_TOOLS,
                         ids=[item[0] for item in _WRITE_TOOLS])
def test_write_tool_missing_required_params_is_param_invalid(world, tool, missing):
    """退步了会怎样：统一必需参数校验层被去掉/漏掉某个工具 → 空参数调用会落到
    handler：改前实测会把**空名注册表、空 id 私有动作、teams/.json（team=""）**
    写进配置存储，并回 `status=ok`（静默数据污染）。

    断言：isError=True、code=param_invalid、消息点名每个缺失参数、
    details.missing == 声明的 required 集合。
    """
    is_error, payload, _raw = _call(world, tool, {})

    assert is_error is True, "%s 空参数必须失败: %r" % (tool, payload)
    err = payload.get("error") or {}
    assert err.get("code") == "param_invalid", err
    for name in missing:
        assert name in (err.get("message") or ""), \
            "错误消息没有点名缺失参数 %r: %r" % (name, err)
    details = err.get("details") or {}
    assert sorted(details.get("missing") or []) == sorted(missing), details
    assert sorted(details.get("required") or []) == sorted(_required_of(world, tool))


def test_arguments_must_be_json_object(world):
    """退步了会怎样：`arguments` 是 null/数组/字符串时直接 `.get()` →
    AttributeError 穿透到协议层（客户端只看到 internal error，不知道是参数形状错）。

    断言：结构化 param_invalid，消息说明 arguments 必须是 JSON 对象。
    """
    raw = world.server._call_tool({"name": "actus_list", "arguments": [1, 2]})
    payload = json.loads(raw["content"][0]["text"])
    assert raw["isError"] is True
    assert (payload.get("error") or {}).get("code") == "param_invalid"
    assert "arguments" in (payload["error"].get("message") or "")


# ---------------------------------------------------------------------------
# 2) 总括门禁：所有声明 required 的工具，空参数都必须 param_invalid
# ---------------------------------------------------------------------------

def test_all_tools_with_required_params_reject_empty_args(world):
    """退步了会怎样（审计探针 B 的对应）：派发层整体坏掉（如 `_call_tool`/handler
    全改抛异常）或统一校验被移除时，逐 handler 的用例可能恰好没覆盖到 ——
    这条遍历 **tools/list 中所有声明 required 的工具**，空参数调用必须统一
    param_invalid 且点名缺失参数；任何例外都会红。

    断言：required 工具数 >= 35（当前 35；数量下降说明 schema 被删减），
    每个都返回 param_invalid + details.missing == 声明 required。
    """
    tools = _tools(world)
    required_tools = {name: (t.get("inputSchema") or {}).get("required") or []
                      for name, t in tools.items()
                      if (t.get("inputSchema") or {}).get("required")}
    assert len(required_tools) >= 35, \
        "声明了 required 的工具只有 %d 个（schema 是否被删减？）" % len(required_tools)

    failures = []
    for name, required in required_tools.items():
        is_error, payload, raw = _call(world, name, {})
        err = payload.get("error") or {}
        ok = (is_error is True and err.get("code") == "param_invalid"
              and sorted(err.get("details", {}).get("missing") or []) == sorted(required))
        if not ok:
            failures.append((name, payload))
    assert not failures, "这些工具的缺参门禁失效: %r" % (failures,)


# ---------------------------------------------------------------------------
# 3) 总括门禁：无必需参数的**只读**工具必须真能调用（防派发层整体坏掉）
# ---------------------------------------------------------------------------

_SAFE_NO_REQUIRED = [
    "actus_list", "actus_status", "actus_runtimes", "actus_records_list",
    "actus_artifacts_list", "actus_triggers_list", "actus_triggers_status",
    "actus_registry_list", "actus_private_list", "actus_team_list",
    # 第 28 轮新增：查 LLM 成本账本（month 可选、无必需参数）。纯只读：
    # 空账本时返回 recorded=False + 明确 message，不写盘、不报错。
    "actus_cost",
    # 第 29 轮新增：校验动作契约（action_id 可选；缺省校验全仓）。纯读：
    # load_index/get_action + split_validation，空仓返回 status=ok、valid=True。
    "actus_validate",
]

#: 无必需参数但**不在本文件调用**的工具（写操作/会起服务/依赖本机动作），
#: 显式登记理由，避免「新工具悄悄漏测」。
_DEFERRED_NO_REQUIRED = {
    "actus_search": "只读但依赖真实索引内容，查询语义由 CLI/其它测试覆盖",
    "actus_recommend": "依赖 AI provider，非确定性",
    "actus_vault_list": "读密钥库，vault 行为由 test_vault2_replay 覆盖",
    "actus_probe": "真跑环境探测（~2s），由 test_probe*.py 覆盖",
    "actus_records_export": "会按参数写导出文件，属写操作",
    "actus_artifacts_cleanup": "会删除产物（写操作）",
    "actus_evolve_status": "读进化状态，属 evolve 家族（另有测试线）",
    "actus_evolve_list": "同上",
    "actus_webhook_start": "会前台起服务（阻塞）",
    "actus_webhook_start_background": "会起后台服务",
    "actus_webhook_stop": "会改全局 webhook 状态",
    "actus_webhook_status": "读 webhook 全局状态（进程级单例）",
    "actus_webhook_logs": "同上",
    "actus_project_load": "读项目文件，project 家族归 cmd-engine 测试线",
    "actus_project_detect": "同上",
    # 第 29 轮新增：系统健康检查（磁盘/网络/编译器/Vault 真探测）。慢且随环境波动，
    # 不适合放进本文件的"只读可安全调用"批量里；待专门派单补行为用例。
    "actus_health": "真跑系统健康检查（慢、随环境波动），待 health 专项测试",
    # 第 30 轮新增：旧格式 vault 密钥行显式迁移（默认**写 db**；dry_run=true 只统计）。
    # 属写操作，需专用 v1/v2 混合夹具，待派单补行为用例。
    "actus_vault_migrate": "默认写 db（legacy→行级加密迁移）；dry_run 可选，属写操作",
    "actus_project_build": "会执行构建命令（写操作）",
    "actus_project_test": "会执行测试命令（写操作）",
    "actus_project_status": "同上",
    "actus_project_validate": "同上",
}


@pytest.mark.parametrize("tool", _SAFE_NO_REQUIRED)
def test_safe_readonly_tools_are_callable(world, tool):
    """退步了会怎样：`_call_tool` 对**无必需参数**的工具（如 actus_records_list）
    整体抛异常 / 返回非 MCP 结构 —— 逐 handler 的缺参用例测不到（没有缺参可测），
    正是审计探针「全改抛异常仍绿」的缺口。

    断言：调用返回结构化 MCP result（content+isError），不抛异常；
    只读工具应成功（isError=False 且 payload 是 dict）。
    """
    _is_error, payload, raw = _call(world, tool, {})
    assert isinstance(raw.get("content"), list) and raw["content"]
    assert isinstance(payload, dict), "%s 返回体不是 JSON 对象: %r" % (tool, payload)
    assert raw["isError"] is False, "%s 作为只读工具应成功: %r" % (tool, payload)


def test_no_required_tool_inventory_has_no_silent_gaps(world):
    """退步了会怎样：工具表新增「无必需参数」的工具但既没被测、也没登记理由 →
    它可能静默成为新的覆盖缺口。这条把清单钉住：无 required 的工具必须
    要么在 `_SAFE_NO_REQUIRED`（已调用），要么在 `_DEFERRED_NO_REQUIRED`（有理由），
    要么是 `actus_basics_*` 种子动作工具（数量随种子目录动态变化）。
    """
    tools = _tools(world)
    no_required = [name for name, t in tools.items()
                   if not ((t.get("inputSchema") or {}).get("required") or [])]
    unexpected = []
    for name in no_required:
        if name in _SAFE_NO_REQUIRED or name in _DEFERRED_NO_REQUIRED:
            continue
        if name.startswith("actus_basics_"):
            continue          # 种子动作工具：随包内种子目录变化，单独由动作测试覆盖
        unexpected.append(name)
    assert not unexpected, \
        "出现未登记的无必需参数工具（新工具需补测试或登记理由）: %r" % (unexpected,)


# ---------------------------------------------------------------------------
# 4) 正常路径：具体返回字段（不是只断言 isError False）
# ---------------------------------------------------------------------------

def test_execute_runs_python_and_returns_stdout(world):
    """退步了会怎样：执行结果字段被改名/丢失（stdout/exit_code/language），
    或非零退出码被报成成功。断言具体值：stdout 含标记、stderr 空、exit_code 0。
    """
    is_error, payload, _raw = _call(
        world, "actus_execute", {"language": "python", "code": "print('MCP-HI')"})

    assert is_error is False, payload
    assert payload["status"] == "ok"
    assert payload["language"] == "python"
    assert "MCP-HI" in payload["stdout"]
    assert payload["stderr"] == ""
    assert payload["exit_code"] == 0


def test_execute_rejects_non_numeric_timeout(world):
    """退步了会怎样：timeout 传字符串被静默忽略（改前在 Windows 上 SIGALRM 分支
    直接失效，timeout 参数被忽略且报成功）。断言 param_invalid + 点名 timeout。
    """
    is_error, payload, _raw = _call(
        world, "actus_execute", {"language": "python", "code": "1", "timeout": "abc"})
    err = payload.get("error") or {}
    assert is_error is True
    assert err.get("code") == "param_invalid"
    assert "timeout" in (err.get("message") or "")


def test_scaffold_normal_path_creates_action_and_returns_validation(world):
    """退步了会怎样：scaffold handler 只回 `isError=False` 却其实没写文件，
    或返回体缺 path/id/validation（调用方无法继续下一步）。

    断言具体值：文件真的落在隔离仓库 actions/ 下、id 正确、首次校验 valid=True。
    """
    is_error, payload, _raw = _call(
        world, "actus_scaffold",
        {"description": "生成一个问候动作", "action_id": "test.mcp.hello"})

    assert is_error is False, payload
    assert payload["id"] == "test.mcp.hello"
    assert payload["validation"] == {"valid": True, "errors": []}
    produced = os.path.join(str(world.repo), "actions", "hello.actus.md")
    assert os.path.normcase(payload["path"]) == os.path.normcase(produced)
    assert os.path.isfile(produced), "handler 报成功但文件不存在"
    assert (world.repo / "tests" / "test_hello.py").is_file(), \
        "audit 级动作应生成配套测试骨架"


def test_registry_write_roundtrip_and_isolated_side_effects(world):
    """退步了会怎样：写操作没有真的落盘（假成功）、或落到真实 HOME。
    断言：add→list 能看到 name/url/priority；remove→removed；再 remove → not_found；
    副作用只出现在 tmp HOME 的 `.actus/config.json`，仓库 actions/ 零变化。
    """
    repo_before = _snapshot(world.actions)

    is_error, added, _raw = _call(
        world, "actus_registry_add",
        {"name": "corp", "url": "https://corp/registry.json", "priority": 3})
    assert is_error is False, added
    reg = added["registry"]
    assert (reg["name"], reg["url"], reg["priority"]) == (
        "corp", "https://corp/registry.json", 3)

    is_error, listed, _raw = _call(world, "actus_registry_list", {})
    names = [item["name"] for item in listed["registries"]]
    assert "corp" in names, names

    is_error, removed, _raw = _call(world, "actus_registry_remove", {"name": "corp"})
    assert is_error is False and removed["removed"] == "corp"

    is_error, missing, _raw = _call(world, "actus_registry_remove", {"name": "corp"})
    assert is_error is True and missing["status"] == "not_found"

    assert (world.home / ".actus" / "config.json").is_file(), \
        "注册表没有落到隔离 HOME 的配置里（假成功或写到了真实 HOME）"
    assert _snapshot(world.actions) == repo_before, "只写配置的操作改了仓库 actions/"


def test_private_action_roundtrip(world):
    """退步了会怎样：私有动作索引写不进/读不出（改前空 id 会写 `private/index.json`
    污染）。断言 add → list 含 action_id + visibility=private → remove → 消失。
    """
    is_error, added, _raw = _call(
        world, "actus_private_add", {"action_id": "my.priv", "author": "alice"})
    assert is_error is False and added["action_id"] == "my.priv"

    is_error, listed, _raw = _call(world, "actus_private_list", {})
    entries = {item["action_id"]: item for item in listed["actions"]}
    assert "my.priv" in entries
    assert entries["my.priv"]["visibility"] == "private"
    assert entries["my.priv"]["author"] == "alice"
    assert listed["count"] == len(entries)

    is_error, removed, _raw = _call(
        world, "actus_private_remove", {"action_id": "my.priv"})
    assert is_error is False and removed["removed"] == "my.priv"
    _is_error, after, _raw = _call(world, "actus_private_list", {})
    assert "my.priv" not in {i["action_id"] for i in after["actions"]}


def test_team_roundtrip_with_roles(world):
    """退步了会怎样：团队/成员写入形状错误（空 team/空 user 落盘）或角色丢失。

    断言：create → creator 是 admin；add_member(viewer) → list 两人且角色正确；
    remove_member → 只剩 creator；移除不存在的成员 → isError=True。
    """
    is_error, created, _raw = _call(
        world, "actus_team_create", {"name": "core", "creator": "alice"})
    assert is_error is False, created
    team = created["team"]
    assert team["team"] == "core"
    assert [(m["id"], m["role"]) for m in team["members"]] == [("alice", "admin")]

    is_error, added, _raw = _call(
        world, "actus_team_add_member",
        {"team": "core", "user_id": "bob", "role": "viewer"})
    assert is_error is False, added
    assert (added["team"], added["user"], added["role"]) == ("core", "bob", "viewer")

    _is_error, listed, _raw = _call(world, "actus_team_list", {"team": "core"})
    roles = {m["id"]: m["role"] for m in listed["team"]["members"]}
    assert roles == {"alice": "admin", "bob": "viewer"}, roles

    is_error, removed, _raw = _call(
        world, "actus_team_remove_member", {"team": "core", "user_id": "bob"})
    assert is_error is False and removed["removed"] == "bob"

    is_error, missing, _raw = _call(
        world, "actus_team_remove_member", {"team": "core", "user_id": "ghost"})
    assert is_error is True, missing


def test_registry_priority_wrong_type_is_structured_error(world):
    """退步了会怎样：priority 传字符串被原样写进 ~/.actus/config.json →
    之后**任何进程**构造 visibility 引擎都会 ValueError，注册表/团队/可见性全挂
    （审计实测踩到过）。断言 param_invalid + 点名 priority，且配置未被写坏。
    """
    is_error, payload, _raw = _call(
        world, "actus_registry_add",
        {"name": "r", "url": "u", "priority": "10"})
    err = payload.get("error") or {}
    assert is_error is True
    assert err.get("code") == "param_invalid"
    assert "priority" in (err.get("message") or "")

    # 配置里不能出现坏 priority（否则后续构造引擎会炸）
    config_file = world.home / ".actus" / "config.json"
    if config_file.is_file():
        data = json.loads(config_file.read_text(encoding="utf-8"))
        for reg in (data.get("registries") or {}).values():
            assert isinstance(reg.get("priority"), int), reg


# ---------------------------------------------------------------------------
# 5) 可见性：校验语义 + 持久化契约（cmd-engine 已收口为真写落盘）
# ---------------------------------------------------------------------------

def test_visibility_set_validates_level_and_team(world):
    """退步了会怎样：非法级别 / team 级缺 team 参数也返回成功（假成功）。

    语义区分（收口后的正确契约）：
      * 非法级别 / team 缺 team —— **与动作是否存在无关**，必须先被参数校验拦下；
      * 合法级别 —— set 是真写落盘，必须先能解析到动作（对不存在的 my.x 应
        返回 action_not_found，而不是回显成功）。所以这里先播种动作再断言成功；
        「写进去了且能读回」由 `test_visibility_set_persists_and_is_readable` 覆盖。
    """
    _write_action(world.actions / "my.actus.md", "my.x")

    is_error, payload, _raw = _call(
        world, "actus_visibility_set",
        {"action_id": "my.x", "visibility": "weird"})
    assert is_error is True and payload["status"] == "invalid"
    assert "weird" in payload["message"]

    is_error, payload, _raw = _call(
        world, "actus_visibility_set",
        {"action_id": "my.x", "visibility": "team"})
    assert is_error is True and "team" in payload["message"]

    is_error, payload, _raw = _call(
        world, "actus_visibility_set",
        {"action_id": "my.x", "visibility": "unlisted"})
    assert is_error is False, payload
    assert (payload["action_id"], payload["visibility"]) == ("my.x", "unlisted")


def test_visibility_set_on_missing_action_is_action_not_found(world):
    """退步了会怎样：对**不存在的动作**调 set 也回显成功（假成功契约复活）——
    真实现必须先解析动作、解析不到就报 action_not_found，不能假装写成功。
    """
    is_error, payload, _raw = _call(
        world, "actus_visibility_set",
        {"action_id": "no.such.action", "visibility": "unlisted"})
    assert is_error is True, payload
    assert (payload.get("error") or {}).get("code") == "action_not_found", payload


def test_visibility_set_persists_and_is_readable(world):
    """退步了会怎样：设置可见性只回显、不持久化，调用方以为已生效。

    断言正确契约：设 private 后，`actus_visibility_get` 必须能读到 private
    （cmd-engine 已改为与 CLI 共用 write_action_visibility，真写动作文件）。
    """
    _write_action(world.actions / "vis.actus.md", "test.mcp.vis")
    is_error, payload, _raw = _call(
        world, "actus_visibility_set",
        {"action_id": "test.mcp.vis", "visibility": "private"})
    assert is_error is False, payload

    _is_error, readback, _raw = _call(
        world, "actus_visibility_get", {"action_id": "test.mcp.vis"})
    assert readback.get("visibility") == "private", readback


# ---------------------------------------------------------------------------
# 6) author / publish：handler 与引擎结果的状态映射（统一判据）
# ---------------------------------------------------------------------------

def test_author_maps_engine_status_to_is_error(monkeypatch, world):
    """退步了会怎样：author 的 `needs_fix`（AI 改了但校验不过）被当成成功
    （MCP 曾只认 'failed'）→ 调用方拿 isError=False 继续往下走。

    用 monkeypatch 引擎返回固定状态（handler 契约测试，不测 AI 本身）：
    ok → isError False；needs_fix → isError True；ActionError → 结构化 error。
    """
    import vools.actus.author as author_mod

    monkeypatch.setattr(author_mod, "author_action",
                        lambda aid, instruction, repo_root=None: {
                            "status": "ok", "action_id": aid})
    is_error, payload, _raw = _call(
        world, "actus_author", {"action_id": "a.b", "instruction": "x"})
    assert is_error is False and payload["status"] == "ok"

    monkeypatch.setattr(author_mod, "author_action",
                        lambda aid, instruction, repo_root=None: {
                            "status": "needs_fix", "action_id": aid})
    is_error, payload, _raw = _call(
        world, "actus_author", {"action_id": "a.b", "instruction": "x"})
    assert is_error is True, "needs_fix 必须算失败（统一判据）"

    def boom(aid, instruction, repo_root=None):
        raise ActionError("action_invalid", "坏动作")

    monkeypatch.setattr(author_mod, "author_action", boom)
    is_error, payload, _raw = _call(
        world, "actus_author", {"action_id": "a.b", "instruction": "x"})
    assert is_error is True
    assert (payload.get("error") or {}).get("code") == "action_invalid"


def test_publish_maps_engine_status_to_is_error(monkeypatch, world):
    """退步了会怎样：publish 的 `needs_human_confirm` / `rejected` 被当成成功，
    或 ActionError 穿透协议层。断言与 `errors.is_failure_status` 同一判据。
    """
    import vools.actus.author as author_mod

    monkeypatch.setattr(author_mod, "publish_action",
                        lambda aid, repo_root=None, force=False: {
                            "status": "published", "action_id": aid})
    is_error, payload, _raw = _call(world, "actus_publish", {"action_id": "a.b"})
    assert is_error is False and payload["status"] == "published"

    monkeypatch.setattr(author_mod, "publish_action",
                        lambda aid, repo_root=None, force=False: {
                            "status": "needs_human_confirm", "action_id": aid})
    is_error, payload, _raw = _call(world, "actus_publish", {"action_id": "a.b"})
    assert is_error is True
    assert is_failure_status(payload["status"]) is True

    def boom(aid, repo_root=None, force=False):
        raise ActionError("visibility_denied", "不可发布")

    monkeypatch.setattr(author_mod, "publish_action", boom)
    is_error, payload, _raw = _call(world, "actus_publish", {"action_id": "a.b"})
    assert is_error is True
    assert (payload.get("error") or {}).get("code") == "visibility_denied"


def test_author_and_publish_real_call_never_raise_through(world):
    """退步了会怎样：真实调用（无 AI / 坏动作）时异常穿透到协议层，客户端只看到
    internal error。断言：真实调用返回结构化 payload（含 action_id / pipeline），
    且 isError 与 payload.status 的判据一致（status 存在时）。
    """
    _write_action(world.actions / "real.actus.md", "test.mcp.real")

    is_error, payload, _raw = _call(
        world, "actus_author",
        {"action_id": "test.mcp.real", "instruction": "改一下"})
    assert isinstance(payload, dict)
    assert payload.get("action_id") == "test.mcp.real"
    assert "pipeline" in payload, payload
    if "status" in payload:
        assert is_error is is_failure_status(payload["status"])

    is_error, payload, _raw = _call(
        world, "actus_publish", {"action_id": "test.mcp.real"})
    assert isinstance(payload, dict)
    assert payload.get("action_id") == "test.mcp.real"
    assert "pipeline" in payload, payload
    if "status" in payload:
        assert is_error is is_failure_status(payload["status"])


# ===========================================================================
# 7) 第 28 轮新增：actus_run_code（旧名 actus_execute 为 deprecated 别名）
#    与 actus_list 的 tool 字段 / actus_cost 只读契约
# ===========================================================================

def test_run_code_and_deprecated_alias_share_behavior(world):
    """退步了会怎样：`actus_execute` 改名 `actus_run_code` 时旧名被删/变成空壳 ——
    已接入的 Agent/脚本按旧名调用会 404 或拿到不一致结果。

    断言：两个名字都能跑 `print(42)`，isError=False、stdout 含 42、exit_code=0，
    且两者返回体**完全一致**（同一 handler，不是两套实现）。
    """
    run_error, run_payload, _raw = _call(
        world, "actus_run_code", {"language": "python", "code": "print(42)"})
    alias_error, alias_payload, _raw = _call(
        world, "actus_execute", {"language": "python", "code": "print(42)"})

    for label, is_error, payload in (
            ("actus_run_code", run_error, run_payload),
            ("actus_execute(deprecated)", alias_error, alias_payload)):
        assert is_error is False, (label, payload)
        assert payload["status"] == "ok", (label, payload)
        assert payload["language"] == "python"
        assert "42" in payload["stdout"], (label, payload)
        assert payload["stderr"] == ""
        assert payload["exit_code"] == 0

    assert run_payload == alias_payload, \
        "旧名与主名返回体不一致（应复用同一个 handler）"


def test_tool_inventory_registers_run_code_and_deprecated_alias(world):
    """退步了会怎样：工具清单里只出现主名或只出现旧名 —— AI 客户端按清单调用
    旧名会"工具不存在"；别名也没有任何提示说明它将被移除。

    断言：tools/list 同时含 `actus_run_code` 与 `actus_execute`；两者 required 都是
    ['language','code']；旧名 description 明确标注 deprecated/已改名。
    """
    tools = _tools(world)
    assert "actus_run_code" in tools
    assert "actus_execute" in tools, "deprecated 别名必须仍在工具清单里（不能是空壳）"

    for name in ("actus_run_code", "actus_execute"):
        required = (tools[name].get("inputSchema") or {}).get("required") or []
        assert required == ["language", "code"], (name, required)

    alias_desc = tools["actus_execute"].get("description") or ""
    assert ("已改名" in alias_desc) or ("deprecated" in alias_desc.lower()), \
        "旧名 description 必须说明已改名/即将移除: %r" % (alias_desc,)


def test_actus_list_rows_expose_tool_field(world):
    """退步了会怎样：`actus_list` 只给动作 id 不给工具名 —— AI 客户端无法把
    "有哪些动作"映射到"该调哪个 MCP tool"（第 28 轮新增 tool 字段的契约）。

    断言：每行都有非空 `tool`，且等于 `_tool_name(id)`；至少包含动作 demo 的那行。
    """
    is_error, payload, _raw = _call(world, "actus_list", {})
    assert is_error is False, payload
    rows = payload["data"]["actions"]
    assert rows, payload

    for row in rows:
        assert row.get("tool"), "actus_list 行缺少 tool 字段: %r" % (row,)
        assert row["tool"] == mcp_server._tool_name(row["id"]), row


def test_cost_tool_reports_unrecorded_honestly(world):
    """退步了会怎样：空账本返回 `spend_usd=0` 却不说明"没有记账" —— 调用方会把
    "没数据"误读成"本月免费"。

    断言：`actus_cost{}` → isError=False、`recorded=False`、message 明说暂无记账、
    附带 budget 字段（不伪造已消费数据）。
    """
    is_error, payload, _raw = _call(world, "actus_cost", {})
    data = payload["data"]

    assert is_error is False, payload
    assert payload["status"] == "ok"
    assert data["recorded"] is False
    assert "暂无记账" in data["message"]
    assert data["calls"] == 0
    assert "budget" in data and data["budget"]["spent_usd"] == 0
