# -*- coding: utf-8 -*-
"""验收 P1-A/B/C + P2 批（registry.py / omega_strong.py / cli.py）。全 tmp 隔离。"""
import json
import os
import sqlite3  # noqa: F401  (保留统一风格)
import subprocess
import sys
import tempfile
import threading
import time
from unittest import mock

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
HOME = tempfile.mkdtemp(prefix='v19_home_')
META = tempfile.mkdtemp(prefix='v19_meta_')
os.environ['HOME'] = HOME
os.environ['USERPROFILE'] = HOME
os.environ['ACTUS_META_DIR'] = META
sys.path.insert(0, os.path.join(REPO, 'vools'))
sys.path.insert(0, os.path.join(REPO, 'tests'))
import _ai_local_bootstrap  # noqa: E402
_ai_local_bootstrap.install()
from vools.actus import registry as R  # noqa: E402
from vools.actus.registry import ActionRegistry, RegistryEntry  # noqa: E402
from vools.actus import omega_strong as O  # noqa: E402
from vools.actus.errors import ActionError  # noqa: E402


def section(title):
    print('\n=== %s ===' % title)


def make_repo(with_index=False):
    repo = tempfile.mkdtemp(prefix='v19_repo_')
    os.makedirs(os.path.join(repo, 'actions', 'cat'))
    cfg = {"id": "demo.cat.a", "name": "A", "version": "1.0.0", "description": "d",
           "tags": ["x"], "kind": "exec", "entry": "main",
           "platform": ["desktop"], "trust": "trusted"}
    path = os.path.join(repo, 'actions', 'cat', 'a.actus.md')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('```json #!cfg\n%s\n```\n\n```python #!run tag=main\nprint(1)\n```\n'
                % json.dumps(cfg))
    if with_index:
        ActionRegistry(cache_dir=os.path.join(HOME, 'c0')).build_from_directory(repo, write=True)
    return repo, path


# ═══════════════ P1-A ═══════════════
section('P1-A1) write_index 原子：写入失败不得破坏旧索引、不留 tmp')
repo, apath = make_repo(with_index=True)
reg = ActionRegistry(cache_dir=os.path.join(HOME, 'c1'))
index = reg.build_from_directory(repo, write=False)
registry_path = os.path.join(repo, '.actus.registry.json')
with open(registry_path, 'rb') as f:
    original = f.read()
with mock.patch.object(R.json, 'dump', side_effect=RuntimeError('磁盘满')):
    try:
        reg.write_index(index, repo)
        print('  UNEXPECTED: 没抛')
    except RuntimeError:
        print('  写入失败按预期抛 RuntimeError')
with open(registry_path, 'rb') as f:
    print('  旧索引字节未被破坏:', f.read() == original)
print('  目录里 tmp 残留:', [n for n in os.listdir(repo) if '.tmp' in n] or '无')

section('P1-A2) 损坏索引：load_from_file 返回空索引 + 明确信号（不抛）')
repo_c, _ = make_repo()
with open(os.path.join(repo_c, '.actus.registry.json'), 'w', encoding='utf-8') as f:
    f.write('{ this is not json')
reg_c = ActionRegistry(cache_dir=os.path.join(HOME, 'c2'))
index_c = reg_c.load_from_file(os.path.join(repo_c, '.actus.registry.json'))
print('  actions =', index_c.get('actions'), '| corrupt =', index_c.get('corrupt'),
      '| problems 条数 =', len(index_c.get('problems') or {}))

section('P1-A3) load_from_repo：损坏索引 → 回退内存重建，且不落盘')
before_files = set(os.listdir(repo_c))
rebuilt = reg_c.load_from_repo(repo_c)
after_files = set(os.listdir(repo_c))
print('  重建后 actions =', [e['id'] for e in rebuilt.get('actions', [])],
      '| rebuilt_from_memory =', rebuilt.get('rebuilt_from_memory'))
print('  仓库文件未变（未落盘）:', before_files == after_files,
      '| 索引仍是坏文件:', open(os.path.join(repo_c, '.actus.registry.json')).read().startswith('{ this'))

section('P1-A4) 陈旧索引：删掉动作文件 → load_from_repo 重建（不再返回幽灵条目）')
repo_s, apath_s = make_repo(with_index=True)
reg_s = ActionRegistry(cache_dir=os.path.join(HOME, 'c3'))
print('  删文件前:', [e.id for e in reg_s.search()] if reg_s.load_from_repo(repo_s) else None)
os.remove(apath_s)
reg_s2 = ActionRegistry(cache_dir=os.path.join(HOME, 'c3b'))
res = reg_s2.load_from_repo(repo_s)
print('  删文件后 actions =', [e['id'] for e in res.get('actions', [])],
      '| stale_index =', res.get('stale_index'))

# ═══════════════ P1-B ═══════════════
section('P1-B) CLI registry validate：真校验（4 项全错 → rc=1 且逐项点名）')
env = dict(os.environ, PYTHONPATH=os.path.join(REPO, 'vools'), PYTHONIOENCODING='utf-8')
fake = tempfile.mkdtemp(prefix='v19_fake_')
bad_index = {'name': 'x', 'version': '1.0.0', 'actions': [
    {'id': 'demo.fake.a', 'name': '', 'version': 'not-semver', 'description': '',
     'category': '', 'path': 'actions/missing.actus.md', 'author': '',
     'tags': [], 'checksum': 'sha256:' + '0' * 64, 'trust_level': 'trusted'}]}
with open(os.path.join(fake, '.actus.registry.json'), 'w', encoding='utf-8') as f:
    json.dump(bad_index, f)
p = subprocess.run([sys.executable, '-m', 'vools.actus.cli', 'registry', 'validate',
                    '--index', os.path.join(fake, '.actus.registry.json')],
                   capture_output=True, text=True, encoding='utf-8',
                   errors='replace', cwd=fake, env=env, timeout=120)
print('  rc =', p.returncode)
for line in (p.stdout or '').strip().splitlines():
    print('   ', line)

section('P1-B2) 正常索引 → rc=0 全通过')
repo_v, _ = make_repo(with_index=True)
p2 = subprocess.run([sys.executable, '-m', 'vools.actus.cli', 'registry', 'validate',
                     '--index', os.path.join(repo_v, '.actus.registry.json')],
                    capture_output=True, text=True, encoding='utf-8',
                    errors='replace', cwd=repo_v, env=env, timeout=120)
print('  rc =', p2.returncode, '|', (p2.stdout or '').strip().splitlines()[-1:])

# ═══════════════ P1-C ═══════════════
section('P1-C) omega 账本 task_id 路径逃逸 → 拒绝')
for bad_id in ('../../escaped', '/tmp/abs_ledger', 'a/b', '..', ''):
    try:
        O.OmegaStrong(bad_id).spec_create('author', '语料')
        print('  %-18r -> UNEXPECTED 未拒绝' % (bad_id,))
    except ActionError as exc:
        print('  %-18r -> ActionError(%s)' % (bad_id, exc.code))
print('  逃逸文件是否写出:', os.path.exists(os.path.join(META, 'escapede.json')),
      '| 合法 id 可写:', bool(O.OmegaStrong('task-ok').spec_create('a', '语料')['ok']))

# ═══════════════ P2 ═══════════════
section('P2-1) 退化验签 fail-closed（签名条目不再"哈希相等"即过）')
entry_sig = RegistryEntry(id='demo.cat.a', name='A', version='1.0.0', description='',
                          category='cat', path='actions/cat/a.actus.md', author='demo',
                          tags=[], checksum='sha256:' + '0' * 64,
                          signature='actions/cat/a.sig', trust_level='community')
print('  _verify_signature_fallback(签名条目) =', reg._verify_signature_fallback(entry_sig, repo),
      '| warnings:', reg.warnings[-1:])

section('P2-2) 安装清单目录可配置（manifest_dir / ACTUS_INSTALLED_DIR）')
repo_i, _ = make_repo()
m_dir = os.path.join(HOME, 'custom_manifests')
reg_i = ActionRegistry(cache_dir=os.path.join(HOME, 'c4'), manifest_dir=m_dir)
reg_i.record_installation('https://example.com/r', repo_i)
print('  显式 manifest_dir 生效:', os.path.isfile(
    os.path.join(m_dir, reg_i._url_to_cache_key('https://example.com/r') + '.json')))
os.environ['ACTUS_INSTALLED_DIR'] = os.path.join(HOME, 'env_manifests')
reg_i2 = ActionRegistry(cache_dir=os.path.join(HOME, 'c4b'))
reg_i2.record_installation('https://example.com/r2', repo_i)
print('  ACTUS_INSTALLED_DIR 生效:', os.path.isdir(os.path.join(HOME, 'env_manifests')))
os.environ.pop('ACTUS_INSTALLED_DIR', None)

section('P2-4/9) 索引 path 越界：加载时跳过 + 记录 problems；不读仓库外文件')
outside = os.path.join(HOME, 'outside.actus.md')
with open(outside, 'w', encoding='utf-8') as f:
    f.write('```json #!cfg\n{"id":"evil.x.y","name":"E"}\n```\n')
repo_t, _ = make_repo(with_index=True)
idx_file = os.path.join(repo_t, '.actus.registry.json')
with open(idx_file, 'r', encoding='utf-8') as f:
    data = json.load(f)
data['actions'].append(dict(data['actions'][0], id='evil.x.y', path=outside))
data['actions'].append(dict(data['actions'][0], id='evil.rel', path='../../../etc/passwd'))
with open(idx_file, 'w', encoding='utf-8') as f:
    json.dump(data, f)
reg_t = ActionRegistry(cache_dir=os.path.join(HOME, 'c5'))
loaded = reg_t.load_from_file(idx_file)
print('  problems:', list((loaded.get('problems') or {}).keys()))
print('  evil 条目未进内存:', reg_t.get('evil.x.y') is None and reg_t.get('evil.rel') is None)
print('  _entry_to_action(绝对 path) =', reg_t._entry_to_action(
    RegistryEntry(id='evil.x.y', name='E', version='1.0.0', description='', category='c',
                  path=outside, author='e', tags=[], checksum='x'), repo_t))

section('P2-5) 损坏账本：备份 .corrupt-* 且拒绝覆盖（历史不丢）')
tid = 'task-corrupt'
O._save_ledger({'task_id': tid, 'records': [{'id': 'spec:%s:r1' % tid,
                                             'status': 'approved'}], 'max_rounds': 3})
ledger_path = os.path.join(META, 'omega_strong', tid + '.json')
with open(ledger_path, 'w', encoding='utf-8') as f:
    f.write('{corrupt')
broken = O.load_ledger(tid)
print('  corrupt =', broken.get('corrupt'), '| backup =', bool(broken.get('corrupt_backup')),
      '| 备份文件存在:', os.path.isfile(broken.get('corrupt_backup') or ''))
try:
    O.OmegaStrong(tid).spec_create('a', 'x')
    print('  UNEXPECTED: 竟然覆盖写入了')
except ActionError as exc:
    print('  写侧拒绝覆盖:', exc.code, '|', str(exc)[:46])

section('P2-6) result_verify 记录交付物指纹')
tid2 = 'task-result2'
o2 = O.OmegaStrong(tid2)
o2.spec_create('author1', '语料')
o2.spec_review('reviewer1', 'approve')
out = o2.result_verify('reviewer2', 'pass', deliverable={'k': 'v'})
rec = [r for r in O.load_ledger(tid2)['records'] if r['spec_type'] == 'result'][-1]
content = json.loads(rec['content'])
print('  deliverable 指纹 =', content.get('deliverable'))

section('P2-7) check_record 要求 cmd+exit_code；ok 不再可信')
tid3 = 'task-check3'
o3 = O.OmegaStrong(tid3)
try:
    o3.check_record({'ok': True})
    print('  UNEXPECTED: ok=True 也通过了')
except ActionError as exc:
    print('  只给 ok=True → 拒绝:', exc.code)
print('  cmd+exit_code=0 →', o3.check_record({'cmd': 'pytest -q', 'exit_code': 0})['status'])
print('  gate =', o3.check_gate({'goal': 'x [gate:required]'}))
print('  cmd+exit_code=1 →', o3.check_record({'cmd': 'false', 'exit_code': 1})['status'],
      '| gate =', o3.check_gate({'goal': 'x [gate:required]'}))

section('P2-8) 账本并发写：20 线程各 append 1 条 → 全保留')
tid4 = 'task-race2'
O.OmegaStrong(tid4).spec_create('seed', 'x')     # 先建账本

def worker(i):
    try:
        O.OmegaStrong(tid4)._append({'id': 'check:%s:r%d' % (tid4, i),
                                     'task_id': tid4, 'spec_type': 'check',
                                     'status': 'passed', 'content': '{}',
                                     'created_at': O._now_iso(),
                                     'updated_at': O._now_iso()})
    except ActionError as exc:
        print('  worker', i, '失败:', exc.code)

threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
for t in threads:
    t.start()
for t in threads:
    t.join()
ids = [r['id'] for r in O.load_ledger(tid4)['records']]
print('  记录数 =', len(ids), '（期望 21 = 1 语料 + 20 check）')

section('P2-9) list_installed 跳过坏清单并记 warning')
m_dir2 = os.path.join(HOME, 'm2')
os.makedirs(m_dir2, exist_ok=True)
with open(os.path.join(m_dir2, 'ok.json'), 'w') as f:
    json.dump({'url': 'u', 'actions': []}, f)
with open(os.path.join(m_dir2, 'broken.json'), 'w') as f:
    f.write('{oops')
reg_l = ActionRegistry(cache_dir=os.path.join(HOME, 'c6'), manifest_dir=m_dir2)
print('  manifests =', len(reg_l.list_installed()), '| warnings =', len(reg_l.warnings))

section('P2-10) filter_by_quality 缺 repo_dir → 明确报错（不再假空）')
try:
    ActionRegistry(cache_dir=os.path.join(HOME, 'c7')).filter_by_quality()
    print('  UNEXPECTED')
except ValueError as exc:
    print('  缺 repo_dir →', str(exc)[:60])

section('P2-11) 构造 ActionRegistry 不再创建 cache 目录')
fresh = os.path.join(HOME, 'never_created_cache')
print('  构造前:', os.path.isdir(fresh))
ActionRegistry(cache_dir=fresh)
print('  构造后:', os.path.isdir(fresh))

section('P2-12) check_gate 新鲜度按 datetime 比较（字符串比较会误判）')
tid5 = 'task-fresh'
o5 = O.OmegaStrong(tid5)
o5.check_record({'cmd': 'pytest', 'exit_code': 0})
# created_at 是 +08:00；task_updated_at 用 UTC 表示"更早" → 字符串比较会误判 stale，
# datetime 比较应判 fresh
utc_earlier = '2026-01-01T00:00:00+00:00'
print('  gate（任务更早） =', o5.check_gate({'goal': 'x [gate:required]'},
                                            task_updated_at=utc_earlier))
utc_later = '2099-01-01T00:00:00+00:00'
print('  gate（任务更晚） =', o5.check_gate({'goal': 'x [gate:required]'},
                                            task_updated_at=utc_later))

section('~/.actus 真实目录文件数（应为独立 HOME 之外的常量）')
print('  当前 HOME 下 .actus 文件数:',
      sum(len(fs) for _r, _d, fs in os.walk(os.path.join(HOME, '.actus'))))
