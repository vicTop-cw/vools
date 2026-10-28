# -*- coding: utf-8 -*-
"""验收：indexer / author / evolution / scattered 四处对 runtime: 的分流（裸仓库 vs 正常仓库）。"""
import json, os, shutil, subprocess, sys, tempfile
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
BARE = tempfile.mkdtemp(prefix='rt_bare_')
BARE_ACTIONS = os.path.join(BARE, 'actions'); os.makedirs(BARE_ACTIONS)

# 一份最小但合法的动作（trusted 免测试绑定），供 Pipeline / scattered 用
MINIMAL = '''```json #!cfg
{
  "id": "audit.rt.min",
  "name": "RT Min",
  "version": "0.0.1",
  "trust": "trusted",
  "kind": "exec",
  "entry": "main",
  "platform": ["desktop"]
}
```

```python #!run tag=main
print("ok")
```
'''
open(os.path.join(BARE_ACTIONS, 'min.actus.md'), 'w', encoding='utf-8').write(MINIMAL)

def run_py(code, repo_root):
    env = dict(os.environ, PYTHONPATH=os.path.join(REPO, 'vools'),
               ACTUS_REPO_ROOT=repo_root, PYTHONIOENCODING='utf-8')
    return subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                          encoding='utf-8', errors='replace', cwd=repo_root, env=env, timeout=300)

def show(title, r):
    print('  %-28s rc=%d' % (title, r.returncode))
    out = (r.stdout or '').strip()
    if out:
        print('   ', out.replace('\n', '\n    '))
    if r.returncode != 0 and r.stderr:
        print('    STDERR:', r.stderr.strip().splitlines()[-1][:160])

print('=== A) indexer：裸仓库里不应把动作标 invalid；正常仓库行为不变 ===')
probe = '''
import json, os, tempfile
from vools.actus.indexer import scan_actions, build_index
root = os.environ["ACTUS_REPO_ROOT"]
actions_dir = os.path.join(root, "actions")
meta = tempfile.mkdtemp()
acts = scan_actions(actions_dir, validate=True)
one = list(acts.values())[0]
print("scan_actions: _validation_errors =", one.meta.get("_validation_errors"))
print("scan_actions: _runtime_notes 条数 =", len(one.meta.get("_runtime_notes") or []))
idx = build_index(actions_dir=actions_dir, meta_dir=meta)
brief = list(idx["actions"].values())[0]
print("build_index: status =", brief.get("status"), "| warnings 条数 =", len(brief.get("warnings") or []))
print("build_index: errors =", brief.get("errors"))
'''
show('裸仓库', run_py(probe, BARE))
show('正常仓库', run_py(probe, REPO))

print('\n=== B) CLI validate（无 id，依赖索引）：裸仓库 rc 应为 0 ===')
env = dict(os.environ, PYTHONPATH=os.path.join(REPO, 'vools'), ACTUS_REPO_ROOT=BARE,
           PYTHONIOENCODING='utf-8')
p = subprocess.run([sys.executable, '-m', 'vools.actus.cli', 'validate'],
                   capture_output=True, text=True, encoding='utf-8', errors='replace',
                   cwd=BARE, env=env, timeout=300)
print('  rc =', p.returncode, '| data.valid =',
      json.loads(p.stdout[p.stdout.index('{'):]).get('data', {}).get('valid'))

print('\n=== C) author Pipeline：schema 步不被 runtime 提示判红，notes 透传 ===')
probe2 = '''
import json, os
from vools.actus.model import parse_cfg_from_file
from vools.actus.author import Pipeline
root = os.environ["ACTUS_REPO_ROOT"]
path = os.path.join(root, "actions", "min.actus.md")
p = Pipeline(parse_cfg_from_file(path), repo_root=root)
res = p.run(dry_run_only=True)
schema_step = [s for s in res["steps"] if s["step"] == "schema_validate"][0]
print("schema_validate ok =", schema_step["ok"], "| message =", schema_step["message"])
print("run.runtime_notes 条数 =", len(res.get("runtime_notes") or []))
print("run.valid =", res["valid"])
'''
show('裸仓库', run_py(probe2, BARE))
show('正常仓库', run_py(probe2, REPO))

print('\n=== D) evolution._phase_validate：valid 只由真实错误决定，warnings 透传 ===')
probe3 = '''
import os
from vools.actus.evolution import EvolutionEngine
root = os.environ["ACTUS_REPO_ROOT"]
eng = EvolutionEngine()
res = eng._phase_validate(os.path.join(root, "actions", "min.actus.md"))
print("valid =", res.get("valid"), "| message =", res.get("message"),
      "| errors =", res.get("errors"), "| warnings 条数 =", len(res.get("warnings") or []))
'''
show('裸仓库', run_py(probe3, BARE))
show('正常仓库', run_py(probe3, REPO))

print('\n=== E) scattered check：valid 不看 runtime 提示，warnings 里保留 ===')
probe4 = '''
import os
from vools.actus.scattered import check_scattered
root = os.environ["ACTUS_REPO_ROOT"]
rep = check_scattered(os.path.join(root, "actions", "min.actus.md"))
print("valid =", rep.get("valid"), "| errors =", len(rep.get("errors") or []),
      "| warnings 条数 =", len(rep.get("warnings") or []))
print("warnings[0:1] =", (rep.get("warnings") or [])[:1])
'''
show('裸仓库', run_py(probe4, BARE))
show('正常仓库', run_py(probe4, REPO))

print('\n=== F) security.py sandbox 同名函数核实（只读结论）===')
import inspect
sys.path.insert(0, os.path.join(REPO, 'vools'))
from vools.actus.security import SandboxEnhancer
src = inspect.getsource(SandboxEnhancer.validate_action)
print('  SandboxEnhancer.validate_action 是否 import vools.actus.validate:',
      'from .validate' in src or 'validate_action(' in src and 'validate_action, ' in src)
print('  是否出现 runtime 前缀处理:', 'runtime' in src)
print('  签名:', str(inspect.signature(SandboxEnhancer.validate_action)))
