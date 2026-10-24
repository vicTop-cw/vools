# -*- coding: utf-8 -*-
"""BUG-I3b（正式版）：purpose/industry 不在 action.schema.json 的 enum 里
  （schema properties 只有 trust/kind/license/pricing 带 enum）——
  所以 purpose: [Transform] 在装了 jsonschema 的正常环境也能通过必填校验，
  但 build_index 用 brief 原值做 by_purpose 键 → filter_by_dimension('purpose','transform')
  查不到。全程默认环境（jsonschema 已安装），无需 fallback。"""
import sys, os, json, tempfile
sys.path.insert(0, r'E:\IDEProjects\AI\vools\actus')
from vools.actus import indexer
from vools.actus.validate import validate_action

tmp = tempfile.mkdtemp(prefix='i3b_')
os.environ['ACTUS_REPO_ROOT'] = tmp
act = os.path.join(tmp, 'actions'); os.makedirs(act)
CFG = {'id': 'cap.purpose', 'name': 'CapP', 'version': '1.0.0', 'trust': 'sandbox',
       'entry': 'main', 'platform': ['desktop'], 'purpose': ['Transform', 'Notify']}
p = os.path.join(act, 'p.actus.md')
open(p, 'w', encoding='utf-8').write(
    '```json #!cfg\n' + json.dumps(CFG) + '\n```\n\n'
    '#!entry main\n```python #!tag=main\nprint(1)\n```\n')

a = indexer.scan_actions(act, validate=True)
errs = validate_action(a['cap.purpose'])
print('validate_action errors:', errs)
assert not any('purpose' in e for e in errs)
idx = indexer.build_index(actions_dir=act, meta_dir=os.path.join(tmp, '_meta'))
print('by_purpose keys:', list(idx['by_purpose']))
lo = indexer.filter_by_dimension('purpose', 'transform', meta_dir=os.path.join(tmp, '_meta'))
hi = indexer.filter_by_dimension('purpose', 'Transform', meta_dir=os.path.join(tmp, '_meta'))
print("filter(purpose='transform') →", lo)
print("filter(purpose='Transform') →", hi)
assert lo == [] and hi == ['cap.purpose']
print('→ 确认：正常环境（jsonschema 在）purpose 原值入索引，闭集小写值查不到该动作；'
      'validate/constants 的 is_known_purpose 用 lower() 判合法（口径分叉）')
print('BUG-I3b OK')
