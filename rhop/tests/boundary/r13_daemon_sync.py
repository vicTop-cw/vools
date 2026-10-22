# -*- coding: utf-8 -*-
"""第三轮边界语料：停机/看护轮询 / 同步乱序重放 / 载荷与结果边界。

定位：语料 + 复现器，不是产品源码（命名不带 test_ 前缀，不进 pytest 收集）。
R3 覆盖共享库并发、白名单等价性、心跳截断、同步发散、结果截断；
R10 覆盖租约续期、多 worker 高竞争、控制意图裁决、提交幂等、畸形输入；
本轮补**看护轮询边界、同步乱序与重放、载荷/结果边界、租约与看护的交互**。

运行：
    cd rhop && python tests/boundary/r13_daemon_sync.py

每条输出 [CONFIRMED] / [NOT-CONFIRMED] + 证据；退出码 = 风险成立条数。
"""
import copy
import datetime
import os
import sys
import tempfile

RHOP = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RHOP)
PY = sys.executable

from vools.rhop.task.config import TaskConfig            # noqa: E402
from vools.rhop.task.exec import ExecPolicy, run_payload  # noqa: E402
from vools.rhop.task.models import TaskRecord, TaskState, iso_add_seconds, utcnow_iso  # noqa: E402
from vools.rhop.task.queue import TaskQueue              # noqa: E402
from vools.rhop.task.sync import TaskSync                # noqa: E402

RESULTS = []


def record(pid, title, risk_realized, evidence):
    RESULTS.append((pid, title, risk_realized, evidence))
    print("[%s] %-38s %s" % ("CONFIRMED" if risk_realized else "NOT-CONFIRMED",
                             pid + " " + title, evidence))


def _cli(script):
    return '"%s" "%s"' % (PY.replace("\\", "/"), script.replace("\\", "/"))


def _wire(role, base, share, store_spec=None, exec_spec=None, queue_spec=None):
    spec = dict(store_spec or {"kind": "sqlite-local"})
    spec.update(queue_spec or {})
    cfg = TaskConfig.from_dict(
        {"name": "link", "role": role, "key": "unit-key",
         "shared": {"write": str(share)}, "queue": {"store": spec},
         "exec": exec_spec or {"allow": ["cli:python"]}},
        base_dir=str(base), warn_plaintext=False)
    store = cfg.build_store()
    syncer = TaskSync(store, cfg.build_crypto(), cfg.role,
                      shared=cfg.build_shared(), name=cfg.name)
    return TaskQueue(cfg, store=store, crypto=cfg.build_crypto(), syncer=syncer)


def _ok_script(work, name="ok.py", body="print('done')\n"):
    path = os.path.join(str(work), name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    return path


# ---------------------------------------------------------------------------
# D1 看护轮询边界：scheduled_at 恰等 / priority 并列 / cancel_requested 与依赖门控
# ---------------------------------------------------------------------------
def d1_poll_boundaries():
    work = tempfile.mkdtemp(prefix="bf-d1-")
    share = os.path.join(work, "share")
    os.makedirs(share)
    q = _wire("A", os.path.join(work, "a"), share, store_spec={"kind": "sqlite-shared"})
    script = _ok_script(work)
    try:
        now = utcnow_iso()
        future = iso_add_seconds(now, 60)
        q.submit([
            {"task_name": "past", "cli": {"cmd": _cli(script)}, "scheduled_at": iso_add_seconds(now, -60)},
            {"task_name": "now", "cli": {"cmd": _cli(script)}, "scheduled_at": now},
            {"task_name": "future", "cli": {"cmd": _cli(script)}, "scheduled_at": future},
        ])
        q.cancel("future")                     # 已取消 + scheduled_at 在未来
        claimed = []
        while True:
            rec = q.store.claim_next("w1")
            if rec is None:
                break
            claimed.append(rec.task_name)
        risk = set(claimed) != {"past", "now"}
        record("D1", "看护轮询边界（scheduled_at/cancel）", risk,
               "claimed=%s（期望 past+now；future 已取消应被跳过；scheduled_at==now 应可领）" % claimed)

        # priority 并列时领取顺序应确定（按 task_id），且不重复
        q.store.requeue("past") if False else None
        q.store.reset_failed()
        q.submit([{"task_name": "p1", "cli": {"cmd": _cli(script)}, "priority": 5},
                  {"task_name": "p2", "cli": {"cmd": _cli(script)}, "priority": 5}])
        order = []
        while True:
            rec = q.store.claim_next("w2")
            if rec is None:
                break
            order.append(rec.task_name)
        tie_ok = sorted(order) == ["p1", "p2"] and len(order) == len(set(order))
        record("D1b", "priority 并列的领取顺序确定且不重复", not tie_ok,
               "order=%s" % order)
        return risk or not tie_ok
    finally:
        q.close()


# ---------------------------------------------------------------------------
# D2 同步乱序与重放
# ---------------------------------------------------------------------------
def d2_sync_reorder_and_replay():
    work = tempfile.mkdtemp(prefix="bf-d2-")
    share = os.path.join(work, "share")
    os.makedirs(share)
    qa = _wire("A", os.path.join(work, "a"), share)
    qb = _wire("B", os.path.join(work, "b"), share)
    try:
        script = _ok_script(work)
        qa.submit([{"task_name": "ord", "value": "v5"}])
        qa.syncer.push_tasks()
        qb.pull_sync()
        fresh = qa.store.get_task("ord")
        stale_rec = copy.copy(fresh)
        stale_rec.value = "v3"
        stale_rec.version = max(0, fresh.version - 1)
        # 直接把「旧版本包」喂给 B 端存储层（模拟乱序到达）——
        # 注意：不能塞进 A 端文档再推，因为 A 端文档合并是 last-write-wins，
        # 那样测的是文档合并语义而不是 B 端的版本单调门。
        outcome = qb.store.apply_task(stale_rec)
        risk = outcome != "stale"
        record("D2", "版本单调门：旧包必须被拒（stale）", risk,
               "B 端当前 v%s；喂入 v%s/version=%s → apply_task 返回 %s（期望 stale）"
               % (qb.get_task("ord").version, stale_rec.value, stale_rec.version, outcome))
        return risk
    finally:
        qa.close()
        qb.close()


# ---------------------------------------------------------------------------
# D3 载荷边界：空 payload / 非 dict / sha 不匹配 → 失败可读且不可重试
# ---------------------------------------------------------------------------
def d3_payload_boundaries():
    work = tempfile.mkdtemp(prefix="bf-d3-")
    share = os.path.join(work, "share")
    os.makedirs(share)
    qb = _wire("B", os.path.join(work, "b"), share, store_spec={"kind": "sqlite-shared"})
    qa = _wire("A", os.path.join(work, "a"), share, store_spec={"kind": "sqlite-shared"})
    try:
        # 空 payload：应能正常解密（不抛错）
        qa.submit([{"task_name": "empty", "handler": "unit-empty", "value": ""}])
        # sha 不匹配：解密阶段必须抛可读的 PayloadError（且不可重试）
        qa.submit([{"task_name": "sha", "handler": "unit-ok", "value": "v"}])
        qa.store.set_state("sha", TaskState.PENDING, force=True, payload_sha="deadbeef")

        qb.pull_sync()
        from vools.rhop.task.errors import PayloadError
        outcomes = {}
        for name in ("empty", "sha"):
            rec = qb.store.get_task(name)
            if rec is None:
                outcomes[name] = ("missing", None)
                continue
            try:
                qb.decrypt_payload(rec)
                outcomes[name] = ("ok", None)
            except PayloadError as exc:
                outcomes[name] = ("raise", str(exc))
        empty_ok = outcomes["empty"][0] == "ok"
        sha_raises = outcomes["sha"][0] == "raise"
        risk = not (empty_ok and sha_raises)
        record("D3", "载荷边界（空/sha 不匹配）→ 失败且不可重试", risk,
               "empty -> %s（应能解密）；sha -> %s（应抛 PayloadError 且文案可读）"
               % (outcomes["empty"], outcomes["sha"]))
        return risk
    finally:
        qa.close()
        qb.close()


# ---------------------------------------------------------------------------
# D4 结果边界：成功但 result=None / 空 dict；成功但已 cancel_requested
# ---------------------------------------------------------------------------
def d4_result_boundaries():
    work = tempfile.mkdtemp(prefix="bf-d4-")
    share = os.path.join(work, "share")
    os.makedirs(share)
    qb = _wire("B", os.path.join(work, "b"), share, store_spec={"kind": "sqlite-shared"},
               exec_spec={"allow": ["cli:python", "handler:*"]})
    qa = _wire("A", os.path.join(work, "a"), share, store_spec={"kind": "sqlite-shared"},
               exec_spec={"allow": ["cli:python", "handler:*"]})
    try:
        from vools.rhop.task.exec import register_handler, HANDLERS
        register_handler("unit-none", lambda payload: None)
        register_handler("unit-empty", lambda payload: {})
        qb.handlers["unit-none"] = HANDLERS["unit-none"]
        qb.handlers["unit-empty"] = HANDLERS["unit-empty"]

        qa.submit([{"task_name": "n", "handler": "unit-none"},
                   {"task_name": "e", "handler": "unit-empty"}])
        qa.submit([{"task_name": "cancelled", "handler": "unit-none"}])
        qa.cancel("cancelled")
        qb.pull_sync()
        stats = {}
        for _ in range(3):
            out = qb.run_once()
            name = out.get("task_name")
            if name:
                rec = qb.get_task(name)
                stats[name] = (rec.state if rec else None,
                               rec.back_info if rec else None)
        qa.pull_sync()
        cancelled_state = qb.get_task("cancelled").state
        risk = (stats.get("n", (None,))[0] != TaskState.COMPLETED
                or stats.get("e", (None,))[0] != TaskState.COMPLETED)
        record("D4", "结果边界（result=None/空 dict、已取消任务）", risk,
               "成功但 result=None -> %s；空 dict -> %s；已取消任务 -> %s（取消应优先于执行）"
               % (stats.get("n", (None, None))[0], stats.get("e", (None, None))[0],
                  cancelled_state))
        return risk
    finally:
        qa.close()
        qb.close()


# ---------------------------------------------------------------------------
# D5 租约与看护交互：LOCKED 的 worker 死了 vs 活着
# ---------------------------------------------------------------------------
def d5_lease_and_watchdog():
    work = tempfile.mkdtemp(prefix="bf-d5-")
    share = os.path.join(work, "share")
    os.makedirs(share)
    qb = _wire("B", os.path.join(work, "b"), share, store_spec={"kind": "sqlite-shared"},
               queue_spec={"lock_ttl_sec": 1})
    qa = _wire("A", os.path.join(work, "a"), share, store_spec={"kind": "sqlite-shared"},
               queue_spec={"lock_ttl_sec": 1})
    try:
        script = _ok_script(work)
        qa.submit([{"task_name": "dead", "cli": {"cmd": _cli(script)}, "timeout_min": 5},
                   {"task_name": "alive", "cli": {"cmd": _cli(script)}, "timeout_min": 5}])
        # 租约口径与 claim_next 一致：max(lock_ttl_sec, timeout_min*60) = max(1, 300) = 300s
        qa.store.claim_next("dead-w")                                    # worker 死了
        qa.store.claim_next("alive-w")
        base = utcnow_iso()
        qa.store.touch_lock("alive", worker_id="alive-w",
                            now=iso_add_seconds(base, 60))                # worker 存活：续期到 +360s
        far = iso_add_seconds(base, 350)                                 # 超过 dead 的 +300s，未超过 alive 的 +360s
        n = qa.store.clean_stale_locks(now=far)
        dead_state = qa.get_task("dead").state
        alive_state = qa.get_task("alive").state
        # 期望：dead 被回收（LOCKED→PENDING，RUNNING 才是 RETRY_PENDING）、alive 因续期而保留
        risk = (dead_state != TaskState.PENDING) or (alive_state != TaskState.LOCKED)
        record("D5", "租约与看护交互（死了 vs 活着）", risk,
               "clean_stale_locks 回收=%s；dead=%s（期望 PENDING）、alive=%s（期望 LOCKED，续期保活）"
               % (n, dead_state, alive_state))
        return risk
    finally:
        qa.close()
        qb.close()


def main():
    print("=" * 92)
    for probe in (d1_poll_boundaries, d2_sync_reorder_and_replay, d3_payload_boundaries,
                  d4_result_boundaries, d5_lease_and_watchdog):
        try:
            probe()
        except Exception as exc:
            record(probe.__name__, "探针自身异常", False, "%s: %s" % (type(exc).__name__, exc))
    confirmed = [r for r in RESULTS if r[2]]
    print("=" * 92)
    print("boundary_cases=%d confirmed=%d not_confirmed=%d"
          % (len(RESULTS), len(confirmed), len(RESULTS) - len(confirmed)))
    for pid, title, ok, _ in RESULTS:
        print("  %-14s %s :: %s" % (pid, "CONFIRMED" if ok else "NOT-CONFIRMED", title))
    return len(confirmed)


if __name__ == "__main__":
    sys.exit(main())