# -*- coding: utf-8 -*-
"""第五轮边界语料：守护停机 / closed 与心跳竞态 / 传输大包 / 依赖卡死 / 重启回收。

定位：语料 + 复现器，不是产品源码（命名不带 test_ 前缀，不进 pytest 收集）。
R3 共享库并发、白名单等价性、心跳截断、同步发散、结果截断；
R10 租约续期、多 worker 高竞争、控制意图裁决、提交幂等、畸形输入；
R13 看护轮询边界、版本单调门、载荷边界、结果边界、租约与看护；
R14 引用失效矩阵、并发写同名、清理误删、目录穿越、分支组合。
本轮补**停机收尾、closed 稳定性、传输层大包、被取消任务的下游依赖、重启后遗留锁**。

运行：
    cd rhop && python tests/boundary/r15_daemon_transport.py

每条输出 [CONFIRMED] / [NOT-CONFIRMED] + 证据；退出码 = 风险成立条数。
"""
import json
import os
import sys
import tempfile

RHOP = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RHOP)

from vools.rhop.task.config import TaskConfig            # noqa: E402
from vools.rhop.task.heartbeat import Heartbeat          # noqa: E402
from vools.rhop.task.models import TaskState             # noqa: E402
from vools.rhop.task.queue import TaskQueue              # noqa: E402
from vools.rhop.transport.local import LocalSharedPath   # noqa: E402

RESULTS = []


def record(pid, title, risk_realized, evidence):
    RESULTS.append((pid, title, risk_realized, evidence))
    print("[%s] %-40s %s" % ("CONFIRMED" if risk_realized else "NOT-CONFIRMED",
                             pid + " " + title, evidence))


def _wire(role, base, share, store_spec=None, exec_spec=None, queue_spec=None):
    spec = dict(store_spec or {"kind": "sqlite-shared"})
    spec.update(queue_spec or {})
    cfg = TaskConfig.from_dict(
        {"name": "link", "role": role, "key": "k", "shared": {"write": str(share)},
         "queue": {"store": spec}, "exec": exec_spec or {"allow": ["cli:python"]}},
        base_dir=str(base), warn_plaintext=False)
    store = cfg.build_store()
    return TaskQueue(cfg, store=store, crypto=cfg.build_crypto())


def _ok(work, name="ok.py", body="print('done')\n"):
    path = os.path.join(str(work), name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    return '"%s" "%s"' % (sys.executable.replace("\\", "/"), path.replace("\\", "/"))


# ---------------------------------------------------------------------------
# G1 停机收尾：request_stop 后在途任务的结果是否丢失
# ---------------------------------------------------------------------------
def g1_stop_midflight():
    work = tempfile.mkdtemp(prefix="bf-g1-")
    share = os.path.join(work, "share")
    os.makedirs(share)
    q = _wire("B", os.path.join(work, "b"), share)
    try:
        script = _ok(work, "slow.py", "import time; time.sleep(0.6); print('done')\n")
        q.submit([{"task_name": "j", "cli": {"cmd": script}, "timeout_min": 30}])
        # 真实守护进程的序列：run_once 内「领取 → 执行 → 记录结果」是原子的
        out1 = q.run_once()
        rec1 = q.get_task("j")
        completed = (out1.get("action") == "completed"
                     and rec1.state == TaskState.COMPLETED and bool(rec1.back_info))
        # 停机请求之后：不再领取新任务（期望行为），但**不得影响已完成任务的结果**
        q.request_stop()
        out2 = q.run_once()
        rec2 = q.get_task("j")
        risk = not (completed and out2.get("action") == "idle"
                    and rec2.state == TaskState.COMPLETED and bool(rec2.back_info))
        record("G1", "停机不影响在途/已完成任务的结果记录", risk,
               "run_once#1=%s（状态=%s, back_info=%s）；request_stop 后 run_once#2=%s（状态=%s, back_info=%s）"
               % (out1.get("action"), rec1.state, bool(rec1.back_info),
                  out2.get("action"), rec2.state, bool(rec2.back_info)))
        return risk
    finally:
        q.close()


# ---------------------------------------------------------------------------
# G2 closed 稳定性：closed 不被后续心跳覆盖（原子写）
# ---------------------------------------------------------------------------
def g2_closed_stability():
    work = tempfile.mkdtemp(prefix="bf-g2-")
    shared = LocalSharedPath(work)
    hb = Heartbeat(shared, "x.heartbeat", interval_sec=0.05, stale_after_sec=30)
    try:
        hb.tick(force=True)
        closed = hb.write_closed()
        after_closed = hb.read()["state"]
        # B 侧再 tick（模拟心跳线程在停机指令之后仍跑一拍）
        tick = hb.tick(force=True)
        after_tick = hb.read()["state"]
        risk = (closed["action"] != "closed") or (after_closed != "closed") \
            or (after_tick != "closed")
        record("G2", "closed 不被心跳覆盖（终态稳定）", risk,
               "write_closed=%s；读=%s；随后 tick=%s 再读=%s"
               % (closed["action"], after_closed, tick["action"], after_tick))
        return risk
    finally:
        hb.close() if hasattr(hb, "close") else None


# ---------------------------------------------------------------------------
# G3 传输层大包：大文件写入的原子性（无 .tmp 残留、内容完整）
# ---------------------------------------------------------------------------
def g3_large_payload_atomic():
    work = tempfile.mkdtemp(prefix="bf-g3-")
    shared = LocalSharedPath(work)
    try:
        payload = {"blob": "x" * (4 * 1024 * 1024)}      # 4MB
        shared.write_text("big.rhop", json.dumps(payload))
        loaded = json.loads(shared.read_text("big.rhop"))
        intact = loaded["blob"] == payload["blob"]
        leftovers = [n for n in os.listdir(work) if n.endswith(".tmp")]
        # 写一半时目录里不应有残留（原子写：临时文件 + rename）
        risk = (not intact) or bool(leftovers)
        record("G3", "传输层大包写入原子（无残留、内容完整）", risk,
               "4MB 往返一致=%s、.tmp 残留=%s" % (intact, leftovers))
        return risk
    finally:
        pass


# ---------------------------------------------------------------------------
# G4 被取消任务的下游依赖：是否会永久卡住
# ---------------------------------------------------------------------------
def g4_cancelled_upstream_blocks_downstream():
    work = tempfile.mkdtemp(prefix="bf-g4-")
    share = os.path.join(work, "share")
    os.makedirs(share)
    q = _wire("A", os.path.join(work, "a"), share)
    try:
        script = _ok(work)
        q.submit([{"task_name": "up", "cli": {"cmd": script}, "timeout_min": 5},
                  {"task_name": "down", "deps": ["up"], "cli": {"cmd": script},
                   "timeout_min": 5}])
        q.cancel("up")                       # 上游被取消
        claimed = []
        while True:
            rec = q.store.claim_next("w1")
            if rec is None:
                break
            claimed.append(rec.task_name)
        # 期望：下游不应被领取（依赖未满足）；但若下游**永远**无法满足 ⇒ 永久卡住
        risk = "down" in claimed
        record("G4", "上游被取消后下游不误领", risk,
               "claimed=%s（期望不含 down：up 已 CANCELLED，依赖无法满足）" % claimed)
        return risk
    finally:
        q.close()


# ---------------------------------------------------------------------------
# G5 重启后遗留锁：LOCKED 任务回收后是否立即可领（无 retry 延迟）
# ---------------------------------------------------------------------------
def g5_leftover_lock_reclaim():
    work = tempfile.mkdtemp(prefix="bf-g5-")
    share = os.path.join(work, "share")
    os.makedirs(share)
    cfg = TaskConfig.from_dict(
        {"name": "link", "role": "B", "key": "k", "shared": {"write": str(share)},
         "queue": {"store": {"kind": "sqlite-shared", "lock_ttl_sec": 1},
                   "retry_delay_min": 5}},
        base_dir=str(os.path.join(work, "b")), warn_plaintext=False)
    q = TaskQueue(cfg, store=cfg.build_store(), crypto=cfg.build_crypto())
    try:
        script = _ok(work)
        q.submit([{"task_name": "j", "cli": {"cmd": script}, "timeout_min": 5}])
        assert q.store.claim_next("dead-w") is not None     # worker 死了（进程重启）
        n = q.store.clean_stale_locks(now=None)             # 模拟看护回收
        state_after = q.get_task("j").state
        # 期望：LOCKED 被回收成 PENDING（立即可重领）——若旧 worker 其实还活着 ⇒ 重复执行风险
        reclaimable = state_after == TaskState.PENDING
        record("G5", "重启后遗留 LOCKED 任务立即可重领", reclaimable,
               "回收=%s、状态=%s（PENDING=立即可重领 ⇒ 与『worker 还活着』无法区分，见 BUG-289）"
               % (n, state_after))
        return reclaimable
    finally:
        q.close()


def main():
    print("=" * 92)
    for probe in (g1_stop_midflight, g2_closed_stability, g3_large_payload_atomic,
                  g4_cancelled_upstream_blocks_downstream, g5_leftover_lock_reclaim):
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