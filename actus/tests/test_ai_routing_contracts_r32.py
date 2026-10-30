"""ai/routing 契约测试（第 32 批，直接由 Lead 编写）。

退步了会怎样：
- _parse_laya_response 解析错误 → LLM 排序结果丢失，降级路径失效
- FallbackChain 冷却逻辑错误 → 不健康的 provider 被反复调用
- compute_fallback_chain 过滤错误 → 主 provider 被包含或健康 provider 被排除
- cost_performance_score 计算错误 → 路由排序失效
"""
import pytest


class TestParseLayaResponse:
    def test_empty_response(self):
        """退步了会怎样：空响应应返回 empty_response 错误。"""
        from vools.actus.ai.routing import _parse_laya_response, LAYARANK_ERR_EMPTY
        result, err = _parse_laya_response("", [])
        assert result == []
        assert err == LAYARANK_ERR_EMPTY

    def test_code_block_response(self):
        """退步了会怎样：代码块包裹的 JSON 应能正确解析。"""
        from vools.actus.ai.routing import _parse_laya_response, RankedCandidate
        text = '```json\n[{"action_id": "a1", "adjustment": 0.1, "reason": "ok"}]\n```'
        # 需要 RankedCandidate 对象做输入
        class FakeCandidate:
            def __init__(self, aid):
                self.action_id = aid; self.tool_name = "tool_" + aid
        candidates = [FakeCandidate("a1")]
        result, err = _parse_laya_response(text, candidates)
        assert err == ''
        assert len(result) == 1
        assert result[0].action_id == "a1"

    def test_bad_json(self):
        """退步了会怎样：非法 JSON 应报 bad_json 错误。"""
        from vools.actus.ai.routing import _parse_laya_response, LAYARANK_ERR_BAD_JSON
        result, err = _parse_laya_response("not json", [])
        assert result == []
        assert LAYARANK_ERR_BAD_JSON in err

    def test_not_list(self):
        """退步了会怎样：非数组 JSON 应报 not_a_list 错误。"""
        from vools.actus.ai.routing import _parse_laya_response, LAYARANK_ERR_NOT_LIST
        result, err = _parse_laya_response('{"a": 1}', [])
        assert result == []
        assert LAYARANK_ERR_NOT_LIST in err

    def test_bad_item_skipped(self):
        """退步了会怎样：adjustment 非数字的项应被跳过。"""
        from vools.actus.ai.routing import _parse_laya_response, LAYARANK_ERR_BAD_ITEM
        class FakeCandidate:
            def __init__(self, aid):
                self.action_id = aid; self.tool_name = "tool_" + aid
        candidates = [FakeCandidate("a1")]
        text = '[{"action_id": "a1", "adjustment": "not_a_number"}, {"action_id": "a2", "adjustment": 0.2}]'
        result, err = _parse_laya_response(text, candidates)
        assert LAYARANK_ERR_BAD_ITEM in err
        # a1 被跳过，a2 不在 candidates 中，所以结果为空
        assert len(result) == 0

    def test_adjustment_clamped(self):
        """退步了会怎样：adjustment 应被限制在 -0.3~+0.3。"""
        from vools.actus.ai.routing import _parse_laya_response
        class FakeCandidate:
            def __init__(self, aid):
                self.action_id = aid; self.tool_name = "tool_" + aid
        candidates = [FakeCandidate("a1")]
        text = '[{"action_id": "a1", "adjustment": 1.0, "reason": "x"}]'
        result, err = _parse_laya_response(text, candidates)
        assert err == ''
        assert result[0].laya_boost <= 0.3


class TestFallbackChain:
    def test_initial_not_cooling(self):
        """退步了会怎样：初始状态不应在冷却。"""
        from vools.actus.ai.routing import FallbackChain
        fc = FallbackChain()
        assert fc.is_cooling("openai", "gpt-4o") is False

    def test_record_success_resets(self):
        """退步了会怎样：record_success 应清除失败计数和冷却。"""
        from vools.actus.ai.routing import FallbackChain
        fc = FallbackChain(fail_threshold=2, cooldown_secs=10)
        fc.record_failure("p", "m")
        fc.record_failure("p", "m")
        assert fc.is_cooling("p", "m") is True
        fc.record_success("p", "m")
        assert fc.is_cooling("p", "m") is False

    def test_cooldown_expires(self):
        """退步了会怎样：冷却到期后应恢复。"""
        from vools.actus.ai.routing import FallbackChain
        fc = FallbackChain(fail_threshold=1, cooldown_secs=-1)  # -1 → 立即过期
        fc.record_failure("p", "m")
        assert fc.is_cooling("p", "m") is False


class TestComputeFallbackChain:
    def test_excludes_primary(self):
        """退步了会怎样：主 provider 不应在 fallback 链中。"""
        from vools.actus.ai.routing import compute_fallback_chain
        all_providers = [("openai", "gpt-4o", None), ("deepseek", "chat", None)]
        chain = compute_fallback_chain("openai", "gpt-4o", all_providers)
        assert ("openai", "gpt-4o") not in chain
        assert ("deepseek", "chat") in chain

    def test_excludes_unhealthy(self):
        """退步了会怎样：不健康的 provider 不应在 fallback 链中。"""
        from vools.actus.ai.routing import compute_fallback_chain
        all_providers = [("openai", "gpt-4o", None), ("deepseek", "chat", None)]
        chain = compute_fallback_chain("openai", "gpt-4o", all_providers,
                                       unhealthy_ids=["deepseek:chat"])
        assert ("deepseek", "chat") not in chain


class TestRetryWithFallback:
    def test_primary_success(self):
        """退步了会怎样：主 provider 成功应立即返回。"""
        from vools.actus.ai.routing import retry_with_fallback
        calls = []
        def caller(provider, model, **kwargs):
            calls.append((provider, model))
            return (True, "result")
        ok, r, attempts = retry_with_fallback(caller, "openai", "gpt-4o")
        assert ok is True
        assert r == "result"
        assert len(calls) == 1  # 只调了主 provider

    def test_fallback_on_failure(self):
        """退步了会怎样：主 provider 失败应尝试 fallback。"""
        from vools.actus.ai.routing import retry_with_fallback
        calls = []
        def caller(provider, model, **kwargs):
            calls.append((provider, model))
            if provider == "openai": return (False, "error")
            return (True, "fallback_result")
        chain = [("deepseek", "chat")]
        ok, r, attempts = retry_with_fallback(caller, "openai", "gpt-4o", fallback_chain=chain, max_retries=0)
        assert ok is True
        assert r == "fallback_result"
        assert len(calls) == 2  # 主 + fallback

    def test_all_fail(self):
        """退步了会怎样：全部失败应返回 False。"""
        from vools.actus.ai.routing import retry_with_fallback
        def caller(provider, model, **kwargs):
            return (False, "error")
        chain = [("deepseek", "chat")]
        ok, r, attempts = retry_with_fallback(caller, "openai", "gpt-4o", fallback_chain=chain, max_retries=0)
        assert ok is False
        assert r is None


class TestCostPerformanceScore:
    def test_known_provider_model(self):
        """退步了会怎样：已知 provider/model 应有正确 score。"""
        from vools.actus.ai.routing import cost_performance_score
        score, price, rank = cost_performance_score("openai", "gpt-4o")
        assert price > 0
        assert rank > 0
        assert score > 0

    def test_unknown_provider(self):
        """退步了会怎样：未知 provider 应返回 0 score。"""
        from vools.actus.ai.routing import cost_performance_score
        score, price, rank = cost_performance_score("unknown", "model")
        assert score == 0.0

    def test_zero_price(self):
        """退步了会怎样：price=0 且 rank>0 时 score 应为 rank。"""
        from vools.actus.ai.routing import cost_performance_score
        score, price, rank = cost_performance_score("groq", "llama-3.1-8b")
        assert score == float(rank)  # price=0 → score = rank


class TestSortByCostPerf:
    def test_sorts_by_score(self):
        """退步了会怎样：应按 score 降序排列。"""
        from vools.actus.ai.routing import sort_by_cost_perf
        class FakeEntry:
            def __init__(self, tool_name):
                self.tool_name = tool_name
        entries = [FakeEntry("gpt-4o-mini"), FakeEntry("gpt-4o")]
        sorted_entries = sort_by_cost_perf(entries, provider="openai")
        # gpt-4o-mini 更便宜 → 应排前面
        assert sorted_entries[0].tool_name == "gpt-4o-mini"

    def test_empty_list(self):
        """退步了会怎样：空列表应返回空列表。"""
        from vools.actus.ai.routing import sort_by_cost_perf
        assert sort_by_cost_perf([], provider="openai") == []


class TestLastLayarankError:
    def test_default_empty(self):
        """退步了会怎样：默认应返回空字符串（无错误）。"""
        from vools.actus.ai.routing import last_layarank_error
        assert last_layarank_error() == ''


class TestLayarankByComplexity:
    def test_empty_candidates(self):
        """退步了会怎样：空候选应返回空列表，无错误。"""
        from vools.actus.ai.routing import layarank_by_complexity
        result, err = layarank_by_complexity(None, "intent", [], with_error=True)
        assert result == []
        assert err == ''

    def test_empty_intent(self):
        """退步了会怎样：空意图应返回空列表，无错误。"""
        from vools.actus.ai.routing import layarank_by_complexity
        result, err = layarank_by_complexity(None, "  ", [], with_error=True)
        assert result == []
        assert err == ''

    def test_client_throws(self):
        """退步了会怎样：client 抛异常应报 call_error。"""
        from vools.actus.ai.routing import layarank_by_complexity, LAYARANK_ERR_CALL

        class FakeCandidate:
            def __init__(self, aid):
                self.action_id = aid; self.tool_name = "tool_" + aid
                self.description = "desc"

        class BadClient:
            def complete(self, msgs, **kw):
                raise RuntimeError("boom")

        result, err = layarank_by_complexity(
            BadClient(), "intent", [FakeCandidate("a1")], with_error=True)
        assert result == []
        assert LAYARANK_ERR_CALL in err

    def test_client_failed_response(self):
        """退步了会怎样：client 返回 failed 响应应报 llm_error。"""
        from vools.actus.ai.routing import layarank_by_complexity, LAYARANK_ERR_LLM

        class FakeCandidate:
            def __init__(self, aid):
                self.action_id = aid; self.tool_name = "tool_" + aid
                self.description = "desc"

        class FailedClient:
            def complete(self, msgs, **kw):
                class Resp:
                    content = ""
                    failed = True
                    raw = {"error_kind": "quota"}
                return Resp()

        result, err = layarank_by_complexity(
            FailedClient(), "intent", [FakeCandidate("a1")], with_error=True)
        assert result == []
        assert LAYARANK_ERR_LLM in err

    def test_client_valid_response(self):
        """退步了会怎样：client 返回合法 JSON 应解析出结果。"""
        from vools.actus.ai.routing import layarank_by_complexity

        class FakeCandidate:
            def __init__(self, aid):
                self.action_id = aid; self.tool_name = "tool_" + aid
                self.description = "desc"

        class GoodClient:
            def complete(self, msgs, **kw):
                class Resp:
                    content = '[{"action_id": "a1", "adjustment": 0.1, "reason": "ok"}]'
                    failed = False
                return Resp()

        result, err = layarank_by_complexity(
            GoodClient(), "intent", [FakeCandidate("a1")], with_error=True)
        assert err == ''
        assert len(result) == 1
        assert result[0].action_id == "a1"

    def test_with_error_false(self):
        """退步了会怎样：with_error=False 应只返回 list（向后兼容）。"""
        from vools.actus.ai.routing import layarank_by_complexity
        result = layarank_by_complexity(None, "intent", [])
        assert isinstance(result, list)

    def test_timeout(self, monkeypatch):
        """退步了会怎样：超时应报 timeout 错误。"""
        from vools.actus.ai.routing import layarank_by_complexity, LAYARANK_ERR_TIMEOUT

        class FakeCandidate:
            def __init__(self, aid):
                self.action_id = aid; self.tool_name = "tool_" + aid
                self.description = "desc"

        class SlowClient:
            def complete(self, msgs, **kw):
                class Resp:
                    content = ""
                    failed = False
                return Resp()

        # mock time.time 返回递增值：start=0，complete 后返回 10
        times = iter([0.0, 10.0])
        monkeypatch.setattr("time.time", lambda: next(times))

        result, err = layarank_by_complexity(
            SlowClient(), "intent", [FakeCandidate("a1")],
            timeout_sec=3.0, with_error=True)
        assert result == []
        assert LAYARANK_ERR_TIMEOUT in err

    def test_empty_response(self, monkeypatch):
        """退步了会怎样：空响应应报 empty_response 错误。"""
        from vools.actus.ai.routing import layarank_by_complexity, LAYARANK_ERR_EMPTY

        class FakeCandidate:
            def __init__(self, aid):
                self.action_id = aid; self.tool_name = "tool_" + aid
                self.description = "desc"

        class EmptyClient:
            def complete(self, msgs, **kw):
                class Resp:
                    content = ""
                    failed = False
                return Resp()

        result, err = layarank_by_complexity(
            EmptyClient(), "intent", [FakeCandidate("a1")], with_error=True)
        assert result == []
        assert LAYARANK_ERR_EMPTY in err

    def test_none_response(self):
        """退步了会怎样：resp is None 应报 llm_error。"""
        from vools.actus.ai.routing import layarank_by_complexity, LAYARANK_ERR_LLM

        class FakeCandidate:
            def __init__(self, aid):
                self.action_id = aid; self.tool_name = "tool_" + aid
                self.description = "desc"

        class NoneClient:
            def complete(self, msgs, **kw):
                return None

        result, err = layarank_by_complexity(
            NoneClient(), "intent", [FakeCandidate("a1")], with_error=True)
        assert result == []
        assert LAYARANK_ERR_LLM in err

    def test_failed_response_with_raw(self):
        """退步了会怎样：failed 响应带 raw error_kind 应报 llm_error。"""
        from vools.actus.ai.routing import layarank_by_complexity, LAYARANK_ERR_LLM

        class FakeCandidate:
            def __init__(self, aid):
                self.action_id = aid; self.tool_name = "tool_" + aid
                self.description = "desc"

        class FailedRawClient:
            def complete(self, msgs, **kw):
                class Resp:
                    content = ""
                    failed = True
                    raw = {"error_kind": "auth_failed"}
                return Resp()

        result, err = layarank_by_complexity(
            FailedRawClient(), "intent", [FakeCandidate("a1")], with_error=True)
        assert result == []
        assert LAYARANK_ERR_LLM in err
        assert "auth_failed" in err

    def test_failed_response_no_raw(self):
        """退步了会怎样：failed 响应无 raw 应报 llm_error。"""
        from vools.actus.ai.routing import layarank_by_complexity, LAYARANK_ERR_LLM

        class FakeCandidate:
            def __init__(self, aid):
                self.action_id = aid; self.tool_name = "tool_" + aid
                self.description = "desc"

        class FailedNoRawClient:
            def complete(self, msgs, **kw):
                class Resp:
                    content = ""
                    failed = True
                    raw = None
                return Resp()

        result, err = layarank_by_complexity(
            FailedNoRawClient(), "intent", [FakeCandidate("a1")], with_error=True)
        assert result == []
        assert LAYARANK_ERR_LLM in err
