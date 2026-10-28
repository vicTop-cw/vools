# -*- coding: utf-8 -*-
"""第 12 轮残留修复：`_v2_read_secret` / `resolver_status` 切到只读会话。"""
import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
P = os.path.join(ROOT, 'vools/actus/vault.py')
s = io.open(P, encoding='utf-8').read()


def patch(old, new):
    global s
    assert old in s, '未匹配:\n%s' % old[:300]
    s = s.replace(old, new, 1)


# ── 1) 只读会话加缓存（热路径 resolve_secret 每个 vault:// 引用都会调；             ──
#        每次重建要跑 100k 次 pbkdf2，缓存后 TTL 内复用同一 token）────────────────
patch("""def _v2_read_secret(name: str):
    \"\"\"读 v2 单个密钥。返回 (state, value, reason)。

    state ∈ {'found','absent','unavailable','error'}：
      * unavailable → 允许回退 v1 读（不是数据问题）；
      * error       → **不回退**（例如 v2 有该密钥但解密失败，隐藏它比报错更危险）。
    \"\"\"
    v2, token, reason = _v2_session()
    if reason:
        return 'unavailable', None, reason
    try:
        result = v2.get_secret(token, name, caller='vault.resolver')
    except Exception as exc:  # noqa: BLE001
        return 'unavailable', None, 'v2 读取异常（%s: %s）' % (type(exc).__name__, exc)
    if result.get('status') == 'ok':
        return 'found', result.get('value'), None
    message = str(result.get('message') or '')
    if '凭证不存在' in message:
        return 'absent', None, None
    if '会话无效' in message:
        v2, token, reason = _v2_session(force=True)
        if reason:
            return 'unavailable', None, reason
        try:
            result = v2.get_secret(token, name, caller='vault.resolver')
        except Exception as exc:  # noqa: BLE001
            return 'unavailable', None, 'v2 读取异常（%s: %s）' % (type(exc).__name__, exc)
        if result.get('status') == 'ok':
            return 'found', result.get('value'), None
        message = str(result.get('message') or '')
        if '凭证不存在' in message:
            return 'absent', None, None
    return 'error', None, 'v2 读取失败：%s' % message""",
"""def _v2_read_secret(name: str):
    \"\"\"读 v2 单个密钥。返回 (state, value, reason)。

    state ∈ {'found','absent','unavailable','error'}：
      * unavailable → 允许回退 v1 读（不是数据问题）；
      * error       → **不回退**（例如 v2 有该密钥但解密失败，隐藏它比报错更危险）。

    ⚠️ 第 12 轮残留修复：本函数是 `resolve_secret()`（CLI `vault get`、`vault list`
    逐 key 解析、executor `vault://` 批量解析）的**最热读路径**，之前用 `_v2_session()`
    （`vault2.auth()` 会 UPDATE `last_auth_at`/`failed_attempts`/`used_codes`），
    等于每次读密钥都在偷写 db。现在改走 `_v2_readonly_session()`：读不是登录，
    不做登录副作用（`used_codes` 防重放/失败计数），但 PIN/锁定/机器指纹检查照做
    —— 因此读到的值、source、warnings 与改前一致（见验收脚本对比）。
    \"\"\"
    v2, token, reason = _v2_readonly_session()
    if reason:
        return 'unavailable', None, reason
    try:
        result = v2.get_secret(token, name, caller='vault.resolver')
    except Exception as exc:  # noqa: BLE001
        return 'unavailable', None, 'v2 读取异常（%s: %s）' % (type(exc).__name__, exc)
    if result.get('status') == 'ok':
        return 'found', result.get('value'), None
    message = str(result.get('message') or '')
    if '凭证不存在' in message:
        return 'absent', None, None
    if '会话无效' in message:
        _V2_READONLY_CACHE.clear()          # 只清只读缓存，重建一次
        v2, token, reason = _v2_readonly_session()
        if reason:
            return 'unavailable', None, reason
        try:
            result = v2.get_secret(token, name, caller='vault.resolver')
        except Exception as exc:  # noqa: BLE001
            return 'unavailable', None, 'v2 读取异常（%s: %s）' % (type(exc).__name__, exc)
        if result.get('status') == 'ok':
            return 'found', result.get('value'), None
        message = str(result.get('message') or '')
        if '凭证不存在' in message:
            return 'absent', None, None
    return 'error', None, 'v2 读取失败：%s' % message""")

# ── 2) resolver_status 也走只读会话（诊断更不该写）──────────────────
patch("""def resolver_status() -> dict:
    \"\"\"resolver 自检：v2 是否可用、v1 路径、懒迁移开关（诊断用）。\"\"\"
    v2, token, reason = _v2_session()""",
"""def resolver_status() -> dict:
    \"\"\"resolver 自检：v2 是否可用、v1 路径、懒迁移开关（诊断用）。

    第 12 轮残留修复：诊断不该有写副作用 —— 切到 `_v2_readonly_session()`
    （此前走 `_v2_session()` 的 `vault2.auth()`，每次诊断都 UPDATE db）。
    \"\"\"
    v2, token, reason = _v2_readonly_session()""")

# ── 3) 只读会话缓存 + 只读值读取统一到 `_v2_read_secret` ──────────────
patch("""def _v2_readonly_session():
    \"\"\"建立**只读** v2 会话（不写 DB）。返回 (vault, token, reason)。

    与 `vault2.auth()` 的检查项对齐（存在性 / 锁定 / PIN / 机器指纹 / seed 解码 /
    master_key 派生），但：
      * 不执行 `failed_attempts/locked_until/last_auth_at` 的 UPDATE（只读）；
      * 不写 used_codes（动态码防重放是"登录"语义，只读会话不做）；
      * 失败原因以可读字符串返回，由 `list_secret_names` 填进 `v2_reason`。
    \"\"\"
    identity_id = os.environ.get(V2_IDENTITY_ENV)
    machine_id = os.environ.get(V2_MACHINE_ENV)
    pin = os.environ.get(V2_PIN_ENV)
    if not (identity_id and machine_id and pin):
        return None, None, ('未配置 v2 凭据（%s / %s / %s），v2 读不可用'
                            % (V2_IDENTITY_ENV, V2_MACHINE_ENV, V2_PIN_ENV))
    try:
        from . import vault2 as v2
        vault = v2._get_vault2()
    except Exception as exc:  # noqa: BLE001
        return None, None, 'v2 不可用（%s: %s）' % (type(exc).__name__, exc)""",
"""def _v2_readonly_session():
    \"\"\"建立**只读** v2 会话（不写 DB）。返回 (vault, token, reason)。

    与 `vault2.auth()` 的检查项对齐（存在性 / 锁定 / PIN / 机器指纹 / seed 解码 /
    master_key 派生），但：
      * 不执行 `failed_attempts/locked_until/last_auth_at` 的 UPDATE（只读）；
      * 不写 used_codes（动态码防重放是"登录"语义，只读会话不做）；
      * 失败原因以可读字符串返回，由 `list_secret_names` 填进 `v2_reason`。

    会话按 (identity, machine, pin, ACTUS_VAULT2_DIR) 缓存：`resolve_secret` 是
    最热读路径（每个 `vault://` 引用都会调），每次重建要跑 100k 次 pbkdf2；
    缓存后 TTL 内复用同一只读 token（token 仍受 vault2 的 SESSION_TTL 约束）。
    \"\"\"
    identity_id = os.environ.get(V2_IDENTITY_ENV)
    machine_id = os.environ.get(V2_MACHINE_ENV)
    pin = os.environ.get(V2_PIN_ENV)
    if not (identity_id and machine_id and pin):
        return None, None, ('未配置 v2 凭据（%s / %s / %s），v2 读不可用'
                            % (V2_IDENTITY_ENV, V2_MACHINE_ENV, V2_PIN_ENV))
    cache_key = (identity_id, machine_id, pin,
                 (os.environ.get('ACTUS_VAULT2_DIR') or '').strip())
    cached = _V2_READONLY_CACHE
    if cached.get('key') == cache_key:
        token_cached = cached.get('token')
        session_cached = (getattr(cached.get('vault'), '_sessions', None) or {}).get(
            token_cached) if token_cached else None
        if session_cached and session_cached.get('expires_at', 0) > int(time.time()):
            return cached.get('vault'), token_cached, None
    try:
        from . import vault2 as v2
        vault = v2._get_vault2()
    except Exception as exc:  # noqa: BLE001
        return None, None, 'v2 不可用（%s: %s）' % (type(exc).__name__, exc)""")

patch("""    token = 'readonly-' + secrets.token_hex(8)
    ttl = v2.SESSION_TTL.get(level, 600)
    vault._sessions[token] = {
        'identity_id': identity_id,
        'machine_id': machine_id,
        'security_level': level,
        'expires_at': int(time.time()) + ttl,
        'master_key': master_key,
    }
    return vault, token, None""",
"""    token = 'readonly-' + secrets.token_hex(8)
    ttl = v2.SESSION_TTL.get(level, 600)
    vault._sessions[token] = {
        'identity_id': identity_id,
        'machine_id': machine_id,
        'security_level': level,
        'expires_at': int(time.time()) + ttl,
        'master_key': master_key,
    }
    _V2_READONLY_CACHE.update({'key': cache_key, 'vault': vault,
                               'token': token, 'ts': time.time()})
    return vault, token, None""")

patch("""def _v2_readonly_value(name: str):
    \"\"\"只读取 v2 密钥值；失败返回 (state, value, reason)。\"\"\"
    vault, token, reason = _v2_readonly_session()
    if reason:
        return 'unavailable', None, reason
    try:
        result = vault.get_secret(token, name, caller='vault.list')
    except Exception as exc:  # noqa: BLE001
        return 'unavailable', None, 'v2 读取异常（%s: %s）' % (type(exc).__name__, exc)
    if result.get('status') == 'ok':
        return 'found', result.get('value'), None
    message = str(result.get('message') or '')
    if '凭证不存在' in message:
        return 'absent', None, None
    return 'error', None, 'v2 读取失败：%s' % message""",
"""def _v2_readonly_value(name: str):
    \"\"\"只读取 v2 密钥值；失败返回 (state, value, reason)。

    与 `_v2_read_secret` 是同一实现（避免两份逻辑漂移：本轮把 `_v2_read_secret`
    也切到只读会话后，二者语义完全一致）。
    \"\"\"
    return _v2_read_secret(name)""")

# ── 4) 常量：只读会话缓存 ─────────────────────────────────────
patch("""_V2_SESSION_CACHE: Dict[str, Any] = {}
_V2_ERROR_CACHE: Dict[str, Any] = {}""",
"""_V2_SESSION_CACHE: Dict[str, Any] = {}        # auth 会话（写路径用）
_V2_ERROR_CACHE: Dict[str, Any] = {}          # auth 失败原因缓存
_V2_READONLY_CACHE: Dict[str, Any] = {}       # 只读会话（读路径用；不含登录副作用）""")

io.open(P, 'w', encoding='utf-8').write(s)
print('vault.py read path -> readonly session patched')
