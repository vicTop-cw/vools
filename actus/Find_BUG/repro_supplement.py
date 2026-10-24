# -*- coding: utf-8 -*-
"""两组补充复现：

BUG-I3b（indexer 索引键 vs validate 大小写口径分叉——fallback 路径可达）：
  validate_action 无 jsonschema 时退化为「手工必填校验」，kind 用 is_known_kind(lower())
  判合法；indexer by_* 反向索引建键用 brief 原值。→ 装不了 jsonschema 的环境里
  kind: Exec / purpose: [Transform] 校验全绿，但 filter_by_dimension('kind','exec')
  查不到该动作（动作从维度索引消失）。

BUG-A1（exec_iface._AdapterIface 内联 spec 丢 output/params 块）：
  代码注释自述「平铺写法（{'type':'cli','command':'echo'}）会被 from_dict 丢弃
  command——这里把平铺键收进 adapter 子对象再构造，两种写法都支持」。
  但 from_dict 契约里 output/params/name 等键在**顶层**；平铺内联块整体被塞进
  adapter 子对象后，顶层 output/params 变成空 → output_type=file/json 声明被静默
  丢弃（执行“成功”但 output_path 不解析、data 不结构化）。
"""
import sys, os, json, tempfile
sys.path.insert(0, r'E:\IDEProjects\AI\vools\actus')

print('== BUG-I3b: 无 jsonschema fallback 下 kind=Exec 校验绿、维度索引黑 ==')
import vools.actus.validate as val
from vools.actus.model import parse_cfg_from_file
import builtins
real_import = builtins.__import__
def fake_import(name, *a, **k):
    if name == 'jsonschema' or name.startswith('jsonschema.'):
        raise ImportError('simulated: jsonschema not installed')
    return real_import(name, *a, **k)
builtins.__import__ = fake_import
try:
    tmp = tempfile.mkdtemp(prefix='nofj_')
    CFG = {'id': 'cap.kind', 'name': 'CapKind', 'version': '1.0.0',
           'trust': 'sandbox', 'entry': 'main', 'platform': ['desktop'],
           'kind': 'Exec', 'purpose': ['Transform']}
    p = os.path.join(tmp, 'cap.actus.md')
    open(p, 'w', encoding='utf-8').write(
        '```json #!cfg\n' + json.dumps(CFG) + '\n```\n\n'
        '#!entry main\n```python #!tag=main\nprint(1)\n```\n')
    action = parse_cfg_from_file(p)
    errs = val.validate_action(action)
    print('  validate_action errors:', errs)
    kind_errs = [e for e in errs if 'kind' in e]
    assert not kind_errs, ('fallback 仍打回 kind', kind_errs)
finally:
    builtins.__import__ = real_import
# 同一动作进索引后按闭集值查不到
os.environ['ACTUS_REPO_ROOT'] = tmp
from vools.actus import indexer
acts = indexer.scan_actions(tmp, validate=False)
# 手工按 build_index 的建键逻辑（原值）
brief = acts['cap.kind'].brief()
kind_key = brief.get('kind') or 'exec'
print('  索引将建出的键: by_kind[%r]（闭集值是小写 exec）' % kind_key)
assert kind_key == 'Exec'
from vools.actus.constants import is_known_kind
assert is_known_kind('Exec') is True   # 校验端判「合法」
print('  → 确认：校验判合法用 lower() 归一，索引建键用原值——fallback 环境该动作'
      '过全部校验却永远查不出 exec 维度')

print()
print('== BUG-A1: 内联平铺 spec 的顶层 output/params 块被静默丢弃 ==')
from vools.actus.exec_iface import executor_for, ExecutionContext
from vools.actus.adapter import AdapterSpec

out_file = os.path.join(tmp, 'result.json')
gen_py = os.path.join(tmp, 'gen.py')
open(gen_py, 'w', encoding='utf-8').write(
    f"open(r'{out_file}', 'w').write('{{\"n\": 1}}')\n")
inline = {
    'type': 'cli',
    'command': f'python {gen_py}',
    'output': {'type': 'file', 'path': out_file},   # 声明：产物文件 → data 应含 path/content
    'params': [{'name': 'x', 'type': 'string'}],
}
class A:
    meta = {'id': 'inline.out', 'adapter': inline}
res = executor_for('adapter').execute(A(), ExecutionContext(params={}))
print('  status:', res.status, '| data:', res.data, '| artifacts:', res.artifacts)
# from_dict 顶层没有 output（全被塞进 adapter 子对象）→ spec.output_path == ''
spec = AdapterSpec.from_dict({'id': 'x', 'adapter': dict(inline)})
print('  构造出的 spec.output_type/output_path:', spec.output_type, repr(spec.output_path))
assert spec.output_path == '' and spec.output_type == 'text'
assert res.status == 'ok'
assert res.data is None or 'path' not in (res.data or {}), res.data
assert res.artifacts == []
print('  → 确认：动作声明了 output.type=file + path，命令也确实写出了文件，'
      '但统一接口回包 data=None、artifacts=[] —— output 块被平铺收编逻辑吞掉，'
      '与注释“两种写法都支持”不符（params 顶层块同理丢失）')
print('SUPPLEMENTARY REPROS OK')
