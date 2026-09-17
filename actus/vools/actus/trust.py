"""trust 信任判定与权限白名单（docs/07 §1/§3）。

执行核心是唯一信任判定源：
- trusted：可自动执行，权限受白名单约束；
- audit：改动型副作用需人类确认（确认通道见 executor / mcp 层）；
- sandbox：仅沙箱根内活动。

permissions 白名单以常量表为准，未声明能力默认拒绝。
"""

__all__ = ['decide', 'check_permissions']

from typing import Optional

from .errors import ActionError
from .constants import PERMISSIONS, TRUST_LEVELS


def decide(trust: str, confirmed: Optional[bool] = None) -> str:
    """trust → 执行策略。

    返回：
      'auto'        — 直接执行（trusted）
      'need_confirm'— 需人类确认（audit 且未确认）
      'sandbox'     — 沙箱执行（sandbox）

    audit 且 confirmed=True（人类已确认回执）→ 视同放行执行。
    非法 trust 抛 trust_rejected。
    """
    if trust not in TRUST_LEVELS:
        raise ActionError('trust_rejected', f'trust 取值非法: {trust!r}')
    if trust == 'trusted':
        return 'auto'
    if trust == 'sandbox':
        return 'sandbox'
    # audit
    return 'auto' if confirmed else 'need_confirm'


def check_permissions(declared, requested: str) -> None:
    """越权检查：requested 能力必须已在动作 permissions 白名单声明。

    越权抛 permission_denied（docs/07 §3：未声明能力默认拒绝）。
    """
    if requested not in PERMISSIONS:
        raise ActionError('permission_denied',
                          f'未知权限: {requested!r}（合法权限见 docs/07 §3）')
    declared = declared or []
    if requested not in declared:
        raise ActionError('permission_denied',
                          f'动作未声明权限 {requested!r}，默认拒绝',
                          {'declared': declared, 'requested': requested})
