"""selfheal.py — 自愈与可靠性引擎 (Phase K)。

三大核心能力:
1. Circuit Breaker — 失败累积后自动熔断，防止雪崩
2. Smart Retry — 指数退避 + 抖动 + 超时递增
3. Error Pattern Learning — 错误归类，推荐修复策略
"""

import time
import random
import logging
from typing import Dict, List, Optional, Callable, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ── 1. Circuit Breaker ──────────────────────────────────────────────────────

class CircuitState:
    """断路器状态。"""
    CLOSED = "closed"       # 正常
    OPEN = "open"           # 熔断（拒绝）
    HALF_OPEN = "half_open" # 试探（允许少量通过）


@dataclass
class CircuitBreaker:
    """断路器。

    当失败次数达到阈值时打开；经过恢复窗口后进入半开试探；
    试探成功则闭合，失败则重新打开。
    """

    failure_threshold: int = 5
    recovery_timeout: float = 30.0      # 熔断后等待恢复的时间（秒）
    half_open_max_calls: int = 1        # 半开时允许的最大试探次数

    def __post_init__(self):
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0.0
        self._half_open_calls = 0

    def can_execute(self) -> bool:
        """检查是否允许执行。"""
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
                logger.info(f"断路器进入半开状态")
                return True
            return False

        # HALF_OPEN
        if self._half_open_calls < self.half_open_max_calls:
            self._half_open_calls += 1
            return True
        return False

    def record_success(self):
        """记录成功。"""
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.success_count = 0
            logger.info(f"断路器闭合")
        else:
            self.failure_count = max(0, self.failure_count - 1)
            self.success_count += 1

    def record_failure(self):
        """记录失败。"""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            logger.warning(f"断路器重新打开（半开试探失败）")
        elif self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(f"断路器打开（连续失败 {self.failure_count} 次）")


# ── 2. Smart Retry ─────────────────────────────────────────────────────────

@dataclass
class RetryPolicy:
    """重试策略。"""

    max_retries: int = 3
    base_delay: float = 0.5         # 初始延迟（秒）
    max_delay: float = 30.0         # 最大延迟
    backoff_factor: float = 2.0     # 指数退避乘数
    jitter: bool = True             # 是否加随机抖动
    retry_on: Tuple[str, ...] = ("timeout", "connection", "rate_limit")  # 重试的错误类型

    def should_retry(self, error_code: str, attempt: int) -> bool:
        """判断是否重试。"""
        if attempt >= self.max_retries:
            return False
        if not self.retry_on:
            return True
        return error_code in self.retry_on

    def get_delay(self, attempt: int) -> float:
        """计算第 attempt 次的延迟。"""
        delay = self.base_delay * (self.backoff_factor ** attempt)
        delay = min(delay, self.max_delay)
        if self.jitter:
            delay *= (0.5 + random.random() * 0.5)  # 50%-100%
        return delay


# ── 3. Error Pattern ───────────────────────────────────────────────────────

@dataclass
class ErrorPattern:
    """错误模式记录。"""

    code: str
    message: str
    count: int = 0
    first_seen: float = 0.0
    last_seen: float = 0.0
    resolution: str = ""            # 已知的修复策略


class ErrorLearner:
    """错误模式学习器。

    归类错误消息，统计频次，推荐已知修复策略。
    """

    def __init__(self):
        self._patterns: Dict[str, ErrorPattern] = {}

    def learn(self, error_code: str, error_message: str, resolution: str = ""):
        """学习一个错误。"""
        key = error_code
        now = time.time()

        if key in self._patterns:
            p = self._patterns[key]
            p.count += 1
            p.last_seen = now
            if resolution and not p.resolution:
                p.resolution = resolution
        else:
            self._patterns[key] = ErrorPattern(
                code=error_code,
                message=error_message[:200],
                count=1,
                first_seen=now,
                last_seen=now,
                resolution=resolution,
            )

    def suggest(self, error_code: str) -> Optional[str]:
        """根据错误代码推荐修复策略。"""
        p = self._patterns.get(error_code)
        if p and p.resolution:
            return p.resolution
        return None

    def get_top_patterns(self, limit: int = 10) -> List[dict]:
        """获取最常见的错误模式。"""
        sorted_p = sorted(self._patterns.values(), key=lambda x: x.count, reverse=True)
        return [
            {
                "code": p.code,
                "message": p.message,
                "count": p.count,
                "last_seen": p.last_seen,
                "resolution": p.resolution,
            }
            for p in sorted_p[:limit]
        ]

    def stats(self) -> dict:
        """统计信息。"""
        return {
            "total_patterns": len(self._patterns),
            "total_errors": sum(p.count for p in self._patterns.values()),
        }


# ── 4. Self-Healing Engine ─────────────────────────────────────────────────

class SelfHealingEngine:
    """自愈引擎。

    整合断路器、智能重试、错误学习。
    用法:
        engine = SelfHealingEngine()
        result = engine.execute(action_id, run_func)
    """

    def __init__(self):
        self.breakers: Dict[str, CircuitBreaker] = {}
        self.learner = ErrorLearner()
        self.default_policy = RetryPolicy()
        self._stats = {"total": 0, "success": 0, "failed": 0, "retried": 0, "rejected": 0}

    def get_breaker(self, action_id: str) -> CircuitBreaker:
        """获取动作的断路器。"""
        if action_id not in self.breakers:
            self.breakers[action_id] = CircuitBreaker()
        return self.breakers[action_id]

    def execute(self, action_id: str, func: Callable, policy: RetryPolicy = None) -> dict:
        """执行动作，带自愈能力。

        参数:
            action_id: 动作 ID
            func: 执行函数 (返回 dict: {status, data, error})
            policy: 重试策略（可选，使用默认）

        返回:
            执行结果 dict。
        """
        self._stats["total"] += 1
        policy = policy or self.default_policy
        breaker = self.get_breaker(action_id)

        # 断路器检查
        if not breaker.can_execute():
            self._stats["rejected"] += 1
            return {
                "status": "rejected",
                "error": f"动作 {action_id} 已熔断，请稍后重试",
                "error_code": "circuit_open",
            }

        last_error = None
        last_error_code = ""

        for attempt in range(policy.max_retries + 1):
            try:
                result = func()

                if result.get("status") == "ok":
                    breaker.record_success()
                    self._stats["success"] += 1
                    return result

                # 执行失败
                error_code = result.get("error_code", "unknown")
                error_msg = result.get("error", "")
                last_error = error_msg
                last_error_code = error_code
                breaker.record_failure()
                self.learner.learn(error_code, error_msg)

                if not policy.should_retry(error_code, attempt):
                    break

                delay = policy.get_delay(attempt)
                self._stats["retried"] += 1
                logger.info(f"重试 {action_id} 第 {attempt + 1} 次，延迟 {delay:.1f}s")
                time.sleep(delay)

            except Exception as e:
                last_error = str(e)
                last_error_code = "exception"
                breaker.record_failure()
                self.learner.learn("exception", last_error)
                if not policy.should_retry("exception", attempt):
                    break
                delay = policy.get_delay(attempt)
                self._stats["retried"] += 1
                time.sleep(delay)

        self._stats["failed"] += 1
        suggestion = self.learner.suggest(last_error_code)
        return {
            "status": "failed",
            "error": last_error,
            "error_code": last_error_code,
            "retried": self._stats["retried"],
            "suggestion": suggestion,
        }

    def stats(self) -> dict:
        """获取自愈引擎统计。"""
        return {
            **self._stats,
            "learner": self.learner.stats(),
            "active_breakers": len(self.breakers),
        }

    def reset(self):
        """重置状态。"""
        self.breakers.clear()
        self._stats = {"total": 0, "success": 0, "failed": 0, "retried": 0, "rejected": 0}


# ── 5. Singleton ───────────────────────────────────────────────────────────

_engine = SelfHealingEngine()


def get_self_healing_engine() -> SelfHealingEngine:
    """获取全局自愈引擎。"""
    return _engine


__all__ = [
    'CircuitBreaker',
    'CircuitState',
    'ErrorLearner',
    'ErrorPattern',
    'RetryPolicy',
    'SelfHealingEngine',
    'get_self_healing_engine',
    'logger'
]
