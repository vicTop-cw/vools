# -*- coding: utf-8 -*-
"""第 16 轮：ACTUS_REFACTOR_PLAN 条目核实（运行时，cwd=actus）。"""
import io
import json
import os
import re as _re
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

# kind 体系 — 判定收紧：AST 精确匹配（真实代码节点），不再用正则/字符串包含
# 原检测只看 `kind == 'alias'` 字面匹配，会漏掉 `kind in ('alias', 'link')`；
# 放宽为正则后仍可能被注释 / 字符串字面量里的字样误报。现在解析 AST 收集
# 真实代码中的 `kind == 'X'` / `kind in (..., 'X')` 判定（单一实现见
# _plan_audit_helpers.code_kind_comparisons，审计测试同引用）。
exec_src = io.open(os.path.join(ROOT, 'vools/actus/executor.py'),
                   encoding='utf-8').read()
from _plan_audit_helpers import code_kind_comparisons  # noqa: E402
exec_kinds = code_kind_comparisons(exec_src)
for kind in ('link', 'alias', 'bundle', 'doc', 'template', 'demo'):
    show('kind 执行语义: ' + kind, kind in exec_kinds,
         'executor.py AST 判定集合=%s' % (sorted(exec_kinds),))
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
# 校验面 — 判定收紧：真实行为验证（不再做字符串包含）
# 原判定 `'target' in validate.py 全文` / `'md5' in validate.py 全文` 恒真
# （validate.py 必然出现这些字样），无法核查校验是否覆盖真实路径/内容。
# 现在直接调用 V.check_link_target / V.check_md5_consistency 构造真实场景断言：
#   * link/alias target 缺失 → error；target 不在索引 → warning；命中 → 无告警；
#   * 索引 md5 与实际文件内容 md5 不一致 → warning；一致 → 无告警。
from types import SimpleNamespace as _SN  # noqa: E402
import hashlib as _hashlib  # noqa: E402

def _write_mini_index(entries):
    with io.open(os.path.join(os.environ['ACTUS_META_DIR'], 'actions.index.json'),
                 'w', encoding='utf-8') as _f:
        json.dump({'actions': entries}, _f)

# link/alias target 存在性：target 缺失 → error；target 不在索引 → warning
_missing_t = V.check_link_target(
    _SN(meta={'kind': 'link', 'target': '', 'id': 'stub.link'}), check_index=False)
_write_mini_index({'actus.real': {'id': 'actus.real', 'md5': '0' * 32}})
_absent_t = V.check_link_target(
    _SN(meta={'kind': 'alias', 'target': 'actus.missing', 'id': 'stub.alias'}),
    check_index=True, meta_dir=os.environ['ACTUS_META_DIR'])
_known_t = V.check_link_target(
    _SN(meta={'kind': 'link', 'target': 'actus.real', 'id': 'stub.link2'}),
    check_index=True, meta_dir=os.environ['ACTUS_META_DIR'])
show('校验: link/alias target 缺失拦截',
     any('缺少 target' in e for e in _missing_t), repr(_missing_t))
show('校验: link/alias target 存在性',
     any('未在索引中找到' in e for e in _absent_t), repr(_absent_t))
show('校验: link/alias target 命中索引', not _known_t, repr(_known_t))

# md5 一致性：索引 md5 vs 文件实际内容 md5 的真实比对
_md5_file = os.path.join(os.environ['ACTUS_META_DIR'], 'stub_md5.txt')
io.open(_md5_file, 'w', encoding='utf-8').write('stub md5 body')
_real_md5 = _hashlib.md5(io.open(_md5_file, 'rb').read()).hexdigest()
_write_mini_index({'stub.md5': {'id': 'stub.md5', 'md5': 'f' * 32}})
_md5_stub = _SN(meta={'id': 'stub.md5'}, md5=_real_md5, path=_md5_file)
_md5_bad = V.check_md5_consistency(_md5_stub, meta_dir=os.environ['ACTUS_META_DIR'])
_write_mini_index({'stub.md5': {'id': 'stub.md5', 'md5': _real_md5}})
_md5_ok = V.check_md5_consistency(_md5_stub, meta_dir=os.environ['ACTUS_META_DIR'])
show('校验: md5 一致性（真实比对）',
     any('索引 md5 与文件不一致' in e for e in _md5_bad), repr(_md5_bad))
show('校验: md5 一致无告警', not _md5_ok, repr(_md5_ok))

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
# 旧式实现（自行 glob/os.walk/字符串搜内容）消失——薄封装委托
# resolver.find_action_file 的写法不算漂移源（785601e6 收口后保留为兼容签名，
# 供 test_author_contracts_r84 / test_omega / test_dependency_contracts_r52 等引用）。
legacy_hits = []
shell_hits = []
for dp, _d, fs in os.walk(os.path.join(ROOT, 'vools', 'actus')):
    for f in fs:
        if f.endswith('.py'):
            pth = os.path.join(dp, f)
            content = io.open(pth, encoding='utf-8', errors='replace').read()
            if _re.search(r'def\s+_find_action_file', content):
                m = _re.search(r'def\s+_find_action_file.*?(?=\n\S|\Z)', content, _re.S)
                body = m.group(0)
                # 跳过 docstring（历史说明里可能提到旧式实现特征词，如 omega.py 的
                # 「用 f'"..." in content 判断」），只看可执行代码体。
                for _q in ('"""', "'''"):
                    _parts = body.split(_q)
                    if len(_parts) >= 3:
                        body = _parts[2]
                        break
                delegating = ('find_action_file(' in body and 'glob' not in body
                              and 'os.walk' not in body and 'in content' not in body)
                if delegating:
                    shell_hits.append(os.path.relpath(pth, ROOT))
                else:
                    legacy_hits.append(os.path.relpath(pth, ROOT))
show('§六.6 _find_action_file 已清理（无旧式实现）', not legacy_hits, '旧式仍存在: %r' % (legacy_hits,))
if shell_hits:
    print('  兼容薄壳（委托 resolver.find_action_file，保留签名）: %r' % (shell_hits,))
