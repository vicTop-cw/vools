# -*- coding: utf-8 -*-
"""验收 v2：indexer/author/evolution/scattered 的 runtime 分流（裸仓库 vs 正常仓库）。"""
import json, os, shutil, subprocess, sys, tempfile
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
BARE = tempfile.mkdtemp(prefix='rt2_')
os.makedirs(os.path.join(BARE, 'actions'))
# zh.actus.md 在正常仓库是"零真实错误"的动作 → 裸仓库里只应剩 runtime 提示
shutil.copy(os.path.join(REPO, 'actions', 'zh.actus.md'), os.path.join(BARE, 'actions', 'zh.actus.md'))

def run_py(code, repo_root):
    env = dict(os.environ, PYTHONPATH=os.path.join(REPO, 'vools'),
               ACTUS_REPO_ROOT=repo_root, PYTHONIOENCODING='utf-8')
    return subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                          encoding='utf-8', errors='replace', cwd=repo_root, env=env, timeout=300)

def show(title, r):
    print('  [%s] rc=%d' % (title, r.returncode))
    out = (r.stdout or '').strip()
    if out:
        print('   ', out.replace('\n', '\n    '))
    if r.returncode != 0 and r.stderr:
        print('    STDERR:', r.stderr.strip().splitlines()[-1][:150])

print('=== A) indexer：裸仓库 status 不因 runtime 提示变 invalid；bad 动作仍 invalid ===')
probe = '''
import json, os, tempfile
from vools.actus.indexer import build_index
root = os.environ["ACTUS_REPO_ROOT"]
idx = build_index(actions_dir=os.path.join(root, "actions"), meta_dir=tempfile.mkdtemp())
for aid, b in sorted(idx["actions"].items()):
    print("%-40s status=%-8s warnings=%d errors=%s" % (
        aid, b.get("status"), len(b.get("warnings") or []),
        (b.get("errors") or [])[:1]))
'''
show('裸仓库', run_py(probe, BARE))
show('正常仓库', run_py(probe, REPO))

print('\n=== B) 假绿灯回归：真错误动作 → status=invalid，CLI validate(无 id) rc=1 ===')
shutil.copy(os.path.join(REPO, 'actions', 'zh.actus.md'),
            os.path.join(BARE, 'actions', 'broken.actus.md'))
broken = os.path.join(BARE, 'actions', 'broken.actus.md')
text = open(broken, encoding='utf-8').read().replace('"id": "actus.generated.zh"', '"id": "audit.broken.act"')
text = text.replace('"name": "Zh"', '"name_BROKEN": "Zh"')   # 去掉必填 name → 真实错误
open(broken, 'w', encoding='utf-8').write(text)
show('裸仓库 build_index', run_py(probe, BARE))
env = dict(os.environ, PYTHONPATH=os.path.join(REPO, 'vools'), ACTUS_REPO_ROOT=BARE,
           PYTHONIOENCODING='utf-8')
p = subprocess.run([sys.executable, '-m', 'vools.actus.cli', 'validate'],
                   capture_output=True, text=True, encoding='utf-8', errors='replace',
                   cwd=BARE, env=env, timeout=300)
d = json.loads(p.stdout[p.stdout.index('{'):])
print('  CLI validate(无 id) rc =', p.returncode, '| data.valid =', d['data'].get('valid'),
      '| invalid keys =', list((d['data'].get('invalid') or {}).keys()))
os.remove(broken)

print('\n=== C) author Pipeline：schema 步只看真实错误，runtime 提示进 runtime_notes ===')
probe2 = '''
import os
from vools.actus.model import parse_cfg_from_file
from vools.actus.author import Pipeline
root = os.environ["ACTUS_REPO_ROOT"]
p = Pipeline(parse_cfg_from_file(os.path.join(root, "actions", "zh.actus.md")),
             repo_root=root)
res = p.run(dry_run_only=True)
step = [s for s in res["steps"] if s["step"] == "schema_validate"][0]
print("schema_validate ok =", step["ok"], "| message =", step["message"])
print("runtime_notes 条数 =", len(res.get("runtime_notes") or []), "| run.valid =", res["valid"])
'''
show('裸仓库', run_py(probe2, BARE))
show('正常仓库', run_py(probe2, REPO))

print('\n=== D) evolution._phase_validate：valid 只看真实错误，warnings 透传 ===')
probe3 = '''
import os
from vools.actus.evolution import EvolutionEngine
root = os.environ["ACTUS_REPO_ROOT"]
res = EvolutionEngine()._phase_validate(os.path.join(root, "actions", "zh.actus.md"))
print("valid =", res.get("valid"), "| errors =", res.get("errors"),
      "| warnings 条数 =", len(res.get("warnings") or []))
'''
show('裸仓库', run_py(probe3, BARE))
show('正常仓库', run_py(probe3, REPO))

print('\n=== E) scattered check：valid 不看 runtime 提示，warnings 保留 ===')
probe4 = '''
import os
from vools.actus.scattered import check_scattered
root = os.environ["ACTUS_REPO_ROOT"]
rep = check_scattered(os.path.join(root, "actions", "zh.actus.md"))
print("valid =", rep.get("valid"), "| errors =", len(rep.get("errors") or []),
      "| warnings 条数 =", len(rep.get("warnings") or []))
'''
show('裸仓库', run_py(probe4, BARE))
show('正常仓库', run_py(probe4, REPO))
