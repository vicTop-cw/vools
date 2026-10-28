# -*- coding: utf-8 -*-
"""补充证据：load_* 读语义零写盘快照 + CLI registry validate 假校验。"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
HOME = tempfile.mkdtemp(prefix='ro_home_')
META = tempfile.mkdtemp(prefix='ro_meta_')
os.environ['HOME'] = HOME
os.environ['USERPROFILE'] = HOME
os.environ['ACTUS_META_DIR'] = META
sys.path.insert(0, os.path.join(REPO, 'vools'))
sys.path.insert(0, os.path.join(REPO, 'tests'))
import _ai_local_bootstrap  # noqa: E402
_ai_local_bootstrap.install()
from vools.actus import registry as R  # noqa: E402
from vools.actus.registry import ActionRegistry  # noqa: E402


def snapshot(*roots):
    snap = {}
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dp, _d, fs in os.walk(root):
            for f in fs:
                p = os.path.join(dp, f)
                try:
                    with open(p, 'rb') as fh:
                        digest = hashlib.sha256(fh.read()).hexdigest()[:16]
                    snap[p] = (digest, os.path.getsize(p), os.path.getmtime(p))
                except OSError:
                    pass
    return snap


repo = tempfile.mkdtemp(prefix='ro_repo_')
os.makedirs(os.path.join(repo, 'actions', 'cat'))
cfg = {"id": "demo.ro.a", "name": "RO", "version": "1.0.0", "description": "ro",
       "tags": ["t"], "kind": "exec", "entry": "main", "platform": ["desktop"],
       "trust": "trusted"}
with open(os.path.join(repo, 'actions', 'cat', 'a.actus.md'), 'w', encoding='utf-8') as f:
    f.write('```json #!cfg\n%s\n```\n\n```python #!run tag=main\nprint(1)\n```\n'
            % json.dumps(cfg))
reg = ActionRegistry(cache_dir=os.path.join(HOME, 'cache'))
reg.build_from_directory(repo, write=True)      # 先建索引（这一步本就该写）
# 预置 manifest / 缓存，便于验证"读也不写"
os.makedirs(os.path.join(HOME, '.actus', 'installed'), exist_ok=True)
with open(os.path.join(HOME, '.actus', 'installed', 'x.json'), 'w') as f:
    json.dump({"url": "https://example.com/x", "actions": []}, f)

before = snapshot(repo, os.path.join(HOME, '.actus'), os.path.join(HOME, 'cache'), META)
calls = [
    ('load_from_repo', lambda: reg.load_from_repo(repo)),
    ('load_from_file', lambda: reg.load_from_file(os.path.join(repo, '.actus.registry.json'))),
    ('search(None)', lambda: reg.search()),
    ('search(q)', lambda: reg.search('demo')),
    ('recommend', lambda: reg.recommend('demo tool')),
    ('list_all/get/categories/authors', lambda: (reg.list_all(), reg.get('demo.ro.a'),
                                                 reg.list_categories(), reg.list_authors())),
    ('search_registry()', lambda: R.search_registry(repo, query='demo')),
    ('filter_by_quality', lambda: reg.filter_by_quality(repo_dir=repo)),
    ('load_cached_index(miss)', lambda: reg.load_cached_index('https://example.com/x')),
    ('load_manifest', lambda: reg.load_manifest('https://example.com/x')),
    ('list_installed', lambda: reg.list_installed()),
    ('verify_checksum/validate_entry', lambda: (
        reg.verify_checksum(reg.get('demo.ro.a'), repo),
        reg.validate_entry(reg.get('demo.ro.a'), repo))),
]
for name, fn in calls:
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        print('  %-34s -> 抛 %s: %s' % (name, type(exc).__name__, str(exc)[:60]))
    else:
        print('  %-34s -> ok' % name)

after = snapshot(repo, os.path.join(HOME, '.actus'), os.path.join(HOME, 'cache'), META)
print('\n=== 读语义零写盘（repo + HOME/.actus + cache + META 快照对比）===')
added = sorted(set(after) - set(before))
removed = sorted(set(before) - set(after))
changed = sorted(k for k in set(before) & set(after) if before[k] != after[k])
print('  新增文件:', added or '无')
print('  删除文件:', removed or '无')
print('  内容/时间变化:', changed or '无')

print('\n=== 索引与磁盘不一致：谁被信任 ===')
idx = json.load(open(os.path.join(repo, '.actus.registry.json'), encoding='utf-8'))
entry = reg.get('demo.ro.a')
print('  索引里 checksum =', entry.checksum[:22], '...')
with open(os.path.join(repo, 'actions', 'cat', 'a.actus.md'), 'a', encoding='utf-8') as f:
    f.write('\n<!-- 磁盘已改 -->\n')
now_ok = reg.verify_checksum(entry, repo)
print('  改盘后 verify_checksum(同一索引条目) =', now_ok, '（索引值 vs 磁盘值不一致 → False）')
print('  但 search_registry 仍照索引返回:', [e.id for e in R.search_registry(repo, query='demo')])

print('\n=== CLI `registry validate`：只数 id 存在 = 伪校验 ===')
repo2 = tempfile.mkdtemp(prefix='cli_repo_')
os.makedirs(os.path.join(repo2, 'actions'))
fake_index = {'name': 'x', 'version': '1.0.0', 'actions': [
    {'id': 'demo.fake.a', 'name': '', 'version': 'not-semver', 'description': '',
     'category': '', 'path': 'actions/missing.actus.md', 'author': '',
     'tags': [], 'checksum': 'sha256:' + '0' * 64, 'trust_level': 'trusted'}]}
with open(os.path.join(repo2, '.actus.registry.json'), 'w', encoding='utf-8') as f:
    json.dump(fake_index, f)
env = dict(os.environ, PYTHONPATH=os.path.join(REPO, 'vools'), PYTHONIOENCODING='utf-8')
p = subprocess.run([sys.executable, '-m', 'vools.actus.cli', 'registry', 'validate',
                    '--index', os.path.join(repo2, '.actus.registry.json')],
                   capture_output=True, text=True, encoding='utf-8', errors='replace',
                   cwd=repo2, env=env, timeout=120)
print('  rc =', p.returncode)
print('  stdout:', (p.stdout or '').strip()[:200])
print('  （该条目：name 空、version 非 semver、文件不存在、checksum 全 0 → 仍报"校验通过"）')

print('\n=== 半截索引对 CLI 的影响 ===')
with open(os.path.join(repo2, '.actus.registry.json'), 'w', encoding='utf-8') as f:
    f.write('{"name": "x", "acti')
p2 = subprocess.run([sys.executable, '-m', 'vools.actus.cli', 'registry', 'info',
                     '--index', os.path.join(repo2, '.actus.registry.json')],
                    capture_output=True, text=True, encoding='utf-8', errors='replace',
                    cwd=repo2, env=env, timeout=120)
print('  rc =', p2.returncode, '| stderr 末行:', (p2.stderr or '').strip().splitlines()[-1:])

print('\n=== ActionRegistry() 构造即建 cache 目录（只读命令也写盘）===')
cache_dir = os.path.join(HOME, 'fresh_cache_check')
print('  构造前存在:', os.path.isdir(cache_dir))
ActionRegistry(cache_dir=cache_dir)
print('  构造后存在:', os.path.isdir(cache_dir))
