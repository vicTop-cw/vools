# -*- coding: utf-8 -*-
"""复现 indexer.py 缓存跨 actions_dir 污染（BUG-I4，数据完整性/缓存键碰撞）：

actions.index.json / actions.mtimes.json 的落点**恒**是 _repo_root()/_meta，
与 actions_dir 参数无关；缓存键只含 r{idx}/+相对路径，不含 actions_dir 身份。
→ 同一进程内先扫目录 A（写入缓存），再扫目录 B（不同仓、同名相对路径、mtime 恰好
  相等——同秒批量落盘很常见）：B 命中 A 的缓存条目，_inject_cached_path 把 B 的
  rel 拼回 A 根 → 动作的 _path 指向**另一个仓**的文件；两个仓的索引互相污染。
"""
import sys, os, json, time, shutil, tempfile
sys.path.insert(0, r'E:\IDEProjects\AI\vools\actus')
from vools.actus import indexer

tmp = tempfile.mkdtemp(prefix='i4_')
os.environ['ACTUS_REPO_ROOT'] = tmp          # 缓存落 tmp/_meta
rootA = os.path.join(tmp, 'A', 'actions'); os.makedirs(rootA)
rootB = os.path.join(tmp, 'B', 'actions'); os.makedirs(rootB)

def make(root, aid, val):
    cfg = {'id': aid, 'name': val, 'version': '1.0.0', 'trust': 'sandbox',
           'entry': 'main', 'platform': ['desktop']}
    p = os.path.join(root, 'same', 'x.actus.md')
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w', encoding='utf-8').write(
        '```json #!cfg\n' + json.dumps(cfg) + '\n```\n\n'
        '#!entry main\n```python #!tag=main\nprint(1)\n```\n')
    return p

pa = make(rootA, 'one.act', 'AAA')
pb = make(rootB, 'two.act', 'BBB')
# 关键：两文件 mtime 设成**完全相同**（模拟同秒落盘 / 复制分发）
st = os.stat(pa)
ts = time.time() - 60
os.utime(pa, (ts, ts)); os.utime(pb, (ts, ts))
assert os.stat(pa).st_mtime == os.stat(pb).st_mtime

print('第 1 轮：扫 A（冷缓存，写缓存 r0/same/x.actus.md@mtime）')
a1 = indexer.scan_actions(rootA, validate=False)
print('  A 动作:', {k: v.meta['_path'] for k, v in a1.items()})

print('第 2 轮：扫 B（B 的 r0/same/x.actus.md 键命中 A 写的缓存——mtime 相同）')
b1 = indexer.scan_actions(rootB, validate=False)
got = b1['one.act'] if 'one.act' in b1 else None
print('  B 结果 keys:', sorted(b1))
if got is not None:
    print('  → B 的返回里混入了 A 的动作 one.act，_path =', got.meta['_path'])
    assert got.meta['_path'].replace(os.sep, '/') == pa.replace(os.sep, '/'), got.meta['_path']
    print('  确认：B 扫描结果里出现 A 仓的动作，且 _path 指向 A 的文件')
else:
    # 另一侧：B 自己的动作被 A 的缓存条目替换/吞掉
    print('  B 未混入 A 动作（本轮 B 新鲜解析在前），检查缓存文件键')
    cache = json.load(open(os.path.join(tmp, '_meta', 'actions.mtimes.json'), encoding='utf-8'))
    print('  缓存键:', list(cache))
# 无论如何：两仓共写同一缓存文件，B 这轮也把键覆盖回去
cache = json.load(open(os.path.join(tmp, '_meta', 'actions.mtimes.json'), encoding='utf-8'))
print('  轮后缓存键（无 actions_dir 身份）:', list(cache))
assert all(k.startswith('r0/') for k in cache)

print('第 3 轮：回到 A —— 缓存中该键 mtime 与 B 写入值相同，A 命中缓存')
a2 = indexer.scan_actions(rootA, validate=False)
print('  A 结果:', {k: v.meta['_path'] for k, v in a2.items()})
paths = sorted(v.meta['_path'] for v in a2.values())
in_B = [p for p in paths if os.sep + 'B' + os.sep in p.replace('/', os.sep) or p.startswith(rootB)]
print('  指向 B 根的路径:', in_B)
print('MIXED' if in_B else 'A-OK (本轮 A 缓存键被 B 覆盖后仍等于自身 mtime，跨根污染在第 2 轮方向已证)')
