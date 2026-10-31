# -*- coding: utf-8 -*-
"""bugreport.py 契约测试（第 85 轮）——运行时 bug 账本（bugs.md）。

覆盖：bugs_path/_read_text/去重键/来源核实（ensure_within/相对化）/
ref_call_id 核实（no_call_log/不存在/成功/失败/sqlite 错误）/
_bump_hit（有/无命中行/无 --- 分隔）/report_bug 全路径/
bug_list（中文键+YAML 别名+过滤）。
"""
import _ai_local_bootstrap  # noqa: F401

import os
import sqlite3

import pytest

import vools.actus.bugreport as bm
from vools.actus.bugreport import (SEVERITIES, BugreportError, bug_list,
                                   bugs_path, report_bug)


@pytest.fixture
def world(tmp_path, monkeypatch):
    home = tmp_path / 'home'
    home.mkdir()
    (tmp_path / '_meta').mkdir()
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setenv('USERPROFILE', str(home))
    monkeypatch.setenv('ACTUS_META_DIR', str(tmp_path / '_meta'))
    monkeypatch.setenv('ACTUS_REPO_ROOT', str(tmp_path))
    return tmp_path


def _source_file(world, name='notes.md'):
    p = world / 'docs' / name
    p.parent.mkdir(exist_ok=True)
    p.write_text('evidence')
    return p


def _call_log(world, seq=42, ok=0):
    db = world / '_meta' / 'call_log.db'
    conn = sqlite3.connect(str(db))
    conn.execute('CREATE TABLE IF NOT EXISTS call_log '
                 '(seq INTEGER PRIMARY KEY, tool TEXT, ok INTEGER)')
    conn.execute('INSERT OR REPLACE INTO call_log VALUES (?, ?, ?)',
                 (seq, 'run_check', ok))
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════════════
# 基础设施
# ═══════════════════════════════════════════════════════════════════

class TestInfra:
    def test_severities_closed(self):
        assert SEVERITIES == ('critical', 'high', 'medium', 'low')

    def test_bugs_path_explicit(self, tmp_path):
        assert bugs_path(str(tmp_path)) == \
            os.path.join(str(tmp_path), 'memory', 'bugs.md')

    def test_bugs_path_default_root(self, world):
        assert bugs_path() == os.path.join(str(world), 'memory', 'bugs.md')

    def test_read_text_missing_empty(self, tmp_path):
        assert bm._read_text(str(tmp_path / 'nope.md')) == ''

    def test_read_text_normalizes_crlf(self, tmp_path):
        p = tmp_path / 'bugs.md'
        p.write_bytes(b'# Bug \r\nx\r\n')
        assert bm._read_text(str(p)) == '# Bug \nx\n'


# ═══════════════════════════════════════════════════════════════════
# 来源与关联调用核实
# ═══════════════════════════════════════════════════════════════════

class TestEvidence:
    def test_source_relative_normalized(self, world):
        p = _source_file(world)
        r = report_bug('s', source='docs/notes.md', project_dir=str(world))
        assert r['id'] == 'BUG-0001'
        text = bm._read_text(bugs_path(str(world)))
        assert '来源：docs/notes.md' in text

    def test_source_absolute_inside(self, world):
        p = _source_file(world)
        r = report_bug('s', source=str(p), project_dir=str(world))
        text = bm._read_text(bugs_path(str(world)))
        assert '来源：docs/notes.md' in text

    def test_source_outside_repo_rejected(self, world, tmp_path_factory):
        out = tmp_path_factory.mktemp('outside')
        bad = out / 'SECRET.txt'
        bad.write_text('x')
        with pytest.raises(BugreportError):
            report_bug('s', source=str(bad), project_dir=str(world))

    def test_source_escape_rejected(self, world):
        with pytest.raises(BugreportError):
            report_bug('s', source='../../etc/passwd', project_dir=str(world))

    def test_source_missing_file_rejected(self, world):
        with pytest.raises(BugreportError) as ei:
            report_bug('s', source='docs/ghost.md', project_dir=str(world))
        assert '不是仓库内真实存在的文件' in str(ei.value)

    def test_no_evidence_rejected(self, world):
        with pytest.raises(BugreportError) as ei:
            report_bug('s', project_dir=str(world))
        assert '缺少可核实出处' in str(ei.value)

    def test_ref_no_call_log(self, world):
        r = report_bug('s', ref_call_id=42, project_dir=str(world))
        assert r['ref_status'] == 'no_call_log'

    def test_ref_points_to_failure(self, world):
        _call_log(world, 42, ok=0)
        r = report_bug('s', ref_call_id=42, project_dir=str(world))
        assert r['ref_status'] == 'verified_failure'

    def test_ref_points_to_success(self, world):
        _call_log(world, 42, ok=1)
        r = report_bug('s', ref_call_id=42, project_dir=str(world))
        assert r['ref_status'] == 'points_to_success'

    def test_ref_seq_missing_rejected(self, world):
        _call_log(world, 7, ok=0)
        with pytest.raises(BugreportError) as ei:
            report_bug('s', ref_call_id=42, project_dir=str(world))
        assert '不得凭编造的 seq' in str(ei.value)

    def test_ref_broken_db_rejected(self, world):
        db = world / '_meta' / 'call_log.db'
        db.write_bytes(b'not a sqlite file')
        with pytest.raises(BugreportError):
            report_bug('s', ref_call_id=42, project_dir=str(world))

    def test_ref_default_root_uses_meta_dir(self, world):
        _call_log(world, 42, ok=0)
        r = report_bug('s', ref_call_id=42)   # 默认根 → ACTUS_META_DIR
        assert r['ref_status'] == 'verified_failure'


# ═══════════════════════════════════════════════════════════════════
# report_bug
# ═══════════════════════════════════════════════════════════════════

class TestReportBug:
    def test_empty_summary_rejected(self, world):
        with pytest.raises(BugreportError):
            report_bug('  ', project_dir=str(world))

    def test_bad_severity_rejected(self, world):
        with pytest.raises(BugreportError) as ei:
            report_bug('s', severity='meh', source='x')
        assert '非法' in str(ei.value)

    def test_none_severity_defaults_medium(self, world):
        _source_file(world)
        r = report_bug('s', severity=None, source='docs/notes.md',
                       project_dir=str(world))
        assert r['severity'] == 'medium'

    def test_first_entry_shape(self, world):
        _source_file(world)
        r = report_bug('s1', detail='d1', severity='high',
                       reported_by='tester', source='docs/notes.md',
                       project_dir=str(world))
        assert r == {**r, 'id': 'BUG-0001', 'seq': 1, 'hits': 1,
                     'duplicate': False, 'status': 'OPEN'}
        text = bm._read_text(bugs_path(str(world)))
        assert text.startswith('# Bug 账本')
        assert '## BUG-0001 [' in text and '。[high] OPEN' in text.replace(
            ' [high] OPEN', '。[high] OPEN') or ' [high] OPEN' in text
        assert '详情：d1' in text and '上报人：tester' in text
        assert '命中：1' in text and text.rstrip().endswith('---')

    def test_seq_increments(self, world):
        _source_file(world)
        report_bug('a', source='docs/notes.md', project_dir=str(world))
        r2 = report_bug('b', source='docs/notes.md', project_dir=str(world))
        assert r2['seq'] == 2

    def test_duplicate_bumps_hits(self, world):
        _source_file(world)
        r1 = report_bug('same', detail='d', source='docs/notes.md',
                        project_dir=str(world))
        r2 = report_bug('same', detail='d', source='docs/notes.md',
                        project_dir=str(world))
        assert r2['duplicate'] is True and r2['id'] == r1['id']
        assert r2['hits'] == 2
        text = bm._read_text(bugs_path(str(world)))
        assert text.count('## BUG-') == 1 and '命中：2' in text

    def test_duplicate_triple_hit(self, world):
        _source_file(world)
        for _ in range(3):
            report_bug('same', source='docs/notes.md', project_dir=str(world))
        assert bm._read_text(bugs_path(str(world))).count('命中：3') == 1

    def test_append_to_ledger_without_trailing_newline(self, world):
        p = bugs_path(str(world))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w', encoding='utf-8') as fh:
            fh.write('# Bug 账本\n旧内容无换行结尾')
        _source_file(world)
        r = report_bug('新条目', source='docs/notes.md', project_dir=str(world))
        assert r['id'] == 'BUG-0001'   # 239 分支：补换行后再追加
        text = bm._read_text(p)
        assert '旧内容无换行结尾' in text and '## BUG-0001' in text

    def test_lf_only_writes(self, world):
        _source_file(world)
        report_bug('lf', source='docs/notes.md', project_dir=str(world))
        p = bugs_path(str(world))
        assert b'\r\n' not in open(p, 'rb').read()


# ═══════════════════════════════════════════════════════════════════
# _bump_hit 边界
# ═══════════════════════════════════════════════════════════════════

class TestBumpHit:
    def test_missing_entry_returns_hits_1(self):
        text, hits = bm._bump_hit('x\ny\n', 'BUG-0009')
        assert hits == 1 and text == 'x\ny\n'

    def test_no_hit_field_no_separator(self):
        block = '## BUG-0001 [t] [low] OPEN\n摘要：s\n'
        text, hits = bm._bump_hit(block, 'BUG-0001')
        assert hits == 2 and '命中：2' in text

    def test_no_hit_field_with_separator(self):
        block = '## BUG-0001 [t] [low] OPEN\n摘要：s\n---\n## BUG-0002 [t] [low] OPEN\n'
        text, hits = bm._bump_hit(block, 'BUG-0001')
        assert hits == 2
        assert '命中：2' in text and '## BUG-0002' in text

    def test_existing_hit_field_incremented(self):
        block = '## BUG-0001 [t] [low] OPEN\n摘要：s\n命中：5\n---\n'
        text, hits = bm._bump_hit(block, 'BUG-0001')
        assert hits == 6 and '命中：6' in text and '命中：5' not in text


# ═══════════════════════════════════════════════════════════════════
# bug_list
# ═══════════════════════════════════════════════════════════════════

class TestBugList:
    def test_empty_ledger(self, world):
        assert bug_list(project_dir=str(world)) == []

    def test_roundtrip_fields(self, world):
        _source_file(world)
        report_bug('s1', detail='d1', severity='high', reported_by='me',
                   source='docs/notes.md', project_dir=str(world))
        entries = bug_list(project_dir=str(world))
        assert len(entries) == 1
        e = entries[0]
        assert e['id'] == 'BUG-0001' and e['seq'] == 1
        assert e['summary'] == 's1' and e['detail'] == 'd1'
        assert e['severity'] == 'high' and e['reported_by'] == 'me'
        assert e['hits'] == 1 and e['来源'] == 'docs/notes.md'

    def test_yaml_alias_fields(self, world):
        p = bugs_path(str(world))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w', encoding='utf-8') as fh:
            fh.write(
            '# Bug 账本\n'
            '## BUG-0002 [t] [low] OPEN\n'
            '- summary: yaml 风格\n'
            '- detail: 别名行\n'
            '- ref_call_id: seq=9\n'
            '- hits: 4\n'
            '---\n')
        entries = bug_list(project_dir=str(world))
        e = entries[0]
        assert e['summary'] == 'yaml 风格' and e['detail'] == '别名行'
        assert e['ref_call_id'] == 'seq=9' and e['hits'] == 4

    def test_status_filter(self, world):
        p = bugs_path(str(world))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w', encoding='utf-8') as fh:
            fh.write(
            '# Bug 账本\n'
            '## BUG-0001 [t] [low] OPEN\n摘要：open 条目\n---\n'
            '## BUG-0002 [t] [low] CLOSED\n摘要：closed 条目\n---\n')
        open_e = bug_list(status='open', project_dir=str(world))
        closed_e = bug_list(status='CLOSED', project_dir=str(world))
        assert [e['id'] for e in open_e] == ['BUG-0001']
        assert [e['id'] for e in closed_e] == ['BUG-0002']

    def test_garbage_lines_skipped(self, world):
        p = bugs_path(str(world))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w', encoding='utf-8') as fh:
            fh.write('# Bug 账本\n这不是条目\n普通文字\n---\n')
        assert bug_list(project_dir=str(world)) == []
