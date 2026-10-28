# -*- coding: utf-8 -*-
"""Round 8 bugfind 探针：常驻消费容错 / 崩溃回收计数 / 续期间隔校验。

只读探针：在临时目录建库，不触碰仓库内任何数据文件。输出 JSON 结论。
"""
import json
import os
import sys
import tempfile
import traceback

RHOP = r"E:\IDEProjects\AI\vools\rhop"
sys.path.insert(0, RHOP)
sys.path.insert(0, r"E:\IDEProjects\AI\vools")

from vools.rhop.task.config import TaskConfig, DEFAULT_QUEUE
from vools.rhop.task.errors import StoreError
from vools.rhop.task.models import TaskState, iso_add_seconds, utcnow_iso
from vools.rhop.task.queue import TaskQueue

OUT = {}


def cfg(base, **queue_over):
    queue = {"store": {"kind": "sqlite-shared"}, "poll_interval_sec": 0.01}
    queue.update(queue_over)
    data = {"name": "probe", "role": "B", "key": "probe-key",
            "shared": {"write": base}, "queue": queue,
            "exec": {"allow": ["handler:*", "action:*"]}}
    return TaskConfig.from_dict(data, base_dir=base, warn_plaintext=False)


# ---------------------------------------------------------------- 探针 1
# 常驻循环是否对单次迭代异常做隔离
def probe_resident():
    base = tempfile.mkdtemp(prefix="rhop-probe1-")
    q = TaskQueue(cfg(base))

    calls = {"n": 0}
    real = q.store.claim_next

    def flaky(wid, **kw):
        calls["n"] += 1
        if calls["n"] == 2:                      # 第二次迭代瞬时故障
            raise StoreError("模拟瞬时数据库错误")
        return real(wid, **kw)

    q.store.claim_next = flaky
    try:
        stats = q.run_resident(max_iterations=5)
        OUT["resident"] = {"survived": True, "stats": stats}
    except BaseException as exc:                  # noqa: BLE001 - 记录形态即可
        OUT["resident"] = {"survived": False, "type": type(exc).__name__,
                           "msg": str(exc), "iterations_attempted": calls["n"],
                           "trace_tail": traceback.format_exc().strip().splitlines()[-3:]}
    finally:
        q.close()


# ---------------------------------------------------------------- 探针 2
# 崩溃回收是否计入重试上限
def probe_reclaim_cap():
    base = tempfile.mkdtemp(prefix="rhop-probe2-")
    q = TaskQueue(cfg(base, max_retries=1, lock_ttl_sec=1),
                  handlers={"probe:ok": lambda payload, ctx: {"ok": True, "result": "ok"}})
    q.submit([{"task_name": "crashy", "task_type": "HANDLER",
               "handler": {"name": "probe:ok"}, "max_retries": 1}])
    cycles = []
    for i in range(5):
        rec = q.store.claim_next("w%d" % i)
        if rec is None:
            cycles.append({"cycle": i, "claim": "none"})
            break
        # 模拟 worker 在 LOCKED/RUNNING 期间崩溃：直接让租约过期并回收
        q.store.set_state(rec.task_name, TaskState.RUNNING, now=utcnow_iso(),
                          worker_id="w%d" % i)
        future = iso_add_seconds(utcnow_iso(), 7200)
        reclaimed = q.store.clean_stale_locks(now=future)
        cur = q.store.get_task("crashy")
        cycles.append({"cycle": i, "claimed": rec.task_name, "reclaimed": reclaimed,
                       "state": cur.state, "retry_count": cur.retry_count,
                       "max_retries": cur.max_retries})
    OUT["reclaim"] = {"cycles": cycles,
                      "still_alive_after_5": q.store.get_task("crashy").state,
                      "final_retry_count": q.store.get_task("crashy").retry_count}
    q.close()


# ---------------------------------------------------------------- 探针 3
# renew_interval_sec 是否有配置校验（对照 BUG-282 的 stale_after 校验）
def probe_renew_interval():
    base = tempfile.mkdtemp(prefix="rhop-probe3-")
    accepted = True
    err = None
    try:
        c = cfg(base, renew_lock=True, renew_interval_sec=100000, lock_ttl_sec=60)
    except Exception as exc:                      # noqa: BLE001
        accepted = False
        err = "%s: %s" % (type(exc).__name__, exc)
    OUT["renew_interval"] = {
        "accepted_interval_gt_ttl": accepted,
        "error": err,
        "renew_interval_sec_in_DEFAULT_QUEUE": "renew_interval_sec" in DEFAULT_QUEUE,
        "normalized_value": (c.queue.get("renew_interval_sec") if accepted else None),
        "lock_ttl_sec": c.queue.get("lock_ttl_sec") if accepted else None,
        "clamp_evidence": "queue.py: interval = max(0.5, min(interval, ttl)) → 静默压到 ttl",
    }


# ---------------------------------------------------------------- 附加
# 交叉验证：其实例能否被 claim_next 反复领取（探针 2 的对照组）
def probe_claimable_again():
    base = tempfile.mkdtemp(prefix="rhop-probe4-")
    q = TaskQueue(cfg(base, lock_ttl_sec=1),
                  handlers={"probe:ok": lambda payload, ctx: {"ok": True, "result": "ok"}})
    q.submit([{"task_name": "again", "task_type": "HANDLER",
               "handler": {"name": "probe:ok"}}])
    claims = 0
    for i in range(3):
        rec = q.store.claim_next("w%d" % i)
        if rec is None:
            break
        claims += 1
        q.store.clean_stale_locks(now=iso_add_seconds(utcnow_iso(), 7200))
    OUT["claimable_again"] = {"claims_after_same_lease_expiry": claims, "expected": 3}
    q.close()


# ---------------------------------------------------------------- 探针 5
# 执行期间被 requeue（运维重跑）→ 收尾时非法状态流转？
# 对照：执行期间 cancel（置标志）→ 应优雅落 CANCELLED，不抛错
def probe_stale_finish():
    from vools.rhop.task.exec import HANDLERS, register_handler

    base = tempfile.mkdtemp(prefix="rhop-probe5-")
    holder = {}

    def requeue_self(payload):
        holder["q"].store.requeue(payload["task_name"])   # 模拟执行期间运维 requeue
        return "done-after-requeue"

    def cancel_self(payload):
        holder["q"].cancel(payload["task_name"])          # 模拟执行期间取消（置标志）
        return "done-after-cancel-flag"

    res = {}
    for name, hname, fn in (("req", "probe:requeue", requeue_self),
                            ("can", "probe:cancel", cancel_self)):
        b2 = tempfile.mkdtemp(prefix="rhop-probe5%s-" % name)
        q = TaskQueue(cfg(b2))
        holder["q"] = q
        register_handler(hname, fn)
        q.handlers[hname] = HANDLERS[hname]
        q.submit([{"task_name": "stale-%s" % name, "task_type": "HANDLER",
                   "handler": hname}])
        try:
            out = q.run_once("w-%s" % name)
            rec = q.store.get_task("stale-%s" % name)
            res[name] = {"run_once": out.get("action"), "final_state": rec.state,
                         "raised": None, "last_err": rec.last_err}
        except BaseException as exc:              # noqa: BLE001
            rec = q.store.get_task("stale-%s" % name)
            res[name] = {"run_once": "raised", "final_state": rec.state,
                         "raised": "%s: %s" % (type(exc).__name__, exc),
                         "last_err": rec.last_err}
        q.handlers.pop(hname, None)
        HANDLERS.pop(hname, None)
        q.close()
    OUT["stale_finish"] = res


for fn in (probe_resident, probe_reclaim_cap, probe_renew_interval,
           probe_claimable_again, probe_stale_finish):
    try:
        fn()
    except BaseException as exc:                  # noqa: BLE001
        OUT[fn.__name__] = {"probe_crashed": "%s: %s" % (type(exc).__name__, exc)}

print(json.dumps(OUT, ensure_ascii=False, indent=2))
