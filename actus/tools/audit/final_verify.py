# -*- coding: utf-8 -*-
"""最终验收：6 条修复逐项复跑（隔离 HOME）。"""
import json, os, sqlite3, sys, tempfile
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, 'tests'))
import _ai_local_bootstrap; _ai_local_bootstrap.install()
TMP = tempfile.mkdtemp(prefix='final_')
os.environ['HOME'] = TMP; os.environ['USERPROFILE'] = TMP
os.environ.pop('ACTUS_VAULT2_DIR', None)
from vools.actus import vault2 as v2
from vools.actus.visibility import TeamManager, VisibilityEngine
OLD = os.getcwd()

def out(label, value):
    print('  %-46s -> %s' % (label, value))

print('① 团队名路径逃逸')
tm = TeamManager(os.path.join(TMP, 'cfg'))
victim = os.path.join(TMP, 'victim.json'); open(victim, 'w').write('{}')
try:
    tm.create_team('../../escaped', 'attacker'); out('create_team("../../escaped")', 'WROTE(!)')
except ValueError:
    out('create_team("../../escaped")', 'ValueError（已拒绝）')
out('越界文件存在?', os.path.isfile(os.path.join(TMP, 'escaped.json')))
out('delete_team("../victim")', tm.delete_team('../victim'))
out('victim 是否还在', os.path.isfile(victim))
out('合法 create_team("team-1")', tm.create_team('team-1', 'alice').name)

print('\n② 默认目录 + 迁移（两种情形）')
repo = os.path.join(TMP, 'repo'); legacy = os.path.join(repo, '_meta', 'vault'); os.makedirs(legacy)
v2.Vault2(legacy).register('u', '123456', machine_name='m', security_level='L1')
os.chdir(repo); inst = v2.Vault2(); os.chdir(OLD)
out('情形1 migrated_from', bool(inst.migrated_from))
out('情形1 旧位置已移走', not os.path.isdir(legacy))
out('情形1 新位置 db', os.path.isfile(os.path.join(TMP, '.actus', 'vault2', 'vault2.db')))
repo2 = os.path.join(TMP, 'repo2'); legacy2 = os.path.join(repo2, '_meta', 'vault'); os.makedirs(legacy2)
v2.Vault2(legacy2).register('old', '123456', machine_name='m', security_level='L1')
home2 = os.path.join(TMP, 'home2'); os.environ['HOME'] = home2; os.environ['USERPROFILE'] = home2
new2 = os.path.join(home2, '.actus', 'vault2'); os.makedirs(new2)
v2.Vault2(new2).register('new', '123456', machine_name='m', security_level='L1')
os.chdir(repo2); inst2 = v2.Vault2(); os.chdir(OLD)
out('情形2 conflict 含 ambiguous', 'ambiguous' in (inst2.migration_conflict or ''))
out('情形2 两边都保留', os.path.isfile(os.path.join(legacy2, 'vault2.db')) and
                        os.path.isfile(os.path.join(new2, 'vault2.db')))
calls = []; orig = os.chmod
os.chmod = lambda p, m: calls.append((os.path.basename(p) or p, oct(m)))
try:
    v2.Vault2(os.path.join(TMP, 'perm'))
finally:
    os.chmod = orig
out('②-e chmod 目标', calls)

print('\n③④⑤ L1 告警 / migrate 真实性 / status 认证')
vl = v2.Vault2(os.path.join(TMP, 'vaultL1'))
reg = vl.register('l1', '123456', machine_name='m1', security_level='L1')
tok = vl.auth(reg['identity_id'], reg['machine_id'], '123456')['session_token']
vl.set_secret(tok, 'k', 'v')
unauth = vl.status(); auth = vl.status(tok)
out('⑤ 无 token 字段', sorted(unauth.keys()))
out('⑤ 含计数?', any(k in unauth for k in ('identities', 'secrets')))
out('③ 有 token warnings', auth.get('warnings'))
with sqlite3.connect(vl.db_path) as c:
    c.execute("INSERT INTO secrets (id, identity_id, name, value, secret_type, security_level, "
              "created_at, cipher_alg, key_salt) VALUES ('lg', ?, 'broken', 'bad', 'api_key', "
              "'L1', 0, 'fernet', NULL)", (reg['identity_id'],))
mig = vl.migrate_legacy_secrets(tok)
out('④ 有失败 status', mig.get('status'))
out('④ 失败条目名', mig.get('failed_names'))

print('\n⑥ _find_action 文档边界')
doc = VisibilityEngine._find_action.__doc__ or ''
out('docstring 明确只查私有索引', ('私有动作索引' in doc) and ('所有注册表' not in doc))
print('\n~/.actus 文件数（最终）:',
      sum(len(f) for _d, _x, f in os.walk(os.path.expanduser('~/.actus'))))
