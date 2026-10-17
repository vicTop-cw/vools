"""
vools.bridge.md.rich.status — 富内容状态/错误模型与文案映射

错误码设计（对应计划 §4.3 / §5 安全模型）：
- OK                     成功
- E_PATH_NOT_FOUND       目标路径不存在
- E_ACCESS_DENIED        路径越权 / 绝对路径未 opt-in / 符号链接逃逸 / 产物引用越界
- E_UNSUPPORTED_EXT      扩展名不在白名单
- E_NO_ASSOC             无关联程序可打开
- E_OPEN_FAILED          打开失败
- E_REMOTE_DISABLED      远程图片默认禁用（未 opt-in）
- E_SANITIZE_BLOCKED     内容被 L1 过滤剥离
- E_LEVEL_VIOLATION      档位越权（块级 level 超过文件级上限）
- E_PROTOCOL_INVALID     宿主消息协议非法

出口条件：status 文案映射全绿（每个错误码都有文案、OK 映射成功）。
"""


__all__ = [
    "RichStatus",
    "message_for",
    "ok_status",
    "error_status",
    "to_dict",
]

from typing import Dict, Optional

from ...core.compat.dataclass_compat import dataclass

#: 成功码
OK_CODE = "OK"

#: 错误码 → 用户可读文案（唯一真源）
STATUS_MESSAGES: Dict[str, str] = {
    OK_CODE: "成功",
    "E_PATH_NOT_FOUND": "目标路径不存在",
    "E_ACCESS_DENIED": "路径越权或安全策略拒绝",
    "E_UNSUPPORTED_EXT": "扩展名不在允许白名单",
    "E_NO_ASSOC": "无关联程序可打开",
    "E_OPEN_FAILED": "打开失败",
    "E_REMOTE_DISABLED": "远程图片默认禁用，需显式 opt-in",
    "E_SANITIZE_BLOCKED": "内容被 L1 过滤剥离",
    "E_LEVEL_VIOLATION": "档位越权：块级 level 超过文件级上限",
    "E_PROTOCOL_INVALID": "宿主消息协议非法",
}


@dataclass
class RichStatus:
    """富内容状态模型"""

    code: str = OK_CODE
    message: str = ""
    ok: bool = True
    detail: Optional[str] = None

    def to_dict(self) -> Dict:
        d: Dict = {"code": self.code, "ok": self.ok}
        if self.message:
            d["message"] = self.message
        if self.detail:
            d["detail"] = self.detail
        return d


def message_for(code: str) -> str:
    """错误码 → 文案（未知码回退通用文案，不抛异常）。"""
    return STATUS_MESSAGES.get(code, "未知状态")


def ok_status(message: str = "") -> RichStatus:
    """构造成功状态。"""
    return RichStatus(
        code=OK_CODE,
        message=message or STATUS_MESSAGES[OK_CODE],
        ok=True,
    )


def error_status(code: str, detail: Optional[str] = None) -> RichStatus:
    """构造失败状态（code 必须在 STATUS_MESSAGES 中，否则回退通用文案）。"""
    msg = STATUS_MESSAGES.get(code, "未知状态")
    return RichStatus(code=code, message=msg, ok=False, detail=detail)

