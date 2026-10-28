# -*- coding: utf-8 -*-
"""审计 registry.py / omega_strong.py：反例实测（全 tmp 隔离，不碰真实 ~/.actus）。"""
import json
import os
import sys
import tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
HOME = tempfile.mkdtemp(prefix='reg_home_')
META = tempfile.mkdtemp(prefix='reg_meta_')
os.environ['HOME'] = HOME
os.environ['USERPROFILE'] = HOME
os.environ['ACTUS_META_DIR'] = META
sys.path.insert(0, os.path.join(REPO, 'vools'))
sys.path.insert(0, os.path.join(REPO, 'tests'))
import _ai_local_bootstrap  # noqa: E402
_ai_local_bootstrap.install()
from vools.actus import registry as R  # noqa: E402
from vools.actus.registry import ActionRegistry, RegistryEntry  # noqa: E402


def section(title):
    print('\n=== %s ===' % title)


def make_repo():
    repo = tempfile.mkdtemp(prefix='reg_repo_')
    os.makedirs(os.path.join(repo, 'actions', 'cat'), exist_ok=True)
    cfg = {"id": "demo.cat.a", "name": "A", "version": "1.0.0",
           "description": "demo", "tags": ["x"], "kind": "exec",
           "entry": "main", "platform": ["desktop"], "trust": "trusted"}
    body = '```json #!cfg\n%s\n```\n\n```python #!run tag=main\nprint(1)\n```\n' % json.dumps(cfg)
    path = os.path.join(repo, 'actions', 'cat', 'a.actus.md')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(body)
    return repo, path


section('R1a) write_index 非原子：截断写入 → 半截索引，读回直接炸')
repo, apath = make_repo()
reg = ActionRegistry(cache_dir=os.path.join(HOME, 'regcache'))
idx = reg.build_from_directory(repo, write=False)
with open(os.path.join(repo, '.actus.registry.json'), 'w', encoding='utf-8') as f:
    f.write(json.dumps(idx, ensure_ascii=False)[:40])
try:
    R.search_registry(repo, query='demo')
    print('  UNEXPECTED: 没炸')
except Exception as exc:
    print('  半截索引 → search_registry 抛:', type(exc).__name__, str(exc)[:70])
print('  write_index 实现：open(path,"w") 截断原文件再 dump → 中断即半截（无 tmp+replace）')

section('R1b) load_from_repo：文件存在但损坏 → 不重建、直接抛')
try:
    reg.load_from_repo(repo)
    print('  UNEXPECTED')
except Exception as exc:
    print('  load_from_repo 抛:', type(exc).__name__, str(exc)[:70])

section('R2) 缓存损坏 → load_cached_index 抛异常（无 try/except）')
os.makedirs(os.path.join(HOME, 'regcache'), exist_ok=True)
ck = reg._url_to_cache_key('https://example.com/x')
with open(os.path.join(HOME, 'regcache', ck + '.json'), 'w') as f:
    f.write('{"url": "x", "cached_at": 1')
try:
    reg.load_cached_index('https://example.com/x')
    print('  UNEXPECTED')
except Exception as exc:
    print('  load_cached_index 抛:', type(exc).__name__, str(exc)[:70])

section('R3) invalidate_cache(None) 删除 cache_dir 内所有文件（不限 .json）')
keep = os.path.join(HOME, 'regcache', 'USER_DATA.txt')
with open(keep, 'w') as f:
    f.write('keep me')
print('  删前存在:', os.path.isfile(keep))
reg.invalidate_cache(None)
print('  删后存在:', os.path.isfile(keep), '（缓存目录里的非 json 文件被误删）')

section('R4) record_installation 无视 cache_dir，固定写 <HOME>/.actus/installed')
repo2, _ = make_repo()
os.environ['ACTUS_REPO_ROOT'] = repo2
reg2 = ActionRegistry(cache_dir=os.path.join(HOME, 'other_cache'))
reg2.record_installation('https://example.com/r', repo2)
inst_dir = os.path.join(HOME, '.actus', 'installed')
mpath = os.path.join(inst_dir, reg2._url_to_cache_key('https://example.com/r') + '.json')
print('  cache_dir =', reg2.cache_dir)
print('  manifest 落点 =', mpath, '| 落在 ~/.actus/installed:', os.path.isfile(mpath))

section('R5) 无签名 + trust_level=trusted：验签结果随"有没有 cryptography"变化（假通过）')
entry = RegistryEntry(id='demo.cat.a', name='A', version='1.0.0', description='',
                      category='cat', path='actions/cat/a.actus.md', author='demo',
                      tags=[], checksum='sha256:' + '0' * 64, signature=None,
                      trust_level='trusted')
print('  verify_signature(trusted, 无签名) =', reg.verify_signature(entry, repo))
print('  _verify_signature_fallback(同一条目) =',
      reg._verify_signature_fallback(entry, repo), '（无 cryptography 时走这里 → True）')

section('R6) fallback 只比 "sig.message == entry.checksum" → 可伪造 sig 文件')
sig = {'message': entry.checksum, 'signature': 'ZmFrZQ=='}
with open(os.path.join(repo, 'actions/cat/a.sig'), 'w') as f:
    f.write(json.dumps(sig))
entry_sig = RegistryEntry(id='demo.cat.a', name='A', version='1.0.0', description='',
                          category='cat', path='actions/cat/a.actus.md', author='demo',
                          tags=[], checksum=entry.checksum, signature='actions/cat/a.sig',
                          trust_level='community')
print('  _verify_signature_fallback(伪造 sig) =',
      reg._verify_signature_fallback(entry_sig, repo), '（message 就是公开 checksum）')

section('R7) 索引 path 可为仓库外绝对路径 → _entry_to_action 读取仓库外文件')
outside = os.path.join(HOME, 'outside.actus.md')
with open(outside, 'w', encoding='utf-8') as f:
    f.write('```json #!cfg\n{"id":"evil.x.y","name":"E"}\n```\n')
reg3 = ActionRegistry(cache_dir=os.path.join(HOME, 'c3'))
reg3._entries['evil.x.y'] = RegistryEntry(id='evil.x.y', name='E', version='1.0.0',
                                          description='', category='cat', path=outside,
                                          author='evil', tags=[],
                                          checksum='sha256:' + '0' * 64)
act = reg3._entry_to_action(reg3._entries['evil.x.y'], repo_dir=repo)
print('  _entry_to_action(path=仓库外绝对路径) →', '读到了' if act else 'None',
      '| 解析出 id =', act.meta.get('id') if act else None)
print('  verify_checksum 同样是 os.path.join(repo_dir, entry.path)')

section('R9) filter_by_quality() 不传 repo_dir → 找不到文件 → []')
reg4 = ActionRegistry(cache_dir=os.path.join(HOME, 'qc'))
reg4._entries['demo.cat.a'] = RegistryEntry(id='demo.cat.a', name='A', version='1.0.0',
                                            description='', category='cat',
                                            path='actions/cat/a.actus.md', author='demo',
                                            tags=[], checksum='sha256:' + '0' * 64)
print('  filter_by_quality() =', reg4.filter_by_quality())
print('  filter_by_quality(repo_dir=repo) =', len(reg4.filter_by_quality(repo_dir=repo)), '条')

section('R10) list_installed：任一 manifest 损坏 → 整个列表抛异常')
with open(os.path.join(HOME, '.actus', 'installed', 'broken.json'), 'w') as f:
    f.write('{oops')
try:
    reg.list_installed()
    print('  UNEXPECTED')
except Exception as exc:
    print('  list_installed 抛:', type(exc).__name__, str(exc)[:60])

section('R11) 索引与磁盘不一致：删掉动作文件后索引照旧返回（幽灵条目）')
repo3, apath3 = make_repo()
reg5 = ActionRegistry(cache_dir=os.path.join(HOME, 'c5'))
reg5.build_from_directory(repo3, write=True)
os.remove(apath3)
res = R.search_registry(repo3, query='demo')
print('  动作文件已删，search_registry 仍返回:', [e.id for e in res])

from vools.actus import omega_strong as O  # noqa: E402

section('O1) task_id 直接拼进文件路径 → 路径逃逸（相对/绝对）')
rel = O.OmegaStrong('../../escaped')
p = rel._save({'task_id': '../../escaped', 'records': [], 'max_rounds': 3})
print('  task_id="../../escaped" → 落盘:', p)
print('  是否逃出 omega_strong/ 目录:', os.path.dirname(p) != os.path.join(META, 'omega_strong'))
abso = O.OmegaStrong(os.path.join(HOME, 'abs_ledger'))
p2 = abso._save({'task_id': os.path.join(HOME, 'abs_ledger'), 'records': [], 'max_rounds': 3})
print('  task_id=绝对路径 → 落盘:', p2, '| 无视 ACTUS_META_DIR:', p2.startswith(HOME))

section('O2) 账本损坏 → load_ledger 静默返回空账本（随后写入覆盖历史）')
tid = 'task-corrupt'
O._save_ledger({'task_id': tid,
                'records': [{'id': 'spec:%s:r1' % tid, 'status': 'approved'}],
                'max_rounds': 3})
os.makedirs(os.path.join(META, 'omega_strong'), exist_ok=True)
with open(os.path.join(META, 'omega_strong', tid + '.json'), 'w') as f:
    f.write('{corrupt')
print('  损坏后 load_ledger records =', O.load_ledger(tid)['records'])
o = O.OmegaStrong(tid)
o.spec_create('a', '语料')
recs = O.load_ledger(tid)['records']
print('  之后 spec_create 落盘 records =', [(r['id'], r['status']) for r in recs])

section('O3) result_verify：deliverable 只判 not None，既不入记录也不校验')
tid2 = 'task-result'
o2 = O.OmegaStrong(tid2)
o2.spec_create('author1', '语料')
o2.spec_review('reviewer1', 'approve')
out = o2.result_verify('reviewer2', 'pass', deliverable={})
rec = [r for r in O.load_ledger(tid2)['records'] if r['spec_type'] == 'result'][-1]
print('  result_verify(deliverable={}) →', out['status'],
      '| 记录含交付物摘要 =', 'deliverable' in rec['content'],
      '| 记录内容 =', rec['content'][:90])

section('O4) check_record 只信调用方传入的 ok=True → 没跑命令也能过 gate')
tid3 = 'task-check'
o3 = O.OmegaStrong(tid3)
print('  check_record({"ok": True}) →', o3.check_record({'ok': True})['status'])
print('  check_gate([gate:required]) →', o3.check_gate({'goal': 'x [gate:required]'}))
print('  记录里 cmd 字段 =', json.loads(O.load_ledger(tid3)['records'][-1]['content']).get('cmd'))

section('O5) 并发丢更新：两实例各自 load→append→save，后写覆盖先写')
tid4 = 'task-race'
a = O.OmegaStrong(tid4)
b = O.OmegaStrong(tid4)
da = a._load()
db = b._load()
da['records'].append({'id': 'spec:%s:rA' % tid4, 'status': 'pending'})
db['records'].append({'id': 'spec:%s:rB' % tid4, 'status': 'pending'})
a._save(da)
b._save(db)
ids = [r['id'] for r in O.load_ledger(tid4)['records']]
print('  最终记录:', ids, '| A 的记录还在?', 'spec:%s:rA' % tid4 in ids)

section('~/.actus 真实目录零变化')
base = os.path.join(os.path.expanduser('~'), '.actus')
count = 0
if os.path.isdir(base):
    for dp, _d, fs in os.walk(base):
        count += len(fs)
print('  真实 ~/.actus 文件数:', count, '（本次审计全部落在 tmp HOME）')
