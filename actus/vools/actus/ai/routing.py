"""routing.py —— 路由增强三层：laya 判断路由 / 性价比选型 / 备用切换。

每个增强项默认关闭（零回归），需显式启用。
"""

__all__ = [
    'RankedCandidate', 'layarank_by_complexity',
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

def layarank_by_complexity(client, intent, candidates, timeout_sec=3.0):
    if not candidates or not intent.strip(): return []
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
    except Exception: return []
    if time.time() - start > timeout_sec: return []
    if resp is None or resp.failed: return []
    return _parse_laya_response(resp.content, candidates)

def _parse_laya_response(text, candidates):
    raw = str(text or "").strip()
    if not raw: return []
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw[3:]
        if raw.lower().startswith("json"): raw = raw[4:]
        raw = raw.strip().strip("`").strip()
    try: items = json.loads(raw)
    except ValueError: return []
    if not isinstance(items, list): return []
    aids = {e.action_id for e in candidates}; result = []
    for item in items:
        if not isinstance(item, dict): continue
        aid = str(item.get("action_id") or "")
        if aid not in aids: continue
        adj = max(-0.3, min(0.3, float(item.get("adjustment", 0.0))))
        entry = next((e for e in candidates if e.action_id == aid), None)
        if entry is None: continue
        result.append(RankedCandidate(action_id=aid, tool_name=entry.tool_name,
            base_confidence=0.5, laya_boost=adj,
            final_confidence=max(0.0, min(1.0, 0.5+adj)),
            reason=str(item.get("reason",""))[:200]))
    return result

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
