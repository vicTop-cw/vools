"""`actus vault rotate-seed` / `actus_vault_rotate_seed` 入口验收（全 tmp 隔离）。

1) CLI 无 --yes → rc=1 + 警告，**不执行**（seed 未变）
2) CLI --yes   → rc=0，输出含全部字段，warnings 打到 stderr
3) MCP confirm=false → isError=True param_invalid
4) MCP confirm=true  → isError=False 且 status=ok（v2 可用时）
5) 两种入口都能看到 warnings（recovery_key_invalidated）
"""
import json
import os
import subprocess
import sys
import tempfile

BASE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

RESULTS = []


def check(label, ok, detail=''):
    RESULTS.append((label, ok))
    print('%s %s%s' % ('PASS' if ok else 'FAIL', label, (': ' + detail) if detail else ''))


def setup_env():
    sandbox = tempfile.mkdtemp(prefix='v2cli-')
    env = dict(os.environ)
    env.update({
        'ACTUS_VAULT2_DIR': os.path.join(sandbox, 'vault2'),
        'ACTUS_VAULT2_PASSPHRASE': 'unit-test-passphrase',
        'HOME': sandbox, 'USERPROFILE': sandbox,
        'PYTHONPATH': BASE, 'PYTHONIOENCODING': 'utf-8',
    })
    reg_code = (
        'import json\n'
        'from vools.actus import vault2\n'
        'v = vault2._get_vault2()\n'
        'r = v.register("cli-user", "123456", security_level="L2")\n'
        'print(json.dumps({"identity": r["identity_id"], "machine": r["machine_id"]}))\n')
    out = subprocess.run([sys.executable, '-c', reg_code], env=env, cwd=BASE,
                         capture_output=True, text=True, encoding='utf-8', errors='replace')
    info = json.loads(out.stdout.strip().splitlines()[-1])
    env.update({'VAULT_IDENTITY_ID': info['identity'],
                'VAULT_MACHINE_ID': info['machine'],
                'VAULT_PIN': '123456'})
    return sandbox, env, info


def seed_of(env):
    code = ('import sqlite3, os, json\n'
            'db = os.path.join(os.environ["ACTUS_VAULT2_DIR"], "vault2.db")\n'
            'c = sqlite3.connect(db)\n'
            'print(c.execute("SELECT seed_key FROM identities").fetchone()[0])\n')
    p = subprocess.run([sys.executable, '-c', code], env=env, cwd=BASE,
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    return (p.stdout or '').strip()


def cli(env, *argv):
    p = subprocess.run([sys.executable, '-m', 'vools.actus.cli'] + list(argv),
                       env=env, cwd=BASE, capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    return p.returncode, p.stdout, p.stderr


def mcp(env, args):
    code = ('import io, json\n'
            'from vools.actus.mcp_server import MCPServer\n'
            'srv = MCPServer(stdin=io.StringIO(), stdout=io.StringIO())\n'
            'r = srv._call_tool({"name": "actus_vault_rotate_seed", "arguments": %s})\n'
            'print(json.dumps({"isError": r["isError"],\n'
            '                  "payload": json.loads(r["content"][0]["text"])}))\n'
            % repr(args))
    p = subprocess.run([sys.executable, '-c', code], env=env, cwd=BASE,
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    line = (p.stdout or '').strip().splitlines()
    return json.loads(line[-1]) if line else {'isError': None, 'payload': {}, 'err': p.stderr[-200:]}


def main():
    sandbox, env, info = setup_env()
    seed0 = seed_of(env)

    # ── 1) 无 --yes：rc=1 + 警告，不执行 ──
    rc, out, err = cli(env, 'vault', 'rotate-seed')
    check('1) CLI 无 --yes → rc=1', rc == 1, 'rc=%d' % rc)
    check('1) CLI 无 --yes → 有警告文案', '破坏性' in (err + out), (err or out).strip()[:60])
    check('1) CLI 无 --yes → **未执行**（seed 未变）', seed_of(env) == seed0)

    # ── 1b) 无 --yes + --json：扁平 refused ──
    rc, out, err = cli(env, 'vault', 'rotate-seed', '--json')
    try:
        payload = json.loads(out)
    except Exception:                              # noqa: BLE001
        payload = {}
    check('1b) --json 无 --yes → refused/rc=1',
          rc == 1 and payload.get('status') == 'refused', str(payload)[:60])
    check('1b) --json refused 有 code=confirmation_required',
          payload.get('code') == 'confirmation_required')

    # ── 2) --yes：rc=0 + 全字段 + warnings 在 stderr ──
    rc, out, err = cli(env, 'vault', 'rotate-seed', '--yes', '--json')
    try:
        payload = json.loads(out)
    except Exception:                              # noqa: BLE001
        payload = {}
    body = payload.get('data') or payload
    check('2) CLI --yes → rc=0', rc == 0, 'rc=%d out=%r err=%r' % (rc, out[:80], err[:80]))
    need = ('identity_id', 'rotated_secrets', 'rotated_backups', 'seed_fingerprint',
            'sessions_invalidated', 'recovery_key_invalidated', 'warnings')
    missing = [k for k in need if k not in body]
    check('2) CLI 输出含全部字段', not missing, 'missing=%s' % missing)
    check('2) CLI --yes 后 seed 变了', seed_of(env) != seed0)
    check('2) warnings 在 stderr 可见（recovery_key 失效）',
          '恢复密钥已失效' in err, err.strip()[:70])

    # ── 3) MCP confirm=false → isError + param_invalid ──
    res = mcp(env, {'confirm': False})
    err_code = ((res.get('payload') or {}).get('error') or {}).get('code')
    check('3) MCP confirm=false → isError=True', res.get('isError') is True)
    check('3) MCP confirm=false → code in (param_invalid, confirmation_required)',
          err_code in ('param_invalid', 'confirmation_required'), str(err_code))

    # ── 4) MCP confirm=true → isError=False 且 status=ok ──
    res = mcp(env, {'confirm': True})
    payload = res.get('payload') or {}
    check('4) MCP confirm=true → isError=False', res.get('isError') is False,
          str(payload)[:90])
    check('4) MCP confirm=true → status=ok', payload.get('status') == 'ok', payload.get('status'))
    check('4) MCP 返回体含 warnings 字段', 'warnings' in payload)
    check('4) MCP 返回 rotated_secrets/backups 统计',
          'rotated_secrets' in payload and 'rotated_backups' in payload)

    print()
    failed = [l for l, ok in RESULTS if not ok]
    print('SUMMARY: %d passed, %d failed' % (len(RESULTS) - len(failed), len(failed)))
    for l in failed:
        print('  FAILED: ' + l)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
