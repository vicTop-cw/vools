"""DAG 依赖状态机（纯计算，三后端共享）。

统一词汇（success 兼容 look_upon 的 COMPLETED）：
    PENDING（有依赖未满足） → READY（依赖全成功，可领） → RUNNING
        → SUCCESS / FAILED；失败可临时落 RETRY_PENDING。
    上游终态 FAILED → 下游（传递）未启动任务级联 SKIPPED。

后端只需提供两个查询回调：
    deps_of(tid)     -> list[int]   # tid 依赖了哪些任务（正向）
    children_of(dep) -> list[int]   # 哪些任务依赖 dep（反向）
    status_of(tid)   -> str         # 当前状态字符串
"""

__all__ = [
    "SUCCESS_STATES",
    "TERMINAL_STATES",
    "initial_status",
    "ready_after_success",
    "skip_after_failure",
]

# look_upon 用 COMPLETED，vools 核心枚举用 SUCCESS；读取时二者等价
SUCCESS_STATES = ("SUCCESS", "COMPLETED")
TERMINAL_STATES = ("SUCCESS", "COMPLETED", "FAILED", "SKIPPED", "CANCEL", "CANCELLED")


def _is_success(status):
    return status in SUCCESS_STATES


def initial_status(dependencies, status_of):
    """提交时：无依赖或依赖全部成功 → READY，否则 PENDING。"""
    deps = list(dependencies or [])
    if not deps:
        return "READY"
    if all(_is_success(status_of(d)) for d in deps):
        return "READY"
    return "PENDING"


def ready_after_success(completed_id, deps_of, children_of, status_of):
    """某任务成功后，返回可由 PENDING 翻 READY 的下游任务 id 列表。

    条件：当前仍 PENDING，且其【全部】依赖都已成功（传递闭包一层推进即可，
    因为每次成功都会调用本函数，链式会自然逐级点亮）。
    """
    out = []
    for child in children_of(completed_id):
        if status_of(child) != "PENDING":
            continue
        if all(_is_success(status_of(d)) for d in deps_of(child)):
            out.append(child)
    return out


def skip_after_failure(failed_id, children_of, status_of):
    """上游终态失败后，BFS 求应级联 SKIPPED 的下游任务 id 集合。

    只跳过尚未真正开始执行的任务（PENDING/READY/RETRY_PENDING）。
    RUNNING 任务不打断（让其自然结束）；已终态的不重复改。
    """
    skippable = {"PENDING", "READY", "RETRY_PENDING"}
    skipped = set()
    stack = [failed_id]
    while stack:
        cur = stack.pop()
        for child in children_of(cur):
            if child in skipped:
                continue
            if status_of(child) in skippable:
                skipped.add(child)
                stack.append(child)
            # RUNNING / 终态：不向下强制（RUNNING 完成后其自己的下游再判定）
    return skipped
