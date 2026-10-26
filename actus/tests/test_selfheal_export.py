# -*- coding: utf-8 -*-
"""selfheal 与 export 的入参边界（扫这两个 blind spot 发现）。

selfheal（熔断器/重试策略）：
  - `CircuitBreaker(recovery_timeout=-5)` 被静默收下 —— 负超时让
    `time.time() - last_failure_time >= timeout` 恒真，断路器**永远停在半开、
    再也不熔断**（保护静默失效）
  - `CircuitBreaker(failure_threshold=0)` / `RetryPolicy(max_retries='x')` 同样零校验
  - `get_delay('x')` 在 `**` 处抛裸 TypeError、`get_delay(-1)` 静默算出负指数延迟

export：
  - `export_to_json('abc')` 把字符串当记录集序列化成 `"abc"`
  - `export_to_csv(None)` / `export_to_markdown(None)` 抛裸 TypeError
  - `load_run_history(limit='x')` 在 `limit > 0` 处抛裸 TypeError
  - **`export_history(format_='zzz')` 静默回退成 json** —— 要 csv 却拿到 JSON
"""
import pytest

from vools.actus import export, selfheal


# --------------------------------------------------------------------------
# CircuitBreaker
# --------------------------------------------------------------------------
@pytest.mark.parametrize("kwargs", [
    {"recovery_timeout": -5},
    {"recovery_timeout": 0},
    {"failure_threshold": 0},
    {"failure_threshold": -1},
    {"half_open_max_calls": 0},
])
def test_circuit_breaker_rejects_bad_params(kwargs):
    with pytest.raises(ValueError):
        selfheal.CircuitBreaker(**kwargs)


def test_circuit_breaker_opens_after_threshold():
    cb = selfheal.CircuitBreaker(failure_threshold=2)
    assert cb.can_execute() is True
    cb.record_failure()
    cb.record_failure()
    assert cb.can_execute() is False, "达到阈值后必须熔断"


def test_circuit_breaker_negative_timeout_would_never_block():
    """负超时曾被静默接受 → 永不熔断。现在必须在构造期拒绝。"""
    with pytest.raises(ValueError) as exc:
        selfheal.CircuitBreaker(recovery_timeout=-1)
    assert "永不熔断" in str(exc.value) or "recovery_timeout" in str(exc.value)


# --------------------------------------------------------------------------
# RetryPolicy
# --------------------------------------------------------------------------
@pytest.mark.parametrize("kwargs", [
    {"max_retries": -1},
    {"max_retries": "x"},
    {"base_delay": -1},
    {"backoff_factor": 0.5},
    {"backoff_factor": "x"},
])
def test_retry_policy_rejects_bad_params(kwargs):
    with pytest.raises(ValueError):
        selfheal.RetryPolicy(**kwargs)


def test_retry_policy_valid():
    rp = selfheal.RetryPolicy(max_retries=3, base_delay=0.5, backoff_factor=2.0)
    assert rp.get_delay(1) > 0
    assert rp.should_retry("timeout", 1) is True
    assert rp.should_retry("timeout", 4) is False   # 超过 max_retries


@pytest.mark.parametrize("attempt", [0, -1, "x", None])
def test_delay_and_retry_require_positive_attempt(attempt):
    rp = selfheal.RetryPolicy()
    with pytest.raises(ValueError):
        rp.get_delay(attempt)
    with pytest.raises(ValueError):
        rp.should_retry("timeout", attempt)


# --------------------------------------------------------------------------
# export：records 形态
# --------------------------------------------------------------------------
@pytest.mark.parametrize("bad", [None, "abc", 123, {"a": 1}])
@pytest.mark.parametrize("fn", ["export_to_json", "export_to_csv",
                                "export_to_markdown", "export_to_html"])
def test_exporters_reject_non_list_records(bad, fn):
    with pytest.raises(TypeError) as exc:
        getattr(export, fn)(bad)
    assert "dict 列表" in str(exc.value), exc.value


def test_exporters_reject_non_dict_items():
    with pytest.raises(TypeError) as exc:
        export.export_to_json([1, 2])
    assert "必须是 dict" in str(exc.value), exc.value


def test_markdown_html_title_must_be_str():
    with pytest.raises(TypeError):
        export.export_to_markdown([], title=123)
    with pytest.raises(TypeError):
        export.export_to_html([], title=None)


def test_exporters_happy_path():
    recs = [{"timestamp": "t1", "action_id": "a", "status": "ok", "duration": 1}]
    assert "a" in export.export_to_json(recs)
    assert "timestamp" in export.export_to_csv(recs)
    assert "# 动作执行历史" in export.export_to_markdown(recs)
    assert "<html" in export.export_to_html(recs)


# --------------------------------------------------------------------------
# export：load_run_history / export_history
# --------------------------------------------------------------------------
@pytest.mark.parametrize("bad", [-1, "x", None, True])
def test_load_history_rejects_bad_limit(tmp_path, bad):
    with pytest.raises(ValueError):
        export.load_run_history(str(tmp_path), limit=bad)


def test_load_history_missing_file_returns_empty(tmp_path):
    assert export.load_run_history(str(tmp_path), limit=0) == []


def test_export_history_unknown_format_is_rejected(tmp_path):
    """此前未知格式静默回退成 json。"""
    with pytest.raises(ValueError) as exc:
        export.export_history(str(tmp_path), format_="zzz")
    assert "未知导出格式" in str(exc.value), exc.value


@pytest.mark.parametrize("fmt", ["json", "csv", "markdown", "md", "html"])
def test_export_history_accepts_known_formats(tmp_path, fmt):
    # 无数据时返回 None（既有行为）
    assert export.export_history(str(tmp_path), format_=fmt) is None
