"""vools.rhop.task.local_runner - 本地任务路由（p1/p2 分流执行）

对标 sparksql-exe S9 的 ``utils/local_runner`` 语义，rhop 化实现：

* ``should_run_local(task, policy)`` — 判定任务能否在**本节点**直接执行：
  显式标记（``exec_local`` / ``EXEC_LOCAL``）优先；否则按 payload 通道推断，
  并要求执行白名单（``ExecPolicy``）放行——白名单拒绝一律不本地跑。
* ``run_local_task(task, policy, result_dir)`` — 用 ``exec.run_payload`` 真跑，
  结果（可选）落盘 ``{result_dir}/{task_name}.result.json``（JSON + sha256 完整性）。
* ``mark_local_result(store, task_name, summary)`` — 把结果摘要回写 store 的
  ``back_info`` 字段（供 sync 通道把状态带回对端）。

任务 dict 字段约定（对齐 sparksql-exe，大小写双兼容）：
    exec_local / EXEC_LOCAL : bool   显式要求本地执行
    runner     / RUNNER     : str   执行通道提示（"cli:python" / "action:jump.probe"）
    task_name / TASK_NAME   : str   任务身份（结果文件命名用）

本模块不接管队列状态流转——只做「判定 + 执行 + 落盘 + 回写摘要」四个纯函数级动作，
调用方（p1/p2 守护进程）自行决定 LOCKED/RUNNING/COMPLETED 的推进。
"""

from __future__ import absolute_import

import hashlib
import json
import os
from typing import Any, Dict, Optional, Tuple

from .exec import ExecPolicy, run_payload, resolve_channel

#: 本地执行显式标记键（双大小写兼容）
_EXEC_LOCAL_KEYS = ("exec_local", "EXEC_LOCAL")
_RUNNER_KEYS = ("runner", "RUNNER")
_TASK_NAME_KEYS = ("task_name", "TASK_NAME")


def _first(task: dict, keys: Tuple[str, ...], default: Any = None) -> Any:
    for k in keys:
        if k in task and task[k] is not None:
            return task[k]
    return default


def should_run_local(task: dict, policy: Optional[ExecPolicy] = None) -> Tuple[bool, str]:
    """判定任务能否在本节点直接执行。

    Returns:
        (True, reason)  可本地执行（reason 为通道名）
        (False, reason) 不可本地执行（reason 说明：无指令 / 白名单拒绝 / 显式关闭）

    判定顺序：
        1. ``exec_local=False``（显式关闭）→ 直接 False；
        2. payload 无可识别通道（action/cli/handler）→ False（转发对端）；
        3. 白名单（policy）拒绝该通道 → False（安全边界，与 exec 一致）；
        4. 其余 → True。
    """
    if not isinstance(task, dict):
        return False, "任务不是 dict"
    if _first(task, _EXEC_LOCAL_KEYS) is False:
        return False, "显式 exec_local=False"
    policy = policy or ExecPolicy()

    payload = task.get("payload") if isinstance(task.get("payload"), dict) else task
    resolved = resolve_channel(payload, task_type=str(task.get("task_type") or ""))
    channel = resolved.get("channel")
    if not channel:
        return False, "无可识别指令通道（%s）" % resolved.get("reason")

    runner_hint = str(_first(task, _RUNNER_KEYS) or "").strip()
    if runner_hint and not runner_hint.startswith(channel):
        # runner 提示与本节点可解析通道不符 → 交给指定通道所在节点
        return False, "runner=%s 与本地通道 %s 不符" % (runner_hint, channel)

    try:
        policy.check(channel, resolved.get("name") or "")
    except Exception as exc:  # ExecDenied —— 与 exec 白名单语义一致
        return False, "白名单拒绝: %s" % exc
    return True, channel


def run_local_task(task: dict, policy: Optional[ExecPolicy] = None,
                   result_dir: Optional[str] = None,
                   timeout_sec: Optional[float] = None) -> Dict[str, Any]:
    """在本地执行一个任务 dict，返回统一结果结构。

    Args:
        task:       任务 dict（含 payload/cli/action/handler 指令 + task_name）
        policy:     执行白名单（缺省 ExecPolicy 默认：action/handler 放行、cli 需显式）
        result_dir: 结果落盘目录；给定时写 ``{result_dir}/{task_name}.result.json``
        timeout_sec: 覆盖执行超时

    Returns:
        {"ok", "task_name", "channel", "result", "error", "result_file", "sha256"}
        result_file/sha256 仅在 result_dir 提供且执行完成（无论成败）时给出。
    """
    policy = policy or ExecPolicy()
    task_name = str(_first(task, _TASK_NAME_KEYS) or "unnamed")
    payload = task.get("payload") if isinstance(task.get("payload"), dict) else task
    # timeout_sec 经 cli 通道生效（run_payload 无独立超时参数；cli 缺省走 policy.timeout_sec）
    if timeout_sec is not None:
        cli = payload.setdefault("cli", {})
        cli["timeout_sec"] = float(timeout_sec)
    out = run_payload(payload, policy=policy, action_cfg=task.get("action_cfg") or {},
                      task_type=str(task.get("task_type") or ""))

    result_file = None
    sha256 = None
    if result_dir:
        os.makedirs(result_dir, exist_ok=True)
        body = {
            "task_name": task_name,
            "ok": bool(out.get("ok")),
            "channel": out.get("channel"),
            "result": out.get("result"),
            "error": out.get("error"),
        }
        raw = json.dumps(body, ensure_ascii=False, sort_keys=True).encode("utf-8")
        sha256 = hashlib.sha256(raw).hexdigest()
        result_file = os.path.join(result_dir, "%s.result.json" % _safe_name(task_name))
        with open(result_file, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({**body, "sha256": sha256}, ensure_ascii=False, indent=2))

    return {
        "task_name": task_name,
        "ok": bool(out.get("ok")),
        "channel": out.get("channel"),
        "result": out.get("result"),
        "error": out.get("error"),
        "result_file": result_file,
        "sha256": sha256,
    }


def mark_local_result(store: Any, task_name: str, summary: Dict[str, Any],
                      now: Optional[str] = None) -> bool:
    """把本地执行结果摘要回写 store 的 back_info（供 sync 通道带回对端）。

    Args:
        store:    TaskStore（get_task/update_fields 能力即可）
        summary:  run_local_task 的返回（或其子集）；序列化为 JSON 文本写入 back_info
    Returns:
        任务存在且回写成功 → True；任务不存在 → False
    """
    rec = store.get_task(task_name)
    if rec is None:
        return False
    compact = json.dumps(summary, ensure_ascii=False, sort_keys=True, default=str)
    return bool(store.update_fields(task_name, now=now, back_info=compact))


def _safe_name(task_name: str) -> str:
    """结果文件名安全化：仅保留字母数字-_，其余转下划线。"""
    return "".join(c if (c.isalnum() or c in "-_") else "_" for c in task_name) or "unnamed"


__all__ = ["should_run_local", "run_local_task", "mark_local_result"]
