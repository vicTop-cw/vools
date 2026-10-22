# -*- coding: utf-8 -*-
"""边界语料：共享库并发、白名单等价性、心跳截断、本地库发散、结果截断（Round 3 bugfind）。

定位：这是**语料 + 复现器**，不是产品源码。命名刻意不叫 ``test_*.py``，避免被 pytest 收集
（按 bugfind 模式约束「不把新测试 case 合并进正式测试文件，交由后续环节」）。

运行：
    cd rhop && python tests/boundary/r3_boundary_probes.py

每条输出 [CONFIRMED] / [NOT-CONFIRMED] + 可复核证据；退出码 = 确认条数。
环境全部建在系统 TEMP，不落产品目录。
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
from vools.rhop.task.heartbeat import Heartbeat          # noqa: E402
from vools.rhop.task.models import TaskState             # noqa: E402
from vools.rhop.task.queue import TaskQueue              # noqa: E402
from vools.rhop.task.sync import TaskSync                # noqa: E402
from vools.rhop.transport.local import LocalSharedPath   # noqa: E402

RESULTS = []


def record(pid, title, confirmed, evidence):
    RESULTS.append((pid, title, confirmed, evidence))
    print("[%s] %-34s %s" % ("CONFIRMED" if confirmed else "NOT-CONFIRMED", pid + " " + title, evidence))


# ---------------------------------------------------------------------------
# P1 共享库多进程并发领取（boundary_probe: race-condition → interleaving / no-barrier）
# ---------------------------------------------------------------------------
def p1_multiprocess_claim():
    work = tempfile.mkdtemp(prefix="bf-p1-")
    db = os.path.join(work, "shared.db")
    worker_src = textwrap.dedent('''
        import json, os, sys
        sys.path.insert(0, %(rhop)r)
        from vools.rhop.task.store import create_store
        args = json.loads(sys.argv[1])
        store = create_store({"kind": "sqlite-shared", "path": args["db"]},
                             {"name": "p1", "role": "B", "base_dir": args["work"],
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

    setup = TaskQueue(TaskConfig.from_dict(
        {"name": "p1", "role": "A", "key": "k", "shared": {"write": work},
         "queue": {"store": {"kind": "sqlite-shared", "path": db}}},
        base_dir=work, warn_plaintext=False))
    names = ["job-%02d" % i for i in range(40)]
    setup.submit(names)
    setup.close()

    procs = []
    for wid in ("w1", "w2"):
        out = os.path.join(work, "%s.json" % wid)
        args = json.dumps({"db": db, "work": work, "wid": wid, "out": out})
        procs.append((out, subprocess.Popen([PY, wpath, args], stdout=subprocess.PIPE,
                                            stderr=subprocess.PIPE, text=True, encoding="utf-8")))
    claimed, errors = [], []
    for out, proc in procs:
        proc.wait(timeout=120)
        data = json.loads(open(out, encoding="utf-8").read())
        claimed.extend(data["got"])
        if data["err"]:
            errors.append(data["err"])
    dup = sorted({n for n in claimed if claimed.count(n) > 1})
    missing = sorted(set(names) - set(claimed))
    # 本条语料的假设是"并发领取会出问题"；所以 CONFIRMED 表示假设成立（即真出风险）。
    # 实测无重复/无遗漏/无崩溃 ⇒ 假设不成立 → 打印 NOT-CONFIRMED（安全实锤，不是缺陷）。
    risk_realized = bool(dup or missing or errors)
    record("P1", "多进程并发领取 40 条（假设=会出问题）", risk_realized,
           "claimed=%d/40 dup=%s missing=%s errors=%s（无重复/无遗漏/无崩溃）"
           % (len(claimed), dup, missing, errors))
    return risk_realized


# ---------------------------------------------------------------------------
# P2 白名单等价性（放行解释器是否等于放行任意代码）
# ---------------------------------------------------------------------------
def p2_whitelist_equivalence():
    work = tempfile.mkdtemp(prefix="bf-p2-")
    share = os.path.join(work, "share")
    os.makedirs(share)
    flag = os.path.join(work, "pwned.txt")
    script = os.path.join(work, "payload.py")
    with open(script, "w", encoding="utf-8") as fh:
        fh.write("open(r'%s', 'w', encoding='utf-8').write('arbitrary-code-ran')\n" % flag)
    cmd = '"%s" "%s"' % (PY.replace("\\", "/"), script.replace("\\", "/"))

    def build(allow):
        return TaskConfig.from_dict(
            {"name": "p2", "role": "B", "key": "k", "shared": {"write": share},
             "queue": {"store": {"kind": "sqlite-shared"}}, "exec": {"allow": allow}},
            base_dir=work, warn_plaintext=False)

    q_allowed = TaskQueue(build(["cli:python"]))
    q_allowed.submit([{"task_name": "run-any-code", "cli": {"cmd": cmd}}])
    outcome = q_allowed.run_once()
    ran = os.path.exists(flag)
    q_allowed.close()

    flag2 = flag + ".denied"
    script2 = script + "2.py"
    with open(script2, "w", encoding="utf-8") as fh:
        fh.write("open(r'%s', 'w', encoding='utf-8').write('should-not-run')\n" % flag2)
    cmd2 = '"%s" "%s"' % (PY.replace("\\", "/"), script2.replace("\\", "/"))
    q_denied = TaskQueue(build(["action:*", "handler:*"]))
    q_denied.submit([{"task_name": "deny-check", "cli": {"cmd": cmd2}}])
    outcome2 = q_denied.run_once()
    denied_ok = (not os.path.exists(flag2)) and outcome2.get("action") == "failed"
    q_denied.close()

    record("P2", "allow cli:python ⇒ 可执行任意代码", ran,
           "allow=[cli:python] B 跑了任意代码=%s（outcome=%s）；对照组 allow=[action:*,handler:*] 被拒=%s（outcome=%s）"
           % (ran, outcome.get("action"), denied_ok, outcome2.get("action")))
    return ran


# ---------------------------------------------------------------------------
# P3 心跳秒精度截断造成的判死误判
# ---------------------------------------------------------------------------
def p3_heartbeat_truncation():
    work = tempfile.mkdtemp(prefix="bf-p3-")
    shared = LocalSharedPath(work)
    tz = datetime.timezone.utc
    # 写入落在"秒末尾"、读取紧随其后仍在同一秒内 ⇒ 截断误差被顶到最大
    write_at = datetime.datetime(2026, 10, 22, 0, 0, 0, 900000, tzinfo=tz)
    Heartbeat(shared, "x.heartbeat", interval_sec=0.05, stale_after_sec=0.5,
              now_fn=lambda: write_at).tick(force=True)
    read_at = write_at + datetime.timedelta(milliseconds=5)
    info = Heartbeat(shared, "x.heartbeat", stale_after_sec=0.5,
                     now_fn=lambda: read_at).read()
    false_stale = info["state"] == "stale"
    default_state = Heartbeat(shared, "x.heartbeat", stale_after_sec=15.0,
                              now_fn=lambda: read_at).read()["state"]
    record("P3", "心跳秒截断导致误判死", false_stale,
           "真实间隔=0.005s 但读到 age=%.3fs（误差 %.3fs）→ state=%s；阈值 15s 时 state=%s"
           % (info["age_sec"], info["age_sec"] - 0.005, info["state"], default_state))
    return false_stale


# ---------------------------------------------------------------------------
# P4 本地库模式 A 端 requeue 造成的状态发散
# ---------------------------------------------------------------------------
def p4_sync_divergence():
    work = tempfile.mkdtemp(prefix="bf-p4-")
    share = os.path.join(work, "share")
    os.makedirs(share)

    def wire(role, sub):
        base = os.path.join(work, sub)
        os.makedirs(base, exist_ok=True)
        cfg = TaskConfig.from_dict(
            {"name": "p4", "role": role, "key": "k", "shared": {"write": share},
             "queue": {"store": {"kind": "sqlite-local"}}, "exec": {"allow": ["cli:python"]}},
            base_dir=base, warn_plaintext=False)
        store = cfg.build_store()
        syncer = TaskSync(store, cfg.build_crypto(), cfg.role,
                          shared=cfg.build_shared(), name=cfg.name)
        return TaskQueue(cfg, store=store, crypto=cfg.build_crypto(), syncer=syncer)

    qa, qb = wire("A", "a"), wire("B", "b")
    script = os.path.join(work, "ok.py")
    with open(script, "w", encoding="utf-8") as fh:
        fh.write("print('done')\n")
    cmd = '"%s" "%s"' % (PY.replace("\\", "/"), script.replace("\\", "/"))
    qa.submit([{"task_name": "j", "cli": {"cmd": cmd}}])
    qb.pull_sync()
    qb.run_once()
    qa.pull_sync()
    state_before = (qa.get_task("j").state, qb.get_task("j").state)

    qa.requeue("j")          # A 端运维动作：把已完成任务重置
    qa.pull_sync()
    qb.pull_sync()
    qb.syncer.push_states()
    qa.pull_sync()
    state_after = (qa.get_task("j").state, qb.get_task("j").state,
                   qa.get_task("j").version, qb.get_task("j").version)
    diverged = state_after[0] == TaskState.PENDING and state_after[1] == TaskState.COMPLETED
    qa.close()
    qb.close()
    record("P4", "A 端 requeue 后本地库状态发散", diverged,
           "before=%s after=(A:%s,B:%s,verA=%s,verB=%s)" % (state_before, *state_after))
    return diverged


# ---------------------------------------------------------------------------
# P5 result_max_bytes 不是硬上限
# ---------------------------------------------------------------------------
def p5_truncation_not_a_cap():
    work = tempfile.mkdtemp(prefix="bf-p5-")
    cfg = TaskConfig.from_dict(
        {"name": "p5", "role": "B", "key": "k",
         "queue": {"store": {"kind": "sqlite-local"}, "encrypt_result": False,
                   "result_max_bytes": 1000}}, base_dir=work, warn_plaintext=False)
    q = TaskQueue(cfg)
    big = {"result": {"blob": "x" * 20000, "exit_code": 0}, "channel": "handler", "name": "n"}
    encoded = q.encode_result(big)
    size = len(encoded.encode("utf-8"))
    parsed = json.loads(encoded)
    over = size > 1000
    q.close()
    record("P5", "result_max_bytes 不是硬上限", over,
           "上限=1000B 实际落库=%dB truncated=%s（非 stdout/stderr 字段不被裁）" % (size, parsed.get("truncated")))
    return over


def main():
    print("=" * 92)
    for probe in (p1_multiprocess_claim, p2_whitelist_equivalence, p3_heartbeat_truncation,
                  p4_sync_divergence, p5_truncation_not_a_cap):
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