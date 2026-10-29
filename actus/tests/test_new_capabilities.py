# -*- coding: utf-8 -*-
"""actus/tests/test_new_capabilities.py — 本轮新增能力的专项验收测试。

为什么单独一份：下面这些能力是近期修的「新东西」，但此前**零专项覆盖**
（或只有实现者手测）。它们有一个共同点 —— 退步时**不会崩**，只会静默给出
错误结论（假成功 / 假空事件流 / 用到伪造缓存 / 缓存命中却标记为 probe），
所以必须断言具体行为，而不是「不抛异常」。

覆盖清单（每条用例的 docstring 都写了「退步了会怎样」）：
1. `errors.is_failure_status` / `OPERATION_OK_STATUSES` —— CLI 与 MCP **共用同一份判据**；
2. `eventbus` 事件落盘 —— 发布可跨「内存清空」读到、三态区分、坏行计数、
   轮转保留尾部、落盘失败不影响 publish、开关可关、`events` CLI 只读且 `--json/--limit/--type` 正确；
3. `probe.cache` 防事故三件套 —— 正常缓存命中；改 items/host/version、删字段 → 精确原因拒绝；
4. `probe.ProbeReport.report_source` —— `--force-refresh` → "probe"，缓存命中 → "cache"，
   且人类可读摘要对缓存来源有显式标注；
5. `probe.actions` 多根 —— `extra["roots"]` 完整、`action_count` = 本地 + 包内种子（动态算）。

隔离：全部走 `tmp_path` + `ACTUS_META_DIR` / `ACTUS_REPO_ROOT` / `HOME` 与
`probe.cache._CACHE_FILE` 覆盖，**零仓库污染**（跑完真实仓库 `git status` 不变）。

py3.6 兼容：只用标准库，% 格式化，不用 f-string。
"""

import io
import json
import os
import pathlib
import sys
import contextlib

import pytest

# 与同目录其它 actus 测试一致：先跑本地源码引导，让 vools.actus 命中源码树
# 而不是 site-packages 的发布 wheel（否则测的是旧包，结论是假的）。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

import vools.actus.cli as cli  # noqa: E402
import vools.actus.eventbus as eventbus  # noqa: E402
import vools.actus.mcp_server as mcp_server  # noqa: E402
from vools.actus.errors import (  # noqa: E402
    OPERATION_OK_STATUSES,
    is_failure_status,
)
from vools.actus.probe import cache as cache_mod  # noqa: E402
from vools.actus.probe import format_summary, probe  # noqa: E402
from vools.actus.probe.actions import ActionsProber  # noqa: E402
from vools.actus.probe.base import ProbeItem  # noqa: E402
from vools.actus.probe.report import ProbeReport  # noqa: E402


# ---------------------------------------------------------------------------
# 夹具：tmp 世界（meta / repo / home / probe cache 全部隔离）
# ---------------------------------------------------------------------------

class _World(object):
    pass


@pytest.fixture(autouse=True)
def world(tmp_path, monkeypatch):
    """所有用例的默认世界：ACTUS_META_DIR / REPO_ROOT / HOME / probe cache 都指 tmp。"""
    meta = tmp_path / "meta"
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    repo.mkdir()
    home.mkdir()

    monkeypatch.setenv("ACTUS_META_DIR", str(meta))
    monkeypatch.setenv("ACTUS_REPO_ROOT", str(repo))
    monkeypatch.setenv("ACTUS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("ACTUS_EVENTS_PERSIST", raising=False)

    # probe 缓存路径覆盖（cache._cache_path() 显式支持测试覆盖）
    monkeypatch.setattr(cache_mod, "_CACHE_FILE", str(tmp_path / "probe_cache.json"))
    monkeypatch.setattr(cache_mod, "_CACHE_DIR", str(tmp_path))

    w = _World()
    w.root = tmp_path
    w.meta = meta
    w.repo = repo
    w.home = home
    return w


def _invoke(argv):
    """同进程跑 cli.main(argv)，返回 (rc, stdout, stderr)。"""
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cli.main(list(argv))
    except SystemExit as exc:
        rc = exc.code if exc.code is not None else 0
    return rc, out.getvalue(), err.getvalue()


def _valid_probe_report():
    """构造一份**形状合法**的 ProbeReport（含四个维度 + items + 自洽 summary）。

    与真实 probe() 的产物同形，但不用跑 2 秒探测：缓存三件套的测试只需要
    「save_cache 写出来的合法 payload」。
    """
    report = ProbeReport(
        platform_info={"os": "TestOS", "is_windows": False, "is_linux": True,
                       "is_macos": False, "path_dirs": []},
        permissions_info={"user": {"name": "tester"}, "is_admin": False},
        environment_info={"path_dirs": [], "path_count": 0,
                          "virtual_env": {"active": False},
                          "conda_env": {"active": False}},
        resources_info={"cpu": {"count_logical": 4}, "memory": {}, "disk": [],
                        "network": {}},
        items=[
            ProbeItem(name="python", category="system_tools", available=True,
                      version="3.13.0"),
            ProbeItem(name="git", category="system_tools", available=False,
                      error="not found"),
        ],
    )
    report.build_summary()
    return report


def _rewrite_cache(mutator):
    """读出已落盘缓存 → 交给 mutator 修改 → 原样写回（模拟「被写过/被改过」）。"""
    path = cache_mod._cache_path()
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    mutator(payload)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False)


def _write_events_file(path, events, extra_lines=()):
    """直接写 events.jsonl（模拟历史/损坏文件；也可用来测轮转后的读取）。"""
    path = pathlib.Path(str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "w", encoding="utf-8") as handle:
        for record in events:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        for line in extra_lines:
            handle.write(line + "\n")


def _event_record(event_type, index, source="test"):
    return {"id": "%s-%d" % (event_type, index), "type": event_type,
            "data": {"i": index}, "source": source, "timestamp": 1000.0 + index}


# ===========================================================================
# 1) errors.is_failure_status / OPERATION_OK_STATUSES（CLI 与 MCP 共用判据）
# ===========================================================================

_CLASSIFICATION_SAMPLES = [
    ("ok", False),
    ("success", False),
    ("modified", False),
    ("skipped", False),
    ("noop", False),
    ("published", False),
    ("  OK  ", False),                    # 大小写/空白归一
    (None, False),                        # 纯数据结果：没有成败声明
    ("", False),
    ("needs_fix", True),
    ("failed", True),
    ("partial", True),
    ("awaiting_confirmation", True),
    ("rejected", True),
    ("totally_unknown_status", True),     # 未知值一律按失败（不许「假 ok」）
]


@pytest.mark.parametrize("status,expected", _CLASSIFICATION_SAMPLES,
                         ids=[repr(s) for s, _e in _CLASSIFICATION_SAMPLES])
def test_is_failure_status_classification(status, expected):
    """退步了会怎样：把某个 OK 状态误判为失败（或把失败误判为成功）→ 这里红。

    成功集：ok/success/modified/skipped/noop/published；空/None 不算失败；
    **其余任何值（含未知）都算失败** —— 未知状态宁可报错也不假装成功。
    """
    assert is_failure_status(status) is expected


def test_operation_ok_statuses_has_exactly_the_documented_members():
    """退步了会怎样：有人往 `OPERATION_OK_STATUSES` 里悄悄加状态 → 这里红。

    这个元组是 CLI/MCP 共同的成功集合，静默扩大会让新的失败形态被当成成功。
    断言精确集合（不是「>=」），并保证全是小写无空白（判据做了 lower/strip）。
    """
    assert set(OPERATION_OK_STATUSES) == {
        "ok", "success", "modified", "skipped", "noop", "published"}
    assert len(OPERATION_OK_STATUSES) == 6
    for status in OPERATION_OK_STATUSES:
        assert status == status.strip().lower()


def test_cli_and_mcp_use_the_same_failure_predicate():
    """退步了会怎样：CLI 与 MCP 各写一份判据（MCP 曾只认 'failed'）→ 这里红。

    对同一批状态分别验证三处的结论必须完全一致：
      * `errors.is_failure_status`（真源）
      * `cli._out_result` 的退出码 + 顶层 status
      * `mcp_server.text_result` 的 `isError`
    """
    for status, expected_failure in _CLASSIFICATION_SAMPLES:
        rc, out, err = _invoke_out_result({"status": status})
        assert rc == (1 if expected_failure else 0), \
            "CLI 退出码与 is_failure_status(%r) 不一致：rc=%r" % (status, rc)
        payload = json.loads(out)
        assert payload["status"] == ("failed" if expected_failure else "ok"), \
            "CLI 顶层 status 与 is_failure_status(%r) 不一致: %r" % (status, payload)

        result = mcp_server.text_result({"status": status})
        assert result["isError"] is expected_failure, \
            "MCP isError 与 is_failure_status(%r) 不一致: %r" % (status, result["isError"])
        assert result["isError"] is is_failure_status(status)


def _invoke_out_result(result, status_field="status"):
    """直接调用 cli._out_result 并捕获它打印的 JSON，返回 (rc, stdout, stderr)。"""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = cli._out_result(result, status_field=status_field)
    return rc, out.getvalue(), err.getvalue()


def test_out_result_handles_validation_shape_and_query_mode():
    """退步了会怎样：`scaffold` 的 `validation.valid=False` 形状退回「假 ok」，
    或把「查询记录里的 status」误当成本次操作状态（查询失败被报失败）。

    断言：无 status 但 `validation.valid=False` → rc=1；True → 0；
    `status_field=None`（查询语义）即便被查对象 status=failed → 仍 rc=0；
    未知 status → rc=1。
    """
    rc_bad, out_bad, _ = _invoke_out_result({"validation": {"valid": False, "errors": ["x"]}})
    assert rc_bad == 1 and json.loads(out_bad)["status"] == "failed"

    rc_ok, out_ok, _ = _invoke_out_result({"validation": {"valid": True}})
    assert rc_ok == 0 and json.loads(out_ok)["status"] == "ok"

    rc_query, out_query, _ = _invoke_out_result({"status": "failed"}, status_field=None)
    assert rc_query == 0 and json.loads(out_query)["status"] == "ok", \
        "查询语义下不该把被查对象的 status 当成本次操作成败"

    rc_unknown, _, _ = _invoke_out_result({"status": "whatever"})
    assert rc_unknown == 1


# ===========================================================================
# 2) eventbus 事件落盘
# ===========================================================================

def test_published_event_is_readable_from_disk_after_memory_cleared(world):
    """退步了会怎样：publish 只写内存、不落盘 → 新进程/CLI 永远读不到事件。

    用**独立 EventBus 实例**发布（避免单例内存干扰），然后清空其内存历史，
    再走 `read_persisted_events()` 读文件 —— 能读到才证明「落盘」而不是「内存」。
    """
    bus = eventbus.EventBus()
    bus.publish("action.started", {"action": "demo.a"}, source="unit")

    path = eventbus.events_path()
    assert os.path.isfile(path), "publish() 没有把事件追加到 events.jsonl"

    bus.clear_history()                       # 模拟「换进程」：内存里什么都没有
    snapshot = eventbus.read_persisted_events()

    assert snapshot["exists"] is True
    assert snapshot["total"] == 1
    assert snapshot["empty"] is False
    event = snapshot["events"][-1]
    assert event["type"] == "action.started"
    assert event["data"] == {"action": "demo.a"}
    assert event["source"] == "unit"


@pytest.mark.parametrize("state,expected", [
    ("missing", {"exists": False, "empty": True, "total": 0, "skipped": 0}),
    ("empty_file", {"exists": True, "empty": True, "total": 0, "skipped": 0}),
    ("bad_lines", {"exists": True, "empty": False, "total": 2, "skipped": 1}),
], ids=["missing", "empty_file", "bad_lines"])
def test_read_persisted_events_three_states(world, state, expected):
    """退步了会怎样：三种状态被混为一谈 → 用户分不清「从未有事件」「事件流为空」
    和「文件坏了 N 行」。

    断言就是三种状态各自的精确计数（exists/empty/total/skipped）。
    """
    path = pathlib.Path(str(eventbus.events_path()))
    if state == "empty_file":
        path.parent.mkdir(parents=True, exist_ok=True)
        open(str(path), "w").close()
    elif state == "bad_lines":
        _write_events_file(path, [_event_record("a", 0), _event_record("b", 1)],
                           extra_lines=["这不是 JSON", ""])

    snapshot = eventbus.read_persisted_events()
    for key, value in expected.items():
        assert snapshot[key] == value, "%s 状态下 %s 应为 %r，实得 %r" % (
            state, key, value, snapshot.get(key))


def test_events_cli_json_reports_counts_and_filtering(world):
    """退步了会怎样：CLI 退回「只读内存历史」→ 新进程永远打印「暂无事件」；
    或 `--limit/--type` 只影响渲染不影响数据。

    断言 `--json` 的精确计数与过滤：文件里 5 条（3a/2b）+ 1 坏行；
    `--limit 2` → count=2 且取最新；`--type b` → 只返回 b。
    """
    path = eventbus.events_path()
    events = [_event_record("a", 0), _event_record("b", 1), _event_record("a", 2),
              _event_record("b", 3), _event_record("a", 4)]
    _write_events_file(path, events, extra_lines=["garbage-line"])

    rc, out, err = _invoke(["events", "--json", "--limit", "2"])
    assert rc == 0
    data = json.loads(out)
    assert data["source"] == "file"
    assert data["history_exists"] is True
    assert data["total_in_file"] == 5
    assert data["skipped_lines"] == 1
    assert data["count"] == 2
    # 事件序列 a0,b1,a2,b3,a4 → 最新两条是 b3,a4
    assert [event["type"] for event in data["events"]] == ["b", "a"]

    rc, out, err = _invoke(["events", "--json", "--type", "b"])
    filtered = json.loads(out)
    assert filtered["count"] == 2
    assert [event["type"] for event in filtered["events"]] == ["b", "b"]

    rc, out, err = _invoke(["events"])
    assert "无法解析" in out, "人类可读输出没有报告坏行数: %r" % (out[:300],)


def test_events_cli_is_read_only(world):
    """退步了会怎样：`events`（纯读命令）顺手创建 events.jsonl 或 `_meta/` 目录。

    断言：文件本不存在时跑完仍不存在，且 `_meta/` 目录没有被创建。
    """
    # 清掉进程内单例总线历史：否则 `_cmd_events` 会走「内存兜底」把本进程里
    # 别的用例发过的事件读出来（source=memory），与「只读/空事件流」无关。
    eventbus.get_event_bus().clear_history()

    assert not os.path.exists(eventbus.events_path())
    assert not world.meta.exists()

    rc, out, err = _invoke(["events", "--json"])
    assert rc == 0
    data = json.loads(out)
    assert data["history_exists"] is False
    assert data["source"] == "none"

    assert not os.path.exists(eventbus.events_path()), "只读命令创建了事件文件"
    assert not world.meta.exists(), "只读命令创建了 _meta/ 目录"


def test_rotation_keeps_recent_tail(world, monkeypatch):
    """退步了会怎样：文件只追加不轮转 → 无限增长（5MB 上限失效）；
    或轮转后保留的是**头部**（旧事件）而不是尾部。

    用小上限 monkeypatch（不真写 5MB）：12 条事件、上限 400 字节/保留 3 行，
    断言文件只剩最近 3 行且是最后 3 条事件。
    """
    monkeypatch.setattr(eventbus, "PERSIST_MAX_BYTES", 400)
    monkeypatch.setattr(eventbus, "PERSIST_KEEP_LINES", 3)

    bus = eventbus.EventBus()
    for index in range(12):
        bus.publish("tick", {"i": index, "pad": "x" * 40})

    path = eventbus.events_path()
    with open(str(path), "r", encoding="utf-8") as handle:
        lines = [line for line in handle.read().splitlines() if line.strip()]

    assert len(lines) == 3, "轮转后应只保留尾部 %d 行，实得 %d 行" % (3, len(lines))
    kept = [json.loads(line)["data"]["i"] for line in lines]
    assert kept == [9, 10, 11], "轮转保留了错误的一端（应保留最新事件）: %r" % (kept,)
    # 字节不变量：轮转时保证「保留量 ≤ MAX」，之后还允许追加**一条**新事件
    # （新事件在写入前不知道该不该触发轮转）→ 文件最多 MAX + 单行字节。
    line_bytes = [len(line.encode("utf-8")) + 1 for line in lines]
    assert sum(line_bytes) <= eventbus.PERSIST_MAX_BYTES + max(line_bytes), \
        "轮转后文件仍超出「MAX + 单行」上界（说明只按行数裁、没按字节收）: %r" % (
            sum(line_bytes),)


def test_persist_failure_does_not_break_publish(world, monkeypatch):
    """退步了会怎样：落盘异常冒泡 → publish() 崩掉（订阅者/内存历史全丢），
    或失败被静默吞掉（排障时看不到 failures 计数）。

    把 `_meta` 指到「父路径是文件」的位置（必然写失败），断言：
    publish 不抛、订阅者仍被通知、内存历史仍有事件、`persistence_stats()["failures"] == 1`。
    """
    blocked = world.root / "blocked"
    blocked.write_text("not a directory", encoding="utf-8")
    monkeypatch.setenv("ACTUS_META_DIR", str(blocked / "meta"))

    bus = eventbus.EventBus()
    received = []
    bus.subscribe("boom", lambda event: received.append(event.type))

    bus.publish("boom", {"k": 1})            # 不应抛异常

    assert received == ["boom"], "落盘失败不该影响订阅者通知"
    assert len(bus.get_history()) == 1, "落盘失败不该丢内存历史"
    stats = bus.persistence_stats()
    assert stats["failures"] == 1, "落盘失败必须留下计数（不静默）: %r" % (stats,)
    assert stats["written"] == 0


def test_persist_switch_off_writes_nothing(world, monkeypatch):
    """退步了会怎样：`ACTUS_EVENTS_PERSIST=0` 失效（想关落盘的部署仍被写文件）。

    断言：关闭后 publish 不创建 events.jsonl，且 `persistence_stats()["enabled"]` 为 False。
    """
    monkeypatch.setenv("ACTUS_EVENTS_PERSIST", "0")
    bus = eventbus.EventBus()
    bus.publish("tick", {"i": 0})

    assert not os.path.exists(eventbus.events_path()), "关闭落盘后仍然写了文件"
    assert bus.persistence_stats()["enabled"] is False
    assert len(bus.get_history()) == 1, "关闭落盘不该影响内存事件"


# ===========================================================================
# 3) probe 缓存三件套（host / probe_version / items_digest）
# ===========================================================================

def test_valid_cache_still_hits(world):
    """退步了会怎样：新闸门把**正常**缓存也拒掉（每次 probe 都重跑，缓存形同虚设）。

    断言 save_cache 写出的真实 payload 能通过校验，且 cache_info 给出 valid/ok。
    """
    report = _valid_probe_report()
    assert cache_mod.save_cache(report.to_dict()) is True

    loaded = cache_mod.load_cache(max_age=999999)
    assert loaded is not None, "正常缓存被新闸门误拒"
    assert len(loaded["items"]) == 2
    info = cache_mod.cache_info()
    assert info["valid"] is True
    assert info["reason"] == "ok"
    assert info["last_reject"] == ""


@pytest.mark.parametrize("mutation,expected_reason", [
    ("items", "digest-mismatch"),
    ("host", "host-mismatch"),
    ("version", "version-mismatch"),
    ("drop-host", "host-missing"),
    ("drop-version", "version-missing"),
    ("drop-digest", "digest-missing"),
], ids=["items", "host", "version", "drop-host", "drop-version", "drop-digest"])
def test_integrity_gate_rejects_tampered_cache(world, mutation, expected_reason):
    """退步了会怎样：缓存被写坏/跨机器拷贝/旧版本残留/人工编辑 → 仍被当成有效缓存，
    把错误能力当成「本机探测结果」（例如显示别的机器装了 VS）。

    断言 `load_cache()` 返回 None、`cache_info()` 的 reason/valid/last_reject 精确指出
    是哪一道闸门拒了它。
    """
    report = _valid_probe_report()
    assert cache_mod.save_cache(report.to_dict()) is True

    def mutate(payload):
        if mutation == "items":
            payload["items"].append({"name": "evil-tool", "category": "x",
                                     "available": True})
            # 刻意**不**更新 items_digest：模拟「改了 items 没改摘要」
        elif mutation == "host":
            payload["host"] = "SomeOtherMachine"
        elif mutation == "version":
            payload["probe_version"] = "0.0.1"
        elif mutation == "drop-host":
            payload.pop("host", None)
        elif mutation == "drop-version":
            payload.pop("probe_version", None)
        elif mutation == "drop-digest":
            payload.pop("items_digest", None)

    _rewrite_cache(mutate)

    assert cache_mod.load_cache(max_age=999999) is None, \
        "%s 篡改后缓存仍被判有效" % mutation
    info = cache_mod.cache_info()
    assert info["valid"] is False
    assert expected_reason in info["reason"], \
        "cache_info.reason 应含 %r，实得 %r" % (expected_reason, info["reason"])
    assert expected_reason in info["last_reject"], \
        "load_cache 的拒绝原因应含 %r，实得 %r" % (expected_reason, info["last_reject"])


# ===========================================================================
# 4) probe.ProbeReport.report_source（probe / cache）
# ===========================================================================

@pytest.mark.timeout(180)
@pytest.mark.slow
def test_report_source_distinguishes_probe_from_cache(world):
    """退步了会怎样：缓存命中的报告仍标 "probe" → 用户/AI 把旧结果当刚探测的，
    或 force-refresh 被缓存短路却标 "cache"。

    断言：先写一份缓存，再 `probe(force_refresh=True)` → report_source="probe"、
    to_dict 同步、摘要**不**带 cache 标注；随后缓存命中 → "cache" 且摘要显式标注。
    """
    seeded = _valid_probe_report()
    assert cache_mod.save_cache(seeded.to_dict()) is True

    fresh = probe(force_refresh=True)          # 必须无视上面那份缓存
    assert fresh.report_source == "probe", \
        "force_refresh=True 的报告应标 probe，实得 %r" % (fresh.report_source,)
    assert fresh.to_dict()["report_source"] == "probe"
    assert "Source: cache" not in format_summary(fresh)

    cached = probe(force_refresh=False, max_age=999999)
    assert cached.report_source == "cache", \
        "缓存命中的报告应标 cache，实得 %r" % (cached.report_source,)
    assert cached.to_dict()["report_source"] == "cache"
    summary_text = format_summary(cached)
    assert "Source: cache" in summary_text, "缓存来源没有在人类可读摘要里标注"
    assert "from cache" in summary_text


# ===========================================================================
# 5) probe.actions 多根（roots / 精确计数）
# ===========================================================================

def _seed_ids():
    """包内种子动作 id（动态取；不写死数量）。"""
    from vools.actus.indexer import _seed_actions_dir
    from vools.actus.probe.actions import _scan_actions_dir

    seed_dir = _seed_actions_dir()
    if not os.path.isdir(seed_dir):
        return []
    return sorted(entry["id"] for entry in _scan_actions_dir(seed_dir)["actions"])


def _write_action(actions_dir, action_id):
    """写一个最小可解析动作（JSON #!cfg 形态）。"""
    actions_dir.mkdir(parents=True, exist_ok=True)
    path = actions_dir / (action_id.rsplit(".", 1)[-1] + ".actus.md")
    meta = {"id": action_id, "name": action_id, "version": "1.0.0", "entry": "main"}
    path.write_text(
        "---\nAIGC:\n    Label: \"1\"\n---\n\n# %s\n\n```json #!cfg\n%s\n```\n"
        % (action_id, json.dumps(meta, ensure_ascii=False)), encoding="utf-8")
    return path


def test_actions_entry_reports_all_roots(world):
    """退步了会怎样：`actions` 条目退回单根 → 报告漏掉包内种子动作
    （`action_readiness`/docs 都是多根，口径又漂移）。

    断言（精确，非「>0」）：`extra["roots"]` 与产品真源 `_action_roots()` 一致且 ≥2；
    用户根为空时 `action_count == 种子数`；新增 1 个本地动作后 `action_count == 种子数 + 1`。
    """
    from vools.actus.indexer import _action_roots

    seed_ids = _seed_ids()
    if not seed_ids:
        pytest.skip("包内种子目录缺失/为空，无法验证多根语义")

    item = [entry for entry in ActionsProber().run() if entry.name == "actions"][0]
    expected_roots = _action_roots()
    assert len(item.extra["roots"]) >= 2, "多根语义下至少应有用户根 + 种子根"
    assert [os.path.normcase(os.path.abspath(p)) for p in item.extra["roots"]] == \
        [os.path.normcase(os.path.abspath(p)) for p in expected_roots]
    assert item.extra["action_count"] == len(seed_ids), \
        "用户根为空时计数应精确等于种子数 %d，实得 %r" % (
            len(seed_ids), item.extra["action_count"])

    # 加一个本地动作：计数必须 +1（证明是多根并集，不是只扫某一边）
    _write_action(world.repo / "actions", "test.newcap.local")
    item2 = [entry for entry in ActionsProber().run() if entry.name == "actions"][0]
    local_ids = {entry["id"] for entry in item2.extra["actions"]} - set(seed_ids)
    assert local_ids == {"test.newcap.local"}, \
        "多根条目里应出现本地动作，实得差集 %r" % (local_ids,)
    assert item2.extra["action_count"] == len(seed_ids) + 1
