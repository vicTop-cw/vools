# -*- coding: utf-8 -*-
import sys, os, tempfile
sys.path.insert(0, r'E:\IDEProjects\AI\vools\actus')
from vools.actus.exec_iface import executor_for, ExecutionContext

tmp = tempfile.mkdtemp(prefix='a1dbg_')
out = os.path.join(tmp, 'r.json')
gen = os.path.join(tmp, 'g.py')
with open(gen, 'w', encoding='utf-8') as f:
    f.write("import json\nwith open(r'%s','w') as f: json.dump({'n':1}, f)\n" % out)

inline = {
    'type': 'cli',
    'command': 'python ' + gen,
    'output': {'type': 'file', 'path': out},
    'params': [{'name': 'x', 'type': 'string'}],
}
class A:
    meta = {'id': 'x', 'adapter': inline}
r = executor_for('adapter').execute(A(), ExecutionContext(params={}))
print('status:', r.status, '| kind:', r.error_kind)
print('error:', repr(r.error)[:300])
print('data:', r.data, '| artifacts:', r.artifacts)
print('output file actually written:', os.path.isfile(out))
