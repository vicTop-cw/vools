"""三方一致性审计：CLI / MCP / Python API 对同一操作的契约对比。

只读审计：不改产品代码。每个（操作 × 入口）都在**独立沙箱**里跑一个子进程，
因此模块级缓存、环境变量、副作用互不干扰；跑完对比「成功判定 / 返回体形状 /
错误码 / 副作用位置 / 默认值 / 参数校验」。

用法：
    python tools/audit/three_entry_audit.py            # 打印矩阵 + 明细
    python tools/audit/three_entry_audit.py --json     # 只输出 JSON
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ACTUS_DIR = os.path.dirname(os.path.dirname(HERE))       # .../actus

# ── 防御：必须以**工作树**里的 vools.actus 为准 ──────────────────────────
# 事故背景：从 `actus/tools/audit/` 直接跑时，`vools` 会解析到 site-packages
# 里已发布的 0.9.0 包（当前目录不含 `actus/`）—— 审计测的是**发布版**而不是
# 当前工作树，且毫无提示（曾让我们误判"CLI 与 API 校验结论相反"）。
# 这里显式把工作树插到 sys.path 最前，并**断言**真的加载到了工作树：
# 误用必须立刻失败，而不是静默测错对象。
if ACTUS_DIR not in sys.path:
    sys.path.insert(0, ACTUS_DIR)
import vools.actus as _vools_actus_probe  # noqa: E402

assert 'site-packages' not in (_vools_actus_probe.__file__ or ''), (
    '审计脚本必须使用工作树里的 vools.actus；实际加载的是 %r。'
    '请设 PYTHONPATH=%s 或从仓库根运行。'
    % (_vools_actus_probe.__file__, ACTUS_DIR))

# 供子进程用的 PYTHONPATH：同上，必须指向工作树根（其下有 vools/ 包）
PARENT = ACTUS_DIR

FENCE = '`' * 3
ACTION_ID = 'demo.audit'


def action_md(action_id=ACTION_ID):
    cfg = json.dumps({
        'id': action_id, 'name': 'Audit Demo', 'version': '1.0.0',
        'trust': 'sandbox', 'platform': 'windows', 'entry': 'main',
        'args': {'type': 'object', 'properties': {}},
    }, ensure_ascii=False)
    return ('---\nAIGC: {}\n---\n\n'
            '# Audit Demo\n\n'
            '## Implementation\n\n'
            + FENCE + 'json #!cfg\n' + cfg + '\n' + FENCE + '\n\n'
            + FENCE + 'python #!run tag=main\nprint("audit-ok")\n' + FENCE + '\n')


def make_sandbox(with_action=True):
    root = tempfile.mkdtemp(prefix='t3-')
    repo = os.path.join(root, 'repo')
    os.makedirs(os.path.join(repo, 'actions'))
    if with_action:
        with open(os.path.join(repo, 'actions', 'demo.actus.md'), 'w', encoding='utf-8') as f:
            f.write(action_md())
    meta = os.path.join(root, 'meta')
    os.makedirs(meta, exist_ok=True)
    home = os.path.join(root, 'home')
    os.makedirs(home, exist_ok=True)
    return root, repo, meta, home


def env_for(repo, meta, home, extra=None):
    env = dict(os.environ)
    env.update({
        'ACTUS_REPO_ROOT': repo,
        'ACTUS_META_DIR': meta,
        'HOME': home,
        'USERPROFILE': home,
        'PYTHONPATH': PARENT,
        'PYTHONIOENCODING': 'utf-8',
    })
    env.pop('ACTUS_VAULT_KEY', None)
    env.update(extra or {})
    return env


def snapshot(root):
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ('.git', '__pycache__')]
        for name in filenames:
            out.append(os.path.relpath(os.path.join(dirpath, name), root).replace(os.sep, '/'))
    return sorted(out)


def _run(argv, env, cwd):
    try:
        p = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=180)
        return p.returncode, p.stdout or '', p.stderr or ''
    except subprocess.TimeoutExpired:
        return 124, '', 'TIMEOUT'


def _extract(stdout, marker='__RESULT__'):
    for line in (stdout or '').splitlines():
        if line.startswith(marker):
            try:
                return json.loads(line[len(marker):].strip())
            except ValueError:
                return None
    return None


def _json_payload(stdout):
    """CLI 输出：整段 JSON 或首行 JSON。"""
    text = (stdout or '').strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        for line in text.splitlines():
            line = line.strip()
            if line.startswith('{'):
                try:
                    return json.loads(line)
                except ValueError:
                    continue
    return None


def run_cli(entry, sandbox):
    root, repo, meta, home = sandbox
    env = env_for(repo, meta, home, entry.get('env'))
    before = snapshot(root)
    rc, out, err = _run([sys.executable, '-m', 'vools.actus.cli'] + entry['argv'],
                        env, repo)
    after = snapshot(root)
    return {
        'entry': 'CLI',
        'ok': rc == 0,
        'rc': rc,
        'payload': _json_payload(out),
        'stderr_head': (err or '').strip().splitlines()[:2],
        'new_files': sorted(set(after) - set(before)),
    }


MCP_WRAPPER = r'''
import io, json, sys
from vools.actus.mcp_server import MCPServer
srv = MCPServer(stdin=io.StringIO(), stdout=io.StringIO())
spec = json.loads(sys.argv[1])
r = srv._call_tool({'name': spec['tool'], 'arguments': spec['args']})
try:
    payload = json.loads(r['content'][0]['text'])
except Exception:
    payload = {'_raw': r.get('content')}
print('__RESULT__', json.dumps({'isError': bool(r.get('isError')), 'payload': payload},
                               ensure_ascii=False))
'''


def run_mcp(entry, sandbox):
    root, repo, meta, home = sandbox
    env = env_for(repo, meta, home, entry.get('env'))
    before = snapshot(root)
    spec = json.dumps({'tool': entry['tool'], 'args': entry.get('args', {})})
    rc, out, err = _run([sys.executable, '-c', MCP_WRAPPER, spec], env, repo)
    after = snapshot(root)
    res = _extract(out) or {}
    payload = res.get('payload')
    return {
        'entry': 'MCP',
        'ok': res.get('isError') is False and payload is not None,
        'isError': res.get('isError'),
        'payload': payload,
        'stderr_head': (err or '').strip().splitlines()[:2],
        'new_files': sorted(set(after) - set(before)),
    }


API_WRAPPER = r'''
import json, sys
spec = json.loads(sys.argv[1])
ns = {}
exec(spec['code'], {'json': json, 'os': __import__('os')}, ns)
print('__RESULT__', json.dumps(ns['result'], ensure_ascii=False, default=str))
'''


def run_api(entry, sandbox):
    root, repo, meta, home = sandbox
    env = env_for(repo, meta, home, entry.get('env'))
    before = snapshot(root)
    rc, out, err = _run([sys.executable, '-c', API_WRAPPER, json.dumps({'code': entry['code']})],
                        env, repo)
    after = snapshot(root)
    res = _extract(out) or {}
    return {
        'entry': 'API',
        'ok': res.get('ok'),
        'payload': res.get('payload'),
        'stderr_head': (err or '').strip().splitlines()[:2],
        'new_files': sorted(set(after) - set(before)),
    }


def top_keys(payload):
    if isinstance(payload, dict):
        return sorted(payload.keys())
    return type(payload).__name__


def error_code(payload):
    if not isinstance(payload, dict):
        return None
    err = payload.get('error')
    if isinstance(err, dict):
        return err.get('code')
    return payload.get('code')


OPS = []


def op(name, cli=None, mcp=None, api=None, env=None):
    OPS.append({'name': name, 'cli': cli, 'mcp': mcp, 'api': api, 'env': env})


# ── 操作定义 ────────────────────────────────────────────────────────────
op('execute',
   cli={'argv': ['run', ACTION_ID]},
   mcp={'tool': 'demo_audit', 'args': {}},
   api={'code': 'import vools.actus as a\n'
                'r = a.execute(%r)\n'
                'from vools.actus.errors import is_failure_status\n'
                'result = {"ok": not is_failure_status(r.get("status")), "payload": r}' % ACTION_ID})

op('validate',
   cli={'argv': ['validate', ACTION_ID]},
   mcp=None,
   api={'code': 'from vools.actus.validate import validate_action\n'
                'from vools.actus.model import parse_cfg_from_file\n'
                'a = parse_cfg_from_file(os.path.join("actions", "demo.actus.md"))\n'
                'res = validate_action(a)\n'
                'result = {"ok": bool(res.get("valid")), "payload": res}'})

op('preview',
   cli={'argv': ['preview', ACTION_ID]},
   mcp={'tool': 'actus_preview', 'args': {'id': ACTION_ID}},
   api={'code': 'import vools.actus as a\n'
                'act = a.get_action(%r)\n'
                'res = a.preview(act)\n'
                'result = {"ok": not bool(res.get("error")), "payload": res}' % ACTION_ID})

op('scaffold',
   cli={'argv': ['scaffold', 'audit scaffold', '--id', 'new.one']},
   mcp={'tool': 'actus_scaffold', 'args': {'description': 'audit scaffold',
                                           'action_id': 'new.two'}},
   api={'code': 'from vools.actus.scaffold import scaffold_action\n'
                'import os\n'
                'r = scaffold_action("audit scaffold", action_id="new.three",\n'
                '                    repo_root=os.environ["ACTUS_REPO_ROOT"], confirmed=True)\n'
                'result = {"ok": r.get("status") in ("ok", "created", "skipped"), "payload": r}'})

op('vault_set',
   cli={'argv': ['vault', 'set', 'K1', 'V1']},
   mcp={'tool': 'actus_vault_set', 'args': {'key': 'K1', 'value': 'V1'}},
   api={'code': 'import os\n'
                'from vools.actus.vault import Vault, default_meta_dir\n'
                'v = Vault(default_meta_dir())\n'
                'r = v.set("K1", "V1")\n'
                'result = {"ok": r.get("status") == "ok", "payload": r}'})

op('vault_get_missing',
   cli={'argv': ['vault', 'get', 'NOPE']},
   mcp={'tool': 'actus_vault_get', 'args': {'key': 'NOPE'}},
   api={'code': 'from vools.actus.vault import Vault, default_meta_dir\n'
                'v = Vault(default_meta_dir())\n'
                'r = v.get("NOPE")\n'
                'result = {"ok": r is not None, "payload": {"value": r}}'})

op('vault_list',
   cli={'argv': ['vault', 'list']},
   mcp={'tool': 'actus_vault_list', 'args': {}},
   api={'code': 'from vools.actus.vault import Vault, default_meta_dir\n'
                'v = Vault(default_meta_dir())\n'
                'r = v.list()\n'
                'result = {"ok": isinstance(r, list), "payload": {"keys": r}}'})

op('registry_build',
   cli={'argv': ['registry', 'build']},
   mcp={'tool': 'actus_registry_list', 'args': {}},
   api={'code': 'from vools.actus.registry import ActionRegistry\n'
                'import os\n'
                'r = ActionRegistry()\n'
                'idx = r.build_from_directory(os.environ["ACTUS_REPO_ROOT"])\n'
                'result = {"ok": isinstance(idx, dict), "payload": {"keys": sorted(idx.keys())}}'})

op('registry_validate_missing',
   cli={'argv': ['registry', 'validate']},
   mcp=None,
   api={'code': 'from vools.actus.registry import ActionRegistry\n'
                'r = ActionRegistry()\n'
                'idx = r.build_from_directory(None) if False else r.load_from_file("/nonexistent/x.json")\n'
                'result = {"ok": bool(idx.get("actions")) and not idx.get("corrupt"), "payload": idx}'})

op('search',
   cli={'argv': ['search', 'demo']},
   mcp={'tool': 'actus_search', 'args': {'query': 'demo'}},
   api={'code': 'from vools.actus.registry import ActionRegistry\n'
                'import os\n'
                'r = ActionRegistry(); r.load_from_repo(os.environ["ACTUS_REPO_ROOT"])\n'
                'hits = r.search("demo")\n'
                'result = {"ok": isinstance(hits, list), "payload": {"hits": hits}}'})

op('visibility_get',
   cli={'argv': ['visibility', 'get', ACTION_ID]},
   mcp={'tool': 'actus_visibility_get', 'args': {'action_id': ACTION_ID}},
   api={'code': 'import vools.actus as a\n'
                'act = a.get_action(%r)\n'
                'result = {"ok": True, "payload": {"visibility": (act.meta.get("visibility") or "public")}}'
                % ACTION_ID})

op('visibility_set_invalid',
   cli={'argv': ['visibility', 'set', ACTION_ID, '--level', 'weird']},
   mcp={'tool': 'actus_visibility_set', 'args': {'action_id': ACTION_ID, 'visibility': 'weird'}},
   api={'code': 'from vools.actus.visibility import write_action_visibility\n'
                'import os\n'
                'path = os.path.join(os.environ["ACTUS_REPO_ROOT"], "actions", "demo.actus.md")\n'
                'ok, msg = write_action_visibility(path, "weird")\n'
                'result = {"ok": ok, "payload": {"message": msg}}'})

op('team_create_invalid',
   cli={'argv': ['team', 'create', 'bad name!', '--creator', 'u1']},
   mcp={'tool': 'actus_team_create', 'args': {'name': 'bad name!', 'creator': 'u1'}},
   api={'code': 'from vools.actus.visibility import TeamManager\n'
                'try:\n'
                '    tm = TeamManager(); t = tm.create_team("bad name!", "u1")\n'
                '    result = {"ok": True, "payload": {"team": str(t)}}\n'
                'except Exception as exc:\n'
                '    result = {"ok": False, "payload": {"error": {"code": type(exc).__name__, "message": str(exc)[:80]}}}'})

op('records_list',
   cli={'argv': ['records', 'list']},
   mcp={'tool': 'actus_records_list', 'args': {}},
   api={'code': 'from vools.actus.records import list_run_records\n'
                'r = list_run_records(None)\n'
                'result = {"ok": isinstance(r, list), "payload": {"count": len(r)}}'})

op('health',
   cli={'argv': ['health']},
   mcp=None,
   api={'code': 'from vools.actus.health import HealthChecker\n'
                'h = HealthChecker()\n'
                'r = h.run_all() if hasattr(h, "run_all") else h.run()\n'
                'result = {"ok": True, "payload": {"keys": sorted(r.keys()) if isinstance(r, dict) else type(r).__name__}}'})

op('probe',
   cli={'argv': ['probe']},
   mcp={'tool': 'actus_probe', 'args': {}},
   api={'code': 'from vools.actus import probe\n'
                'r = probe.run_probe() if hasattr(probe, "run_probe") else probe.probe()\n'
                'result = {"ok": True, "payload": {"keys": sorted(r.keys()) if isinstance(r, dict) else type(r).__name__}}'})


def main():
    only = None
    if len(sys.argv) > 1 and sys.argv[1] not in ('--json',):
        only = sys.argv[1]
    rows = []
    detail = {}
    for spec in OPS:
        if only and spec['name'] != only:
            continue
        results = {}
        for entry_name, runner, entry in (
                ('CLI', run_cli, spec.get('cli')),
                ('MCP', run_mcp, spec.get('mcp')),
                ('API', run_api, spec.get('api'))):
            if not entry:
                results[entry_name] = {'entry': entry_name, 'ok': None, 'payload': None,
                                       'new_files': [], 'stderr_head': ['(no such entry)'],
                                       'rc': None, 'isError': None}
                continue
            root, repo, meta, home = make_sandbox()
            try:
                results[entry_name] = runner(entry, (root, repo, meta, home))
            finally:
                pass
        detail[spec['name']] = results
        ok_map = {k: v.get('ok') for k, v in results.items()}
        keys_map = {k: top_keys(v.get('payload')) for k, v in results.items()}
        code_map = {k: error_code(v.get('payload')) for k, v in results.items()}
        files_map = {k: v.get('new_files') for k, v in results.items()}
        rows.append({
            'op': spec['name'],
            'ok': ok_map,
            'top_keys': keys_map,
            'error_code': code_map,
            'new_files': files_map,
        })

    if '--json' in sys.argv:
        print(json.dumps({'rows': rows, 'detail': detail}, ensure_ascii=False, indent=2))
        return

    print('=' * 100)
    print('三方一致性审计（每格 = 该入口的成功判定 / 顶层键 / 错误码 / 新文件数）')
    print('=' * 100)
    header = '%-24s %-30s %-30s %-30s' % ('operation', 'CLI', 'MCP', 'API')
    print(header)
    print('-' * 100)
    for r in rows:
        cells = []
        for k in ('CLI', 'MCP', 'API'):
            ok = r['ok'][k]
            flag = '?' if ok is None else ('ok' if ok else 'FAIL')
            keys = r['top_keys'][k]
            keys_s = ','.join(keys)[:16] if isinstance(keys, list) else str(keys)[:16]
            cells.append('%s|%s|%s|%s' % (flag, keys_s, r['error_code'][k], len(r['new_files'][k] or [])))
        print('%-24s %-30s %-30s %-30s' % (r['op'], cells[0][:30], cells[1][:30], cells[2][:30]))

    print()
    print('=' * 100)
    print('明细')
    print('=' * 100)
    for name, res in detail.items():
        print('[%s]' % name)
        for entry in ('CLI', 'MCP', 'API'):
            d = res[entry]
            print('   %-4s ok=%-5s rc=%-4s isError=%-5s keys=%s' % (
                entry, d.get('ok'), d.get('rc'), d.get('isError'), top_keys(d.get('payload'))))
            if d.get('stderr_head'):
                print('        stderr: %s' % (d['stderr_head'][:1],))
            if d.get('new_files'):
                print('        new files: %s' % (d['new_files'][:6],))
            if isinstance(d.get('payload'), dict) and d['payload']:
                snippet = json.dumps(d['payload'], ensure_ascii=False)[:160]
                print('        payload: %s' % snippet)
        print()


if __name__ == '__main__':
    main()
