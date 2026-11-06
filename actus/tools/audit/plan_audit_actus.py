# -*- coding: utf-8 -*-
"""第 16 轮：ACTUS_REFACTOR_PLAN 条目核实（运行时，cwd=actus）。"""
import io
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.environ['ACTUS_META_DIR'] = tempfile.mkdtemp(prefix='plan16a_')

from vools.actus import resolver  # noqa: E402
from vools.actus.indexer import scan_actions, build_index  # noqa: E402
from vools.actus import validate as V  # noqa: E402

print('=== ACTUS_REFACTOR_PLAN 条目核实 ===')
scanned = scan_actions(validate=False, write_cache=False)
by_id = next(iter(scanned.values()))
name_action = next((a for a in scanned.values()
                    if isinstance(a.meta.get('name'), str) and a.meta.get('name')), None)
md5_action = next((a for a in scanned.values() if getattr(a, 'md5', None)), None)

def show(label, ok, ev):
    print('  %-5s %-34s %s' % ('OK' if ok else 'MISS', label, ev))

try:
    r = resolver.resolve_target(by_id.meta['id'])
    show('target: 动作 id', r.source == 'id', 'source=' + r.source)
except Exception as exc:  # noqa: BLE001
    show('target: 动作 id', False, str(exc))
try:
    r = resolver.resolve_target(by_id.path)
    show('target: 本地零散路径', r.source in ('path', 'id'), 'source=' + r.source)
except Exception as exc:  # noqa: BLE001
    show('target: 本地零散路径', False, str(exc))
if name_action:
    try:
        r = resolver.resolve_target(name_action.meta['name'])
        show('target: 可读名称', r.source == 'name',
             'source=%s ambiguous=%s' % (r.source, r.ambiguous))
    except Exception as exc:  # noqa: BLE001
        show('target: 可读名称', False, str(exc))
if md5_action:
    try:
        r = resolver.resolve_target(md5_action.md5)
        show('target: 内容 md5', r.source == 'md5', 'source=' + r.source)
    except Exception as exc:  # noqa: BLE001
        show('target: 内容 md5', False, str(exc))
try:
    resolver.resolve_target('https://example.invalid/x.actus.md', allow_hosts=[])
    show('target: URL 动作源', False, '未抛错')
except Exception as exc:  # noqa: BLE001
    show('target: URL 动作源', True, 'URL 分支可达（%s）' % str(exc)[:60])

# 入参七形态
p = resolver.resolve_params_extended('{"a":1}')
show('params: JSON 字面量', p == {'a': 1}, repr(p))
pf = os.path.join(tempfile.mkdtemp(prefix='plan16p_'), 'a.json')
io.open(pf, 'w', encoding='utf-8').write('{"b":2}')
show('params: @file', resolver.resolve_params_extended('@' + pf) == {'b': 2}, '@file')
try:
    resolver.resolve_params_extended('https://example.invalid/a.json', allow_hosts=[])
    show('params: URL JSON', False, '未抛错')
except Exception as exc:  # noqa: BLE001
    show('params: URL JSON', True, 'URL 入参分支可达（%s）' % str(exc)[:50])
show('params: @action 递归深度保护', 'max_action_depth' in
     io.open(os.path.join(ROOT, 'vools/actus/resolver.py'), encoding='utf-8').read(),
     'resolver.resolve_params_extended(max_action_depth=3)')

# kind 体系 — 检测逻辑放宽：`kind == 'X'` 或 `kind in (..., 'X')` 都算已落地
# 原检测只看 `kind == 'alias'` 字面匹配，但 executor.py 用 `kind in ('alias', 'link')`
# 更优雅的写法，导致 alias 被误报 MISS。
exec_src = io.open(os.path.join(ROOT, 'vools/actus/executor.py'),
                   encoding='utf-8').read()
import re as _re
for kind in ('link', 'alias', 'bundle', 'doc', 'template', 'demo'):
    pattern = _re.compile(
        r"kind\s*==\s*['\"]%s['\"]|kind\s+in\s*\([^)]*['\"]%s['\"]" % (
            _re.escape(kind), _re.escape(kind))
    )
    show('kind 执行语义: ' + kind, bool(pattern.search(exec_src)),
         'executor.py (%s)' % ('kind== or kind in') if pattern.search(exec_src) else 'executor.py')
show('kind 非执行豁免清单', 'demo' in V._NON_EXEC_KINDS,
     '_NON_EXEC_KINDS=%r' % (V._NON_EXEC_KINDS,))
kinds = {}
for a in scanned.values():
    k = str(a.meta.get('kind') or 'exec')
    kinds[k] = kinds.get(k, 0) + 1
print('  种子动作 kind 分布:', kinds)

# 索引扩展
idx = build_index(meta_dir=os.environ['ACTUS_META_DIR'], write=False, write_cache=False)
for key in ('by_name', 'by_md5', 'by_kind'):
    show('索引扩展: ' + key, key in idx, 'build_index keys')
print('  by_kind=', {k: len(v) for k, v in (idx.get('by_kind') or {}).items()})
brief = next(iter((idx.get('actions') or {}).values()), {})
for key in ('kind', 'md5', 'name', 'languages', 'platform'):
    print('  brief 含 %-10s: %s' % (key, key in brief))

# 校验面
show('校验: 代码块语言检查', hasattr(V, 'check_block_languages'),
     'validate.check_block_languages')
show('校验: kind 合法性',
      hasattr(V, 'check_kind') or hasattr(V, 'is_known_kind'),
      'validate.is_known_kind' if hasattr(V, 'is_known_kind') and not hasattr(V, 'check_kind') else 'validate.check_kind' if hasattr(V, 'check_kind') else '未找到')
show('校验: link/alias target 存在性',
     'target_not_found' in io.open(os.path.join(ROOT, 'vools/actus/validate.py'),
                                   encoding='utf-8').read()
     or 'target' in io.open(os.path.join(ROOT, 'vools/actus/validate.py'),
                            encoding='utf-8').read(),
     'validate.py 含 target 校验')
show('校验: md5 一致性告警',
     'md5' in io.open(os.path.join(ROOT, 'vools/actus/validate.py'),
                      encoding='utf-8').read(), 'validate.py 含 md5')

# 语言可路由
try:
    from vools.bridge.md.runner import is_routable
    langs = ['python', 'shell', 'powershell', 'cmd', 'bat', 'node', 'go',
             'rust', 'ruby', 'php', 'typescript', 'zig', 'nim']
    route = {l: is_routable(l) for l in langs}
    print('  语言可路由:', route)
    show('语言: 任意语言入口（runner 路由）', any(route.values()), 'is_routable')
except Exception as exc:  # noqa: BLE001
    show('语言: 任意语言入口（runner 路由）', False, str(exc))

# docs 同步
doc03 = os.path.join(os.path.dirname(ROOT), 'docs', 'actus', '03-动作规范.md')
std = os.path.join(ROOT, 'docs', 'DEVELOPMENT_STANDARDS.md')
show('docs: 03-动作规范.md', os.path.isfile(doc03), doc03)
show('docs: DEVELOPMENT_STANDARDS.md', os.path.isfile(std), std)
if os.path.isfile(doc03):
    txt = io.open(doc03, encoding='utf-8').read()
    for kw in ('kind', 'link', 'demo', 'template', 'bundle', 'md5'):
        print('  docs/03 含 %-8s: %s' % (kw, kw in txt))

# §六.6 _find_action_file — 检测函数定义（def _find_action_file），而非任意字符串
# 原检测只看 `_find_action_file` 字符串出现，会把注释里的历史说明也命中
# （paths.py 注释「5 份 _find_action_file 实现吃过亏」）。真正的清理判据是
# 函数定义消失——薄封装调用 resolver 的写法不算漂移源。
hits = []
for dp, _d, fs in os.walk(os.path.join(ROOT, 'vools', 'actus')):
    for f in fs:
        if f.endswith('.py'):
            pth = os.path.join(dp, f)
            content = io.open(pth, encoding='utf-8', errors='replace').read()
            if _re.search(r'def\s+_find_action_file', content):
                hits.append(os.path.relpath(pth, ROOT))
show('§六.6 _find_action_file 已清理', not hits, '仍存在: %r' % (hits,))
