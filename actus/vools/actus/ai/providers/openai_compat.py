"""OpenAI 兼容端点客户端 —— 一个实现覆盖 5 家 preset。

覆盖 openai / deepseek / groq / ollama / vllm，原因是它们都提供
`POST {base_url}/chat/completions` 这一个形状；差异只在 base_url、
默认模型与密钥环境变量，已由 registry.PRESETS 表达。

只依赖标准库 urllib —— vools-actus 的依赖面不容许为 AI 层加重 SDK。

Example:
    >>> c = OpenAICompatClient(base_url='http://localhost:11434/v1', model='qwen')
    >>> c.available()          # 本地端点不可达时不抛异常，返回 False
    False
"""

__all__ = ['OpenAICompatClient']

import json
import os
import socket
import urllib.error
import urllib.request

from ..base import LLMResponse, LLMClient, llm_error_code, records_usage
from ..registry import register_provider

# 不实现流式：显式报错好过静默返回不完整结果。
_STREAM_MSG = ('stream=True 尚未实现 —— vools.actus.ai 目前只提供一次性补全；'
               '如需增量输出请消费 AgentSession 的事件流')


def _error_response(kind, message, model=''):
    """把错误类别编成 LLMResponse，错误码放进 raw 供上层取用。

    Args:
        kind: base.ErrorKind 之一。
        message: 人类可读描述。
        model: 参与本次调用的模型名。

    Returns:
        LLMResponse: stop_reason='error'，raw 里带 error_kind 与 code。
    """
    return LLMResponse(
        content=message,
        stop_reason='error',
        model=model,
        raw={'error_kind': kind, 'code': llm_error_code(kind)},
    )


@register_provider
class OpenAICompatClient(LLMClient):
    """OpenAI 兼容 chat/completions 客户端。

    Attributes:
        base_url: 端点前缀，如 'https://api.openai.com/v1'。
        model: 模型名；空串表示由端点自行决定（vllm 常见）。
        env_name: 密钥的环境变量名；空串表示无需密钥（本地端点）。
        timeout: 单次请求超时秒数。

    Example:
        >>> OpenAICompatClient(name='openai_compat').complete([])
        ... # doctest: +SKIP
    """

    name = 'openai_compat'

    def __init__(self, base_url='', model='', api_key='', env_name='OPENAI_API_KEY',
                 timeout=60, name=None):
        """构造客户端。

        Args:
            base_url: 端点前缀。
            model: 模型名。
            api_key: 显式密钥；留空则按 env_name 读环境变量。
            env_name: 密钥环境变量名。
            timeout: 请求超时秒数。
            name: 覆盖类级 provider 名（registry 传 preset 名时用）。
        """
        self.base_url = (base_url or '').rstrip('/')
        self.model = model or ''
        self.env_name = env_name or ''
        self.timeout = int(timeout)
        if name:
            self.name = name
        self._api_key = api_key or ''

    # ── 内部 ──

    def _resolve_key(self):
        """str: 密钥。优先显式值，其次 env_name 指向的环境变量。"""
        if self._api_key:
            return self._api_key
        if self.env_name:
            return os.environ.get(self.env_name, '') or ''
        return ''

    @staticmethod
    def _build_messages(messages):
        """把 List[Message] 转成 OpenAI 形状的消息数组。"""
        out = []
        for m in messages or []:
            item = {'role': m.role, 'content': m.content or ''}
            if m.role == 'assistant' and m.tool_calls:
                item['tool_calls'] = [{
                    'id': tc.id,
                    'type': 'function',
                    'function': {'name': tc.name, 'arguments': json.dumps(
                        tc.arguments, ensure_ascii=False)},
                } for tc in m.tool_calls]
            elif m.role == 'tool':
                item['tool_call_id'] = m.tool_call_id
                if m.name:
                    item['name'] = m.name
            out.append(item)
        return out

    @staticmethod
    def _build_tools(tools):
        """把 List[ToolSpec] 转成 OpenAI function-calling 形状。"""
        return [{'type': 'function',
                 'function': {'name': t.name, 'description': t.description or '',
                              'parameters': t.parameters or {}}}
                for t in tools or []]

    def _parse(self, payload):
        """解析 chat/completions 响应为 LLMResponse。

        契约：任何形状问题都归一为 bad_response 错误返回，不抛异常。

        Args:
            payload: 已 json.loads 的响应体。

        Returns:
            LLMResponse: 成功时 stop_reason 为 'stop' 或 'tool_calls'。

        Raises:
            不抛。
        """
        from ..base import ToolCall
        if not isinstance(payload, dict):
            return _error_response('bad_response', '响应不是 JSON object: %r' % type(payload),
                                   self.model)
        choices = payload.get('choices')
        if not isinstance(choices, list) or not choices:
            return _error_response('bad_response', '响应缺 choices 数组', self.model)
        message = choices[0].get('message')
        if not isinstance(message, dict):
            return _error_response('bad_response', '响应缺 choices[0].message', self.model)

        calls = []
        for raw_call in message.get('tool_calls') or []:
            fn = (raw_call or {}).get('function') or {}
            name = fn.get('name') or ''
            raw_args = fn.get('arguments') or '{}'
            # arguments 是 JSON 字符串，必须解析；解析失败不当致命错误，
            # 降级为空参数并把该次调用标出来。
            if isinstance(raw_args, str):
                try:
                    args = json.loads(raw_args) if raw_args.strip() else {}
                except ValueError as e:
                    return _error_response(
                        'bad_response',
                        'tool_call.arguments 不是合法 JSON: %s' % e, self.model)
            elif isinstance(raw_args, dict):
                args = raw_args
            else:
                args = {}
            if not isinstance(args, dict):
                args = {'_raw': args}
            calls.append(ToolCall(id=raw_call.get('id') or '', name=name, arguments=args))

        usage = payload.get('usage') or {}
        stop_reason = 'tool_calls' if calls else 'stop'
        return LLMResponse(
            content=message.get('content') or '',
            tool_calls=tuple(calls),
            stop_reason=stop_reason,
            # 响应没有 usage 时填 0 —— 不猜、不估算。
            prompt_tokens=int(usage.get('prompt_tokens') or 0),
            completion_tokens=int(usage.get('completion_tokens') or 0),
            model=payload.get('model') or self.model,
            raw=payload,
        )

    # ── LLMClient 协议 ──

    @records_usage          # 成功调用后 best-effort 记账（见 base.records_usage）
    def complete(self, messages, tools=None, temperature=0.0, max_tokens=None,
                 stream=False):
        """发起一次补全。失败编码进返回值，不抛异常。"""
        if stream:
            # 显式拒绝优于静默降级：静默返回非流式结果会让调用方
            # 误以为拿到的就是增量内容。
            return _error_response('param_invalid', _STREAM_MSG, self.model)
        if not self.base_url:
            return _error_response('param_invalid', '缺少 base_url', self.model)
        key = self._resolve_key()
        if self.env_name and not key:
            return _error_response(
                'auth',
                '缺少密钥：环境变量 %s 未设置' % self.env_name, self.model)

        body = {'model': self.model, 'messages': self._build_messages(messages),
                'temperature': temperature}
        if max_tokens:
            body['max_tokens'] = int(max_tokens)
        if tools:
            body['tools'] = self._build_tools(tools)

        headers = {'Content-Type': 'application/json'}
        if key:
            headers['Authorization'] = 'Bearer ' + key
        req = urllib.request.Request(
            self.base_url + '/chat/completions',
            data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
            headers=headers)
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
        """探测密钥或本地端点是否就绪。**任何失败都返回 False，不抛异常。**"""
        if self.env_name and not self._resolve_key():
            return False
        if not self.env_name:
            # 本地端点：探一次模型列表，2 秒超时
            try:
                req = urllib.request.Request(self.base_url + '/models')
                with urllib.request.urlopen(req, timeout=2):
                    return True
            except Exception:
                return False
        return True


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