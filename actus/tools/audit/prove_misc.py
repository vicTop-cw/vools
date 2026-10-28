# -*- coding: utf-8 -*-
"""只读审计：为 4 条候选缺陷取证（不碰产品代码，全部临时目录）。"""
import json, os, sys, tempfile
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import _ai_local_bootstrap; _ai_local_bootstrap.install()

print('### A) mdtest 的 `from vools.actus import pytest_compat` 是否真的炸')
try:
    import vools.actus.mdtest as mdtest
    print('  import vools.actus.mdtest -> OK（未炸）')
except Exception as exc:
    print('  import vools.actus.mdtest -> %s: %s' % (type(exc).__name__, exc))

print('\n### B) cost.get_cost_summary 静默跳过坏账行')
from vools.actus import cost
tmp = tempfile.mkdtemp()
cost.COSTS_DIR = tmp
month = __import__('datetime').datetime.now().strftime('%Y-%m')
path = os.path.join(tmp, month + '.jsonl')
with open(path, 'w', encoding='utf-8') as f:
    f.write(json.dumps({'cost_usd': 1.5, 'provider': 'openai'}) + '\n')
    f.write('{ this is not json\n')                                  # 坏行1：JSON 坏了
    f.write(json.dumps({'cost_usd': 'boom', 'provider': 'x'}) + '\n')  # 坏行2：类型不对
print('  账本内容（1 好 + 2 坏）:')
for line in open(path, encoding='utf-8'):
    print('   ', line.rstrip())
summary = cost.get_cost_summary(month)
print('  -> get_cost_summary =', summary)
print('  -> 是否透出任何错误标记:', 'error' in summary or 'skipped' in summary)

print('\n### C) history.json 损坏 vs 没有历史 是否可区分')
from vools.actus.export import load_run_history
meta = tempfile.mkdtemp(); os.makedirs(os.path.join(meta, 'runs'), exist_ok=True)
empty = load_run_history(meta)
open(os.path.join(meta, 'runs', 'history.json'), 'w', encoding='utf-8').write('{ broken json')
corrupt = load_run_history(meta)
print('  没有文件 ->', empty)
print('  文件损坏 ->', corrupt)
print('  -> 两者可区分?', empty != corrupt or 'NO：都是空列表')

print('\n### D) analyze_actions 的 builtin 依赖是否恒判 ok（不校验真实性）')
from vools.actus.probe.actions import _check_simple_dep
for name in ('dialog', 'this_builtin_does_not_exist_xyz', ''):
    print('  builtin %-32r -> %r' % (name, _check_simple_dep('builtin', name, None)))
