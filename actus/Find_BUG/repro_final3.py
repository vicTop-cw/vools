# -*- coding: utf-8 -*-
"""最后三个点：
BD-FM2: 单个元数据块内含**嵌套** generated-by:（如 ai: 子键、provenance: 子键）时，
  ln.strip().startswith('generated-by:') 不区分缩进 → 整块被判 AIGC →
  strip_frontmatter 把动作唯一元数据块剥掉（正是注释里点名要防的存量 bug 的回归面）。
BD-X2: executor 依赖预检 hard_missing 早退（L227-237）不经 finish()——
  exec_id 已领用，但无 runs 记录/无 status.json/无指标/无事件，
  且回执缺 record/exec_id 之外的 finish 附加键（mode/env_prefix）。docstring
  「全程留痕」落空——对照：ActionError 路径都有留痕。
BD-QS: quality.is_maintained 公开 API 对 None 抛 TypeError（只捕 OSError），
  与 quality_scale 内部归一（path or ''）口径不一致——独立调用面（CLI/测试替身）暴露。
"""
import sys, os, json, tempfile, time
sys.path.insert(0, r'E:\IDEProjects\AI\vools\actus')

print('== BD-FM2: 元数据块内嵌套 generated-by: 触发误判 ==')
from vools.actus.frontmatter import strip_frontmatter, parse_action_metadata, _split_frontmatter_blocks
text = ('---\n'
        'id: actus.nested\n'
        'name: NestedAI\n'
        'version: 1.0.0\n'
        'trust: sandbox\n'
        'entry: main\n'
        'ai:\n'
        '  generated: true\n'
        '  generated-by: claude\n'
        '---\n'
        '#!entry main\n'
        '```python #!tag=main\nprint(1)\n```\n')
blocks, body = _split_frontmatter_blocks(text)
print('  blocks kinds:', [k for k, _ in blocks])
assert blocks[0][0] == 'aigc', '唯一元数据块被误判成 AIGC'
meta, rem = parse_action_metadata(text)
print('  parse_action_metadata →', meta)
assert meta == {}, meta
s = strip_frontmatter(text)
print('  strip_frontmatter 后正文开头:', repr(s[:40]))
assert 'id: actus.nested' not in s, 'id 应保留（它是元数据不是 AIGC 块）'
print('  → 确认：docs/10 §D.4 合法的 ai.generated-by 子键把整个元数据块吞掉——'
      '元数据缺失动作不可解析（正是模块注释 L19-21 声明要防的那类存量 bug）')

print()
print('== BD-QS: is_maintained(None) TypeError（对照 quality_scale 内部归一）==')
from vools.actus.quality import is_maintained
try:
    is_maintained(None)
    print('  未抛出（意外）')
except TypeError as e:
    print('  → 确认：is_maintained(None) 抛 TypeError（捕获面只有 OSError）:', e)

print()
print('== BD-X2: 依赖预检 hard_missing 早退跳过 finish() 留痕 ==')
# 构造：dependency strategy='fail' 且 required 的真缺失
from vools.actus import executor as ex_mod
tmp = tempfile.mkdtemp(prefix='x2_')
os.environ['ACTUS_REPO_ROOT'] = tmp
act_dir = os.path.join(tmp, 'actions'); os.makedirs(act_dir)
os.makedirs(os.path.join(tmp, 'tests'))
open(os.path.join(tmp, 'tests', 't.py'), 'w').write('# dep.hard\n')
CFG = {'id': 'dep.hard', 'name': 'DepHard', 'version': '1.0.0', 'trust': 'sandbox',
       'entry': 'main', 'platform': ['desktop'], 'kind': 'exec',
       'dependencies': {'system': ['no-such-binary-zzz'], 'strategy': 'fail'}}
p = os.path.join(act_dir, 'd.actus.md')
open(p, 'w', encoding='utf-8').write(
    '```json #!cfg\n' + json.dumps(CFG) + '\n```\n\n'
    '#!entry main\n```python #!tag=main\nprint(1)\n```\n')
meta_dir = os.path.join(tmp, '_meta')
r = ex_mod.execute('dep.hard', {}, confirmed=True, meta_dir=meta_dir, actions_dir=act_dir)
print('  status:', r['status'], '| code:', (r.get('error') or {}).get('code'),
      '| record:', 'record' in r, '| exec_id:', 'exec_id' in r, '| mode:', 'mode' in r)
runs = os.path.join(meta_dir, 'runs')
print('  runs 目录存在:', os.path.isdir(runs), '（全程留痕承诺：每次执行应有 runs/<exec_id>.json）')
import sqlite3
db = os.path.join(meta_dir, 'call_log.db')
if os.path.isfile(db):
    c = sqlite3.connect(db)
    try:
        n = c.execute("SELECT COUNT(*) FROM action_metrics WHERE action_id='dep.hard'").fetchone()[0]
    except Exception:
        n = 0
    c.close()
    print('  指标行数:', n, '（deps_missing 拒绝也计入使用量=否，但留痕同样=无）')
if (r.get('error') or {}).get('code') == 'deps_missing':
    assert 'record' not in r and not os.path.isdir(runs)
    print('  → 确认：deps_missing 早退回执无 record/mode/env_prefix，runs/ 不建，finish 一切附加语义全无')
else:
    print('  （本样本走的是主流程 dependency_missing 路径（有留痕）——'
          '预检 hard_missing 触发需 resolver 判非懒；早退代码 L227 return result '
          '不经 finish() 为静态事实，标 candidate）')
