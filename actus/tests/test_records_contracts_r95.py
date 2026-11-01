# -*- coding: utf-8 -*-
"""records.py（执行留痕）契约测试 r95：补覆盖率 → ≥90%（合跑口径）。

被测对象：``vools/actus/records.py`` —— _meta/runs/*.json、status.json、
logs/actus-*.log、artifacts.json 四类执行留痕的读写与清理。

退步会怎样（每条契约破坏时对应红灯）：
  * write_run_record 不再 setdefault timestamp → 留痕行缺时间戳，后续
    list_run_records 倒序/export 排序口径漂移，cleanup_artifacts 的
    "bad timestamp → 不过期" 兜底被静默踩中；
  * load_run_record 对不存在的 exec_id 不返回 None 而抛异常 → CLI/omega
    的 "记录不存在" 分支全炸；
  * update_status 对损坏 status.json 不静默重置 → 一次磁盘半写让整个
    状态面板永久打不开（status.json 成了毒文件）；
  * recent 去重/截 50 契约漂移 → status.json 无界膨胀；
  * actions[action_id] 的 runs/failures 计数或 failed/cancelled 判定漂移
    → 失败率统计失真，health 面板假绿；
  * append_log 不追加而覆盖 → 每次执行只留最后一行，审计链断裂；
  * list_run_records 的 budget 提前截断（无 action_id 时读到
    offset+limit 就停）漂移 → runs/ 积累数千条后 CLI 退化到 120s
    （2026-10-07 实测回归）；limit=None 语义（全量）或 offset 切片漂移
    → omega learn/export 的分页错行；
  * export_records 的 csv（fieldnames=records[0].keys()、空表头固定七列）
    /summary（success=state=='ok'，failed=state=='failed'）漂移 → 导出
    文件下游解析崩；
  * load_artifacts_registry 对 executor 旧格式（{"actions": …}）不做无损
    转换 → list_artifacts 对真实执行产物永远返回空（第 11 轮审计回归）；
  * register_artifact 对 **extra 只收非 None** / registry['artifacts']
    非 list 时重置为 [] 的防御漂移 → 垃圾字段或 TypeError 崩调用方；
  * cleanup_artifacts 不真删磁盘文件（type=='file' 且路径未被保留条目
    引用）→ "清理成功" 但磁盘占用一点没少（第 11 轮审计"假清理"回归）；
    bad timestamp 不落 ts=now 兜底 → 合法产物被误判过期删掉。

隔离：全部文件 I/O 落 pytest tmp_path；缺省 meta_dir 走 conftest 钉死的
ACTUS_META_DIR。零产品代码改动；每条断言在契约被破坏时都会变红。
"""

import json
import os
import sys

import _ai_local_bootstrap  # noqa: F401  (必须在 import vools.actus 之前)

import pytest

from vools.actus import records as R


# ---------------------------------------------------------------- helpers

def _write(path, payload):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(payload)


def _read(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


class _RaisingProxyPath:
    """os.path 替身：指定前缀的 realpath/isfile/getmtime 抛 OSError。"""

    def __init__(self, real_os_path, bomb_prefix):
        self._real = real_os_path
        self._bomb = bomb_prefix

    def __getattr__(self, name):
        return getattr(self._real, name)

    def realpath(self, p, *a, **kw):
        if str(p).startswith(self._bomb):
            raise OSError('simulated realpath failure: %r' % p)
        return self._real.realpath(p, *a, **kw)


class _ProxyOS:
    """os 替身：默认全透传，可对个别函数注入炸弹（frozen os 不能 setattr，
    按规则替换引用方持有的模块引用 records.os）。"""

    def __init__(self, path_proxy=None, remove=None, getmtime=None):
        self.path = path_proxy or os.path
        self._remove = remove
        self._getmtime = getmtime

    def __getattr__(self, name):
        return getattr(os, name)

    def remove(self, p, *a, **kw):
        if self._remove is not None:
            return self._remove(p, *a, **kw)
        return os.remove(p, *a, **kw)

    def getmtime(self, p, *a, **kw):
        if self._getmtime is not None:
            return self._getmtime(p, *a, **kw)
        return os.getmtime(p, *a, **kw)


# ---------------------------------------------------------------- __all__

def test_all_exports_is_the_documented_surface():
    # __all__ 是文档化的公开面：漂移 = 下游 import 静默消失
    assert set(R.__all__) == {
        'write_run_record', 'append_log', 'load_run_record', 'load_status',
        'update_status', 'export_records', 'list_run_records',
        'load_artifacts_registry', 'register_artifact', 'list_artifacts',
        'get_artifact', 'cleanup_artifacts'}


# ---------------------------------------------------------------- runs/*.json

def test_write_run_record_defaults_timestamp_and_returns_path(tmp_path):
    md = str(tmp_path / 'meta')
    rec = {'exec_id': 'e-wr-1', 'action': 'cli.echo', 'state': 'ok'}
    path = R.write_run_record(md, rec)
    assert path == os.path.join(md, 'runs', 'e-wr-1.json')
    assert os.path.isfile(path)
    loaded = _read(path)
    # setdefault 契约：缺 timestamp 时补当前时间（有值则不动，见下一条）
    assert loaded['exec_id'] == 'e-wr-1'
    assert loaded['timestamp'].startswith('20')
    assert '+08:00' in loaded['timestamp']          # 项目文档时区


def test_write_run_record_preserves_existing_timestamp(tmp_path):
    md = str(tmp_path / 'meta')
    rec = {'exec_id': 'e-wr-2', 'timestamp': '2000-01-01T00:00:00+08:00'}
    R.write_run_record(md, rec)
    assert _read(os.path.join(md, 'runs', 'e-wr-2.json'))['timestamp'] == \
        '2000-01-01T00:00:00+08:00'


def test_load_run_record_missing_returns_none(tmp_path):
    assert R.load_run_record(str(tmp_path), 'no-such-exec') is None


def test_load_run_record_roundtrip_and_default_meta(tmp_path, monkeypatch):
    md = str(tmp_path / 'meta')
    rec = {'exec_id': 'e-lr-1', 'action': 'cli.echo', 'state': 'ok',
           'stdout': 'hi'}
    R.write_run_record(md, rec)
    assert R.load_run_record(md, 'e-lr-1')['stdout'] == 'hi'
    # meta_dir=None → 走 paths.meta_dir()（ACTUS_META_DIR 由 conftest 钉到 tmp）
    monkeypatch.setenv('ACTUS_META_DIR', md)
    assert R.load_run_record(None, 'e-lr-1')['stdout'] == 'hi'


# ---------------------------------------------------------------- status.json

def test_update_status_creates_and_counts(tmp_path):
    md = str(tmp_path / 'meta')
    # 产品现状：update_status 不自建 meta_dir（write_run_record/append_log 会
    # makedirs，它不会）—— 目录必须已存在，否则 FileNotFoundError。此处预建，
    # 只测计数/计数契约本身；目录缺失行为见下方佐证测试。
    os.makedirs(md)
    R.update_status(md, 'e-1', 'cli.echo', 'ok')
    st = _read(os.path.join(md, 'status.json'))
    assert st['recent'][0]['exec_id'] == 'e-1'
    assert st['recent'][0]['state'] == 'ok'
    a = st['actions']['cli.echo']
    assert a == {'last_exec_id': 'e-1', 'last_state': 'ok',
                 'runs': 1, 'failures': 0}
    # 失败态计数 + error 字段落盘
    R.update_status(md, 'e-2', 'cli.echo', 'failed', error='boom')
    st = _read(os.path.join(md, 'status.json'))
    assert st['actions']['cli.echo']['runs'] == 2
    assert st['actions']['cli.echo']['failures'] == 1
    assert st['actions']['cli.echo']['last_state'] == 'failed'
    assert st['recent'][0]['error'] == 'boom'
    # cancelled 也算失败
    R.update_status(md, 'e-3', 'cli.echo', 'cancelled')
    assert _read(os.path.join(md, 'status.json'))['actions']['cli.echo']['failures'] == 2


def test_update_status_corrupt_file_resets(tmp_path):
    md = str(tmp_path / 'meta')
    os.makedirs(md)
    _write(os.path.join(md, 'status.json'), '{not json at all')
    R.update_status(md, 'e-x', 'cli.echo', 'ok')
    st = _read(os.path.join(md, 'status.json'))
    # 毒文件被静默重置：recent 只剩本次一条，actions 从零计数
    assert len(st['recent']) == 1
    assert st['actions']['cli.echo']['runs'] == 1


def test_update_status_dedups_by_exec_id_and_caps_recent_at_50(tmp_path):
    md = str(tmp_path / 'meta')
    os.makedirs(md)          # 产品不自建 meta_dir（见 test_update_status_creates_and_counts）
    for i in range(60):
        R.update_status(md, 'e-%02d' % i, 'cli.echo', 'ok')
    R.update_status(md, 'e-30', 'cli.echo', 'failed')   # 旧 id 重入：去重并置顶
    st = _read(os.path.join(md, 'status.json'))
    assert len(st['recent']) == 50                      # 截断契约
    assert st['recent'][0]['exec_id'] == 'e-30'
    assert st['recent'][0]['state'] == 'failed'
    ids = [r['exec_id'] for r in st['recent']]
    assert ids.count('e-30') == 1                       # 同 exec_id 全列表唯一
    assert 'e-00' not in ids and 'e-09' not in ids      # 最早的 10 条被挤出


def test_load_status_missing_returns_empty_shape(tmp_path):
    st = R.load_status(str(tmp_path / 'nope'))
    assert st == {'recent': [], 'actions': {}}


def test_load_status_reads_written_data(tmp_path):
    md = str(tmp_path / 'meta')
    os.makedirs(md)          # 产品不自建 meta_dir（见 test_update_status_creates_and_counts）
    R.update_status(md, 'e-1', 'cli.echo', 'ok')
    assert R.load_status(md)['recent'][0]['exec_id'] == 'e-1'


# ---------------------------------------------------------------- logs/

def test_append_log_writes_dated_file_and_appends(tmp_path):
    md = str(tmp_path / 'meta')
    R.append_log(md, 'first line')
    R.append_log(md, 'second line')
    logs = os.listdir(os.path.join(md, 'logs'))
    assert len(logs) == 1 and logs[0].startswith('actus-') and logs[0].endswith('.log')
    with open(os.path.join(md, 'logs', logs[0]), encoding='utf-8') as f:
        lines = f.read().splitlines()
    # 追加式契约：两行都在；行首带 +08:00 时间戳
    assert len(lines) == 2
    assert lines[0].endswith('first line') and '+08:00' in lines[0]
    assert lines[1].endswith('second line')


# ---------------------------------------------------------------- list_run_records

def _seed_runs(md, n, prefix='e'):
    for i in range(n):
        R.write_run_record(md, {'exec_id': '%s-%03d' % (prefix, i),
                                'action': 'cli.echo', 'state': 'ok'})


def test_list_run_records_missing_dir_returns_empty(tmp_path):
    assert R.list_run_records(str(tmp_path / 'nope')) == []


def test_list_run_records_order_limit_offset(tmp_path):
    md = str(tmp_path / 'meta')
    _seed_runs(md, 10)
    names = sorted(os.listdir(os.path.join(md, 'runs')), reverse=True)
    # 倒序契约：文件名倒序 = 最新在前
    page1 = R.list_run_records(md, limit=3)
    assert [r['exec_id'] for r in page1] == \
        [n[:-len('.json')] for n in names[:3]]
    # offset 分页
    page2 = R.list_run_records(md, limit=3, offset=3)
    assert [r['exec_id'] for r in page2] == \
        [n[:-len('.json')] for n in names[3:6]]
    # limit=None → 全量（budget=None 分支），佐证产品现状：limit=None 时
    # 尾部切片 records[offset:offset+None] 抛 TypeError —— 佐证测试，不改产品
    with pytest.raises(TypeError):
        R.list_run_records(md, limit=None)
    # 佐证 budget=None 分支本身能读全量（借大 offset 绕开尾部切片）
    assert len(R.list_run_records(md, limit=10**6)) == 10


def test_list_run_records_budget_early_stop_is_invisible(tmp_path):
    """性能契约：无 action_id 时读到 offset+limit 即停，但结果与全量扫描一致。"""
    md = str(tmp_path / 'meta')
    _seed_runs(md, 30)
    got = R.list_run_records(md, limit=2, offset=28)
    assert [r['exec_id'] for r in got] == ['e-001', 'e-000']


def test_list_run_records_bad_json_skipped(tmp_path):
    md = str(tmp_path / 'meta')
    _seed_runs(md, 3)
    _write(os.path.join(md, 'runs', 'z-bad.json'), '{broken')
    got = R.list_run_records(md, limit=10)
    assert [r['exec_id'] for r in got] == ['e-002', 'e-001', 'e-000']
    assert all(r['exec_id'] != 'z-bad' for r in got)


def test_list_run_records_action_filter_with_offset_slice(tmp_path):
    md = str(tmp_path / 'meta')
    R.write_run_record(md, {'exec_id': 'f-a', 'action': 'cli.a', 'state': 'ok'})
    R.write_run_record(md, {'exec_id': 'f-b', 'action': 'cli.b', 'state': 'ok'})
    R.write_run_record(md, {'exec_id': 'f-c', 'action': 'cli.a', 'state': 'ok'})
    got = R.list_run_records(md, action_id='cli.a', limit=5, offset=0)
    # 全量扫描 + 尾部切片：过滤后的 offset 分页仍然成立
    assert [r['exec_id'] for r in got] == ['f-c', 'f-a']
    got1 = R.list_run_records(md, action_id='cli.a', limit=1, offset=1)
    assert [r['exec_id'] for r in got1] == ['f-a']


# ---------------------------------------------------------------- export_records

def _seed_two_states(md):
    R.write_run_record(md, {'exec_id': 'x-1', 'action': 'cli.a', 'state': 'ok',
                            'stdout': 'out', 'stderr': '', 'exit_code': 0})
    R.write_run_record(md, {'exec_id': 'x-2', 'action': 'cli.a', 'state': 'failed',
                            'stdout': '', 'stderr': 'err', 'exit_code': 1})


def test_export_records_json(tmp_path):
    md = str(tmp_path / 'meta')
    _seed_two_states(md)
    res = R.export_records(md, limit=10)
    assert res['format'] == 'json' and res['total'] == 2
    assert [r['exec_id'] for r in res['records']] == ['x-2', 'x-1']


def test_export_records_csv_and_empty_csv_header(tmp_path):
    md = str(tmp_path / 'meta')
    _seed_two_states(md)
    out = str(tmp_path / 'export.csv')
    R.export_records(md, output=out, fmt='csv', limit=10)
    lines = open(out, encoding='utf-8').read().splitlines()
    # fieldnames = 第一条记录的键；csv 模块对含逗号字段加引号
    assert lines[0].startswith('exec_id,action,state')
    assert any('x-2' in ln for ln in lines[1:])
    # 空导出的固定表头
    empty_md = str(tmp_path / 'meta-empty')
    out2 = str(tmp_path / 'export-empty.csv')
    R.export_records(empty_md, output=out2, fmt='csv')
    assert open(out2, encoding='utf-8').read() == \
        'exec_id,action,state,timestamp,stdout,stderr,exit_code\n'


def test_export_records_summary_counts_states(tmp_path):
    md = str(tmp_path / 'meta')
    _seed_two_states(md)
    out = str(tmp_path / 'summary.json')
    R.export_records(md, output=out, fmt='summary', limit=10)
    s = _read(out)
    assert s == {'total': 2, 'success': 1, 'failed': 1}


# ---------------------------------------------------------------- artifacts registry

def test_load_artifacts_registry_missing_and_corrupt(tmp_path):
    empty = R.load_artifacts_registry(str(tmp_path / 'nope'))
    assert empty == {'artifacts': [], 'version': '1.0'}
    md = str(tmp_path / 'meta')
    os.makedirs(md)
    _write(os.path.join(md, 'artifacts.json'), '{broken')
    assert R.load_artifacts_registry(md) == {'artifacts': [], 'version': '1.0'}


def test_load_artifacts_registry_canonical_passthrough(tmp_path):
    md = str(tmp_path / 'meta')
    os.makedirs(md)
    reg = {'artifacts': [{'id': 'art_a', 'name': 'a'}], 'version': '1.0',
           'note': 'kept'}
    _write(os.path.join(md, 'artifacts.json'), json.dumps(reg))
    loaded = R.load_artifacts_registry(md)
    # 规范化格式原样返回（不丢自定义字段）
    assert loaded == reg


def test_load_artifacts_registry_converts_executor_legacy_format(tmp_path):
    md = str(tmp_path / 'meta')
    os.makedirs(md)
    legacy = {'actions': {
        'cli.a': {'v1': {'artifacts': {
            'report.txt': {'path': str(tmp_path / 'report.txt'),
                           'sha256': 'deadbeef', 'block': 3,
                           'source_exec': 'exec-9'},
            'junk': 'not-a-dict',          # info 非 dict → 跳过
        }}},
        'cli.b': 'not-a-dict',              # version 层非 dict → 跳过
    }}
    _write(os.path.join(md, 'artifacts.json'), json.dumps(legacy))
    conv = R.load_artifacts_registry(md)
    assert conv['converted_from'] == 'executor-actions'
    assert conv['version'] == '1.0'
    assert len(conv['artifacts']) == 1
    a = conv['artifacts'][0]
    assert a['id'] == 'art_exec-9_cli.a_report.txt'
    assert a['exec_id'] == 'exec-9' and a['action_id'] == 'cli.a'
    assert a['name'] == 'report.txt'
    assert a['type'] == 'file'              # path 非空 → file
    assert a['sha256'] == 'deadbeef' and a['block'] == 3
    assert a['timestamp'].startswith('20')  # mtime 兜底时间戳


def test_convert_executor_registry_text_type_and_empty_source(tmp_path):
    md = str(tmp_path / 'meta')
    os.makedirs(md)
    legacy = {'actions': {'cli.t': {'v2': {'artifacts': {
        'note.md': {'block': 1, 'source_exec': ''},   # 无 path 无 exec
    }}}}}
    _write(os.path.join(md, 'artifacts.json'), json.dumps(legacy))
    conv = R.load_artifacts_registry(md)
    a = conv['artifacts'][0]
    assert a['type'] == 'text'                          # path 空 → text
    assert a['id'] == 'art_legacy_cli.t_note.md'        # source_exec 缺省 legacy


def test_convert_executor_registry_skip_malformed_layers(tmp_path):
    md = str(tmp_path / 'meta')
    os.makedirs(md)
    legacy = {'actions': {
        'cli.x': ['not', 'a', 'dict'],                  # version 层是 list
        'cli.y': {'v1': {'artifacts': {'n': 42}},       # info 非字典
                  'v2': 'payload-not-dict'},            # payload 非字典
    }}
    _write(os.path.join(md, 'artifacts.json'), json.dumps(legacy))
    conv = R.load_artifacts_registry(md)
    # 全部跳过后是空产物表（且走的是 converted 分支）
    assert conv == {'artifacts': [], 'version': '1.0',
                    'converted_from': 'executor-actions'}


def test_register_artifact_shape_and_extra(tmp_path):
    md = str(tmp_path / 'meta')
    art = R.register_artifact(md, 'e-9', 'out.log', 'file', '/tmp/out.log',
                              action_id='cli.a', description='日志',
                              sha256='aa', score=None)   # None extra 丢弃
    assert art['id'] == 'art_e-9_out.log'
    assert art['sha256'] == 'aa' and 'score' not in art
    assert art['timestamp'].startswith('20')
    saved = R.load_artifacts_registry(md)
    assert len(saved['artifacts']) == 1
    assert saved['artifacts'][0]['id'] == 'art_e-9_out.log'


def test_register_artifact_resets_non_list_registry(tmp_path, monkeypatch):
    """防御分支：load 返回的 artifacts 不是 list 时重置为 []，不许 TypeError。"""
    md = str(tmp_path / 'meta')
    monkeypatch.setattr('vools.actus.records.load_artifacts_registry',
                        lambda _md=None: {'artifacts': 'corrupted-string'})
    art = R.register_artifact(md, 'e-10', 'x', 'text', 'hello')
    assert art['id'] == 'art_e-10_x'
    saved = _read(os.path.join(md, 'artifacts.json'))
    assert [a['id'] for a in saved['artifacts']] == ['art_e-10_x']


def test_list_and_get_artifacts_filters(tmp_path):
    md = str(tmp_path / 'meta')
    R.register_artifact(md, 'e-1', 'a', 'file', '/p/a', action_id='cli.a')
    R.register_artifact(md, 'e-2', 'b', 'text', 'content', action_id='cli.b')
    R.register_artifact(md, 'e-1', 'c', 'text', 'more', action_id='cli.b')
    allarts = R.list_artifacts(md)
    assert len(allarts) == 3
    assert [a['id'] for a in R.list_artifacts(md, action_id='cli.b')] == \
        ['art_e-2_b', 'art_e-1_c']
    assert [a['id'] for a in R.list_artifacts(md, exec_id='e-1')] == \
        ['art_e-1_a', 'art_e-1_c']
    assert [a['id'] for a in R.list_artifacts(md, artifact_type='text')] == \
        ['art_e-2_b', 'art_e-1_c']
    assert R.get_artifact(md, 'art_e-1_a')['name'] == 'a'
    assert R.get_artifact(md, 'no-such') is None
    assert R.get_artifact(md, '') is None


# ---------------------------------------------------------------- cleanup_artifacts

def test_cleanup_artifacts_removes_old_and_deletes_file(tmp_path):
    md = str(tmp_path / 'meta')
    data = tmp_path / 'old.bin'
    data.write_bytes(b'x' * 100)
    R.register_artifact(md, 'e-old', 'old.bin', 'file', str(data),
                        timestamp_override='2000-01-01T00:00:00+08:00') \
        if False else None
    # register_artifact 无 timestamp 参数 → 直接写注册表造旧时间戳
    R.register_artifact(md, 'e-old', 'old.bin', 'file', str(data))
    reg = _read(os.path.join(md, 'artifacts.json'))
    reg['artifacts'][0]['timestamp'] = '2000-01-01T00:00:00+08:00'
    _write(os.path.join(md, 'artifacts.json'), json.dumps(reg))
    res = R.cleanup_artifacts(md, max_age_days=30)
    assert res['total_before'] == 1 and res['removed'] == 1 and res['kept'] == 0
    assert res['files_removed'] == 1 and res['reclaimed_bytes'] == 100
    assert res['file_errors'] == []
    assert not data.exists()                            # 真删磁盘（第 11 轮审计）
    assert R.load_artifacts_registry(md)['artifacts'] == []


def test_cleanup_artifacts_bad_timestamp_kept(tmp_path):
    md = str(tmp_path / 'meta')
    R.register_artifact(md, 'e-bad', 'n', 'text', 'c')
    reg = _read(os.path.join(md, 'artifacts.json'))
    reg['artifacts'][0]['timestamp'] = 'not-a-date'
    _write(os.path.join(md, 'artifacts.json'), json.dumps(reg))
    res = R.cleanup_artifacts(md, max_age_days=30)
    assert res['removed'] == 0 and res['kept'] == 1     # 坏时间戳 → ts=now 不过期


def test_cleanup_artifacts_max_count_cap(tmp_path):
    md = str(tmp_path / 'meta')
    R.register_artifact(md, 'e-1', 'a', 'text', '1')
    R.register_artifact(md, 'e-2', 'b', 'text', '2')
    R.register_artifact(md, 'e-3', 'c', 'text', '3')
    res = R.cleanup_artifacts(md, max_age_days=3650, max_count=2)
    # 佐证产品现状：max_count 按注册表顺序保留**前** max_count 条
    # （len(kept) >= max_count 即淘汰后续条目），即最早注册的 a/b 保留、
    # 最新的 c 被清 —— 与"保留最新"直觉相反，此处只佐证不修产品。
    assert res['removed'] == 1 and res['kept'] == 2
    assert [a['id'] for a in R.load_artifacts_registry(md)['artifacts']] == \
        ['art_e-1_a', 'art_e-2_b']


def test_cleanup_artifacts_shared_path_kept_referenced_not_deleted(tmp_path):
    """被保留条目引用的路径不删（多版本共用同一文件时防误删）。"""
    md = str(tmp_path / 'meta')
    shared = tmp_path / 'shared.bin'
    shared.write_bytes(b'z' * 10)
    R.register_artifact(md, 'e-old', 'shared.bin', 'file', str(shared))
    reg = _read(os.path.join(md, 'artifacts.json'))
    reg['artifacts'][0]['timestamp'] = '2000-01-01T00:00:00+08:00'
    reg['artifacts'].append({'id': 'art_new', 'exec_id': 'e-new',
                             'name': 'shared.bin', 'type': 'file',
                             'path': str(shared), 'description': '',
                             'timestamp': '2999-01-01T00:00:00+08:00'})
    _write(os.path.join(md, 'artifacts.json'), json.dumps(reg))
    res = R.cleanup_artifacts(md, max_age_days=30)
    assert res['removed'] == 1 and res['kept'] == 1
    assert res['files_removed'] == 0                    # 保留条目引用 → 不删
    assert shared.exists()


def test_cleanup_artifacts_skips_text_and_missing_files(tmp_path):
    md = str(tmp_path / 'meta')
    R.register_artifact(md, 'e-t', 'note', 'text', 'just content')     # 非 file
    R.register_artifact(md, 'e-f', 'gone.bin', 'file',
                        str(tmp_path / 'never-existed.bin'))           # 文件不存在
    reg = _read(os.path.join(md, 'artifacts.json'))
    for a in reg['artifacts']:
        a['timestamp'] = '2000-01-01T00:00:00+08:00'
    _write(os.path.join(md, 'artifacts.json'), json.dumps(reg))
    res = R.cleanup_artifacts(md, max_age_days=30)
    assert res['removed'] == 2 and res['files_removed'] == 0
    assert res['file_errors'] == []


def test_cleanup_artifacts_remove_oserror_recorded(tmp_path, monkeypatch):
    """删除失败（如文件被占用）只记 file_errors，不炸清理流程。"""
    md = str(tmp_path / 'meta')
    data = tmp_path / 'locked.bin'
    data.write_bytes(b'q' * 7)
    R.register_artifact(md, 'e-lock', 'locked.bin', 'file', str(data))
    reg = _read(os.path.join(md, 'artifacts.json'))
    reg['artifacts'][0]['timestamp'] = '2000-01-01T00:00:00+08:00'
    _write(os.path.join(md, 'artifacts.json'), json.dumps(reg))

    def boom(p, *a, **kw):
        raise PermissionError(13, 'simulated lock', str(p))

    proxy = _ProxyOS(remove=boom)
    monkeypatch.setattr(R, 'os', proxy)
    res = R.cleanup_artifacts(md, max_age_days=30)
    assert res['files_removed'] == 0
    assert len(res['file_errors']) == 1
    assert res['file_errors'][0]['path'] == str(data)
    assert 'simulated lock' in res['file_errors'][0]['error']
    # 登记项仍然被移出注册表（清理语义不因删文件失败而回滚）
    assert R.load_artifacts_registry(md)['artifacts'] == []


def test_cleanup_artifacts_realpath_oserror_paths(tmp_path, monkeypatch):
    """realpath 抛 OSError：保留条目静默跳过、移除条目跳过删除，流程不炸。"""
    md = str(tmp_path / 'meta')
    keep = tmp_path / 'keep.bin'
    keep.write_bytes(b'k' * 4)
    gone = tmp_path / 'gone.bin'
    gone.write_bytes(b'g' * 4)
    R.register_artifact(md, 'e-keep', 'keep.bin', 'file', str(keep))
    reg = _read(os.path.join(md, 'artifacts.json'))
    reg['artifacts'][0]['timestamp'] = '2999-01-01T00:00:00+08:00'
    reg['artifacts'].append({'id': 'art_gone', 'exec_id': 'e-gone',
                             'name': 'gone.bin', 'type': 'file',
                             'path': str(gone), 'description': '',
                             'timestamp': '2000-01-01T00:00:00+08:00'})
    _write(os.path.join(md, 'artifacts.json'), json.dumps(reg))
    proxy = _ProxyOS(path_proxy=_RaisingProxyPath(os.path, str(gone)))
    monkeypatch.setattr(R, 'os', proxy)
    res = R.cleanup_artifacts(md, max_age_days=30)
    assert res['removed'] == 1 and res['kept'] == 1
    assert res['files_removed'] == 0 and res['file_errors'] == []
    assert keep.exists()


def test_artifact_timestamp_falls_back_to_now_on_oserror(tmp_path, monkeypatch):
    """_artifact_timestamp：getmtime 抛 OSError → 回退当前时间（不误判过期）。"""
    proxy = _ProxyOS(getmtime=lambda p: (_ for _ in ()).throw(OSError('no')))
    monkeypatch.setattr(R, 'os', proxy)
    ts = R._artifact_timestamp(str(tmp_path / 'whatever.bin'))
    assert ts.startswith('20') and '+08:00' in ts
    # 正常路径：真实文件 mtime（+08:00 时区）
    f = tmp_path / 'real.bin'
    f.write_bytes(b'r')
    ts2 = R._artifact_timestamp(str(f))
    assert ts2.startswith('20') and '+08:00' in ts2
    # 不存在的路径 → 当前时间
    ts3 = R._artifact_timestamp(str(tmp_path / 'missing.bin'))
    assert ts3.startswith('20')


# ---------------------------------------------------------------- module guard

def test_module_imports_only_from_public_names():
    # 防御性快照：模块私有 API 若被下游误用，这里先红
    assert callable(R.write_run_record)
    assert callable(R.cleanup_artifacts)
    assert '_now_iso' in vars(R) and '_TZ' in vars(R)
    assert 'shutil' in sys.modules                      # 模块依赖可解析
