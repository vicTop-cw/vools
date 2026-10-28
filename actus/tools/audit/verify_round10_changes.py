# -*- coding: utf-8 -*-
"""验收 ① 结构校验 / ③ security 分级 / 性能与影响面（修正版）。"""
import glob
import json
import os
import sys
import tempfile
import time

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
HOME = tempfile.mkdtemp(prefix='v20_home2_')
META = tempfile.mkdtemp(prefix='v20_meta2_')
os.environ['HOME'] = HOME
os.environ['USERPROFILE'] = HOME
os.environ['ACTUS_META_DIR'] = META
sys.path.insert(0, os.path.join(REPO, 'vools'))
sys.path.insert(0, os.path.join(REPO, 'tests'))
import _ai_local_bootstrap  # noqa: E402
_ai_local_bootstrap.install()
from vools.actus.model import parse_cfg_from_file  # noqa: E402
from vools.actus.validate import (validate_action, validate_schema_md,  # noqa: E402
                                  split_validation, is_valid)


def section(t):
    print('\n=== %s ===' % t)


def write_cfg_action(cfg, code):
    d = tempfile.mkdtemp()
    p = os.path.join(d, 'a.actus.md')
    with open(p, 'w', encoding='utf-8') as f:
        f.write('```json #!cfg\n%s\n```\n\n```python #!run tag=main\n%s\n```\n'
                % (json.dumps(cfg), code))
    return parse_cfg_from_file(p)


def write_schema_md(meta_yaml, body):
    d = tempfile.mkdtemp()
    p = os.path.join(d, 'a.actus.schema.md')
    with open(p, 'w', encoding='utf-8') as f:
        f.write('---\n%s\n---\n\n%s' % (meta_yaml, body))
    return parse_cfg_from_file(p)


section('① 结构校验：缺章节 → 报错；种子动作不受影响')
bad = write_schema_md(
    'id: a.bad.x\nname: B\nversion: 1.0.0\ntrust: sandbox\nkind: exec\n'
    'entry: main\nplatform: [desktop]\nargs: {type: object}\n'
    'dependencies: {pip: [requests]}',
    '```python #!run tag=main\nprint(1)\n```\n')
print('  缺三章节:', validate_schema_md(bad))
print('  种子动作:')
for name in ('calculator', 'image-viewer', 'text-editor', 'todo-list'):
    path = os.path.join(REPO, 'vools', 'actus', 'actions', 'basics',
                        name + '.actus.schema.md')
    print('   %-14s %s' % (name, validate_schema_md(parse_cfg_from_file(path))))

section('③-A validate_action：低信任命中 → security 错误；高信任 → warning 提示')
code = ('import subprocess\nsubprocess.run("x", shell=True)\n'
        'api_key = "sk-AAAAAAAAAAAAAAAAAAAA"')
low = write_cfg_action({'id': 'a.low.x', 'name': 'L', 'version': '1.0.0',
                        'trust': 'sandbox', 'kind': 'exec', 'entry': 'main',
                        'platform': ['desktop']}, code)
errs_low = validate_action(low)
print('  sandbox errors =', errs_low, '| is_valid =', is_valid(errs_low))
high = write_cfg_action({'id': 'a.high.x', 'name': 'H', 'version': '1.0.0',
                         'trust': 'trusted', 'kind': 'exec', 'entry': 'main',
                         'platform': ['desktop']}, code)
errs_high = validate_action(high)
real, notes = split_validation(errs_high)
print('  trusted real_errors =', real)
print('  trusted notes =', [n[:70] for n in notes], '| is_valid =', is_valid(errs_high))

section('③-B 影响面：现有动作接入安全检查后是否新增失败')
failed = []
for f in glob.glob(os.path.join(REPO, 'vools/actus/actions/**/*.actus*.md'),
                   recursive=True):
    a = parse_cfg_from_file(f)
    errs = (validate_schema_md(a) if f.endswith('.schema.md') else validate_action(a))
    if not is_valid(errs):
        failed.append((os.path.basename(f), split_validation(errs)[0][:2]))
print('  仍失败的动作:', failed or '无')

section('③-C 性能：check_security 增量')
actions = [parse_cfg_from_file(f) for f in
           glob.glob(os.path.join(REPO, 'vools/actus/actions/**/*.actus*.md'),
                     recursive=True)]
rounds = 20
t0 = time.perf_counter()
for _ in range(rounds):
    for a in actions:
        validate_action(a)
full = time.perf_counter() - t0
from vools.actus import validate as V  # noqa: E402
orig = V.check_security
V.check_security = lambda action: []
try:
    t0 = time.perf_counter()
    for _ in range(rounds):
        for a in actions:
            validate_action(a)
    base = time.perf_counter() - t0
finally:
    V.check_security = orig
print('  %d 个动作 × %d 轮: 完整 %.0f ms | 不扫描 %.0f ms | 扫描增量 %.1f ms/轮'
      % (len(actions), rounds, full * 1000, base * 1000,
         (full - base) * 1000 / rounds))

section('③-D executor：低信任 + 危险内容 → permission_denied')
from vools.actus import executor as EX  # noqa: E402
repo = tempfile.mkdtemp(prefix='v20_repo2_')
os.makedirs(os.path.join(repo, 'actions'))
import shutil  # noqa: E402
shutil.copy(os.path.join(REPO, 'vools/actus/actions/basics/calculator.actus.schema.md'),
            os.path.join(repo, 'actions', 'calculator.actus.schema.md'))
with open(os.path.join(repo, 'actions', 'evil.actus.md'), 'w', encoding='utf-8') as f:
    f.write('```json #!cfg\n%s\n```\n\n%s' % (json.dumps(
        {'id': 'a.evil.x', 'name': 'E', 'version': '1.0.0', 'trust': 'sandbox',
         'kind': 'exec', 'entry': 'main', 'platform': ['desktop']}),
        '```python #!run tag=main\nimport subprocess\nsubprocess.run("x", shell=True)\n```\n'))
os.environ['ACTUS_REPO_ROOT'] = repo
res = EX.execute('a.evil.x', {}, actions_dir=os.path.join(repo, 'actions'),
                 confirmed=True, meta_dir=os.path.join(META, 'm2'),
                 artifacts_dir=os.path.join(META, 'a2'))
print('  execute status =', res.get('status'),
      '| error =', (res.get('error') or {}).get('message'))

section('③-E 产物目录策略：blocked_paths → 拒绝')
from vools.actus import security as S  # noqa: E402
policy = S.get_security_scanner().policy
orig_blocked = list(policy.blocked_paths)
try:
    policy.blocked_paths = orig_blocked + [META]
    try:
        EX._check_artifacts_access(os.path.join(META, 'art'))
        print('  UNEXPECTED: 未拒绝')
    except Exception as exc:
        print('  →', type(exc).__name__, '|', str(exc)[:80])
finally:
    policy.blocked_paths = orig_blocked
