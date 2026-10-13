"""决策会话：消息历史 + token 预算 + 事件流。

为什么需要它：Actus 的执行模型是「跑完 → 打印一次 JSON」，没有增量
通道。所以本类**不提供**流式渲染，只做三件离线可做的事 —— 留痕、
预算控制、事件累积。事件由调用方在关键节点 append，需要 UI 时
再从 session.events 回放。

落盘沿用 Actus 既有惯例：`_meta/agents/<session_id>.json`
（对齐 loop_prompt 的 `_meta/loops/`）。

Example:
    >>> s = AgentSession('demo', '/tmp')
    >>> s.append(Message(role='user', content='hi'))
    >>> s.total_tokens
    0
    >>> s.budget_left(0)      # 0 表示不限
    -1
"""

__all__ = ['SessionEvent', 'AgentSession', 'session_path']

import json
import os
import re
from datetime import datetime, timezone, timedelta

from vools.core.dataclass_compat import dataclass, field

from .base import Message, ToolCall

_TZ = timezone(timedelta(hours=8))

# session_id 只保留字母数字与下划线。**点也一并替换掉** —— 保留 `.` 会让
# '../../etc/passwd' 变成 '.._.._etc_passwd'，虽然不含分隔符、仍在
# agents/ 目录内，但文件名里留 '..' 读起来像逃逸意图，不如彻底清掉。
_ID_SAFE = re.compile(r'[^A-Za-z0-9_]+')


@dataclass(frozen=True)
class SessionEvent(object):
    """会话中的一个事件点。

    Attributes:
        kind: 事件类型（如 'select' / 'call' / 'error'），由调用方约定。
        data: 附加结构化信息。
        at: ISO8601 带时区的时间戳。
    """

    kind: str
    data: dict = field(default_factory=dict)
    at: str = ''


def session_path(meta_dir, session_id):
    """算出会话落盘路径。

    Args:
        meta_dir: _meta 目录。
        session_id: 会话 id。非法字符（含 `.` `-` 与路径分隔符）会被替换为
            '_'，保证结果始终落在 meta_dir 内。

    Returns:
        str: 路径，形如 '<meta_dir>/agents/<session_id>.json'。

    Example:
        >>> import os
        >>> session_path('/tmp/_meta', 'agent-20261013') == \\
        ...     os.path.join('/tmp/_meta', 'agents', 'agent_20261013.json')
        True
    """
    safe = _ID_SAFE.sub('_', str(session_id or 'session')).strip('_') or 'session'
    return os.path.join(str(meta_dir), 'agents', safe + '.json')


class AgentSession(object):
    """一次决策会话。

    Attributes:
        session_id: 会话标识，形如 'agent-20261013-142530'。
        project_dir: 关联的工作目录。
        exec_id: 触发的 Actus 执行 id（可空）。
        messages: 消息历史，按追加顺序。
        total_tokens: 累计 token 消耗。
        events: 事件列表，供 UI 回放。
    """

    def __init__(self, session_id, project_dir='', exec_id=''):
        """构造空会话。

        Args:
            session_id: 会话标识。
            project_dir: 工作目录。
            exec_id: Actus 执行 id。
        """
        self.session_id = str(session_id or '')
        self.project_dir = str(project_dir or '')
        self.exec_id = str(exec_id or '')
        self.messages = []
        self.total_tokens = 0
        self.events = []

    @staticmethod
    def new_id(prefix='agent'):
        """生成一个带时间戳的会话 id。

        Args:
            prefix: id 前缀。

        Returns:
            str: 形如 'agent-20261013-142530' 的 id。
        """
        return prefix + '-' + datetime.now(_TZ).strftime('%Y%m%d-%H%M%S')

    @staticmethod
    def _now():
        """str: 当前时间的 ISO8601 文本。"""
        return datetime.now(_TZ).isoformat(timespec='seconds')

    def append(self, message):
        """追加一条消息。

        Args:
            message: Message 实例。

        Returns:
            Message: 原对象，便于链式。
        """
        self.messages.append(message)
        return message

    def add_event(self, kind, data=None):
        """记录一个事件点。

        Args:
            kind: 事件类型。
            data: 附加结构化信息。

        Returns:
            SessionEvent: 新建的事件。
        """
        ev = SessionEvent(kind=str(kind), data=data or {}, at=self._now())
        self.events.append(ev)
        return ev

    def budget_left(self, budget):
        """剩余 token 预算。

        Args:
            budget: 预算上限；<= 0 表示不限。

        Returns:
            int: 剩余额度；**不限时返回 -1**（与 0 区分开 ——
            0 表示刚好用完）。
        """
        if budget is None or int(budget) <= 0:
            return -1
        return int(budget) - self.total_tokens

    def to_dict(self):
        """转成可 JSON 序列化的结构。

        Returns:
            dict: 会话快照。
        """
        return {
            'session_id': self.session_id,
            'project_dir': self.project_dir,
            'exec_id': self.exec_id,
            'total_tokens': self.total_tokens,
            'messages': [{'role': m.role, 'content': m.content,
                          'tool_call_id': m.tool_call_id, 'name': m.name,
                          'tool_calls': [{'id': t.id, 'name': t.name,
                                          'arguments': t.arguments}
                                         for t in m.tool_calls]}
                         for m in self.messages],
            'events': [{'kind': e.kind, 'data': e.data, 'at': e.at}
                       for e in self.events],
        }

    def save(self, meta_dir):
        """落盘到 meta_dir/agents/<session_id>.json。

        Args:
            meta_dir: _meta 目录；不存在会自动创建。

        Returns:
            str: 落盘路径。
        """
        path = session_path(meta_dir, self.session_id)
        parent = os.path.dirname(path)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        return path

    @classmethod
    def load(cls, path):
        """从落盘文件读回会话。

        Args:
            path: save() 返回的路径。

        Returns:
            AgentSession: 读回的会话。

        Raises:
            ActionError: code='action_not_found'，文件不存在或格式非法。
        """
        from ..errors import ActionError
        if not os.path.isfile(path):
            raise ActionError('action_not_found', '会话文件不存在: %s' % path)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            raise ActionError('action_invalid', '会话文件无法解析: %s' % e,
                              {'path': path})
        obj = cls(data.get('session_id') or '', data.get('project_dir') or '',
                  data.get('exec_id') or '')
        obj.total_tokens = int(data.get('total_tokens') or 0)
        for m in data.get('messages') or []:
            calls = tuple(
                ToolCall(id=t.get('id') or '', name=t.get('name') or '',
                         arguments=t.get('arguments') or {})
                for t in (m.get('tool_calls') or []))
            obj.messages.append(Message(role=m.get('role') or 'user',
                                         content=m.get('content') or '',
                                         tool_calls=calls,
                                         tool_call_id=m.get('tool_call_id') or '',
                                         name=m.get('name') or ''))
        for e in data.get('events') or []:
            obj.events.append(SessionEvent(kind=e.get('kind') or '',
                                           data=e.get('data') or {},
                                           at=e.get('at') or ''))
        return obj