# -*- coding: utf-8 -*-
"""第 12 轮：vault 统一 secret resolver（v2 优先 / v1 兼容读）+ executor 接线。"""
import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)


def patch(path, old, new, count=1):
    p = os.path.join(ROOT, path)
    s = io.open(p, encoding='utf-8').read()
    assert old in s, '%s 未匹配:\n%s' % (path, old[:300])
    s = s.replace(old, new, count)
    io.open(p, 'w', encoding='utf-8').write(s)
    print('patched:', path)


# ── 1) vault.py：__all__ + Vault 初始化/读取回退 + 统一 resolver ──────────
patch('vools/actus/vault.py',
"""__all__ = ['Vault', 'default_meta_dir', 'set_key', 'get_key', 'delete_key',
           'list_keys', 'resolve_secrets']""",
"""__all__ = ['Vault', 'default_meta_dir', 'set_key', 'get_key', 'delete_key',
           'list_keys', 'resolve_secrets',
           # 统一 secret resolver（第 12 轮：v2 优先 / v1 兼容读）
           'resolve_secret', 'write_secret', 'resolve_vault_refs',
           'resolver_status']""")

patch('vools/actus/vault.py',
"""        self._keys_data: Dict[str, Dict[str, str]] = self._load(self._keys_path)
        self._meta_data: Dict[str, Dict[str, dict]] = self._load(self._meta_path)""",
"""        self._keys_data: Dict[str, Dict[str, str]] = self._load(self._keys_path)
        self._meta_data: Dict[str, Dict[str, dict]] = self._load(self._meta_path)
        #: 最近一次 get() 的取值来源（'v1' / 'v2' / None）—— 供上层诊断"这份密钥
        #: 到底来自哪个库"（第 12 轮统一 resolver 的兼容读会填 'v2'）。
        self.last_read_source: Optional[str] = None
        #: 最近一次写操作被拒的原因（临时密钥守卫等）；None = 未被拒。
        self.last_refusal: Optional[dict] = None""")

patch('vools/actus/vault.py',
"""    def get(self, key: str, scope: str = 'global') -> Optional[str]:
        \"\"\"解密获取密钥。

        返回:
            密钥值，或 None（不存在）。
        \"\"\"
        encrypted = self._keys_data.get(scope, {}).get(key)
        if encrypted is None:
            return None
        try:
            return self._backend.decrypt(encrypted)
        except Exception:
            return None""",
"""    def get(self, key: str, scope: str = 'global',
            _allow_v2_fallback: bool = True) -> Optional[str]:
        \"\"\"解密获取密钥；v1 里没有时**兼容回退读 v2**（统一 resolver 的读侧）。

        返回:
            密钥值，或 None（两个库都没有）。

        第 12 轮统一 resolver 的兼容读：CLI `vault get` 走的仍是本方法，若只认 v1，
        "resolver 写进 v2 的新密钥"在 CLI 里就永远读不到（这边写、那边读不到）。
        因此 v1 缺失时按需尝试 v2（需要 `VAULT_IDENTITY_ID/MACHINE_ID/PIN` 且 v2
        可用；否则静默跳过，不报错）。`last_read_source` 记录来源。

        注意：**只回退读、不回退写** —— v1 的写入口保持原样（临时密钥守卫不变）。
        \"\"\"
        encrypted = self._keys_data.get(scope, {}).get(key)
        if encrypted is None:
            if _allow_v2_fallback and _resolver_enabled():
                state, value, _reason = _v2_read_secret(key)
                if state == 'found':
                    self.last_read_source = 'v2'
                    return value
            self.last_read_source = None
            return None
        try:
            value = self._backend.decrypt(encrypted)
            self.last_read_source = 'v1'
            return value
        except Exception:
            return None""")

# 在模块便捷函数之后追加统一 resolver 实现
append = '''

# ── 统一 secret resolver（第 12 轮：v2 优先 / v1 兼容读）────────────────
#
# 设计（docs/vault-v1-v2-merge.md §3）：
#   * **读**：先 v2（keyring/passphrase 保护、有审计/轮换），v2 不可用或没有该
#     密钥时回退 v1（老数据兼容）；两边都有但值不同 → **报 conflict，不自动选**。
#   * **写**：默认写 v2；v2 不可用时**拒绝**（除非显式 allow_v1_write=True），
#     绝不静默写进一个将来 resolver 读不到的地方。
#   * **懒迁移**：默认关闭（opt-in `ACTUS_VAULT_LAZY_MIGRATE=1`）。原因见 §3 报告：
#     本轮 CLI 仍直连 v1 写入，若读时自动把 v1 复制到 v2，CLI 之后再改 v1 的值就会
#     与 v2 的旧副本"不同" → 每次读都变冲突；等 CLI 也切到 resolver 后再打开默认迁移。
#   * v2 凭据口径与 executor 既有一致：VAULT_IDENTITY_ID / VAULT_MACHINE_ID / VAULT_PIN。

V2_IDENTITY_ENV = 'VAULT_IDENTITY_ID'
V2_MACHINE_ENV = 'VAULT_MACHINE_ID'
V2_PIN_ENV = 'VAULT_PIN'
RESOLVER_ENV = 'ACTUS_VAULT_RESOLVER'
LAZY_MIGRATE_ENV = 'ACTUS_VAULT_LAZY_MIGRATE'

_V2_SESSION_CACHE: Dict[str, Any] = {}
_V2_ERROR_CACHE: Dict[str, Any] = {}
_V2_SESSION_TTL = 300.0
_V2_ERROR_TTL = 30.0


def _resolver_enabled() -> bool:
    """统一 resolver 总开关（默认开；`ACTUS_VAULT_RESOLVER=0` 可关闭回退读）。"""
    return (os.environ.get(RESOLVER_ENV) or '1').strip().lower() not in ('0', 'false', 'no', 'off')


def _lazy_migrate_enabled() -> bool:
    return (os.environ.get(LAZY_MIGRATE_ENV) or '').strip().lower() in ('1', 'true', 'yes', 'on')


def _v2_credentials():
    return (os.environ.get(V2_IDENTITY_ENV), os.environ.get(V2_MACHINE_ENV),
            os.environ.get(V2_PIN_ENV))


def _v2_session(force: bool = False):
    """尝试建立 v2 会话。返回 (module, token, reason)；失败不抛。

    v2 不可用（未配置凭据 / 没有 keyring 或 passphrase / auth 失败）→
    (None, None, 可读原因)。调用方据此决定"回退 v1 读"或"拒绝写"。
    """
    creds = _v2_credentials()
    if not all(creds):
        return None, None, ('未配置 v2 凭据（%s / %s / %s），v2 读不可用'
                            % (V2_IDENTITY_ENV, V2_MACHINE_ENV, V2_PIN_ENV))
    now = time.time()
    cache = _V2_SESSION_CACHE
    if (not force and cache.get('creds') == creds and cache.get('token')
            and now - cache.get('ts', 0.0) < _V2_SESSION_TTL):
        return cache.get('module'), cache.get('token'), None
    err = _V2_ERROR_CACHE
    if (not force and err.get('creds') == creds and err.get('reason')
            and now - err.get('ts', 0.0) < _V2_ERROR_TTL):
        return None, None, err.get('reason')
    try:
        from . import vault2 as v2
        vault = v2._get_vault2()
        result = vault.auth(creds[0], creds[1], creds[2])
    except Exception as exc:  # noqa: BLE001 —— v2 不可用必须降级为可读原因
        reason = 'v2 不可用（%s: %s）' % (type(exc).__name__, exc)
        _V2_ERROR_CACHE.update({'creds': creds, 'ts': now, 'reason': reason})
        return None, None, reason
    if result.get('status') != 'ok':
        reason = 'v2 auth 失败：%s' % result.get('message')
        _V2_ERROR_CACHE.update({'creds': creds, 'ts': now, 'reason': reason})
        return None, None, reason
    token = result.get('session_token')
    cache.update({'creds': creds, 'token': token, 'module': v2, 'ts': now})
    _V2_ERROR_CACHE.update({'creds': None, 'ts': 0.0, 'reason': None})
    return v2, token, None


def _v2_read_secret(name: str):
    """读 v2 单个密钥。返回 (state, value, reason)。

    state ∈ {'found','absent','unavailable','error'}：
      * unavailable → 允许回退 v1 读（不是数据问题）；
      * error       → **不回退**（例如 v2 有该密钥但解密失败，隐藏它比报错更危险）。
    """
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
    return 'error', None, 'v2 读取失败：%s' % message


def _v1_read_secret(name: str, scope: str, meta_dir: Optional[str]):
    """读 v1 单个密钥。返回 (state, value, reason)；区分 absent / undecryptable。"""
    try:
        vault = Vault(meta_dir or default_meta_dir())
    except Exception as exc:  # noqa: BLE001
        return 'error', None, 'v1 打开失败（%s: %s）' % (type(exc).__name__, exc)
    status = vault.inspect(name, scope)
    if status == 'absent':
        return 'absent', None, None
    if status == 'undecryptable':
        return 'error', None, ('v1 中存在 %r 但当前 ACTUS_VAULT_KEY 解不开'
                               '（请配置正确主密钥，而不是把它当"不存在"）' % name)
    value = vault.get(name, scope, _allow_v2_fallback=False)
    if value is None:
        return 'absent', None, None
    return 'found', value, None


def _secret_fingerprint(value: str) -> str:
    """值的短指纹（冲突报错用；不打印明文，避免日志泄露密钥）。"""
    return hashlib.sha256(str(value).encode('utf-8')).hexdigest()[:12]


def resolve_secret(name: str, scope: str = 'global',
                   meta_dir: Optional[str] = None,
                   lazy_migrate: Optional[bool] = None) -> dict:
    """**统一 secret resolver**：读一个密钥（v2 优先，v1 兼容回退）。

    返回:
        {'status': 'ok'|'not_found'|'conflict'|'error',
         'name': ..., 'value': ..., 'source': 'v2'|'v1'|'v2+v1',
         'warnings': [...], 'migrated': bool, ...}

    规则（lead 裁决）：
      * v2 有 → 用它；v1 也有且相同 → source='v2+v1'；**不同 → conflict（不自动选）**；
      * v2 不可用/没有 → 回退 v1 读（数据在，读不能丢），并给 warning 说明；
      * 都没有 → not_found（附 v2 不可用原因，便于排查）；
      * v2 读出错（如密钥存在但解不开）→ error，**不回退**（避免把"坏了"伪装成"没有"）；
      * 懒迁移 opt-in：`lazy_migrate=True` 或 `ACTUS_VAULT_LAZY_MIGRATE=1` 时，
        读到 v1 的密钥会复制到 v2（失败只 warning，不影响本次读取）。
    """
    raw = '' if name is None else str(name).strip()
    if raw.startswith('vault://'):
        raw = raw[len('vault://'):]
    if not raw:
        return {'status': 'error', 'code': 'param_invalid',
                'message': '密钥名不能为空', 'name': raw}

    v2_state, v2_value, v2_reason = _v2_read_secret(raw)
    v1_state, v1_value, v1_reason = _v1_read_secret(raw, scope, meta_dir)
    warnings: list = []

    if v2_state == 'error':
        return {'status': 'error', 'code': 'v2_read_failed', 'name': raw,
                'source': 'v2', 'message': v2_reason}
    if v1_state == 'error':
        return {'status': 'error', 'code': 'v1_read_failed', 'name': raw,
                'source': 'v1', 'message': v1_reason}

    if v2_state == 'found' and v1_state == 'found':
        if str(v2_value) == str(v1_value):
            return {'status': 'ok', 'name': raw, 'value': v2_value,
                    'source': 'v2+v1', 'warnings': ['两个库值一致（以 v2 为准）'],
                    'migrated': False}
        return {
            'status': 'conflict', 'code': 'vault_secret_conflict', 'name': raw,
            'source': 'v1+v2',
            'message': ('v1 与 v2 都存在密钥 %r 但**值不同**（v1 指纹 %s…，v2 指纹 %s…）；'
                        'resolver 不自动选择，请人工确认保留哪个（删除其中一个或人工改齐）'
                        % (raw, _secret_fingerprint(v1_value), _secret_fingerprint(v2_value))),
            'conflicts': [{'name': raw, 'v1_fingerprint': _secret_fingerprint(v1_value),
                           'v2_fingerprint': _secret_fingerprint(v2_value)}],
        }

    if v2_state == 'found':
        return {'status': 'ok', 'name': raw, 'value': v2_value, 'source': 'v2',
                'warnings': warnings, 'migrated': False}

    if v1_state == 'found':
        if v2_state == 'unavailable':
            warnings.append('v2 不可用，本次回退读取旧库 v1：%s' % v2_reason)
        else:
            warnings.append('该密钥只在旧库 v1 中（v2 没有），已兼容读取；'
                            '建议迁移（见 docs/vault-v1-v2-merge.md）')
        migrated = False
        do_migrate = _lazy_migrate_enabled() if lazy_migrate is None else bool(lazy_migrate)
        if do_migrate and v2_state != 'unavailable':
            migrated, migrate_reason = _migrate_to_v2(raw, v1_value)
            if migrated:
                warnings.append('已懒迁移到 v2（%r）' % raw)
            elif migrate_reason:
                warnings.append('懒迁移失败（本次仍返回 v1 值）：%s' % migrate_reason)
        return {'status': 'ok', 'name': raw, 'value': v1_value, 'source': 'v1',
                'warnings': warnings, 'migrated': migrated}

    message = '密钥不存在: %r（v1 与 v2 都没有）' % raw
    if v2_state == 'unavailable':
        message += '；v2 不可用：%s' % v2_reason
    return {'status': 'not_found', 'code': 'secret_not_found', 'name': raw,
            'message': message, 'warnings': warnings}


def _migrate_to_v2(name: str, value: str):
    """把 v1 里的密钥复制到 v2（懒迁移）。返回 (ok, reason)。"""
    v2, token, reason = _v2_session()
    if reason:
        return False, reason
    try:
        result = v2.set_secret(token, name, str(value), caller='vault.resolver')
    except Exception as exc:  # noqa: BLE001
        return False, 'v2 写入异常（%s: %s）' % (type(exc).__name__, exc)
    if result.get('status') != 'ok':
        return False, 'v2 写入失败：%s' % result.get('message')
    return True, None


def write_secret(name: str, value: str, scope: str = 'global',
                 meta_dir: Optional[str] = None,
                 allow_v1_write: bool = False) -> dict:
    """**统一 secret resolver**：写一个密钥（默认写 v2）。

    失败模式（lead 硬要求：写不能落到将来读不到的地方）：
      * v2 可用 → 写 v2；若 v1 已有同名且**值不同** → 返回 conflict（避免制造分歧），
        若相同 → 覆盖 v2 并提示；
      * v2 **不可用** → 默认**拒绝**（code='vault2_unavailable'）。只有调用方显式
        `allow_v1_write=True` 时才写 v1（并在返回值里 warning 说明"眼下只能写 v1"）。
    """
    raw = '' if name is None else str(name).strip()
    if raw.startswith('vault://'):
        raw = raw[len('vault://'):]
    if not raw:
        return {'status': 'error', 'code': 'param_invalid', 'message': '密钥名不能为空'}
    if value is None:
        return {'status': 'error', 'code': 'param_invalid', 'message': '密钥值不能为空'}

    v1_state, v1_value, _v1_reason = _v1_read_secret(raw, scope, meta_dir)
    v2_state, _v2_value, v2_reason = _v2_read_secret(raw)

    if v2_state == 'error':
        return {'status': 'error', 'code': 'v2_read_failed', 'message': _v2_value or '',
                'source': 'v2'}

    if v2_state == 'found':
        if v1_state == 'found' and str(v1_value) != str(value):
            return {'status': 'conflict', 'code': 'vault_secret_conflict', 'name': raw,
                    'message': ('v1 中已有 %r 且与本次要写的值不同（v1 指纹 %s…）；'
                                '直接写 v2 会制造双库分歧，请先人工确认'
                                % (raw, _secret_fingerprint(v1_value)))}
        v2, token, reason = _v2_session()
        if reason:
            return {'status': 'refused', 'code': 'vault2_unavailable', 'name': raw,
                    'message': 'v2 不可用，拒绝写入：%s' % reason}
        try:
            result = v2.set_secret(token, raw, str(value), caller='vault.resolver')
        except Exception as exc:  # noqa: BLE001
            return {'status': 'error', 'code': 'v2_write_failed', 'name': raw,
                    'message': 'v2 写入异常（%s: %s）' % (type(exc).__name__, exc)}
        if result.get('status') != 'ok':
            return {'status': 'error', 'code': 'v2_write_failed', 'name': raw,
                    'message': 'v2 写入失败：%s' % result.get('message')}
        warnings = []
        if v1_state == 'found':
            warnings.append('v1 中已有同名密钥且值相同；已更新 v2（v1 未改动）')
        return {'status': 'ok', 'name': raw, 'source': 'v2', 'warnings': warnings}

    # v2 不可用或没有该密钥：v2 不可用时默认拒绝
    if v2_state == 'unavailable':
        if not allow_v1_write:
            return {'status': 'refused', 'code': 'vault2_unavailable', 'name': raw,
                    'message': ('v2 不可用（%s），拒绝写入 —— 避免写进一个 resolver '
                                '将来读不到的地方；如确需只写 v1，请显式 allow_v1_write=True'
                                % v2_reason)}
        vault = Vault(meta_dir or default_meta_dir())
        result = vault.set(raw, str(value), scope)
        if result.get('status') != 'ok':
            result.setdefault('warnings', []).append('v2 不可用，本次写入的是 v1')
            return result
        return {'status': 'ok', 'name': raw, 'source': 'v1',
                'warnings': ['v2 不可用（%s）：本次按显式 allow_v1_write 写入了 v1'
                             % v2_reason]}

    # v2 可用但当前没有该密钥：写 v2
    v2, token, reason = _v2_session()
    if reason:
        return {'status': 'refused', 'code': 'vault2_unavailable', 'name': raw,
                'message': 'v2 不可用，拒绝写入：%s' % reason}
    try:
        result = v2.set_secret(token, raw, str(value), caller='vault.resolver')
    except Exception as exc:  # noqa: BLE001
        return {'status': 'error', 'code': 'v2_write_failed', 'name': raw,
                'message': 'v2 写入异常（%s: %s）' % (type(exc).__name__, exc)}
    if result.get('status') != 'ok':
        return {'status': 'error', 'code': 'v2_write_failed', 'name': raw,
                'message': 'v2 写入失败：%s' % result.get('message')}
    return {'status': 'ok', 'name': raw, 'source': 'v2', 'warnings': []}


def resolve_vault_refs(secrets_config: List[dict], meta_dir: str = '') -> dict:
    """批量解析动作的 `vault://` 引用（executor 注入 secrets 用）。

    Returns:
        {'status': 'ok'|'conflict'|'error', 'resolved': {env: value},
         'missing': [...], 'conflicts': [...], 'warnings': [...]}

    冲突/错误**不吞**：status 由调用方决定怎么处理（executor 会显式拒绝执行），
    绝不静默挑一个值。
    """
    resolved: Dict[str, str] = {}
    missing: List[str] = []
    conflicts: List[dict] = []
    errors: List[dict] = []
    warnings: List[str] = []
    for item in secrets_config or []:
        if not isinstance(item, dict):
            continue
        env_name = item.get('env')
        key_ref = str(item.get('key') or '')
        default = item.get('default')
        if not key_ref.startswith('vault://'):
            if env_name and default is not None:
                resolved[env_name] = default
            continue
        result = resolve_secret(key_ref, meta_dir=meta_dir or None)
        state = result.get('status')
        if state == 'ok':
            if env_name and result.get('value'):
                resolved[env_name] = result.get('value')
            warnings.extend(result.get('warnings') or [])
        elif state == 'conflict':
            conflicts.append(result)
        elif state == 'error':
            errors.append(result)
        elif default is not None:
            if env_name:
                resolved[env_name] = default
        else:
            missing.append(key_ref)
    if conflicts:
        return {'status': 'conflict', 'code': 'vault_secret_conflict',
                'resolved': resolved, 'missing': missing,
                'conflicts': conflicts, 'warnings': warnings,
                'message': '有 %d 个密钥在 v1/v2 中值不同，拒绝自动选择' % len(conflicts)}
    if errors:
        return {'status': 'error', 'code': 'vault_read_failed',
                'resolved': resolved, 'missing': missing, 'errors': errors,
                'warnings': warnings,
                'message': '有 %d 个密钥读取失败' % len(errors)}
    return {'status': 'ok', 'resolved': resolved, 'missing': missing,
            'warnings': warnings}


def resolver_status() -> dict:
    """resolver 自检：v2 是否可用、v1 路径、懒迁移开关（诊断用）。"""
    v2, token, reason = _v2_session()
    return {
        'enabled': _resolver_enabled(),
        'v2_available': v2 is not None,
        'v2_reason': reason,
        'v1_path': os.path.join(default_meta_dir(), 'vault'),
        'lazy_migrate': _lazy_migrate_enabled(),
    }
'''

p = os.path.join(ROOT, 'vools/actus/vault.py')
s = io.open(p, encoding='utf-8').read()
s = s.rstrip('\n') + '\n' + append
io.open(p, 'w', encoding='utf-8').write(s)
print('appended resolver to vault.py')

# ── 2) executor：vault:// 走统一 resolver，冲突/缺失显式报错 ──────────
P = os.path.join(ROOT, 'vools/actus/executor.py')
s = io.open(P, encoding='utf-8').read()
old = '''    try:
        vault_refs = [
            s for s in secrets_config
            if str(s.get('key', s.get('env', ''))).startswith('vault://')
        ]
        if vault_refs:
            from . import vault2 as vault2_mod
            identity_id = os.environ.get('VAULT_IDENTITY_ID')
            machine_id = os.environ.get('VAULT_MACHINE_ID')
            pin = os.environ.get('VAULT_PIN')
            if identity_id and machine_id and pin:
                auth_result = vault2_mod.auth(identity_id, machine_id, pin)
                if auth_result.get('status') == 'ok':
                    token = auth_result['session_token']
                    resolve_result = vault2_mod.resolve_vault_refs(token, vault_refs)
                    if resolve_result.get('status') == 'ok':
                        for env_name, env_value in resolve_result.get('resolved', {}).items():
                            if env_value:
                                os.environ[env_name] = env_value
    except Exception:
        pass
'''
new = '''    # ── vault:// 引用：统一 secret resolver（第 12 轮：v2 优先 / v1 兼容读）──
    # 旧实现分两段：v1 `resolve_secrets`（不认 vault://）+ 仅当 VAULT_* 凭据齐全时
    # 直接调 vault2；且整段包在 `except: pass` 里 —— 凭据缺失/库切换时 vault:// 引用
    # 静默不解析。现在统一走 resolver：v2 优先、回退 v1；**冲突/读取失败显式拒绝执行**
    # （不静默挑一个值，也不静默跳过）。
    vault_refs = [
        s for s in secrets_config
        if str(s.get('key', s.get('env', ''))).startswith('vault://')
    ]
    if vault_refs:
        resolved = vault_mod.resolve_vault_refs(vault_refs, meta_dir=meta_dir or '')
        if resolved.get('status') == 'conflict':
            raise ActionError(
                'vault_secret_conflict',
                '密钥冲突，拒绝执行：%s（请人工确认保留 v1 还是 v2 的值）'
                % resolved.get('message'),
                {'conflicts': resolved.get('conflicts') or []})
        if resolved.get('status') == 'error':
            raise ActionError(
                'vault_read_failed',
                '密钥读取失败，拒绝执行：%s' % resolved.get('message'),
                {'errors': resolved.get('errors') or []})
        for env_name, env_value in (resolved.get('resolved') or {}).items():
            if env_value:
                os.environ[env_name] = env_value
'''
assert old in s
s = s.replace(old, new, 1)
io.open(P, 'w', encoding='utf-8').write(s)
print('patched: executor.py vault:// -> resolver')

# ── 3) docs：第 3 步标记为已实施 ─────────────────────────────
p = os.path.join(ROOT, 'docs/vault-v1-v2-merge.md')
s = io.open(p, encoding='utf-8').read()
s = s.replace('# vault v1 / v2 现状与合并建议\n\n> 第 10 轮审计产出（`cmd-polish`），供决策用；**未改动任何 vault 代码**。',
"""# vault v1 / v2 现状与合并建议

> 第 10 轮审计产出（`cmd-polish`）；**第 12 轮已实施第 3 步（统一 secret resolver）**，
> 实施细节见文末 §6。

## 0. 第 3 步实施记录（第 12 轮，2026-10-29）

已在 `vault.py` 落地统一 resolver（无新模块）：
`resolve_secret(name, scope, meta_dir, lazy_migrate=None)` /
`write_secret(...)` / `resolve_vault_refs(config, meta_dir)` / `resolver_status()`。

- **读**：v2 优先（凭据 `VAULT_IDENTITY_ID/VAULT_MACHINE_ID/VAULT_PIN`，与 executor 旧口径一致）；
  v2 不可用或没有该密钥 → 回退 v1（`Vault.last_read_source` 记来源）；
  **两边都有且值不同 → `status='conflict'`，不自动选择**（消息里给两个值的 sha256 短指纹，
  不打印明文）。
- **写**：默认写 v2；v2 不可用 → **拒绝**（`code='vault2_unavailable'`），
  仅显式 `allow_v1_write=True` 才写 v1 并 warning（避免"写到 resolver 将来读不到的地方"）。
- **懒迁移**：**默认关闭**，opt-in `ACTUS_VAULT_LAZY_MIGRATE=1`。原因：本轮 CLI 仍直连 v1
  写入（`cli.py` 在并行改动，禁改），若读时自动把 v1 复制到 v2，CLI 之后再改 v1 的值
  就会与 v2 旧副本"值不同" → 每次读都变冲突。等 CLI 切到 resolver（下一步）后再打开默认迁移。
- **executor 的 `vault://`** 已改走 resolver：冲突/读取失败 → `ActionError`
  （`vault_secret_conflict` / `vault_read_failed`）显式拒绝执行，不再静默跳过。
- **CLI 兼容读**：v1 `Vault.get()` 在 v1 缺失时按需回退读 v2（`ACTUS_VAULT_RESOLVER=0` 可关），
  因此 resolver/v2 写入的密钥，现有 `actus vault get` 也能读到 —— **CLI 写入路径不变**，
  切换 CLI 写入口（让它也写 v2）仍需 cmd-engine 协调（`cli.py` 禁改）。
""")
io.open(p, 'w', encoding='utf-8').write(s)
print('docs updated')
print('done')
