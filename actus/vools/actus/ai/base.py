"""AI 决策层：协议与数据模型。

本模块是 Actus AI 层最底层的词汇表 —— 所有 provider 实现、工具目录、
意图选择、任务拆解都建立在这些类型上。

三条设计约定：

1. **失败编码进返回值，不抛异常**。`LLMClient.complete()` 契约上永不抛
   异常，任何失败都用 `LLMResponse(stop_reason='error')` 表达。
   理由：调用方（动作前置校验、doctor、Selector）是无保护调用，
   一次 provider 抖动不应该炸掉整条决策链。
2. **工具声明与动作契约同构**。`ToolSpec.parameters` 直接是 Actus 动作
   `args` 字段的 JSON Schema（draft-07），不做任何转换 —— MCP 的
   `_input_schema()` 已在做同一件事。
3. **错误码只用 vools.actus.errors.ERROR_CODES 里的既有码**。
   本包不新增错误码（LLM 相关语义经 `ERROR_MAP` 归一到既有码），
   以免下游按码分支时漏判。

Example:
    >>> spec = ToolSpec(name='cli_jq', description='jq JSON 处理',
    ...                 parameters={'type': 'object'}, action_id='cli.jq')
    >>> spec.action_id
    'cli.jq'
"""

__all__ = ['Role', 'StopReason', 'ErrorKind', 'ERROR_MAP', 'ToolSpec',
           'ToolCall', 'Message', 'LLMResponse', 'LLMClient',
           'llm_error_code']

# 角色：system / user / assistant / tool
Role = str

# 停止原因：stop=正常收敛 / tool_calls=要调工具 / length=被 max_tokens 截断
#          / content_filter=被内容过滤 / error=失败（见 content）
StopReason = str

# LLM 侧错误类别（内部用，不出现在 ActionError.code 里）
ErrorKind = str

# LLM 错误类别 → vools.actus.errors.ERROR_CODES 既有码的归一表。
# 刻意不新增码：ERROR_CODES 是 docs/08 §5 的权威清单，
# 引入表外码会让下游按码分支的实现静默漏判。
ERROR_MAP = {
    'auth': 'auth_required',            # 密钥缺失 / 401 / 403
    'quota': 'dependency_missing',      # 429 / 配额耗尽
    'unreachable': 'dependency_missing',  # DNS / 连接失败 / 超时
    'bad_response': 'internal',         # 非 JSON / 缺 choices / 形状不符
    'param_invalid': 'param_invalid',   # 调用参数不合法（如 stream=True 未实现）
    'unknown_provider': 'param_invalid',  # provider 名未登记
}


def llm_error_code(kind: str) -> str:
    """把 LLM 错误类别映射到既有 ActionError 码。

    Args:
        kind: ErrorKind 之一，见 ERROR_MAP 的键。

    Returns:
        str: ERROR_CODES 内的错误码。未知类别归一到 'internal'
        （而不是抛异常 —— 错误处理路径本身不该再抛）。

    Example:
        >>> llm_error_code('auth')
        'auth_required'
    """
    return ERROR_MAP.get(kind, 'internal')


from vools.core.dataclass_compat import dataclass, field  # noqa: E402  (约定：dataclass 走兼容层)


@dataclass(frozen=True)
class ToolSpec(object):
    """LLM function-calling 工具声明，由 Actus 动作的 args schema 转换而来。

    Attributes:
        name: 已规范化工具名，同 mcp_server._tool_name 的规则。
        description: 动作 description（+ usage 拼接，截断至 1024 字符）。
        parameters: 动作 args 的 JSON Schema（draft-07），原样透传。
        action_id: 回溯用，LLM 命中后可映射回动作 id。
        trust: 动作 trust 字段（'audit'|'trusted'|'sandbox'），
            供调用方决定是否需要人工确认。
        permissions: 动作声明的权限元组，供调用方做白名单校验。

    Example:
        >>> ToolSpec(name='x', description='y', parameters={}).permissions
        ()
    """

    name: str
    description: str = ''
    parameters: dict = field(default_factory=dict)
    action_id: str = ''
    trust: str = 'audit'
    permissions: tuple = ()


@dataclass(frozen=True)
class ToolCall(object):
    """LLM 请求的一次工具调用。

    Attributes:
        id: provider 给出的调用 id，原样回传给 role='tool' 的消息。
        name: 工具名（对应 ToolSpec.name）。
        arguments: 已解析成 dict 的参数。解析失败时该次调用会被丢弃，
            错误记在 LLMResponse.stop_reason。
    """

    id: str
    name: str
    arguments: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Message(object):
    """单轮对话消息。

    role='tool' 时必须带 tool_call_id（回指 ToolCall.id）。
    role='assistant' 且带 tool_calls 时 content 允许为空。

    Attributes:
        role: Role 之一。
        content: 文本内容。
        tool_calls: ToolCall 元组，普通消息为空。
        tool_call_id: 工具结果的回指 id。
        name: 工具名（role='tool' 时用）。

    Example:
        >>> Message(role='user', content='hi').tool_calls
        ()
    """

    role: str
    content: str = ''
    tool_calls: tuple = ()
    tool_call_id: str = ''
    name: str = ''


@dataclass(frozen=True)
class LLMResponse(object):
    """一次补全结果。

    失败时不抛异常，而是 stop_reason='error' 且 content 存人类可读描述。

    Attributes:
        content: 文本内容（失败时为错误描述）。
        tool_calls: ToolCall 元组。
        stop_reason: StopReason 之一。
        prompt_tokens: 输入 token 数，响应无 usage 时为 0（不估算）。
        completion_tokens: 输出 token 数，同上。
        model: 实际使用的模型名，供 cost.record_cost 记账。
        raw: provider 原始响应，便于排障。

    Example:
        >>> LLMResponse(prompt_tokens=10, completion_tokens=5).total_tokens
        15
    """

    content: str = ''
    tool_calls: tuple = ()
    stop_reason: str = 'stop'
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = ''
    raw: dict = field(default_factory=dict)

    @property
    def total_tokens(self):
        """int: 本次调用消耗的总 token 数。"""
        return self.prompt_tokens + self.completion_tokens

    @property
    def failed(self):
        """bool: 是否是失败响应。"""
        return self.stop_reason == 'error'


class LLMClient(object):
    """LLM provider 协议。

    实现类必须继承本类并注册到 vools.actus.ai.registry。
    本类**不打算被直接实例化** —— 它是协议与文档载体。

    Example:
        >>> class Fake(LLMClient):
        ...     name = 'fake'
        ...     def complete(self, messages, tools=None, temperature=0.0,
        ...                  max_tokens=None):
        ...         return LLMResponse(content='ok')
        ...     def available(self):
        ...         return True
        >>> Fake().complete([]).content
        'ok'
    """

    name = 'abstract'

    def complete(self, messages, tools=None, temperature=0.0, max_tokens=None,
                 stream=False):
        """发起一次补全。

        Args:
            messages: List[Message]，已按本 provider 形状排好序。
            tools: Optional[List[ToolSpec]]；None 表示不用 function calling。
            temperature: float，采样温度。
            max_tokens: Optional[int]，输出上限。
            stream: 预留的流式开关。**当前所有实现均未实现流式** ——
                传 True 必须显式返回 stop_reason='error' 说明未实现，
                **不许静默忽略**（静默降级会让调用方以为拿到了完整结果）。

        Returns:
            LLMResponse: 补全结果。**任何失败都编码进返回值**
            （stop_reason='error'），本方法契约上不抛异常。

        Raises:
            不抛。
        """
        raise NotImplementedError('%s 未实现 complete()' % self.name)

    def available(self):
        """探测端点与密钥是否就绪。

        Returns:
            bool: True 表示可正常调用。**探测失败必须返回 False**，
            禁止抛异常 —— 调用方（doctor / 动作前置校验）会无保护调用它。
        """
        return False