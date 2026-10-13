"""任务拆解。

存在的理由很具体：Actus 的 `selfdrive.Decomposer` 拆解计划是
`selfdrive.py:50-54` 里三条**硬编码模板**（澄清 / 实现 / 补测试），
零语义理解。本模块是那个 `planner: Callable[[str, int], List[str]]`
插槽的正式化 —— 下游只需传 `LlmPlanner` 即可替换。

**接线说明（本期不做，属 Actus 仓库的事）**：

    from vools.actus.ai import LlmPlanner, get_provider
    from vools.actus import selfdrive

    planner = LlmPlanner(get_provider('deepseek'))
    selfdrive.Decomposer(planner=planner.decompose).decompose(goal)

拆解结果里的 `verify` 字段留给下游的 Ω 门消费
（Actus 侧 `omega.verify_output`）—— 本模块只负责**产出判据**，
不做判定。判定该不该由 LLM 做，参见 FIST-MBT `ARCHITECTURE.md:77`
「绝不让 LLM 自评」。

Example:
    >>> class _Fake(LLMClient):
    ...     name = 'fake'
    ...     def complete(self, messages, tools=None, temperature=0.0,
    ...                  max_tokens=None, stream=False):
    ...         return LLMResponse(content='{}')
    ...     def available(self): return True
    >>> LlmPlanner(_Fake()).decompose('x').steps
    ()
"""

__all__ = ['Planner', 'LlmPlanner', 'Plan', 'PlanStep', 'plan_from_intent']

import json

from vools.core.dataclass_compat import dataclass, field

from .base import Message, LLMClient, llm_error_code
from .catalog import build_catalog

_SYSTEM_PROMPT = (
    '你是任务拆解器。把一个目标拆成可独立执行、可验证的步骤。\n'
    '\n'
    '规则：\n'
    '1. 每步只做一件事，且必须能被独立验证。\n'
    '2. 按依赖顺序排列：被依赖的在前。\n'
    '3. target_action 只能从给定动作清单里选；确实不需要动作的步骤留空。\n'
    '4. verify 写清「怎么知道这步做完了」，要具体到可观察的现象。\n'
    '5. 步数不超过给定上限。\n'
    '\n'
    '只返回 JSON 对象：\n'
    '{"steps": [{"id": str, "title": str, "target_action": str, '
    '"arguments": object, "verify": str}]}\n'
    '不要求严格遵守字段顺序，但每个 step 必须有 id 与 title。'
)


@dataclass(frozen=True)
class PlanStep(object):
    """一步。

    Attributes:
        id: 步骤标识（同一份计划内唯一）。
        title: 一句话说明这步做什么。
        target_action: 对应的动作 id；空串表示纯推理/纯文本产出。
        arguments: 该步预填的参数。
        verify: 完成判据，供下游 Ω 门消费。
    """

    id: str
    title: str = ''
    target_action: str = ''
    arguments: dict = field(default_factory=dict)
    verify: str = ''


@dataclass(frozen=True)
class Plan(object):
    """一份拆解结果。

    Attributes:
        goal: 原始目标。
        steps: 步骤序列。
        source: 拆解来源 —— 'llm' / 'template' / 'caller'。
        error: 失败原因（成功时为空串）。
    """

    goal: str = ''
    steps: tuple = ()
    source: str = 'llm'
    error: str = ''


class Planner(object):
    """拆解器协议。

    只需实现 `decompose`。Actus 的 `selfdrive.Decomposer` 已预留
    同形状的 `planner=` 插槽，本类是其正式化。
    """

    def decompose(self, goal, max_steps=8):
        """把目标拆成步骤。

        Args:
            goal: 目标描述。
            max_steps: 最多拆几步。

        Returns:
            Plan: 拆解结果；失败时 steps 为空且 error 非空。
        """
        raise NotImplementedError('%s 未实现 decompose()' % type(self).__name__)


class LlmPlanner(Planner):
    """用 LLM 做任务拆解。

    Attributes:
        catalog: 可选动作清单来源（None 则惰性构建）。
        max_steps: 默认步数上限。

    Example:
        >>> LlmPlanner(_Fake()).max_steps
        8
    """

    def __init__(self, client, catalog=None, max_steps=8):
        """构造拆解器。

        Args:
            client: LLMClient 实例。
            catalog: ToolCatalog；None 时惰性构建（用于给模型动作清单）。
            max_steps: 默认步数上限。
        """
        self.client = client
        self.catalog = catalog
        self.max_steps = int(max_steps)

    def _catalog(self):
        """ToolCatalog: 取动作清单。"""
        if self.catalog is None:
            self.catalog = build_catalog()
        return self.catalog

    def decompose(self, goal, max_steps=None):
        """把目标拆成可验证的步骤。

        Args:
            goal: 目标描述。
            max_steps: 步数上限；None 用构造时的值。

        Returns:
            Plan: 拆解结果。模型不可用或输出不可解析时，error 给出原因
            且 steps 为空 —— **不做「猜一个计划」的兜底**，因为
            错误的计划比没有计划更贵（下游会照着执行）。
        """
        limit = int(max_steps or self.max_steps)
        goal = str(goal or '').strip()
        if not goal:
            return Plan(goal='', steps=(), source='llm', error='goal_empty')

        if self.client is None or not self.client.available():
            return Plan(goal=goal, steps=(), source='llm',
                        error='llm 不可用（密钥缺失或端点不可达）')

        known = self._catalog().action_ids()
        prompt = ('目标：%s\n\n步数上限：%d\n\n可用动作 id：\n%s\n\n'
                  '只返回 JSON 对象 {\"steps\": [...]}。'
                  % (goal, limit, '\n'.join(known) if known else '（动作清单为空）'))

        resp = self.client.complete(
            [Message(role='system', content=_SYSTEM_PROMPT),
             Message(role='user', content=prompt)], temperature=0.2)

        if resp is None or resp.failed:
            detail = getattr(resp, 'content', '') if resp is not None else ''
            code = (getattr(resp, 'raw', {}) or {}).get('code',
                                                        llm_error_code('bad_response'))
            return Plan(goal=goal, steps=(), source='llm',
                        error='模型调用失败（%s）：%s' % (code, detail or '未知'))

        steps = self._parse_steps(resp.content, known, limit)
        if not steps:
            return Plan(goal=goal, steps=(), source='llm',
                        error='模型未给出可解析的步骤')
        return Plan(goal=goal, steps=tuple(steps), source='llm')

    @staticmethod
    def _parse_steps(text, known_actions, limit):
        """从模型回复里解析步骤，过滤掉指向未知动作的 target_action。

        未知动作不整步丢弃 —— 步骤本身可能仍然有效（只是没有对应工具，
        需要人工介入），把 target_action 清空并保留 title 更实用。

        Args:
            text: 模型回复原文。
            known_actions: 合法动作 id 集合。
            limit: 步数上限。

        Returns:
            List[PlanStep]: 解析出的步骤（可能为空）。
        """
        raw = str(text or '').strip()
        if not raw:
            return []
        if raw.startswith('```'):
            parts = raw.split('```')
            raw = parts[1] if len(parts) > 1 else raw[3:]
            if raw.lower().startswith('json'):
                raw = raw[4:]
            raw = raw.strip().strip('`').strip()
        start, end = raw.find('{'), raw.rfind('}')
        if start < 0 or end <= start:
            return []
        try:
            data = json.loads(raw[start:end + 1])
        except ValueError:
            return []
        items = data.get('steps') if isinstance(data, dict) else None
        if not isinstance(items, list):
            return []

        known = set(known_actions or ())
        out = []
        for i, item in enumerate(items[:limit], 1):
            if not isinstance(item, dict):
                continue
            sid = str(item.get('id') or '').strip() or ('step%d' % i)
            title = str(item.get('title') or '').strip()
            if not title:
                continue
            action = str(item.get('target_action') or '').strip()
            if action and known and action not in known:
                action = ''          # 模型编造的动作 id：清空但保留这一步
            args = item.get('arguments')
            out.append(PlanStep(id=sid, title=title, target_action=action,
                                arguments=args if isinstance(args, dict) else {},
                                verify=str(item.get('verify') or '')))
        return out


def plan_from_intent(goal, client=None, catalog=None, max_steps=8):
    """便捷函数：等价于 `LlmPlanner(client, catalog).decompose(goal)`。

    Args:
        goal: 目标描述。
        client: LLMClient 实例；None 时按环境变量选 provider（失败则返回带 error 的 Plan）。
        catalog: 可选 ToolCatalog。
        max_steps: 步数上限。

    Returns:
        Plan: 拆解结果。

    Example:
        >>> plan_from_intent('').error
        'goal_empty'
    """
    # 先校验目标再去找 provider —— 空目标是调用方的错，
    # 不该被「provider 不可用」掩盖掉
    if not str(goal or '').strip():
        return Plan(goal='', steps=(), source='llm', error='goal_empty')
    if client is None:
        try:
            from .registry import get_provider
            client = get_provider('openai')
        except Exception as e:
            return Plan(goal=str(goal or ''), steps=(), source='llm',
                        error='无可用 provider: %s' % e)
    return LlmPlanner(client, catalog, max_steps).decompose(goal)