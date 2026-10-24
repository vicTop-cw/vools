# -*- coding: utf-8 -*-
"""最后一批复现：
BUG-S2 (validate.check_triggers): docstring 承诺「expr 必须是合法 cron 表达式」，
  实际 cron_field_re 只查形状不查值域 → '99 99 * * *'（99 分 99 时）被判合法。
  另 '1-5' 反向范围（5-1）同样放行。
BD-FM1 (frontmatter.strip_frontmatter): docstring「文件不以 --- 开头 → 原样返回」，
  实际 _split 会跳过前导空行再匹配 → 前置空行的 AIGC 块被剥（返回≠原文，且原样返回
  承诺落空）。
BD-SC1 (exec_iface._ScatteredIface): docstring「confirmed=False 时只校验不执行」
  「dry_run=True → confirmed=False」。实际 confirmed 只是人工确认位，trusted 动作
  confirmed=False 照样真跑 → 统一接口 dry_run=True 对 scattered 源同样真执行。
"""
import sys, os, json, tempfile, time
sys.path.insert(0, r'E:\IDEProjects\AI\vools\actus')

print('== BUG-S2: check_triggers 值域不查 ==')
from vools.actus.validate import check_triggers
errs = check_triggers({'triggers': [{'type': 'cron', 'expr': '99 99 * * *'}]})
print("  '99 99 * * *' errors:", errs)
assert errs == [], '期望按“合法 cron”打回'
errs2 = check_triggers({'triggers': [{'type': 'cron', 'expr': '0 0 31 2 *'}]})  # 2月31日
print("  '0 0 31 2 *'（2月31）errors:", errs2)
assert errs2 == []
print('  → 确认：分钟 99/小时 99/二月卅一 全部放行，docstring“合法 cron 表达式”仅形状校验')

print()
print('== BD-FM1: strip_frontmatter 前导空行 ≠ 原样返回 ==')
from vools.actus.frontmatter import strip_frontmatter
text = '\n\n---\nAIGC: 1\n---\n正文\n'
out = strip_frontmatter(text)
print('  in  repr:', repr(text[:24]))
print('  out repr:', repr(out[:24]))
assert out != text, 'docstring：不以 --- 开头 → 原样返回'
print('  → 确认：文件首字符是换行（不以 --- 开头），AIGC 块仍被剥离——与文档“原样返回”不符')

print()
print('== BD-SC1: scattered 源 dry_run=True 照样真执行（trusted 动作）==')
tmp = tempfile.mkdtemp(prefix='sc_')
os.environ['ACTUS_REPO_ROOT'] = tmp
marker = os.path.join(tmp, 'RAN.txt')
act_dir = os.path.join(tmp, 'mydir')
os.makedirs(act_dir)
os.makedirs(os.path.join(tmp, 'tests'))
open(os.path.join(tmp, 'tests', 't_sc.py'), 'w').write('# sc.trusted.run\n')
CFG = {'id': 'sc.trusted.run', 'name': 'ScRun', 'version': '1.0.0',
       'trust': 'trusted', 'entry': 'main', 'platform': ['desktop'], 'kind': 'exec'}
p = os.path.join(act_dir, 'sc.actus.md')
open(p, 'w', encoding='utf-8').write(
    '```json #!cfg\n' + json.dumps(CFG) + '\n```\n\n'
    '#!entry main\n```python #!tag=main\n'
    f"open(r'{marker}','w').write('executed')\n" + '```\n')

from vools.actus.exec_iface import executor_for, ExecutionContext
class A:
    meta = {'id': 'sc.trusted.run'}
    path = p
res = executor_for('scattered').execute(A(),
                                        ExecutionContext(params={}, dry_run=True))
print('  dry_run=True status:', res.status, '| kind:', res.error_kind,
      '| error:', res.error[:300])
print('  副作用标记文件存在（动作真的跑了）:', os.path.isfile(marker))
assert os.path.isfile(marker), 'dry_run 不应产生副作用'
print('  → 确认：_ScatteredIface docstring「dry_run=True→confirmed=False→只校验不执行」落空，'
      'trusted 零散动作在预览模式下真实执行并落副作用')
print('LAST BATCH REPROS OK')
