"""vools.rhop.interact - 配置驱动一键交互入口（配置驱动地基 Step 4 收口）

交互入口（analysis/rhop-PLAN.md 附录 C C.1）:
    rhop.interact(cfg, action="jump.push", payload={...})
    # cfg: 密钥 + 本端角色 + 介质配置 + 对端/中转地址
    # 自动完成: 选通道 -> 加密 -> 传输 -> 解密验证 -> 执行动作 -> 回传结果

三种模式：
    mode="execute"   本端直接执行动作（jump.probe 等无对端动作）
    mode="request"   发送侧：加密动作请求包投递到介质，交由对端处理
    mode="roundtrip" 单机闭环：发送请求包 -> 对端（同进程模拟）取包解密执行 ->
                     加密回传 -> 本端取回解密验证（测试/演示用）

接收侧处理：
    handle_request(cfg, filename)  取包 -> 解密验证 -> run_action ->
                                   加密回传 "res_<filename>"，返回完整结果
"""

from typing import Any, Dict, Optional, Union

from .actions import omega_unwrap, run_action
from .config import RhopConfig, load_config


def _coerce(cfg: Union[RhopConfig, dict, str]) -> RhopConfig:
    """接受 RhopConfig / dict / JSON 文件路径，统一为 RhopConfig。"""
    if isinstance(cfg, RhopConfig):
        return cfg
    if isinstance(cfg, dict):
        return RhopConfig.from_dict(cfg)
    if isinstance(cfg, str):
        return load_config(cfg)
    raise ValueError("cfg 必须是 RhopConfig / dict / JSON 文件路径")


def interact(
    cfg: Union[RhopConfig, dict, str],
    action: str,
    payload: Optional[dict] = None,
    mode: str = "execute",
    request_filename: Optional[str] = None,
) -> dict:
    """配置驱动一键交互。

    Args:
        cfg: RhopConfig / dict / JSON 文件路径
        action: 动作名（jump.probe / jump.push / jump.pull / jump.sync）
        payload: 动作载荷
        mode: execute（本端执行）/ request（发送动作包）/ roundtrip（单机闭环）
        request_filename: 动作包文件名（缺省按动作名生成）

    Returns:
        execute     -> omega_unwrap 后的动作结果
        request     -> {"status": "ok", "transport", "filename"} 投递结果
        roundtrip   -> {"status": "ok", "transport", "result": <omega_unwrap 结果>,
                        "response_transport", "response_filename"}
    """
    config = _coerce(cfg)

    if mode == "execute":
        result = run_action(action, config.action_cfg(), payload)
        return omega_unwrap(result)

    if mode not in ("request", "roundtrip"):
        raise ValueError("未知 mode: %s（可用 execute/request/roundtrip）" % mode)

    filename = request_filename or "req_{0}.rhop".format(action.replace(".", "_"))
    sender = config.build_session(role="SEND")
    request = {"action": action, "payload": payload if payload is not None else {}}
    sent = sender.send_package(filename, request)
    if mode == "request":
        return sent

    # roundtrip: 对端同进程模拟（B 端复用同一份介质/密钥取包执行并回传）
    response = handle_request(config, filename, session=config.build_session(role="RECV"))
    if response.get("status") != "ok":
        return {"status": "error", "omega_gate": response}

    # 发送侧取回响应并解密验证
    sender_back = sender
    resp_filename = "res_{0}".format(filename)
    fetched = sender_back.recv_package(resp_filename)
    if fetched.get("status") != "ok":
        return {"status": "error", "omega_gate": fetched}
    payload_out = fetched.get("payload") or {}
    return {
        "status": "ok",
        "transport": sent.get("transport"),
        "filename": filename,
        "response_transport": fetched.get("transport"),
        "response_filename": resp_filename,
        "result": payload_out.get("result"),
        "action_result": payload_out.get("action_result"),
    }


def handle_request(
    cfg: Union[RhopConfig, dict, str],
    filename: str,
    session: Optional[object] = None,
) -> dict:
    """接收侧处理一个动作请求包。

    流程：取包 -> 解密验证 -> run_action -> 加密回传 "res_<filename>"。
    返回: {"status": "ok", "action", "transport", "result", "response_filename"}
         失败: {"status": "error", "reason", ...}
    """
    config = _coerce(cfg)
    receiver = session or config.build_session(role="RECV")
    received = receiver.recv_package(filename)
    if received.get("status") != "ok":
        return {"status": "error", "reason": received.get("reason"),
                "transport": received.get("transport")}

    request = received.get("payload") or {}
    action = request.get("action")
    if not action:
        return {"status": "error", "reason": "请求包缺少 action 字段"}
    result = run_action(action, config.action_cfg(), request.get("payload"))
    unwrapped = omega_unwrap(result)

    # 回传处理结果
    resp_filename = "res_{0}".format(filename)
    sender = receiver.reverse()
    sent = sender.send_package(resp_filename, {
        "action": action,
        "result": unwrapped.get("status"),
        "action_result": unwrapped,
    })
    return {
        "status": "ok",
        "action": action,
        "transport": received.get("transport"),
        "result": unwrapped,
        "response_filename": resp_filename,
        "response_sent": sent.get("status"),
    }
