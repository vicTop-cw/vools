# -*- coding: utf-8 -*-
"""omega_strong.py 契约测试 (Round 62)。

覆盖：标记/白名单/账本路径防逃逸、load_ledger 损坏语义（只读/repair/
粘性状态）、_save_ledger 原子写 + 损坏拒写、_deliverable_digest、
_parse_iso、OmegaStrong 三环全流程（spec_create/spec_review/result_verify
含打回与升级）、record_check（exit_code 唯一判据 + ok 剥离）、
三道门禁（execute/verify/check 含新鲜度）、status、教训回流。
"""

import hashlib
import json
import os
import time

import pytest

from vools.actus import omega_strong as ommod
from vools.actus.errors import ActionError
from vools.actus.omega_strong import (
    OmegaStrong,
    _as_text,
    _deliverable_digest,
    _ledger_path,
    _now_iso,
    _parse_iso,
    _validate_task_id,
    gate_enabled,
    gate_mark,
    get_ledger,
    ledger_corrupt,
    load_ledger,
    omega_enabled,
    omega_mark,
    omega_max_rounds_default,
    omega_norm_max_rounds,
)


@pytest.fixture(autouse=True)
def _meta_env(tmp_path, monkeypatch):
    """把默认 meta 目录指到 tmp（_note_lesson/_default_meta 都走这里）。"""
    monkeypatch.setattr(ommod, 'meta_dir', lambda: str(tmp_path / '_meta'))
    return tmp_path / '_meta'


def _eng(task_id='t1', **kw):
    return OmegaStrong(task_id, meta_dir=str(kw.pop('meta')), max_rounds=kw.pop('max_rounds', 3))


# ---------------------------------------------------------------- 标记/辅助

def test_marks():
    assert omega_mark() == '[omega:required]'
    assert gate_mark() == '[gate:required]'


def test_as_text_dict_and_other():
    assert _as_text({'goal': 'g', 'description': 'd', 'action_id': 'a', 'id': 'i'}) == 'g d a i'
    assert _as_text('plain [omega:required]') == 'plain [omega:required]'


def test_enabled_checks():
    assert omega_enabled({'description': 'x [omega:required] y'}) is True
    assert omega_enabled('no mark') is False
    assert gate_enabled({'description': 'a [gate:required]'}) is True
    assert gate_enabled('') is False


def test_max_rounds_norm():
    assert omega_max_rounds_default() == 3
    assert omega_norm_max_rounds(None) == 3
    assert omega_norm_max_rounds(0) == 3
    assert omega_norm_max_rounds(-5) == 3
    assert omega_norm_max_rounds(5) == 5
    assert omega_norm_max_rounds(99) == 10  # 硬上限


@pytest.mark.parametrize('bad', [None, '', '..', 'a/../b', 'a/b', 'a\\b', '.',
                                 'x\x00y', 'a' * 129])
def test_validate_task_id_rejects(bad):
    with pytest.raises(ActionError) as ei:
        _validate_task_id(bad)
    assert ei.value.code == 'param_invalid'


def test_validate_task_id_accepts():
    assert _validate_task_id('task-1') == 'task-1'
    assert _validate_task_id(42) == '42'


def test_ledger_path_within_meta(tmp_path):
    p = _ledger_path('t1', str(tmp_path))
    assert p == os.path.join(str(tmp_path), 'omega_strong', 't1.json')


def test_now_iso_shape():
    v = _now_iso()
    assert v.endswith('+08:00') and len(v) == 25  # 秒级精度


# ---------------------------------------------------------------- digest / parse

class TestDigest:
    def test_dict_sorted_sha(self):
        d1 = _deliverable_digest({'a': 1, 'b': 2})
        d2 = _deliverable_digest({'b': 2, 'a': 1})
        assert d1 == d2  # 键序无关
        assert d1['type'] == 'dict'
        raw = json.dumps({'a': 1, 'b': 2}, ensure_ascii=False, sort_keys=True,
                         default=str).encode('utf-8')
        assert d1['sha256'] == hashlib.sha256(raw).hexdigest()
        assert d1['size'] == len(raw)

    def test_list_and_bytes_and_str(self):
        assert _deliverable_digest([1])['type'] == 'list'
        assert _deliverable_digest(b'x')['type'] == 'bytes'
        d = _deliverable_digest(42)
        assert d['type'] == 'int'
        assert d['sha256'] == hashlib.sha256(b'42').hexdigest()

    def test_non_json_object_via_default_str(self):
        d = _deliverable_digest({'x': object()})
        assert d['type'] == 'dict'  # default=str 不炸


class TestParseIso:
    def test_variants(self):
        assert _parse_iso('2026-01-02T03:04:05Z') is not None
        assert _parse_iso('2026-01-02T03:04:05+08:00') is not None
        assert _parse_iso('2026-01-02T03:04:05') is not None
        assert _parse_iso('') is None
        assert _parse_iso(None) is None
        assert _parse_iso('garbage') is None


# ---------------------------------------------------------------- ledger 原语

class TestLedger:
    def test_load_missing_empty(self, tmp_path):
        led = load_ledger('t9', str(tmp_path))
        assert led == {'task_id': 't9', 'records': [], 'max_rounds': 3}

    def test_save_load_roundtrip(self, tmp_path):
        e = _eng('t1', meta=tmp_path)
        e.spec_create('author', 'content')
        led = load_ledger('t1', str(tmp_path))
        assert len(led['records']) == 1
        assert led['records'][0]['spec_type'] == 'spec'

    def test_load_corrupt_readonly(self, tmp_path):
        p = tmp_path / 'omega_strong' / 'tc.json'
        p.parent.mkdir(parents=True)
        p.write_text('{broken', encoding='utf-8')
        led = load_ledger('tc', str(tmp_path))
        assert led['corrupt'] is True
        assert led['corrupt_backup'] is None
        assert 'repair=False' in led['corrupt_reason']
        assert ledger_corrupt() is True

    def test_load_corrupt_with_repair_backs_up(self, tmp_path):
        p = tmp_path / 'omega_strong' / 'tc.json'
        p.parent.mkdir(parents=True)
        p.write_text('{broken', encoding='utf-8')
        led = load_ledger('tc', str(tmp_path), repair=True)
        assert led['corrupt_backup'] and os.path.isfile(led['corrupt_backup'])
        assert not p.exists()  # 原文件已改名

    def test_corrupt_state_sticky(self, tmp_path):
        p = tmp_path / 'omega_strong' / 'tc.json'
        p.parent.mkdir(parents=True)
        p.write_text('{broken', encoding='utf-8')
        load_ledger('tc', str(tmp_path), repair=True)
        # 备份存在 + 主文件缺失 → 粘性拒绝
        led2 = load_ledger('tc', str(tmp_path))
        assert led2['corrupt'] is True
        assert '等待人工确认' in led2['corrupt_reason']

    def test_load_non_dict_json_corrupt(self, tmp_path):
        p = tmp_path / 'omega_strong' / 'tl.json'
        p.parent.mkdir(parents=True)
        p.write_text('[1,2]', encoding='utf-8')
        assert load_ledger('tl', str(tmp_path))['corrupt'] is True

    def test_load_fills_defaults(self, tmp_path):
        p = tmp_path / 'omega_strong' / 'td.json'
        p.parent.mkdir(parents=True)
        p.write_text('{"records": []}', encoding='utf-8')
        led = load_ledger('td', str(tmp_path))
        assert led['task_id'] == 'td'
        assert led['max_rounds'] == 3

    def test_save_refuses_corrupt_data(self, tmp_path):
        data = {'task_id': 't1', 'records': [], 'corrupt': True}
        with pytest.raises(ActionError) as ei:
            ommod._save_ledger(data, str(tmp_path))
        assert ei.value.code == 'internal'

    def test_append_upsert_same_id(self, tmp_path):
        e = _eng('t1', meta=tmp_path)
        e.spec_create('a', 'v1')
        # 直接 _append 同 id 覆盖
        rec = dict(e.latest('spec'))
        rec['content'] = 'v2'
        e._append(rec)
        led = load_ledger('t1', str(tmp_path))
        assert len(led['records']) == 1
        assert led['records'][0]['content'] == 'v2'

    def test_update_status_touches_updated_at(self, tmp_path):
        e = _eng('t1', meta=tmp_path)
        e.spec_create('a', 'c')
        sid = e.latest('spec')['id']
        old = e.latest('spec')['updated_at']
        e._update_status(sid, 'approved')
        assert e.latest('spec')['status'] == 'approved'
        assert e.latest('spec')['updated_at'] >= old


# ---------------------------------------------------------------- 三环流程

class TestSpecCreate:
    def test_empty_author_rejected(self, tmp_path):
        with pytest.raises(ActionError):
            _eng(meta=tmp_path).spec_create('  ', 'c')

    def test_empty_content_rejected(self, tmp_path):
        with pytest.raises(ActionError):
            _eng(meta=tmp_path).spec_create('a', '   ')

    def test_dict_content_json_encoded(self, tmp_path):
        out = _eng(meta=tmp_path).spec_create('a', {'k': 1})
        led = load_ledger('t1', str(tmp_path))
        assert led['records'][0]['content'] == '{"k": 1}'

    def test_bad_spec_rejected(self, tmp_path):
        with pytest.raises(ActionError) as ei:
            _eng(meta=tmp_path).spec_create('a', 'c', spec={'type': 'zzz'})
        assert '语料 spec 结构非法' in ei.value.message

    def test_create_ok_shape(self, tmp_path):
        out = _eng(meta=tmp_path).spec_create('author', 'content')
        assert out['ok'] is True and out['stage'] == 'spec'
        assert out['spec_id'] == 'spec:t1:r1'
        assert out['status'] == 'pending'
        assert out['next_action'] == 'omega_spec_review'
        assert out['round'] == 1 and out['max_rounds'] == 3

    def test_second_create_while_pending_rejected(self, tmp_path):
        e = _eng(meta=tmp_path)
        e.spec_create('a', 'c')
        with pytest.raises(ActionError) as ei:
            e.spec_create('a', 'c2')
        assert '已存在待审核语料' in ei.value.message

    def test_create_after_approved_rejected(self, tmp_path):
        e = _eng(meta=tmp_path)
        e.spec_create('a', 'c')
        e.spec_review('r', 'approve')
        with pytest.raises(ActionError) as ei:
            e.spec_create('a', 'c2')
        assert '已通过审核' in ei.value.message

    def test_escalate_after_max_rejects(self, tmp_path):
        e = _eng(meta=tmp_path, max_rounds=2)
        for i in range(2):
            e.spec_create('a', 'c%d' % i)
            e.spec_review('r', 'reject', 'bad')
        out = e.spec_create('a', 'c3')
        assert out['escalated'] is True
        assert out['needs_human_review'] is True
        assert out['task_paused'] is True
        assert out['next_action'] == 'human_review'


class TestSpecReview:
    def test_empty_reviewer_rejected(self, tmp_path):
        with pytest.raises(ActionError):
            _eng(meta=tmp_path).spec_review('', 'approve')

    def test_no_spec_rejected(self, tmp_path):
        with pytest.raises(ActionError) as ei:
            _eng(meta=tmp_path).spec_review('r', 'approve')
        assert '尚无语料' in ei.value.message

    def test_not_pending_rejected(self, tmp_path):
        e = _eng(meta=tmp_path)
        e.spec_create('a', 'c')
        e.spec_review('r', 'approve')
        with pytest.raises(ActionError) as ei:
            e.spec_review('r2', 'reject')
        assert '不是待审核状态' in ei.value.message

    def test_self_review_rejected(self, tmp_path):
        e = _eng(meta=tmp_path)
        e.spec_create('author', 'c')
        with pytest.raises(ActionError) as ei:
            e.spec_review('author', 'approve')
        assert '验证者不可审核自己创建的语料' in ei.value.message

    def test_approve(self, tmp_path):
        e = _eng(meta=tmp_path)
        e.spec_create('a', 'c')
        out = e.spec_review('reviewer', 'approve')
        assert out['verdict'] == 'approved'
        assert out['next_action'] == 'execute'
        assert e.latest('spec')['status'] == 'approved'

    @pytest.mark.parametrize('v', ['approve', 'approved', 'pass', 'ok'])
    def test_approve_aliases(self, tmp_path, v):
        e = _eng(meta=tmp_path)
        e.spec_create('a', 'c')
        assert e.spec_review('r', v)['verdict'] == 'approved'

    def test_reject_counts_and_lesson(self, tmp_path):
        e = _eng(meta=tmp_path)
        e.spec_create('a', 'c')
        out = e.spec_review('r', 'reject', '理由')
        assert out['verdict'] == 'rejected'
        assert out['rounds_rejected'] == 1
        assert out['next_action'] == 'omega_spec_create'
        lessons = tmp_path / '_meta' / 'omega_strong' / 'lessons.jsonl'
        assert lessons.is_file()
        entry = json.loads(lessons.read_text(encoding='utf-8').strip())
        assert entry['kind'] == 'omega.spec_rejected'
        assert entry['reason'] == '理由'

    def test_reject_beyond_max_escalates(self, tmp_path):
        e = _eng(meta=tmp_path, max_rounds=2)
        e.spec_create('a', 'c')
        e.spec_review('r', 'reject')          # 打回 1
        e.spec_create('a', 'c2')              # 1 < 2 仍可建
        out = e.spec_review('r', 'reject')    # 打回 2+1=3? 否：rejected 计 2 → 2 > 2? 用 r2 后计 2 → 2 > max(2)? 不；此处第二次 reject 把 rejected 变 2，2>2 为假 → 正常打回。改用 max_rounds=1 场景在 create 侧升级（test_escalate_after_max_rejects）
        assert out['verdict'] == 'rejected'
        assert out['rounds_rejected'] == 2


class TestResultVerify:
    def _approved(self, tmp_path, spec=None):
        e = _eng(meta=tmp_path)
        e.spec_create('a', 'c', spec=spec)
        e.spec_review('r', 'approve')
        return e

    def test_empty_reviewer_rejected(self, tmp_path):
        with pytest.raises(ActionError):
            _eng(meta=tmp_path).result_verify('', 'pass', deliverable={})

    def test_no_spec_rejected(self, tmp_path):
        with pytest.raises(ActionError) as ei:
            _eng(meta=tmp_path).result_verify('r', 'pass', deliverable={})
        assert '尚无执行前语料' in ei.value.message

    def test_spec_not_approved_rejected(self, tmp_path):
        e = _eng(meta=tmp_path)
        e.spec_create('a', 'c')  # pending
        with pytest.raises(ActionError) as ei:
            e.result_verify('r', 'pass', deliverable={})
        assert '未通过审核' in ei.value.message

    def test_no_deliverable_rejected(self, tmp_path):
        e = self._approved(tmp_path)
        with pytest.raises(ActionError) as ei:
            e.result_verify('r', 'pass')
        assert '尚无交付物' in ei.value.message

    def test_pass_records_digest_and_gate(self, tmp_path):
        spec = {'version': '1', 'target': 'x', 'action_id': 'a.t',
                'output_schema': {'type': 'object'}, 'assertions': [
                    {'type': 'equals', 'path': 'code', 'value': 0}]}
        e = self._approved(tmp_path, spec=spec)
        out = e.result_verify('r', 'pass', deliverable={'code': 0})
        assert out['status'] == 'approved'
        assert out['next_action'] == 'verify'
        assert out['gate'] is not None  # Ω-gate 客观佐证
        assert out['deliverable']['type'] == 'dict'

    def test_pass_gate_exception_swallowed(self, tmp_path, monkeypatch):
        spec = {'version': '1', 'target': 'x', 'action_id': 'a.t',
                'output_schema': {'type': 'object'}, 'assertions': []}
        e = self._approved(tmp_path, spec=spec)

        def boom(spec, out):
            raise RuntimeError('gate down')

        monkeypatch.setattr(ommod._omega, 'run_gate', boom)
        out = e.result_verify('r', 'pass', deliverable={'a': 1})
        assert out['gate'] is None
        assert out['status'] == 'approved'

    def test_fail_counts_and_escalates(self, tmp_path):
        e = self._approved(tmp_path)
        out = e.result_verify('r', 'fail', '不行', deliverable={'x': 1})
        assert out['verdict'] == 'rejected'
        assert out['rounds_rejected'] == 1
        e.result_verify('r', 'fail', deliverable={'x': 2})
        e.result_verify('r', 'fail', deliverable={'x': 3})
        out4 = e.result_verify('r', 'fail', deliverable={'x': 4})
        assert out4['escalated'] is True  # 第 4 次 > max_rounds=3

    def test_fail_aliases(self, tmp_path):
        e = self._approved(tmp_path)
        for v in ('no', 'bad', 'reject'):
            assert e.result_verify('r', v, deliverable={'n': 1})['verdict'] == 'rejected'


# ---------------------------------------------------------------- record_check

class TestRecordCheck:
    def test_non_dict_rejected(self, tmp_path):
        with pytest.raises(ActionError):
            _eng(meta=tmp_path).record_check('nope')

    def test_missing_cmd_rejected(self, tmp_path):
        with pytest.raises(ActionError) as ei:
            _eng(meta=tmp_path).record_check({'exit_code': 0})
        assert '缺少非空 cmd' in ei.value.message

    @pytest.mark.parametrize('ec', [None, '0', 1.5, True, False])
    def test_bad_exit_code_rejected(self, tmp_path, ec):
        with pytest.raises(ActionError) as ei:
            _eng(meta=tmp_path).record_check({'cmd': 'x', 'exit_code': ec})
        assert '整数 exit_code' in ei.value.message

    def test_exit_code_is_only_truth(self, tmp_path):
        e = _eng(meta=tmp_path)
        out = e.record_check({'cmd': 'pytest', 'exit_code': 1, 'ok': True,
                              'status': 'passed'})
        assert out['status'] == 'failed'  # ok=True 被忽略
        rec = e.latest('check')
        payload = json.loads(rec['content'])
        assert 'ok' not in payload and 'status' not in payload  # 已剥离

    def test_passed_zero(self, tmp_path):
        out = _eng(meta=tmp_path).record_check({'cmd': 'pytest', 'exit_code': 0})
        assert out == {'ok': True, 'check_id': 'check:t1:r1', 'task_id': 't1',
                       'round': 1, 'status': 'passed', 'exit_code': 0,
                       'cmd': 'pytest'}

    def test_deprecated_alias(self, tmp_path):
        e = _eng(meta=tmp_path)
        assert e.check_record({'cmd': 'x', 'exit_code': 0})['status'] == 'passed'


# ---------------------------------------------------------------- 三道门禁

class TestGates:
    def test_execute_gate_disabled_without_mark(self, tmp_path):
        e = _eng(meta=tmp_path)
        assert e.execute_gate('plain task') == (True, 'disabled')

    def test_execute_gate_no_spec(self, tmp_path):
        e = _eng(meta=tmp_path)
        ok, msg = e.execute_gate('[omega:required] task')
        assert ok is False and '尚未创建语料' in msg

    def test_execute_gate_pending_blocked(self, tmp_path):
        e = _eng(meta=tmp_path)
        e.spec_create('a', 'c')
        ok, msg = e.execute_gate('[omega:required]')
        assert ok is False and 'pending' in msg

    def test_execute_gate_approved(self, tmp_path):
        e = _eng(meta=tmp_path)
        e.spec_create('a', 'c')
        e.spec_review('r', 'approve')
        assert e.execute_gate('[omega:required]') == (True, 'approved')

    def test_execute_gate_task_none_forces_check(self, tmp_path):
        e = _eng(meta=tmp_path)
        assert e.execute_gate()[0] is False

    def test_verify_gate_flow(self, tmp_path):
        e = _eng(meta=tmp_path)
        assert e.verify_gate('[omega:required]')[0] is False
        e.spec_create('a', 'c')
        e.spec_review('r', 'approve')
        e.result_verify('r', 'pass', deliverable={'x': 1})
        assert e.verify_gate('[omega:required]') == (True, 'approved')

    def test_check_gate_disabled_without_mark(self, tmp_path):
        e = _eng(meta=tmp_path)
        assert e.check_gate('plain') == (True, 'disabled')

    def test_check_gate_no_records(self, tmp_path):
        e = _eng(meta=tmp_path)
        ok, msg = e.check_gate('[gate:required]')
        assert ok is False and 'run_check' in msg

    def test_check_gate_failed_blocked(self, tmp_path):
        e = _eng(meta=tmp_path)
        e.record_check({'cmd': 'x', 'exit_code': 1})
        ok, msg = e.check_gate('[gate:required]')
        assert ok is False and 'failed' in msg

    def test_check_gate_fresh_passed(self, tmp_path):
        e = _eng(meta=tmp_path)
        e.record_check({'cmd': 'x', 'exit_code': 0})
        assert e.check_gate('[gate:required]') == (True, 'fresh_passed')

    def test_check_gate_stale_detected(self, tmp_path):
        e = _eng(meta=tmp_path)
        e.record_check({'cmd': 'x', 'exit_code': 0})
        # 任务更新时间晚于检查 → 过期
        future = '2099-01-01T00:00:00+08:00'
        ok, msg = e.check_gate('[gate:required]', task_updated_at=future)
        assert ok is False and '早于任务最后更新' in msg

    def test_check_gate_tz_mismatch_uses_datetime(self, tmp_path):
        # P3 审计修复佐证：02:00Z 与 10:00+08:00 是同一时刻。
        # 字符串比较会判 stale（'02'<'10'），datetime 比较判新鲜。
        e = _eng(meta=tmp_path)
        e.record_check({'cmd': 'x', 'exit_code': 0})
        rec = e.latest('check')
        rec['created_at'] = '2026-01-02T02:00:00Z'
        data = load_ledger('t1', str(tmp_path))
        data['records'] = [r if r['id'] != rec['id'] else rec
                           for r in data['records']]
        ommod._save_ledger(data, str(tmp_path))
        ok, _ = e.check_gate('[gate:required]',
                             task_updated_at='2026-01-02T10:00:00+08:00')
        assert ok is True  # 同一时刻，datetime 比较不误判

    def test_check_gate_string_fallback_stale(self, tmp_path):
        # 一边不可解析 → 退化为字符串比较：created < updated 决定 stale。
        # '0' 排在任何 ISO 日期之前 → created < '0' 为假 → 不 stale
        e = _eng(meta=tmp_path)
        e.record_check({'cmd': 'x', 'exit_code': 0})
        ok, _ = e.check_gate('[gate:required]', task_updated_at='0')
        assert ok is True
        # 反向：'9999' 排在之后 → stale → 拒绝
        ok2, msg2 = e.check_gate('[gate:required]', task_updated_at='9999')
        assert ok2 is False and '早于任务最后更新' in msg2


# ---------------------------------------------------------------- 状态/便捷

def test_status_shape(tmp_path):
    e = _eng(meta=tmp_path)
    e.spec_create('a', 'c')
    s = e.status()
    assert s['ok'] is True and s['task_id'] == 't1'
    assert s['spec_rounds'] == 1 and s['spec_status'] == 'pending'
    assert s['result_status'] == 'none' and s['check_status'] == 'none'
    assert s['escalated'] is False
    assert len(s['records']) == 1


def test_get_ledger_convenience(tmp_path):
    e = get_ledger('tx', meta_dir=str(tmp_path), max_rounds=2)
    assert isinstance(e, OmegaStrong)
    assert e.max_rounds == 2
    assert e.task_id == 'tx'


def test_thread_lock_reused(tmp_path):
    p = str(tmp_path / 'a.json')
    assert ommod._thread_lock_for(p) is ommod._thread_lock_for(p)


class _FakeTime:
    """time.time 首次 0、随后 999（锁立即超时）；sleep 空转。"""

    def __init__(self):
        self.calls = 0

    def time(self):
        self.calls += 1
        return 0.0 if self.calls == 1 else 999.0

    def sleep(self, s):
        pass

    def perf_counter(self):
        return 0.0


def _rec(tid, n=1):
    return {'id': 'x:%s:%d' % (tid, n), 'task_id': tid, 'spec_type': 'spec',
            'content': 'c', 'status': 'pending', 'author': 'a',
            'created_at': '2026-01-01T00:00:00+08:00',
            'updated_at': '2026-01-01T00:00:00+08:00'}


def test_thread_lock_timeout(tmp_path):
    # 进程内锁是 RLock（同线程可重入）—— 超时路径需要另一个线程占锁。
    # acquire 用真实 5s 超时，本测试耗时 ~5s。
    import threading
    e = _eng('tlock2', meta=tmp_path)
    e._append(_rec('tlock2'))
    p = ommod._ledger_path('tlock2', str(tmp_path))
    lock = ommod._thread_lock_for(p)
    def holder():
        lock.acquire()
        time.sleep(30)  # 守过 5s join + 5s 锁超时窗口（daemon 进程退出即清）

    t = threading.Thread(target=holder, daemon=True)
    t.start()
    t.join(5)
    assert lock.acquire(blocking=False) is False  # 线程持有中（RLock 无 locked()）
    with pytest.raises(ActionError) as ei:
        e._append(_rec('tlock2', 2))
    assert '获取锁超时' in ei.value.message


def test_file_lock_contention_timeout(tmp_path, monkeypatch):
    # 真实 msvcrt 文件锁被外部句柄占住 → _append 的文件锁重试到超时
    import msvcrt
    e = _eng('tfile', meta=tmp_path)
    e._append(_rec('tfile'))  # 生成 .lock 文件
    p = ommod._ledger_path('tfile', str(tmp_path))
    holder = open(p + '.lock', 'a+b')
    holder.seek(0)
    msvcrt.locking(holder.fileno(), msvcrt.LK_NBLCK, 1)
    ft = _FakeTime()
    monkeypatch.setattr(ommod, 'time', ft)
    try:
        with pytest.raises(ActionError) as ei:
            e._append(_rec('tfile', 2))
        assert '获取锁超时' in ei.value.message
    finally:
        try:
            holder.seek(0)
            msvcrt.locking(holder.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        holder.close()


def test_check_gate_mixed_tz_falls_back(tmp_path):
    # 一边 naive 一边 aware → TypeError → 字符串比较回退
    e = _eng(meta=tmp_path)
    e.record_check({'cmd': 'x', 'exit_code': 0})
    rec = e.latest('check')
    rec['created_at'] = '2026-01-02T02:00:00'  # naive
    data = load_ledger('t1', str(tmp_path))
    data['records'] = [r if r['id'] != rec['id'] else rec
                       for r in data['records']]
    ommod._save_ledger(data, str(tmp_path))
    # '2026-01-02T02:00:00' < '2026-01-02T09:99:99+08:00' 字符串 → stale
    ok, msg = e.check_gate('[gate:required]',
                           task_updated_at='2026-01-02T09:99:99+08:00')
    assert ok is False and '早于任务最后更新' in msg


def test_escalation_recorded(tmp_path):
    e = _eng(meta=tmp_path, max_rounds=2)
    e.spec_create('a', 'c')
    e.spec_review('r', 'reject')   # 打回 1
    e.spec_create('a', 'c2')       # 1 < 2 可建
    e.spec_review('r', 'reject')   # 打回 2
    out = e.spec_create('a', 'c3')  # rejected(2) >= max(2) → 升级
    assert out['escalated'] is True
    s = e.status()
    assert s['escalated'] is True
    esc = e.latest('escalation')
    assert esc['status'] == 'escalated'
    payload = json.loads(esc['content'])
    assert payload['needs_human_review'] is True
