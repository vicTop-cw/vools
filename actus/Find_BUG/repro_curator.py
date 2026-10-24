# -*- coding: utf-8 -*-
"""复现 curator.py 两处缺陷：
BUG-C1: _collection_path sanitize 把空格直接删除而非替换为分隔符 →
        "My List" / "MyList" / "my list"（大小写不同仍不同，但空格变体全同）碰撞到同一文件，
        create_collection 文档承诺「同名覆盖」，实际是「同 sanitize 路径覆盖」，
        不同名的两个集合互相静默覆盖，list_collections 只剩一份。
BUG-C2: 文档原则「best-effort：文件读写失败不抛出」——default_repos.json 内容含
        非 dict 元素（如被人手工写成 ["repo-a"]）时 add/remove 直接 AttributeError 抛出。
"""
import sys, json, os, tempfile
sys.path.insert(0, r'E:\IDEProjects\AI\vools\actus')
from vools.actus import curator

tmp = tempfile.mkdtemp(prefix='curator_repro_')
cfg = os.path.join(tmp, 'config')
curator._CONFIG_DIR = cfg
curator._DEFAULT_REPOS_FILE = os.path.join(cfg, 'default_repos.json')
curator._COLLECTIONS_DIR = os.path.join(cfg, 'collections')

print('== BUG-C1: 空格名与无空格名碰撞同一文件 ==')
p1 = curator._collection_path('My List')
p2 = curator._collection_path('MyList')
print('  _collection_path("My List") =', os.path.basename(p1))
print('  _collection_path("MyList")  =', os.path.basename(p2))
assert p1 == p2, (p1, p2)
ok1 = curator.create_collection('My List', ['a.actus.id', 'b.actus.id'])
ok2 = curator.create_collection('MyList', ['z.actus.id'])
print('  create 均成功:', ok1, ok2)
listed = curator.list_collections()
print('  list_collections:', listed)
assert len(listed) == 1, listed
# "My List" 的两条动作被 "MyList" 的一条静默顶掉
got = curator.load_collection('My List')
print('  load_collection("My List") 返回:', got)
assert got['name'] == 'MyList' and got['action_ids'] == ['z.actus.id']
print('  → 确认：不同名集合互相静默覆盖（数据丢失），文档只承诺「同名覆盖」')

print()
print('== BUG-C2: 脏 default_repos.json（列表含字符串）→ add/remove 抛出 ==')
os.makedirs(cfg, exist_ok=True)
with open(curator._DEFAULT_REPOS_FILE, 'w', encoding='utf-8') as f:
    json.dump(['legacy-string-entry'], f)
try:
    curator.add_default_repo('https://example.com/x', 'x')
    print('  add_default_repo 未抛出（意外）')
except AttributeError as e:
    print('  add_default_repo 抛出 AttributeError:', e)
    print('  → 确认：违反模块头「best-effort：文件读写失败不抛出」契约')
try:
    curator.remove_default_repo('whatever')
except AttributeError as e:
    print('  remove_default_repo 同样抛出 AttributeError:', e)
print('ALL CURATOR REPROS OK')
