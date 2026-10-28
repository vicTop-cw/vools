"""验收：`info` / `preview` / `validate` / `run` 对**重名目标**的错误结构逐字段相等。

背景（第 17 轮）：`run` 发 `{code:'ambiguous', details:{candidates}}`，而
`_resolve_cli_target` 捕获 resolver 异常时**丢了 details**、code 也不同
（`action_ambiguous`）。同一语义两套结构 → 脚本没法统一处理。
修法：抽 `_ambiguous_error(target, candidates)`，两处都调它。

跑法：`python tools/audit/verify_ambiguous_contract.py`（全 tmp 隔离）
"""
import json
import os
import subprocess
import sys
import tempfile

BASE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

FENCE = '`' * 3


def action_text(aid, name):
    return ('# %s\n\n' % name + FENCE + 'json #!cfg\n'
            '{"id": "%s", "name": "%s", "version": "1.0.0", "description": "d",'
            ' "trust": "sandbox", "entry": "main", "platform": "desktop"}\n'
            % (aid, name) + FENCE + '\n\n'
            + FENCE + "python #!run tag=main\nprint('hi')\n" + FENCE + '\n')


def setup():
    sandbox = tempfile.mkdtemp(prefix='amb-')
    repo = os.path.join(sandbox, 'repo')
    actions = os.path.join(repo, 'actions')
    meta = os.path.join(sandbox, 'meta')
    for d in (actions, meta):
        os.makedirs(d)
    # 两个动作**同名不同 id** → resolver 的 name 分支命中多个
    open(os.path.join(actions, 'one.actus.md'), 'w', encoding='utf-8').write(
        action_text('myapp.dup.one', 'Dup'))
    open(os.path.join(actions, 'two.actus.md'), 'w', encoding='utf-8').write(
        action_text('myapp.dup.two', 'Dup'))
    env = dict(os.environ, ACTUS_REPO_ROOT=repo, ACTUS_META_DIR=meta,
               HOME=sandbox, USERPROFILE=sandbox, PYTHONPATH=BASE,
               PYTHONIOENCODING='utf-8')
    return repo, env


def run(env, argv):
    p = subprocess.run([sys.executable, '-m', 'vools.actus.cli'] + argv,
                       env=env, cwd=env['ACTUS_REPO_ROOT'], capture_output=True,
                       text=True, encoding='utf-8', errors='replace')
    try:
        payload = json.loads(p.stdout.strip())
    except Exception:                              # noqa: BLE001
        payload = {'_raw': p.stdout.strip()[:200], '_err': p.stderr.strip()[-200:]}
    return p.returncode, payload


def main():
    repo, env = setup()
    cases = {
        'run': ['run', 'Dup'],
        'info': ['info', 'Dup'],
        'validate': ['validate', 'Dup'],
        'preview': ['preview', 'Dup'],
    }
    results = {}
    for name, argv in cases.items():
        rc, payload = run(env, argv)
        results[name] = (rc, payload.get('error'))
        print('%-9s rc=%d error=%s' % (name, rc, json.dumps(payload.get('error'),
                                                           ensure_ascii=False)[:160]))

    print()
    ok = True
    base_err = results['run'][1]
    for name, (rc, err) in results.items():
        same = err == base_err
        rc_ok = rc == 1
        print('%s %-9s 与 run 逐字段相等 = %-5s | rc=1 = %s'
              % ('PASS' if (same and rc_ok) else 'FAIL', name, same, rc_ok))
        ok = ok and same and rc_ok
    print()
    print('候选列表 =', (base_err or {}).get('details', {}).get('candidates'))
    print('\nSUMMARY: 四命令错误结构%s' % ('完全一致 ✓' if ok else '**不一致**'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
