# -*- coding: utf-8 -*-
"""第 12 轮验收：统一 secret resolver（6 步 + executor 接线）。"""
import json
import os
import subprocess
import sys
import tempfile
from types import SimpleNamespace

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HOME = tempfile.mkdtemp(prefix='r12_home_')
META = tempfile.mkdtemp(prefix='r12_meta_')
os.environ['HOME'] = HOME
os.environ['USERPROFILE'] = HOME
os.environ['ACTUS_META_DIR'] = META
os.environ['ACTUS_VAULT_KEY'] = 'test-master-key-0123456789'
os.environ['ACTUS_VAULT2_KEY_PROTECTION'] = 'file-key'
for k in ('ACTUS_VAULT_LAZY_MIGRATE', 'ACTUS_VAULT_RESOLVER',
          'VAULT_IDENTITY_ID', 'VAULT_MACHINE_ID', 'VAULT_PIN'):
    os.environ.pop(k, None)
sys.path.insert(0, os.path.join(REPO, 'vools'))
sys.path.insert(0, os.path.join(REPO, 'tests'))
import _ai_local_bootstrap  # noqa: E402
_ai_local_bootstrap.install()
from vools.actus import vault as V  # noqa: E402
from vools.actus import vault2 as V2  # noqa: E402


def section(t):
    print('\n=== %s ===' % t)


def show(label, result):
    keep = {k: result.get(k) for k in ('status', 'code', 'source', 'value',
                                       'migrated', 'message') if result.get(k) is not None}
    print('  %-34s %s' % (label, json.dumps(keep, ensure_ascii=False)[:160]))


# 准备：v2 身份（file-key 保护，不碰 OS keyring）+ v1 主密钥
v2v = V2._get_vault2()          # 与 resolver 内部同一个单例（token 才有效）
reg = v2v.register('u', '123456', machine_name='m', security_level='L1')
authed = v2v.auth(reg['identity_id'], reg['machine_id'], '123456')
os.environ['VAULT_IDENTITY_ID'] = reg['identity_id']
os.environ['VAULT_MACHINE_ID'] = reg['machine_id']
os.environ['VAULT_PIN'] = '123456'
token = authed['session_token']
v2v.set_secret(token, 'v2-only', 'V2VAL')
v1 = V.Vault(META)
v1.set('v1-only', 'V1VAL')

section('1) 统一 resolver 能读 v2（新数据）')
show('resolve_secret("v2-only")', V.resolve_secret('v2-only', meta_dir=META))

section('2) 能读 v1（老数据，兼容回退）')
show('resolve_secret("v1-only")', V.resolve_secret('v1-only', meta_dir=META))

section('3) 两边都有且值不同 → conflict（不静默选一个）')
v2v.set_secret(token, 'shared', 'FROM_V2')
v1.set('shared', 'FROM_V1')
conf = V.resolve_secret('shared', meta_dir=META)
show('resolve_secret("shared")', conf)
print('  消息是否含两库指纹:', 'v1 指纹' in (conf.get('message') or '')
      and 'v2 指纹' in (conf.get('message') or ''))
print('  是否含明文值（应为 False）:', 'FROM_V1' in (conf.get('message') or ''))

section('4) 懒迁移：默认不迁；opt-in 后迁移且行为一致')
before = v2v.get_secret(token, 'v1-only')
print('  默认（未开 opt-in）v2 有 v1-only:', before.get('status') == 'ok')
r = V.resolve_secret('v1-only', meta_dir=META, lazy_migrate=True)
show('lazy_migrate=True 读取', r)
after = v2v.get_secret(token, 'v1-only')
print('  迁移后 v2 可读:', after.get('status') == 'ok', '| 值一致:',
      after.get('value') == 'V1VAL')
show('再次 resolve("v1-only")', V.resolve_secret('v1-only', meta_dir=META))

section('5) v2 不可用时的失败模式（读回退 v1 / 写拒绝或显式 v1）')
os.environ.pop('VAULT_PIN', None)
show('无凭据读 v1-only', V.resolve_secret('v1-only', meta_dir=META))
show('无凭据写 v2-new', V.write_secret('v2-new', 'X', meta_dir=META))
show('无凭据写 + allow_v1_write', V.write_secret('v2-new', 'X', meta_dir=META,
                                               allow_v1_write=True))
os.environ['VAULT_PIN'] = '123456'

section('6) 临时密钥守卫仍生效（未配 ACTUS_VAULT_KEY）')
saved = os.environ.pop('ACTUS_VAULT_KEY')
try:
    res = V.Vault(META).set('guard-key', 'G')
    print('  Vault.set（临时密钥）:', res.get('status'), '| code:', res.get('code'))
finally:
    os.environ['ACTUS_VAULT_KEY'] = saved

section('7) CLI vault 与 executor 的 vault:// 读到同一份')
ENV = dict(os.environ, PYTHONPATH=os.path.join(REPO, 'vools'), PYTHONIOENCODING='utf-8')
def cli(*args):
    return subprocess.run([sys.executable, '-m', 'vools.actus.cli'] + list(args),
                          capture_output=True, text=True, encoding='utf-8',
                          errors='replace', cwd=REPO, env=ENV, timeout=120)

p = cli('vault', 'get', 'v2-only')
d = json.loads(p.stdout)
print('  CLI vault get v2-only:', json.dumps(d, ensure_ascii=False)[:140])
r2 = V.resolve_secret('v2-only', meta_dir=META)
print('  一致:', d.get('value') == r2.get('value') == 'V2VAL')

from vools.actus import executor as EX  # noqa: E402
action = SimpleNamespace(id='demo.act', path='x.actus.md', env_prefix='ACTUS_T_',
                         meta={'secrets': [{'env': 'R12_SECRET', 'key': 'vault://v1-only'}]})
os.environ.pop('R12_SECRET', None)
EX._apply_env_injections(action, {}, 'exec-1', META, False, META)
print('  executor vault:// 注入 R12_SECRET =', os.environ.get('R12_SECRET'),
      '| 与 resolver 一致:', os.environ.get('R12_SECRET') == 'V1VAL')

section('8) executor 遇到冲突 → 显式拒绝执行')
action2 = SimpleNamespace(id='demo.act2', path='x.actus.md', env_prefix='ACTUS_T2_',
                          meta={'secrets': [{'env': 'R12_C', 'key': 'vault://shared'}]})
try:
    EX._apply_env_injections(action2, {}, 'exec-2', META, False, META)
    print('  UNEXPECTED: 未拒绝')
except Exception as exc:
    print('  冲突 →', type(exc).__name__, '| code:', getattr(exc, 'code', None),
          '|', str(getattr(exc, 'message', exc))[:90])

section('9) resolver 自检')
print(' ', json.dumps(V.resolver_status(), ensure_ascii=False)[:200])
