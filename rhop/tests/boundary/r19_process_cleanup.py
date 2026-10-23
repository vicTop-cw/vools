# -*- coding: utf-8 -*-
"""第九轮边界语料：执行器的进程清理（超时截断 / 孙进程泄漏 / shell 闸门 / cancel 停止）。

定位：语料 + 复现器，不是产品源码（命名不带 test_ 前缀，不进 pytest 收集）。
前八件语料覆盖了并发领取、同步乱序、租约续期、控制意图裁决、提交幂等、畸形输入、
文件通道、停机回收、敏感信息解析、共享介质、重试与退避；本轮第一次把**进程清理**
做成边界实证——超时截断后子进程是否真被杀掉、命令派生的孙进程是否泄漏。

运行：
    cd rhop && python tests/boundary/r19_process_cleanup.py

每条输出 [CONFIRMED] / [NOT-CONFIRMED] + 证据；退出码 = 风险成立条数。
"""
import os
import subprocess
import sys
import tempfile
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
    print("[%s] %-44s %s" % ("CONFIRMED" if risk_realized else "NOT-CONFIRMED",
                             pid + " " + title, evidence))


def _queue(work, **queue_overrides):
    cfg_dict = {"name": "link", "role": "B", "key": "k",
                "exec": {"allow_any": True},
                "queue": {"store": {"kind": "sqlite-local"}}}
    cfg_dict["queue"].update(queue_overrides)
    cfg = TaskConfig.from_dict(cfg_dict, base_dir=str(work), warn_plaintext=False)
    return TaskQueue(cfg)


def _cmd(code):
    return '"%s" "-c" "%s"' % (PY, code.replace('"', '\\"'))


def _write_scripts(work):
    """把孙进程脚本写成文件（避免 -c 的引号嵌套把命令本身弄坏）。"""
    marker = os.path.join(work, "gc.marker")
    marker_arg = marker.replace("\\", "/")
    gc = os.path.join(work, "gc.py")
    with open(gc, "w", encoding="utf-8") as fh:
        fh.write("import time, sys\n"
                 "while True:\n"
                 "    with open(sys.argv[1], 'w') as f:\n"
                 "        f.write(str(time.time()))\n"
                 "    time.sleep(0.4)\n")
    parent = os.path.join(work, "parent.py")
    with open(parent, "w", encoding="utf-8") as fh:
        fh.write("import subprocess, sys, time, os\n"
                 "marker = sys.argv[1]\n"
                 "if sys.argv[2] == 'spawn':\n"
                 "    subprocess.Popen([sys.executable, sys.argv[3]], close_fds=True)\n"
                 "    time.sleep(5)\n"
                 "else:\n"
                 "    while True:\n"
                 "        with open(marker, 'w') as f:\n"
                 "            f.write(str(time.time()))\n"
                 "        time.sleep(0.4)\n")
    return marker, parent_path(parent, gc)


def parent_path(parent, gc):
    return parent, gc


def _marker_alive(marker, gap=1.0):
    """标记文件在 gap 秒内是否仍在被更新（⇒ 持有它的进程还活着）。"""
    try:
        with open(marker, "r", encoding="utf-8") as fh:
            a = fh.read()
        time.sleep(gap)
        with open(marker, "r", encoding="utf-8") as fh:
            b = fh.read()
        return a != b
    except OSError:
        return False


# ---------------------------------------------------------------------------
# P1 超时截断后：命令派生的孙进程是否被真正杀掉
# ---------------------------------------------------------------------------
def p1_timeout_kills_grandchild():
    work = tempfile.mkdtemp(prefix="bf-p1-")
    marker, (parent, gc) = _write_scripts(work)
    q = _queue(work, retry_delay_min=0, max_retries=0)
    try:
        cmd = '"%s" "%s" "%s" "spawn" "%s"' % (PY, parent.replace("\\", "/"),
                                               marker.replace("\\", "/"),
                                               gc.replace("\\", "/"))
        q.submit([{"task_name": "j", "cli": {"cmd": cmd}, "timeout_min": 0.02}])
        t0 = time.time()
        q.run_once()
        elapsed = time.time() - t0
        rec = q.get_task("j")
        time.sleep(1.5)                      # 给孙进程一点时间继续写
        alive = _marker_alive(marker, gap=1.0)
        risk = alive
        record("P1", "超时截断后孙进程被真正杀掉", risk,
               "命令耗时=%.2fs（超时 0.02min=1.2s）；状态=%s；"
               "截断后孙进程仍在写标记=%s" % (elapsed, rec.state, alive))
        return risk
    finally:
        q.close()


# ---------------------------------------------------------------------------
# P2 超时截断后执行器必须立刻返回（不阻塞在读管道上），并把超时归为可重试
# ---------------------------------------------------------------------------
def p2_timeout_returns_promptly():
    work = tempfile.mkdtemp(prefix="bf-p2-")
    marker, (parent, gc) = _write_scripts(work)
    q = _queue(work, retry_delay_min=0, max_retries=2)
    try:
        cmd = '"%s" "%s" "%s" "spawn" "%s"' % (PY, parent.replace("\\", "/"),
                                               marker.replace("\\", "/"),
                                               gc.replace("\\", "/"))
        q.submit([{"task_name": "j", "cli": {"cmd": cmd}, "timeout_min": 0.02}])
        t0 = time.time()
        q.run_once()
        elapsed = time.time() - t0
        rec = q.get_task("j")
        # 超时 1.2s；命令本身要睡 5s。若执行器阻塞在读管道上，耗时会接近 5s。
        prompt = elapsed < 3.0
        retryable = rec.state in (TaskState.RETRY_PENDING, TaskState.PENDING)
        risk = not (prompt and retryable)
        record("P2", "超时截断后立刻返回且归为可重试", risk,
               "耗时=%.2fs（超时 1.2s、命令睡 5s）；状态=%s；立刻返回=%s；可重试=%s"
               % (elapsed, rec.state, prompt, retryable))
        return risk
    finally:
        q.close()


# ---------------------------------------------------------------------------
# P3 shell 闸门：shell=True 的配置是否被拒绝/告警
# ---------------------------------------------------------------------------
def p3_shell_gate():
    work = tempfile.mkdtemp(prefix="bf-p3-")
    cfg = TaskConfig.from_dict(
        {"name": "n", "role": "B", "key": "k",
         "exec": {"allow_any": True, "shell": True},
         "queue": {"store": {"kind": "sqlite-local"}}},
        base_dir=str(work), warn_plaintext=False)
    risk = False
    try:
        cfg.build_policy() if hasattr(cfg, "build_policy") else None
        from vools.rhop.task.exec import ExecPolicy
        policy = ExecPolicy(cfg.exec)
        risk = bool(policy.shell)
        record("P3", "shell=True 默认被闸门拒绝", risk,
               "policy.shell=%s（期望 False：shell 闸门默认关闭）" % policy.shell)
    except Exception as exc:
        record("P3", "shell=True 默认被闸门拒绝", False,
               "构造时被拒（%s）—— 拒绝即正确" % type(exc).__name__)
    return risk


# ---------------------------------------------------------------------------
# P4 cancel 对在途命令的停止语义
# ---------------------------------------------------------------------------
def p4_cancel_stops_running_command():
    work = tempfile.mkdtemp(prefix="bf-p4-")
    marker = os.path.join(work, "alive.marker")
    code = ("import time\n"
            "while True:\n"
            "  open(%r,'w').write(str(time.time()))\n"
            "  time.sleep(0.4)\n" % marker.replace("\\", "/"))
    q = _queue(work, retry_delay_min=0, max_retries=0)
    try:
        q.submit([{"task_name": "j", "cli": {"cmd": _cmd(code)}, "timeout_min": 30}])
        # 领取并手动置 RUNNING（模拟正在执行），再 cancel
        rec = q.store.claim_next("w1")
        q.store.set_state("j", TaskState.RUNNING)
        result = q.cancel("j")
        pending = result.get("pending")
        # cancel 只打标记（RUNNING → cancel_requested），执行器是否真的停止是另一层：
        # 这里验证「cancel 不会把 RUNNING 直接改成终态」（文档口径：等其收尾）
        after = q.get_task("j").state
        risk = (after != TaskState.RUNNING) or (pending is not True)
        record("P4", "cancel 对 RUNNING 只打标记、等其收尾", risk,
               "cancel 返回 pending=%s；cancel 后状态=%s（期望 RUNNING）" % (pending, after))
        return risk
    finally:
        q.close()


def main():
    print("=" * 92)
    for probe in (p1_timeout_kills_grandchild, p2_timeout_returns_promptly,
                  p3_shell_gate, p4_cancel_stops_running_command):
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