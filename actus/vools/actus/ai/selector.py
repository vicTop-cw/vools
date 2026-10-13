"""意图 → 动作 + 参数填充。

这是 Actus 最该有、却一直没有的一层：现有五套并行打分器
（`intent.IntentRouter`、`__main__.graph._graph_query`、
`registry.recommend`、`registry.search_registry`、`actus search`）
全是关键词子串匹配，零语义，且互相不知道对方存在。
`IntentRouter` 的关键词表只覆盖 12 个动作，而市场有 109 个。

两个安全边界都在这里，**不许为了「聪明」而放松**：

1. **候选集有上限**。先把全部工具塞进 prompt 既贵又会稀释注意力，
   所以先用 `catalog.grep()` 粗筛再交给模型。
2. **模型给的 action_id 必须回查目录**。模型会编造不存在的动作 id ——
   当成有效选择返回，等于把「调用不存在的东西」这件事说成了真的。

Example:
    >>> class _Fake(LLMClient):
    ...     name = 'fake'
    ...     def complete(self, messages, tools=None, temperature=0.0,
    ...                  max_tokens=None, stream=False):
    ...         return LLMResponse(content='{}')
    ...     def available(self): return True
    >>> Selector(_Fake(), ToolCatalog(())).select('随便').tool_name
    ''
"""

__all__ = ['Selector', 'Selection', 'validate_params']

import json

from vools.core.dataclass_compat import dataclass, field

from .base import Message, LLMClient, ToolSpec

_SYSTEM_PROMPT = (
    '你是 Actus 动作选择器。Actus 是一个动作执行平台，每个动作是一个工具。'
    '你的任务：根据用户的意图，从给定工具里选出**唯一一个**最适合的，'
    '并按该工具的 parameters schema 填好参数。\n'
    '\n'
    '规则：\n'
    '1. 只能从给定工具里选，**绝对不要编造不存在的工具名**。\n'
    '2. 没有合适工具时返回 {"action_id": "", "confidence": 0}。\n'
    '3. confidence 用 0..1 的小数：非常有把握给 0.9 以上，'
    '只是勉强匹配给 0.3 以下，不确定要给低分。\n'
    '4. 只返回一个 JSON 对象，不要 markdown 代码块、不要解释文字。\n'
    '\n'
    '输出格式：{"action_id": str, "arguments": object, '
    '"confidence": number, "reason": str}'
)


@dataclass(frozen=True)
class Selection(object):
    """一次选择结果。

    Attributes:
        tool_name: 命中的工具名；空串表示没选出来。
        action_id: 命中的动作 id。
        arguments: 校验并清洗后的参数。
        confidence: 模型自评置信度 0..1。
        candidates: 备选条目摘要。置信度低或没选出来时非空，供调用方让用户挑。
        reason: 选/不选的理由（面向人）。
        needs_confirm: 需要人工确认。命中 audit 级动作、或置信度低于阈值时为 True。
        missing_args: 必填但模型没给的参数名。
        error: 失败原因描述（成功时为空串）。

    Example:
        >>> Selection(tool_name='cli_jq', confidence=0.9).found
        True
    """

    tool_name: str = ''
    action_id: str = ''
    arguments: dict = field(default_factory=dict)
    confidence: float = 0.0
    candidates: tuple = ()
    reason: str = ''
    needs_confirm: bool = False
    missing_args: tuple = ()
    error: str = ''

    @property
    def found(self):
        """bool: 是否选出了可执行的动作。"""
        return bool(self.action_id and self.tool_name)


def validate_params(schema, params):
    """按 draft-07 子集校验参数。**不引第三方依赖**（jsonschema 太重）。

    覆盖：type（string/integer/number/boolean/object/array）、
    required、enum、minimum/maximum、default 补齐。

    明确**不覆盖**：oneOf/anyOf/allOf/$ref/format ——
    动作 schema 里用到这些时本函数只做 required + 类型检查，
    真正的校验仍由 `validate.validate_action` 与执行期负责。

    Args:
        schema: 动作的 args JSON Schema。
        params: 待校验的参数字典。

    Returns:
        tuple: (cleaned, missing, errors)
        - cleaned: 丢弃未知属性、补默认值后的参数副本
        - missing: 必填但缺失的参数名元组
        - errors: 类型/enum/取值范围问题的描述列表

    Example:
        >>> sc = {'type': 'object', 'required': ['a'],
        ...       'properties': {'a': {'type': 'string'}}}
        >>> cleaned, missing, errs = validate_params(sc, {'a': 1, 'z': 9})
        >>> missing, errs[0][:12]
        ((), '参数 a 期望 st')
    """
    schema = schema if isinstance(schema, dict) else {}
    raw_props = schema.get('properties')
    props = raw_props if isinstance(raw_props, dict) else {}
    required = tuple(schema.get('required') or ())
    allow_extra = schema.get('additionalProperties', False) is not False

    params = params if isinstance(params, dict) else {}
    cleaned = {}
    errors = []

    for key, value in params.items():
        if key in props or allow_extra:
            cleaned[key] = value

    for name, spec in props.items():
        if isinstance(spec, dict) and 'default' in spec and name not in cleaned:
            cleaned[name] = spec['default']

    missing = tuple(n for n in required if n not in cleaned)

    types = {'string': str, 'integer': int, 'number': (int, float),
             'boolean': bool, 'object': dict, 'array': list}
    for key, value in list(cleaned.items()):
        spec = props.get(key)
        if not isinstance(spec, dict):
            continue
        want = spec.get('type')
        # bool 是 int 的子类，Python 上 isinstance(True, int) 为真，
        # 所以数值类型要显式排除 bool，否则布尔会被当成整数放行
        if want in types:
            if want in ('integer', 'number') and isinstance(value, bool):
                errors.append('参数 %s 期望 %s，得到 boolean' % (key, want))
            elif not isinstance(value, types[want]):
                errors.append('参数 %s 期望 %s' % (key, want))
        if 'enum' in spec and isinstance(spec['enum'], list) and value not in spec['enum']:
            errors.append('参数 %s 取值必须在 %s 内' % (key, spec['enum']))
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if 'minimum' in spec and value < spec['minimum']:
                errors.append('参数 %s 不得小于 %s' % (key, spec['minimum']))
            if 'maximum' in spec and value > spec['maximum']:
                errors.append('参数 %s 不得大于 %s' % (key, spec['maximum']))

    return cleaned, missing, errors


class Selector(object):
    """用 LLM 把自然语言意图映射到「哪个动作 + 参数填什么」。

    Attributes:
        max_candidates: 送给 LLM 的候选集上限。
        threshold: 低于此置信度视为不确定，返回 needs_confirm=True。
        catalog: 可选的工具目录（None 则惰性载入）。

    Example:
        >>> Selector(_Fake(), ToolCatalog(()), max_candidates=5).max_candidates
        5
    """

    def __init__(self, client, catalog=None, max_candidates=24, threshold=0.25):
        """构造选择器。

        Args:
            client: LLMClient 实例。
            catalog: ToolCatalog；None 时惰性调 load_catalog()。
            max_candidates: 候选集上限。
            threshold: 置信度阈值，低于它 needs_confirm=True。
        """
        self.client = client
        self.catalog = catalog
        self.max_candidates = int(max_candidates)
        self.threshold = float(threshold)

    def _cat(self):
        """ToolCatalog: 取目录，未注入则惰性载入。"""
        if self.catalog is None:
            from .catalog import load_catalog
            self.catalog = load_catalog()
        return self.catalog

    def _candidates(self, intent):
        """粗筛候选集。

        先用 grep 命中优先；命中不足时用全目录前 N 条补齐 ——
        保证「描述里没出现动作关键词」的情况也能有候选。

        Args:
            intent: 自然语言意图。

        Returns:
            List[CatalogEntry]: 最多 max_candidates 条。
        """
        cat = self._cat()
        picked = cat.grep(intent, limit=self.max_candidates)
        if len(picked) >= self.max_candidates:
            return picked
        seen = set(e.tool_name for e in picked)
        for e in cat:
            if len(picked) >= self.max_candidates:
                break
            if e.tool_name not in seen:
                picked.append(e)
                seen.add(e.tool_name)
        return picked

    @staticmethod
    def _briefs(entries):
        """候选动作的紧凑清单（给 prompt 用，不塞完整 description）。

        Args:
            entries: 候选条目。

        Returns:
            list: 可 JSON 序列化的清单。
        """
        out = []
        for e in entries:
            spec = e.parameters if isinstance(e.parameters, dict) else {}
            raw_props = spec.get('properties')
            props = raw_props if isinstance(raw_props, dict) else {}
            brief_props = {}
            for name, s in props.items():
                if not isinstance(s, dict):
                    continue
                item = {'type': s.get('type', 'string')}
                if 'description' in s:
                    item['description'] = str(s['description'])[:80]
                if 'enum' in s:
                    item['enum'] = s['enum']
                if 'default' in s:
                    item['default'] = s['default']
                brief_props[name] = item
            out.append({
                'tool_name': e.tool_name,
                'action_id': e.action_id,
                'description': (e.description or '')[:200],
                'parameters': {'type': 'object',
                               'properties': brief_props,
                               'required': list(spec.get('required') or [])},
            })
        return out

    @staticmethod
    def _parse_payload(text):
        """从模型回复里抠出 JSON 对象。

        模型常把 JSON 包在 ```json 代码块里，所以要容忍围栏。

        Args:
            text: 原始文本。

        Returns:
            dict: 解析结果；失败返回 {}。
        """
        raw = str(text or '').strip()
        if not raw:
            return {}
        if raw.startswith('```'):
            parts = raw.split('```')
            raw = parts[1] if len(parts) > 1 else raw[3:]
            if raw.lower().startswith('json'):
                raw = raw[4:]
            raw = raw.strip().strip('`').strip()
        start, end = raw.find('{'), raw.rfind('}')
        if start < 0 or end <= start:
            return {}
        try:
            data = json.loads(raw[start:end + 1])
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    def _cand_briefs(self, entries):
        """候选摘要元组。

        Args:
            entries: 候选条目。

        Returns:
            tuple: 可 JSON 序列化的候选摘要。
        """
        return tuple({'action_id': e.action_id, 'tool_name': e.tool_name,
                      'description': (e.description or '')[:120]} for e in entries)

    def select(self, intent, context=''):
        """把意图映射到动作与参数。

        Args:
            intent: 自然语言意图。
            context: 补充上下文（当前选中文本、目录清单等）。

        Returns:
            Selection: 选择结果。失败时 action_id 为空且 error 说明原因。
        """
        entries = self._candidates(intent)
        if not entries:
            return Selection(reason='动作目录为空，无法选择。', error='catalog_empty')

        tools = [ToolSpec(name=e.tool_name, description=(e.description or '')[:200],
                          parameters=e.parameters, action_id=e.action_id,
                          trust=e.trust, permissions=e.permissions)
                 for e in entries]
        prompt = '用户意图：%s' % intent
        if context:
            prompt += '\n补充上下文：%s' % context
        prompt += '\n\n可用工具：\n%s' % json.dumps(
            self._briefs(entries), ensure_ascii=False, indent=2)

        resp = self.client.complete(
            [Message(role='system', content=_SYSTEM_PROMPT),
             Message(role='user', content=prompt)],
            tools=tools, temperature=0.0)

        if resp is None or resp.failed:
            detail = getattr(resp, 'content', '') if resp is not None else ''
            return Selection(
                reason='模型调用失败：%s' % (detail or '未知原因'),
                error='llm_failed', needs_confirm=True,
                candidates=self._cand_briefs(entries))

        data = {}
        if getattr(resp, 'tool_calls', ()):
            # function-calling 模式：取第一个 tool_call 的参数
            call = resp.tool_calls[0]
            entry = next((e for e in entries if e.tool_name == call.name), None)
            if entry is None:
                return self._reject_hallucination(call.name, entries, intent)
            data = {'action_id': entry.action_id, 'arguments': call.arguments,
                    'confidence': 0.8,
                    'reason': '模型通过 function-calling 选定'}
        else:
            data = self._parse_payload(resp.content)

        action_id = str(data.get('action_id') or '').strip()
        if not action_id:
            return Selection(reason=str(data.get('reason') or '模型未选出动作。'),
                             error='no_match', needs_confirm=True,
                             candidates=self._cand_briefs(entries))

        entry = next((e for e in entries if e.action_id == action_id), None)
        if entry is None:
            return self._reject_hallucination(action_id, entries, intent)

        raw_args = data.get('arguments')
        cleaned, missing, errs = validate_params(
            entry.parameters, raw_args if isinstance(raw_args, dict) else {})

        try:
            confidence = float(data.get('confidence', 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))

        reason = data.get('reason')
        parts = [reason] if isinstance(reason, str) and reason else []
        parts.extend(errs)
        if missing:
            parts.append('缺少必填参数：%s' % ', '.join(missing))

        needs_confirm = entry.trust == 'audit' or confidence < self.threshold
        candidates = ()
        if confidence < self.threshold:
            candidates = tuple({'action_id': e.action_id,
                                'tool_name': e.tool_name,
                                'description': (e.description or '')[:120]}
                               for e in entries if e.action_id != entry.action_id)

        return Selection(tool_name=entry.tool_name, action_id=entry.action_id,
                         arguments=cleaned, confidence=confidence,
                         candidates=candidates,
                         reason='；'.join([p for p in parts if p]),
                         needs_confirm=needs_confirm, missing_args=missing,
                         error='param_mismatch' if errs else '')

    def _reject_hallucination(self, name, entries, intent):
        """模型给了目录外的东西 —— 降级为候选，不当作有效选择。

        Args:
            name: 模型给出的 action_id 或 tool_name。
            entries: 候选条目。
            intent: 原意图（用于报错信息）。

        Returns:
            Selection: tool_name 为空、error='hallucinated' 的结果。
        """
        return Selection(
            reason='模型给出了目录外的动作 %r（意图：%s），已拒绝并降级为候选。'
                   % (name, str(intent)[:60]),
            error='hallucinated', needs_confirm=True,
            candidates=self._cand_briefs(entries))

    def fill_args(self, action_id, hint):
        """已知动作、只填参数。

        Args:
            action_id: 动作 id。
            hint: 描述参数取值的意图片段。

        Returns:
            dict: 校验清洗后的参数。动作不在目录里时返回 {}。
        """
        entry = self._cat().find_by_action(action_id)
        if entry is None:
            return {}
        brief = self._briefs([entry])[0]
        prompt = ('请为动作 %s 填充调用参数。\n取值说明：%s\n\n'
                  '参数 schema：\n%s\n\n'
                  '只返回 {"arguments": {...}} 这个 JSON 对象。'
                  % (action_id, str(hint or ''),
                     json.dumps(brief['parameters'], ensure_ascii=False, indent=2)))
        resp = self.client.complete(
            [Message(role='system', content=_SYSTEM_PROMPT),
             Message(role='user', content=prompt)], temperature=0.0)
        if resp is None or resp.failed:
            return {}
        data = self._parse_payload(resp.content)
        args = data.get('arguments')
        if not isinstance(args, dict):
            args = {k: v for k, v in data.items() if k != 'confidence'}
        cleaned, _, _ = validate_params(entry.parameters, args)
        return cleaned