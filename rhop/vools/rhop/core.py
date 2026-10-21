"""vools.rhop.core - 双方对等镜像任务中继协议基础模型

Side: 需求端 / 任务端（只有两方）
TaskStatus: 任务状态机（PENDING → CLAIMED → RUNNING → DONE / FAILED / CANCELLED）

开放问题 Q3 默认决策：PENDING 可取消；daemon 推送后对端可能已领走，取消尽力而为。
"""

from enum import Enum


class Side(Enum):
    """双方对等：只有两方，无控制端。"""
    REQUESTER = "requester"   # 需求端：提交任务，等结果
    EXECUTOR = "executor"     # 任务端：领任务，执行，回结果

    @property
    def other(self):
        """对端。"""
        return Side.EXECUTOR if self == Side.REQUESTER else Side.REQUESTER


class TaskStatus(Enum):
    """任务状态机。

    状态流转：
        PENDING ──► CLAIMED ──► RUNNING ──► DONE
           │            │            │
           │            │            └──► FAILED
           │            │
           └────────────┴──► CANCELLED (仅 PENDING 可取消)
    """
    PENDING = "pending"       # 需求端已提交，任务端未领
    CLAIMED = "claimed"       # 任务端已领，准备执行
    RUNNING = "running"       # 任务端正在执行
    DONE = "done"             # 任务端执行完成，结果已写回
    FAILED = "failed"         # 任务端执行失败
    CANCELLED = "cancelled"   # 需求端取消

    # ---- 合法流转（函数式查表，避免 Enum 类属性被 metaclass 吃掉） ----

    def can_transition(self, new_status: "TaskStatus") -> bool:
        """判断当前状态是否可以流转到 new_status。"""
        return new_status in _TRANSITIONS.get(self, set())

    @property
    def is_terminal(self) -> bool:
        """是否终态。"""
        return not _TRANSITIONS.get(self, set())


# 模块级流转表（放在类外，避免 Enum metaclass 把类体里的 mutable dict 当成员吃掉）
_TRANSITIONS = {
    TaskStatus.PENDING:   {TaskStatus.CLAIMED, TaskStatus.CANCELLED},
    TaskStatus.CLAIMED:   {TaskStatus.RUNNING, TaskStatus.CANCELLED},
    TaskStatus.RUNNING:   {TaskStatus.DONE, TaskStatus.FAILED},
    TaskStatus.DONE:      set(),
    TaskStatus.FAILED:    set(),
    TaskStatus.CANCELLED: set(),
}
