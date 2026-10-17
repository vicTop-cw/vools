"""
vools.bridge.md.rich.protocol — 宿主消息协议

宿主（宿主应用 / CLI 预览器）与 rich 渲染器之间交换的消息格式。

消息类型：
- open_file:   请求方请求宿主打开文件（携带 request_id）
- open_result: 宿主回传打开结果（携带同一 request_id，配对校验）
- render:      rich 渲染块产出 HTML 片段（渲染器 → 宿主，无需 request_id）

统一字段：
- type:        消息类型
- block_id:    来源块标识
- request_id:  请求标识（open_file / open_result 必须成对出现并一致）
- payload:     消息体（dict）

出口条件：序列化 → 反序列化往返后字段等价；request_id 不匹配时
matches_request 返回 False；非法消息抛 MDRichProtocolError。
"""


__all__ = [
    "build_open_file",
    "build_open_result",
    "build_render",
    "serialize",
    "deserialize",
    "validate_message",
    "matches_request",
    "OPEN_FILE",
    "OPEN_RESULT",
    "RENDER",
    "VALID_TYPES",
]

import json
from typing import Dict, Optional

from ..errors import MDRichProtocolError
from .status import OK_CODE

OPEN_FILE = "open_file"
OPEN_RESULT = "open_result"
RENDER = "render"

VALID_TYPES = (OPEN_FILE, OPEN_RESULT, RENDER)


def _base(block_id: str, msg_type: str, request_id: Optional[str] = None) -> Dict:
    msg: Dict = {"type": msg_type, "block_id": block_id, "payload": {}}
    if request_id is not None:
        msg["request_id"] = request_id
    return msg


def build_open_file(
    block_id: str,
    request_id: str,
    target: str,
    resolved_path: Optional[str] = None,
    payload: Optional[Dict] = None,
) -> Dict:
    """构造 open_file 消息（请求宿主打开 target）。"""
    msg = _base(block_id, OPEN_FILE, request_id)
    msg["payload"]["target"] = target
    if resolved_path:
        msg["payload"]["resolved_path"] = resolved_path
    if payload:
        msg["payload"].update(payload)
    return msg


def build_open_result(
    block_id: str,
    request_id: str,
    status,
    payload: Optional[Dict] = None,
) -> Dict:
    """构造 open_result 消息。status 可为 RichStatus / dict / bool。"""
    msg = _base(block_id, OPEN_RESULT, request_id)
    if hasattr(status, "to_dict"):
        msg["payload"]["status"] = status.to_dict()
    elif isinstance(status, dict):
        msg["payload"]["status"] = status
    else:
        ok = bool(status)
        msg["payload"]["status"] = {
            "code": OK_CODE if ok else "E_OPEN_FAILED",
            "ok": ok,
        }
    if payload:
        msg["payload"].update(payload)
    return msg


def build_render(
    block_id: str,
    html_fragment: str,
    meta: Optional[Dict] = None,
) -> Dict:
    """构造 render 消息（渲染器 → 宿主，无 request_id）。"""
    msg = _base(block_id, RENDER)
    msg["payload"]["html"] = html_fragment
    if meta:
        msg["payload"]["meta"] = meta
    return msg


def serialize(msg: Dict) -> str:
    """消息 → JSON 字符串（先校验，再序列化）。"""
    validate_message(msg)
    return json.dumps(msg, ensure_ascii=False)


def deserialize(raw: str) -> Dict:
    """JSON 字符串 → 消息（先解析，再校验）。"""
    try:
        msg = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise MDRichProtocolError(
            f"消息 JSON 非法: {exc}",
            code="E_PROTOCOL_INVALID",
        ) from exc
    validate_message(msg)
    return msg


def validate_message(msg) -> None:
    """结构校验：类型合法、必填字段齐全、request_id 成对规则。"""
    if not isinstance(msg, dict):
        raise MDRichProtocolError(
            "消息必须是 dict",
            code="E_PROTOCOL_INVALID",
        )
    mtype = msg.get("type")
    if mtype not in VALID_TYPES:
        raise MDRichProtocolError(
            f"未知消息类型: {mtype!r}",
            code="E_PROTOCOL_INVALID",
        )
    if "block_id" not in msg:
        raise MDRichProtocolError(
            "消息缺少 block_id",
            code="E_PROTOCOL_INVALID",
        )
    payload = msg.get("payload")
    if not isinstance(payload, dict):
        raise MDRichProtocolError(
            "消息缺少 payload dict",
            code="E_PROTOCOL_INVALID",
        )
    if mtype in (OPEN_FILE, OPEN_RESULT) and not msg.get("request_id"):
        raise MDRichProtocolError(
            "open_file/open_result 必须携带 request_id",
            code="E_PROTOCOL_INVALID",
        )


def matches_request(msg: Dict, request_id: str) -> bool:
    """request_id 配对校验：消息必须存在且与期望一致。"""
    if not isinstance(msg, dict) or "request_id" not in msg:
        return False
    return str(msg["request_id"]) == str(request_id)

