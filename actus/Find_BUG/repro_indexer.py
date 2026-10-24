# -*- coding: utf-8 -*-
"""复现 indexer.py scan_actions 缓存合并段两处缺陷 + 一处性能契约漂移：

BUG-I1（数据完整性）：缓存命中分支的合并循环
    for rel, action in cached_actions.items():
        if aid and aid not in actions: actions[aid] = action
  与新鲜解析路径不对称——新鲜路径对 (a) 缺 id (b) id 重复 都会记 problems；
  缓存命中路径两者都**静默丢弃、problems 无痕**。同 id 双胞胎文件在首轮扫描
  （无缓存）报 conflict，第二轮（全缓存命中）问题消失 → 索引/体检读数抖动，
  重复 id 动作从「有罪名单」蒸发。

BUG-I2（性能契约漂移）：文档承诺「use_cache=True 基于 mtime 增量缓存，仅重解析
  变更文件」；实际缓存命中分支照样 parse_cfg_from_file(full) 全量重解析
  （mtime 只用于决定是否跳过 problem 判定，不省解析）。

BUG-I3（索引覆盖）：by_kind/by_purpose/by_industry 直接用 brief 原值做键，
  而 validate.is_known_* 用小写归一判合法 → 声明 kind: Exec 的动作校验通过，
  但落在 by_kind['Exec'] 下；filter_by_dimension('kind','exec') 返回空。
"""
import sys, os, json, shutil, tempfile, time
sys.path.insert(0, r'E:\IDEProjects\AI\vools\actus')
from vools.actus import indexer
from vools.actus.model import parse_cfg_from_file

tmp = tempfile.mkdtemp(prefix='indexer_repro_')
act = os.path.join(tmp, 'actions')
os.makedirs(act)

CFG = {
    'id': 'dup.id', 'name': 'Dup', 'version': '1.0.0', 'trust': 'sandbox',
    'entry': 'main', 'platform': ['desktop'], 'kind': 'Exec',
}
BODY = ('```json #!cfg\n' + json.dumps(CFG) + '\n```\n\n'
        '#!entry main\n```python #!tag=main\nprint(1)\n```\n')
BODY2 = BODY.replace('"dup.id"', '"dup.id2"')

f1 = os.path.join(act, 'dupA.actus.md')
f2 = os.path.join(act, 'dupB.actus.md')
open(f1, 'w', encoding='utf-8').write(BODY2.replace('dup.id2', 'dup.id'))  # 同 id！
open(f2, 'w', encoding='utf-8').write(BODY)
# 第二个文件缺 id
NOID = {k: v for k, v in CFG.items() if k != 'id'}
f3 = os.path.join(act, 'noid.actus.md')
open(f3, 'w', encoding='utf-8').write(
    '```json #!cfg\n' + json.dumps(NOID) + '\n```\n\n'
    '#!entry main\n```python #!tag=main\nprint(1)\n```\n')

os.environ['ACTUS_REPO_ROOT'] = tmp  # 缓存落到 tmp/_meta，不污染真仓

print('== 第 1 轮（冷缓存，新鲜解析）==')
a1 = indexer.scan_actions(act, validate=False)
p1 = dict(indexer.scan_actions.problems)
print('  actions:', sorted(a1))
print('  problems:', p1)
assert 'dup.id' in a1
assert any('conflict' in v for v in p1.values()), p1
assert any('缺少 id' in v for v in p1.values()), p1

print('== 第 2 轮（mtime 全部命中缓存）==')
time.sleep(1.1)  # 确认 mtime 未变（文件不再写）
# 打点：数 parse_cfg_from_file 被调用几次 → 证伪「仅重解析变更文件」
calls = []
orig_parse = indexer.parse_cfg_from_file
def counting_parse(path, *a, **k):
    calls.append(os.path.basename(path))
    return orig_parse(path, *a, **k)
indexer.parse_cfg_from_file = counting_parse
a2 = indexer.scan_actions(act, validate=False)
indexer.parse_cfg_from_file = orig_parse
p2 = dict(indexer.scan_actions.problems)
print('  actions:', sorted(a2))
print('  problems:', p2)
print('  本轮 parse_cfg_from_file 调用文件:', calls)
assert p2 == {}, ('第 2 轮 conflict/缺id 无痕消失:', p1, '->', p2)
print('  → BUG-I1 确认：第 1 轮 2 条 problems（conflict+缺id），第 2 轮全缓存命中后 '
      'problems 变空——重复 id/缺 id 动作被静默吞掉，不再出现在任何名单')
assert len(calls) >= 3, ('缓存命中仍全量重解析', calls)
print('  → BUG-I2 确认：声称「仅重解析变更文件」，实际 0 变更文件仍解析', len(calls), '次')

print('== BUG-I3: by_kind 键不归一小写 ==')
idx = indexer.build_index(actions_dir=act, meta_dir=os.path.join(tmp, '_meta'))
kinds = list(idx['by_kind'])
print('  by_kind keys:', kinds)
assert 'Exec' in kinds and 'exec' not in kinds, kinds
from vools.actus.validate import validate_action
errs = validate_action(a1['dup.id'])
print('  kind=Exec 校验结果:', errs)
assert not any('kind 非法' in e for e in errs), errs  # 校验端认小写归一是合法的
# filter_by_dimension 按闭集值 'exec' 查
hits = indexer.filter_by_dimension('kind', 'exec', meta_dir=os.path.join(tmp, '_meta'))
print('  filter_by_dimension(kind=exec) →', hits, '（明明有动作，索引查不到）')
assert hits == []
print('  → BUG-I3 确认：校验判合法用 lower()，索引建键用原值——kind=Exec 通过校验却从 exec 维度消失')
print('ALL INDEXER REPROS OK')
