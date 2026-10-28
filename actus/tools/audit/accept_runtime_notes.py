# -*- coding: utf-8 -*-
"""验收：runtime: 提示不算动作校验失败 —— 裸仓库四步（全 Python，免 shell 引号地狱）。"""
import json, os, shutil, subprocess, sys, tempfile
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
PYTHONPATH = os.path.join(REPO, 'vools')
BARE = tempfile.mkdtemp(prefix='bare_')
os.makedirs(os.path.join(BARE, 'actions'))
shutil.copy(os.path.join(REPO, 'actions', 'zh.actus.md'),
            os.path.join(BARE, 'actions', 'zh.actus.md'))
ENV = dict(os.environ, PYTHONPATH=PYTHONPATH, ACTUS_REPO_ROOT=BARE,
           PYTHONIOENCODING='utf-8')

def run_cli(*args, cwd=None):
    return subprocess.run([sys.executable, '-m', 'vools.actus.cli'] + list(args),
                          capture_output=True, text=True, encoding='utf-8',
                          errors='replace', cwd=cwd or BARE, env=ENV, timeout=300)

def run_py(code):
    return subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                          encoding='utf-8', errors='replace', cwd=BARE, env=ENV, timeout=300)

print('=== 1) 裸仓库：validate_action 仍返回 runtime: 提示，但 is_valid=True ===')
r = run_py(
 'from vools.actus.model import parse_cfg_from_file\n'
 'from vools.actus.validate import validate_action, split_validation, is_valid\n'
 'a = parse_cfg_from_file("actions/zh.actus.md")\n'
 'e = validate_action(a)\n'
 'real, notes = split_validation(e)\n'
 'print("errors =", e)\n'
 'print("real_errors =", real)\n'
 'print("runtime_notes =", notes)\n'
 'print("is_valid =", is_valid(e))\n')
print(r.stdout.rstrip())

print('\n=== 2) 裸仓库：scaffold CLI → exit 0，stderr 有警告，--json 有 warnings ===')
p = run_cli('scaffold', '审计用：一个 JSON 格式化小工具')
print('  scaffold rc =', p.returncode, '(期望 0)')
d = json.loads(p.stdout[p.stdout.index('{'):])
v = (d.get('data') or {}).get('validation') or {}
print('  top status =', d.get('status'), '| 顶层 warnings 条数 =', len(d.get('warnings') or []))
print('  validation.valid =', v.get('valid'), '| runtime_notes 条数 =', len(v.get('runtime_notes') or []))
print('  stderr 含 runtime 提示 =', 'runtime:' in (p.stderr or ''))

print('\n=== 3) 生成的骨架测试在裸仓库下应绿 ===')
tests_dir = os.path.join(BARE, 'tests')
gen = sorted(os.path.join(tests_dir, f) for f in os.listdir(tests_dir)) if os.path.isdir(tests_dir) else []
print('  生成测试:', [os.path.basename(g) for g in gen])
for g in gen:
    q = subprocess.run([sys.executable, '-m', 'pytest', '-q', g], capture_output=True,
                       text=True, encoding='utf-8', errors='replace', cwd=BARE, env=ENV)
    print('  %-32s rc=%d %s' % (os.path.basename(g), q.returncode, q.stdout.strip().splitlines()[-1:]))

print('\n=== 4) 真错误（缺必填 name）→ is_valid=False、validate CLI rc=1 ===')
broken = os.path.join(BARE, 'actions', 'broken.actus.md')
open(broken, 'w', encoding='utf-8').write(
    '```json #!cfg\n{\n  "id": "audit.broken.act",\n  "version": "0.0.1",\n'
    '  "trust": "audit",\n  "kind": "exec",\n  "entry": "main",\n'
    '  "platform": ["desktop"]\n}\n```\n\n```python main\nprint(1)\n```\n')
r = run_py(
 'from vools.actus.model import parse_cfg_from_file\n'
 'from vools.actus.validate import validate_action, split_validation, is_valid\n'
 'e = validate_action(parse_cfg_from_file("actions/broken.actus.md"))\n'
 'real, notes = split_validation(e)\n'
 'print("real_errors =", real)\n'
 'print("runtime_notes =", len(notes), "条（仍保留）")\n'
 'print("is_valid =", is_valid(e))\n')
print(r.stdout.rstrip())
p = run_cli('validate', 'audit.broken.act')
print('  validate CLI rc =', p.returncode, '(期望 1)')
d = json.loads(p.stdout[p.stdout.index('{'):])
print('  top status =', d.get('status'),
      '| data.warnings 保留 runtime =', bool((d.get('data') or {}).get('warnings')))

print('\n=== 对照）正常仓库（有 contracts）：行为不变 ===')
env2 = dict(ENV); env2.pop('ACTUS_REPO_ROOT', None)
q = subprocess.run([sys.executable, '-m', 'vools.actus.cli', 'validate', 'actus.generated.zh'],
                   capture_output=True, text=True, encoding='utf-8', errors='replace',
                   cwd=REPO, env=env2, timeout=300)
d = json.loads(q.stdout[q.stdout.index('{'):])
print('  rc =', q.returncode, '| status =', d.get('status'),
      '| errors =', d['data'].get('errors'), '| warnings 字段存在 =', 'warnings' in d['data'])
