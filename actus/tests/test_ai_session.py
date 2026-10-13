"""会话状态、token 预算、落盘往返的判据。"""

import json
import os

import pytest

import _ai_local_bootstrap as _boot   # noqa: F401  —— 必须先于 vools.actus

_boot.install()

from vools.actus.ai.base import Message, ToolCall
from vools.actus.ai.session import AgentSession, SessionEvent, session_path


# ── 预算 ──

def test_budget_left_unlimited():
    """budget<=0 表示不限，返回 -1（与「刚好用完」的 0 区分开）。"""
    s = AgentSession('s1')
    assert s.budget_left(0) == -1
    assert s.budget_left(-5) == -1
    assert s.budget_left(None) == -1


def test_budget_left_decrements():
    s = AgentSession('s1')
    s.total_tokens = 30
    assert s.budget_left(100) == 70
    s.total_tokens = 120
    assert s.budget_left(100) == -20, '超支应返回负数而不是 0'


# ── 累积 ──

def test_append_and_events():
    s = AgentSession('s1')
    msg = s.append(Message(role='user', content='hi'))
    assert s.messages == [msg]
    ev = s.add_event('select', {'action_id': 'cli.jq'})
    assert isinstance(ev, SessionEvent)
    assert ev.data['action_id'] == 'cli.jq'
    assert ev.at, '事件应自带时间戳'
    assert len(s.events) == 1


def test_new_id_has_prefix():
    """会话 id 要能自解释（_meta/agents/ 下按时间排序有用）。"""
    sid = AgentSession.new_id('agent')
    assert sid.startswith('agent-')
    assert len(sid) > len('agent-')


# ── 路径 ──

def test_session_path_shape():
    """路径分隔符随平台变化，断言必须用 os.path.join 而不是硬编码 '/'。"""
    assert session_path('/tmp/_meta', 'agent-20261013') == \
        os.path.join('/tmp/_meta', 'agents', 'agent_20261013.json')


def test_session_path_sanitizes_id():
    """id 里的路径分隔符与点都要清掉 —— 文件名里留 '..' 读起来像逃逸意图。"""
    got = session_path('/tmp/_meta', '../../etc/passwd')
    name = os.path.basename(got)
    assert '..' not in name
    assert os.sep not in name.replace(os.sep, '')  # 文件名内不再有分隔符残留
    assert os.path.dirname(got) == os.path.join('/tmp/_meta', 'agents')


# ── 落盘往返 ──

def test_save_load_roundtrip(tmp_path):
    """往返后 messages / total_tokens / events 必须相等。"""
    s = AgentSession('rt-1', '/proj', 'exec-9')
    s.append(Message(role='user', content='hi'))
    s.append(Message(role='assistant', content='', tool_calls=(
        ToolCall(id='c1', name='cli_jq', arguments={'filter': '.a'}),)))
    s.append(Message(role='tool', content='ok', tool_call_id='c1', name='cli_jq'))
    s.total_tokens = 42
    s.add_event('call', {'n': 1})

    path = s.save(str(tmp_path))
    assert os.path.isfile(path)

    back = AgentSession.load(path)
    assert back.session_id == 'rt-1'
    assert back.project_dir == '/proj'
    assert back.exec_id == 'exec-9'
    assert back.total_tokens == 42
    assert len(back.messages) == 3
    assert back.messages[1].tool_calls[0].arguments == {'filter': '.a'}
    assert isinstance(back.messages[1].tool_calls[0], ToolCall)
    assert back.messages[2].tool_call_id == 'c1'
    assert len(back.events) == 1


def test_save_is_json_serializable(tmp_path):
    """落盘产物必须是合法 JSON（下游可能有别的工具要读它）。"""
    s = AgentSession('rt-2')
    s.append(Message(role='user', content='中文也要能写'))
    path = s.save(str(tmp_path))
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    assert data['messages'][0]['content'] == '中文也要能写'


def test_save_creates_missing_dirs(tmp_path):
    """目标目录不存在时自动创建，不该抛异常。"""
    s = AgentSession('rt-3')
    path = s.save(str(tmp_path / 'deep' / 'nested'))
    assert os.path.isfile(path)


def test_load_missing_file_raises():
    from vools.actus.errors import ActionError
    with pytest.raises(ActionError) as ei:
        AgentSession.load('/definitely/not/here.json')
    assert ei.value.code == 'action_not_found'


def test_load_corrupt_file_raises():
    """坏文件要报 action_invalid，而不是抛 JSONDecodeError。"""
    import tempfile
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False,
                                     encoding='utf-8') as f:
        f.write('{ not json')
        bad = f.name
    from vools.actus.errors import ActionError
    try:
        with pytest.raises(ActionError) as ei:
            AgentSession.load(bad)
        assert ei.value.code == 'action_invalid'
    finally:
        os.unlink(bad)


def test_load_tolerates_missing_fields(tmp_path):
    """老版本/手写的会话文件缺字段时要能读，不能 KeyError。"""
    path = tmp_path / 'agents' / 'thin.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'session_id': 'thin'}), encoding='utf-8')
    back = AgentSession.load(str(path))
    assert back.session_id == 'thin'
    assert back.messages == []
    assert back.events == []
