"""`actus vault rotate-kek` / `actus_vault_rotate_kek` 入口验收（全 tmp 隔离，**单进程**）。

1) 无 `--yes`（非干跑）→ rc=1 + 警告 + **未执行**
2) `--yes` 各模式 → rc=0 + 字段齐全 + warnings 可见（JSON 体）
3) `--dry-run` 三模式 → **三件套零写**：db(sha256+mtime) / keyring 条目数 / 目录文件数
4) MCP `confirm=false` → confirmation_required；`dry_run=true` 不需 confirm；`confirm=true` → ok
5) `--mode` 与库实际不符 → mode_mismatch（切换保护方式不是轮换）

⚠️ 为什么**单进程**而不是 subprocess：每次 CLI 子进程都会重新 auth，而 TOTP 在同一个
60s 窗口内只能用一次（防重放）—— 连跑两条 CLI 命令必然"动态码已被使用"。
测试里用 `cli.main()` 同进程调用 + 会话缓存，并在需要时推进窗口。
"""
import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile

BASE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

RESULTS = []


def check(label, ok, detail=''):
    RESULTS.append((label, ok))
    print('%s %s%s' % ('PASS' if ok else 'FAIL', label, (': ' + detail) if detail else ''))


def shift_window(v2mod, otp, delta):
    """推进 TOTP 窗口（同进程）：让下一次 auth 用新的动态码。"""
    import types
    saved = (v2mod.time, otp.time)
    for mod, real in ((v2mod, saved[0]), (otp, saved[1])):
        shim = types.SimpleNamespace()
        for attr in dir(real):
            if not attr.startswith('__'):
                try:
                    setattr(shim, attr, getattr(real, attr))
                except Exception:              # noqa: BLE001
                    pass
        shim.time = (lambda real=real: real.time() + delta)
        mod.time = shim
    return saved


def restore_window(v2mod, otp, saved):
    v2mod.time, otp.time = saved


def run_cli(cli, argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = cli.main(list(argv))
        except SystemExit as exc:
            rc = exc.code if exc.code is not None else 0
    stdout, stderr = out.getvalue(), err.getvalue()
    try:
        payload = json.loads(stdout)
    except Exception:                              # noqa: BLE001
        payload = {}
    return rc, payload, stderr, stdout


def setup(tag, mode):
    import importlib
    sandbox = tempfile.mkdtemp(prefix='kekentry-%s-' % tag)
    vdir = os.path.join(sandbox, 'vault2')
    os.environ['ACTUS_VAULT2_DIR'] = vdir
    os.environ['HOME'] = sandbox
    os.environ['USERPROFILE'] = sandbox
    for k in ('ACTUS_VAULT2_PASSPHRASE', 'ACTUS_VAULT2_KEY_PROTECTION',
              'VAULT_IDENTITY_ID', 'VAULT_MACHINE_ID', 'VAULT_PIN'):
        os.environ.pop(k, None)
    if mode == 'passphrase':
        os.environ['ACTUS_VAULT2_PASSPHRASE'] = 'unit-test-passphrase'
    elif mode == 'file-key':
        os.environ['ACTUS_VAULT2_KEY_PROTECTION'] = 'file-key'
    elif mode == 'keyring':
        os.environ['ACTUS_VAULT2_KEY_PROTECTION'] = 'keyring'

    import vools.actus.vault2 as v2mod
    import vools.security.otp as otp
    importlib.reload(v2mod)
    import vools.actus.cli as cli
    importlib.reload(cli)
    # keyring 模式注入替身（不碰真实 OS 凭据库）
    store = None
    if mode == 'keyring':
        sys.path.insert(0, os.path.join(BASE, 'tools', 'audit'))
        import fake_keyring as fk
        store = fk.FakeKeyring()
        v2mod.probe_keyring = lambda: (fk.FakeKeyringModule(store), 'ok')

    v = v2mod.Vault2()
    reg = v.register('kek-u', '123456', security_level='L2')
    auth = v.auth(reg['identity_id'], reg['machine_id'], '123456')
    v.set_secret(auth['session_token'], 'K', 'V')
    os.environ.update({'VAULT_IDENTITY_ID': reg['identity_id'],
                       'VAULT_MACHINE_ID': reg['machine_id'], 'VAULT_PIN': '123456'})
    return v2mod, otp, cli, v, store


def db_stat(vdir):
    db = os.path.join(vdir, 'vault2.db')
    st = os.stat(db)
    with open(db, 'rb') as f:
        return (hashlib.sha256(f.read()).hexdigest(), st.st_mtime_ns)


def dir_files(vdir):
    return sorted(os.listdir(vdir)) if os.path.isdir(vdir) else []


def run_mode(mode):
    v2mod, otp, cli, v, store = setup(mode, mode)
    vdir = os.environ['ACTUS_VAULT2_DIR']
    # 让 CLI 的 _v2_session 用新的 TOTP 窗口（注册/设值时那次 auth 已用掉当前码）
    saved = shift_window(v2mod, otp, 180)
    try:
        # ── 1) 无 --yes ──
        before = db_stat(vdir)
        rc, payload, stderr, stdout = run_cli(cli, ['vault', 'rotate-kek'])
        check('%s: 无 --yes → rc=1' % mode, rc == 1, 'rc=%d' % rc)
        check('%s: 无 --yes → 有警告' % mode, '破坏性' in (stderr + stdout), (stderr or stdout)[:40])
        check('%s: 无 --yes → **未执行**' % mode, db_stat(vdir) == before)

        # ── 3) --dry-run → 三件套零写 ──
        # ⚠️ 先 prime 一次 CLI 调用（auth 本身会写 used_codes / last_auth_at —— 那是**登录**，
        # 不是轮换）；否则会把 auth 的写算到 dry-run 头上。prime 之后会话命中缓存，不再 auth。
        run_cli(cli, ['vault', 'rotate-kek', '--dry-run', '--json'])
        files_before, db_before = dir_files(vdir), db_stat(vdir)
        kr_before = len(store.snapshot()) if store else None
        rc, payload, stderr, _ = run_cli(cli, ['vault', 'rotate-kek', '--dry-run', '--json'])
        body = payload.get('data') or payload
        files_after, db_after = dir_files(vdir), db_stat(vdir)
        kr_after = len(store.snapshot()) if store else None
        check('%s: --dry-run → rc=0' % mode, rc == 0, 'rc=%d %s' % (rc, str(body)[:60]))
        check('%s: --dry-run → dry_run=true' % mode, body.get('dry_run') is True)
        check('%s: --dry-run → would_* 统计' % mode,
              isinstance(body.get('would'), dict) and 'kek_gen' in body['would'],
              str(body.get('would'))[:60])
        check('%s: --dry-run → **db sha256+mtime 不变**' % mode, db_before == db_after)
        check('%s: --dry-run → **目录文件数不变**' % mode, files_before == files_after,
              '%d→%d' % (len(files_before), len(files_after)))
        if store is not None:
            check('%s: --dry-run → **keyring 条目数不变**' % mode, kr_before == kr_after,
                  '%s→%s' % (kr_before, kr_after))

        # ── 2) --yes（真执行）──
        rc, payload, stderr, _ = run_cli(cli, ['vault', 'rotate-kek', '--yes', '--json'])
        body = payload.get('data') or payload
        check('%s: --yes → rc=0' % mode, rc == 0, 'rc=%d %s' % (rc, str(body)[:60]))
        need = ('mode', 'kek_gen', 'kek_gen_old', 'envelope_rotated', 'gc', 'warnings')
        missing = [k for k in need if k not in body]
        check('%s: --yes → 字段齐全' % mode, not missing, 'missing=%s' % missing)
        check('%s: --yes → 代数 +1' % mode,
              body.get('kek_gen') == (body.get('kek_gen_old') or 0) + 1,
              '%s→%s' % (body.get('kek_gen_old'), body.get('kek_gen')))

        # ── 5) mode 不符 ──
        wrong = {'passphrase': 'keyring', 'file-key': 'passphrase',
                 'keyring': 'file-key'}[mode]
        rc, payload, _e, _o = run_cli(cli, ['vault', 'rotate-kek', '--yes',
                                            '--mode', wrong, '--json'])
        body2 = payload.get('data') or payload
        check('%s: mode 不符 → mode_mismatch' % mode, body2.get('code') == 'mode_mismatch',
              str(body2.get('code')))
    finally:
        restore_window(v2mod, otp, saved)
    return v2mod, cli, v, store


def run_mcp(cli_module_env):
    v2mod, cli, v, store = cli_module_env
    import io as _io
    from vools.actus.mcp_server import MCPServer
    srv = MCPServer(stdin=_io.StringIO(), stdout=_io.StringIO())

    def call(args):
        r = srv._call_tool({'name': 'actus_vault_rotate_kek', 'arguments': args})
        return r['isError'], json.loads(r['content'][0]['text'])

    err1, p1 = call({'confirm': False})
    check('MCP confirm=false → isError + confirmation_required',
          err1 is True and ((p1.get('error') or {}).get('code') == 'confirmation_required'),
          str((p1.get('error') or {}).get('code')))
    err2, p2 = call({'confirm': False, 'dry_run': True})
    check('MCP dry_run=true 不需 confirm → 成功且 dry_run',
          err2 is False and p2.get('dry_run') is True, str(p2.get('status')))
    err3, p3 = call({'confirm': True})
    check('MCP confirm=true → isError=False + status=ok',
          err3 is False and p3.get('status') == 'ok', str(p3.get('status')))
    required = [t['inputSchema'].get('required', [])
                for t in srv._list_tools() if t['name'] == 'actus_vault_rotate_kek']
    check('MCP 工具已注册且 required=[confirm]', required == [['confirm']], str(required))


def main():
    for mode in ('passphrase', 'keyring', 'file-key'):
        state = run_mode(mode)
        if mode == 'passphrase':          # MCP 用同一套（passphrase 模式）
            run_mcp(state)

    print()
    failed = [l for l, ok in RESULTS if not ok]
    print('SUMMARY: %d passed, %d failed' % (len(RESULTS) - len(failed), len(failed)))
    for l in failed:
        print('  FAILED: ' + l)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
