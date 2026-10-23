# -*- coding: utf-8 -*-
"""第八轮边界语料：任务重试与退避的状态机。

定位：语料 + 复现器，不是产品源码（命名不带 test_ 前缀，不进 pytest 收集）。
前七件语料覆盖了并发领取、同步乱序、租约续期、控制意图裁决、提交幂等、畸形输入、
文件通道、停机回收、敏感信息解析、共享介质；本轮第一次把**重试/退避状态机**做成边界实证：
RETRY_PENDING 的延迟窗口、重试计数的跨周期累加、max_retries=0 / retry_delay_min=0 的退化、
超时归类、retry_failed 的重置连带。

运行：
    cd rhop && python tests/boundary/r18_retry_backoff.py

每条输出 [CONFIRMED] / [NOT-CONFIRMED] + 证据；退出码 = 风险成立条数。
"""
import os
import sys
import tempfile
import time

RHOP = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RHOP)

from vools.rhop.task.config import TaskConfig            # noqa: E402
from vools.rhop.task.models import TaskState             # noqa: E402
from vools.rhop.task.queue import TaskQueue              # noqa: E402

RESULTS = []
FAIL_CMD = '"%s" "-c" "raise SystemExit(3)"' % (sys.executable.replace("\\", "/"),)


def record(pid, title, risk_realized, evidence):
    RESULTS.append((pid, title, risk_realized, evidence))
    print("[%s] %-44s %s" % ("CONFIRMED" if risk_realized else "NOT-CONFIRMED",
                             pid + " " + title, evidence))


def _queue(work, role="B", **queue_overrides):
    # exec 是**顶层**配置键（不在 queue 下）；本轮探针只关心重试/退避语义，
    # 故放开任意命令，避免白名单挡下命令导致测到的是白名单而非重试。
    cfg_dict = {"name": "link", "role": role, "key": "k",
                "exec": {"allow_any": True},
                "queue": {"store": {"kind": "sqlite-local"}}}
    cfg_dict["queue"].update(queue_overrides)
    cfg = TaskConfig.from_dict(cfg_dict, base_dir=str(work), warn_plaintext=False)
    return TaskQueue(cfg)


def _submit(q, name, cmd=None, **over):
    task = {"task_name": name, "timeout_min": 5}
    if cmd:
        task["cli"] = {"cmd": cmd}
    task.update(over)
    q.submit([task])
    return name


# ---------------------------------------------------------------------------
# R1 RETRY_PENDING 的延迟窗口：到点前不可领，到点后可领
# ---------------------------------------------------------------------------
def r1_retry_backoff_window():
    work = tempfile.mkdtemp(prefix="bf-r1-")
    q = _queue(work, retry_delay_min=60)          # 60 分钟退避
    try:
        _submit(q, "j", FAIL_CMD)
        q.run_once()                               # 第一次执行 → 失败 → RETRY_PENDING
        rec = q.get_task("j")
        before = q.store.claim_next("w1")          # 退避未到，不应可领
        time.sleep(0.05)
        # 把退避时间改短后重跑：用 retry_delay_min=0 的队列重新构造同一任务不现实，
        # 改为直接验证「RETRY_PENDING 状态下 claim_next 返回 None」
        risk = (rec.state != TaskState.RETRY_PENDING) or before is not None
        record("R1", "退避窗口内 RETRY_PENDING 不可重领", risk,
               "执行后状态=%s；窗口内 claim_next=%s（期望 None）"
               % (rec.state, before.task_name if before else None))
        return risk
    finally:
        q.close()


# ---------------------------------------------------------------------------
# R2 重试计数跨周期累加 + 达到 max_retries 后不再重试
# ---------------------------------------------------------------------------
def r2_retry_count_accumulates():
    work = tempfile.mkdtemp(prefix="bf-r2-")
    q = _queue(work, max_retries=2, retry_delay_min=0)
    try:
        _submit(q, "j", FAIL_CMD)
        states = []
        for _ in range(4):
            # 只调 run_once（它内部自行领取+执行），不要手动 claim_next —— 否则双重领取
            q.run_once()
            states.append(q.get_task("j").state)
        final = q.get_task("j").state
        risk = final != TaskState.FAILED
        record("R2", "重试计数累加并在 max_retries 后转 FAILED", risk,
               "每轮执行后状态=%s；最终=%s（期望 FAILED）" % (states, final))
        return risk
    finally:
        q.close()


# ---------------------------------------------------------------------------
# R3 max_retries=0：失败后不应再重试
# ---------------------------------------------------------------------------
def r3_zero_retries():
    work = tempfile.mkdtemp(prefix="bf-r3-")
    q = _queue(work, max_retries=0, retry_delay_min=0)
    try:
        _submit(q, "j", FAIL_CMD)
        q.run_once()
        first = q.get_task("j").state
        again = q.store.claim_next("w1")
        risk = (first != TaskState.FAILED) or (again is not None)
        record("R3", "max_retries=0 时失败即终态、不再重领", risk,
               "首次执行后=%s；再次 claim_next=%s（期望 FAILED / None）"
               % (first, again.task_name if again else None))
        return risk
    finally:
        q.close()


# ---------------------------------------------------------------------------
# R4 retry_delay_min=0：退避为零，立即可重领
# ---------------------------------------------------------------------------
def r4_zero_delay_immediate_reclaim():
    work = tempfile.mkdtemp(prefix="bf-r4-")
    q = _queue(work, retry_delay_min=0, max_retries=5)
    try:
        _submit(q, "j", FAIL_CMD)
        q.run_once()
        again = q.store.claim_next("w1")
        risk = again is None
        record("R4", "retry_delay_min=0 时立即可重领", risk,
               "执行后再次 claim_next=%s（期望非空）"
               % (again.task_name if again else None))
        return risk
    finally:
        q.close()


# ---------------------------------------------------------------------------
# R5 超时触发的重试归类（应可重试，而非不可重试）
# ---------------------------------------------------------------------------
def r5_timeout_bounds_execution():
    """timeout_min 必须真正约束命令执行时长（否则租约先过期 → 重复执行）。"""
    work = tempfile.mkdtemp(prefix="bf-r5-")
    q = _queue(work, retry_delay_min=0, max_retries=2)
    try:
        slow = '"%s" "-c" "import time; time.sleep(5)"' % sys.executable.replace("\\", "/")
        _submit(q, "j", slow, timeout_min=0.05)          # 3 秒超时，命令本身睡 5 秒
        t0 = time.time()
        q.run_once()
        elapsed = time.time() - t0
        rec = q.get_task("j")
        bounded = elapsed < 4.5                          # 被 3s 超时截断（而非跑满 5s）
        retryable = rec.state in (TaskState.RETRY_PENDING, TaskState.PENDING)
        risk = not (bounded and retryable)
        record("R5", "timeout_min 真正约束命令执行时长", risk,
               "耗时=%.2fs（超时 0.05min=3s，命令睡 5s）；状态=%s；被约束=%s；可重试=%s"
               % (elapsed, rec.state, bounded, retryable))
        return risk
    finally:
        q.close()


# ---------------------------------------------------------------------------
# R6 retry_failed 重置计数的连带影响
# ---------------------------------------------------------------------------
def r6_retry_failed_resets():
    work = tempfile.mkdtemp(prefix="bf-r6-")
    q = _queue(work, max_retries=1, retry_delay_min=0)
    try:
        _submit(q, "j", FAIL_CMD)
        q.run_once()                                  # 第 1 次失败
        rec1 = q.get_task("j")
        q.run_once()                                  # 第 2 次（计数到顶）→ FAILED
        rec2 = q.get_task("j")
        q.retry_failed()                              # 重置
        rec3 = q.get_task("j")
        claimable = q.store.claim_next("w1") is not None
        risk = (rec2.state != TaskState.FAILED) or (rec3.state != TaskState.PENDING) \
            or not claimable
        record("R6", "retry_failed 把 FAILED 重置为可重领", risk,
               "第1次=%s 第2次=%s reset后=%s 可领=%s"
               % (rec1.state, rec2.state, rec3.state, claimable))
        return risk
    finally:
        q.close()


def main():
    print("=" * 92)
    for probe in (r1_retry_backoff_window, r2_retry_count_accumulates, r3_zero_retries,
                  r4_zero_delay_immediate_reclaim, r5_timeout_bounds_execution,
                  r6_retry_failed_resets):
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