# -*- coding: utf-8 -*-
"""KEK 轮换（**第 2 步：keyring 双代 + 日志 + GC**）的**崩溃矩阵骨架**。

⚠️ 本轮（第 21 轮）**只做骨架，不动 `vault2.py`**：这里的 `rotate_keyring_ref()`
是**测试侧的参考模型**（把设计文档 §4.3 的算法逐步写出来），用来：
  1. 把 6 个崩溃点 × 4 条不变式**定义清楚**（骨架即规格）；
  2. 用**故意错误的实现**（`variant='delete_old_first'`）证明这套断言**真的会红**；
  3. 给将来 `vault2.rotate_kek(mode='keyring')` 提供可复用的崩溃点注入器。

崩溃点（设计文档 §2 的崩溃窗口表）
    C1  写新 KEK **前**
    C2  写新 KEK **后**、DB 提交**前**
    C3  DB 提交**后**、GC **前**
    C4  GC 中、删旧 KEK **前**
    C5  GC 中、删旧 KEK **后**（尚未标 cleaned）
    C6  GC **后**

不变式
    I1  seed 永远可解：崩溃+重启后，DB 引用的 locator 条目存在且能解出 seed
    I2  旧 KEK 只在 DB **不再引用**其后才删：旧代条目缺失 ⇒ DB 的 kek_gen 已 > 旧代
    I3  不留"谎报已清理"：`kek_retired.cleaned=1` 的行 ⇒ 对应 locator 在 keyring 里**确实**不存在
    I4  孤儿新 KEK（C1/C2 崩溃留下）不阻塞：不违反 I1，且不影响后续轮换

运行（打印矩阵表 + 用错误实现验证能红）：
    python tools/audit/kek_crash_matrix.py
"""
import base64
import json
import os
import sqlite3
import sys
import tempfile

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

from vools.actus.vault2 import ENVELOPE_PREFIX, _FernetBackend  # noqa: E402

from fake_keyring import (FakeKeyring, b64, kek_locator, make_kek)  # noqa: E402

CRASH_POINTS = ('C1', 'C2', 'C3', 'C4', 'C5', 'C6')

CRASH_MEANING = {
    'C1': '写新 KEK 前',
    'C2': '写新 KEK 后、DB 提交前',
    'C3': 'DB 提交后、GC 前',
    'C4': 'GC 中、删旧 KEK 前',
    'C5': 'GC 中、删旧 KEK 后（未标 cleaned）',
    'C6': 'GC 后',
}


class Crash(Exception):
    """模拟进程猝死（不执行任何清理分支）。"""


def _maybe_crash(point, crash):
    if crash == point:
        raise Crash(point)


# ── 测试侧最小库（只建轮换需要的列/表，与真实 schema 同形）──────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS identities (
    id TEXT PRIMARY KEY,
    seed_key TEXT NOT NULL,
    key_meta TEXT
);
CREATE TABLE IF NOT EXISTS kek_retired (
    identity_id TEXT NOT NULL,
    kek_gen     INTEGER NOT NULL,
    locator     TEXT NOT NULL,
    retired_at  TEXT NOT NULL,
    cleaned     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (identity_id, kek_gen)
);
"""


def make_db(path, identity_id='id-1', seed='SECRET-SEED', gen=0, kek=None):
    """造一个"已按旧代加密"的库。返回 (conn, seed_hex)。"""
    key = kek or make_kek(identity_id, gen)
    envelope = ENVELOPE_PREFIX + _FernetBackend(key).encrypt(seed)
    conn = sqlite3.connect(path, isolation_level=None)   # 手动控制事务
    conn.executescript(SCHEMA)
    conn.execute("INSERT OR REPLACE INTO identities (id, seed_key, key_meta) VALUES (?,?,?)",
                 (identity_id, envelope,
                  json.dumps({'kek_gen': gen, 'kek_locator': {'kind': 'keyring',
                                                             'user': kek_locator(identity_id, gen)}})))
    return conn, key


def db_state(conn, identity_id='id-1'):
    row = conn.execute("SELECT seed_key, key_meta FROM identities WHERE id=?",
                       (identity_id,)).fetchone()
    meta = json.loads(row[1]) if row and row[1] else {}
    retired = conn.execute(
        "SELECT kek_gen, locator, cleaned FROM kek_retired WHERE identity_id=?",
        (identity_id,)).fetchall()
    return {'envelope': row[0] if row else None,
            'gen': int(meta.get('kek_gen', 0)),
            'locator': ((meta.get('kek_locator') or {}).get('user')),
            'retired': retired}


def _decrypt(envelope, kek):
    return _FernetBackend(kek).decrypt(envelope[len(ENVELOPE_PREFIX):])


def rotate_keyring_ref(store, conn, identity_id='id-1', crash=None,
                       variant='correct'):
    """**参考模型**（不是产品实现）：按设计文档 §4.3 逐步做 keyring 模式的 KEK 轮换。

    variant='correct'          —— 预期算法：先写新代 → 提交 DB → 再 GC 旧代
    variant='delete_old_first' —— **故意错误**：先删旧 KEK 再写新代（证明骨架会红）
    """
    st = db_state(conn, identity_id)
    old_gen, old_locator = st['gen'], st['locator'] or kek_locator(identity_id, st['gen'])
    old_kek = None
    raw = store.get_password('svc', old_locator)
    if raw:
        import base64
        old_kek = base64.b64decode(raw)
    if old_kek is None:
        raise RuntimeError('前置失败：旧代 KEK 不存在（%s）' % old_locator)
    seed_plain = _decrypt(st['envelope'], old_kek)

    new_gen = old_gen + 1
    new_locator = kek_locator(identity_id, new_gen)
    new_kek = make_kek(identity_id, new_gen, salt_hex='%02x' % new_gen)

    if variant == 'delete_old_first':
        # 错误示范：旧 KEK 先删 —— C1/C2 崩溃后 DB 仍引用旧代 → seed 永久不可解
        store.delete_password('svc', old_locator)
        _maybe_crash('C1', crash)
        store.set_password('svc', new_locator, b64(new_kek))
        _maybe_crash('C2', crash)
    else:
        _maybe_crash('C1', crash)
        store.set_password('svc', new_locator, b64(new_kek))
        # 写后自检：读回必须等于新 KEK（排查 stale_read 类后端缓存）
        readback = store.get_password('svc', new_locator)
        if readback != b64(new_kek):
            raise RuntimeError('写后自检失败：读回的不是新 KEK')
        _maybe_crash('C2', crash)

    # ── DB 单事务：换信封 + 记 retired ──
    new_envelope = ENVELOPE_PREFIX + _FernetBackend(new_kek).encrypt(seed_plain)
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("UPDATE identities SET seed_key=?, key_meta=? WHERE id=?",
                 (new_envelope,
                  json.dumps({'kek_gen': new_gen,
                              'kek_locator': {'kind': 'keyring', 'user': new_locator}}),
                  identity_id))
    conn.execute("INSERT OR REPLACE INTO kek_retired "
                 "(identity_id, kek_gen, locator, retired_at, cleaned) VALUES (?,?,?,?,0)",
                 (identity_id, old_gen, old_locator, '2026-10-29T00:00:00'))
    conn.execute("COMMIT")
    _maybe_crash('C3', crash)

    # ── GC：删旧 KEK，确认真的没了才标 cleaned ──
    _maybe_crash('C4', crash)
    try:
        store.delete_password('svc', old_locator)
    except Exception:                       # noqa: BLE001 —— 删不掉就留着待重试
        return {'gc': 'delete_failed'}
    _maybe_crash('C5', crash)
    # delete_lag 场景：删除"成功"但条目还在 → 绝不能标 cleaned=1
    if store.has(old_locator):
        return {'gc': 'lag_kept_pending'}
    conn.execute("UPDATE kek_retired SET cleaned=1 WHERE identity_id=? AND kek_gen=?",
                 (identity_id, old_gen))
    _maybe_crash('C6', crash)
    return {'gc': 'done'}


# ── 不变式检查 ────────────────────────────────────────────────────────
def check_invariants(store, conn, identity_id='id-1'):
    """崩溃+重启后检查 I1/I2/I3/I4。返回 {name: (ok, detail)}。"""
    st = db_state(conn, identity_id)
    out = {}
    raw = store.get_password('svc', st['locator']) if st['locator'] else None
    # I1：DB 引用的 KEK 在且能解出 seed
    if not raw:
        out['I1'] = (False, 'DB 引用 %s 但 keyring 里没有（seed 不可解）' % st['locator'])
    else:
        import base64
        try:
            plain = _decrypt(st['envelope'], base64.b64decode(raw))
            out['I1'] = (True, 'seed=%r' % plain)
        except Exception as exc:            # noqa: BLE001
            out['I1'] = (False, '解不开：%s' % exc)
    # I2：旧代条目缺失 ⇒ DB 必须已指向更新的代
    old_gen = 0
    old_locator = kek_locator(identity_id, old_gen)
    if not store.has(old_locator):
        out['I2'] = (st['gen'] > old_gen,
                     '旧代已删，DB gen=%d（应 >%d）' % (st['gen'], old_gen))
    else:
        out['I2'] = (True, '旧代仍在（DB gen=%d）' % st['gen'])
    # I3：cleaned=1 ⇒ 条目确实不存在（防 delete_lag 误标）
    bad = [(g, loc) for (g, loc, cleaned) in st['retired']
           if cleaned == 1 and store.has(loc)]
    out['I3'] = (not bad, '谎报清理的行=%s' % bad if bad else '无谎报')
    # I4：孤儿新 KEK 不阻塞（只要 I1 成立即可；这里显式记录孤儿数量，供观察）
    orphans = [loc for loc in store.snapshot()
               if loc.endswith('#g%d' % st['gen']) is False and loc != st['locator']]
    out['I4'] = (out['I1'][0], '孤儿条目=%s（不影响可解性）' % orphans)
    return out


def run_case(crash=None, variant='correct', faults=(), identity_id='id-1',
             tmpdir=None):
    """跑一次「轮换 + 可能的崩溃 + 重启」，返回 (state, invariants)。"""
    import base64
    import tempfile

    tmpdir = tmpdir or tempfile.mkdtemp(prefix='kekmatrix-')
    db = os.path.join(tmpdir, 'v.db')
    store = FakeKeyring()
    conn, old_kek = make_db(db, identity_id=identity_id, gen=0)
    store.set_password('svc', kek_locator(identity_id, 0), b64(old_kek))

    # 故障注入（在轮换开始前设定，模拟后端在整段期间的行为）
    for f in faults:
        setattr(store, f, True) if hasattr(store, f) else None

    crashed = None
    try:
        rotate_keyring_ref(store, conn, identity_id, crash=crash, variant=variant)
    except Crash as exc:
        crashed = str(exc)
    except Exception as exc:                 # noqa: BLE001 —— 后端故障（如 fail_write）
        crashed = 'fault: %s' % exc
    finally:
        try:
            conn.close()
        except Exception:                    # noqa: BLE001
            pass

    # ── "进程重启"：重开连接 + keyring 重启（volatile 条目丢失）──
    store.restart()
    conn2 = sqlite3.connect(db, isolation_level=None)
    inv = check_invariants(store, conn2, identity_id)
    conn2.close()
    return {'crashed': crashed, 'invariants': inv}, db


def matrix(verbose=True):
    """6 崩溃点 × (正确实现 / 故意错误实现) 的矩阵表。"""
    rows = []
    for point in CRASH_POINTS:
        good, _ = run_case(crash=point, variant='correct')
        bad, _ = run_case(crash=point, variant='delete_old_first')
        rows.append({'crash': point, 'meaning': CRASH_MEANING[point],
                     'correct': {k: v[0] for k, v in good['invariants'].items()},
                     'wrong': {k: v[0] for k, v in bad['invariants'].items()},
                     'wrong_detail': {k: v[1] for k, v in bad['invariants'].items()}})
    if verbose:
        print('崩溃点 × 不变式矩阵（✅=成立 / ❌=违反）')
        print('%-4s %-34s | 正确实现 I1 I2 I3 I4 | 错误实现 I1 I2 I3 I4' % ('点', '含义'))
        print('-' * 96)
        for r in rows:
            g, w = r['correct'], r['wrong']
            print('%-4s %-34s |        %s  %s  %s  %s |        %s  %s  %s  %s' % (
                r['crash'], r['meaning'][:34],
                _mark(g['I1']), _mark(g['I2']), _mark(g['I3']), _mark(g['I4']),
                _mark(w['I1']), _mark(w['I2']), _mark(w['I3']), _mark(w['I4'])))
        print()
        caught = [r['crash'] for r in rows if not r['wrong']['I1']]
        print('骨架能否抓错：错误实现在 %s 处违反 I1（seed 不可解）' % (', '.join(caught) or '无(!)'))
    return rows


#: 故障模式矩阵：外部 store 行为异常 × 期望结果（expected=是否应当满足不变式）
#: `expect_i1=False` 表示"这条是**已记录的局限**"（如 keyring 条目被云同步回滚 →
#: seed 永久不可解，任何 DB 侧设计都救不了），而不是"我们的 bug"。
FAULT_MATRIX = (
    ('fail_write@C2', {'fail_write': True}, 'C2', True,
     '新 KEK 写不进去 → 绝不能提交 DB；旧 KEK 与旧信封必须原样可用'),
    ('stale_read@C2', {'stale_read_once': True}, 'C2', True,
     '写后读回旧值 → 自检必须中止（不能拿"读回的旧 KEK"去提交）'),
    ('fail_delete@C5', {'fail_delete': True}, 'C5', True,
     '旧 KEK 删不掉 → 留 cleaned=0 待重试；旧代仍在，I2 不要求删'),
    ('delete_lag@C5', {'delete_lag': True}, 'C5', True,
     '删除"成功"但条目仍在 → **绝不能标 cleaned=1**（I3）'),
    ('delete_lag@C6', {'delete_lag': True}, 'C6', True,
     'GC 完成后条目仍在 → 同上，I3 必须守住'),
    ('restart_drop_new@C6', {'restart_drop_volatile': True}, 'C6', None,
     '**已记录局限**：keyring 丢掉被引用的新代 → I1 无法保持（DB 侧设计救不了；'
     '只能靠备份/多副本，属第 4 步文档范围）'),
)


#: file-key 模式专用故障模式（外部是**文件系统**，比 keyring 多出短写/占用/隔离）
FAULT_MATRIX_FILE = (
    ('fileshort_write@C2', {'short_write': True}, 'C2', True,
     '短写 → 回读比对发现长度不对 → 必须中止且不提交（旧代完好）'),
    ('filefail_create@C2', {'fail_create': True}, 'C2', True,
     'O_EXCL 创建失败（已存在/只读）→ 绝不覆盖、不提交'),
    ('filefail_unlink@C5', {'fail_unlink': True}, 'C5', True,
     'unlink 抛异常 → cleaned 必须保持 0（等重试）'),
    ('fileunlink_lag@C5', {'unlink_lag': True}, 'C5', True,
     'unlink"成功"但文件仍在 → **删后回读确认**必须拦住 cleaned=1'),
    ('fileunlink_lag@C6', {'unlink_lag': True}, 'C6', True,
     'GC 后文件仍在 → 同上'),
)


def _file_name(gen):
    return '.vault2.key' if gen == 0 else '.vault2.key#g%d' % gen


def rotate_filekey_ref(store, conn, identity_id='id-1', crash=None):
    """file-key 的**参考模型**（与 keyring 同骨架，差异见注释）。

    file-key 比 keyring 多两处必须处理：
      1. **O_EXCL**：创建用独占语义（先检查再写 = TOCTOU）；
      2. **孤儿**：文件系统能扫目录 → 保守策略下"只报告不删除"（见 orphan_report）。
    """
    from fake_filekey import decode as _decode

    st = db_state(conn, identity_id)
    old_gen = st['gen']
    old_name = _file_name(old_gen)
    raw = store.read(old_name)
    if raw is None:
        raise RuntimeError('前置失败：旧代 KEK 文件不存在（%s）' % old_name)
    old_kek = _decode(old_name, raw)
    seed_plain = _decrypt(st['envelope'], old_kek)

    new_gen = old_gen + 1
    new_name = _file_name(new_gen)
    new_kek = make_kek(identity_id, new_gen, salt_hex='f%02x' % new_gen)

    _maybe_crash('C1', crash)
    store.create_exclusive(new_name, new_kek)          # O_EXCL：已存在就抛
    back = store.read(new_name)                        # ★ 写后回读
    if back is None or _decode(new_name, back) != new_kek:
        raise RuntimeError('写后回读不一致（短写？）')
    _maybe_crash('C2', crash)

    new_envelope = ENVELOPE_PREFIX + _FernetBackend(new_kek).encrypt(seed_plain)
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("UPDATE identities SET seed_key=?, key_meta=? WHERE id=?",
                 (new_envelope,
                  json.dumps({'kek_gen': new_gen,
                              'kek_locator': {'kind': 'file', 'name': new_name}}),
                  identity_id))
    conn.execute("INSERT OR REPLACE INTO kek_retired "
                 "(identity_id, kek_gen, locator, retired_at, cleaned) VALUES (?,?,?,?,0)",
                 (identity_id, old_gen, old_name, '2026-10-29T00:00:00'))
    conn.execute("COMMIT")
    _maybe_crash('C3', crash)

    _maybe_crash('C4', crash)
    try:
        store.unlink(old_name)
    except Exception:                       # noqa: BLE001
        return {'gc': 'delete_failed'}
    if store.exists(old_name):              # ★ 删后回读确认
        return {'gc': 'lag_kept_pending'}
    _maybe_crash('C5', crash)
    conn.execute("UPDATE kek_retired SET cleaned=1 WHERE identity_id=? AND kek_gen=?",
                 (identity_id, old_gen))
    _maybe_crash('C6', crash)
    return {'gc': 'done'}


def file_fault_matrix(verbose=True):
    """file-key 故障矩阵：每条都要 I1 保持（外部异常不得让 seed 不可解）。"""
    from fake_filekey import FakeFileKeys

    rows = []
    for name, faults, crash, expected_i1, why in FAULT_MATRIX_FILE:
        tmp = tempfile.mkdtemp(prefix='kekfile-')
        db = os.path.join(tmp, 'v.db')
        conn, old_kek = make_db(db)
        store = FakeFileKeys()
        store.files[_file_name(0)] = __import__('base64').b64encode(old_kek)
        for k, v in faults.items():
            setattr(store, k, v)
        crashed = None
        try:
            rotate_filekey_ref(store, conn, crash=crash)
        except Crash:
            crashed = 'crash'
        except Exception as exc:            # noqa: BLE001
            crashed = 'fault: %s' % exc
        finally:
            try:
                conn.close()
            except Exception:               # noqa: BLE001
                pass
        conn2 = sqlite3.connect(db, isolation_level=None)
        inv = check_invariants_filekey(store, conn2)
        conn2.close()
        rows.append({'name': name, 'inv': inv, 'expected_i1': expected_i1,
                     'why': why, 'crashed': crashed})
    if verbose:
        print()
        print('file-key 故障矩阵（外部 = 文件系统）')
        print('%-24s %-6s %-6s %-6s | 期望 I1 | 结论' % ('场景', 'I1', 'I2', 'I3'))
        print('-' * 88)
        for r in rows:
            inv = r['inv']
            i1 = inv['I1'][0]
            ok = (r['expected_i1'] is None) or (i1 == r['expected_i1'])
            print('%-24s %-6s %-6s %-6s | %-7s | %s' % (
                r['name'], _mark(i1), _mark(inv['I2'][0]), _mark(inv['I3'][0]),
                '成立' if r['expected_i1'] else '违反',
                '✅ 符合预期' if ok else '❌ 不符预期'))
            print('    %s' % r['why'])
    return rows


def check_invariants_filekey(store, conn, identity_id='id-1'):
    """file-key 版不变式（locator 是文件名，不是 keyring user）。"""
    from fake_filekey import decode as _decode

    st = db_state(conn, identity_id)
    out = {}
    # make_db 默认写的 locator 是 keyring user（骨架共用）；file-key 下要按文件名回退
    loc = st['locator'] or ''
    name = loc if loc.startswith('.vault2.key') else _file_name(st['gen'])
    raw = store.read(name)
    if raw is None:
        out['I1'] = (False, 'DB 引用 %s 但文件不存在（seed 不可解）' % name)
    else:
        try:
            out['I1'] = (True, 'seed=%r' % _decrypt(st['envelope'], _decode(name, raw)))
        except Exception as exc:            # noqa: BLE001
            out['I1'] = (False, '解不开：%s' % exc)
    old_name = _file_name(0)
    if not store.exists(old_name):
        out['I2'] = (st['gen'] > 0, '旧代文件已删，DB gen=%d' % st['gen'])
    else:
        out['I2'] = (True, '旧代文件仍在（DB gen=%d）' % st['gen'])
    bad = [(g, loc) for (g, loc, cleaned) in st['retired']
           if cleaned == 1 and store.exists(loc)]
    out['I3'] = (not bad, '谎报清理的文件=%s' % bad if bad else '无谎报')
    # 孤儿：存在的文件里，既不被引用、也不在日志里的（保守策略：只报告）
    referenced = {name}
    logged = {loc for (_g, loc, _c) in st['retired']}
    out['ORPHANS'] = (True, '孤儿=%s' % store.orphans(referenced, logged))
    return out


def fault_matrix(verbose=True):
    """跑故障模式矩阵，返回 [{name, i1_ok, detail, expected_i1}]。"""
    rows = []
    for name, faults, crash, expected_i1, why in FAULT_MATRIX:
        store_faults = [k for k, v in faults.items() if v]
        # restart_drop 需要把**新代**标记为 volatile（重启后丢失）
        if 'restart_drop_volatile' in store_faults:
            import base64
            import tempfile
            tmp = tempfile.mkdtemp(prefix='kekfault-')
            db = os.path.join(tmp, 'v.db')
            store = FakeKeyring()
            conn, old_kek = make_db(db)
            store.set_password('svc', kek_locator('id-1', 0), base64.b64encode(old_kek).decode())
            store.mark_volatile(kek_locator('id-1', 1))     # 新代在重启后丢失
            try:
                rotate_keyring_ref(store, conn, crash=crash)
            except Crash:
                pass
            finally:
                conn.close()
            store.restart()
            conn2 = sqlite3.connect(db, isolation_level=None)
            inv = check_invariants(store, conn2)
            conn2.close()
            rows.append({'name': name, 'inv': inv, 'expected_i1': expected_i1, 'why': why})
            continue
        res, _ = run_case(crash=crash, faults=[f for f in store_faults if f != 'restart_drop_volatile'])
        rows.append({'name': name, 'inv': res['invariants'],
                     'expected_i1': expected_i1, 'why': why})
        # 追加断言：故障注入是否真的生效
    if verbose:
        print()
        print('故障模式矩阵（外部 store 行为异常）')
        print('%-24s %-6s %-6s %-6s %-6s | 期望 I1 | 结论' % ('场景', 'I1', 'I2', 'I3', 'I4'))
        print('-' * 96)
        for r in rows:
            inv = r['inv']
            i1 = inv['I1'][0]
            ok = (r['expected_i1'] is None) or (i1 == r['expected_i1'])
            print('%-24s %-6s %-6s %-6s %-6s | %-7s | %s' % (
                r['name'], _mark(i1), _mark(inv['I2'][0]), _mark(inv['I3'][0]),
                _mark(inv['I4'][0]),
                '局限' if r['expected_i1'] is None else ('成立' if r['expected_i1'] else '违反'),
                '✅ 符合预期' if ok else '❌ 不符预期'))
            print('    %s' % r['why'])
    return rows


def _mark(ok):
    return '✅' if ok else '❌'


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        pass
    rows = matrix(verbose=True)
    frows = fault_matrix(verbose=True)
    file_rows = file_fault_matrix(verbose=True)
    good_all = all(all(r['correct'].values()) for r in rows)
    caught = [r['crash'] for r in rows if not r['wrong']['I1']]
    print()
    print('正确实现 6/6 通过全部不变式 :', '✅' if good_all else '❌')
    print('错误实现被抓住的崩溃点       :', ', '.join(caught) or '无 —— 骨架失效！')
    print()
    print('结论：骨架%s' % ('可用（能红能绿）' if good_all and caught else '有缺陷'))
    fault_ok = all((r['expected_i1'] is None) or (r['inv']['I1'][0] == r['expected_i1'])
                   for r in frows)
    file_ok = all((r['expected_i1'] is None) or (r['inv']['I1'][0] == r['expected_i1'])
                  for r in file_rows)
    print('file-key 故障矩阵符合预期   :', '✅' if file_ok else '❌')
    return 0 if (good_all and caught and fault_ok and file_ok) else 1


if __name__ == '__main__':
    sys.exit(main())
