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
           'llm_error_code', 'records_usage', 'usage_record_stats']

import functools

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


# ---------------------------------------------------------------------------
# 用量记账（best-effort）
#
# 审计背景：`cost.record_cost()` 全库从未被调用 —— 账本永远是空的，于是
# `check_budget()` 恒 `spent_usd=0`、`alert_budget_if_over()` 的告警分支在生产
# 路径上永远走不到（"承诺了但没做"）。现在两个真实 provider 的 `complete()`
# 成功后由 `@records_usage` 记账：一处实现，两处挂载；不碰 Selector/Planner 的
# 调用点，也不让测试里的 FakeClient 往真实账本里写垃圾行。
#
# 三条硬约束：
#   1. **记账失败绝不影响 LLM 调用**：异常在这里吞掉，但计入 `usage_record_stats()`
#      的计数器（留信号，不静默）。
#   2. **cost_usd 口径必须诚实**：只有价格表能唯一定位到该模型时才写估算值，并把
#      来源写进 `cost_source`；否则写 `None`（账本里是 JSON null）+ `unknown` 标记，
#      **绝不用 0 冒充真实成本**（0 的语义是"确实免费"，那是另一件事）。
#   3. **失败响应不记账**（`stop_reason='error'` 没发生真实调用）；成功但端点
#      不返回 usage 的调用**照记一行**（tokens=0、cost_usd=null、
#      cost_source='unknown:no-usage-tokens'）—— 调用确实发生了，装作没发生才是失真。
# ---------------------------------------------------------------------------

# 记账通道运行计数（排障用；模块级，进程内累积）
_USAGE_RECORD_ATTEMPTS = 0
_USAGE_RECORD_FAILURES = 0
_USAGE_RECORD_LAST_ERROR = ''

# 账本里 `action_id` 的取值：这不是动作调用，是 AI 层自己的用量
_USAGE_ACTION_ID = 'ai.llm.complete'

# 价格表来源标识（写进账本行，让"这个数从哪来"可追溯）
_PRICE_SOURCE = 'estimated:routing.PROVIDER_COST_PERF'


def usage_record_stats():
    """返回记账通道的计数（只读）。

    Returns:
        dict: attempts（尝试次数）、failures（失败次数）、last_error（最近一次
        失败原因，成功过则为空串）。排障时用它判断"账本为空"是"没调用"还是
        "记账一直失败"—— 后者在日志里不会有任何痕迹。
    """
    return {
        'attempts': _USAGE_RECORD_ATTEMPTS,
        'failures': _USAGE_RECORD_FAILURES,
        'last_error': _USAGE_RECORD_LAST_ERROR,
    }


def _lookup_price_per_1k(provider, model):
    """从 routing.PROVIDER_COST_PERF 查每 1k token 的估算单价。

    返回 (price, matched):
      price   —— float 或 None（价格表里没有 → None，绝不返回 0 冒充免费）
      matched —— 命中的来源描述（provider/model），供账本行追溯

    查找顺序：先按 (provider, model) 精确命中；再按 model 扫全表（同一模型在
    不同 provider 下单价可能不同，扫到多个则取字典序第一个并把歧义写进 matched）。
    价格表本身是**路由打分用的启发式表**（含 rank 字段），不是正式计费表 ——
    所以账本把结果标成 estimated，而不是 final。
    """
    if not model:
        return None, ''
    try:
        from .routing import PROVIDER_COST_PERF
    except Exception:
        return None, ''

    entry = PROVIDER_COST_PERF.get(provider, {}).get(model)
    if isinstance(entry, dict):
        price = entry.get('price_per_1k')
        if isinstance(price, (int, float)) and not isinstance(price, bool):
            return float(price), '%s/%s' % (provider, model)

    matches = []
    for prov in sorted(PROVIDER_COST_PERF):
        candidate = PROVIDER_COST_PERF[prov].get(model)
        if isinstance(candidate, dict):
            price = candidate.get('price_per_1k')
            if isinstance(price, (int, float)) and not isinstance(price, bool):
                matches.append((prov, float(price)))
    if len(matches) == 1:
        prov, price = matches[0]
        return price, '%s/%s' % (prov, model)
    if len(matches) > 1:
        prov, price = matches[0]
        ambiguous = ','.join(p for p, _v in matches)
        return price, '%s/%s(ambiguous:%s)' % (prov, model, ambiguous)
    return None, ''


def _record_usage(client, response):
    """把一次成功调用写进成本账本。调用方负责兜异常。"""
    global _USAGE_RECORD_ATTEMPTS, _USAGE_RECORD_FAILURES, _USAGE_RECORD_LAST_ERROR
    _USAGE_RECORD_ATTEMPTS += 1

    from ..cost import record_cost

    provider = getattr(client, 'name', '') or 'unknown'
    model = getattr(response, 'model', '') or getattr(client, 'model', '') or ''
    prompt_tokens = int(getattr(response, 'prompt_tokens', 0) or 0)
    completion_tokens = int(getattr(response, 'completion_tokens', 0) or 0)
    total_tokens = prompt_tokens + completion_tokens

    price, matched = _lookup_price_per_1k(provider, model)
    if total_tokens <= 0:
        # 调用成功但端点是"无 usage"的形状（部分本地 OpenAI 兼容端点如此）：
        # 调用确实发生了，只是我们不知道它的规模 —— 记一行 null，而不是装作没发生。
        cost_usd = None
        cost_source = 'unknown:no-usage-tokens'
    elif price is None:
        cost_usd = None                      # 诚实：未知就是未知，不是 0
        cost_source = 'unknown:no-price-entry'
    else:
        cost_usd = round(total_tokens / 1000.0 * price, 8)
        cost_source = _PRICE_SOURCE

    record_cost(
        _USAGE_ACTION_ID,
        provider,
        cost_usd,
        tokens=total_tokens,
        model=model,
        extra={
            'prompt_tokens': prompt_tokens,
            'completion_tokens': completion_tokens,
            'cost_source': cost_source,
            'price_per_1k': price,                  # None = 价格表没有该模型
            'price_source_matched': matched,        # 命中项，便于回溯
            'stop_reason': getattr(response, 'stop_reason', ''),
        },
    )


def records_usage(method):
    """装饰 `LLMClient.complete`：成功返回后 best-effort 记账。

    只挂在**真实 provider** 上（见 providers/*.py 的 `@records_usage`）：
    测试里的 FakeClient 直接构造、不经过这里，不会往真实账本写垃圾行。

    记账失败只累加 `usage_record_stats()` 的计数，**不影响返回值、不抛异常** ——
    "成本模块崩了导致 LLM 调用失败"是不能接受的失败模式。
    """
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        response = method(self, *args, **kwargs)
        global _USAGE_RECORD_FAILURES, _USAGE_RECORD_LAST_ERROR
        try:
            if isinstance(response, LLMResponse) and not response.failed:
                _record_usage(self, response)
        except Exception as exc:      # 记账故障绝不上抛
            _USAGE_RECORD_FAILURES += 1
            _USAGE_RECORD_LAST_ERROR = '%s: %s' % (type(exc).__name__, exc)
        return response

    return wrapper