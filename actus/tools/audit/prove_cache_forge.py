# -*- coding: utf-8 -*-
"""只读验证：手写缓存能否冒充真实探测报告（probe 报告权威性）。"""
import json, os, sys, tempfile, time
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, 'tests'))
import _ai_local_bootstrap; _ai_local_bootstrap.install()
from vools.actus.probe import cache as cache_mod
from vools.actus.probe import probe, format_summary

tmp = tempfile.mkdtemp()
cache_mod._CACHE_DIR = tmp
cache_mod._CACHE_FILE = os.path.join(tmp, 'probe_cache.json')

forged = {
    'schema_version': cache_mod.CACHE_SCHEMA_VERSION,
    'timestamp': time.time(),
    'elapsed_ms': 1.0,
    'platform': {'os': 'TotallyFakeOS', 'os_release': '99', 'arch': 'FAKE',
                 'python_version': '0.0.1', 'python_executable': '/fake/python'},
    'permissions': {'user': {'name': 'attacker'}, 'is_admin': True,
                    'can_install_system_wide': True},
    'environment': {'path_count': 12345, 'path_dirs': []},
    'resources': {'cpu': {'count_logical': 9999}, 'memory': {}, 'disk': [],
                  'network': {}},
    'summary': {'total_items': 1, 'available_items': 999, 'unavailable_items': -998,
                'by_category': {'totally_fake': {'total': 1, 'available': 1}},
                'key_tools': {'ghost_tool': {'version': '1.0', 'path': '/ghost'}}},
    'items': [{'name': 'ghost', 'category': 'totally_fake', 'available': True,
               'version': '9.9'}],
}
open(cache_mod._CACHE_FILE, 'w', encoding='utf-8').write(json.dumps(forged))
print('已写入伪造缓存（schema=%s，形状合法）' % forged['schema_version'])

report = probe(force_refresh=False, max_age=3600)
d = report.to_dict()
print('\nprobe() 接受伪造缓存了吗 -> ACCEPTED（当成真实报告返回）')
print('  platform.os      =', d['platform'].get('os'))
print('  permissions.user =', d['permissions'].get('user'))
print('  is_admin         =', d['permissions'].get('is_admin'))
print('  summary          =', json.dumps({k: d['summary'][k] for k in
      ('total_items', 'available_items', 'unavailable_items')}, ensure_ascii=False))
print('  items            =', [i['name'] for i in d['items']])
print('  -> available(%d) > total(%d) 自相矛盾，但缓存里的 summary 被原样当结论'
      % (d['summary']['available_items'], d['summary']['total_items']))
text = format_summary(report)
print('\n人类可读摘要前 10 行:')
print('\n'.join('   ' + l for l in text.splitlines()[:10]))
print('\n[Summary] 段:')
block = text[text.index('[Summary]'):text.index('[By Category]')]
print('\n'.join('   ' + l for l in block.splitlines()))
