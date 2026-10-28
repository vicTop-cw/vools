"""desktop smoke：首页 + 动作列表 + 动作详情 + 运行端点（13 轮两个 500 的回归守卫）。

用法：在 `actus/` 下 `python tools/audit/desktop_smoke.py`（CI 里以
`continue-on-error: true` 跑，并把输出写进 Job Summary —— 告警级，不阻塞合并）。

设计取舍：
  * **真的执行动作**在 CI 里既慢又依赖环境（GUI 动作要显示器），所以"运行动作"
    只验证**端点不返回 500**（用不存在的 id 走错误分支），一样能抓住
    "handler 未捕获异常 → 500" 这类回归；
  * 动作**详情**用真实 id（只读，不执行），覆盖"解析单动作 500"这一路。
"""
import os
import sys
import tempfile

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

ok_lines, fail_lines = [], []


def _report(label, ok, detail=''):
    line = '%s %s%s' % ('✅' if ok else '❌', label, (': ' + detail) if detail else '')
    print(line)
    (ok_lines if ok else fail_lines).append(line)


def main():
    sandbox = tempfile.mkdtemp(prefix='desktop-smoke-')
    os.environ.setdefault('ACTUS_META_DIR', os.path.join(sandbox, '_meta'))
    os.environ.setdefault('HOME', sandbox)
    os.environ.setdefault('USERPROFILE', sandbox)
    os.makedirs(os.environ['ACTUS_META_DIR'], exist_ok=True)

    try:
        from fastapi.testclient import TestClient
    except ImportError as exc:
        _report('fastapi/httpx 可用（TestClient）', False, str(exc))
        return 1

    try:
        from vools.actus import desktop
    except Exception as exc:                       # noqa: BLE001
        _report('import vools.actus.desktop', False, '%s: %s' % (type(exc).__name__, exc))
        return 1
    _report('import vools.actus.desktop', True)

    # 建索引：/api/actions 读的是索引，CI 全新 _meta 下不建就是空列表
    action_ids = []
    try:
        from vools.actus.indexer import load_index
        idx = load_index()
        action_ids = [aid for aid in (idx.get('actions') or {})
                      if not aid.startswith('_invalid:')]
        _report('构建动作索引', True, 'count=%d' % len(action_ids))
    except Exception as exc:                       # noqa: BLE001
        _report('构建动作索引', False, '%s: %s' % (type(exc).__name__, exc))

    client = TestClient(desktop.app, raise_server_exceptions=False)

    # ① 首页（13 轮事故之一：500）
    try:
        r = client.get('/')
        _report('GET /（首页）200', r.status_code == 200, 'status=%d' % r.status_code)
    except Exception as exc:                       # noqa: BLE001
        _report('GET /（首页）200', False, '%s: %s' % (type(exc).__name__, exc))

    # ② 动作列表
    api_ids = []
    try:
        r = client.get('/api/actions')
        ok = r.status_code == 200
        if ok:
            payload = r.json()
            rows = (payload.get('data') or payload.get('actions'))                 if isinstance(payload, dict) else payload
            for row in (rows or []):
                aid = row.get('id') if isinstance(row, dict) else row
                if aid:
                    api_ids.append(aid)
        _report('GET /api/actions 200', ok, 'status=%d count=%d' % (r.status_code, len(api_ids)))
    except Exception as exc:                       # noqa: BLE001
        _report('GET /api/actions 200', False, '%s: %s' % (type(exc).__name__, exc))

    # ③ 动作详情（只读，不执行）——覆盖"解析单动作 500"
    probe_id = (api_ids or action_ids or [None])[0]
    if probe_id:
        try:
            r = client.get('/api/actions/%s' % probe_id)
            _report('GET /api/actions/<%s> 无 500' % probe_id,
                    r.status_code != 500, 'status=%d' % r.status_code)
        except Exception as exc:                   # noqa: BLE001
            _report('GET /api/actions/<id> 无 500', False,
                    '%s: %s' % (type(exc).__name__, exc))
    else:
        _report('GET /api/actions/<id> 无 500', True, '（无动作，跳过）')

    # ④ 运行端点：用不存在的 id 走错误分支，只要求"不 500"
    try:
        r = client.post('/api/actions/__smoke_missing__/run', json={'params': {}})
        _report('POST /api/actions/<missing>/run 无 500',
                r.status_code != 500, 'status=%d' % r.status_code)
    except Exception as exc:                       # noqa: BLE001
        _report('POST /api/actions/<missing>/run 无 500', False,
                '%s: %s' % (type(exc).__name__, exc))

    print()
    print('SUMMARY: %d 通过, %d 失败' % (len(ok_lines), len(fail_lines)))
    for f in fail_lines:
        print('  ' + f)
    return 1 if fail_lines else 0


if __name__ == '__main__':
    sys.exit(main())
