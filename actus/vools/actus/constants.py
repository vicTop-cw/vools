"""平台常量：trust 三级、平台清单、权限白名单、允许的平台目录名（docs/03、docs/07 §3）。

分类体系 v2.0（docs/03 §2 分类体系章节）：
- 5 维度分类：kind / purpose / industry / trigger / context_applies
- 开放枚举：已知值集合可追加扩展，不破坏兼容
- 验证分级：kind 未知值打回；purpose/industry/trigger/context_applies 未知值警告

资产化治理（future_plan §3）：platform 必填、id 命名约束、secrets 敏感字样
均在此定义单一真源，validate.py / indexer.py 复用。
"""

import re

__all__ = [
    'TRUST_LEVELS', 'PLATFORMS', 'PERMISSIONS', 'ALLOWED_PLATFORM_DIRS', 'SCOPE_LEVELS',
    'SCOPE_PERMISSIONS',
    # 动作文件后缀单一真源
    'ACTION_SUFFIXES', 'is_action_file',
    # 分类体系 v2.0
    'KIND_LEVELS', 'PURPOSE_LEVELS', 'INDUSTRY_LEVELS', 'TRIGGER_DECL_LEVELS',
    'LICENSE_LEVELS', 'PRICING_LEVELS', 'DECLARED_FEATURE_LEVELS',
    'CLASSIFICATION_VERSION',
    'is_known_kind', 'is_known_purpose', 'is_known_industry', 'is_known_trigger_decl',
    'is_known_license', 'is_known_pricing', 'is_known_declared_feature',
    # 资产化治理（future_plan §3 修订落地）
    'ID_NAMESPACE_RE', 'TESTISH_ID_PARTS', 'SECRET_SENSITIVE_PATTERNS',
    'is_known_platform', 'is_namespaced_id', 'is_testish_id',
    'is_secret_sensitive_name', 'SECRET_SENSITIVE_HARDCODE_RE',
]

TRUST_LEVELS = ('audit', 'trusted', 'sandbox')

# ── 平台清单（docs/03 §2 可使用平台）────────────────────────────
# future_plan §3 #1：platform 由「选填、缺省全平台」改为「必填」。
# 取值覆盖本机资产化主线：windows（本机 Win 桌面）/ wsl（WSL 桥）/ android（模拟器）
# 与原桌面/Web/专属平台枚举叠加。
PLATFORMS = ('desktop', 'web', 'macos', 'harmonyos', 'linux',
             'windows', 'wsl', 'android')

# ── 动作 id 命名约束（future_plan §3 #6）────────────────────────
# 资产池正式动作：至少两段点分小写（反向域名风格），如 actus.hello / jump.push
# id 命名空间（docs/03 §4.2）：反域名风格，**段内允许下划线**
# （scaffold._generate_id 生成的 actus.generated.xxx 与 basics 的 image_viewer
#  都带下划线；早期正则不含下划线，把一批合法存量 id 误判为"不合命名"）。
ID_NAMESPACE_RE = re.compile(r'^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$')

# 测试味片段：出现在正式 id 中即视为「非资产池资产」。
# demo 命名空间单独豁免（kind=demo 的演示动作本就不进资产池，由调用方判定）。
TESTISH_ID_PARTS = ('test', 'generated', 'foo', 'example', 'bar')

# ── 敏感凭据字样（future_plan §3 #4 secrets 强制）────────────────
# 用于静态扫描：硬编码赋值 / 未声明敏感 env
SECRET_SENSITIVE_PATTERNS = (
    'password', 'passwd', 'pwd', 'token', 'api[_-]?key', 'secret',
    'access[_-]?key', 'private[_-]?key', 'credential',
)

SECRET_SENSITIVE_HARDCODE_RE = re.compile(
    r'(?:password|passwd|pwd|token|api[_-]?key|secret|access[_-]?key|'
    r'private[_-]?key|credential)\s*[=:]\s*["\']',
    re.IGNORECASE,
)

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

# ============================================================================
# 动作文件后缀（单一真源，docs/08 §1 + ACTUS_SCHEMA_SPEC.md）
# ============================================================================
# 双后缀：.actus.md（旧格式 #!cfg JSON）+ .actus.schema.md（新格式 YAML front-matter）。
# 历史上各模块各写一份 endswith('.actus.md')，导致 installer/publisher/registry
# 等对新格式动作"半盲"（扫不到、装不了、校验漏）——统一走本谓词。
ACTION_SUFFIXES = ('.actus.md', '.actus.schema.md')


def is_action_file(filename: str) -> bool:
    """动作文件判定（单一真源）。

    所有扫描/安装/发布/注册路径必须走本函数，禁止再写 endswith('.actus.md')。
    """
    return str(filename).endswith(ACTION_SUFFIXES)

# ============================================================================
# 分类体系 v2.0（docs/03 §2 分类体系章节）
# ============================================================================
# 开放枚举：新值追加到元组即可扩展，不破坏兼容（向后兼容保证）。
# 验证分级（docs/03 §2.4 验证分级表）：
#   - kind：未知值 → 打回（决定执行逻辑，错误值导致执行混乱）
#   - purpose/industry/trigger_decl：未知值 → 警告（分类标签，不影响执行）
#   - context_applies：自由字符串 + 警告（Quicker 式：exe 名/文件类型/OS）
# ============================================================================

CLASSIFICATION_VERSION = '2.0'

# 维度 1：kind（执行类型，单值，必填）——决定系统如何执行该动作
KIND_LEVELS = ('exec', 'link', 'demo', 'template', 'alias', 'bundle', 'doc')

# 维度 2：purpose（用途，多值 1..5，可选，默认 [utility]）——动作"做什么"
PURPOSE_LEVELS = ('source', 'sink', 'transform', 'orchestrator', 'notify',
                  'control', 'monitor', 'compute', 'ai', 'data-store',
                  'security', 'utility')

# 维度 3：industry（行业，多值 1..5，可选，默认 [general]）——动作"服务谁"
INDUSTRY_LEVELS = ('devops', 'finance', 'healthcare', 'hr', 'sales',
                   'marketing', 'customer-support', 'education', 'legal', 'general')

# 维度 4：trigger（触发方式声明，多值 1..8，可选，默认 [manual]）
# 主触发声明，不替代 ## Triggers 段（triggers.py 的完整触发器配置仍是真源）
TRIGGER_DECL_LEVELS = ('manual', 'cron', 'watch', 'webhook', 'hotkey',
                       'on_startup', 'signal', 'dataset')

# 许可证注册表（可选，默认 mit）——作者声明，未知值警告
LICENSE_LEVELS = ('mit', 'apache-2.0', 'gpl-3.0', 'cc0', 'proprietary', 'custom')

# 定价模式（可选，默认 free）——gated 付费预留（未接支付前 paid 按 gated 免费放行+警告）
PRICING_LEVELS = ('free', 'paid', 'subscription')

# 作者自声明特性（可选）——供 trust 决策预计算，与扫描结果不符 → 警告
DECLARED_FEATURE_LEVELS = ('network-access', 'file-write', 'state-persist',
                           'third-party-api', 'ui-automation')

# context_applies 不预设闭集——自由字符串 + 警告（Quicker 式：exe 名/文件类型/OS）


# ─── 已知值判定（单一真源，validate.py 复用） ───

def is_known_kind(value: str) -> bool:
    """kind 已知值判定。"""
    return str(value).lower() in KIND_LEVELS


def is_known_purpose(value: str) -> bool:
    """purpose 已知值判定。"""
    return str(value).lower() in PURPOSE_LEVELS


def is_known_industry(value: str) -> bool:
    """industry 已知值判定。"""
    return str(value).lower() in INDUSTRY_LEVELS


def is_known_trigger_decl(value: str) -> bool:
    """trigger 声明已知值判定。"""
    return str(value).lower() in TRIGGER_DECL_LEVELS


def is_known_license(value: str) -> bool:
    """license 已知值判定。"""
    return str(value).lower() in LICENSE_LEVELS


def is_known_pricing(value: str) -> bool:
    """pricing 已知值判定。"""
    return str(value).lower() in PRICING_LEVELS


def is_known_declared_feature(value: str) -> bool:
    """declared_features 已知值判定。"""
    return str(value).lower() in DECLARED_FEATURE_LEVELS


# ─── 资产化治理判定（future_plan §3 单一真源） ───

def is_known_platform(value: str) -> bool:
    """platform 取值已知判定（docs/03 §2 可使用平台枚举）。"""
    return str(value).lower() in PLATFORMS


def is_namespaced_id(value: str) -> bool:
    """id 是否符合资产池命名：至少两段点分小写（反向域名风格）。"""
    return bool(ID_NAMESPACE_RE.match(str(value) or ''))


def is_testish_id(value: str) -> bool:
    """id 是否含测试味片段（test/generated/foo/example/bar）。

    注意：仅判片段，不含 kind=demo 豁免——demo 命名空间由调用方
    （indexer 资产池判定）结合 kind 一并裁决。
    """
    aid = str(value or '').lower()
    return any(p in aid.split('.') for p in TESTISH_ID_PARTS)


def is_secret_sensitive_name(name: str) -> bool:
    """环境变量名是否命中敏感凭据字样（password/token/key/secret...）。"""
    n = str(name or '').lower()
    return any(re.search(p, n) for p in SECRET_SENSITIVE_PATTERNS)
