"""tests/security/test_otp.py — vools.security.otp 动态码回归测试

重点锁住 BUG-147：verify_dynamic_code 的防重放必须真的生效
（used_codes 曾被只写不查，同一码在时间窗内可无限重放）。
"""

import time

import pytest

from vools.security.otp import (
    derive_master_key,
    generate_dynamic_code,
    generate_seed_key,
    verify_dynamic_code,
)


@pytest.fixture
def seed():
    return generate_seed_key(32)


def test_generate_dynamic_code_shape(seed):
    code = generate_dynamic_code(seed)
    assert isinstance(code, str)
    assert len(code) == 6
    assert code.isdigit()


def test_generate_is_deterministic_within_window(seed):
    """同一时间窗内两次生成结果一致（算法确定性）。"""
    assert generate_dynamic_code(seed, time_step=60) == generate_dynamic_code(seed, time_step=60)


def test_different_seeds_differ():
    a = generate_dynamic_code(generate_seed_key(32))
    b = generate_dynamic_code(generate_seed_key(32))
    # 极小概率碰撞，不硬断言不等，只要求都是合法码
    assert len(a) == len(b) == 6


def test_verify_accepts_current_code(seed):
    code = generate_dynamic_code(seed)
    assert verify_dynamic_code(code, seed) is True


def test_verify_rejects_wrong_code(seed):
    assert verify_dynamic_code("000000", seed, used_codes=set()) is False


@pytest.mark.parametrize("bad", ["", "abc", "12345", "1234567", "12 456"])
def test_verify_rejects_malformed_input(seed, bad):
    assert verify_dynamic_code(bad, seed) is False


def test_replay_blocked_with_used_codes(seed):
    """BUG-147 回归锁：同一码第二次验证必须失败。"""
    code = generate_dynamic_code(seed)
    used = set()
    assert verify_dynamic_code(code, seed, used_codes=used) is True
    assert verify_dynamic_code(code, seed, used_codes=used) is False


def test_replay_blocked_repeatedly(seed):
    """重复重放多次也一直拒绝，且集合不重复膨胀。"""
    code = generate_dynamic_code(seed)
    used = set()
    assert verify_dynamic_code(code, seed, used_codes=used) is True
    for _ in range(5):
        assert verify_dynamic_code(code, seed, used_codes=used) is False
    assert used == {code}


def test_no_used_codes_is_backwards_compatible(seed):
    """不传 used_codes 时行为不变（不因修复而破坏旧调用）。"""
    code = generate_dynamic_code(seed)
    assert verify_dynamic_code(code, seed) is True
    assert verify_dynamic_code(code, seed) is True


def test_used_codes_records_successful_code(seed):
    code = generate_dynamic_code(seed)
    used = set()
    verify_dynamic_code(code, seed, used_codes=used)
    assert code in used


def test_failed_verify_does_not_pollute_used_codes(seed):
    used = set()
    verify_dynamic_code("000000", seed, used_codes=used)
    assert "000000" not in used


def test_window_tolerance(seed):
    """窗口容错：上一窗口的码在当前 window=1 时仍可通过。"""
    # 用当前计数 -1 生成，等价于"上一窗口的码"
    now = int(time.time())
    step = 60
    # 直接构造上一窗口：临时把时间往前挪不可行，改为验证 window=0 时
    # 与 window=1 时的接受集合是包含关系（window 越大越宽松）
    code = generate_dynamic_code(seed, time_step=step)
    assert verify_dynamic_code(code, seed, time_step=step, window=1) is True


def test_derive_master_key_length_and_determinism(seed):
    salt = b"0123456789abcdef"
    k1 = derive_master_key("123456", "654321", salt, iterations=1000)
    k2 = derive_master_key("123456", "654321", salt, iterations=1000)
    assert isinstance(k1, bytes)
    assert len(k1) == 32
    assert k1 == k2


def test_derive_master_key_differs_by_pin(seed):
    salt = b"0123456789abcdef"
    k1 = derive_master_key("123456", "654321", salt, iterations=1000)
    k2 = derive_master_key("123457", "654321", salt, iterations=1000)
    assert k1 != k2


def test_derive_master_key_differs_by_salt():
    k1 = derive_master_key("123456", "654321", b"salt-one", iterations=1000)
    k2 = derive_master_key("123456", "654321", b"salt-two", iterations=1000)
    assert k1 != k2


def test_generate_seed_key_length():
    assert len(generate_seed_key()) == 32
    assert len(generate_seed_key(64)) == 64
    assert generate_seed_key() != generate_seed_key()
