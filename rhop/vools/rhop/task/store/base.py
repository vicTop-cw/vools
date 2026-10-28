"""vools.rhop.task.store.base - 任务存储抽象（可换后端）

**这是「数据库抽象」的契约面**：队列层（TaskQueue/TaskSync）只依赖本抽象，
不直接碰 SQL。因此三种拓扑都能插进来：

1. ``sqlite-shared`` —— 单一共享 SQLite 文件，A/B 打开同一文件同时读写
   （双方直接看到同一份任务状态，无需同步）；
2. ``sqlite-local``  —— 双方各自持一个本地 SQLite，靠 TaskSync（加密 JSON 包）
   收敛成"同样的库"（介质无法承载并发读写时用这种）；
3. 未来 ``postgres``  —— 网络数据库后端，注册一个工厂即可，接口不变
   （见 ``store/__init__.py`` 的 ``register_store`` 与文档示例）。

实现约定（backend 必须遵守）：
- ``task_name`` 是唯一身份，``insert_tasks`` 必须**幂等**（重复提交不产生新行）；
- ``deps`` 里存的是 task_name（不是自增 id），依赖门控由 ``claim_next`` 保证；
- ``claim_next`` 必须是**原子**的：并发 worker 不会领到同一条任务；
- 所有时间字段都是 UTC ISO 文本（``models.utcnow_iso`` 格式），便于跨库比较。
"""

from __future__ import absolute_import

import abc
from typing import Any, Dict, List, Optional

from ..errors import TaskNotFound, StoreUnavailable
from ..models import TaskRecord, TaskState, iso_add_seconds, utcnow_iso


#: 租约过期回收时写入 ``last_err`` 的说明（「为什么又重试了」的运维线索）。
#: 放在契约面而不是各后端里：sqlite / pg 共用同一句话，避免两份文案漂移。
LEASE_RECLAIM_LAST_ERR = "租约过期回收（worker 失联 / 进程崩溃未正常收尾）"


class TaskStore(abc.ABC):
    """任务存储抽象基类（**真 ABC**：契约受强制）。

    实现约定（backend 必须全部实现，否则无法实例化）：下方标了
    ``@abc.abstractmethod`` 的方法即为契约面。继承 ``abc.ABC`` 而非 ``object``
    是刻意的——只有设了 ``ABCMeta``，``__abstractmethods__`` 才会被计算，
    缺失实现的子类在**构造期**就抛 TypeError，而不是拖到运行期某个调用点才炸
    （历史缺陷 BUG-279：旧写法 class TaskStore(object) 让 @abstractmethod 完全惰性，
    裸 TaskStore() 与零实现子类都能实例化，create_store 的 isinstance 校验也就形同虚设）。

    Args:
        spec: 存储规格 dict（``kind`` / ``path`` / ``table`` / ``journal_mode`` ...
              由 ``store/__init__.py`` 的工厂补默认值后透传）
        ctx:  解析上下文（``name`` / ``role`` / ``base_dir`` / ``shared_root`` / ``shared``），
              供后端解析相对路径与介质形态。
    """

    #: 后端标识（子类覆盖，如 "sqlite"）
    kind = "abstract"

    def __init__(self, spec: Optional[dict] = None, ctx: Optional[dict] = None):
        self.spec = dict(spec or {})
        self.ctx = dict(ctx or {})

    def touch_lock(self, task_name: str, worker_id: Optional[str] = None,
                   now: Optional[str] = None) -> bool:
        """刷新任务租约（BUG-289 收口）。

        租约 = ``lock_time`` + ``expire_time``：只要任务已被领取（LOCKED）或正在执行（RUNNING）
        且持有者匹配，就把两者推到现在，这样 ``clean_stale_locks`` 就不会把**还在跑**的任务
        判死回收（判死回收会让另一个 worker 重新领取并重复执行 ⇒ 重复副作用）。

        默认实现走契约内的 ``update_fields``，因此**所有后端自动获得续期能力**，
        不需要在每个后端里重复写 SQL。SqliteTaskStore 覆盖了本方法（版本无关的 UPDATE，
        因为续期不该改变任务定义、不该推 version）。

        Args:
            task_name: 任务名
            worker_id: 持有者；非空时只有持有者本人能续（防止已被回收的任务被旧 worker 续活）
            now: 刷新时间（缺省当前时间）

        Returns:
            bool: 是否真的刷新了租约
        """
        record = self.get_task(task_name)
        if record is None or record.state not in (TaskState.LOCKED, TaskState.RUNNING):
            return False
        if worker_id and record.worker_id and record.worker_id != worker_id:
            return False
        now_iso = now or utcnow_iso()
        # 与 claim_next 同口径：租约取「全局 lock_ttl」与「该任务自己的 timeout_min」的较大者
        lease = max(float(self.spec.get("lock_ttl_sec") or 900),
                    float(record.timeout_min or 60) * 60.0)
        expire_iso = iso_add_seconds(now_iso, lease)
        return bool(self.update_fields(task_name, now=now_iso, lock_time=now_iso,
                                      expire_time=expire_iso))

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    @abc.abstractmethod
    def init_schema(self) -> None:
        """建表/建索引（幂等）。"""

    @abc.abstractmethod
    def close(self) -> None:
        """释放连接/句柄。"""

    def describe(self) -> Dict[str, Any]:
        """后端自描述（诊断/配置回显用）。"""
        return {"kind": self.kind, "spec": dict(self.spec)}

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    @abc.abstractmethod
    def insert_tasks(self, records: List[TaskRecord]) -> int:
        """批量写入任务定义（幂等：task_name 已存在则跳过）。

        Returns:
            int: 实际新增的行数。
        """

    @abc.abstractmethod
    def set_state(self, task_name: str, state: str, expect_version: Optional[int] = None,
                  force: bool = False, now: Optional[str] = None, **fields) -> bool:
        """更新任务状态与附加字段。

        Args:
            task_name:      任务身份
            state:          目标状态（TaskState 之一）
            expect_version: 乐观锁前置条件：本地 version 大于它则不写（返回 False）
            force:          True 时跳过流转合法性校验（运维重跑 / 同步应用）
            now:            当前时间（缺省 utcnow_iso）
            **fields:       同事务写入的附加列（back_info / last_err / retry_count /
                            start_time / end_time / worker_id / lock_time /
                            cancel_requested / scheduled_at / expire_time 等）

        Returns:
            bool: 是否真的写入。
        """

    @abc.abstractmethod
    def update_fields(self, task_name: str, now: Optional[str] = None, **fields) -> bool:
        """只更新字段、不改状态。"""

    @abc.abstractmethod
    def claim_next(self, worker_id: str, now: Optional[str] = None,
                   lock_ttl_sec: Optional[float] = None) -> Optional[TaskRecord]:
        """原子领取一条可执行任务。

        条件：状态可领取、未被取消、``scheduled_at`` 已到、**所有 deps 均 COMPLETED**；
        按 priority DESC, task_id ASC 取第一条；命中即置 LOCKED 并写 worker_id /
        lock_time / expire_time。

        Returns:
            TaskRecord（已置 LOCKED）或 None（无可用任务）。
        """

    @abc.abstractmethod
    def clean_stale_locks(self, now: Optional[str] = None,
                          lock_timeout_sec: Optional[float] = None) -> int:
        """回收失效锁：LOCKED 超时→PENDING；RUNNING 超时→RETRY_PENDING / FAILED。

        两条路径的**语义不同**（BUG-366 收口，勿合并）：

        * ``LOCKED`` 到期 ⇒ ``PENDING``，**不计重试**。LOCKED 只存在于
          ``claim_next`` → ``set_state(RUNNING)`` 这中间的一瞬（``queue.run_once``
          里两行紧邻），到期说明 worker 在「领到」和「开始执行」之间就没了，
          **用户代码一行都没跑**。把基础设施抖动记到任务账上只会白烧重试预算。
        * ``RUNNING`` 到期 ⇒ ``retry_count + 1``（计入 ``max_retries`` 预算）：
          ``retry_count < max_retries`` 时落 ``RETRY_PENDING``，否则落 ``FAILED``，
          并写 ``last_err``（``LEASE_RECLAIM_LAST_ERR``）说明是租约回收。
          这正是「毒任务无限重跑」的收口点——worker 在 RUNNING 期间被 kill
          （OOM / 段错误 / 死循环直到被回收）时，行内状态就停在 RUNNING，
          不计数就会被无限重领。

        回收**不额外退避**（不动 ``scheduled_at``）：租约到期本身（默认 900s）已是
        天然延迟，回到 ``PENDING`` / ``RETRY_PENDING`` 后即可再次领取
        （``test_task_e2e.test_crash_recovery_reclaims_running_task`` 依赖该语义）。

        Returns:
            int: 被回收的行数。
        """

    @abc.abstractmethod
    def reset_failed(self, now: Optional[str] = None) -> int:
        """把所有 FAILED 重置回 PENDING（运维重跑），返回影响行数。"""

    @abc.abstractmethod
    def requeue(self, task_name: str, now: Optional[str] = None) -> bool:
        """把单个任务强制重置回 PENDING（清锁，版本+1）。"""

    @abc.abstractmethod
    def set_cancel_requested(self, task_name: str, flag: bool = True,
                             now: Optional[str] = None) -> bool:
        """打/撤取消请求标记（RUNNING 任务靠它优雅退出）。"""

    @abc.abstractmethod
    def apply_task(self, record: TaskRecord) -> str:
        """同步用：按版本幂等落一条任务定义。

        Returns:
            str: "inserted" | "updated" | "stale"（本地版本更新，丢弃）
        """

    @abc.abstractmethod
    def apply_state(self, data: Dict[str, Any]) -> str:
        """同步用：按版本幂等落一条状态更新。

        Returns:
            str: "updated" | "stale" | "missing"（本地没有该任务）
        """

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------

    @abc.abstractmethod
    def get_task(self, task_name: str) -> Optional[TaskRecord]:
        """按 task_name 读一条；不存在返回 None。"""

    @abc.abstractmethod
    def list_tasks(self, state: Optional[str] = None, limit: int = 200,
                   order: str = "priority") -> List[TaskRecord]:
        """列出任务（可按状态过滤）。"""

    @abc.abstractmethod
    def all_task_names(self) -> List[str]:
        """全部 task_name（DAG 校验用）。"""

    @abc.abstractmethod
    def count_by_state(self) -> Dict[str, int]:
        """按状态计数。"""

    # ---- 派生便捷方法（子类不必重写） ----

    def active_tasks(self) -> List[TaskRecord]:
        """所有非终态任务（PENDING/LOCKED/RUNNING/RETRY_PENDING）。"""
        out = []
        for state in TaskState.ACTIVE:
            out.extend(self.list_tasks(state=state, limit=100000))
        return out

    def is_all_done(self) -> bool:
        """是否已无待办（终结判据：没有任何 ACTIVE 状态任务）。"""
        counts = self.count_by_state()
        return all(counts.get(state, 0) == 0 for state in TaskState.ACTIVE)

    def summary(self) -> Dict[str, Any]:
        """状态统计 + 后端描述（CLI status 头部用）。"""
        return {"counts": self.count_by_state(), "store": self.describe()}

    def require_task(self, task_name: str) -> TaskRecord:
        """读一条，不存在则抛 TaskNotFound。"""
        rec = self.get_task(task_name)
        if rec is None:
            raise TaskNotFound("任务不存在: %s" % task_name)
        return rec


def resolve_path_template(template: str, ctx: Dict[str, Any]) -> str:
    """展开路径模板里的 ``{name}`` / ``{role}`` / ``{base_dir}`` / ``{shared}``。

    未知占位符保持原样（便于报错时定位）。``shared`` 在 ctx 里是 shared 介质根路径，
    缺失时展开为空串并不静默 —— 调用方（工厂）负责校验非空。
    """
    if not template:
        return template
    mapping = {
        "name": str(ctx.get("name") or "rhop"),
        "role": str(ctx.get("role") or "").lower(),
        "base_dir": str(ctx.get("base_dir") or ""),
        "shared": str(ctx.get("shared_root") or ""),
    }
    out = str(template)
    for key, value in mapping.items():
        out = out.replace("{" + key + "}", value)
    return out


def require_shared_root(ctx: Dict[str, Any]) -> str:
    """校验 ctx 里存在可承载数据库的共享根路径，否则抛 StoreUnavailable。

    只有文件系统形态的 shared path（本地目录 / UNC / 盘符 / file:// 解析出的路径）
    能承载 SQLite；http(s) 形态或只有 SFTP/Git 在线通道时，应改用 sqlite-local。
    """
    root = ctx.get("shared_root")
    if not root:
        raise StoreUnavailable(
            "sqlite-shared 需要 shared path 能解析为文件系统路径（本地目录 / UNC / 盘符 / file://）。"
            "当前配置拿不到共享根路径：请补 shared.write（或 shared.read）指向双方共同可达的目录，"
            "或把 queue.store.kind 改为 sqlite-local（双方各自持库 + 加密同步）。"
        )
    return str(root)


__all__ = ["TaskStore", "resolve_path_template", "require_shared_root",
           "LEASE_RECLAIM_LAST_ERR"]