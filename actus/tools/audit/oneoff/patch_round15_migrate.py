# -*- coding: utf-8 -*-
"""第 15 轮：vault migrate CLI + MCP（薄包装 + 入口）。"""
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


# ═══════ 1) vault.py：薄包装 migrate_legacy_secrets（dry-run 只读）═══════
patch('vools/actus/vault.py',
"""           # 合并清单 / 删除（第 12 轮收尾：CLI/MCP 不再依赖私有 _v2_session）
           'list_secret_names', 'delete_secret']""",
"""           # 合并清单 / 删除（第 12 轮收尾：CLI/MCP 不再依赖私有 _v2_session）
           'list_secret_names', 'delete_secret',
           # 显式迁移 legacy 行（第 15 轮：读路径不迁移，迁移只能显式触发）
           'migrate_legacy_secrets']""")

append = '''

# ── 显式迁移 legacy 行（第 15 轮：读路径绝不迁移，迁移只能显式触发）────────
def _legacy_secret_names(vault, token) -> list:
    """只读列出当前身份下 legacy 行（`key_salt IS NULL`）的名字。"""
    session = (getattr(vault, '_sessions', None) or {}).get(token) or {}
    identity_id = session.get('identity_id')
    if not identity_id:
        return []
    with vault._db() as conn:
        return [row[0] for row in conn.execute(
            "SELECT name FROM secrets WHERE identity_id=? AND key_salt IS NULL",
            (identity_id,)).fetchall()]


def migrate_legacy_secrets(dry_run: bool = False, meta_dir: Optional[str] = None,
                           scope: str = 'global') -> dict:
    """**显式**把 v2 legacy 行（key_salt 为空）迁移为行级加密。

    `dry_run=True`：只读会话 + COUNT 查询，**不写 db、不写 audit.log**，返回
    `checked`（待迁移条数）供先看后迁；`dry_run=False` 才真正迁移（写 db）。

    返回（扁平，CLI `--json` 与 MCP 共用）：
        {status, checked, migrated, failed, failed_names[], dry_run, scope}
        status: ok | partial（有失败）| refused（无 v2 凭据）| param_invalid

    失败条目不静默：`failed_names` + `failed_details`。
    """
    scope = scope or 'global'
    base = {'status': 'ok', 'checked': 0, 'migrated': 0, 'failed': 0,
            'failed_names': [], 'dry_run': bool(dry_run), 'scope': scope}
    if scope not in ('global', 'project'):
        return dict(base, status='param_invalid',
                    message='scope 只能是 global 或 project')
    if dry_run:
        vault, token, reason = _v2_readonly_session()
        if reason:
            return dict(base, status='refused', code='vault2_unavailable',
                        message='v2 不可用：%s' % reason,
                        hint=('配置 VAULT_IDENTITY_ID / VAULT_MACHINE_ID / '
                              'VAULT_PIN 后再迁移'))
        names = _legacy_secret_names(vault, token)
        return dict(base, status='ok', checked=len(names), legacy_names=names)
    v2, token, reason = _v2_session()
    if reason:
        return dict(base, status='refused', code='vault2_unavailable',
                    message='v2 不可用：%s' % reason,
                    hint=('配置 VAULT_IDENTITY_ID / VAULT_MACHINE_ID / '
                          'VAULT_PIN 后再迁移'))
    try:
        result = v2.migrate_legacy_rows(token)
    except Exception as exc:  # noqa: BLE001
        return dict(base, status='error', code='vault_migrate_failed',
                    message='迁移异常（%s: %s）' % (type(exc).__name__, exc))
    if result.get('status') != 'ok':
        return dict(base, status='error',
                    message=result.get('message') or '迁移失败')
    failed_details = result.get('failed') or []
    failed_names = [item.get('name') for item in failed_details if item.get('name')]
    out = dict(base,
               checked=result.get('checked', 0),
               migrated=result.get('migrated', 0),
               failed=len(failed_details),
               failed_names=failed_names,
               failed_details=failed_details)
    if out['failed'] > 0:
        out['status'] = 'partial'
        out['message'] = ('%d 条迁移失败（见 failed_names），其余已迁移'
                          % out['failed'])
    return out
'''

p = os.path.join(ROOT, 'vools/actus/vault.py')
s = io.open(p, encoding='utf-8').read().rstrip('\n') + '\n' + append
io.open(p, 'w', encoding='utf-8').write(s)
print('vault.py migrate_legacy_secrets added')

# ═══════ 2) cli.py：vault migrate 子命令 ═══════
patch('vools/actus/cli.py',
"""    p_vault_delete.add_argument('--all', action='store_true',
                                help='同时删除旧库 v1 的副本（**破坏性**：默认只删 v2）')""",
"""    p_vault_delete.add_argument('--all', action='store_true',
                                help='同时删除旧库 v1 的副本（**破坏性**：默认只删 v2）')

    p_vault_migrate = vault_sub.add_parser(
        'migrate', help='迁移旧格式（legacy）vault 密钥行到行级加密')
    p_vault_migrate.add_argument('--scope', default='global',
                                 choices=['global', 'project'],
                                 help='作用域（v2 按身份迁移；--scope 仅兼容保留）')
    p_vault_migrate.add_argument('--dry-run', dest='dry_run', action='store_true',
                                 help='只统计待迁移条数，**不写任何数据/审计**（先看后迁）')
    p_vault_migrate.add_argument('--all', action='store_true',
                                 help='迁移当前身份全部 legacy 行（默认即全部；保留兼容）')""")

patch('vools/actus/cli.py',
"""    if args.vault_command == 'delete':""",
"""    if args.vault_command == 'migrate':
        from vools.actus.vault import migrate_legacy_secrets
        r = migrate_legacy_secrets(
            dry_run=bool(getattr(args, 'dry_run', False)),
            meta_dir=meta_dir,
            scope=getattr(args, 'scope', 'global'))
        if r.get('status') == 'refused' and r.get('code') == 'vault2_unavailable':
            # 可行动提示（硬要求）：告诉用户缺什么、怎么补
            r = dict(r)
            r['hint'] = ('配置 v2 凭据（VAULT_IDENTITY_ID / VAULT_MACHINE_ID / '
                         'VAULT_PIN）后再运行；也可先用 --dry-run 查看待迁移条数'
                         '（dry-run 不需要写权限）')
        # 统一走 _out_result：partial/refused/error 都映射为非 0
        return _out_result(r)

    if args.vault_command == 'delete':""")

# ═══════ 3) mcp_server.py：actus_vault_migrate 工具 + handler ═══════
patch('vools/actus/mcp_server.py',
"""            {'name': 'actus_vault_delete',
             'description': '删除密钥：从保险库中移除指定密钥',
             'inputSchema': {'type': 'object', 'required': ['key'],
                             'properties': {
                                 'key': {'type': 'string',
                                         'description': '密钥名称'},
                                 'scope': {'type': 'string',
                                           'description': '作用域（默认 global）'},
                             }}},""",
"""            {'name': 'actus_vault_delete',
             'description': '删除密钥：从保险库中移除指定密钥',
             'inputSchema': {'type': 'object', 'required': ['key'],
                             'properties': {
                                 'key': {'type': 'string',
                                         'description': '密钥名称'},
                                 'scope': {'type': 'string',
                                           'description': '作用域（默认 global）'},
                             }}},
            {'name': 'actus_vault_migrate',
             'description': ('显式迁移旧格式（legacy）vault 密钥行到行级加密。'
                             'dry_run=true 只统计（零写，建议先预览）；'
                             '真迁移写 db。读路径**绝不**自动迁移。'),
             'inputSchema': {'type': 'object',
                             'properties': {
                                 'dry_run': {'type': 'boolean',
                                             'description': '只统计不写（默认 false）'},
                                 'scope': {'type': 'string',
                                           'enum': ['global', 'project'],
                                           'description': '作用域（v2 按身份迁移，'
                                                          '仅兼容保留）'},
                                 'all': {'type': 'boolean',
                                         'description': '迁移当前身份全部 legacy 行'
                                                        '（默认即全部，保留兼容）'},
                             }}},""")

patch('vools/actus/mcp_server.py',
"""        if name == 'actus_runtimes':""",
"""        if name == 'actus_vault_migrate':
            # 第 15 轮：显式迁移 legacy 行（dry_run 零写；读路径不迁移）
            from vools.actus.vault import migrate_legacy_secrets
            from vools.actus.paths import meta_dir as _paths_meta_dir
            try:
                r = migrate_legacy_secrets(
                    dry_run=bool(args.get('dry_run', False)),
                    meta_dir=_paths_meta_dir(),
                    scope=args.get('scope') or 'global')
                if r.get('status') == 'refused':
                    r = dict(r)
                    r['hint'] = ('配置 v2 凭据（VAULT_IDENTITY_ID / VAULT_MACHINE_ID / '
                                 'VAULT_PIN）后再迁移；dry_run=true 不需要写权限')
                # text_result 默认按 status 判 isError：partial/refused/error → True
                return text_result(r)
            except Exception as e:
                return text_result({'status': 'failed', 'error': {
                    'code': 'vault_error', 'message': str(e)}}, True)

        if name == 'actus_runtimes':""")

print('done')
