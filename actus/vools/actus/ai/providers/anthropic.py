"""Anthropic Messages API 客户端。

与 OpenAI 兼容端点的差异有三处，故独立成实现（而不是塞进
openai_compat 加分支）：`system` 是顶层字段而非 message、content
是内容块数组而非字符串、tool schema 的参数键叫 `input_schema`。
这三处差异会渗透到消息序列化与解析，分支处理反而更乱。

未经真机密钥实测 —— 见模块末尾的验证声明。

Example:
    >>> AnthropicClient().available()
    False
"""

__all__ = ['AnthropicClient']

import json
import os
import socket
import urllib.error
import urllib.request

from ..base import LLMResponse, LLMClient, ToolCall, llm_error_code
from ..registry import register_provider

# API 版本头。Anthropic 用日期版本号，不跟随模型名。
API_VERSION = '2023-06-01'
DEFAULT_BASE_URL = 'https://api.anthropic.com/v1'
DEFAULT_MODEL = 'claude-3-5-sonnet-latest'
DEFAULT_ENV = 'ANTHROPIC_API_KEY'

_STREAM_MSG = ('stream=True 尚未实现 —— vools.actus.ai 目前只提供一次性补全；'
               '如需增量输出请消费 AgentSession 的事件流')


def _error_response(kind, message, model=''):
    """把错误类别编成 LLMResponse，错误码放进 raw 供上层取用。"""
    return LLMResponse(content=message, stop_reason='error', model=model,
                       raw={'error_kind': kind, 'code': llm_error_code(kind)})


@register_provider
class AnthropicClient(LLMClient):
    """Anthropic Messages API 客户端。

    Attributes:
        base_url: 端点前缀，默认 'https://api.anthropic.com/v1'。
        model: 模型名。
        env_name: 密钥环境变量名。
        timeout: 请求超时秒数。

    验证状态：**本实现只有 mock 覆盖，无真机密钥实测**。首次接入前请用
    真实密钥跑一次 `complete([Message(role='user', content='hi')])` 核对
    token 计数与 stop_reason 取值。
    """

    name = 'anthropic'

    def __init__(self, base_url='', model='', api_key='', env_name='',
                 timeout=60, max_tokens=4096, name=None):
        """构造客户端。

        Args:
            base_url: 端点前缀，留空用 DEFAULT_BASE_URL。
            model: 模型名，留空用 DEFAULT_MODEL。
            api_key: 显式密钥，留空则读 env_name 指向的环境变量。
            env_name: 密钥环境变量名，留空用 'ANTHROPIC_API_KEY'。
            timeout: 请求超时秒数。
            max_tokens: Messages API 的 max_tokens 是必填项，给个安全默认。
            name: 覆盖类级 provider 名。
        """
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip('/')
        self.model = model or DEFAULT_MODEL
        self.env_name = env_name or DEFAULT_ENV
        self.timeout = int(timeout)
        self.max_tokens = int(max_tokens)
        if name:
            self.name = name
        self._api_key = api_key or ''

    def _resolve_key(self):
        """str: 密钥。优先显式值，其次环境变量。"""
        if self._api_key:
            return self._api_key
        return os.environ.get(self.env_name, '') or ''

    def _build_body(self, messages, tools, temperature, max_tokens):
        """把 Message 序列转成 Messages API 请求体。

        关键约束：Messages API 要求 user/assistant **严格交替**，且一次
        assistant 回合里多个 tool_use 的回传必须是【同一个 user 回合】
        content 数组里的多个 tool_result 块。因此连续的 role='tool' 消息
        必须合并，不能各自发成独立 user 消息（否则 400 roles must alternate）。
        """
        system_parts = [m.content for m in messages if m.role == 'system']
        convo = []

        def _last_user_blocks():
            """取末尾 user 回合的 content 列表（没有则新建）。"""
            if convo and convo[-1]['role'] == 'user' \
                    and isinstance(convo[-1]['content'], list):
                return convo[-1]['content']
            convo.append({'role': 'user', 'content': []})
            return convo[-1]['content']

        for m in messages:
            if m.role == 'system':
                continue
            if m.role == 'tool':
                _last_user_blocks().append({
                    'type': 'tool_result', 'tool_use_id': m.tool_call_id,
                    'content': m.content or '',
                })
            elif m.role == 'assistant' and m.tool_calls:
                blocks = []
                if m.content:
                    blocks.append({'type': 'text', 'text': m.content})
                for tc in m.tool_calls:
                    blocks.append({'type': 'tool_use', 'id': tc.id,
                                   'name': tc.name, 'input': tc.arguments})
                convo.append({'role': 'assistant', 'content': blocks})
            elif m.role == 'user' and convo and convo[-1]['role'] == 'user' \
                    and isinstance(convo[-1]['content'], list):
                # 紧跟工具结果的同一用户回合：追加文本块，仍保持一次 user 回合
                if m.content:
                    convo[-1]['content'].append({'type': 'text', 'text': m.content})
            else:
                convo.append({'role': m.role, 'content': m.content or ''})

        # 若某个 user 回合只有结构化块（理论不会），兜底转字符串
        body = {'model': self.model, 'max_tokens': int(max_tokens or self.max_tokens),
                'messages': convo}
        if system_parts:
            body['system'] = '\n\n'.join(system_parts)
        # 注意：不能写 `if temperature:` —— 0.0 是合法且常用的确定性取值，
        # 真值判断会把它丢弃，使请求退回 Anthropic 默认的 1.0（选择器明确要 0.0）。
        if temperature is not None:
            body['temperature'] = temperature
        if tools:
            body['tools'] = [{'name': t.name, 'description': t.description or '',
                              'input_schema': t.parameters or {'type': 'object'}}
                             for t in tools]
        return body

    def _parse(self, payload):
        """解析 Messages API 响应为 LLMResponse。形状问题归一为 bad_response。"""
        if not isinstance(payload, dict):
            return _error_response('bad_response', '响应不是 JSON object', self.model)
        blocks = payload.get('content')
        if not isinstance(blocks, list):
            return _error_response('bad_response', '响应缺 content 数组', self.model)

        texts, calls = [], []
        for block in blocks:
            if not isinstance(block, dict):
                continue
            kind = block.get('type')
            if kind == 'text':
                texts.append(block.get('text') or '')
            elif kind == 'tool_use':
                args = block.get('input')
                calls.append(ToolCall(id=block.get('id') or '',
                                      name=block.get('name') or '',
                                      arguments=args if isinstance(args, dict) else {}))

        usage = payload.get('usage') or {}
        return LLMResponse(
            content='\n'.join(t for t in texts if t),
            tool_calls=tuple(calls),
            stop_reason='tool_calls' if calls else 'stop',
            prompt_tokens=int(usage.get('input_tokens') or 0),
            completion_tokens=int(usage.get('output_tokens') or 0),
            model=payload.get('model') or self.model,
            raw=payload,
        )

    def complete(self, messages, tools=None, temperature=0.0, max_tokens=None,
                 stream=False):
        """发起一次补全。失败编码进返回值，不抛异常。"""
        if stream:
            return _error_response('param_invalid', _STREAM_MSG, self.model)
        key = self._resolve_key()
        if not key:
            return _error_response('auth',
                                   '缺少密钥：环境变量 %s 未设置' % self.env_name, self.model)

        body = self._build_body(messages, tools, temperature, max_tokens)
        req = urllib.request.Request(
            self.base_url + '/messages',
            data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
            headers={'Content-Type': 'application/json',
                     'x-api-key': key,
                     'anthropic-version': API_VERSION})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode('utf-8')
        except urllib.error.HTTPError as e:
            code = getattr(e, 'code', 0)
            if code in (401, 403):
                kind = 'auth'
            elif code == 429:
                kind = 'quota'
            else:
                kind = 'unreachable'
            return _error_response(kind, 'HTTP %s: %s' % (code, _tail(e)), self.model)
        except (urllib.error.URLError, socket.timeout, OSError) as e:
            return _error_response('unreachable', '端点不可达: %s' % _tail(e), self.model)

        try:
            payload = json.loads(raw)
        except ValueError as e:
            return _error_response('bad_response', '响应不是合法 JSON: %s' % e, self.model)
        return self._parse(payload)

    def available(self):
        """密钥是否就绪。**不探测网络**（Anthropic 无 /models 端点）。"""
        return bool(self._resolve_key())


def _tail(exc, limit=300):
    """取异常的可读尾部文本。

    Args:
        exc: 异常对象。
        limit: 截断长度。

    Returns:
        str: 异常描述，截断至 limit 字符。
    """
    try:
        msg = getattr(exc, 'reason', None) or str(exc) or ''
    except Exception:
        msg = ''
    return str(msg)[:limit]