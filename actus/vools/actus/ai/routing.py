"""routing.py —— 路由增强三层：laya 判断路由 / 性价比选型 / 备用切换。

每个增强项默认关闭（零回归），需显式启用。
"""

__all__ = [
    'RankedCandidate', 'layarank_by_complexity', 'last_layarank_error',
    'LAYARANK_ERR_CALL', 'LAYARANK_ERR_TIMEOUT', 'LAYARANK_ERR_LLM',
    'LAYARANK_ERR_EMPTY', 'LAYARANK_ERR_BAD_JSON', 'LAYARANK_ERR_NOT_LIST',
    'LAYARANK_ERR_BAD_ITEM',
    'cost_performance_score', 'sort_by_cost_perf', 'PROVIDER_COST_PERF',
    'FallbackChain', 'FallbackEntry',
    'retry_with_fallback', 'compute_fallback_chain',
]

import json, os, time
from typing import Callable, List, Optional, Tuple
from .base import LLMClient, LLMResponse, Message
from .catalog import CatalogEntry
from ..errors import ActionError, ERROR_CODES
from vools.core.dataclass_compat import dataclass, field

@dataclass(frozen=True)
class RankedCandidate(object):
    action_id: str; tool_name: str; base_confidence: float
    laya_boost: float; final_confidence: float; reason: str

# Laya 重排序最近一次失败/降级的分型原因（'' = 正常）。
# 改前 `except Exception: return []` 把三种完全不同的情况混成同一个空列表：
#   ① LLM 调用崩了  ② LLM 超时  ③ LLM 正常返回「不需要调整」
# 调用方无法区分 → 排序静默退化成不排序，排障时零信号（与 probe 侧已修的
# 「静默吞异常」同一族）。现在：返回仍兼容（默认仍是 list），但另给分型原因。
_LAST_LAYARANK_ERROR = ''

# 分型常量（写进 last_layarank_error()，便于调用方按类型分支）
LAYARANK_ERR_CALL = 'call_error'        # client.complete 抛异常
LAYARANK_ERR_TIMEOUT = 'timeout'        # 超过 timeout_sec
LAYARANK_ERR_LLM = 'llm_error'          # 响应本身是失败（auth/quota/unreachable…）
LAYARANK_ERR_EMPTY = 'empty_response'   # 响应成功但内容为空
LAYARANK_ERR_BAD_JSON = 'bad_json'      # 内容不是合法 JSON
LAYARANK_ERR_NOT_LIST = 'not_a_list'    # JSON 合法但不是数组
LAYARANK_ERR_BAD_ITEM = 'bad_item'      # 数组里逐项的 adjustment 不是数字


def last_layarank_error():
    """最近一次 `layarank_by_complexity()` 的失败/降级分型。

    Returns:
        str: '' 表示正常（真的拿到排序结果，或输入为空无需调用）；
        否则是 LAYARANK_ERR_* 之一，带简短上下文，如
        `'call_error:TimeoutError: timed out'`、`'llm_error:quota'`。

    为什么需要：改前调用方只看到 `[]`，无法分辨「LLM 说不用调整」与
    「LLM 挂了」——前者可以继续，后者必须降级告警。
    """
    return _LAST_LAYARANK_ERROR


def layarank_by_complexity(client, intent, candidates, timeout_sec=3.0,
                           with_error=False):
    """用 LLM 评估候选复杂度并给出置信度调整。

    Args:
        with_error: False（默认，向后兼容）返回 list；True 返回
            `(adjustments, error)`，`error` 为 '' 或 LAYARANK_ERR_* 分型串。
            无论哪种形态，最近一次原因都可通过 `last_layarank_error()` 读取。

    Returns:
        List[RankedCandidate] 或 (List[RankedCandidate], str)。
    """
    adjustments, error = _layarank_impl(client, intent, candidates, timeout_sec)
    if with_error:
        return adjustments, error
    return adjustments


def _layarank_impl(client, intent, candidates, timeout_sec):
    """内部实现，恒返回 (adjustments, error)。"""
    global _LAST_LAYARANK_ERROR
    if not candidates or not intent.strip():
        # 输入为空不是错误：没有候选就没有可调整的对象
        _LAST_LAYARANK_ERROR = ''
        return [], ''
    brief = [{"action_id": e.action_id, "tool_name": e.tool_name,
              "description": (e.description or "")[:200]} for e in candidates]
    prompt = ("你是 Actus 路由复杂度评估器。用户意图：%s\n候选：%s\n"
              "请评估每条候选的复杂度并给出 adjustment(-0.3~+0.3)和理由。"
              "只返回 JSON 数组，不要代码块。"
              "[{\"action_id\": str, \"adjustment\": float, \"reason\": str}]" 
              % (str(intent)[:200], json.dumps(brief, ensure_ascii=False)))
    start = time.time()
    try:
        resp = client.complete([Message(role="user", content=prompt)], temperature=0.3, max_tokens=500)
    except Exception as exc:
        _LAST_LAYARANK_ERROR = '%s:%s: %s' % (
            LAYARANK_ERR_CALL, type(exc).__name__, str(exc)[:120])
        return [], _LAST_LAYARANK_ERROR
    elapsed = time.time() - start
    if elapsed > timeout_sec:
        _LAST_LAYARANK_ERROR = '%s(%.2fs > %.2fs)' % (
            LAYARANK_ERR_TIMEOUT, elapsed, timeout_sec)
        return [], _LAST_LAYARANK_ERROR
    if resp is None:
        _LAST_LAYARANK_ERROR = '%s:no-response' % LAYARANK_ERR_LLM
        return [], _LAST_LAYARANK_ERROR
    if resp.failed:
        kind = ''
        try:
            kind = (resp.raw or {}).get('error_kind', '') or ''
        except AttributeError:
            kind = ''
        _LAST_LAYARANK_ERROR = '%s:%s' % (LAYARANK_ERR_LLM, kind or 'failed')
        return [], _LAST_LAYARANK_ERROR
    result, error = _parse_laya_response(resp.content, candidates)
    _LAST_LAYARANK_ERROR = error
    return result, error


def _parse_laya_response(text, candidates):
    """解析 LLM 返回；返回 (adjustments, error)。"""
    raw = str(text or "").strip()
    if not raw:
        return [], LAYARANK_ERR_EMPTY
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw[3:]
        if raw.lower().startswith("json"): raw = raw[4:]
        raw = raw.strip().strip("`").strip()
    try: items = json.loads(raw)
    except ValueError as exc:
        return [], '%s: %s' % (LAYARANK_ERR_BAD_JSON, str(exc)[:80])
    if not isinstance(items, list):
        return [], '%s: %s' % (LAYARANK_ERR_NOT_LIST, type(items).__name__)
    aids = {e.action_id for e in candidates}; result = []
    bad_items = 0
    for item in items:
        if not isinstance(item, dict): continue
        aid = str(item.get("action_id") or "")
        if aid not in aids: continue
        try:
            adj = float(item.get("adjustment", 0.0))
        except (TypeError, ValueError):
            bad_items += 1
            continue
        adj = max(-0.3, min(0.3, adj))
        entry = next((e for e in candidates if e.action_id == aid), None)
        if entry is None: continue
        result.append(RankedCandidate(action_id=aid, tool_name=entry.tool_name,
            base_confidence=0.5, laya_boost=adj,
            final_confidence=max(0.0, min(1.0, 0.5+adj)),
            reason=str(item.get("reason",""))[:200]))
    if bad_items:
        return result, '%s: %d item(s) 的 adjustment 不是数字（已跳过）' % (
            LAYARANK_ERR_BAD_ITEM, bad_items)
    return result, ''

PROVIDER_COST_PERF = {
    "openai": {"gpt-4o": {"price_per_1k": 0.005, "rank": 9},
        "gpt-4o-mini": {"price_per_1k": 0.0005, "rank": 7}},
    "deepseek": {"deepseek-chat": {"price_per_1k": 0.0003, "rank": 6}},
    "groq": {"llama-3.1-8b": {"price_per_1k": 0.0, "rank": 4}},
    "ollama": {"qwen2.5-coder": {"price_per_1k": 0.0, "rank": 5}},
    "anthropic": {"claude-3-5-sonnet-latest": {"price_per_1k": 0.003, "rank": 9}},
}

@dataclass(frozen=True)
class FallbackEntry(object):
    provider: str; model: str; success: bool = True; error: str = ""

class FallbackChain(object):
    def __init__(self, fail_threshold=3, cooldown_secs=60, max_retries=1):
        self.fail_threshold = fail_threshold; self.cooldown_secs = cooldown_secs
        self.max_retries = max_retries; self._fail_counts = {}; self._cooldowns = {}
    def record_failure(self, provider, model):
        key = "%s:%s" % (provider, model); c = self._fail_counts.get(key, 0) + 1
        self._fail_counts[key] = c
        if c >= self.fail_threshold: self._cooldowns[key] = time.time() + self.cooldown_secs
    def record_success(self, provider, model):
        key = "%s:%s" % (provider, model)
        self._fail_counts.pop(key, None); self._cooldowns.pop(key, None)
    def is_cooling(self, provider, model):
        key = "%s:%s" % (provider, model); end = self._cooldowns.get(key, 0)
        if end == 0: return False
        if time.time() > end: self._cooldowns.pop(key, None); self._fail_counts.pop(key, None); return False
        return True

def compute_fallback_chain(primary_provider, primary_model, all_providers, unhealthy_ids=None, fallback=None):
    primary_key = "%s:%s" % (primary_provider, primary_model)
    unhealthy = set(unhealthy_ids or [])
    if fallback:
        for p, m, _ in all_providers:
            if fallback.is_cooling(p, m): unhealthy.add("%s:%s" % (p, m))
    return [(p, m) for p, m, _ in all_providers 
            if "%s:%s" % (p, m) != primary_key and "%s:%s" % (p, m) not in unhealthy]

def retry_with_fallback(caller, primary_provider, primary_model, fallback_chain=None, fallback=None, max_retries=1, **kwargs):
    if fallback_chain is None: fallback_chain = []
    attempts = []; remaining = list(fallback_chain)
    for _ in range(max_retries + 1):
        ok, r = caller(primary_provider, primary_model, **kwargs)
        attempts.append(FallbackEntry(provider=primary_provider, model=primary_model, success=ok, error=str(r) if not ok else ""))
        if fallback:
            if ok: fallback.record_success(primary_provider, primary_model); return (True, r, attempts)
            else: fallback.record_failure(primary_provider, primary_model)
        if ok: return (True, r, attempts)
    for ap, am in remaining:
        ok, r = caller(ap, am, **kwargs)
        attempts.append(FallbackEntry(provider=ap, model=am, success=ok, error=str(r) if not ok else ""))
        if fallback:
            if ok: fallback.record_success(ap, am); return (True, r, attempts)
            else: fallback.record_failure(ap, am)
        if ok: return (True, r, attempts)
    return (False, None, attempts)


PROVIDER_COST_PERF = {
    "openai": {
        "gpt-4o": {"price_per_1k": 0.005, "rank": 9},
        "gpt-4o-mini": {"price_per_1k": 0.0005, "rank": 7},
    },
    "deepseek": {
        "deepseek-chat": {"price_per_1k": 0.0003, "rank": 6},
    },
    "groq": {
        "llama-3.1-8b": {"price_per_1k": 0.0, "rank": 4},
    },
    "ollama": {
        "qwen2.5-coder": {"price_per_1k": 0.0, "rank": 5},
    },
    "anthropic": {
        "claude-3-5-sonnet-latest": {"price_per_1k": 0.003, "rank": 9},
    },
}


def cost_performance_score(provider, model="", price=0.0, rank=0):
    if provider in PROVIDER_COST_PERF and model:
        known = PROVIDER_COST_PERF[provider].get(model)
        if known:
            if price <= 0:
                price = known["price_per_1k"]
            if rank <= 0:
                rank = known["rank"]
    elif provider in PROVIDER_COST_PERF and not model:
        models = PROVIDER_COST_PERF[provider]
        if models:
            avg_price = sum(m["price_per_1k"] for m in models.values()) / len(models)
            avg_rank = sum(m["rank"] for m in models.values()) / len(models)
            if price <= 0:
                price = avg_price
            if rank <= 0:
                rank = int(avg_rank)
    if price > 0 and rank > 0:
        score = rank / price
    elif rank > 0:
        score = float(rank)
    else:
        score = 0.0
    return (score, price, rank)


def sort_by_cost_perf(candidates, provider="", tier="free"):
    def _score(e):
        sc, _, _ = cost_performance_score(provider, e.tool_name)
        return sc
    scored = [(e, _score(e)) for e in candidates]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [e for e, _ in scored]
