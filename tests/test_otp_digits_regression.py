# -*- coding: utf-8 -*-
"""回归测试：OTP 动态码位数一致（BUG-201）。

generate_dynamic_code 支持 digits 参数（默认 6），但 verify_dynamic_code 曾硬编码
只接受 6 位，导致 digits != 6 生成的码永远无法验证。现长度校验与 _hotp_truncate
的 digits 语义对齐（1..10 位）。
"""

from vools.security.otp import generate_dynamic_code, verify_dynamic_code

SEED = bytes(range(32))


class TestOtpDigitsConsistency:
    """非 6 位动态码必须可正常验证（BUG-201）。"""

    def test_digits_6_verifies(self):
        code = generate_dynamic_code(SEED, digits=6)
        assert len(code) == 6
        assert verify_dynamic_code(code, SEED) is True

    def test_digits_8_verifies(self):
        code = generate_dynamic_code(SEED, digits=8)
        assert len(code) == 8
        assert verify_dynamic_code(code, SEED) is True

    def test_digits_10_verifies(self):
        code = generate_dynamic_code(SEED, digits=10)
        assert len(code) == 10
        assert verify_dynamic_code(code, SEED) is True


class TestOtpVerifyRejections:
    """无效码仍须被拒绝（保留原校验语义）。"""

    def test_empty_rejected(self):
        assert verify_dynamic_code("", SEED) is False

    def test_non_digit_rejected(self):
        assert verify_dynamic_code("abcdef", SEED) is False

    def test_wrong_code_rejected(self):
        # 任意错误码在宽窗口内也应被拒绝
        assert verify_dynamic_code("000000", SEED, window=5) is False

    def test_overlong_rejected(self):
        # 超过 10 位视为滥用，拒绝
        assert verify_dynamic_code("1" * 11, SEED) is False