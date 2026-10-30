# -*- coding: utf-8 -*-
"""selfheal.py 契约测试 (Round 61)。

覆盖：CircuitBreaker 全状态机（CLOSED/OPEN/HALF_OPEN 转移、半开配额、
参数校验）、RetryPolicy（校验/should_retry/get_delay）、ErrorLearner
（learn 去重/截断/分辨率首写、suggest/get_top_patterns/stats）、
SelfHealingEngine（get_breaker 缓存、拒绝、成功、失败重试、异常路径、
stats/reset）、单例。

BUG-SH1（佐证，未修）：SelfHealingEngine.execute() 的失败路径必然崩——
重试循环 `for attempt in range(max_retries+1)` 从 attempt=0 开始，而
should_retry()/get_delay() 内的 _require_attempt() 要求 ≥1：第一次
should_retry(code, 0) 抛 ValueError 被 except Exception 吞掉、改为
error_code='exception'，随后 except 块内的第二次 should_retry("exception", 0)
再次抛 ValueError —— 这次在 except 块里，直接冲出 execute()。后果：
任何失败的 func 都让 execute 抛裸 ValueError（而不是返回 failed dict），
retried 计数永远不增长，time.sleep 永不执行，ErrorLearner 的 suggest
返回值（failed 结果里的 suggestion 字段）不可达。
"""

import pytest

from vools.actus import selfheal as smod
from vools.actus.selfheal import (
    CircuitBreaker,
    CircuitState,
    ErrorLearner,
    ErrorPattern,
    RetryPolicy,
    SelfHealingEngine,
    get_self_healing_engine,
)


# ---------------------------------------------------------------- breaker

class TestCircuitBreaker:
    def test_initial_state(self):
        cb = CircuitBreaker()
        assert cb.state is CircuitState.CLOSED
        assert cb.failure_count == 0
        assert cb.success_count == 0
        assert cb.last_failure_time == 0.0

    @pytest.mark.parametrize('kwargs', [
        {'failure_threshold': 0}, {'failure_threshold': -1},
        {'failure_threshold': 1.5}, {'failure_threshold': True},
        {'recovery_timeout': 0}, {'recovery_timeout': -5},
        {'recovery_timeout': True},
        {'half_open_max_calls': 0}, {'half_open_max_calls': True},
    ])
    def test_param_validation(self, kwargs):
        with pytest.raises(ValueError):
            CircuitBreaker(**kwargs)

    def test_opens_at_threshold(self):
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure()
        assert cb.state is CircuitState.CLOSED
        cb.record_failure()
        assert cb.state is CircuitState.OPEN
        assert cb.last_failure_time > 0

    def test_open_blocks_within_timeout(self):
        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure()
        assert cb.can_execute() is False  # 刚失败，窗口未过

    def test_open_to_half_open_after_timeout(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=10)
        cb.record_failure()
        cb.last_failure_time -= 20  # 伪造超时
        assert cb.can_execute() is True
        assert cb.state is CircuitState.HALF_OPEN
        assert cb._half_open_calls == 0

    def test_half_open_quota(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=10,
                            half_open_max_calls=2)
        cb.record_failure()
        cb.last_failure_time -= 20
        # BUG-SH2 佐证：状态转移的那次试探不消耗配额 —— max_calls=2 时
        # 实际放行 3 次（转移 True + 两次自增），与「半开时允许的最大试探次数」
        # 的文档语义差 1
        assert cb.can_execute() is True   # OPEN→HALF_OPEN 转移（不计数）
        assert cb.can_execute() is True   # 配额 1/2
        assert cb.can_execute() is True   # 配额 2/2
        assert cb.can_execute() is False  # 配额用尽

    def test_half_open_success_closes(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=10)
        cb.record_failure()
        cb.last_failure_time -= 20
        assert cb.can_execute() is True
        cb.record_success()
        assert cb.state is CircuitState.CLOSED
        assert cb.failure_count == 0
        assert cb.success_count == 0

    def test_half_open_failure_reopens(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=10)
        cb.record_failure()
        cb.last_failure_time -= 20
        cb.can_execute()  # HALF_OPEN
        cb.record_failure()
        assert cb.state is CircuitState.OPEN

    def test_success_in_closed_decrements(self):
        cb = CircuitBreaker(failure_threshold=5)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.failure_count == 1
        assert cb.success_count == 1

    def test_success_floor_zero(self):
        cb = CircuitBreaker()
        cb.record_success()
        assert cb.failure_count == 0  # max(0, -1)

    def test_state_constants(self):
        assert (CircuitState.CLOSED, CircuitState.OPEN, CircuitState.HALF_OPEN) == \
               ('closed', 'open', 'half_open')


# ---------------------------------------------------------------- retry policy

class TestRetryPolicy:
    @pytest.mark.parametrize('kwargs', [
        {'max_retries': -1}, {'max_retries': True},
        {'base_delay': -1}, {'base_delay': 'x'},
        {'max_delay': -1},
        {'backoff_factor': 0.5}, {'backoff_factor': 'x'},
    ])
    def test_param_validation(self, kwargs):
        with pytest.raises(ValueError):
            RetryPolicy(**kwargs)

    def test_defaults(self):
        p = RetryPolicy()
        assert p.max_retries == 3
        assert p.base_delay == 0.5
        assert p.max_delay == 30.0
        assert p.backoff_factor == 2.0
        assert p.jitter is True
        assert p.retry_on == ('timeout', 'connection', 'rate_limit')

    def test_should_retry_exhausted(self):
        p = RetryPolicy(max_retries=2)
        assert p.should_retry('timeout', 3) is False
        assert p.should_retry('timeout', 2) is True

    def test_should_retry_empty_set_always_true(self):
        p = RetryPolicy(retry_on=())
        assert p.should_retry('anything', 1) is True

    def test_should_retry_membership(self):
        p = RetryPolicy()
        assert p.should_retry('timeout', 1) is True
        assert p.should_retry('auth', 1) is False

    @pytest.mark.parametrize('bad', [0, -1, 'x', 1.5, True])
    def test_require_attempt_rejects(self, bad):
        p = RetryPolicy()
        with pytest.raises(ValueError):
            p.should_retry('timeout', bad)

    def test_get_delay_exact_without_jitter(self):
        p = RetryPolicy(base_delay=1.0, backoff_factor=2.0, max_delay=100.0,
                        jitter=False)
        assert p.get_delay(1) == 2.0
        assert p.get_delay(2) == 4.0

    def test_get_delay_capped(self):
        p = RetryPolicy(base_delay=10.0, backoff_factor=3.0, max_delay=15.0,
                        jitter=False)
        assert p.get_delay(2) == 15.0

    def test_get_delay_jitter_range(self):
        p = RetryPolicy(base_delay=1.0, backoff_factor=1.0, max_delay=100.0,
                        jitter=True)
        for _ in range(20):
            d = p.get_delay(1)
            assert 0.5 <= d <= 1.0

    def test_get_delay_rejects_bad_attempt(self):
        with pytest.raises(ValueError):
            RetryPolicy().get_delay(0)


# ---------------------------------------------------------------- learner

class TestErrorLearner:
    def test_learn_new_pattern(self):
        l = ErrorLearner()
        l.learn('timeout', 'call timed out', '检查网络')
        p = l._patterns['timeout']
        assert p.code == 'timeout'
        assert p.message == 'call timed out'
        assert p.count == 1
        assert p.resolution == '检查网络'
        assert p.first_seen == p.last_seen

    def test_learn_truncates_message_200(self):
        l = ErrorLearner()
        l.learn('x', 'a' * 500)
        assert l._patterns['x'].message == 'a' * 200

    def test_learn_repeated_counts(self):
        l = ErrorLearner()
        l.learn('t', 'msg')
        l.learn('t', 'msg')
        assert l._patterns['t'].count == 2

    def test_learn_resolution_first_write_wins(self):
        l = ErrorLearner()
        l.learn('t', 'm', '策略A')
        l.learn('t', 'm', '策略B')  # 已有 resolution 不覆盖
        assert l._patterns['t'].resolution == '策略A'

    def test_learn_empty_resolution_keeps_empty(self):
        l = ErrorLearner()
        l.learn('t', 'm')
        assert l._patterns['t'].resolution == ''

    def test_learn_resolution_added_later(self):
        # 首次无 resolution、重复学习时补上 → 写入
        l = ErrorLearner()
        l.learn('t', 'm')
        l.learn('t', 'm', '后补策略')
        assert l._patterns['t'].resolution == '后补策略'

    def test_suggest(self):
        l = ErrorLearner()
        assert l.suggest('nope') is None
        l.learn('t', 'm')
        assert l.suggest('t') is None  # 无 resolution
        l.learn('r', 'm', '重试')
        assert l.suggest('r') == '重试'

    def test_get_top_patterns_sorted_and_limited(self):
        l = ErrorLearner()
        for code, n in [('a', 1), ('b', 3), ('c', 2)]:
            for _ in range(n):
                l.learn(code, 'm')
        top = l.get_top_patterns(limit=2)
        assert [x['code'] for x in top] == ['b', 'c']
        assert top[0]['count'] == 3
        assert set(top[0]) == {'code', 'message', 'count', 'last_seen', 'resolution'}

    def test_stats(self):
        l = ErrorLearner()
        l.learn('a', 'm')
        l.learn('a', 'm')
        l.learn('b', 'm')
        assert l.stats() == {'total_patterns': 2, 'total_errors': 3}

    def test_error_pattern_defaults(self):
        p = ErrorPattern(code='c', message='m')
        assert p.count == 0 and p.first_seen == 0.0 and p.resolution == ''


# ---------------------------------------------------------------- engine

def _ok():
    return {'status': 'ok', 'data': 1}


class TestSelfHealingEngine:
    def test_get_breaker_cached(self):
        e = SelfHealingEngine()
        assert e.get_breaker('a') is e.get_breaker('a')

    def test_execute_rejected_when_open(self):
        e = SelfHealingEngine()
        b = e.get_breaker('a')
        for _ in range(b.failure_threshold):
            b.record_failure()
        calls = []

        r = e.execute('a', lambda: calls.append(1) or _ok())
        assert r == {'status': 'rejected',
                     'error': '动作 a 已熔断，请稍后重试',
                     'error_code': 'circuit_open'}
        assert calls == []  # func 未被执行
        assert e._stats['rejected'] == 1
        assert e._stats['total'] == 1

    def test_execute_success_first_try(self):
        e = SelfHealingEngine()
        r = e.execute('a', _ok)
        assert r['status'] == 'ok'
        assert e._stats == {'total': 1, 'success': 1, 'failed': 0,
                            'retried': 0, 'rejected': 0}

    def test_execute_failure_raises_valueerror(self):
        # BUG-SH1 佐证：失败路径必崩（attempt=0 过不了 _require_attempt）
        e = SelfHealingEngine()
        p = RetryPolicy(max_retries=2, base_delay=0)
        with pytest.raises(ValueError):
            e.execute('a', lambda: {'status': 'failed', 'error': 'boom',
                                    'error_code': 'timeout'}, p)

    def test_execute_exception_raises_valueerror(self):
        # BUG-SH1 补充：func 抛异常同样崩在 except 块的第二次 should_retry
        e = SelfHealingEngine()
        p = RetryPolicy(max_retries=1, base_delay=0)

        def boom():
            raise RuntimeError('exploded')

        with pytest.raises(ValueError):
            e.execute('a', boom, p)

    def test_breaker_double_counts_failure(self):
        # BUG-SH1 附带伤害：except 块把同一次失败又 record_failure 一次 ——
        # 每次失败对断路器计 2 次（先在 try 里、再在 except 里），熔断阈值
        # 实际按一半生效
        e = SelfHealingEngine()
        with pytest.raises(ValueError):
            e.execute('a', lambda: {'status': 'failed', 'error': 'x',
                                    'error_code': 'timeout'})
        assert e.get_breaker('a').failure_count == 2  # 双计数
        assert 'timeout' in e.learner._patterns
        assert 'exception' in e.learner._patterns  # 被 except 改写

    def test_stats_shape(self):
        e = SelfHealingEngine()
        e.execute('a', _ok)
        s = e.stats()
        assert s['total'] == 1 and s['success'] == 1
        assert s['learner'] == {'total_patterns': 0, 'total_errors': 0}
        assert s['active_breakers'] == 1

    def test_reset(self):
        e = SelfHealingEngine()
        e.execute('a', _ok)
        e.reset()
        assert e.breakers == {}
        assert e._stats == {'total': 0, 'success': 0, 'failed': 0,
                            'retried': 0, 'rejected': 0}

    def test_custom_policy_used(self):
        e = SelfHealingEngine()
        p = RetryPolicy(max_retries=0)
        assert e.execute('a', _ok, p)['status'] == 'ok'


# ---------------------------------------------------------------- singleton

def test_singleton():
    assert get_self_healing_engine() is get_self_healing_engine()
    assert isinstance(get_self_healing_engine(), SelfHealingEngine)


def test_all_exports():
    assert set(smod.__all__) == {'CircuitBreaker', 'CircuitState', 'ErrorLearner',
                                 'ErrorPattern', 'RetryPolicy', 'SelfHealingEngine',
                                 'get_self_healing_engine', 'logger'}
