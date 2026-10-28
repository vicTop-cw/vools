# -*- coding: utf-8 -*-
"""actus/tests/test_mcp_async_tasks.py — MCP 异步任务化（慢工具不阻塞）契约回归。

为什么要这份文件（第 17 轮）
---------------------------
`mcp_server.serve_forever` 是 read→handle→write 的**单线程**循环：一个 GUI 动作
（实测 calculator 188s）会把整个服务拖死，期间所有请求无响应。cmd-hardening 把
**动作工具**改成「先同步等 `ACTUS_MCP_ASYNC_GRACE` 秒，超时转后台 + 返回 task_id，
用 `actus_status(task_id=...)` 轮询」，并加写锁保证并发写 stdout 不出半行。
这套能力当时只有手工验收，没有回归测试 —— 本文件把它钉住。

关键契约（读实现后按真实语义断言）：
  * 只有**动作工具**（`_action_tool_map()` 命中）走异步；其它工具完全同步。
  * 快动作在 grace 内完成 → 返回体与改前一致（`status=ok`，无 task_id）。
  * 超 grace → `status='running'` + task_id + `isError=False`（"还在跑"不是失败）。
  * 轮询结果 `result` 与直接同步调用**逐字段一致**。
  * 运行中任务数 ≥ `_TASK_RUNNING_MAX` → `task_capacity`，不无限开线程。
  * 超时：Python 线程无法强杀 → `status='timeout'` + `worker_may_still_run=True`
    （如实标注），迟到结果挂 `late_result`，不把 timeout 改写回 ok。
  * 任务表在**进程内存**：server 重启（表被清空）后旧 task_id → `task_not_found`
    （这是设计决策，本文件钉成契约，防将来改成落盘后语义漂移）。
  * 写锁必须覆盖**整条消息**（json + 换行 + flush），否则并发下发客户端读到半行。

隔离与速度：HOME / ACTUS_META_DIR 由 `tests/conftest.py` 全局指 tmp；所有耗时用
monkeypatch 的假 handler + 很小的 grace/timeout 控制，全文件 < 10s，不依赖真动作。
"""

import io
import json
import os
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

from vools.actus import mcp_server  # noqa: E402


# ---------------------------------------------------------------------------
# 夹具 / 辅助
# ---------------------------------------------------------------------------

def _payload(raw):
    """MCP result → (isError, 解析后的业务 payload)。"""
    assert isinstance(raw, dict) and "content" in raw and "isError" in raw, raw
    return raw["isError"], json.loads(raw["content"][0]["text"])


@pytest.fixture(autouse=True)
def _clean_task_table():
    """每个用例前后清空进程内任务表（它是全局状态，跨用例会互相污染）。"""
    with mcp_server._TASKS_LOCK:
        mcp_server._TASKS.clear()
    yield
    time.sleep(0.02)
    with mcp_server._TASKS_LOCK:
        mcp_server._TASKS.clear()


@pytest.fixture
def server():
    srv = mcp_server.MCPServer(stdout=io.BytesIO())
    return srv


def _patch_action_tools(monkeypatch, mapping=None):
    """把工具→动作映射换成固定表，让 fake 工具走异步分支。"""
    mapping = mapping or {"slow_tool": "my.slow", "fast_tool": "my.fast"}
    monkeypatch.setattr(mcp_server, "_action_tool_map", lambda ttl=5.0: dict(mapping))


def _patch_handler(monkeypatch, delays):
    """给动作工具装假 handler：按名字 sleep 指定秒数后返回确定 payload。

    只拦截 fake 工具名；其它工具（如 actus_status）仍走真实分发 —— 这样轮询
    验证的是真实 `actus_status` 分支，而不是替身。
    """
    real_call = mcp_server.MCPServer._call_tool

    def fake_call(self, params):
        name = (params or {}).get("name", "")
        if name in delays:
            time.sleep(delays[name])
            return mcp_server.text_result({
                "status": "ok",
                "data": {"tool": name, "done": True, "arguments": params.get("arguments")},
            })
        return real_call(self, params)

    monkeypatch.setattr(mcp_server.MCPServer, "_call_tool", fake_call)


def _call(server, name, arguments):
    """同步调用工具并解析 payload（fake 工具会 sleep）。"""
    return _payload(server._call_tool({"name": name, "arguments": arguments or {}}))


def _poll(server, task_id, timeout=3.0, interval=0.01):
    """轮询 actus_status 直到任务不再 running；返回 data.snapshot。"""
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        is_error, payload = _call(server, "actus_status", {"task_id": task_id})
        assert is_error is False, payload      # 查询本身成功（被查任务可能已失败）
        snap = payload["data"]
        last = snap
        if snap["status"] != "running":
            return snap
        time.sleep(interval)
    raise AssertionError("轮询超时，最后快照=%r" % (last,))


# ===========================================================================
# 1) 写锁 → 并发写 stdout 消息原子性
# ===========================================================================

class _ChunkedStdout(object):
    """把每次 write 拆成两半、中间 sleep —— 没有整条消息锁时两条消息必然交错。

    这样「是否加锁」在测试里是**确定性**可见的，而不是靠运气复现竞态。
    """

    def __init__(self):
        self.buffer = bytearray()
        self.lock = threading.Lock()

    def write(self, data):
        mid = max(1, len(data) // 2)
        for chunk in (data[:mid], data[mid:]):
            with self.lock:
                self.buffer.extend(chunk)
            time.sleep(0.0005)

    def flush(self):
        pass


def test_concurrent_writes_produce_only_valid_json_lines(server):
    """退步了会怎样：`_write` 的锁粒度不是整条消息（json/换行/flush 三步之间
    可被另一线程插入）→ 客户端读到半行 JSON（spike 复现过），协议直接坏掉。

    做法：把 stdout 换成「分两半写、中间让出 GIL」的流；多线程并发 `_write`；
    断言最终每一行都是合法 JSON、id 集合完整且不重不漏。
    """
    stream = _ChunkedStdout()
    server.stdout = stream
    total, workers = 120, 6
    ids = list(range(total))

    def writer(start):
        for i in ids[start::workers]:
            server._write({"jsonrpc": "2.0", "id": i,
                           "result": {"payload": "x" * 40}})

    threads = [threading.Thread(target=writer, args=(k,)) for k in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    raw = bytes(stream.buffer).decode("utf-8")
    lines = [line for line in raw.splitlines() if line.strip()]
    assert len(lines) == total, "写出的消息行数不对: %d != %d" % (len(lines), total)

    seen = []
    for line in lines:
        try:
            obj = json.loads(line)
        except ValueError:
            raise AssertionError("并发写下出现半行/坏行 JSON: %r" % (line[:120],))
        assert obj.get("jsonrpc") == "2.0"
        seen.append(obj.get("id"))
    assert sorted(seen) == ids, "消息 id 有丢失或重复（交错写坏）"


# ===========================================================================
# 2) 慢工具 → 返回任务句柄
# ===========================================================================

def test_slow_action_returns_running_task_handle(server, monkeypatch):
    """退步了会怎样：慢动作仍然同步阻塞 → 188s 卡死服务的问题回归；
    或把「还在跑」误报成失败（isError=True）。

    断言：monkeypatch 假慢 handler（sleep > grace）后，handle() 的 tools/call
    返回 `status='running'`、有 `task_id`、`isError=False`、poll 指向 actus_status。
    """
    monkeypatch.setattr(mcp_server, "_TASK_GRACE_SEC", 0.02)
    _patch_action_tools(monkeypatch)
    _patch_handler(monkeypatch, {"slow_tool": 0.25})

    resp = server.handle({"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                          "params": {"name": "slow_tool", "arguments": {"k": 1}}})
    is_error, payload = _payload(resp["result"])

    assert is_error is False, payload
    assert payload["status"] == "running", payload
    task_id = payload["task_id"]
    assert isinstance(task_id, str) and task_id.startswith("task-")
    assert payload["poll"]["tool"] == "actus_status"
    assert payload["poll"]["arguments"]["task_id"] == task_id
    assert payload["action"] == "my.slow"


# ===========================================================================
# 3) 快工具 → 仍同步（不变成两段式）
# ===========================================================================

def test_fast_action_stays_synchronous(server, monkeypatch):
    """退步了会怎样：所有动作都被异步化（或 grace 被改成 0）→ 快动作也返回
    `running + task_id`，调用方被迫轮询，与改前行为不一致、CLI/客户端全要改。

    断言：快 handler（sleep 0.05s，远小于默认 grace 2s）→ 直接返回 `status='ok'`、
    业务 data 正确、**没有 task_id**、isError=False。
    故意**不用 monkeypatch 覆盖 grace**：这样「grace 被改成 0」这类产品回归
    才不会被测试自己的桩掩盖（变异验证依赖这一点）。
    """
    _patch_action_tools(monkeypatch)
    _patch_handler(monkeypatch, {"fast_tool": 0.05})

    is_error, payload = _payload(
        server._call_tool_async({"name": "fast_tool", "arguments": {"k": 2}}))

    assert is_error is False
    assert payload["status"] == "ok", payload
    assert payload["data"]["tool"] == "fast_tool"
    assert payload["data"]["arguments"] == {"k": 2}
    assert "task_id" not in payload, "快动作不应返回任务句柄（行为回退）"


# ===========================================================================
# 4) 轮询结果与同步调用逐字段一致
# ===========================================================================

def test_polling_returns_result_identical_to_sync_call(server, monkeypatch):
    """退步了会怎样：后台执行路径与同步执行路径结果不一致（少包一层/丢字段/
    isError 反转），调用方按 task_id 拿到的结果和直接调用对不上。

    断言：轮询到 ok 后，任务快照里的 `result` 与**直接同步调用**同一 fake 工具
    的返回体逐字段相等（含嵌套 content 与 isError）。
    """
    monkeypatch.setattr(mcp_server, "_TASK_GRACE_SEC", 0.01)
    _patch_action_tools(monkeypatch)
    _patch_handler(monkeypatch, {"slow_tool": 0.2})

    is_error, handle_payload = _payload(
        server._call_tool_async({"name": "slow_tool", "arguments": {"q": "abc"}}))
    assert is_error is False and handle_payload["status"] == "running"
    task_id = handle_payload["task_id"]

    snap = _poll(server, task_id)
    assert snap["status"] == "ok", snap
    assert snap["tool"] == "slow_tool"
    assert snap["arguments"] == {"q": "abc"}
    assert snap["result"] is not None

    direct = server._call_tool({"name": "slow_tool", "arguments": {"q": "abc"}})
    assert snap["result"] == direct, "轮询结果与直接同步调用不一致"
    assert _payload(snap["result"])[1]["data"]["arguments"] == {"q": "abc"}


# ===========================================================================
# 5) 并发上限 → task_capacity
# ===========================================================================

def test_running_capacity_rejects_new_slow_task(server, monkeypatch):
    """退步了会怎样：运行中任务数不设上限 —— 客户端连点就无限开线程，内存/句柄
    耗尽；或超限时静默排队（调用方以为立刻执行了）。

    断言：把 `_TASK_RUNNING_MAX` 调到 2，连发 3 个慢任务 → 前两个 running，
    第 3 个 `failed` + `code='task_capacity'` + isError=True，且 details 带上限。
    """
    monkeypatch.setattr(mcp_server, "_TASK_GRACE_SEC", 0.01)
    monkeypatch.setattr(mcp_server, "_TASK_RUNNING_MAX", 2)
    _patch_action_tools(monkeypatch)
    _patch_handler(monkeypatch, {"slow_tool": 0.5})

    first_err, first = _payload(
        server._call_tool_async({"name": "slow_tool", "arguments": {}}))
    second_err, second = _payload(
        server._call_tool_async({"name": "slow_tool", "arguments": {}}))
    third_err, third = _payload(
        server._call_tool_async({"name": "slow_tool", "arguments": {}}))

    assert first_err is False and first["status"] == "running"
    assert second_err is False and second["status"] == "running"
    assert third_err is True, third
    assert third["status"] == "failed"
    assert third["error"]["code"] == "task_capacity", third
    assert third["error"]["details"]["running"] == 2
    assert third["error"]["details"]["running_max"] == 2


# ===========================================================================
# 6) 超时 → timeout + worker_may_still_run（如实标注，不是真杀）
# ===========================================================================

def test_timeout_marks_worker_may_still_run_and_keeps_late_result(server, monkeypatch):
    """退步了会怎样：超时被当成失败且不说明「worker 可能还在跑」（用户以为已停止，
    实际后台还在执行/占资源）；或迟到结果把 timeout 改写成 ok（假绿灯）。

    断言：timeout 调小后轮询 → `status='timeout'`、`worker_may_still_run=True`、
    `timed_out=True`；worker 迟到结束后再轮询仍是 timeout，且迟到结果挂
    `late_result`（不覆盖超时结论）。

    注意：假 handler 故意 sleep 1.0s（远大于 timeout 0.05s）—— 机器慢/负载高时
    worker 若在第一次轮询前就结束，快照会是 ok，测不到 timeout 路径（曾实际 flake）。
    """
    monkeypatch.setattr(mcp_server, "_TASK_GRACE_SEC", 0.01)
    monkeypatch.setattr(mcp_server, "_TASK_TIMEOUT_SEC", 0.05)
    _patch_action_tools(monkeypatch)
    _patch_handler(monkeypatch, {"slow_tool": 1.0})

    is_error, handle_payload = _payload(
        server._call_tool_async({"name": "slow_tool", "arguments": {}}))
    assert is_error is False and handle_payload["status"] == "running"
    task_id = handle_payload["task_id"]

    snap = _poll(server, task_id)
    assert snap["status"] == "timeout", snap
    assert snap["worker_may_still_run"] is True, "必须如实标注 worker 可能仍在跑"
    assert snap["timed_out"] is True
    assert snap["timeout_sec"] == 0.05

    # 等 worker 真正结束（迟到），再轮询：超时结论不能被迟到结果改写
    time.sleep(1.2)
    later = _poll(server, task_id)
    assert later["status"] == "timeout", later
    assert later.get("late_result") is not None, "迟到结果应挂在 late_result，而不是覆盖状态"


# ===========================================================================
# 7) task_id 不存在 → task_not_found
# ===========================================================================

def test_unknown_task_id_reports_task_not_found(server):
    """退步了会怎样：查不存在的 task_id 返回 ok/空快照（调用方以为任务还在跑），
    或抛 KeyError 穿透协议层。

    断言：`actus_status(task_id='no-such')` → isError=True、`code='task_not_found'`、
    消息点名该 id、details 带 task_id。
    """
    is_error, payload = _payload(server._call_tool(
        {"name": "actus_status", "arguments": {"task_id": "no-such-task"}}))

    assert is_error is True
    err = payload["error"]
    assert err["code"] == "task_not_found", err
    assert "no-such-task" in err["message"]
    assert err["details"]["task_id"] == "no-such-task"


# ===========================================================================
# 8) 「结果存内存」是契约：清空任务表（模拟重启）后旧 task_id 失效
# ===========================================================================

def test_task_table_is_memory_only_so_restart_invalidates_task_id(server, monkeypatch):
    """退步了会怎样：任务表改成落盘后，「重启后 task_id 失效」的语义漂移 ——
    客户端可能拿到跨重启的陈旧结果，或测试/工具依赖的清理语义失效。

    断言：慢任务完成后轮询拿到 ok；随后清空 `_TASKS`（等同 server 重启）→
    同一 task_id 再查 → `task_not_found`。
    """
    monkeypatch.setattr(mcp_server, "_TASK_GRACE_SEC", 0.01)
    _patch_action_tools(monkeypatch)
    _patch_handler(monkeypatch, {"slow_tool": 0.15})

    _is_error, handle_payload = _payload(
        server._call_tool_async({"name": "slow_tool", "arguments": {}}))
    task_id = handle_payload["task_id"]
    assert _poll(server, task_id)["status"] == "ok"

    with mcp_server._TASKS_LOCK:
        mcp_server._TASKS.clear()      # 模拟进程重启：内存任务表清空

    is_error, payload = _payload(server._call_tool(
        {"name": "actus_status", "arguments": {"task_id": task_id}}))
    assert is_error is True
    assert payload["error"]["code"] == "task_not_found", payload
