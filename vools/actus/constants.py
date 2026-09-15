"""平台常量：trust 三级、平台清单、权限白名单、允许的平台目录名（docs/03、docs/07 §3）。"""

__all__ = ['TRUST_LEVELS', 'PLATFORMS', 'PERMISSIONS', 'ALLOWED_PLATFORM_DIRS', 'SCOPE_LEVELS']

TRUST_LEVELS = ('audit', 'trusted', 'sandbox')

PLATFORMS = ('desktop', 'web', 'macos', 'harmonyos', 'linux')

PERMISSIONS = (
    'files:read', 'files:write', 'files:delete',
    'net:connect', 'net:listen',
    'process:spawn',
    'ui:notify', 'ui:control', 'ui:capture',
    'sys:settings',
)

# docs/08 §1：分类子目录仅作组织用途，可按需扩展，这里给出一组默认值
ALLOWED_PLATFORM_DIRS = frozenset(PLATFORMS) | frozenset(
    ['text', 'files', 'net', 'system', 'clipboard', 'demo', 'utils', 'ai'])

# 动作市场信任级别（docs/20 §3）
SCOPE_LEVELS = ('trusted', 'community', 'unverified', 'sandbox')

# Scope 到权限的映射（docs/20 §5）
SCOPE_PERMISSIONS = {
    'trusted': list(PERMISSIONS),  # 全部权限
    'community': ['files:read', 'files:write', 'net:connect', 'process:spawn', 'ui:notify'],
    'unverified': ['files:read'],  # 只读
    'sandbox': ['files:read', 'ui:notify'],  # 沙箱内只读+通知
}
