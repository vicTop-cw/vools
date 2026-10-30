"""calllog.py 契约测试（第 79 轮：本模块此前无专门契约测试文件）。

覆盖：
  1. _now_iso 格式（+08:00、秒级）、_default_meta 优先级（ACTUS_METRICS_DIR 逃生门）
  2. log_path / metrics_path / _next_seq 单调
  3. CallLogStore：构造不落盘（第 16 轮契约）、写读、JSON 兜底、8000 截断、
     max_rows 裁剪（seq%500 门）、SQLite 失败降级内存、纯读不建库、内存环形上限
  4. get_store 单例（按 meta_dir 换键）、write_call_log/recent_call_logs
  5. instrument/_InstrumentCtx：正常/异常（ok=False + result 提要、异常继续上抛、
     日志失败不影响业务）
  6. action_metrics：write_action_metric（空 id 拒/成功/失败 best-effort）、
     _metrics_exclusions、aggregate_metrics（零值/聚合/7d30d 窗口/自指排除/坏库零值）、
     popular_actions（排序/success_rate/limit 钳制）、trending_actions（增长公式/
     新动作 2.0/排序/空库）
"""
import json
import os
import sqlite3

import pytest

from vools.actus import calllog as C


# ═══════════════════════════════════════════════════════════════════
# 夹具
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
def world(monkeypatch, tmp_path):
    home = tmp_path / "home"
    meta = tmp_path / "meta"
    for d in (home, meta):
        d.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("ACTUS_META_DIR", str(meta))
    monkeypatch.delenv("ACTUS_METRICS_DIR", raising=False)
    return {"home": home, "meta": meta, "tmp": tmp_path}


@pytest.fixture
def fresh_store(world, monkeypatch):
    """显式 meta_dir 的独立库 + 把全局单例指向它（instrument 走 write_call_log→get_store）。"""
    mdir = str(world["tmp"] / "logmeta")
    os.makedirs(mdir, exist_ok=True)
    monkeypatch.setattr(C, '_default_meta', lambda: mdir)
    monkeypatch.setattr(C, '_store', None)
    return C.CallLogStore(meta_dir=mdir), mdir


def _insert_metric(mdir, action_id, ts, caller='executor', ok=1, runtime_ms=10):
    os.makedirs(mdir, exist_ok=True)
    db = sqlite3.connect(C.metrics_path(mdir))
    try:
        db.execute(C._METRICS_DDL)  # 独立插行前先建表（write_action_metric 才建）
        db.execute("INSERT INTO action_metrics (action_id, ts, caller, ok, runtime_ms)"
                   " VALUES (?,?,?,?,?)", (action_id, ts, caller, ok, runtime_ms))
        db.commit()
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════
# ① 基础函数
# ═══════════════════════════════════════════════════════════════════


class TestBasics:
    def test_now_iso_shape(self):
        ts = C._now_iso()
        assert ts.endswith('+08:00')
        assert len(ts) == 25  # YYYY-MM-DDTHH:MM:SS+08:00

    def test_default_meta_metrics_dir_wins(self, world, monkeypatch):
        mdir = str(world["tmp"] / "metricshome")
        os.makedirs(mdir, exist_ok=True)
        monkeypatch.setenv("ACTUS_METRICS_DIR", mdir)
        assert C._default_meta() == mdir

    def test_default_meta_falls_to_meta_dir(self, world):
        assert os.path.samefile(C._default_meta(), str(world["meta"]))

    def test_log_path_explicit_and_default(self, world):
        assert C.log_path('X').endswith(os.path.join('X', 'call_log.db'))
        assert C.log_path() == os.path.join(str(world["meta"]), 'call_log.db')

    def test_metrics_path_same_db(self, world):
        assert C.metrics_path(str(world["tmp"])) == C.log_path(str(world["tmp"]))

    def test_next_seq_monotonic(self):
        a, b = C._next_seq(), C._next_seq()
        assert b == a + 1


# ═══════════════════════════════════════════════════════════════════
# ② CallLogStore
# ═══════════════════════════════════════════════════════════════════


class TestCallLogStore:
    def test_construct_does_not_create_db(self, fresh_store):
        store, mdir = fresh_store
        assert store.available is True
        assert not os.path.exists(os.path.join(mdir, 'call_log.db'))

    def test_write_and_recent_roundtrip(self, fresh_store):
        store, _ = fresh_store
        assert store.write('tool_a', params={'k': 1}, result={'r': 2},
                           ok=True, runtime_ms=7, caller='mcp', ns='ns1') is True
        rows = store.recent()
        assert len(rows) == 1
        r = rows[0]
        assert r['tool'] == 'tool_a' and r['ns'] == 'ns1'
        assert json.loads(r['params']) == {'k': 1}
        assert json.loads(r['result']) == {'r': 2}
        assert r['ok'] is True and r['runtime_ms'] == 7

    def test_recent_newest_first(self, fresh_store):
        store, _ = fresh_store
        for i in range(3):
            store.write('t%d' % i)
        rows = store.recent(2)
        assert [r['tool'] for r in rows] == ['t2', 't1']

    def test_recent_limit_clamps(self, fresh_store):
        store, _ = fresh_store
        store.write('only')
        assert store.recent(0)[0]['tool'] == 'only'      # 0 → 50 兜底（现状）
        assert store.recent(-5)[0]['tool'] == 'only'     # 负数 → 1
        assert store.recent(None)[0]['tool'] == 'only'

    def test_non_json_params_falls_back_to_str(self, fresh_store):
        store, _ = fresh_store
        obj = object()
        store.write('t', params=obj, result=obj)
        r = store.recent()[0]
        assert 'object' in r['params'] or r['params']  # default=str 可读形态

    def test_oversize_payload_truncated(self, fresh_store):
        store, _ = fresh_store
        big = 'x' * 9000
        store.write('t', params=big, result=big)
        r = store.recent()[0]
        assert len(r['params']) < 9000
        assert r['params'].endswith('…<truncated>')
        assert r['result'].endswith('…<truncated>')

    def test_max_rows_prune_on_seq_mod_500(self, fresh_store):
        store, _ = fresh_store
        store.max_rows = 5
        for i in range(10):
            store.write('fill%d' % i)
        store.write('trigger', seq=500)  # 显式 seq 命中裁剪门
        rows = store.recent(50)
        # 裁剪语义：DELETE id <= MAX(id)-5 → 11 行保留最后 5 行（含 trigger）
        assert len(rows) == 5
        assert rows[0]['tool'] == 'trigger'

    def test_sql_failure_degrades_to_memory(self, fresh_store):
        store, _ = fresh_store

        def boom():
            raise RuntimeError('db gone')

        store._connect = boom
        assert store.write('mem_tool') is False
        rows = store.recent()
        assert rows[0]['tool'] == 'mem_tool'
        assert rows[0]['ok'] is True

    def test_memory_mode_and_ring_limit(self, fresh_store):
        store, _ = fresh_store
        store._use_sql = False
        for i in range(C._MEM_LIMIT + 10):
            store.write('m%d' % i)
        assert store.write('last') is False
        # 写 'last' 后 len=501 → 环掉最旧一条（m10）→ 头部变 m11
        rows = store.recent(10)
        assert len(rows) == 10
        assert rows[0]['tool'] == 'last'
        assert store._mem[0]['tool'] == 'm11'

    def test_pure_read_does_not_create_db(self, fresh_store):
        store, mdir = fresh_store
        assert store.recent() == []
        assert not os.path.exists(os.path.join(mdir, 'call_log.db'))

    def test_recent_sql_read_failure_falls_to_mem(self, fresh_store):
        store, _ = fresh_store
        store.write('t1')
        store._mem.append({'seq': 1, 'ts': 'x', 'tool': 'mem_row', 'caller': '',
                           'ns': '', 'params': '{}', 'result': '{}',
                           'ok': True, 'runtime_ms': 0})
        # recent 里 SQL 读异常 → 回内存
        orig_connect = store._connect

        def flaky():
            store._connect = orig_connect  # 只炸一次
            raise RuntimeError('read fail')

        store._connect = flaky
        rows = store.recent()
        assert rows[0]['tool'] == 'mem_row'
        assert store._connect is orig_connect

    def test_close_is_noop(self, fresh_store):
        store, _ = fresh_store
        assert store.close() is None


# ═══════════════════════════════════════════════════════════════════
# ③ 单例与便捷入口
# ═══════════════════════════════════════════════════════════════════


class TestSingleton:
    def test_get_store_same_key_same_instance(self, world):
        mdir = str(world["tmp"] / "s1")
        os.makedirs(mdir, exist_ok=True)
        a = C.get_store(mdir)
        b = C.get_store(mdir)
        assert a is b

    def test_get_store_key_change_rebuilds(self, world):
        m1 = str(world["tmp"] / "s1")
        m2 = str(world["tmp"] / "s2")
        for m in (m1, m2):
            os.makedirs(m, exist_ok=True)
        a = C.get_store(m1)
        b = C.get_store(m2)
        assert a is not b
        c = C.get_store(m1)          # 键换回 → 重建新实例
        assert c is not a
        assert C.get_store(m1) is c  # 重建后同键复用

    def test_write_call_log_and_recent_helpers(self, world):
        mdir = str(world["tmp"] / "s3")
        os.makedirs(mdir, exist_ok=True)
        C._store = None  # 隔离全局单例
        try:
            store = C.get_store(mdir)
            assert C.write_call_log('helper_tool', params={'p': 1}) is True
            rows = C.recent_call_logs(5)
            assert rows[0]['tool'] == 'helper_tool'
        finally:
            C._store = None


# ═══════════════════════════════════════════════════════════════════
# ④ instrument
# ═══════════════════════════════════════════════════════════════════


class TestInstrument:
    def test_happy_path_records(self, fresh_store):
        store, _ = fresh_store
        with C.instrument('ctx_tool', caller='cli', ns='nsx') as ctx:
            ctx.params = {'a': 1}
            ctx.result = {'done': True}
        rows = store.recent()
        assert rows[0]['tool'] == 'ctx_tool'
        assert rows[0]['caller'] == 'cli' and rows[0]['ns'] == 'nsx'
        assert json.loads(rows[0]['result']) == {'done': True}
        assert rows[0]['ok'] is True
        assert rows[0]['runtime_ms'] >= 0

    def test_exception_marks_failure_and_reraises(self, fresh_store):
        store, _ = fresh_store
        with pytest.raises(ValueError):
            with C.instrument('boom_tool') as ctx:
                raise ValueError('kapow')
        r = store.recent()[0]
        assert r['ok'] is False
        assert 'ValueError' in r['result'] and 'kapow' in r['result']

    def test_exception_with_user_result_keeps_it(self, fresh_store):
        store, _ = fresh_store
        with pytest.raises(RuntimeError):
            with C.instrument('boom2') as ctx:
                ctx.result = {'partial': True}
                raise RuntimeError('late')
        r = store.recent()[0]
        assert json.loads(r['result']) == {'partial': True}
        assert r['ok'] is False

    def test_log_failure_does_not_break_business(self, fresh_store, monkeypatch):
        store, _ = fresh_store
        monkeypatch.setattr(C, 'write_call_log',
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError('log down')))
        with C.instrument('ok_tool') as ctx:
            ctx.result = 1
        # 不抛 → 业务不受日志故障影响
        assert True


# ═══════════════════════════════════════════════════════════════════
# ⑤ action_metrics
# ═══════════════════════════════════════════════════════════════════


class TestMetrics:
    def test_write_metric_empty_id_rejected(self, world):
        assert C.write_action_metric('') is False

    def test_write_metric_ok_and_row(self, world):
        mdir = str(world["tmp"] / "m1")
        assert C.write_action_metric('a.b', ok=True, runtime_ms=33,
                                     caller='executor', meta_dir=mdir) is True
        db = sqlite3.connect(C.metrics_path(mdir))
        try:
            rows = db.execute("SELECT action_id, caller, ok, runtime_ms"
                              " FROM action_metrics").fetchall()
        finally:
            db.close()
        assert rows == [('a.b', 'executor', 1, 33)]

    def test_write_metric_failure_best_effort(self, world, monkeypatch):
        monkeypatch.setattr(C, '_metrics_connect',
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError('no db')))
        assert C.write_action_metric('a.b') is False

    def test_exclusions_clause(self):
        assert C._metrics_exclusions([]) == ('', [])
        clause, params = C._metrics_exclusions(['quality', 'mcp'])
        assert clause == 'AND caller NOT IN (?, ?)'
        assert params == ['quality', 'mcp']

    def test_aggregate_empty_is_all_zero(self, world):
        mdir = str(world["tmp"] / "m2")
        out = C.aggregate_metrics('nope', meta_dir=mdir)
        assert out == {'total': 0, 'last_7d': 0, 'last_30d': 0,
                       'success_rate': 0.0, 'avg_runtime_ms': 0, 'unique_callers': 0}

    def test_aggregate_full(self, world):
        from datetime import datetime, timedelta, timezone
        mdir = str(world["tmp"] / "m3")
        now = datetime.now(C._TZ)
        _insert_metric(mdir, 'a.b', now.isoformat(timespec='seconds'),
                       caller='executor', ok=1, runtime_ms=100)
        _insert_metric(mdir, 'a.b', now.isoformat(timespec='seconds'),
                       caller='cli', ok=0, runtime_ms=50)
        _insert_metric(mdir, 'a.b', (now - timedelta(days=20)).isoformat(timespec='seconds'),
                       caller='executor', ok=1, runtime_ms=10)
        out = C.aggregate_metrics('a.b', meta_dir=mdir)
        assert out['total'] == 3
        assert out['success_rate'] == 0.6667  # AVG(ok)=2/3 → round(,4)
        assert out['avg_runtime_ms'] == 53  # (100+50+10)/3 = 53.33 → int 53
        assert out['unique_callers'] == 2
        assert out['last_7d'] == 2
        assert out['last_30d'] == 3

    def test_aggregate_excludes_callers(self, world):
        from datetime import datetime
        mdir = str(world["tmp"] / "m4")
        now = datetime.now(C._TZ).isoformat(timespec='seconds')
        _insert_metric(mdir, 'a.b', now, caller='quality', ok=1, runtime_ms=1)
        _insert_metric(mdir, 'a.b', now, caller='executor', ok=1, runtime_ms=1)
        out = C.aggregate_metrics('a.b', meta_dir=mdir, exclude_callers=['quality'])
        assert out['total'] == 1
        assert out['unique_callers'] == 1

    def test_aggregate_corrupt_db_returns_zeros(self, world):
        mdir = str(world["tmp"] / "m5")
        os.makedirs(mdir, exist_ok=True)
        with open(C.metrics_path(mdir), 'w', encoding='utf-8') as f:
            f.write('this is not a database')
        out = C.aggregate_metrics('a.b', meta_dir=mdir)
        assert out['total'] == 0  # best-effort 零值

    def test_popular_sorted_desc_with_rate(self, world):
        from datetime import datetime
        mdir = str(world["tmp"] / "m6")
        now = datetime.now(C._TZ).isoformat(timespec='seconds')
        for _ in range(3):
            _insert_metric(mdir, 'hot', now, ok=1)
        for _ in range(1):
            _insert_metric(mdir, 'cold', now, ok=0)
        out = C.popular_actions(meta_dir=mdir)
        assert out[0]['action_id'] == 'hot'
        assert out[0]['count'] == 3
        assert out[0]['success_rate'] == 1.0
        assert out[1]['success_rate'] == 0.0

    def test_popular_limit_clamp_and_period(self, world):
        from datetime import datetime, timedelta
        mdir = str(world["tmp"] / "m7")
        old = (datetime.now(C._TZ) - timedelta(days=40)).isoformat(timespec='seconds')
        _insert_metric(mdir, 'old.action', old)
        assert C.popular_actions(meta_dir=mdir, period_days=30) == []
        assert C.popular_actions(limit=0, meta_dir=mdir) == []  # limit→1，但无 30d 内行

    def test_popular_corrupt_db_empty(self, world):
        mdir = str(world["tmp"] / "m8")
        os.makedirs(mdir, exist_ok=True)
        with open(C.metrics_path(mdir), 'w', encoding='utf-8') as f:
            f.write('garbage')
        assert C.popular_actions(meta_dir=mdir) == []

    def test_trending_growth_and_new_action(self, world):
        from datetime import datetime, timedelta
        mdir = str(world["tmp"] / "m9")
        now = datetime.now(C._TZ)
        d10 = (now - timedelta(days=10)).isoformat(timespec='seconds')
        d20 = (now - timedelta(days=20)).isoformat(timespec='seconds')
        _insert_metric(mdir, 'steady', d20, ok=1)   # 30d only（c7=0）→ growth 0
        _insert_metric(mdir, 'hot', d10, ok=1)      # 30d only（d10 不在 7d）→ 0
        _insert_metric(mdir, 'brand.new', (now - timedelta(days=1)).isoformat(timespec='seconds'))
        out = C.trending_actions(meta_dir=mdir)
        by_id = {r['action_id']: r for r in out}
        # growth = (c7/7)/(c30/30)；brand.new c30=1,c7=1 → 30/7 ≈ 4.286
        assert by_id['brand.new']['growth'] == 4.286
        assert by_id['hot']['growth'] == 0.0
        assert by_id['steady']['growth'] == 0.0
        assert out[0]['action_id'] == 'brand.new'      # growth 降序

    def test_trending_tiebreak_by_7d_count(self, world):
        from datetime import datetime
        mdir = str(world["tmp"] / "m10")
        now = datetime.now(C._TZ).isoformat(timespec='seconds')
        _insert_metric(mdir, 'x', now)
        _insert_metric(mdir, 'x', now)
        _insert_metric(mdir, 'y', now)
        out = C.trending_actions(meta_dir=mdir)
        assert [r['action_id'] for r in out] == ['x', 'y']  # 同 growth → count_7d 降序

    def test_trending_limit(self, world):
        from datetime import datetime
        mdir = str(world["tmp"] / "m11")
        now = datetime.now(C._TZ).isoformat(timespec='seconds')
        for i in range(5):
            _insert_metric(mdir, 'a%d' % i, now)
        out = C.trending_actions(limit=2, meta_dir=mdir)
        assert len(out) == 2

    def test_trending_corrupt_db_empty(self, world):
        mdir = str(world["tmp"] / "m12")
        os.makedirs(mdir, exist_ok=True)
        with open(C.metrics_path(mdir), 'w', encoding='utf-8') as f:
            f.write('garbage')
        assert C.trending_actions(meta_dir=mdir) == []

    def test_trending_old_row_outside_all_windows(self, world):
        from datetime import datetime, timedelta
        mdir = str(world["tmp"] / "m13")
        # 40 天旧行：30d 窗口外 → SQL WHERE 直接过滤 → 空列表
        old = (datetime.now(C._TZ) - timedelta(days=40)).isoformat(timespec='seconds')
        _insert_metric(mdir, 'ancient', old)
        assert C.trending_actions(meta_dir=mdir) == []
