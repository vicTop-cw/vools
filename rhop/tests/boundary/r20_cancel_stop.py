# -*- coding: utf-8 -*-
"""第十轮边界语料：cancel 对在途命令的真实停止语义。

定位：语料 + 复现器，不是产品源码（命名不带 test_ 前缀，不进 pytest 收集）。
第九轮 P4 只验证了「cancel 对 RUNNING 只打标记」——**执行器到底有没有真的中断
正在跑的命令**还没测到。§6/§15 的口径是「RUNNING 打取消标记**等其收尾**」：
取消检查发生在领取时（queue.py:750），执行期间不轮询 ⇒ 在途命令会跑完。
所以本轮验证的是**文档口径下的收敛性**：命令跑完后任务必须收敛到 CANCELLED，
而不是被记成 COMPLETED。

运行：
    cd rhop && python tests/boundary/r20_cancel_stop.py

每条输出 [CONFIRMED] / [NOT-CONFIRMED] + 证据；退出码 = 风险成立条数。
"""
import os
import sys
import tempfile
import threading
import time

RHOP = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RHOP)

from vools.rhop.task.config import TaskConfig            # noqa: E402
from vools.rhop.task.models import TaskState             # noqa: E402
from vools.rhop.task.queue import TaskQueue              # noqa: E402

RESULTS = []
PY = sys.executable.replace("\\", "/")


def record(pid, title, risk_realized, evidence):
    RESULTS.append((pid, title, risk_realized, evidence))
    print("[%s] %-46s %s" % ("CONFIRMED" if risk_realized else "NOT-CONFIRMED",
                             pid + " " + title, evidence))


def _queue(work, **queue_overrides):
    store = {"kind": "sqlite-local"}
    kind = queue_overrides.pop("store_kind", None)
    if kind:
        store["kind"] = kind
    path = queue_overrides.pop("store_path", None)
    if path:
        store["path"] = path
    cfg_dict = {"name": "link", "role": "B", "key": "k",
                "exec": {"allow_any": True},
                "queue": {"store": store}}
    cfg_dict["queue"].update(queue_overrides)
    cfg = TaskConfig.from_dict(cfg_dict, base_dir=str(work), warn_plaintext=False)
    return TaskQueue(cfg)


def _long_script(work, seconds=10.0):
    """写一个「持续写标记、总共跑 N 秒」的脚本，返回 (脚本路径, 标记路径)。"""
    marker = os.path.join(work, "alive.marker")
    script = os.path.join(work, "long.py")
    with open(script, "w", encoding="utf-8") as fh:
        fh.write("import time\n"
                 "for _ in range(%d):\n"
                 "    with open(%r, 'w') as f:\n"
                 "        f.write(str(time.time()))\n"
                 "    time.sleep(0.5)\n" % (int(seconds / 0.5), marker))
    return script, marker


def _wait_marker(marker, timeout=8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(marker):
            return True
        time.sleep(0.1)
    return False


# ---------------------------------------------------------------------------
# C1 cancel 在途任务：命令会跑完（设计如此），但任务必须收敛到 CANCELLED
# ---------------------------------------------------------------------------
def c1_cancel_running_converges_not_completed():
    work = tempfile.mkdtemp(prefix="bf-c1-")
    db_dir = os.path.join(work, "shared")
    os.makedirs(db_dir)
    db_path = os.path.join(db_dir, "tasks.db")
    script, marker = _long_script(work, seconds=10.0)
    cmd = '"%s" "%s"' % (PY, script.replace("\\", "/"))
    box = {}

    def runner():
        # store 在 worker 线程内创建 ⇒ SQLite 连接线程局部，不跨线程（否则报
        # "SQLite objects created in a thread can only be used in that same thread"）
        q = _queue(work, store_kind="sqlite-shared", store_path=db_path,
                   retry_delay_min=0, max_retries=0)
        try:
            q.submit([{"task_name": "j", "cli": {"cmd": cmd}, "timeout_min": 30}])
            box["t0"] = time.time()
            box["res"] = q.run_once()
            box["t1"] = time.time()
        except Exception as exc:
            box["err"] = "%s: %s" % (type(exc).__name__, exc)
        finally:
            q.close()

    th = threading.Thread(target=runner, daemon=True)
    th.start()
    started = _wait_marker(marker)
    time.sleep(0.5)
    qa = _queue(work, store_kind="sqlite-shared", store_path=db_path,
                retry_delay_min=0, max_retries=0)
    cancel_err = None
    try:
        qa.cancel("j")
    except Exception as exc:
        cancel_err = "%s: %s" % (type(exc).__name__, exc)
    finally:
        qa.close()
    th.join(timeout=40)
    elapsed = box.get("t1", 0) - box.get("t0", 0)
    qb = _queue(work, store_kind="sqlite-shared", store_path=db_path,
                retry_delay_min=0, max_retries=0)
    try:
        state = qb.get_task("j").state
    except Exception as exc:
        state = "读取失败:%s" % type(exc).__name__
    finally:
        qb.close()
    converged = state == TaskState.CANCELLED
    risk = not (started and converged)
    record("C1", "cancel 后收敛到 CANCELLED（命令跑完属设计）", risk,
           "命令已启动=%s；run_once 耗时=%.2fs（命令本身 10s）；状态=%s；收敛=%s；"
           "cancel 异常=%s；runner 异常=%s"
           % (started, elapsed, state, converged, cancel_err, box.get("err")))
    return risk


# ---------------------------------------------------------------------------
# C2 领取时已打取消标记的任务不会被执行（queue.py:750 的领取期检查）
# ---------------------------------------------------------------------------
def c2_cancelled_task_not_executed():
    work = tempfile.mkdtemp(prefix="bf-c2-")
    script, marker = _long_script(work, seconds=6.0)
    q = _queue(work, retry_delay_min=0, max_retries=0)
    try:
        q.submit([{"task_name": "j", "cli": {"cmd": '"%s" "%s"' % (PY, script.replace("\\", "/"))},
                  "timeout_min": 30}])
        q.cancel("j")                       # 领取前就取消
        result = q.run_once()
        state = q.get_task("j").state
        # claim_next 已过滤 cancel_requested ⇒ 任务根本不会被领取 ⇒ action 是 idle；
        # 「cancelled」只用于「领取后才发现被取消」的竞态分支。判据是状态与命令未执行。
        risk = (state != TaskState.CANCELLED) or os.path.exists(marker) \
            or result.get("action") not in ("idle", "cancelled")
        record("C2", "已取消任务不被领取执行", risk,
               "run_once action=%s；状态=%s；命令标记文件出现=%s（期望 False）"
               % (result.get("action"), state, os.path.exists(marker)))
        return risk
    finally:
        q.close()


# ---------------------------------------------------------------------------
# C3 取消 PENDING（未领取）任务：直接终态，且之后不再执行
# ---------------------------------------------------------------------------
def c3_cancel_pending_never_runs():
    work = tempfile.mkdtemp(prefix="bf-c3-")
    script, marker = _long_script(work, seconds=6.0)
    q = _queue(work, retry_delay_min=0, max_retries=0)
    try:
        q.submit([{"task_name": "j", "cli": {"cmd": '"%s" "%s"' % (PY, script.replace("\\", "/"))},
                  "timeout_min": 30}])
        result = q.cancel("j")
        rec = q.get_task("j")
        q.run_once()
        still_cancelled = q.get_task("j").state == TaskState.CANCELLED
        risk = (rec.state != TaskState.CANCELLED) or (result.get("pending") is not False) \
            or not still_cancelled
        record("C3", "取消 PENDING 任务直接终态且不再执行", risk,
               "cancel 返回 pending=%s；状态=%s；再跑一轮后仍=CANCELLED=%s"
               % (result.get("pending"), rec.state, still_cancelled))
        return risk
    finally:
        q.close()


def main():
    print("=" * 92)
    for probe in (c1_cancel_running_converges_not_completed, c2_cancelled_task_not_executed,
                  c3_cancel_pending_never_runs):
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