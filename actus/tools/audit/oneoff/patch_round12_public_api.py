# -*- coding: utf-8 -*-
"""第 12 轮收尾：vault.py 公开 list_secret_names / delete_secret（供 CLI/MCP 切换）。"""
import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
P = os.path.join(ROOT, 'vools/actus/vault.py')
s = io.open(P, encoding='utf-8').read()

# 1) __all__ 增加两个公开 API
old_all = """           # 统一 secret resolver（第 12 轮：v2 优先 / v1 兼容读）
           'resolve_secret', 'write_secret', 'resolve_vault_refs',
           'resolver_status']"""
new_all = """           # 统一 secret resolver（第 12 轮：v2 优先 / v1 兼容读）
           'resolve_secret', 'write_secret', 'resolve_vault_refs',
           'resolver_status',
           # 合并清单 / 删除（第 12 轮收尾：CLI/MCP 不再依赖私有 _v2_session）
           'list_secret_names', 'delete_secret']"""
assert old_all in s
s = s.replace(old_all, new_all, 1)

append = '''

# ── 合并清单 / 删除（公开 API；CLI/MCP 不再借私有 `_v2_session`）──────────
#
# 背景（第 12 轮收尾）：CLI/MCP 为了"v1+v2 合并清单"直接 import 了 resolver 的
# 私有 `_v2_session` 并调 v2 私有实例方法 —— 一旦 resolver 内部重构就断。这里
# 把两件事提升为公开 API，行为与调用方现有实现逐字段对齐（见验收脚本对比）。
#
# 只读保证：`list_secret_names` 走**只读 v2 会话**（不调用 v2.auth：auth 会写
# last_auth_at / used_codes / 审计；这里只 SELECT，PIN/锁定/机器指纹检查全部在
# 内存里做）——因此 keys.json 与 vault2.db 逐字节不变（审计日志仍会追加"读了什么"，
# 那是审计语义，不是数据变更；要在 vault2 里加真正的 read-only session API 属后续项）。

def _v2_readonly_session():
    """建立**只读** v2 会话（不写 DB）。返回 (vault, token, reason)。

    与 `vault2.auth()` 的检查项对齐（存在性 / 锁定 / PIN / 机器指纹 / seed 解码 /
    master_key 派生），但：
      * 不执行 `failed_attempts/locked_until/last_auth_at` 的 UPDATE（只读）；
      * 不写 used_codes（动态码防重放是"登录"语义，只读会话不做）；
      * 失败原因以可读字符串返回，由 `list_secret_names` 填进 `v2_reason`。
    """
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
        return None, None, 'v2 不可用（%s: %s）' % (type(exc).__name__, exc)
    try:
        with vault._db() as conn:
            row = conn.execute(
                "SELECT pin_hash, salt, seed_key, security_level, failed_attempts, "
                "locked_until, key_salt, key_protection, key_meta "
                "FROM identities WHERE id=?", (identity_id,)
            ).fetchone()
            if not row:
                return None, None, 'v2 身份不存在: %s' % identity_id
            (pin_hash_hex, salt_hex, seed_key_stored, level, _failed, locked,
             key_salt_hex, seed_protection, seed_meta) = row
            if locked and int(time.time()) < locked:
                return None, None, ('v2 账户已锁定，请 %d 秒后重试'
                                    % (locked - int(time.time())))
            expected_hash = hashlib.pbkdf2_hmac(
                'sha256', pin.encode('utf-8'), bytes.fromhex(salt_hex), 100000)
            if not hmac.compare_digest(expected_hash.hex(), pin_hash_hex):
                return None, None, 'PIN 错误'
            machine = conn.execute(
                "SELECT fingerprint FROM machines WHERE id=? AND identity_id=?",
                (machine_id, identity_id)).fetchone()
            if not machine:
                return None, None, 'v2 机器未注册: %s' % machine_id
            if machine[0] != vault._machine_fingerprint():
                return None, None, 'v2 机器指纹不匹配'
        seed_key_hex = vault._decode_seed_hex(
            identity_id, seed_key_stored, seed_protection, seed_meta)
        dynamic_code = ''
        if level != 'L1':
            dynamic_code = v2.generate_dynamic_code(
                bytes.fromhex(seed_key_hex), v2.DEFAULT_TIME_STEP)
        if key_salt_hex:
            master_key = v2.derive_master_key(seed_key_hex, dynamic_code,
                                              bytes.fromhex(key_salt_hex))
        else:                                  # 旧身份（无 key_salt）：与 auth 同口径
            master_key = v2.derive_master_key(pin, dynamic_code,
                                              bytes.fromhex(salt_hex))
    except Exception as exc:  # noqa: BLE001
        return None, None, 'v2 只读会话建立失败（%s: %s）' % (type(exc).__name__, exc)
    token = 'readonly-' + secrets.token_hex(8)
    ttl = v2.SESSION_TTL.get(level, 600)
    vault._sessions[token] = {
        'identity_id': identity_id,
        'machine_id': machine_id,
        'security_level': level,
        'expires_at': int(time.time()) + ttl,
        'master_key': master_key,
    }
    return vault, token, None


def _v2_readonly_names():
    """只读列出 v2 密钥名。返回 (names, available, reason)。"""
    vault, token, reason = _v2_readonly_session()
    if reason:
        return [], False, reason
    try:
        result = vault.list_secrets(token)
    except Exception as exc:  # noqa: BLE001
        return [], False, 'v2 列举异常（%s: %s）' % (type(exc).__name__, exc)
    if result.get('status') != 'ok':
        return [], False, str(result.get('message') or 'v2 列举失败')
    return [item.get('name') for item in (result.get('secrets') or [])], True, None


def _v2_readonly_value(name: str):
    """只读取 v2 密钥值；失败返回 (state, value, reason)。"""
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
    return 'error', None, 'v2 读取失败：%s' % message


def list_secret_names(scope: str = 'global', meta_dir: Optional[str] = None) -> dict:
    """**合并清单（v1 + v2）**，只读、不写任何数据文件。

    每条：
        {'key', 'scope', 'source': 'v1'|'v2'|'v2+v1'|'v1+v2',
         'conflict': bool, 'in_v1': bool, 'in_v2': bool}

    顶层诊断：`v2_available` / `v2_reason` / `v1_error`（与 CLI 现有
    `_list_secrets_merged` 的返回体逐字段一致，便于无行为差异切换）。

    `source` 口径与 `resolve_secret` 一致：两边都有且值相同 → `v2+v1`；
    值不同 → `v1+v2` + `conflict=True`（**不静默挑一个**）。
    值比对用明文（只是不落盘）；v2 不可用不抛错，返回 v1 部分 + `v2_available=False`。
    """
    scope = scope or 'global'
    v1_names: list = []
    v1_error = None
    v1_vault = None
    try:
        v1_vault = Vault(meta_dir or default_meta_dir())
        v1_names = [row.get('key') for row in v1_vault.list(scope)]
    except Exception as exc:  # noqa: BLE001
        v1_error = 'v1 列举异常（%s: %s）' % (type(exc).__name__, exc)
    v2_names, v2_available, v2_reason = _v2_readonly_names()
    names = sorted(set(n for n in v1_names if n) | set(n for n in v2_names if n))
    rows = []
    for name in names:
        in_v1 = name in v1_names
        in_v2 = name in v2_names
        conflict = False
        if in_v1 and in_v2:
            v1_value = v1_vault.get(name, scope, _allow_v2_fallback=False) if v1_vault else None
            state, v2_value, _reason = _v2_readonly_value(name)
            if state == 'found' and v1_value is not None:
                conflict = str(v1_value) != str(v2_value)
        if in_v1 and in_v2:
            source = 'v1+v2' if conflict else 'v2+v1'
        else:
            source = 'v1' if in_v1 else 'v2'
        rows.append({'key': name, 'scope': scope, 'source': source,
                     'conflict': conflict, 'in_v1': in_v1, 'in_v2': in_v2})
    return {'status': 'ok', 'keys': rows, 'count': len(rows),
            'v2_available': v2_available, 'v2_reason': v2_reason,
            'v1_error': v1_error}


def delete_secret(name: str, scope: str = 'global', meta_dir: Optional[str] = None,
                  include_v1: bool = False, caller: str = None) -> dict:
    """**删除密钥**：默认只删 v2（resolver 的权威写入口与优先读源）。

    - `include_v1=True` 才会删旧库 v1 副本（**破坏性，必须显式**）；
    - v2 不可用 → `status='failed'` + `errors=[原因]` + `hint`（**不是静默 not_found**）；
    - 返回体同时给出 `deleted_v2` / `deleted_v1` / `not_found`（"删了几个/原本在不在"）。

    行为与 CLI 现有 `_delete_secret_merged` 对齐（字段为超集：多 `deleted_v2` /
    `not_found`；`hint` 用中性文案，调用方可按自己的 CLI 旗标覆写）。
    """
    raw = '' if name is None else str(name).strip()
    if raw.startswith('vault://'):
        raw = raw[len('vault://'):]
    scope = scope or 'global'
    removed: list = []
    errors: list = []
    v2, token, reason = _v2_session()
    if reason:
        errors.append('v2 不可用：%s' % reason)
    else:
        try:
            result = v2.delete_secret(token, raw, caller=caller or 'vault.resolver')
            if result.get('status') == 'ok':
                removed.append('v2')
            elif '凭证不存在' in str(result.get('message') or ''):
                pass                       # v2 里没有，不算错
            else:
                errors.append('v2 删除失败：%s' % result.get('message'))
        except Exception as exc:  # noqa: BLE001
            errors.append('v2 删除异常（%s: %s）' % (type(exc).__name__, exc))
    if include_v1:
        try:
            if Vault(meta_dir or default_meta_dir()).delete(raw, scope):
                removed.append('v1')
        except Exception as exc:  # noqa: BLE001
            errors.append('v1 删除异常（%s: %s）' % (type(exc).__name__, exc))
    status = 'ok' if removed else ('failed' if errors else 'not_found')
    payload = {'status': status, 'key': raw, 'scope': scope,
               'deleted': removed,
               'deleted_v2': 'v2' in removed,
               'deleted_v1': 'v1' in removed,
               'not_found': status == 'not_found',
               'errors': errors}
    if not include_v1:
        payload['hint'] = ('默认只删 v2（权威来源）；旧库 v1 若也有副本，'
                           '请显式 include_v1=True（破坏性）')
    return payload
'''

s = s.rstrip('\n') + '\n' + append
io.open(P, 'w', encoding='utf-8').write(s)
print('vault.py public API appended')
