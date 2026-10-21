"""vools.rhop.actions - 公开动作集（配置驱动地基 Step 2）

rhop 交互的执行单元：动作名 + 配置 + payload 即得统一出参。
每个动作签名 (cfg, payload) -> dict，出参形状：
    {"status": "ok"|"error", "action": "<name>", "data": <动作结果 dict>}

跨动作调用带 Ω-gate 容错解包（对齐 analysis/rhop-PLAN.md 附录 C C2.2）：
    omega_unwrap(result)：
        - 外层 status=="ok" 且内层 data.status in ("ok","partial") -> 判成功，返回 data
        - 否则返回带 omega_gate 字段的错误出参（gate error 挂 omega_gate）
"""

from typing import Callable, Dict, Optional

from .jump import ACTIONS as _JUMP_ACTIONS

# 动作注册表：动作名 -> 处理函数 (cfg, payload) -> dict
ACTIONS: Dict[str, Callable] = dict(_JUMP_ACTIONS)

# 判成功的内层状态集合（对齐 actus Ω-gate：data.status==ok 即成功，partial 视为可接受）
_OK_STATUSES = ("ok", "partial")

__all__ = [
    "ACTIONS",
    "run_action",
    "omega_unwrap",
    "jump_probe",
    "jump_push",
    "jump_pull",
    "jump_sync",
]


def run_action(action: str, cfg: dict, payload: Optional[dict] = None) -> dict:
    """按动作名执行公开动作，统一包一层外层状态。

    返回:
        {"status": "ok", "action": action, "data": <动作结果>}
        {"status": "error", "action": action, "data": None,
         "omega_gate": {"error": <原因>}}
    """
    handler = ACTIONS.get(action)
    if handler is None:
        known = ", ".join(sorted(ACTIONS.keys()))
        return {
            "status": "error",
            "action": action,
            "data": None,
            "omega_gate": {"error": "未知动作: %s（可用: %s）" % (action, known)},
        }
    try:
        result = handler(cfg, payload)
    except Exception as e:  # 动作实现内部异常统一收纳，不给调用方裸抛
        return {
            "status": "error",
            "action": action,
            "data": None,
            "omega_gate": {"error": "动作执行异常: %s" % e},
        }
    return {"status": "ok", "action": action, "data": result}


def omega_unwrap(result: dict) -> dict:
    """Ω-gate 容错解包：内层 data.status==ok（或 partial）判成功。

    成功 -> 原样返回内层 data（调用方直接消费动作结果）。
    失败 -> 返回带 omega_gate 字段的错误出参，错误细节集中挂载：
        {"status": "error", "omega_gate": {"action", "error", "data"}}
    """
    if not isinstance(result, dict):
        return {"status": "error", "omega_gate": {"error": "非 dict 结果"}}
    if result.get("status") != "ok":
        return {"status": "error",
                "omega_gate": result.get("omega_gate") or {"error": "外层状态异常"}}
    data = result.get("data")
    if not isinstance(data, dict):
        return {"status": "error", "omega_gate": {"error": "内层 data 缺失或非 dict"}}
    inner_status = data.get("status")
    if inner_status in _OK_STATUSES:
        return data
    return {
        "status": "error",
        "omega_gate": {
            "action": result.get("action"),
            "error": "内层 status=%s" % inner_status,
            "data": data,
        },
    }
