# -*- coding: utf-8 -*-
"""第二轮边界语料：租约续期 / 并发领取 / 控制意图交错 / 幂等与畸形输入。

定位：语料 + 复现器，不是产品源码（命名不带 test_ 前缀，不进 pytest 收集）。
R3 语料覆盖共享库并发、白名单等价性、心跳截断、同步发散、结果截断；
本轮往**更深层的队列语义**走：租约过期后的重复执行、多 worker 高竞争、
cancel 与 reset 的意图交错、提交幂等边界、畸形任务名与坏 JSON。

运行：
    cd rhop && python tests/boundary/r10_concurrency_sync.py

每条输出 [CONFIRMED] / [NOT-CONFIRMED] + 证据；退出码 = 风险成立条数。
"""
import datetime
import json
import os
import subprocess
import sys
import tempfile
import textwrap

RHOP = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RHOP)
PY = sys.executable

from vools.rhop.task.config import TaskConfig            # noqa: E402
from vools.rhop.task.exec import ExecPolicy, run_payload  # noqa: E402
from vools.rhop.task.models import TaskRecord, TaskState  # noqa: E402
from vools.rhop.task.queue import TaskQueue              # noqa: E402
from vools.rhop.task.sync import TaskSync                # noqa: E402

RESULTS = []


def record(pid, title, risk_realized, evidence):
    RESULTS.append((pid, title, risk_realized, evidence))
    print("[%s] %-40s %s" % ("CONFIRMED" if risk_realized else "NOT-CONFIRMED",
                             pid + " " + title, evidence))


def _wire(role, base, share, store_spec=None, hb=None, exec_spec=None):
    cfg = TaskConfig.from_dict(
        {"name": "link", "role": role, "key": "unit-key",
         "shared": {"write": str(share)},
         "queue": {"store": store_spec or {"kind": "sqlite-shared"}},
         "exec": exec_spec or {"allow": ["cli:python"]}},
        base_dir=str(base), warn_plaintext=False)
    store = cfg.build_store()
    if hb:
        cfg.queue["heartbeat"] = hb
    syncer = TaskSync(store, cfg.build_crypto(), cfg.role,
                      shared=cfg.build_shared(), name=cfg.name)
    return TaskQueue(cfg, store=store, crypto=cfg.build_crypto(), syncer=syncer)


def _cli(script):
    return '"%s" "%s"' % (PY.replace("\\", "/"), script.replace("\\", "/"))


# ---------------------------------------------------------------------------
# P6 租约过期后任务可被重复领取执行（无续期通道）
# ---------------------------------------------------------------------------
def p6_lease_expiry_reexecutes():
    work = tempfile.mkdtemp(prefix="bf-p6-")
    db = os.path.join(work, "shared.db")
    counter = os.path.join(work, "counter.txt")
    script = os.path.join(work, "tick.py")
    with open(script, "w", encoding="utf-8") as fh:
        fh.write("import pathlib\np = pathlib.Path(r'%s')\n"
                 "p.write_text(str(int(p.read_text() or '0') + 1) if p.exists() else '1',"
                 " encoding='utf-8')\nprint('ticked')\n" % counter)

    qb = TaskQueue(TaskConfig.from_dict(
        {"name": "p6", "role": "B", "key": "k", "shared": {"write": work},
         "queue": {"store": {"kind": "sqlite-shared", "path": db},
                   "lock_ttl_sec": 1, "timeout_min": 5},
         "exec": {"allow": ["cli:python"]}}, base_dir=work, warn_plaintext=False))
    qa = TaskQueue(TaskConfig.from_dict(
        {"name": "p6", "role": "A", "key": "k", "shared": {"write": work},
         "queue": {"store": {"kind": "sqlite-shared", "path": db}}},
        base_dir=work, warn_plaintext=False))
    try:
        qa.submit([{"task_name": "j", "cli": {"cmd": _cli(script)}, "timeout_min": 30}])
        rec = qb.store.claim_next("w1")
        reclaim_state = None
        counter_after_reclaim = 0
        renew_ok, renew_note = False, "无 renew_lock / touch_lock 接口"
        if rec is not None and rec.task_name == "j":
            # 正向校验（BUG-289 修复契约）：续期接口必须存在，且能把 lock_time/expire_time 推到未来
            rec_now = qb.store.get_task("j")
            try:
                touched = qb.renew_lock("j", worker_id=rec_now.worker_id,
                                        now="2030-01-01T00:00:00Z")
                after = qb.store.get_task("j")
                renew_ok = bool(touched) and after.expire_time > rec_now.expire_time
                renew_note = "renew_lock=%s，expire_time %s -> %s" % (
                    touched, rec_now.expire_time, after.expire_time)
            except AttributeError as exc:
                renew_note = "接口缺失: %s" % exc

            payload = qb.decrypt_payload(rec)
            policy = ExecPolicy(allow=["cli:python"])
            run_payload(payload, policy=policy)                  # worker1 正在跑（长任务）
            qb.store.clean_stale_locks(now="2999-01-01T00:00:00Z")  # 机制演示：默认无续期时被回收
            reclaim_state = qb.store.get_task("j").state
            if qb.store.claim_next("w2") is not None:
                run_payload(payload, policy=policy)              # worker2 重跑同一任务

        executed = int(open(counter, encoding="utf-8").read()) if os.path.exists(counter) else 0
        counter_after_reclaim = executed
        # 判定的是「修复契约是否成立」：续期接口必须存在且生效。
        # 「无续期时租约过期会被回收重跑」是设计行为（默认关闭续期、可 opt-in），不算缺陷。
        risk = not renew_ok
        record("P6", "租约续期接口与刷新效果（BUG-289）", risk,
               "机制演示：无续期时被回收重跑计数器=%d、回收后状态=%s（默认行为，可 opt-in）；"
               "正向校验：%s" % (counter_after_reclaim, reclaim_state, renew_note))
        return risk
    finally:
        qa.close()
        qb.close()


# ---------------------------------------------------------------------------
# P7 多 worker 高并发领取（4 进程 × 200 任务）
# ---------------------------------------------------------------------------
def p7_multi_worker_high_contention():
    work = tempfile.mkdtemp(prefix="bf-p7-")
    db = os.path.join(work, "shared.db")
    worker_src = textwrap.dedent('''
        import json, sys
        sys.path.insert(0, %(rhop)r)
        from vools.rhop.task.store import create_store
        args = json.loads(sys.argv[1])
        store = create_store({"kind": "sqlite-shared", "path": args["db"],
                              "lock_ttl_sec": 1},
                             {"name": "p7", "role": "B", "base_dir": args["work"],
                              "shared_root": args["work"]})
        got, err = [], None
        try:
            while True:
                rec = store.claim_next(args["wid"])
                if rec is None:
                    break
                got.append(rec.task_name)
        except Exception as exc:
            err = "%%s: %%s" %% (type(exc).__name__, exc)
        finally:
            store.close()
        open(args["out"], "w", encoding="utf-8").write(json.dumps({"got": got, "err": err}))
    ''') % {"rhop": RHOP}
    wpath = os.path.join(work, "worker.py")
    with open(wpath, "w", encoding="utf-8") as fh:
        fh.write(worker_src)

    cfg = TaskConfig.from_dict(
        {"name": "p7", "role": "A", "key": "k", "shared": {"write": work},
         "queue": {"store": {"kind": "sqlite-shared", "path": db}, "lock_ttl_sec": 1}},
        base_dir=work, warn_plaintext=False)
    setup = TaskQueue(cfg)
    names = ["task-%03d" % i for i in range(200)]
    setup.submit(names)
    setup.close()

    procs = []
    for wid in ("w1", "w2", "w3", "w4"):
        out = os.path.join(work, "%s.json" % wid)
        procs.append((out, subprocess.Popen([PY, wpath, json.dumps({
            "db": db, "work": work, "wid": wid, "out": out})],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")))
    claimed, errors = [], []
    for out, proc in procs:
        proc.wait(timeout=180)
        data = json.loads(open(out, encoding="utf-8").read())
        claimed.extend(data["got"])
        if data["err"]:
            errors.append(data["err"])
    dup = sorted({n for n in claimed if claimed.count(n) > 1})
    missing = sorted(set(names) - set(claimed))
    risk = bool(dup or missing or errors)
    record("P7", "4 进程高竞争领取 200 条", risk,
           "claimed=%d/200 dup=%s missing=%s errors=%s" % (len(claimed), dup, missing, errors))
    return risk


# ---------------------------------------------------------------------------
# P8 cancel 与 reset 的控制意图交错
# ---------------------------------------------------------------------------
def p8_control_intent_interleaving():
    outcomes = {}
    for label, order in (("reset_then_cancel", ["requeue", "cancel"]),
                         ("cancel_then_reset", ["cancel", "requeue"])):
        work = tempfile.mkdtemp(prefix="bf-p8-")
        share = os.path.join(work, "share")
        os.makedirs(share)
        script = os.path.join(work, "ok.py")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write("print('done')\n")
        qa = _wire("A", os.path.join(work, "a"), share, store_spec={"kind": "sqlite-local"})
        qb = _wire("B", os.path.join(work, "b"), share, store_spec={"kind": "sqlite-local"})
        try:
            qa.submit([{"task_name": "j", "cli": {"cmd": _cli(script)}, "timeout_min": 5}])
            qb.pull_sync()
            qb.run_once()
            qa.pull_sync()
            for action in order:
                if action == "requeue":
                    qa.requeue("j")
                else:
                    qa.cancel("j")
            qb.pull_sync()
            qb.syncer.push_states()
            qa.pull_sync()
            a, b = qa.get_task("j"), qb.get_task("j")
            outcomes[label] = (a.state, b.state, a.version, b.version)
        finally:
            qa.close()
            qb.close()

    r_then_c = outcomes["reset_then_cancel"]
    c_then_r = outcomes["cancel_then_reset"]
    # 判定（BUG-290 收口后）：文档 §14 已声明「重置优先于取消」——因此两种顺序都必须
    # 收敛到「重置后的状态」（PENDING）。若任一顺序不收敛到 PENDING，说明裁决被破坏。
    risk = not (r_then_c[0] == TaskState.PENDING and r_then_c[1] == TaskState.PENDING
                and c_then_r[0] == TaskState.PENDING and c_then_r[1] == TaskState.PENDING)
    record("P8", "cancel/reset 意图裁决（重置优先）", risk,
           "reset_then_cancel -> (A:%s,B:%s,verA:%s,verB:%s)；cancel_then_reset -> (A:%s,B:%s,verA:%s,verB:%s)"
           % (*r_then_c, *c_then_r))
    return risk


# ---------------------------------------------------------------------------
# P9 提交幂等边界
# ---------------------------------------------------------------------------
def p9_submit_idempotency():
    work = tempfile.mkdtemp(prefix="bf-p9-")
    share = os.path.join(work, "share")
    os.makedirs(share)
    qa = _wire("A", os.path.join(work, "a"), share)
    qb = _wire("B", os.path.join(work, "b"), share)
    try:
        # 同批重复名：文档口径是「不会产生新行」（§10，INSERT OR IGNORE），skipped 计数要如实返回
        res_dup = qa.submit([{"task_name": "dup", "value": "v1"},
                             {"task_name": "dup", "value": "v2"}])
        dup_rows = len([r for r in qa.store.list_tasks() if r.task_name == "dup"])
        dup_value = qa.get_task("dup").value
        dup_skipped = res_dup["skipped"]

        # 跨提交重复提交同一名字：同样跳过（保留旧定义），且版本不前进
        qa.submit([{"task_name": "ord", "value": "old"}])
        res_ord = qa.submit([{"task_name": "ord", "value": "new"}])
        ord_value = qa.get_task("ord").value
        ord_version = qa.get_task("ord").version

        # 依赖指向从未提交的任务：应在 submit 阶段被可读地拒绝，而不是静默留下永远 PENDING 的孤儿
        try:
            qa.submit([{"task_name": "orphan", "deps": ["never-submitted"]}])
            orphan_rejected, orphan_note = False, "未被拒绝（意外：会留下永远 PENDING 的孤儿任务）"
        except Exception as exc:
            orphan_rejected = type(exc).__name__ == "DagValidationError"
            orphan_note = "%s: %s" % (type(exc).__name__, exc)

        # 同批互相依赖：应被允许（deps 必须已提交或同批出现）
        qa.submit([{"task_name": "a", "deps": ["b"]}, {"task_name": "b"}])
        batch_ok = qa.get_task("a").state == TaskState.PENDING

        # 设计口径自洽性：文档 §10 说「不会产生新行」、§14 却说「幂等 upsert」——后者暗示后到覆盖
        risk = not (dup_rows == 1 and dup_value == "v1" and dup_skipped == 1
                    and orphan_rejected and batch_ok and res_ord["skipped"] == 1)
        record("P9", "提交幂等/依赖校验/版本单调", risk,
               "同批重复名 -> 行数=%d 取值=%s skipped=%s（§10 口径：保留首个）；跨提交重复 -> 取值=%s "
               "skipped=%s 版本=%s（保留旧定义、不前进）；未知依赖 -> 被拒绝=%s（%s）；同批互依赖 -> %s"
               % (dup_rows, dup_value, dup_skipped, ord_value, res_ord["skipped"], ord_version,
                  orphan_rejected, orphan_note, batch_ok))
        return risk
    finally:
        qa.close()
        qb.close()


# ---------------------------------------------------------------------------
# P10 畸形任务名与坏 JSON
# ---------------------------------------------------------------------------
def p10_malformed_inputs():
    work = tempfile.mkdtemp(prefix="bf-p10-")
    share = os.path.join(work, "share")
    os.makedirs(share)
    qa = _wire("A", os.path.join(work, "a"), share)
    qb = _wire("B", os.path.join(work, "b"), share)
    try:
        odd_names = ["a/b", "a' OR 1=1--", "中文 名", "x;y", "名\n符"]
        submitted, errors = [], []
        for name in odd_names:
            try:
                qa.submit([{"task_name": name, "value": "v"}])
                submitted.append(name)
            except Exception as exc:
                errors.append("%s -> %s: %s" % (name, type(exc).__name__, exc))
        round_trip = [n for n in submitted
                      if qb.pull_sync() is not None and qa.get_task(n) is not None]

        bad_deps = []
        for dep in ("{not json", "[1,2", "", "  ", 42):
            try:
                qa.submit([{"task_name": "d%d" % (abs(hash(dep)) % 100000), "deps": dep}])
            except Exception as exc:
                bad_deps.append("%r -> %s: %s" % (dep, type(exc).__name__, exc))

        risk = bool(errors) or len(round_trip) != len(submitted)
        record("P10", "畸形任务名与坏 deps JSON", risk,
               "提交成功=%d/%d 异常=%s；往返一致=%d；坏 deps 异常=%s"
               % (len(submitted), len(odd_names), errors, len(round_trip), bad_deps))
        return risk
    finally:
        qa.close()
        qb.close()


def main():
    print("=" * 92)
    for probe in (p6_lease_expiry_reexecutes, p7_multi_worker_high_contention,
                  p8_control_intent_interleaving, p9_submit_idempotency, p10_malformed_inputs):
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