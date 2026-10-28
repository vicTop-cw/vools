# -*- coding: utf-8 -*-
"""统计：把 canonical tests 失败纳入 passed 后，有多少 spec/动作会由 pass 变 fail。

扫描范围（只读）：
  * 全仓 *.md 里含 sigma 规约块的（```sigma / '# Module:' / '## Operation:'）
  * 全仓 *.spec.json
用法：python tools/audit/sigma_flip_stats.py [before|after]
before 记录基线（当前 check_iron_laws 语义），after 记录改后语义，二者 diff 即翻转数。
"""
import json, os, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, 'tests'))
import _ai_local_bootstrap; _ai_local_bootstrap.install()
from vools.actus import sigma

SKIP_DIRS = {'.git', '__pycache__', 'node_modules', '.venv', 'venv'}

def candidates():
    out = []
    for dirpath, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            p = os.path.join(dirpath, fn)
            if fn.endswith('.spec.json'):
                out.append(('spec_json', p))
            elif fn.endswith('.md'):
                try:
                    text = open(p, encoding='utf-8', errors='replace').read()
                except OSError:
                    continue
                if ('## Operation:' in text) or ('```sigma' in text) or ('# Module:' in text):
                    out.append(('md', p))
    return out

rows = []
for kind, path in candidates():
    rel = os.path.relpath(path, ROOT)
    try:
        if kind == 'spec_json':
            spec = sigma.load_spec_json(path)
            module = sigma._module_from_spec(spec)
        else:
            text = open(path, encoding='utf-8', errors='replace').read()
            body = sigma.extract_sigma_block(text) if '```' in text else text
            if not body.strip() or ('## Operation' not in body and 'Fingerprint' not in body):
                continue
            module = sigma.parse_module_text(body)
    except Exception as exc:
        rows.append({'kind': kind, 'path': rel, 'error': '%s: %s' % (type(exc).__name__, str(exc)[:80])})
        continue
    r = sigma.check_iron_laws(module)
    rows.append({'kind': kind, 'path': rel,
                 'ops': len(module['ops']),
                 'passed': r['passed'],
                 'failed_laws': [l['id'] for l in r['failed_laws']],
                 'tests_total': r['tests']['total'],
                 'tests_failed': len(r['tests']['failures'])})

mode = sys.argv[1] if len(sys.argv) > 1 else 'before'
out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'sigma_flip_%s.json' % mode)
json.dump(rows, open(out_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

total = len(rows)
passed = sum(1 for r in rows if r.get('passed'))
with_tests = [r for r in rows if r.get('tests_failed')]
would_flip = [r for r in rows if r.get('passed') and r.get('tests_failed')]
print('模式=%s | 候选文件=%d | 当前 passed=%d' % (mode, total, passed))
print('有规范测试失败的文件=%d | 其中当前仍判 passed（= 会翻转）=%d' % (len(with_tests), len(would_flip)))
for r in would_flip:
    print('  FLIP %-55s tests %d/%d 失败' % (r['path'], r['tests_failed'], r['tests_total']))
print('明细已写入:', out_path)
