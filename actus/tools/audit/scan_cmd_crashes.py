# -*- coding: utf-8 -*-
"""只读扫描：给每个 CLI 子命令喂一组无害参数，抓 AttributeError/NameError 类崩溃。"""
import json, subprocess, sys, os

CLI = [sys.executable, '-m', 'vools.actus.cli']
CASES = [
    ('health', ['health']), ('health-json', ['health', '--json']),
    ('viz', ['viz']), ('viz-action', ['viz', '--action', 'foo']),
    ('viz-action-id', ['viz', '--action', 'actus.test.foo']),
    ('events', ['events']), ('status', ['status']), ('scan', ['scan']),
    ('list', ['list']), ('validate', ['validate']), ('runtimes', ['runtimes']),
    ('records-list', ['records', 'list']), ('artifacts-list', ['artifacts', 'list']),
    ('template-list', ['template', 'list']), ('triggers-list', ['triggers', 'list']),
    ('triggers-status', ['triggers', 'status']), ('loop-list', ['loop', 'list']),
    ('vault-list', ['vault', 'list']), ('reg-list', ['reg', 'list']),
    ('private-list', ['private', 'list']), ('team-list', ['team', 'list']),
    ('registry-info', ['registry', 'info']), ('registry-validate', ['registry', 'validate']),
    ('list-installed', ['list-installed']), ('check-update', ['check-update']),
    ('pending', ['pending']), ('runtimes-json', ['runtimes', '--json']),
    ('deps-help', ['deps', '--help']), ('info-help', ['info', '--help']),
    ('concurrency-status', ['concurrency', 'status']),
    ('concurrency-list', ['concurrency', 'list']),
    ('selfheal-status', ['selfheal', 'status']), ('template-list2', ['template', 'list']),
    ('notify-stats', ['notify', 'stats']), ('notify-history', ['notify', 'history']),
    ('project-mgmt', ['project-mgmt', '--help']),
    ('omega-format', ['omega', 'format', '--help']),
    ('replay', ['replay']), ('export-help', ['export', '--help']),
]

BAD = ('has no attribute', 'is not defined', 'is not iterable',
       'object is not callable', 'unexpected keyword argument')

def run(args):
    try:
        p = subprocess.run(CLI + args, capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=120,
                           cwd=os.getcwd())
        return p.returncode, (p.stdout or '') + (p.stderr or '')
    except subprocess.TimeoutExpired:
        return 'TIMEOUT', ''

hits = []
for label, args in CASES:
    rc, out = run(args)
    if rc == 'TIMEOUT':
        print('%-18s TIMEOUT' % label); continue
    found = [b for b in BAD if b in out]
    status = 'CRASH' if found else 'ok'
    print('%-18s rc=%-4s %-5s %s' % (label, rc, status,
          (' | ' + found[0] if found else '')))
    if found:
        msg = ''
        try:
            d = json.loads(out[out.index('{'):])
            msg = d.get('error', {}).get('message', '')
        except Exception:
            msg = out.strip().splitlines()[-1] if out.strip() else ''
        hits.append((label, args, found[0], msg))

print('\n=== 崩溃清单 ===')
for label, args, why, msg in hits:
    print('  %-18s %-30s %s -> %s' % (label, ' '.join(args), why, msg[:110]))
