# -*- coding: utf-8 -*-
"""只读验证：cost.get_cost_summary 的账本完整性信号（改前/改后对比）。"""
import json, os, sys, tempfile
from datetime import datetime
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import _ai_local_bootstrap; _ai_local_bootstrap.install()
from vools.actus import cost

def run(rows, label):
    tmp = tempfile.mkdtemp()
    cost.COSTS_DIR = tmp
    month = datetime.now().strftime('%Y-%m')
    with open(os.path.join(tmp, month + '.jsonl'), 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(r + '\n')
    print('### %s（%d 行）' % (label, len(rows)))
    for r in rows:
        print('   |', r[:90])
    summary = cost.get_cost_summary(month)
    print('   返回体:', json.dumps(summary, ensure_ascii=False, sort_keys=True))
    print('   ledger_complete =', summary['ledger_complete'],
          '| skipped =', summary['skipped_lines'], summary['skipped_reasons'],
          '| incomplete =', summary['incomplete_lines'], summary['incomplete_reasons'])
    return summary

# 1) 与审计时完全相同的 fixture：1 合法 + 2 坏
orig = run([
    json.dumps({'cost_usd': 1.5, 'provider': 'openai'}),
    '{ this is not json',
    json.dumps({'cost_usd': 'boom', 'provider': 'x'}),
], '原审计 fixture')

# 2) 全覆盖分类
full = run([
    json.dumps({'cost_usd': 1.5, 'provider': 'openai'}),      # 合法
    '{ this is not json',                                     # bad_json
    json.dumps(['not', 'an', 'object']),                      # not_object
    json.dumps({'cost_usd': 'boom', 'provider': 'x'}),        # bad_cost_usd
    json.dumps({'provider': 'p1'}),                           # missing_cost_usd（按 0 计入）
    json.dumps({'cost_usd': 2.0}),                            # missing_provider（归 unknown）
    json.dumps({'cost_usd': 0.5, 'provider': 123}),           # bad_provider（归 unknown）
    '',                                                       # 空行：忽略，不算跳过
], '分类全覆盖')

# 3) 既有语义不变：合法行 total/calls 与旧算法一致
valid_only = [json.dumps({'cost_usd': 1.5, 'provider': 'openai'}),
              json.dumps({'cost_usd': 2.0, 'provider': 'anthropic'})]
clean = run(valid_only, '仅合法行')
print('   total_usd 期望 3.5 ->', clean['total_usd'], '| calls 期望 2 ->', clean['calls'])

# 4) check_budget：数学不变 + 透传完整性
print('\n### check_budget（在原审计 fixture 上，阈值 $10）')
cost.COSTS_DIR = tempfile.mkdtemp()
month = datetime.now().strftime('%Y-%m')
open(os.path.join(cost.COSTS_DIR, month + '.jsonl'), 'w', encoding='utf-8').write(
    json.dumps({'cost_usd': 1.5, 'provider': 'openai'}) + '\n{ broken\n')
status = cost.check_budget(10.0)
print('   ', json.dumps(status, ensure_ascii=False, sort_keys=True))

# 5) 空目录：字段同构
empty = cost.get_cost_summary(month) if False else cost.get_cost_summary('1999-01')
print('\n### 不存在的账本:', json.dumps(empty, ensure_ascii=False, sort_keys=True))

# 6) 账本完整时 ledger_complete 必须为 True
print('\n### 完整账本 ledger_complete =', clean['ledger_complete'])
